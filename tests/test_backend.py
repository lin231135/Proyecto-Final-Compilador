"""
Generacion de codigo: analisis del TAC, getReg, secuencias de llamada y salida
de los dos procesadores. Lo que hace cada programa de la bateria lo comprueba
tests/test_bateria.py; aqui se prueban las piezas del back-end por separado.
"""

import pytest

from backend import BackendError, generar_ensamblador
from backend.cfg import INFINITO, agrupar_parametros, construir_cfg, definicion, es_literal, usos
from backend.regalloc import Descriptores, elegir_variables_en_registro
from driver import analizar
from simulador.ejecucion import ErrorEjecucionExterna, ejecutar_codigo, medios_disponibles
from tests.helpers import compilar


def cfg_de(fuente: str, funcion: str = "main"):
    tac = compilar(fuente).tac.function(funcion)
    return construir_cfg(agrupar_parametros(tac))


def asm(fuente: str, target: str = "mips") -> str:
    return generar_ensamblador(compilar(fuente), target).codigo


def correr(fuente: str, target: str = "mips") -> str:
    return ejecutar_codigo(asm(fuente, target), target, "interno").salida


# --- analisis del TAC -----------------------------------------------------


def test_los_literales_no_son_nombres():
    assert es_literal("5") and es_literal("-1.5") and es_literal('"x"')
    assert es_literal("true") and es_literal("null")
    assert not es_literal("x") and not es_literal("t1") and not es_literal("@g")


def test_param_se_agrupa_con_su_llamada():
    tac = compilar("function f(a: integer, b: integer) { } f(1, 2);").tac.function("main")
    codigo = agrupar_parametros(tac)
    assert [i.op for i in codigo] == ["call"]
    assert codigo[0].args == ["1", "2"]


def test_agrupar_no_modifica_el_tac_original():
    r = compilar("print(1);")
    agrupar_parametros(r.tac.function("main"))
    assert [i.op for i in r.tac.function("main").instructions] == ["param", "call"]


def test_usos_y_definicion():
    r = compilar("function f(x: integer): integer { let y: integer = x + 1; return y; } print(f(1));")
    primera = agrupar_parametros(r.tac.function("f"))[0]
    assert usos(primera) == ["x"]
    assert definicion(primera) == "y"


def test_un_if_parte_el_codigo_en_bloques():
    cfg = cfg_de("function f(a: integer): integer { if (a > 0) { return 1; } return 2; } print(f(1));", "f")
    assert len(cfg.bloques) == 3
    assert len(cfg.bloques[0].sucesores) == 2


def test_un_return_no_tiene_sucesores():
    cfg = cfg_de("function f(a: integer): integer { if (a > 0) { return 1; } return 2; } print(f(1));", "f")
    assert cfg.bloques[1].sucesores == []


def test_liveness_una_variable_de_bucle_vive_en_el_ciclo():
    cfg = cfg_de("function f(): integer { let i: integer = 0; while (i < 3) { i = i + 1; } return i; } print(f());", "f")
    condicion = cfg.bloques[1]
    assert "i" in condicion.live_in and "i" in condicion.live_out


def test_liveness_lo_no_usado_no_esta_vivo():
    cfg = cfg_de("function f() { let a: integer = 1; let b: integer = 2; print(b); } f();", "f")
    assert cfg.entrada.live_in == set()
    assert "a" not in cfg.entrada.next_use[0]


def test_variable_sin_inicializar_esta_viva_al_entrar():
    cfg = cfg_de("function f(): integer { let x: integer; return x; } print(f());", "f")
    assert "x" in cfg.entrada.live_in


def test_next_use_apunta_al_siguiente_uso_en_el_bloque():
    cfg = cfg_de("function f(a: integer): integer { let b: integer = a + 1; let c: integer = b + 2; return c; } print(f(1));", "f")
    b = cfg.entrada
    assert b.next_use[0]["b"] == 1
    assert "b" not in b.next_use[1]


def test_next_use_infinito_si_vive_al_salir_del_bloque():
    cfg = cfg_de("function f(a: integer): integer { let b: integer = a; if (a > 0) { return b; } return 0; } print(f(1));", "f")
    assert cfg.entrada.next_use[0]["b"] == INFINITO


def test_cruza_llamada():
    fuente = "function g() { } function f(a: integer): integer { let b: integer = a + 1; g(); return b; } print(f(1));"
    b = cfg_de(fuente, "f").entrada
    assert b.cruza_llamada("b", 0)
    assert not b.cruza_llamada("a", 0)


def test_profundidad_de_bucle():
    cfg = cfg_de(
        "function f() { for (let i: integer = 0; i < 2; i = i + 1) { for (let j: integer = 0; j < 2; j = j + 1) { print(j); } } } f();",
        "f",
    )
    assert max(cfg.profundidad_bucle.values()) == 2


def test_con_try_todos_los_bloques_llegan_al_manejador():
    cfg = cfg_de("function f() { let x: integer = 1; try { print(x); } catch (e) { print(x); } } f();", "f")
    assert cfg.manejadores
    assert all(cfg.manejadores[0] in b.sucesores for b in cfg.bloques)
    assert "x" in cfg.vivos_en_manejadores()


