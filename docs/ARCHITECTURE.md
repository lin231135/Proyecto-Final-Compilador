# Arquitectura del compilador

Compilador de **Compiscript** (subconjunto de TypeScript) que produce ensamblador
MIPS32 y AArch64 pasando por código intermedio de tres direcciones (TAC). Reúne las
tres fases del proyecto: análisis léxico, sintáctico y semántico; código intermedio,
temporales y tabla de símbolos extendida; y generación de código final, con secuencias
de llamada y asignación de registros. El detalle de esta última fase está en
[Generacion_Codigo.md](Generacion_Codigo.md).

## 1. Flujo

```
                 programa.cps
                      │
        ┌─────────────▼──────────────┐
  (1)   │ ANTLR  (grammar/Compiscript.g4)   lexer + parser  →  árbol sintáctico
        └─────────────┬──────────────┘      errores léxicos/sintácticos (línea:columna)
                      │ ParseTree
        ┌─────────────▼──────────────┐
  (2)   │ SemanticVisitor (semantico/)      pasada 1: prepass (funciones y clases)
        │                                   pasada 2: tipos, ámbitos, funciones, clases…
        └─────────────┬──────────────┘      → tabla de símbolos + errores semánticos
                      │ árbol anotado: ctx.scope (entornos) y ctx.tipo (tipos)
              ¿hay errores? ── sí ──► se muestran (tipo + ubicación); NO se genera TAC
                      │ no
        ┌─────────────▼──────────────┐
  (3)   │ TACGenerator (codegen/generator.py)   Visitor de ANTLR sobre el MISMO árbol
        │   · traduce cada construcción a TAC
        │   · asigna/recicla temporales
        │   · completa la tabla de símbolos (offset, tamaño, AR, etiquetas)
        └─────────────┬──────────────┘
                      │
     TAC (codegen/tac.py)  +  tabla de símbolos extendida (codegen/report.py)
                      │
        ┌─────────────▼──────────────┐
  (4)   │ backend/                          CFG, liveness y next-use (cfg.py)
        │   · secuencias de llamada         getReg y descriptores (regalloc.py)
        │   · asignación de registros       traducción común (generador.py)
        │   · traducción de cada instr.     MIPS32 (mips.py) · AArch64 (aarch64.py)
        └─────────────┬──────────────┘      → error de back-end si no se puede traducir
                      │
              ensamblador + runtime
                      │
  (5)   simulador/   interno (MIPS y AArch64) · MARS · SPIM · nativo en la Raspberry
                      │
        CLI (main.py)  ·  IDE (ide/app.py)  ·  batería (pruebas/runner.py)
```

`driver.analizar(fuente)` ejecuta (1)–(3) y devuelve un `Resultado` con los
errores, el árbol, la tabla, el TAC y el generador. Es el **único** punto de
entrada: el IDE, la CLI y las pruebas lo usan; nadie más instancia
lexer/parser/visitor. `backend.generar_ensamblador(resultado, target)` hace (4) y
`simulador.ejecucion.ejecutar_codigo(codigo, target, medio)` hace (5).

## 2. Estructura del repositorio

