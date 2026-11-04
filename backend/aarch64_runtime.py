"""
Runtime en ensamblador AArch64 para Linux, sin libc: usa las llamadas al
sistema `write` (64), `exit` (93) y `mmap` (222).

Respeta la convencion de los programas: argumentos en x0-x7 (un double en d0),
resultado en x0, destruye x0-x17 y d0-d7, preserva x19-x29. Es el mismo
programa que `backend/mips_runtime.py`; la conversion de double a texto es la
de core/runtime.py::formato_float.
"""

from core.runtime import MSG_DIVISION, MSG_INDICE, MSG_NULL, PREFIJO_ERROR

RUNTIME_DATOS = f"""// ---- runtime: datos
    .balign 8
__rt_f_medio: .double 0.0000005
__rt_f_limite: .double 2.0e18
__rt_f_2p31: .double 2147483648.0
__rt_f_1e6: .double 1000000.0
__rt_f_1e9: .double 1000000000.0
__rt_handler: .quad 0
__rt_heap: .quad 0
__rt_heap_fin: .quad 0
__rt_s_null: .asciz "null"
__rt_s_true: .asciz "true"
__rt_s_false: .asciz "false"
__rt_s_nan: .asciz "nan"
__rt_s_inf: .asciz "inf"
__rt_s_funcion: .asciz "<funcion>"
__rt_s_coma: .asciz ", "
__rt_msg_indice: .asciz "{MSG_INDICE}"
__rt_msg_division: .asciz "{MSG_DIVISION}"
__rt_msg_null: .asciz "{MSG_NULL}"
__rt_msg_error: .asciz "{PREFIJO_ERROR}"
"""

