"""
Los simuladores deben rechazar lo que un procesador o simulador real rechaza:
si dejaran pasar un error, la bateria dejaria de ser una prueba.
"""

import pytest

from simulador import aarch64, mips


def mips_main(cuerpo: str, datos: str = "") -> str:
    return f".data\n{datos}\n.text\nmain:\n{cuerpo}\n li $v0, 10\n syscall\n"


def arm_main(cuerpo: str, datos: str = "") -> str:
    return f".data\n{datos}\n.text\n_start:\n{cuerpo}\n mov x0, #0\n mov x8, #93\n svc #0\n"


# --- MIPS -----------------------------------------------------------------


def test_mips_aritmetica_e_impresion():
    r = mips.simular(mips_main(" li $a0, 40\n addiu $a0, $a0, 2\n li $v0, 1\n syscall"))
    assert r.salida == "42"


def test_mips_print_string_y_char():
    datos = 's: .asciiz "hola"'
    r = mips.simular(mips_main(" la $a0, s\n li $v0, 4\n syscall\n li $a0, 33\n li $v0, 11\n syscall", datos))
    assert r.salida == "hola!"


def test_mips_exit_con_codigo():
    assert mips.simular(mips_main(" li $a0, 3\n li $v0, 17\n syscall")).codigo_salida == 3


def test_mips_lw_desalineado_falla():
    with pytest.raises(mips.ErrorSimulacion, match="desalineado"):
        mips.simular(mips_main(" la $t0, x\n lw $t1, 2($t0)", "x: .word 1, 2"))


def test_mips_double_desalineado_falla():
    datos = ".align 3\nx: .double 1.5"
    with pytest.raises(mips.ErrorSimulacion, match="desalineado"):
        mips.simular(mips_main(" la $t0, x\n l.d $f4, 4($t0)", datos))


def test_mips_direccion_invalida_falla():
    with pytest.raises(mips.ErrorSimulacion, match="invalida"):
        mips.simular(mips_main(" lw $t0, 0($zero)"))


def test_mips_registro_doble_impar_falla():
    with pytest.raises(mips.ErrorSimulacion, match="impar"):
        mips.simular(mips_main(" add.d $f1, $f2, $f4"))


def test_mips_instruccion_desconocida_falla():
    with pytest.raises(mips.ErrorEnsamblado, match="no soportada"):
        mips.simular(mips_main(" frobnicate $t0"))


def test_mips_etiqueta_desconocida_falla():
    with pytest.raises(mips.ErrorEnsamblado, match="desconocida"):
        mips.simular(mips_main(" j nada"))


def test_mips_etiqueta_repetida_falla():
    with pytest.raises(mips.ErrorEnsamblado, match="repetida"):
        mips.simular(mips_main("a:\na:"))


def test_mips_escribir_en_zero_falla():
    with pytest.raises(mips.ErrorEnsamblado, match="zero"):
        mips.simular(mips_main(" addu $zero, $t0, $t1"))


def test_mips_detecta_bucle_infinito():
    with pytest.raises(mips.ErrorSimulacion, match="no termino"):
        mips.simular(mips_main("L: j L"), max_instrucciones=1000)


def test_mips_salirse_del_codigo_falla():
    with pytest.raises(mips.ErrorSimulacion, match="se salio"):
        mips.simular(".text\nmain: nop")


def test_mips_division_sin_verificar_falla():
    with pytest.raises(mips.ErrorSimulacion, match="sin verificar"):
        mips.simular(mips_main(" li $t0, 1\n div $t0, $zero"))


def test_mips_estricto_detecta_registro_guardado_destruido():
    fuente = ".text\nmain:\n jal f\n li $v0, 10\n syscall\nf:\n li $s0, 5\n jr $ra\n"
    with pytest.raises(mips.ErrorSimulacion, match="no preservo"):
        mips.simular(fuente)


def test_mips_estricto_destruye_temporales_al_retornar():
    fuente = (
        ".text\nmain:\n li $t0, 7\n jal f\n move $a0, $t0\n li $v0, 1\n syscall\n li $v0, 10\n syscall\n"
        "f:\n jr $ra\n"
    )
    assert mips.simular(fuente, estricto=False).salida == "7"
    assert mips.simular(fuente).salida != "7"


def test_mips_desbordamiento_de_pila():
    fuente = ".text\nmain:\nL:\n addiu $sp, $sp, -1048576\n sw $zero, 0($sp)\n j L\n"
    with pytest.raises(mips.ErrorSimulacion, match="pila"):
        mips.simular(fuente)


# --- AArch64 --------------------------------------------------------------


def salida_arm(cuerpo: str, datos: str = "") -> str:
    return aarch64.simular(arm_main(cuerpo, datos)).salida


def test_arm_write():
    datos = 's: .asciz "hola"'
    cuerpo = " adrp x1, s\n add x1, x1, :lo12:s\n mov x2, #4\n mov x0, #1\n mov x8, #64\n svc #0"
    assert salida_arm(cuerpo, datos) == "hola"


def test_arm_exit_con_codigo():
    assert aarch64.simular(".text\n_start:\n mov x0, #9\n mov x8, #93\n svc #0\n").codigo_salida == 9


def test_arm_w_trunca_a_32_bits():
    fuente = (
        ".text\n_start:\n movz w9, #65535\n movk w9, #65535, lsl #16\n add w0, w9, #2\n"
        " mov x8, #93\n svc #0\n"
    )
    assert aarch64.simular(fuente).codigo_salida == 1


def test_arm_cmp_con_signo():
    fuente = (
        ".text\n_start:\n movz w9, #65535\n movk w9, #65535, lsl #16\n mov w10, #1\n cmp w9, w10\n"
        " cset w0, lt\n mov x8, #93\n svc #0\n"
    )
    assert aarch64.simular(fuente).codigo_salida == 1


def test_arm_sp_desalineado_falla():
    with pytest.raises(aarch64.ErrorSimulacion, match="desalineado"):
        salida_arm(" sub sp, sp, #8\n str x0, [sp]")


def test_arm_direccion_invalida_falla():
    with pytest.raises(aarch64.ErrorSimulacion, match="invalida"):
        salida_arm(" mov x9, #0\n ldr x0, [x9]")


def test_arm_instruccion_desconocida_falla():
    with pytest.raises(aarch64.ErrorEnsamblado, match="no soportada"):
        salida_arm(" frobnicate x0")


def test_arm_registro_invalido_falla():
    with pytest.raises(aarch64.ErrorEnsamblado, match="invalido"):
        salida_arm(" mov x40, x1")


def test_arm_estricto_detecta_registro_guardado_destruido():
    fuente = ".text\n_start:\n bl f\n mov x0, #0\n mov x8, #93\n svc #0\nf:\n mov x19, #5\n ret\n"
    with pytest.raises(aarch64.ErrorSimulacion, match="no preservo"):
        aarch64.simular(fuente)


def test_arm_detecta_bucle_infinito():
    with pytest.raises(aarch64.ErrorSimulacion, match="no termino"):
        aarch64.simular(arm_main("L: b L"), max_instrucciones=1000)