# --- getReg ---------------------------------------------------------------


def descriptores(temporales=("$t0", "$t1"), guardados=("$s0",), flotantes=("$f4",)):
    escritos = []
    d = Descriptores(list(temporales), list(guardados), list(flotantes), lambda n, r: escritos.append((n, r)))
    return d, escritos


def bloque_con(next_use, llamadas=()):
    from backend.cfg import Bloque

    b = Bloque(0, [])
    b.next_use = [next_use]
    b.llamadas = list(llamadas)
    return b


def test_get_reg_prefiere_temporales_si_no_cruza_llamada():
    d, _ = descriptores()
    assert d.get_reg(False, False, bloque_con({}), 0) == "$t0"


def test_get_reg_prefiere_guardados_si_cruza_llamada():
    d, _ = descriptores()
    assert d.get_reg(False, True, bloque_con({}), 0) == "$s0"
    assert d.guardados_usados == {"$s0"}


def test_get_reg_usa_el_banco_flotante():
    d, _ = descriptores()
    assert d.get_reg(True, False, bloque_con({}), 0) == "$f4"


def test_get_reg_toma_otro_registro_si_el_primero_esta_ocupado():
    d, _ = descriptores()
    d.ocupar("$t0", "a", sucio=False)
    assert d.get_reg(False, False, bloque_con({"a": 5}), 0) == "$t1"


def test_get_reg_desaloja_el_de_uso_mas_lejano_y_lo_guarda():
    d, escritos = descriptores(guardados=())
    d.ocupar("$t0", "cerca", sucio=True)
    d.ocupar("$t1", "lejos", sucio=True)
    r = d.get_reg(False, False, bloque_con({"cerca": 2, "lejos": 9}), 0)
    assert r == "$t1"
    assert escritos == [("lejos", "$t1")]
    assert d.stats.derrames == 1
    assert d.en_registro("lejos") is None


def test_get_reg_no_guarda_un_valor_limpio():
    d, escritos = descriptores(guardados=())
    d.ocupar("$t0", "a", sucio=False)
    d.ocupar("$t1", "b", sucio=False)
    d.get_reg(False, False, bloque_con({"a": 2, "b": 9}), 0)
    assert escritos == []
    assert d.stats.desalojos == 1 and d.stats.derrames == 0


def test_get_reg_no_guarda_un_valor_muerto():
    d, escritos = descriptores(guardados=())
    d.ocupar("$t0", "vivo", sucio=True)
    d.ocupar("$t1", "muerto", sucio=True)
    assert d.get_reg(False, False, bloque_con({"vivo": 3}), 0) == "$t1"
    assert escritos == []


def test_get_reg_no_desaloja_los_operandos_de_la_instruccion():
    d, _ = descriptores(guardados=())
    d.ocupar("$t0", "a", sucio=False)
    d.ocupar("$t1", "b", sucio=False)
    d.fijar("$t1")
    assert d.get_reg(False, False, bloque_con({"a": 1, "b": 9}), 0) == "$t0"


def test_escribir_vivos_solo_escribe_lo_sucio_y_vivo():
    d, escritos = descriptores()
    d.ocupar("$t0", "sucio_vivo", sucio=True)
    d.ocupar("$t1", "sucio_muerto", sucio=True)
    d.ocupar("$s0", "limpio", sucio=False)
    d.escribir_vivos({"sucio_vivo", "limpio"})
    assert escritos == [("sucio_vivo", "$t0")]


def test_liberar_muertos():
    d, _ = descriptores()
    d.ocupar("$t0", "a", sucio=True)
    d.ocupar("$t1", "b", sucio=True)
    d.liberar_muertos({"a": 3})
    assert d.en_registro("a") == "$t0" and d.en_registro("b") is None


def test_un_nombre_no_queda_en_dos_registros():
    d, _ = descriptores()
    d.ocupar("$t0", "a", sucio=True)
    d.ocupar("$t1", "a", sucio=True)
    assert d.en_registro("a") == "$t1"
    assert d.duenio["$t0"] is None


def test_plan_elige_las_variables_mas_pesadas():
    plan = elegir_variables_en_registro({"a": 100, "b": 5, "c": 50}, ["$t0"], ["$s0", "$s1", "$s2"], False, 3, 1, 0)
    assert [(v.nombre, v.registro) for v in plan.variables] == [("a", "$s0"), ("c", "$s1")]
    assert plan.guardados == ["$s2"]


def test_plan_ignora_las_variables_poco_usadas():
    plan = elegir_variables_en_registro({"a": 2}, ["$t0"], ["$s0", "$s1"], False, 3, 0, 0)
    assert plan.variables == []


def test_plan_de_funcion_hoja_usa_temporales():
    plan = elegir_variables_en_registro({"a": 9}, ["$t0", "$t1", "$t2", "$t3"], ["$s0"], True, 3, 0, 3)
    assert plan.variables[0].registro == "$t3"
    assert plan.guardados == ["$s0"]


