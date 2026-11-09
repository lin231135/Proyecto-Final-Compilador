# Proyecto 3 — Generación de código para Compiscript

Construcción de Compiladores · UVG 2026

Compilador completo de **Compiscript** (subconjunto de TypeScript): análisis léxico y
sintáctico con ANTLR, análisis semántico, código intermedio de tres direcciones (TAC) y
generación de **ensamblador MIPS32**, ejecutable en un simulador, y de **AArch64**, nativo
en una Raspberry Pi 4.

| Entregable del enunciado | Dónde está |
|---|---|
| Secuencias de llamada y retorno (20 pts) | `backend/generador.py` (`_secuencia_de_llamada`, `_resultado`, `_gen_ret`), `backend/mips.py` (`prologo`, `epilogo`), [documentación](docs/Generacion_Codigo.md#4-secuencias-de-llamada-y-de-retorno) |
| Asignación de registros, `getReg()` (20 pts) | `backend/regalloc.py` (`Descriptores.get_reg`), `backend/cfg.py` (liveness y next-use), [documentación](docs/Generacion_Codigo.md#5-asignación-de-registros) |
| Código MIPS funcional, ejecutado en simulador, con batería (60 pts) | `backend/mips.py`, `backend/mips_runtime.py`, `simulador/`, `pruebas/asm_*/` |
| Batería de casos exitosos y fallidos | `pruebas/` (`python pruebas/runner.py`), `tests/` |
| Documentación de la arquitectura | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/Generacion_Codigo.md`](docs/Generacion_Codigo.md) |
| Cómo ejecutar el compilador | esta página y [`docs/Raspberry_Pi.md`](docs/Raspberry_Pi.md) |
| IDE funcional | `ide/app.py` (`python main.py`) |

## Requisitos e instalación

- Python 3.11+
- (Opcional) Java, para MARS o para regenerar el parser si cambia la gramática
- (Opcional) Graphviz (`dot` en el `PATH`), para ver el árbol sintáctico como imagen

```bash
pip install -r requirements.txt
```

El parser de ANTLR **ya viene generado** en `generated/`. Solo si se cambia
`grammar/Compiscript.g4`:

```bash
python build_grammar.py
```

## Cómo ejecutar

```bash
# IDE gráfico
python main.py

# Código intermedio y tabla de símbolos
python main.py programa.cps                 # TAC (o los errores, con código de salida 1)
python main.py programa.cps --symbols       # + tabla de símbolos y registros de activación

# Ensamblador
python main.py programa.cps -o programa.asm             # MIPS32
python main.py programa.cps --target arm64 -o programa.s  # AArch64 (Raspberry Pi 4)
python main.py programa.cps --asm                       # en la salida estándar
python main.py programa.cps --regs                      # marcos y asignación de registros

# Compilar y ejecutar
python main.py programa.cps --run                       # MIPS en el simulador interno
python main.py programa.cps --run --simulador mars      # en MARS
python main.py programa.cps --run --simulador spim      # en SPIM
python main.py programa.cps --run --target arm64        # en la Raspberry: en el procesador

# Pruebas
python pruebas/runner.py                    # batería .cps con los simuladores internos
python pruebas/runner.py --simulador mars   # batería con MARS
python -m pytest -q                         # todas las pruebas
```

Para ver el MIPS correr paso a paso sin instalar nada, abra
[`simulador_retro/index.html`](simulador_retro/README.md) en el navegador: un IDE retro
donde se pega el `.asm`, se ejecuta y se inspeccionan registros, pila y memoria.

Para MARS, descargue `Mars4_5.jar` y cópielo en `tools/` o indique su ruta en la variable
de entorno `MARS_JAR`. También se puede abrir el `.asm` en la interfaz de MARS: ensamblar y
ejecutar, sin cambiar ninguna opción.

### En la Raspberry Pi 4

Una Raspberry Pi 4 es ARM: **no ejecuta MIPS directamente**. El compilador genera AArch64
para correr en el procesador, y el MIPS corre en ella dentro de SPIM o MARS. Un solo
comando lo prueba todo:

```bash
bash scripts/probar_en_raspberry.sh
```

Detalles y requisitos en [`docs/Raspberry_Pi.md`](docs/Raspberry_Pi.md).

### IDE

Estilo oscuro tipo Visual Studio Code: editor con resaltado, numeración de líneas, errores
marcados, explorador de casos de prueba y panel inferior con pestañas. La pestaña
ENSAMBLADOR permite elegir procesador, dónde ejecutar y guardar el código.

| Atajo | Acción |
|---|---|
| **F5** (o Ctrl+Enter) | Compilar: llena *Código intermedio*, *Ensamblador*, *Registros*, *Problemas*, *Tabla de símbolos* y *Árbol sintáctico* |
| **F6** | Ejecutar el TAC y mostrar la salida |
| **F8** | Ejecutar el ensamblador en el medio elegido |
| **F7** | Correr la batería de pruebas |
| Ctrl+S / Ctrl+O | Guardar / abrir |
| Ctrl+/ | Comentar o descomentar las líneas |
| Ctrl + rueda, Ctrl +/-, Ctrl+0 | Zoom del editor |

## Ejemplo

```cps
function fact(n: integer): integer {
  if (n <= 1) { return 1; }
  return n * fact(n - 1);
}
print(fact(5));
```

`python main.py fact.cps --asm` genera, además del runtime:

```asm
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

## Qué soporta

Todo `docs/Especificaciones.md`, en TAC, MIPS y AArch64:

- **Expresiones**: `+ - * / %`, comparaciones, `&& || !` con cortocircuito, `?:`, unarios;
  `let`/`var`/`const`, asignaciones encadenadas; `integer`, `float` (double), `boolean`,
  `string` con concatenación y comparación.
- **Control de flujo**: `if/else`, `while`, `do-while`, `for`, `foreach`, `switch` con
  *fallthrough*, `break`, `continue`, `try/catch`.
- **Funciones**: parámetros (por registro y por pila), retorno, recursión directa y mutua,
  funciones anidadas y **closures**, funciones como valores.
- **Clases**: `new` + constructor, atributos con valores iniciales, métodos, `this`, herencia
  y sobrescritura con despacho dinámico.
- **Listas**: creación, indexación con verificación de rango, asignación, listas anidadas.
- **`print`** de cualquier valor, incluidas listas y objetos.
- **Errores**: léxicos, sintácticos y semánticos con su tipo y ubicación; errores de
  ejecución (índice fuera de rango, división entre cero, acceso a `null`) que `try/catch`
  captura aunque ocurran en otra función.

## Documentación

- [`docs/Generacion_Codigo.md`](docs/Generacion_Codigo.md): registro de activación,
  secuencias de llamada, `getReg`, traducción de cada instrucción, closures, excepciones,
  runtime y limitaciones.
- [`docs/Raspberry_Pi.md`](docs/Raspberry_Pi.md): cómo probar en la Raspberry Pi 4.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): arquitectura, contrato entre fases y
  estructura del repositorio.
- [`docs/Lenguaje_Intermedio_TAC.md`](docs/Lenguaje_Intermedio_TAC.md): el lenguaje
  intermedio, con ejemplos y supuestos.
- [`docs/Tabla de Simbolos.md`](docs/Tabla%20de%20Simbolos.md): direcciones, tamaños,
  registros de activación y layout de objetos.
- [`docs/Especificaciones.md`](docs/Especificaciones.md): el lenguaje Compiscript.
- [`pruebas/README.md`](pruebas/README.md): convención de la batería de pruebas.