```
main.py                CLI (TAC, ensamblador, ejecucion); sin args abre el IDE
driver.py              analizar(fuente) -> Resultado   (pipeline completo)
build_grammar.py       regenera generated/ desde grammar/Compiscript.g4

grammar/Compiscript.g4 gramática ANTLR de Compiscript
generated/             lexer/parser/visitor generados por ANTLR (VERSIONADO: no hace falta Java para correr)

core/                  contrato compartido
  types.py               sistema de tipos (integer, float, string, boolean, arreglos, clases, funciones)
  symbols.py             Symbol / Scope / SymbolTable  (con los campos de codegen)
  memory.py              tamaños, ActivationRecord, ClassLayout   ← tabla de símbolos extendida
  errors.py              SemanticError / ErrorReporter
  runtime.py             contrato de ejecucion: enteros de 32 bits, formato de float, mensajes

semantico/             análisis semántico (Visitor de ANTLR, un mixin por área)
  prepass.py             pasada 1: funciones globales y clases por adelantado
  scope_mixin.py         estado compartido (tabla, errores, pilas)
  type_mixin.py          expresiones, tipos, listas, asignaciones
  function_mixin.py      ámbitos, funciones, control de flujo
  class_mixin.py         clases, this, new, herencia
  visitor.py             SemanticVisitor = combinación de los mixins

codegen/               generación de código intermedio
  tac.py                 instrucciones TAC, TempManager (reciclaje), TACFunction/TACProgram
  generator.py           TACGenerator: el Visitor que traduce
  report.py              reporte de la tabla de símbolos extendida (AR, layout, closures)
  interpreter.py         simulador de TAC: la referencia con la que se comparan los back-ends

backend/               generación de código final
  cfg.py                 bloques básicos, CFG, liveness, next-use
  regalloc.py            getReg, descriptores, variables fijas en registros
  generador.py           análisis del programa y traducción de cada instrucción
  target.py              interfaz con el procesador destino
  mips.py, mips_runtime.py          MIPS32
  aarch64.py, aarch64_runtime.py    AArch64 (Raspberry Pi 4)

simulador/             ejecución del ensamblador
  mips.py, aarch64.py    simuladores en Python, con verificación de la convención de llamada
  ejecucion.py           interno, MARS, SPIM o nativo, con la misma interfaz

scripts/               probar_en_raspberry.sh
arbol/                 árbol sintáctico → imagen (Graphviz) para el IDE
ide/app.py             IDE (CustomTkinter)
pruebas/               batería .cps (válidos/inválidos) + runner
tests/                 pytest
docs/                  esta documentación
```

## 3. Contrato entre el análisis semántico y el generador

El generador **no** vuelve a analizar el programa; confía en el semántico y
reutiliza lo que este deja en el árbol:

| Anotación | Quién la pone | Quién la usa |
|---|---|---|
| `ctx.scope` en `FunctionDeclaration`, `ClassDeclaration`, `Block`, `ForStatement`, `ForeachStatement`, `TryCatchStatement` | `function_mixin` / `class_mixin` | `TACGenerator._entrar` cambia de `Scope`; `scope.resolve(nombre)` devuelve el mismo `Symbol` que creó el semántico |
| `ctx.tipo` en expresiones, `new`, `this`, `leftHandSide` | `type_mixin` / `class_mixin` | resolución de métodos y campos por tipo |
| `visitor.clases` (`ClassType` con campos, métodos y padre) | prepass / `class_mixin` | layout de objetos, despacho |

Si se agrega una construcción nueva que abra un entorno, el semántico debe
asignar `ctx.scope` y el generador entrar a él con `_entrar`.

## 4. Cómo funciona el generador

- **Un Visitor de ANTLR.** Cada `visit*` de una expresión **devuelve el lugar**
  (variable, temporal o literal) donde queda su valor; las sentencias no
  devuelven nada. `visitLeftHandSide` pliega el átomo y los sufijos
  (`.campo`, `[i]`, `(args)`) de izquierda a derecha, igual que el semántico.
- **Estado por función** (`FuncState`): AR, función TAC en construcción,
  `TempManager`, pila de bucles (para `break`/`continue`).
- **Código de saltos** (`jump_if_false`/`jump_if_true`): las condiciones se
  compilan directamente a saltos (cortocircuito de `&&`/`||`, `!` intercambia
  destinos, comparaciones fusionadas en `if a op b goto`). Solo se materializa
  un boolean cuando su valor se guarda.
- **Temporales**: se liberan en cuanto se consumen y antes de asignar el
  resultado (ver `docs/Lenguaje_Intermedio_TAC.md` §5). Cada sentencia verifica
  que no dejó temporales vivos (`temp_leaks`).
- **Fusión** (`emit_assign`): `t1 = a + b; x = t1` → `x = a + b`.
- **Símbolos**: `_bind` asigna la ranura (área estática si es global, AR si es
  local/parámetro) y rellena `storage/offset/size/frame/tac_name`; `_place`
  decide cómo se nombra una variable desde la función actual (`x`, `@x`,
  `upN.x`).
