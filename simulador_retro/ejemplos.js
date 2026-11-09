/* Ejemplos escritos a mano para MIPSTATION 3000. Los que genera el compilador
   están en ejemplos_compiscript.js (python simulador_retro/generar_ejemplos.py). */
window.EJEMPLOS = [
  {
    nombre: 'Bienvenida',
    archivo: 'bienvenida.asm',
    descripcion: 'Imprime un saludo y cuenta del 1 al 5: syscalls 4, 1 y 11.',
    codigo: `# ===============================================================
#  MIPSTATION 3000 · programa de bienvenida
#
#  F5  ejecutar          F7  paso a paso (mira los registros)
#  F3  ensamblar         F9  reiniciar
#  Clic en un numero de linea pone un punto de ruptura.
#
#  Pega aqui el .asm que genera el compilador:
#     python main.py programa.cps -o programa.asm
# ===============================================================

        .data
saludo: .asciiz "Hola desde la MIPSTATION 3000!\\nContando: "
coma:   .asciiz ", "
fin:    .asciiz "\\nListo.\\n"

        .text
main:
        la   $a0, saludo        # imprimir cadena
        li   $v0, 4
        syscall

        li   $t0, 1             # contador
        li   $t1, 5             # limite
ciclo:
        move $a0, $t0           # imprimir entero
        li   $v0, 1
        syscall
        beq  $t0, $t1, salir
        la   $a0, coma
        li   $v0, 4
        syscall
        addiu $t0, $t0, 1
        j    ciclo

salir:
        la   $a0, fin
        li   $v0, 4
        syscall
        li   $v0, 10            # terminar
        syscall
`,
  },
  {
    nombre: 'Factorial recursivo',
    archivo: 'factorial.asm',
    descripcion: 'Secuencia de llamada completa: marco en la pila, $ra y $s0 guardados, recursión.',
    codigo: `# Factorial recursivo: fact(n) = n * fact(n - 1)
# Usa F7 y la pestaña CPU para ver como crece y se libera la pila.

        .data
msg1:   .asciiz "! = "
nl:     .asciiz "\\n"

        .text
main:
        li   $s1, 0             # i = 0
bucle:
        bgt  $s1, 10, terminar
        move $a0, $s1
        li   $v0, 1
        syscall
        la   $a0, msg1
        li   $v0, 4
        syscall

        move $a0, $s1
        jal  fact               # $v0 = fact(i)

        move $a0, $v0
        li   $v0, 1
        syscall
        la   $a0, nl
        li   $v0, 4
        syscall
        addiu $s1, $s1, 1
        j    bucle
terminar:
        li   $v0, 10
        syscall

# int fact(int n)
fact:
        addiu $sp, $sp, -8      # prologo: reservar el marco
        sw   $ra, 4($sp)        #   direccion de retorno
        sw   $s0, 0($sp)        #   registro preservado
        move $s0, $a0

        li   $v0, 1
        ble  $s0, 1, fact_fin   # caso base

        addiu $a0, $s0, -1
        jal  fact
        mul  $v0, $s0, $v0      # n * fact(n - 1)
fact_fin:
        lw   $s0, 0($sp)        # epilogo
        lw   $ra, 4($sp)
        addiu $sp, $sp, 8
        jr   $ra
`,
  },
  {
    nombre: 'Fibonacci',
    archivo: 'fibonacci.asm',
    descripcion: 'Los primeros 25 números de Fibonacci con un ciclo y tres registros.',
    codigo: `# Primeros 25 numeros de Fibonacci

        .data
sep:    .asciiz " "
        .text
main:
        li   $t0, 0             # a
        li   $t1, 1             # b
        li   $t2, 25            # cuantos faltan
otro:
        move $a0, $t0
        li   $v0, 1
        syscall
        la   $a0, sep
        li   $v0, 4
        syscall
        addu $t3, $t0, $t1      # siguiente = a + b
        move $t0, $t1
        move $t1, $t3
        addiu $t2, $t2, -1
        bnez $t2, otro

        li   $a0, 10            # salto de linea
        li   $v0, 11
        syscall
        li   $v0, 10
        syscall
`,
  },
  {
    nombre: 'Ordenamiento burbuja',
    archivo: 'burbuja.asm',
    descripcion: 'Ordena un arreglo de .data: lw/sw con desplazamientos y ciclos anidados.',
    codigo: `# Ordenamiento burbuja de un arreglo de enteros

        .data
arreglo: .word 34, -7, 23, 32, 5, 62, 0, 18, -21, 9
n:       .word 10
antes:   .asciiz "antes:   "
despues: .asciiz "despues: "

        .text
main:
        la   $a0, antes
        jal  imprimir

        lw   $t0, n             # i = n - 1
        addiu $t0, $t0, -1
externo:
        blez $t0, listo
        li   $t1, 0             # j = 0
        la   $t2, arreglo       # p = &arreglo[0]
interno:
        bge  $t1, $t0, fin_interno
        lw   $t3, 0($t2)
        lw   $t4, 4($t2)
        ble  $t3, $t4, no_cambia
        sw   $t4, 0($t2)        # intercambiar
        sw   $t3, 4($t2)
no_cambia:
        addiu $t1, $t1, 1
        addiu $t2, $t2, 4
        j    interno
fin_interno:
        addiu $t0, $t0, -1
        j    externo
listo:
        la   $a0, despues
        jal  imprimir
        li   $v0, 10
        syscall

# imprimir(titulo): imprime el titulo y el arreglo
imprimir:
        li   $v0, 4
        syscall
        la   $t5, arreglo
        lw   $t6, n
mas:
        lw   $a0, 0($t5)
        li   $v0, 1
        syscall
        li   $a0, 32
        li   $v0, 11
        syscall
        addiu $t5, $t5, 4
        addiu $t6, $t6, -1
        bnez $t6, mas
        li   $a0, 10
        li   $v0, 11
        syscall
        jr   $ra
`,
  },
  {
    nombre: 'Entrada del teclado',
    archivo: 'entrada.asm',
    descripcion: 'Lee un nombre y dos enteros desde la consola (syscalls 8 y 5).',
    codigo: `# Lee datos desde la consola: escribe en el campo y presiona Enter

        .data
pide_nombre: .asciiz "Como te llamas? "
pide_a:      .asciiz "Primer numero: "
pide_b:      .asciiz "Segundo numero: "
hola:        .asciiz "Hola, "
suma:        .asciiz "La suma es "
producto:    .asciiz " y el producto "
nombre:      .space 64

        .text
main:
        la   $a0, pide_nombre
        li   $v0, 4
        syscall
        la   $a0, nombre        # leer cadena en el bufer
        li   $a1, 64
        li   $v0, 8
        syscall

        la   $a0, hola
        li   $v0, 4
        syscall
        la   $a0, nombre        # la cadena trae su salto de linea
        li   $v0, 4
        syscall

        la   $a0, pide_a
        li   $v0, 4
        syscall
        li   $v0, 5             # leer entero
        syscall
        move $s0, $v0

        la   $a0, pide_b
        li   $v0, 4
        syscall
        li   $v0, 5
        syscall
        move $s1, $v0

        la   $a0, suma
        li   $v0, 4
        syscall
        addu $a0, $s0, $s1
        li   $v0, 1
        syscall
        la   $a0, producto
        li   $v0, 4
        syscall
        mul  $a0, $s0, $s1
        li   $v0, 1
        syscall
        li   $a0, 10
        li   $v0, 11
        syscall
        li   $v0, 10
        syscall
`,
  },
  {
    nombre: 'Punto flotante',
    archivo: 'flotantes.asm',
    descripcion: 'Área de círculos con double: l.d, mul.d, cvt.d.w y syscall 3 (ver pestaña FPU).',
    codigo: `# Area de circulos de radio 1 a 5 con double (coprocesador 1)

        .data
pi:     .double 3.141592653589793
txt1:   .asciiz "r = "
txt2:   .asciiz "   area = "

        .text
main:
        l.d  $f2, pi
        li   $t0, 1
radio:
        bgt  $t0, 5, fin
        la   $a0, txt1
        li   $v0, 4
        syscall
        move $a0, $t0
        li   $v0, 1
        syscall

        mtc1 $t0, $f4           # entero -> double
        cvt.d.w $f4, $f4
        mul.d $f6, $f4, $f4     # r * r
        mul.d $f12, $f6, $f2    # pi * r * r

        la   $a0, txt2
        li   $v0, 4
        syscall
        li   $v0, 3             # imprimir double
        syscall
        li   $a0, 10
        li   $v0, 11
        syscall
        addiu $t0, $t0, 1
        j    radio
fin:
        li   $v0, 10
        syscall
`,
  },
  {
    nombre: 'Melodía (sonido)',
    archivo: 'melodia.asm',
    descripcion: 'Toca una escala y un arpegio con las syscalls MIDI 31 y 33.',
    codigo: `# Escala de Do mayor y arpegio con la syscall 33 (nota MIDI y espera)
#   $a0 = tono (60 = Do central), $a1 = duracion en ms,
#   $a2 = instrumento, $a3 = volumen (0-127)

        .data
notas:  .byte 60, 62, 64, 65, 67, 69, 71, 72, 67, 64, 60, 64, 67, 72
cuantas: .word 14
txt:    .asciiz "nota "

        .text
main:
        la   $s0, notas
        lw   $s1, cuantas
otra:
        la   $a0, txt
        li   $v0, 4
        syscall
        lbu  $a0, 0($s0)
        li   $v0, 1
        syscall
        li   $a0, 10
        li   $v0, 11
        syscall

        lbu  $a0, 0($s0)
        li   $a1, 220
        li   $a2, 80
        li   $a3, 100
        li   $v0, 33
        syscall

        addiu $s0, $s0, 1
        addiu $s1, $s1, -1
        bnez $s1, otra
        li   $v0, 10
        syscall
`,
  },
  {
    nombre: 'Dados aleatorios',
    archivo: 'dados.asm',
    descripcion: 'Lanza 600 dados (syscall 42) y dibuja un histograma con asteriscos.',
    codigo: `# Histograma de 600 lanzamientos de un dado

        .data
cuenta: .word 0:6               # seis contadores en cero
cara:   .asciiz "cara "
dos_p:  .asciiz ": "

        .text
main:
        li   $s0, 600
lanzar:
        li   $a0, 0
        li   $a1, 6             # aleatorio en [0, 6)
        li   $v0, 42
        syscall
        sll  $t0, $a0, 2        # indice * 4
        la   $t1, cuenta
        addu $t1, $t1, $t0
        lw   $t2, 0($t1)
        addiu $t2, $t2, 1
        sw   $t2, 0($t1)
        addiu $s0, $s0, -1
        bnez $s0, lanzar

        li   $s1, 0             # cara actual
dibujar:
        beq  $s1, 6, salir
        la   $a0, cara
        li   $v0, 4
        syscall
        addiu $a0, $s1, 1
        li   $v0, 1
        syscall
        la   $a0, dos_p
        li   $v0, 4
        syscall
        sll  $t0, $s1, 2
        lw   $s2, cuenta($t0)   # etiqueta($registro)
        move $a0, $s2
        li   $v0, 1
        syscall
        li   $a0, 32
        li   $v0, 11
        syscall
        div  $s2, $s2, 4        # un asterisco cada 4 lanzamientos
estrella:
        blez $s2, fila
        li   $a0, 42
        li   $v0, 11
        syscall
        addiu $s2, $s2, -1
        j    estrella
fila:
        li   $a0, 10
        li   $v0, 11
        syscall
        addiu $s1, $s1, 1
        j    dibujar
salir:
        li   $v0, 10
        syscall
`,
  },
  {
    nombre: 'Error en tiempo de ejecución',
    archivo: 'error.asm',
    descripcion: 'Un acceso desalineado a memoria: muestra cómo se reporta un error y su línea.',
    codigo: `# Este programa falla a proposito: lw necesita una direccion multiplo de 4.

        .data
datos:  .word 10, 20, 30
        .text
main:
        la   $t0, datos
        lw   $a0, 4($t0)        # bien: 20
        li   $v0, 1
        syscall
        li   $a0, 10
        li   $v0, 11
        syscall
        lw   $a0, 6($t0)        # mal: 0x10010006 no esta alineada
        li   $v0, 1
        syscall
        li   $v0, 10
        syscall
`,
  },
];
