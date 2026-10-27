# Tabla de símbolos extendida y registros de activación

La tabla de símbolos nace en el análisis semántico (entornos anidados, tipos)
y la **generación de código la completa** con la información que necesita un
back-end: dirección (desplazamiento), tamaño, etiqueta y registro de
activación de cada símbolo. Es la misma tabla, no una copia: el generador de
TAC consulta los `Scope` del análisis y escribe en los mismos `Symbol`.

- [1. Qué guarda cada símbolo](#1-qué-guarda-cada-símbolo)
- [2. Cómo interactúa con cada fase](#2-cómo-interactúa-con-cada-fase)
- [3. Tamaños y alineación](#3-tamaños-y-alineación)
- [4. Registros de activación](#4-registros-de-activación)
- [5. Área estática (variables globales)](#5-área-estática-variables-globales)
- [6. Layout de objetos](#6-layout-de-objetos)
- [7. Funciones anidadas y closures](#7-funciones-anidadas-y-closures)
- [8. Ejemplo completo](#8-ejemplo-completo)
- [9. Simplificaciones](#9-simplificaciones)

## 1. Qué guarda cada símbolo

`core/symbols.py::Symbol`:

| Campo | Lo llena | Significado |
|---|---|---|
| `name`, `type`, `kind` (`var`/`const`/`param`/`function`/`class`) | análisis semántico | identidad y tipo (`core/types.py`) |
| `initialized`, `line`, `column` | análisis semántico | ubicación para los errores |
| `storage` | generación | `global` (área estática), `local`, `param`, `field`, `function`, `class` |
| `offset` | generación | desplazamiento en bytes dentro de su AR, del área estática o del objeto (campos) |
| `size` | generación | tamaño en bytes (según el tipo) |
| `frame` | generación | `ActivationRecord` que contiene la ranura (`None` para clases) |
| `tac_name` | generación | nombre del operando en el TAC: `x`, `x_2` (si otro bloque ya usó `x`), `@x` (global) |
| `label` | generación | etiqueta de las funciones: `f`, `f.g`, y de las clases |

`Scope` (global, función, clase, bloque) es el entorno léxico; `SymbolTable`
conserva **todos** los entornos creados, también los ya cerrados, para poder
mostrar su estado final.

## 2. Cómo interactúa con cada fase

| Fase | Uso de la tabla |
|---|---|
| ANTLR (léxico/sintáctico) | no la usa; produce el árbol |
| Análisis semántico, pasada 1 (`semantico/prepass.py`) | declara por adelantado funciones globales y clases (recursión mutua, herencia hacia adelante) |
| Análisis semántico, pasada 2 | crea los `Scope`, define los `Symbol` (tipo, `kind`), valida redeclaraciones/ámbitos/tipos. Deja en el árbol `ctx.scope` (entorno que abre cada función, clase y bloque) y `ctx.tipo` (tipo de cada expresión) |
| Generación de TAC (`codegen/generator.py`) | recorre el árbol con los mismos `Scope` (`ctx.scope`): resuelve cada identificador con `scope.resolve`, **asigna** `storage/offset/size/frame/tac_name/label` y decide si un acceso es local, global o `upN.` |
| Reporte (`main.py --symbols`, pestaña del IDE) | imprime la tabla con las direcciones, los registros de activación, el layout de objetos y los accesos de closures |

## 3. Tamaños y alineación

| Tipo | Bytes |
|---|---|
| `integer` | 4 |
| `float` | 8 |
| `boolean` | 1 |
| `string`, listas, objetos, funciones, `null` | 8 (referencia) |
| temporal | 8 |

Cada ranura se alinea a su propio tamaño; el AR completo se redondea a
múltiplos de 8.

## 4. Registros de activación

Cada función, método y el programa principal (`main`) tiene un
`ActivationRecord` (`core/memory.py`). Desplazamientos crecientes:

| Ranura | Contenido |
|---|---|
| `+0` `<enlace_control>` | AR de quien llamó (cadena dinámica) |
| `+8` `<enlace_acceso>` | AR de la función donde se **definió** (cadena estática) |
| `+16` `<direccion_retorno>` | dirección de retorno |
| `+24` `<valor_retorno>` | valor de retorno |
| `+32…` parámetros | en orden de declaración (los métodos llevan `this` primero) |
| siguientes | variables locales, en orden de declaración |
| al final | temporales `t1…tN`, uno por cada distinto que usó la función (ver [reciclaje](Lenguaje_Intermedio_TAC.md#5-variables-temporales-asignación-y-reciclaje)) |

- `depth` es la profundidad léxica: `main` = 0, una función de primer nivel = 1,
  una anidada = 2, etc. `parent` es el AR léxico (el que el enlace de acceso
  apunta).
- Dos bloques que declaran el mismo nombre obtienen **ranuras distintas**
  (`x`, `x_2`): no se reutilizan ranuras entre bloques.

## 5. Área estática (variables globales)

Las variables declaradas en el nivel superior no viven en el AR de `main`: están
en el área estática (`<globales>`), con su propio desplazamiento. Se nombran
`@x` en el TAC y cualquier función puede usarlas directamente, sin enlaces.
Las variables de un bloque del nivel superior (un `for`, un `{ … }`) sí son
locales de `main`.

## 6. Layout de objetos

`core/memory.py::ClassLayout`. Un objeto empieza con un puntero al
**descriptor de clase** (8 bytes, usado por `callv`); luego van los campos
heredados (mismo desplazamiento que en la clase padre, así un objeto de la
subclase se puede tratar como uno de la superclase) y después los propios.

```
Animal:  +0 <descriptor>  +8 nombre:string  +16 patas:integer      (24 B)
Perro :  +0 <descriptor>  +8 nombre (heredado)  +16 patas (heredado) (24 B)
```

El layout incluye la **tabla de métodos** de la clase (método → etiqueta
efectiva, con herencia y sobrescritura) y si tiene inicializador de campos
(`Clase._init`).

## 7. Funciones anidadas y closures

Una función anidada `g` dentro de `f` tiene `AR(g).parent = AR(f)`. Para
alcanzar una variable de `f`, `g` sigue el enlace de acceso: `depth(g) −
depth(f)` saltos. El generador lo emite como `up1.c` y registra cada uso
(variable, quién la usa, dónde está definida, saltos, desplazamiento) en la
sección “Acceso a variables de funciones envolventes” del reporte. Tres niveles
de anidamiento producen `up2.x`.

## 8. Ejemplo completo

Salida real de `python main.py ejemplo.cps --symbols` (la sección “Tabla de
símbolos”, el área estática, el layout y los registros de activación):

```cps
let total: integer = 0;
class P {
  let x: integer = 1;
  let n: string;
  function m(k: integer): integer { return this.x + k; }
}
function f(a: integer): integer {
  let c: integer = a;
  function g(): integer { c = c + total; return c; }
  return g();
}
print(f(2));
```

```symbols
[0] global
    class P: P
    function f: (integer) -> integer   [label=f]
    var total: integer   [global @total  <globales>+0  4B]
[1] class P
    var x: integer   [campo +8  4B]
    var n: string   [campo +16  8B]
[2] function m
    param k: integer   [param k  P.m+40  4B]
[3] function f
    param a: integer   [param a  f+32  4B]
    var c: integer   [local c  f+36  4B]
    function g: () -> integer   [label=f.g]
[4] function g: (sin simbolos locales)

== Area estatica (globales, 8 B) ==
    +0    [global] total: integer  (4 B)

== Layout de objetos ==
clase P  (instancia = 24 B)
    +0    <descriptor_de_clase>  (8 B)
    +8    x: integer  (4 B)
    +16   n: string  (8 B)
    metodos: m -> P.m
    inicializador de campos: P._init

== Registros de activacion ==

AR main  (profundidad 0, tamano 40 B)
    +0    [control_link] <enlace_control>  (8 B)
    +8    [access_link] <enlace_acceso>  (8 B)
    +16   [return_address] <direccion_retorno>  (8 B)
    +24   [return_value] <valor_retorno>  (8 B)
    +32   [temp] t1  (8 B)

AR P._init  (profundidad 1, AR lexico padre = main, tamano 40 B)
    +0    [control_link] <enlace_control>  (8 B)
    +8    [access_link] <enlace_acceso>  (8 B)
    +16   [return_address] <direccion_retorno>  (8 B)
    +24   [return_value] <valor_retorno>  (8 B)
    +32   [param] this: P  (8 B)

AR P.m  (profundidad 1, AR lexico padre = main, tamano 56 B)
    +0    [control_link] <enlace_control>  (8 B)
    +8    [access_link] <enlace_acceso>  (8 B)
    +16   [return_address] <direccion_retorno>  (8 B)
    +24   [return_value] <valor_retorno>  (8 B)
    +32   [param] this: P  (8 B)
    +40   [param] k: integer  (4 B)
    +48   [temp] t1  (8 B)

AR f  (profundidad 1, AR lexico padre = main, tamano 48 B)
    +0    [control_link] <enlace_control>  (8 B)
    +8    [access_link] <enlace_acceso>  (8 B)
    +16   [return_address] <direccion_retorno>  (8 B)
    +24   [return_value] <valor_retorno>  (8 B)
    +32   [param] a: integer  (4 B)
    +36   [local] c: integer  (4 B)
    +40   [temp] t1  (8 B)

AR f.g  (profundidad 2, AR lexico padre = f, tamano 32 B)
    +0    [control_link] <enlace_control>  (8 B)
    +8    [access_link] <enlace_acceso>  (8 B)
    +16   [return_address] <direccion_retorno>  (8 B)
    +24   [return_value] <valor_retorno>  (8 B)

== Acceso a variables de funciones envolventes (enlace de acceso) ==
    'c' usada en f.g, definida en f: 1 salto(s) de enlace de acceso, desplazamiento +36   (op. up1.c)
```

## 9. Simplificaciones

- El modelo de memoria es didáctico (tamaños fijos, sin ABI de una arquitectura
  real): no se genera código de máquina.
- Los AR de funciones con closures se modelan como si pudieran sobrevivir a la
  llamada; en un back-end real habría que alojarlos en el heap si una función
  se devolviera como valor (el lenguaje actual no lo permite, ver
  [supuesto 9](Lenguaje_Intermedio_TAC.md#7-supuestos-y-decisiones-de-diseño)).
- No se reutilizan las ranuras de variables de bloques ya cerrados.
- El reporte imprime los tamaños de los registros, pero no hay un
  planificador/asignador de registros de CPU (queda para la fase de código
  objeto).
