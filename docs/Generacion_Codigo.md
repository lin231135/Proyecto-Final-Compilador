# Generación de código

Esta fase traduce el código intermedio (TAC) a ensamblador. Hay dos procesadores
destino, que comparten el análisis, la asignación de registros y las secuencias de
llamada:

| Destino | Para qué | Se ejecuta en |
|---|---|---|
| **MIPS32** (`--target mips`, por defecto) | lo que pide el enunciado | MARS, SPIM o el simulador interno |
| **AArch64** (`--target arm64`) | código nativo de la Raspberry Pi 4 | la Raspberry (`as` + `ld`) o el simulador interno |

Una Raspberry Pi 4 tiene un procesador ARM: no ejecuta instrucciones MIPS. El código
MIPS corre en ella dentro de un simulador (SPIM o MARS); el código AArch64 corre
directamente en el procesador. Ver [`Raspberry_Pi.md`](Raspberry_Pi.md).

- [1. Organización](#1-organización)
- [2. Representación de los datos](#2-representación-de-los-datos)
- [3. Registro de activación](#3-registro-de-activación)
- [4. Secuencias de llamada y de retorno](#4-secuencias-de-llamada-y-de-retorno)
- [5. Asignación de registros](#5-asignación-de-registros)
- [6. Traducción de cada instrucción](#6-traducción-de-cada-instrucción)
- [7. Closures y enlaces de acceso](#7-closures-y-enlaces-de-acceso)
- [8. Errores de ejecución y try/catch](#8-errores-de-ejecución-y-trycatch)
- [9. Runtime](#9-runtime)
- [10. Ejemplo completo](#10-ejemplo-completo)
- [11. Limitaciones](#11-limitaciones)

## 1. Organización

```
TAC + tabla de símbolos (driver.Resultado)
        │
        ▼
backend/cfg.py        agrupa param+call, bloques básicos, CFG,
                      liveness global, next-use por instrucción
        │
        ▼
backend/generador.py  Programa: capturas, enlaces, marcos en heap, selectores
                      GeneradorFuncion: recorre bloques, secuencias de llamada
        │  usa
        ├── backend/regalloc.py   descriptores + getReg + variables fijas
        │
        ▼  primitivas (load, store, prologo, ...)
backend/target.py  ──►  backend/mips.py     + backend/mips_runtime.py
                   └─►  backend/aarch64.py  + backend/aarch64_runtime.py
        │
        ▼
simulador/            mips.py, aarch64.py (Python) y ejecucion.py (MARS, SPIM, nativo)
```

`backend/generador.py` decide **qué** hay que hacer; una subclase de `Target` sabe
**cómo** se escribe en su ensamblador. Agregar un procesador es escribir otra
subclase con sus registros, su marco y su runtime.

El TAC se imprime sin tipos, pero cada `Instr` lleva dos anotaciones invisibles
(`ty`, `clase`) que escribe el generador de TAC: el back-end las necesita para
elegir ancho de memoria, banco de registros y la operación correcta (`+` de enteros,
de `float` o concatenación). La conversión `integer` → `float` es explícita en el
TAC (`itof`).

## 2. Representación de los datos

| Tipo | Valor en un registro | En memoria |
|---|---|---|
| `integer` | 32 bits con signo; da la vuelta al desbordarse | 4 bytes |
| `boolean` | 0 o 1 | 1 byte |
| `float` | double IEEE-754, en los registros de punto flotante | 8 bytes |
| `string` | dirección de bytes terminados en cero (UTF-8) | referencia |
| lista | dirección de `[longitud][elemento 0][elemento 1]...`, 8 bytes por casilla | referencia |
| objeto | dirección de `[descriptor de clase][campos]` | referencia |
| función | dirección del par `[código][entorno]` | referencia |
| `null` | 0 | referencia |

Una referencia ocupa la ranura de 8 bytes que le asigna la fase 2. En MIPS se usan
solo sus primeros 4 bytes. Por eso **los desplazamientos de la tabla de símbolos se
usan tal cual en el ensamblador**: `ActivationRecord`, `ClassLayout` y el área estática
sirven a los dos procesadores sin recalcular nada (lo verifica
`tests/test_backend.py::test_los_offsets_son_los_de_la_tabla_de_simbolos`).

Las globales viven en `__globales`, un bloque del segmento de datos apuntado por
`$gp` (MIPS) o `x28` (AArch64), de modo que `@x` es un acceso de una instrucción:
`lw $t0, 16($gp)`.

Un descriptor de clase contiene el nombre de la clase y una tabla de métodos. Cada
nombre de método tiene una posición fija en **todas** las tablas (`Programa.selectores`),
así `callv` no necesita saber la clase estática del objeto.

## 3. Registro de activación

El marco extiende el AR de la fase 2 con dos zonas. `$fp` apunta a la base del AR y
los desplazamientos crecen hacia arriba, igual que en la tabla de símbolos; la pila
crece hacia abajo.

```
direcciones altas
        ┌──────────────────────────────┐
        │ marco del llamador           │
        │   argumentos salientes       │ ← el llamador deja aquí los argumentos de pila
        ├──────────────────────────────┤ ←┐
        │ registros guardados ($s)     │  │
        │ manejadores de try           │  │
        │ temporales t1..tN            │  │
        │ variables locales            │  │  tamaño del marco
        │ parámetros                   │  │
 +24    │ valor de retorno             │  │
 +16    │ dirección de retorno ($ra)   │  │
 +8     │ enlace de acceso             │  │
 +0     │ enlace de control ($fp viejo)│  │
 $fp →  ├──────────────────────────────┤ ←┘
        │ argumentos salientes         │  zona fija: `8 * posición` desde $sp
 $sp →  └──────────────────────────────┘
direcciones bajas
```

Los argumentos salientes tienen tamaño fijo por función (el máximo que necesita), así
que `$sp` no se mueve dentro del cuerpo. Los marcos están alineados a 8 bytes en MIPS
(lo exige `l.d`) y a 16 en AArch64 (lo exige el procesador para `sp`).

`--regs` (o la pestaña REGISTROS del IDE) muestra el marco de cada función.

## 4. Secuencias de llamada y de retorno

Convención en MIPS (en AArch64 es análoga, ver `backend/aarch64.py`):

| Quién | Qué |
|---|---|
| Argumentos | los 4 primeros enteros/referencias en `$a0-$a3`, por posición. Un `float` y los que siguen van en `8 * posición($sp)` |
| Retorno | `$v0` o `$f0`, además de la ranura `return_value` del AR |
| Enlace de acceso | `$v1` |
| Guarda el llamador | `$t0-$t7`, `$f4-$f18`: solo lo que sigue vivo tras la llamada, en su ranura del AR |
| Guarda el llamado | `$s0-$s7` que use, `$fp`, `$ra` |

**Llamador** (`GeneradorFuncion._secuencia_de_llamada`):

1. copia a la zona saliente los argumentos que van por pila;
2. escribe en su ranura los valores vivos que están en registros que la llamada destruye;
3. carga `$a0-$a3`;
4. calcula el enlace de acceso (si el llamado lo necesita) y salta con `jal` o `jalr`;
5. olvida lo que la llamada pudo cambiar: registros temporales y copias de globales
   y variables capturadas;
6. `GeneradorFuncion._resultado` lleva `$v0` / `$f0` al destino.

**Llamado, prólogo** (`MIPS.prologo`, `_recibir_parametros`, `_inicializar_locales`):

```asm
addiu $sp, $sp, -(marco + salientes)   # reserva el marco
sw $fp, salientes($sp)                 # enlace de control
sw $ra, salientes+16($sp)              # dirección de retorno
addiu $fp, $sp, salientes              # nueva base
sw $v1, 8($fp)                         # enlace de acceso (solo si se usa)
sw $s0, ...($fp)                       # registros guardados que use
```

Después mueve cada argumento a su registro fijo o a su ranura y pone en cero lo que
se podría leer antes de escribirse (lo decide liveness).

**Llamado, retorno** (`_gen_ret`, `MIPS.epilogo`):

```asm
move $v0, valor          # o mov.d $f0
sw valor, 24($fp)        # ranura return_value
lw $s0, ...($fp)         # restaura lo guardado
lw $ra, 16($fp)
addiu $sp, $fp, marco    # descarta el marco
lw $fp, 0($fp)           # restaura la base del llamador
jr $ra
```

`main` es el punto de entrada: alinea la pila, carga `$gp`, no guarda registros y
termina con la llamada al sistema `exit`. Va primero en `.text` porque MARS empieza
por la primera instrucción.

## 5. Asignación de registros

`backend/regalloc.py` usa cada tipo de registro en lo que le corresponde, en dos
niveles.

**Nivel 1, variables de larga vida.** Antes de traducir una función,
`elegir_variables_en_registro` fija sus variables más usadas en un registro para toda
la función. El peso de una variable es la suma de `10^profundidad de bucle` de sus
usos. Van a registros guardados (`$s`); en una **función hoja** van a registros
temporales, que no hay que guardar. Siempre queda una reserva para el nivel 2. No se
fijan las variables capturadas ni las globales, porque otro código las lee, ni los
`float`, ni nada en una función con `try`, porque el `catch` debe encontrarlas en
memoria.

**Nivel 2, `getReg`.** Los demás valores y los temporales del TAC viven en registros
dentro de un bloque básico, con el algoritmo del Dragon Book (8.6) y dos descriptores:

| Descriptor | Dónde | Contenido |
|---|---|---|
| de registros | `duenio` | qué nombre contiene cada registro |
| de direcciones | `registro_de`, `sucios` | en qué registro está cada nombre y si su copia en memoria está al día |

`Descriptores.get_reg(flotante, cruza_llamada, bloque, k)`:

1. Si el valor ya está en un registro, lo reutiliza (`GeneradorFuncion.use`).
2. Si hay un registro libre, lo toma. Si el valor **cruza una llamada** del bloque
   prefiere uno guardado (`$s`), que sobrevive; si no, uno temporal (`$t`), que no
   hay que guardar en el prólogo. Los `float` usan su propio banco.
3. Si no hay ninguno libre, desaloja el registro cuyo valor se vuelve a usar más tarde
   (política de Belady, con la información next-use) sin tocar los operandos de la
   instrucción actual. Si ese valor está sucio y sigue vivo, lo escribe antes en su
   ranura del AR: ese es el **derrame a la pila**.

Toda variable y temporal tiene ranura en el AR desde la fase 2, así que siempre hay
dónde derramar.

El destino de una instrucción reutiliza el registro de un operando que muere en ella
(`registro_destino`), de modo que `t1 = t1 + t2` no gasta otro registro. Al terminar
un bloque se escriben los valores sucios que siguen vivos según **liveness global**;
un temporal muerto nunca toca la memoria.

Globales y variables capturadas se pueden leer de un registro dentro de un bloque,
pero se escriben directo a memoria y se olvidan tras cada llamada.

Ejemplo real: `--regs` sobre el programa de la sección 10:

```regs
main: marco 48 B (AR 48 B, argumentos salientes 0 B)
  variables en registro: i->$s0 (peso 41)
  getReg: 4 pedidos, 4 libres, 0 desalojos, 0 derrames a la pila, 0 salvados antes de llamadas
fact: marco 56 B (AR 48 B, argumentos salientes 0 B)
  variables en registro: n->$s0 (peso 3)
  registros guardados en el prologo: $s0
  getReg: 4 pedidos, 4 libres, 0 desalojos, 0 derrames a la pila, 0 salvados antes de llamadas
TOTAL getReg: 8 pedidos, 8 libres, 0 desalojos, 0 derrames a la pila, 0 salvados antes de llamadas
```

Los programas de `pruebas/asm_registros/` fuerzan cada caso, incluidos los derrames de
enteros y de `float`.

## 6. Traducción de cada instrucción

| TAC | MIPS |
|---|---|
| `x = a + b` | `addu` (`addiu` con literal); `add.d` si es `float`; `__rt_concat` si es `string` |
| `x = a / b` | verifica cero, `div` + `mflo` (`%`: `mfhi`) |
| `x = a < b` | `slt` y variantes; `float`: `c.lt.d` + `bc1t`; `string` (`==`): `__rt_str_eq` |
| `if a < b goto L` | `blt`; `float`: `c.lt.d` + `bc1t` |
| `x = itof a` | `mtc1` + `cvt.d.w` |
| `x = obj.campo` | verifica `null`, `lw/lbu/l.d off(obj)` con el offset de `ClassLayout` |
| `x = arr[i]` | verifica `null` y `0 <= i < longitud` con una sola comparación sin signo |
| `x = new C, n` | `__rt_alloc(n)` y guarda `cls_C` en la palabra 0 |
| `x = newlist n` | `__rt_alloc(8 + 8n)` y guarda la longitud |
| `x = closure f` | dirección de un par estático, o par nuevo si necesita entorno |
| `call f, n` | secuencia de llamada + `jal` |
| `callv o.m, n` | carga la tabla de la clase real y `jalr` |
| `callc f, n` | carga código y entorno del par y `jalr` |
| `try L` / `endtry` / `catch e` | ver sección 8 |

Cada instrucción TAC queda como comentario en el ensamblador.

## 7. Closures y enlaces de acceso

Una variable de una función envolvente se lee recorriendo enlaces de acceso: `up2.a`
carga `8($fp)`, luego `8(...)`, y por último la ranura de `a`. `Programa` calcula por
punto fijo qué funciones necesitan su enlace; a las demás no se les pasa.

Un closure es el par `(código, entorno)`. Una función global no tiene entorno, así que
su par es estático. Una función anidada se puede guardar y sobrevivir a la función que
la creó:

```cps
let h = cero;
function crear(inicio: integer) {
  let c: integer = inicio;
  function siguiente(): integer { c = c + 1; return c; }
  h = siguiente;
}
```

Si el marco de `crear` estuviera en la pila, `h` apuntaría a memoria ya reutilizada.
Por eso los marcos de las funciones que crean closures de funciones anidadas
**se reservan en el heap** (`Programa.marco_en_heap`). El resto del código no cambia:
todo se accede por `$fp`.

## 8. Errores de ejecución y try/catch

Hay tres errores, con mensaje fijo: `indice fuera de rango`, `division entre cero` y
`acceso a null`. Sin `catch`, el programa imprime `Error de ejecucion: <mensaje>` y
termina con código 1.

`try L` escribe en el marco un registro `(anterior, L, $fp, $sp)` y lo enlaza en
`__rt_handler`. `__rt_raise` toma el más reciente, restaura `$fp` y `$sp` desde él y
salta a `L` con el mensaje en `$v0`; `catch e` lo guarda. El error puede atravesar
cualquier cantidad de marcos. El TAC emite `endtry` en toda salida del bloque,
incluidos `break`, `continue` y `return`.

Como `$fp` y `$sp` se restauran sin pasar por los epílogos, una función con `try`:

- guarda **todos** los registros `$s` en su prólogo, para devolvérselos intactos a
  quien la llamó aunque un marco abandonado los haya cambiado;
- no fija variables en registros;
- escribe directo a memoria lo que esté vivo en un `catch` (`vivos_en_manejadores`).
  El CFG tiene arcos de todos sus bloques a cada `catch`.

## 9. Runtime

Rutinas en ensamblador que se agregan a cada programa (`backend/*_runtime.py`):
`__rt_alloc` (heap por avance sobre `sbrk`/`mmap`, siempre en ceros y alineado a 8, sin
liberación), `__rt_print_*`, `__rt_concat`, `__rt_str_eq`, `__rt_raise`.

`print` de una lista o un objeto recibe un descriptor de tipo estático. Un `float` se
imprime con hasta 6 decimales con un algoritmo propio y no con la llamada al sistema
del simulador, porque MARS y SPIM escriben los double de forma distinta. El mismo
algoritmo, operación por operación, está en `core/runtime.py::formato_float`.

`core/runtime.py` es el contrato común: el simulador de TAC, MIPS y AArch64 deben
imprimir exactamente lo mismo, y la batería lo comprueba.

## 10. Ejemplo completo

```cps
function fact(n: integer): integer {
  if (n <= 1) { return 1; }
  return n * fact(n - 1);
}
let s: integer = 0;
for (let i: integer = 1; i <= 5; i = i + 1) { s = s + fact(i); }
print(s);
```

```mips
# Generado por el compilador de Compiscript (MIPS32, para MARS o SPIM)
    .text
    .globl main

# ---- funcion main()
main:
    la $gp, __globales
    li $t8, -8
    and $sp, $sp, $t8     # los double exigen alineacion a 8
    addiu $sp, $sp, -48
    sw $fp, 0($sp)     # enlace de control
    sw $ra, 16($sp)     # direccion de retorno
    addiu $fp, $sp, 0
    # @s = 0
    li $t0, 0
    sw $t0, 0($gp)
    # i = 1
    li $s0, 1
    # L2:
L2:
    # if i > 5 goto L4
    li $t0, 5
    bgt $s0, $t0, L4
    # t1 = call fact, 1   (args: i)
    move $a0, $s0
    jal fn_fact
    move $t0, $v0
    # @s = @s + t1
    lw $t1, 0($gp)
    addu $t1, $t1, $t0
    sw $t1, 0($gp)
    # L3:
L3:
    # i = i + 1
    addiu $s0, $s0, 1
    # goto L2
    j L2
    # L4:
L4:
    # call print, 1   (args: @s)
    lw $a0, 0($gp)
    jal __rt_print_int
main_fin:
    j __rt_exit

# ---- funcion fact(n)
fn_fact:
    addiu $sp, $sp, -56
    sw $fp, 0($sp)     # enlace de control
    sw $ra, 16($sp)     # direccion de retorno
    addiu $fp, $sp, 0
    sw $s0, 48($fp)
    move $s0, $a0
    # if n > 1 goto L1
    li $t0, 1
    bgt $s0, $t0, L1
    # return 1
    li $t0, 1
    move $v0, $t0
    sw $t0, 24($fp)
    j fn_fact_fin
    # L1:
L1:
    # t1 = n - 1
    addiu $t0, $s0, -1
    # t1 = call fact, 1   (args: t1)
    move $a0, $t0
    jal fn_fact
    move $t0, $v0
    # t1 = n * t1
    mul $t0, $s0, $t0
    # return t1
    move $v0, $t0
    sw $t0, 24($fp)
fn_fact_fin:
    lw $s0, 48($fp)
    lw $ra, 16($fp)
    addiu $sp, $fp, 56
    lw $fp, 0($fp)
    jr $ra
```

Sin contar el runtime, que sigue a este código. `i` vive en `$s0` en `main` porque
cruza llamadas, `n` en `$s0` de `fact`, que por eso lo guarda y restaura, y `@s` se
escribe directo en el área estática.

## 11. Limitaciones

- No hay recolector de basura: el heap solo crece.
- No hay detección de desbordamiento de pila: una recursión sin fin termina con un
  error del simulador o del sistema operativo.
- Los valores no llevan etiqueta de tipo en ejecución. Por eso un parámetro sin
  anotación toma el tipo de sus argumentos y no puede recibir tipos distintos
  (`pruebas/asm_errores/invalidos/parametro_con_tipos_distintos.cps`). Si la función no
  se llama, o solo recibe argumentos de otro parámetro sin anotación, el back-end avisa
  o rechaza el programa en vez de generar código incorrecto.
- Una `integer[]` ya creada no se puede usar como `float[]` (sus casillas tienen otra
  representación); un literal sí: `let a: float[] = [1, 2];`.
- Un método no se puede usar como valor (`let f = obj.metodo;`).
- `float` se imprime con 6 decimales; a partir de 2^31 se omite la parte decimal y a
  partir de 2·10^18 se imprime `inf`.
- `%` de `float` usa `a - b * trunc(a / b)`, con el cociente limitado a 32 bits.
- Los saltos condicionales de MIPS alcanzan ±128 KB: un programa de más de unas 30 000
  instrucciones podría no llegar a las rutinas de error del runtime.