RUNTIME_TEXTO = r"""// ---- runtime: codigo
    .text
__rt_exit:
    mov x0, #0
    mov x8, #93
    svc #0

// __rt_alloc(x0 = bytes) -> x0 = bloque en ceros, alineado a 8
__rt_alloc:
    add x0, x0, #7
    and x0, x0, #0xfffffffffffffff8
    adrp x9, __rt_heap
    add x9, x9, :lo12:__rt_heap
    ldr x10, [x9]
    ldr x11, [x9, #8]
    add x12, x10, x0
    cmp x12, x11
    b.hi __rt_alloc_mas
    cbz x10, __rt_alloc_mas
    str x12, [x9]
    mov x0, x10
    ret
__rt_alloc_mas:
    mov x13, x0
    movz x14, #16, lsl #16
    add x12, x0, #8
    cmp x14, x12
    csel x14, x14, x12, hs
    mov x0, #0
    mov x1, x14
    mov x2, #3
    mov x3, #34
    mov x4, #-1
    mov x5, #0
    mov x8, #222
    svc #0
    adrp x9, __rt_heap
    add x9, x9, :lo12:__rt_heap
    add x10, x0, x14
    str x10, [x9, #8]
    add x10, x0, x13
    str x10, [x9]
    ret

// Errores de ejecucion
__rt_err_index:
    adrp x0, __rt_msg_indice
    add x0, x0, :lo12:__rt_msg_indice
    b __rt_raise
__rt_err_div:
    adrp x0, __rt_msg_division
    add x0, x0, :lo12:__rt_msg_division
    b __rt_raise
__rt_err_null:
    adrp x0, __rt_msg_null
    add x0, x0, :lo12:__rt_msg_null
__rt_raise:
    adrp x9, __rt_handler
    add x9, x9, :lo12:__rt_handler
    ldr x10, [x9]
    cbz x10, __rt_sin_manejador
    ldr x11, [x10]
    str x11, [x9]
    ldr x12, [x10, #8]
    ldr x29, [x10, #16]
    ldr x11, [x10, #24]
    mov sp, x11
    br x12
__rt_sin_manejador:
    mov x19, x0
    adrp x0, __rt_msg_error
    add x0, x0, :lo12:__rt_msg_error
    bl __rt_puts
    mov x0, x19
    bl __rt_puts
    bl __rt_nl
    mov x0, #1
    mov x8, #93
    svc #0

// Salida
__rt_puts:
    mov x9, x0
__rt_puts_largo:
    ldrb w10, [x9]
    cbz w10, __rt_puts_fin
    add x9, x9, #1
    b __rt_puts_largo
__rt_puts_fin:
    sub x2, x9, x0
    mov x1, x0
    mov x0, #1
    mov x8, #64
    svc #0
    ret
__rt_nl:
    mov w0, #10
__rt_putc:
    sub sp, sp, #16
    strb w0, [sp]
    mov x1, sp
    mov x2, #1
    mov x0, #1
    mov x8, #64
    svc #0
    add sp, sp, #16
    ret

// __rt_show_int(w0): sin salto de linea
__rt_show_int:
    sub sp, sp, #32
    add x9, sp, #24
    sxtw x10, w0
    mov w11, #0
    cmp x10, #0
    b.ge __rt_si_digitos
    neg x10, x10
    mov w11, #1
__rt_si_digitos:
    mov x12, #10
__rt_si_ciclo:
    udiv x13, x10, x12
    msub x14, x13, x12, x10
    add w14, w14, #48
    sub x9, x9, #1
    strb w14, [x9]
    mov x10, x13
    cbnz x10, __rt_si_ciclo
    cbz w11, __rt_si_escribir
    sub x9, x9, #1
    mov w14, #45
    strb w14, [x9]
__rt_si_escribir:
    add x10, sp, #24
    sub x2, x10, x9
    mov x1, x9
    mov x0, #1
    mov x8, #64
    svc #0
    add sp, sp, #32
    ret

// print
__rt_print_int:
    str x30, [sp, #-16]!
    bl __rt_show_int
    ldr x30, [sp], #16
    b __rt_nl
__rt_print_str:
    str x30, [sp, #-16]!
    bl __rt_show_str
    ldr x30, [sp], #16
    b __rt_nl
__rt_print_bool:
    str x30, [sp, #-16]!
    bl __rt_show_bool
    ldr x30, [sp], #16
    b __rt_nl
__rt_print_float:
    str x30, [sp, #-16]!
    bl __rt_show_float
    ldr x30, [sp], #16
    b __rt_nl
__rt_print_val:
    str x30, [sp, #-16]!
    bl __rt_show_val
    ldr x30, [sp], #16
    b __rt_nl

__rt_show_str:
    cbnz x0, __rt_puts
    adrp x0, __rt_s_null
    add x0, x0, :lo12:__rt_s_null
    b __rt_puts

__rt_show_bool:
    cbnz w0, __rt_show_true
    adrp x0, __rt_s_false
    add x0, x0, :lo12:__rt_s_false
    b __rt_puts
__rt_show_true:
    adrp x0, __rt_s_true
    add x0, x0, :lo12:__rt_s_true
    b __rt_puts

// __rt_show_val(x0 = valor, x1 = descriptor de tipo): sin salto de linea
__rt_show_val:
    ldr x9, [x1]
    cmp x9, #6
    b.eq __rt_show_lista
    cmp x9, #5
    b.eq __rt_show_funcion
    cmp x9, #4
    b.eq __rt_show_objeto
    cmp x9, #3
    b.eq __rt_show_str
    cmp x9, #2
    b.eq __rt_show_bool
    b __rt_show_int
__rt_show_funcion:
    cbz x0, __rt_show_str
    adrp x0, __rt_s_funcion
    add x0, x0, :lo12:__rt_s_funcion
    b __rt_puts
__rt_show_objeto:
    cbz x0, __rt_show_str
    str x30, [sp, #-16]!
    ldr x9, [x0]
    ldr x9, [x9]
    str x9, [sp, #8]
    mov w0, #60
    bl __rt_putc
    ldr x0, [sp, #8]
    bl __rt_puts
    mov w0, #62
    bl __rt_putc
    ldr x30, [sp], #16
    ret
__rt_show_lista:
    cbz x0, __rt_show_str
    sub sp, sp, #32
    str x30, [sp]
    str x0, [sp, #8]
    ldr x9, [x1, #8]
    str x9, [sp, #16]
    str xzr, [sp, #24]
    mov w0, #91
    bl __rt_putc
__rt_show_lista_ciclo:
    ldr x9, [sp, #24]
    ldr x10, [sp, #8]
    ldr w11, [x10]
    cmp w9, w11
    b.ge __rt_show_lista_fin
    cbz x9, __rt_show_lista_elem
    adrp x0, __rt_s_coma
    add x0, x0, :lo12:__rt_s_coma
    bl __rt_puts
__rt_show_lista_elem:
    ldr x9, [sp, #24]
    ldr x10, [sp, #8]
    add x10, x10, x9, lsl #3
    add x10, x10, #8
    ldr x1, [sp, #16]
    ldr x11, [x1]
    cmp x11, #1
    b.eq __rt_show_lista_float
    cmp x11, #2
    b.eq __rt_show_lista_bool
    cmp x11, #0
    b.eq __rt_show_lista_int
    ldr x0, [x10]
    bl __rt_show_val
    b __rt_show_lista_sig
__rt_show_lista_int:
    ldr w0, [x10]
    bl __rt_show_val
    b __rt_show_lista_sig
__rt_show_lista_bool:
    ldrb w0, [x10]
    bl __rt_show_val
    b __rt_show_lista_sig
__rt_show_lista_float:
    ldr d0, [x10]
    bl __rt_show_float
__rt_show_lista_sig:
    ldr x9, [sp, #24]
    add x9, x9, #1
    str x9, [sp, #24]
    b __rt_show_lista_ciclo
__rt_show_lista_fin:
    mov w0, #93
    bl __rt_putc
    ldr x30, [sp]
    add sp, sp, #32
    ret

// __rt_show_float(d0): ver core/runtime.py::formato_float
__rt_show_float:
    sub sp, sp, #32
    str x30, [sp]
    fcmp d0, d0
    b.vc __rt_sf_numero
    adrp x0, __rt_s_nan
    add x0, x0, :lo12:__rt_s_nan
    bl __rt_puts
    b __rt_sf_fin
__rt_sf_numero:
    fcmp d0, #0.0
    b.pl __rt_sf_positivo
    fneg d0, d0
    mov w0, #45
    bl __rt_putc
__rt_sf_positivo:
    adrp x8, __rt_f_medio
    add x8, x8, :lo12:__rt_f_medio
    ldr d1, [x8]
    fadd d0, d0, d1
    adrp x8, __rt_f_limite
    add x8, x8, :lo12:__rt_f_limite
    ldr d1, [x8]
    fcmp d0, d1
    b.lt __rt_sf_finito
    adrp x0, __rt_s_inf
    add x0, x0, :lo12:__rt_s_inf
    bl __rt_puts
    b __rt_sf_fin
__rt_sf_finito:
    adrp x8, __rt_f_2p31
    add x8, x8, :lo12:__rt_f_2p31
    ldr d1, [x8]
    fcmp d0, d1
    b.ge __rt_sf_grande
    fcvtzs w0, d0
    scvtf d2, w0
    fsub d3, d0, d2
    bl __rt_show_int
    adrp x8, __rt_f_1e6
    add x8, x8, :lo12:__rt_f_1e6
    ldr d1, [x8]
    fmul d3, d3, d1
    fcvtzs w9, d3
    str x9, [sp, #8]
    mov w0, #46
    bl __rt_putc
    ldr x9, [sp, #8]
    cbnz w9, __rt_sf_quitar_ceros_inicio
    mov w0, #48
    bl __rt_putc
    b __rt_sf_fin
__rt_sf_quitar_ceros_inicio:
    movz w10, #34464
    movk w10, #1, lsl #16
    mov w11, #10
__rt_sf_quitar_ceros:
    udiv w12, w9, w11
    msub w13, w12, w11, w9
    cbnz w13, __rt_sf_digitos
    mov w9, w12
    udiv w10, w10, w11
    b __rt_sf_quitar_ceros
__rt_sf_digitos:
    cbz w10, __rt_sf_fin
    udiv w12, w9, w10
    msub w9, w12, w10, w9
    str x9, [sp, #8]
    str x10, [sp, #16]
    add w0, w12, #48
    bl __rt_putc
    ldr x9, [sp, #8]
    ldr x10, [sp, #16]
    mov w11, #10
    udiv w10, w10, w11
    b __rt_sf_digitos
__rt_sf_fin:
    ldr x30, [sp]
    add sp, sp, #32
    ret
__rt_sf_grande:
    adrp x8, __rt_f_1e9
    add x8, x8, :lo12:__rt_f_1e9
    ldr d1, [x8]
    fdiv d2, d0, d1
    fcvtzs w0, d2
    scvtf d2, w0
    fmul d2, d2, d1
    fsub d3, d0, d2
    fcvtzs w9, d3
    cmp w9, #0
    csel w9, w9, wzr, ge
    str x9, [sp, #8]
    bl __rt_show_int
    ldr x9, [sp, #8]
    movz w10, #57600
    movk w10, #1525, lsl #16
__rt_sf_grande_digitos:
    cbz w10, __rt_sf_grande_fin
    udiv w12, w9, w10
    msub w9, w12, w10, w9
    str x9, [sp, #8]
    str x10, [sp, #16]
    add w0, w12, #48
    bl __rt_putc
    ldr x9, [sp, #8]
    ldr x10, [sp, #16]
    mov w11, #10
    udiv w10, w10, w11
    b __rt_sf_grande_digitos
__rt_sf_grande_fin:
    mov w0, #46
    bl __rt_putc
    mov w0, #48
    bl __rt_putc
    b __rt_sf_fin

// __rt_str_eq(x0, x1) -> x0 = 1 si son iguales (null solo es igual a null)
__rt_str_eq:
    cmp x0, x1
    b.eq __rt_str_eq_si
    cbz x0, __rt_str_eq_no
    cbz x1, __rt_str_eq_no
__rt_str_eq_ciclo:
    ldrb w9, [x0]
    ldrb w10, [x1]
    cmp w9, w10
    b.ne __rt_str_eq_no
    cbz w9, __rt_str_eq_si
    add x0, x0, #1
    add x1, x1, #1
    b __rt_str_eq_ciclo
__rt_str_eq_si:
    mov x0, #1
    ret
__rt_str_eq_no:
    mov x0, #0
    ret

// __rt_concat(x0, x1) -> x0 = nuevo string (null se concatena como "null")
__rt_concat:
    sub sp, sp, #32
    str x30, [sp, #16]
    cbnz x0, __rt_concat_1
    adrp x0, __rt_s_null
    add x0, x0, :lo12:__rt_s_null
__rt_concat_1:
    cbnz x1, __rt_concat_2
    adrp x1, __rt_s_null
    add x1, x1, :lo12:__rt_s_null
__rt_concat_2:
    str x0, [sp]
    str x1, [sp, #8]
    mov x9, x0
__rt_concat_largo_a:
    ldrb w10, [x9]
    cbz w10, __rt_concat_largo_b_inicio
    add x9, x9, #1
    b __rt_concat_largo_a
__rt_concat_largo_b_inicio:
    sub x11, x9, x0
    mov x9, x1
__rt_concat_largo_b:
    ldrb w10, [x9]
    cbz w10, __rt_concat_reservar
    add x9, x9, #1
    b __rt_concat_largo_b
__rt_concat_reservar:
    sub x12, x9, x1
    add x0, x11, x12
    add x0, x0, #1
    bl __rt_alloc
    mov x9, x0
    ldr x10, [sp]
__rt_concat_copia_a:
    ldrb w11, [x10]
    cbz w11, __rt_concat_copia_b_inicio
    strb w11, [x9]
    add x9, x9, #1
    add x10, x10, #1
    b __rt_concat_copia_a
__rt_concat_copia_b_inicio:
    ldr x10, [sp, #8]
__rt_concat_copia_b:
    ldrb w11, [x10]
    strb w11, [x9]
    cbz w11, __rt_concat_fin
    add x9, x9, #1
    add x10, x10, #1
    b __rt_concat_copia_b
__rt_concat_fin:
    ldr x30, [sp, #16]
    add sp, sp, #32
    ret
"""
