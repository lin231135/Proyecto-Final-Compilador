"""
Runtime en ensamblador MIPS32, se agrega al final de cada programa.

Respeta la convencion de los programas: argumentos en $a0-$a3 (un double en
$f12), resultado en $v0, destruye $t*, $a*, $v* y $f*, preserva $s*, $fp y $gp.

Heap: asignador por avance sobre bloques que entrega `sbrk` (syscall 9). No se
libera memoria. Todo bloque va alineado a 8 y lleno de ceros.
Excepciones: `__rt_handler` apunta al registro de `try` mas reciente (ver
`MIPS.activar_manejador`); `__rt_raise` restaura $fp y $sp desde ahi.
La conversion de double a texto es la misma de core/runtime.py::formato_float.
"""

from core.runtime import MSG_DIVISION, MSG_INDICE, MSG_NULL, PREFIJO_ERROR

RUNTIME_DATOS = f"""# ---- runtime: datos
    .align 3
__rt_f_medio: .double 0.0000005
__rt_f_limite: .double 2.0e18
__rt_f_2p31: .double 2147483648.0
__rt_f_1e6: .double 1000000.0
__rt_f_1e9: .double 1000000000.0
__rt_handler: .word 0
__rt_heap: .word 0
__rt_heap_fin: .word 0
__rt_s_null: .asciiz "null"
__rt_s_true: .asciiz "true"
__rt_s_false: .asciiz "false"
__rt_s_nan: .asciiz "nan"
__rt_s_inf: .asciiz "inf"
__rt_s_funcion: .asciiz "<funcion>"
__rt_s_coma: .asciiz ", "
__rt_msg_indice: .asciiz "{MSG_INDICE}"
__rt_msg_division: .asciiz "{MSG_DIVISION}"
__rt_msg_null: .asciiz "{MSG_NULL}"
__rt_msg_error: .asciiz "{PREFIJO_ERROR}"
"""