# --- secuencias de llamada (MIPS) ----------------------------------------


FACT = "function fact(n: integer): integer { if (n <= 1) { return 1; } return n * fact(n - 1); } print(fact(5));"


def test_prologo_reserva_marco_y_guarda_enlaces():
    codigo = asm(FACT)
    prologo = codigo[codigo.index("fn_fact:"):]
    assert "addiu $sp, $sp, -" in prologo
    assert "sw $fp, 0($sp)" in prologo
    assert "sw $ra, 16($sp)" in prologo


def test_epilogo_restaura_y_retorna():
    codigo = asm(FACT)
    epilogo = codigo[codigo.index("fn_fact_fin:"):]
    assert "lw $ra, 16($fp)" in epilogo
    assert "lw $fp, 0($fp)" in epilogo
    assert "jr $ra" in epilogo


def test_el_valor_de_retorno_va_en_v0_y_en_su_ranura():
    codigo = asm(FACT)
    assert "move $v0," in codigo
    assert ", 24($fp)" in codigo  # ranura return_value del AR


def test_llamada_usa_jal_y_a0():
    codigo = asm(FACT)
    assert "jal fn_fact" in codigo
    assert "move $a0," in codigo


def test_los_offsets_son_los_de_la_tabla_de_simbolos():
    r = compilar("function f(a: float): float { let b: float = a; let c: integer = 1; print(c); return b; } print(f(1.5));")
    ar = next(x for x in r.generador.activation_records if x.name == "f")
    codigo = generar_ensamblador(r).codigo
    assert f"{ar.slot('a').offset}($fp)" in codigo


def test_globales_usan_el_offset_del_area_estatica():
    r = compilar("let a: integer = 1; let b: integer = 2; print(a + b);")
    codigo = generar_ensamblador(r).codigo
    assert f"{r.generador.global_area.slot('b').offset}($gp)" in codigo


def test_main_empieza_primero_y_termina_con_exit():
    codigo = asm("function f() { } f();")
    assert codigo.index("main:") < codigo.index("fn_f:")
    assert "j __rt_exit" in codigo


def test_cada_instruccion_tac_queda_como_comentario():
    assert "# t1 = n - 1" in asm(FACT)


def test_salida_de_ejemplo_del_enunciado():
    assert correr(FACT) == "120\n"


# --- ambos procesadores ---------------------------------------------------


@pytest.mark.parametrize("target", ["mips", "arm64"])
def test_programa_vacio(target):
    assert correr("", target) == ""


@pytest.mark.parametrize("target", ["mips", "arm64"])
def test_codigo_de_salida_de_un_error_no_capturado(target):
    resultado = ejecutar_codigo(asm("let x: integer[] = []; print(x[0]);", target), target, "interno")
    assert resultado.codigo_salida == 1
    assert resultado.salida == "Error de ejecucion: indice fuera de rango\n"


def test_arm_tiene_punto_de_entrada_y_usa_syscalls():
    codigo = asm("print(1);", "arm64")
    assert ".global _start" in codigo
    assert "svc #0" in codigo


def test_arm_usa_registros_de_32_bits_para_integer():
    assert "add w" in asm("function f(a: integer): integer { return a + 1; } print(f(1));", "arm64")


def test_arm_no_usa_sintaxis_de_mips():
    codigo = asm(FACT, "arm64")
    assert "$" not in codigo and "jal" not in codigo


def test_mips_no_usa_sintaxis_de_arm():
    codigo = asm(FACT)
    assert "svc" not in codigo and "x29" not in codigo


def test_target_desconocido():
    with pytest.raises(BackendError):
        generar_ensamblador(compilar(""), "z80")


def test_backend_rechaza_tipo_desconocido_en_campo():
    r = compilar("class A { let x: integer; } class B { let y: integer; } function f(o) { print(o.z); }")
    with pytest.raises(BackendError):
        generar_ensamblador(r)


def test_aviso_por_print_sin_tipo():
    r = analizar("function f(a) { print(a); }")
    assert generar_ensamblador(r).avisos


def test_reporte_de_registros():
    reporte = generar_ensamblador(compilar(FACT)).reporte()
    assert "fact: marco" in reporte
    assert "n->$s0" in reporte
    assert "TOTAL getReg" in reporte


# --- medios de ejecucion --------------------------------------------------


def test_siempre_hay_un_simulador_disponible():
    assert "interno" in medios_disponibles("mips")
    assert "interno" in medios_disponibles("arm64")


def test_spim_no_ejecuta_arm():
    with pytest.raises(ErrorEjecucionExterna):
        ejecutar_codigo("", "arm64", "spim")


def test_nativo_no_ejecuta_mips():
    with pytest.raises(ErrorEjecucionExterna):
        ejecutar_codigo("", "mips", "nativo")


def test_medio_desconocido():
    with pytest.raises(ErrorEjecucionExterna):
        ejecutar_codigo("", "mips", "qemu")