- **Clases**: `_layout_of` calcula el layout (campos heredados primero); las
  llamadas a métodos son estáticas salvo que una subclase redefina el método
  (`callv`).

## 5. Pruebas

| Qué | Dónde |
|---|---|
| Batería de programas `.cps` (válidos e inválidos) con salida esperada, fragmentos de TAC, máximo de temporales | `pruebas/` + `pruebas/runner.py` (parametrizada en `tests/test_bateria.py`) |
| TAC exacto por construcción | `tests/test_codegen_tac.py` |
| Temporales y reciclaje | `tests/test_codegen_temporales.py` |
| Tabla de símbolos, AR, layout | `tests/test_codegen_simbolos.py` |
| Ejecución del TAC en el simulador (resultados correctos) | `tests/test_codegen_ejecucion.py` |
| Cada programa válido de la batería se ejecuta en MIPS y AArch64 e imprime lo mismo que el TAC | `pruebas/` + `pruebas/runner.py` |
| CFG, liveness, next-use, `getReg`, prólogo y epílogo | `tests/test_backend.py` |
| Programas aleatorios en TAC, MIPS y AArch64; mutación del derrame de registros | `tests/test_diferencial.py`, `tests/generador_programas.py` |
| Los simuladores rechazan lo que una máquina real rechaza | `tests/test_simuladores.py` |
| Errores de las fases 1 y 2 hallados al generar código real | `tests/test_regresiones.py` |
| CLI y pipeline | `tests/test_cli.py`, `tests/test_driver.py` |
| La documentación coincide con el compilador | `tests/test_docs.py` |
| Análisis semántico (tipos, ámbitos, funciones, clases) | `tests/test_tipos.py`, `test_funciones.py`, `test_clases.py`, `test_symbols.py`, `test_mixins.py` |

## 6. Cambios respecto al proyecto anterior

Este proyecto parte del analizador semántico de `CC3032-Proyecto`. Cambios en
el front-end, todos con prueba:

- `ctx.scope` en los contextos que abren entornos (lo necesita el generador).
- `break` válido dentro de `switch` (la especificación usa `switch` con
  `break`).
- Comparación `objeto == null` / `lista != null` permitida.
- Listas de objetos: el tipo del elemento es el ancestro común
  (`[new Animal(), new Perro()]` es `Animal[]`).
- Herencia cíclica reportada como error (antes colgaba el análisis).
- Strings con secuencias de escape (`\"`) en la gramática.

## 7. Cambios en la fase de generación de código

Generar código real exigió completar las fases anteriores (cada cambio tiene prueba
en `tests/test_regresiones.py`):

- El TAC lleva tipos anotados (`Instr.ty`, `Instr.clase`), invisibles en su forma
  impresa, y la conversión `itof` explícita.
- `break`, `continue` y `return` dentro de `try` emiten `endtry`.
- Una variable llamada `t1` ya no se confunde con el temporal `t1`, y una función
  llamada `main` ya no choca con el programa principal.
- Una función anidada en un método se puede llamar y ve `this` por el enlace de acceso.
- `let d = null;` anota lo que recibe (`Symbol.tipo_asignado`) y los parámetros sin
  anotación se deducen de sus llamadas.
- El simulador de TAC sigue el contrato de `core/runtime.py`: enteros de 32 bits,
  división truncada, objetos comparados por identidad, valores por defecto y errores de
  ejecución definidos.
- Una expresión muy anidada ya no agota la recursión de Python.

## 8. Limitaciones conocidas

- El lenguaje no tiene tipos de función en las anotaciones: una función no puede
  devolverse desde otra (sí funcionan las funciones anidadas con acceso al
  entorno de definición y las funciones como valores).
- No hay `throw`: `try/catch` captura errores de ejecución (p. ej. índice fuera
  de rango).
- El TAC no tiene optimizaciones más allá del reciclaje de temporales y de las
  fusiones descritas.
- Las limitaciones del back-end están en
  [Generacion_Codigo.md](Generacion_Codigo.md#11-limitaciones).