RUNTIME_TEXTO = r"""# ---- runtime: codigo
    .text
__rt_exit:
    li $v0, 10
    syscall

# __rt_alloc(a0 = bytes) -> v0 = bloque en ceros, alineado a 8
__rt_alloc:
    addiu $a0, $a0, 7
    li $t8, -8
    and $a0, $a0, $t8
    lw $t0, __rt_heap
    lw $t1, __rt_heap_fin
    addu $t2, $t0, $a0
    sltu $t3, $t1, $t2
    bnez $t3, __rt_alloc_mas
    sw $t2, __rt_heap
    move $v0, $t0
    jr $ra
__rt_alloc_mas:
    move $t6, $a0
    li $t4, 65536
    addiu $t5, $a0, 8
    slt $t3, $t4, $t5
    beqz $t3, __rt_alloc_sbrk
    move $t4, $t5
__rt_alloc_sbrk:
    move $a0, $t4
    li $v0, 9
    syscall
    addiu $t0, $v0, 7
    and $t0, $t0, $t8
    addu $t1, $v0, $t4
    sw $t1, __rt_heap_fin
    addu $t2, $t0, $t6
    sw $t2, __rt_heap
    move $v0, $t0
    jr $ra

# Errores de ejecucion
__rt_err_index:
    la $a0, __rt_msg_indice
    j __rt_raise
__rt_err_div:
    la $a0, __rt_msg_division
    j __rt_raise
__rt_err_null:
    la $a0, __rt_msg_null
__rt_raise:
    lw $t0, __rt_handler
    beqz $t0, __rt_sin_manejador
    lw $t1, 0($t0)
    sw $t1, __rt_handler
    lw $t2, 4($t0)
    lw $fp, 8($t0)
    lw $sp, 12($t0)
    move $v0, $a0
    jr $t2
__rt_sin_manejador:
    move $t0, $a0
    la $a0, __rt_msg_error
    li $v0, 4
    syscall
    move $a0, $t0
    li $v0, 4
    syscall
    li $a0, 10
    li $v0, 11
    syscall
    li $a0, 1
    li $v0, 17
    syscall

# print
__rt_nl:
    li $a0, 10
    li $v0, 11
    syscall
    jr $ra
__rt_print_int:
    li $v0, 1
    syscall
    j __rt_nl
__rt_print_str:
    addiu $sp, $sp, -8
    sw $ra, 0($sp)
    jal __rt_show_str
    lw $ra, 0($sp)
    addiu $sp, $sp, 8
    j __rt_nl
__rt_print_bool:
    addiu $sp, $sp, -8
    sw $ra, 0($sp)
    jal __rt_show_bool
    lw $ra, 0($sp)
    addiu $sp, $sp, 8
    j __rt_nl
__rt_print_float:
    addiu $sp, $sp, -8
    sw $ra, 0($sp)
    jal __rt_show_float
    lw $ra, 0($sp)
    addiu $sp, $sp, 8
    j __rt_nl
__rt_print_val:
    addiu $sp, $sp, -8
    sw $ra, 0($sp)
    jal __rt_show_val
    lw $ra, 0($sp)
    addiu $sp, $sp, 8
    j __rt_nl

__rt_show_str:
    bnez $a0, __rt_show_str_1
    la $a0, __rt_s_null
__rt_show_str_1:
    li $v0, 4
    syscall
    jr $ra

__rt_show_bool:
    la $t0, __rt_s_true
    bnez $a0, __rt_show_bool_1
    la $t0, __rt_s_false
__rt_show_bool_1:
    move $a0, $t0
    li $v0, 4
    syscall
    jr $ra

# __rt_show_val(a0 = valor, a1 = descriptor de tipo): sin salto de linea
__rt_show_val:
    lw $t0, 0($a1)
    li $t1, 6
    beq $t0, $t1, __rt_show_lista
    li $t1, 5
    beq $t0, $t1, __rt_show_funcion
    li $t1, 4
    beq $t0, $t1, __rt_show_objeto
    li $t1, 3
    beq $t0, $t1, __rt_show_str
    li $t1, 2
    beq $t0, $t1, __rt_show_bool
    li $v0, 1
    syscall
    jr $ra
__rt_show_funcion:
    beqz $a0, __rt_show_str
    la $a0, __rt_s_funcion
    j __rt_show_str
__rt_show_objeto:
    beqz $a0, __rt_show_str
    lw $t0, 0($a0)
    lw $t0, 0($t0)
    li $a0, 60
    li $v0, 11
    syscall
    move $a0, $t0
    li $v0, 4
    syscall
    li $a0, 62
    li $v0, 11
    syscall
    jr $ra
__rt_show_lista:
    beqz $a0, __rt_show_str
    addiu $sp, $sp, -16
    sw $ra, 0($sp)
    sw $a0, 4($sp)
    lw $t0, 4($a1)
    sw $t0, 8($sp)
    sw $zero, 12($sp)
    li $a0, 91
    li $v0, 11
    syscall
__rt_show_lista_ciclo:
    lw $t0, 12($sp)
    lw $t1, 4($sp)
    lw $t2, 0($t1)
    slt $t3, $t0, $t2
    beqz $t3, __rt_show_lista_fin
    beqz $t0, __rt_show_lista_elem
    la $a0, __rt_s_coma
    li $v0, 4
    syscall
__rt_show_lista_elem:
    lw $t0, 12($sp)
    lw $t1, 4($sp)
    sll $t3, $t0, 3
    addu $t3, $t3, $t1
    addiu $t3, $t3, 8
    lw $a1, 8($sp)
    lw $t4, 0($a1)
    li $t5, 1
    beq $t4, $t5, __rt_show_lista_float
    li $t5, 2
    beq $t4, $t5, __rt_show_lista_bool
    lw $a0, 0($t3)
    jal __rt_show_val
    j __rt_show_lista_sig
__rt_show_lista_bool:
    lbu $a0, 0($t3)
    jal __rt_show_val
    j __rt_show_lista_sig
__rt_show_lista_float:
    l.d $f12, 0($t3)
    jal __rt_show_float
__rt_show_lista_sig:
    lw $t0, 12($sp)
    addiu $t0, $t0, 1
    sw $t0, 12($sp)
    j __rt_show_lista_ciclo
__rt_show_lista_fin:
    li $a0, 93
    li $v0, 11
    syscall
    lw $ra, 0($sp)
    addiu $sp, $sp, 16
    jr $ra

# __rt_show_float(f12): ver core/runtime.py::formato_float
__rt_show_float:
    c.eq.d $f12, $f12
    bc1t __rt_sf_numero
    la $a0, __rt_s_nan
    li $v0, 4
    syscall
    jr $ra
__rt_sf_numero:
    mtc1 $zero, $f0
    mtc1 $zero, $f1
    c.lt.d $f12, $f0
    bc1f __rt_sf_positivo
    neg.d $f12, $f12
    li $a0, 45
    li $v0, 11
    syscall
__rt_sf_positivo:
    l.d $f2, __rt_f_medio
    add.d $f12, $f12, $f2
    l.d $f2, __rt_f_limite
    c.le.d $f2, $f12
    bc1f __rt_sf_finito
    la $a0, __rt_s_inf
    li $v0, 4
    syscall
    jr $ra
__rt_sf_finito:
    l.d $f2, __rt_f_2p31
    c.le.d $f2, $f12
    bc1t __rt_sf_grande
    trunc.w.d $f4, $f12
    mfc1 $a0, $f4
    cvt.d.w $f4, $f4
    sub.d $f6, $f12, $f4
    li $v0, 1
    syscall
    l.d $f2, __rt_f_1e6
    mul.d $f6, $f6, $f2
    trunc.w.d $f6, $f6
    mfc1 $t0, $f6
    li $a0, 46
    li $v0, 11
    syscall
    bnez $t0, __rt_sf_quitar_ceros_inicio
    li $a0, 48
    li $v0, 11
    syscall
    jr $ra
__rt_sf_quitar_ceros_inicio:
    li $t1, 100000
    li $t2, 10
__rt_sf_quitar_ceros:
    div $t0, $t2
    mfhi $t3
    bnez $t3, __rt_sf_digitos
    mflo $t0
    div $t1, $t2
    mflo $t1
    j __rt_sf_quitar_ceros
__rt_sf_digitos:
    # t0 = decimales significativos, t1 = peso del primer digito
    beqz $t1, __rt_sf_fin
    div $t0, $t1
    mflo $a0
    mfhi $t0
    addiu $a0, $a0, 48
    li $v0, 11
    syscall
    div $t1, $t2
    mflo $t1
    j __rt_sf_digitos
__rt_sf_fin:
    jr $ra
__rt_sf_grande:
    l.d $f2, __rt_f_1e9
    div.d $f4, $f12, $f2
    trunc.w.d $f4, $f4
    mfc1 $a0, $f4
    cvt.d.w $f4, $f4
    mul.d $f4, $f4, $f2
    sub.d $f6, $f12, $f4
    trunc.w.d $f6, $f6
    mfc1 $t0, $f6
    bgez $t0, __rt_sf_grande_alto
    move $t0, $zero
__rt_sf_grande_alto:
    li $v0, 1
    syscall
    li $t1, 100000000
    li $t2, 10
__rt_sf_grande_digitos:
    beqz $t1, __rt_sf_grande_fin
    div $t0, $t1
    mflo $a0
    mfhi $t0
    addiu $a0, $a0, 48
    li $v0, 11
    syscall
    div $t1, $t2
    mflo $t1
    j __rt_sf_grande_digitos
__rt_sf_grande_fin:
    li $a0, 46
    li $v0, 11
    syscall
    li $a0, 48
    li $v0, 11
    syscall
    jr $ra

# __rt_str_eq(a0, a1) -> v0 = 1 si son iguales (null solo es igual a null)
__rt_str_eq:
    beq $a0, $a1, __rt_str_eq_si
    beqz $a0, __rt_str_eq_no
    beqz $a1, __rt_str_eq_no
__rt_str_eq_ciclo:
    lbu $t0, 0($a0)
    lbu $t1, 0($a1)
    bne $t0, $t1, __rt_str_eq_no
    beqz $t0, __rt_str_eq_si
    addiu $a0, $a0, 1
    addiu $a1, $a1, 1
    j __rt_str_eq_ciclo
__rt_str_eq_si:
    li $v0, 1
    jr $ra
__rt_str_eq_no:
    move $v0, $zero
    jr $ra

# __rt_concat(a0, a1) -> v0 = nuevo string (null se concatena como "null")
__rt_concat:
    addiu $sp, $sp, -16
    sw $ra, 12($sp)
    bnez $a0, __rt_concat_1
    la $a0, __rt_s_null
__rt_concat_1:
    bnez $a1, __rt_concat_2
    la $a1, __rt_s_null
__rt_concat_2:
    sw $a0, 0($sp)
    sw $a1, 4($sp)
    move $t0, $a0
__rt_concat_largo_a:
    lbu $t1, 0($t0)
    beqz $t1, __rt_concat_largo_b_inicio
    addiu $t0, $t0, 1
    j __rt_concat_largo_a
__rt_concat_largo_b_inicio:
    subu $t2, $t0, $a0
    move $t0, $a1
__rt_concat_largo_b:
    lbu $t1, 0($t0)
    beqz $t1, __rt_concat_reservar
    addiu $t0, $t0, 1
    j __rt_concat_largo_b
__rt_concat_reservar:
    subu $t3, $t0, $a1
    addu $a0, $t2, $t3
    addiu $a0, $a0, 1
    jal __rt_alloc
    move $t0, $v0
    lw $t1, 0($sp)
__rt_concat_copia_a:
    lbu $t2, 0($t1)
    beqz $t2, __rt_concat_copia_b_inicio
    sb $t2, 0($t0)
    addiu $t0, $t0, 1
    addiu $t1, $t1, 1
    j __rt_concat_copia_a
__rt_concat_copia_b_inicio:
    lw $t1, 4($sp)
__rt_concat_copia_b:
    lbu $t2, 0($t1)
    sb $t2, 0($t0)
    beqz $t2, __rt_concat_fin
    addiu $t0, $t0, 1
    addiu $t1, $t1, 1
    j __rt_concat_copia_b
__rt_concat_fin:
    lw $ra, 12($sp)
    addiu $sp, $sp, 16
    jr $ra
"""
