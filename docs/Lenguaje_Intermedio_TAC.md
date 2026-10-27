# Lenguaje intermedio: código de tres direcciones (TAC)

Especificación del lenguaje intermedio que genera el compilador de Compiscript
(`codegen/`), con la traducción de **cada** construcción del lenguaje y los
supuestos de diseño. Todos los ejemplos son la salida real del compilador:
`tests/test_docs.py` los recompila y falla si este documento se desactualiza.

- [1. Forma de un programa TAC](#1-forma-de-un-programa-tac)
- [2. Operandos](#2-operandos)
- [3. Conjunto de instrucciones](#3-conjunto-de-instrucciones)
- [4. Traducción de cada construcción](#4-traducción-de-cada-construcción)
- [5. Variables temporales: asignación y reciclaje](#5-variables-temporales-asignación-y-reciclaje)
- [6. Convenciones de llamada y entorno de ejecución](#6-convenciones-de-llamada-y-entorno-de-ejecución)
- [7. Supuestos y decisiones de diseño](#7-supuestos-y-decisiones-de-diseño)
- [8. Simulador de TAC](#8-simulador-de-tac)

## 1. Forma de un programa TAC

Un programa es una lista de **funciones**. Cada función es un bloque
`func nombre(parámetros): … endfunc` con una instrucción por línea; las
etiquetas (`L1:`) van sin sangría.

| Función | Contenido |
|---|---|
| `main` | las sentencias del nivel superior del programa (siempre es la última) |
| `f` | una función global `f` |
| `f.g` | una función `g` anidada dentro de `f` (el nombre calificado evita choques) |
| `Clase.metodo` | un método; su primer parámetro es siempre `this` |
| `Clase._init(this)` | inicializa los campos con valor inicial (`let x: integer = 5;`); solo existe si la clase los tiene |

No hay una instrucción de “inicio de programa”: la ejecución comienza en `main`.
Toda función termina en `return` (se agrega uno implícito si el código fuente no
lo tiene), excepto `main`.

## 2. Operandos

Cada instrucción trabaja con *lugares* (places) y literales:

| Operando | Ejemplo | Significado |
|---|---|---|
| variable local / parámetro | `x`, `n` | ranura en el registro de activación (AR) de la función actual. Si dos bloques declaran el mismo nombre, el segundo se renombra `x_2`, `x_3`… |
| temporal | `t1`, `t2` | valor intermedio; ver [§5](#5-variables-temporales-asignación-y-reciclaje) |
| variable global | `@total` | variable declarada en el nivel superior; vive en el **área estática** |
| variable de función envolvente | `up1.c`, `up2.a` | variable de la función que contiene (lexicamente) a la actual, alcanzada con `N` saltos del **enlace de acceso** (closures) |
| `this` | `this` | primer parámetro de todo método |
| literal | `5`, `3.14`, `"hola"`, `true`, `false`, `null` | constante |

Una instrucción nunca contiene una expresión anidada: cada instrucción tiene a
lo más **una operación** (de ahí “tres direcciones”: destino, operando
izquierdo y operando derecho).

## 3. Conjunto de instrucciones

| Instrucción | Significado |
|---|---|
| `x = y` | copia |
| `x = a op b` | operación binaria. `op` ∈ `+ - * / %` (aritméticas, `+` también concatena strings) y `== != < <= > >=` (producen boolean) |
| `x = - a`  /  `x = ! a` | negación aritmética / lógica |
| `L:` | etiqueta |
| `goto L` | salto incondicional |
| `if a goto L` | salta si `a` es verdadero |
| `ifFalse a goto L` | salta si `a` es falso |
| `if a op b goto L` | salto condicional con comparación fusionada (`op` relacional): evita materializar un boolean |
| `param a` | empuja el argumento `a` para la siguiente llamada |
| `x = call f, n` / `call f, n` | llama a la función `f` con los últimos `n` `param`; `x` recibe el valor de retorno (se omite si la función es `void`) |
| `x = callv obj.m, n` | llamada **virtual**: busca el método `m` en la clase real de `obj` (despacho dinámico) |
| `x = callc f, n` | llamada **indirecta**: `f` es un valor-función (ver `closure`) |
| `return a` / `return` | retorna de la función, con o sin valor |
| `x = new Clase, size` | reserva `size` bytes para un objeto (tamaño del [layout](Tabla%20de%20Simbolos.md)) |
| `x = obj.campo` / `obj.campo = a` | lee / escribe un atributo |
| `x = newlist n` | crea una lista de `n` elementos |
| `x = a[i]` / `a[i] = b` | lee / escribe un elemento |
| `x = len a` | cantidad de elementos de la lista `a` |
| `x = closure f` | crea un valor-función con la función `f` y el entorno actual (enlace de acceso) |
| `try L` / `endtry` | instala / retira el manejador cuyo código empieza en `L` |
| `catch e` | primera instrucción de un manejador: `e` recibe el error capturado |

## 4. Traducción de cada construcción

### 4.1 Expresiones aritméticas (`+ - * /`) y precedencia

La precedencia y la asociatividad a la izquierda las resuelve la gramática
(ANTLR); el generador recorre el árbol en post-orden, así que cada operación
usa los resultados de sus hijos:

```cps
let a: integer = 2;
let b: integer = 3;
let r: integer = (a + b) * 4 - a / 2;
```

```tac
func main():
    @a = 2
    @b = 3
    t1 = @a + @b
    t1 = t1 * 4
    t2 = @a / 2
    @r = t1 - t2
endfunc
```

`(a + b) * 4` se calcula antes que `a / 2` porque así lo dicta el árbol, y los
temporales se reciclan (`t1` se reutiliza para el producto; ver §5).

### 4.2 Expresiones lógicas y comparaciones

`&&` y `||` usan **cortocircuito**: se traducen con saltos, de modo que el
operando derecho solo se evalúa si hace falta. Las comparaciones dentro de una
condición se fusionan en `if a op b goto L` (con el operador invertido cuando
se salta por falso). Solo cuando el resultado debe guardarse en una variable se
materializa `true`/`false`:

```cps
let a: integer = 1;
let ok: boolean = a > 0 && a < 10 || !(a == 5);
```

```tac
func main():
    @a = 1
    if @a <= 0 goto L4
    if @a < 10 goto L3
L4:
    if @a == 5 goto L1
L3:
    t1 = true
    goto L2
L1:
    t1 = false
L2:
    @ok = t1
endfunc
```

### 4.3 Declaraciones y asignaciones

`let x = e;` / `const x = e;` / `x = e;` se emiten como `x = …`. Cuando la
última instrucción calculó un temporal que se copia enseguida a la variable, el
generador las **fusiona** (`t1 = a + b; x = t1` → `x = a + b`) y el temporal
desaparece. Los ejemplos de arriba muestran variables globales (`@a`). Una
declaración sin valor (`let c: integer;`) solo reserva la ranura.

### 4.4 `if` / `else`

La condición salta a la rama `else` (o al final) cuando es falsa:

```cps
let x: integer = 7;
if (x < 10) { print("chico"); } else { print("grande"); }
```

```tac
func main():
    @x = 7
    if @x >= 10 goto L1
    param "chico"
    call print, 1
    goto L2
L1:
    param "grande"
    call print, 1
L2:
endfunc
```

### 4.5 `while`

```cps
let i: integer = 0;
while (i < 3) { print(i); i = i + 1; }
```

```tac
func main():
    @i = 0
L1:
    if @i >= 3 goto L2
    param @i
    call print, 1
    @i = @i + 1
    goto L1
L2:
endfunc
```

### 4.6 `do-while`

El cuerpo va antes de la condición, que salta hacia atrás si es verdadera:

```cps
let i: integer = 0;
do { i = i + 1; } while (i < 3);
```

```tac
func main():
    @i = 0
L1:
    @i = @i + 1
L2:
    if @i < 3 goto L1
L3:
endfunc
```

### 4.7 `for`, `break` y `continue`

`continue` salta a la etiqueta del incremento (`L2`) y `break` a la del final
(`L3`) **del bucle que los contiene**: el generador mantiene una pila de bucles.

```cps
for (let i: integer = 0; i < 3; i = i + 1) {
  if (i == 1) { continue; }
  print(i);
}
```

```tac
func main():
    i = 0
L1:
    if i >= 3 goto L3
    if i != 1 goto L4
    goto L2
L4:
    param i
    call print, 1
L2:
    i = i + 1
    goto L1
L3:
endfunc
```

### 4.8 `foreach`

Usa dos temporales que viven durante todo el bucle: el índice (`t1`) y la
longitud (`t2`).

```cps
let xs: integer[] = [4, 5];
foreach (x in xs) { print(x); }
```

```tac
func main():
    t1 = newlist 2
    t1[0] = 4
    t1[1] = 5
    @xs = t1
    t1 = 0
    t2 = len @xs
L1:
    if t1 >= t2 goto L3
    x = @xs[t1]
    param x
    call print, 1
L2:
    t1 = t1 + 1
    goto L1
L3:
endfunc
```

### 4.9 `switch`

Primero una cadena de comparaciones despacha al caso; después van los cuerpos
**en orden**, de modo que, como en la especificación del lenguaje, un caso sin
`break` cae al siguiente (*fallthrough*). `break` salta al final del `switch`.

```cps
let n: integer = 2;
switch (n) {
  case 1: print("uno"); break;
  case 2: print("dos");
  default: print("otro");
}
```

```tac
func main():
    @n = 2
    if @n == 1 goto L2
    if @n == 2 goto L3
    goto L4
L2:
    param "uno"
    call print, 1
    goto L1
L3:
    param "dos"
    call print, 1
L4:
    param "otro"
    call print, 1
L1:
endfunc
```

### 4.10 `try` / `catch`

```cps
let xs: integer[] = [1];
try { print(xs[5]); } catch (e) { print("error"); }
```

```tac
func main():
    t1 = newlist 1
    t1[0] = 1
    @xs = t1
    try L1
    t1 = @xs[5]
    param t1
    call print, 1
    endtry
    goto L2
L1:
    catch e
    param "error"
    call print, 1
L2:
endfunc
```

### 4.11 Funciones: definición, parámetros, llamada y retorno

Los argumentos se evalúan primero (de izquierda a derecha) y **después** se
emiten todos los `param` seguidos, de modo que las llamadas anidadas
(`f(g(x))`) no mezclan sus argumentos. Una función `void` se llama sin destino.

```cps
function suma(a: integer, b: integer): integer { return a + b; }
let r: integer = suma(2, 3);
```

```tac
func suma(a, b):
    t1 = a + b
    return t1
endfunc

func main():
    param 2
    param 3
    @r = call suma, 2
endfunc
```

### 4.12 Recursión

Una función se resuelve por su etiqueta, así que la recursión directa y la
mutua no necesitan tratamiento especial (el análisis previo registra todas las
funciones globales antes de compilar los cuerpos).

```cps
function fact(n: integer): integer {
  if (n <= 1) { return 1; }
  return n * fact(n - 1);
}
print(fact(5));
```

```tac
func fact(n):
    if n > 1 goto L1
    return 1
L1:
    t1 = n - 1
    param t1
    t1 = call fact, 1
    t1 = n * t1
    return t1
endfunc

func main():
    param 5
    t1 = call fact, 1
    param t1
    call print, 1
endfunc
```

### 4.13 Funciones anidadas y closures

`inc` está declarada dentro de `contador` y usa su variable `c`. Se genera como
la función `contador.inc` y accede a `c` con `up1.c`: un salto por el **enlace
de acceso** del registro de activación, que apunta al AR de la función donde
`inc` fue definida (y no al de quien la llama). Con tres niveles aparece `up2.x`,
etc. El reporte de la tabla de símbolos lista cada uno de estos accesos.

```cps
function contador(): integer {
  let c: integer = 0;
  function inc(): integer { c = c + 1; return c; }
  inc();
  return inc();
}
print(contador());
```

```tac
func contador():
    c = 0
    t1 = call contador.inc, 0
    t1 = call contador.inc, 0
    return t1
endfunc

func contador.inc():
    up1.c = up1.c + 1
    return up1.c
endfunc

func main():
    t1 = call contador, 0
    param t1
    call print, 1
endfunc
```

Una función también puede usarse como **valor**: `closure f` captura el entorno
actual y `callc` la invoca de forma indirecta.

```cps
function f(): integer { return 1; }
let g = f;
print(g());
```

```tac
func f():
    return 1
endfunc

func main():
    @g = closure f
    t1 = callc @g, 0
    param t1
    call print, 1
endfunc
```

### 4.14 Clases, objetos, herencia, `this` y métodos

- `new C(args)` reserva el objeto (`new C, size`), ejecuta los inicializadores
  de campos de la cadena de herencia (`Clase._init`, de la raíz hacia la
  clase) y luego el constructor (el propio o el heredado), con el objeto como
  primer argumento.
- `this` es el primer parámetro de todo método; `this.x` es un acceso a atributo.
- `obj.m(args)` pasa `obj` como primer `param`. Si ninguna subclase redefine
  `m`, la llamada es **estática** (`call Clase.m`); si alguna la redefine se usa
  **despacho dinámico** (`callv obj.m`), que elige el método según la clase
  real del objeto (aquí `a` es un `Animal` pero contiene un `Perro`).

```cps
class Animal {
  let nombre: string;
  let patas: integer = 4;
  function constructor(nombre: string) { this.nombre = nombre; }
  function hablar(): string { return this.nombre + " hace ruido"; }
}
class Perro : Animal {
  function hablar(): string { return this.nombre + " ladra"; }
}
let a: Animal = new Perro("Rex");
print(a.hablar());
a.patas = 3;
```

```tac
func Animal._init(this):
    this.patas = 4
    return
endfunc

func Animal.constructor(this, nombre):
    this.nombre = nombre
    return
endfunc

func Animal.hablar(this):
    t1 = this.nombre
    t1 = t1 + " hace ruido"
    return t1
endfunc

func Perro.hablar(this):
    t1 = this.nombre
    t1 = t1 + " ladra"
    return t1
endfunc

func main():
    t1 = new Perro, 24
    param t1
    call Animal._init, 1
    param t1
    param "Rex"
    call Animal.constructor, 2
    @a = t1
    param @a
    t1 = callv @a.hablar, 1
    param t1
    call print, 1
    @a.patas = 3
endfunc
```

### 4.15 Listas

`[e0, e1, …]` crea la lista y asigna cada elemento; los índices pueden ser
expresiones y las listas pueden anidarse:

```cps
let xs: integer[] = [10, 20, 30];
let i: integer = 1;
xs[i] = xs[0] + xs[i + 1];
let m: integer[][] = [[1, 2], [3, 4]];
print(m[1][0]);
```

```tac
func main():
    t1 = newlist 3
    t1[0] = 10
    t1[1] = 20
    t1[2] = 30
    @xs = t1
    @i = 1
    t1 = @xs[0]
    t2 = @i + 1
    t2 = @xs[t2]
    t1 = t1 + t2
    @xs[@i] = t1
    t1 = newlist 2
    t2 = newlist 2
    t2[0] = 1
    t2[1] = 2
    t1[0] = t2
    t2 = newlist 2
    t2[0] = 3
    t2[1] = 4
    t1[1] = t2
    @m = t1
    t1 = @m[1]
    t1 = t1[0]
    param t1
    call print, 1
endfunc
```

## 5. Variables temporales: asignación y reciclaje

**Asignación.** `TempManager.new_temp()` devuelve el temporal *libre de menor
número*; si no hay ninguno libre acuña uno nuevo (`tN+1`).

**Reciclaje.** Un temporal se libera en cuanto su valor se **consume**, es
decir, justo después de emitir la instrucción que lo usa y *antes* de asignar el
temporal del resultado. Eso permite que el resultado reutilice el temporal de
uno de sus operandos (`t1 = t1 * t2`).

1. Se evalúan los operandos (cada uno deja su valor en una variable, un literal
   o un temporal).
2. Se **liberan** los operandos que eran temporales.
3. Se pide el temporal del resultado y se emite la instrucción.

Resultado: una expresión necesita tantos temporales como su *profundidad de
evaluación*, no uno por subexpresión. `(a+b)*(c+d) - (a-b)*(c-d)` tiene 7
operaciones pero usa solo **3** temporales:

```cps
function calc(a: integer, b: integer, c: integer, d: integer): integer {
  return (a + b) * (c + d) - (a - b) * (c - d);
}
```

```tac
func calc(a, b, c, d):
    t1 = a + b
    t2 = c + d
    t1 = t1 * t2
    t2 = a - b
    t3 = c - d
    t2 = t2 * t3
    t1 = t1 - t2
    return t1
endfunc

func main():
endfunc
```

Reglas adicionales:

- **Entre sentencias**: ninguna sentencia deja temporales vivos al terminar
  (el generador lo comprueba y lo expone en `temp_leaks`; las pruebas exigen
  que sea `0`). Por eso cada sentencia vuelve a empezar desde `t1`.
- **Fusión de asignaciones**: `x = a + b` no usa ningún temporal.
- **Temporales largos**: el índice y la longitud de un `foreach`, o el
  resultado de un `?:`, viven durante toda su construcción; las sentencias del
  cuerpo piden temporales distintos, nunca los pisan.
- Cada temporal usado ocupa una ranura de 8 bytes al final del registro de
  activación de su función (ver [Tabla de Símbolos](Tabla%20de%20Simbolos.md)).

## 6. Convenciones de llamada y entorno de ejecución

- **Argumentos**: `param` en orden; el llamado los recibe en los parámetros que
  declara su cabecera (`func suma(a, b)`). Los métodos reciben `this` primero.
- **Retorno**: `return a` deja el valor en `<valor_retorno>` del AR; el
  llamador lo toma con `x = call …`.
- **Enlaces**: todo AR tiene *enlace de control* (quién llamó) y *enlace de
  acceso* (AR de la función donde se **definió**). Una función de primer nivel
  tiene como enlace de acceso a `main`; una anidada, al AR de su función
  contenedora. `upN.x` = seguir `N` enlaces de acceso y leer `x`.
- **Objetos**: cada objeto empieza con un puntero a su clase (descriptor);
  luego van los campos heredados y los propios (offsets en el reporte de la
  tabla de símbolos). `callv` consulta ese descriptor.
- **Globales**: `@x` apunta al área estática; no pasan por enlaces.

## 7. Supuestos y decisiones de diseño

1. **El TAC solo se genera si el análisis semántico no reporta errores.** El
   generador asume un programa bien tipado (reglas de tipos, ámbitos, aridad,
   herencia no cíclica, etc. ya comprobadas) y reutiliza el árbol, los `Scope`
   y los tipos del análisis.
2. **Sin tipos en el TAC.** Los tipos se usan al generar (tamaños, resolución
   de métodos) pero no aparecen en las instrucciones. Los enteros y flotantes
   comparten los operadores; `/` entre enteros es división entera.
3. **Operandos simbólicos, memoria en la tabla de símbolos.** El TAC nombra
   variables; sus desplazamientos y tamaños están en la tabla de símbolos
   extendida (`--symbols`). Así el TAC es legible y un back-end puede traducir
   cada nombre a `AR + offset`.
4. **Convención de tamaños**: `integer`=4, `float`=8, `boolean`=1; `string`,
   listas, objetos y funciones son referencias de 8 bytes; cada ranura se
   alinea a su tamaño.
5. **Despacho**: estático cuando es seguro (nadie redefine el método) y
   dinámico (`callv`) cuando una subclase lo redefine.
6. **Constructores**: no existe `super`; si una subclase declara su propio
   constructor, el del padre no se invoca automáticamente. Los inicializadores
   de campo de **toda** la cadena sí se ejecutan antes del constructor.
7. **`switch` con *fallthrough*** (como en `docs/Especificaciones.md`): la
   comparación usa `==` y `break` es válido dentro de un `switch`. `continue`
   solo es válido en bucles.
8. **`try/catch`**: el lenguaje no tiene `throw`; el error que se captura es el
   que produce la ejecución (por ejemplo un índice fuera de rango). La variable
   del `catch` es un string.
9. **Valores-función**: una función puede guardarse en una variable o pasarse
   como argumento (`closure`/`callc`). Como el lenguaje no tiene tipos de
   función en las anotaciones, una función no puede *devolverse* desde otra
   (el analizador lo rechaza porque `return` exige el tipo declarado); sí se
   soportan funciones anidadas que acceden al entorno de su definición.
10. **Sin optimizaciones** más allá de la fusión de asignaciones, la fusión
    `if a op b goto` y el reciclaje de temporales.
11. **Strings** admiten secuencias de escape (`\"`, `\n`, `\\`).
12. **Memoria dinámica**: el TAC no libera objetos ni listas (no hay recolector
    ni `delete` en el lenguaje).

## 8. Simulador de TAC

`codegen/interpreter.py` ejecuta el TAC (marcos con enlace de acceso, área
estática, objetos, listas, closures, despacho virtual, `try/catch`) y devuelve
lo que imprime el programa. No es un back-end: sirve para que la batería de
pruebas compruebe que la traducción es **correcta** (`// @salida:`), y está
disponible en el IDE con el botón *Ejecutar TAC*.

```bash
python main.py programa.cps              # TAC
python main.py programa.cps --symbols    # TAC + tabla de símbolos y registros de activación
```
