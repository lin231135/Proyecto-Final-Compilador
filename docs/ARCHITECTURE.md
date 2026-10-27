# Arquitectura del compilador

Compilador de **Compiscript** (subconjunto de TypeScript) que produce código
intermedio de tres direcciones (TAC). Continúa el proyecto anterior
(analizador léxico, sintáctico y semántico) y agrega la generación de código
intermedio, el manejo de temporales y la tabla de símbolos extendida con
registros de activación.

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
        CLI (main.py)  ·  IDE (ide/app.py)  ·  batería (pruebas/runner.py)
```

`driver.analizar(fuente)` ejecuta (1)–(3) y devuelve un `Resultado` con los
errores, el árbol, la tabla, el TAC y el generador. Es el **único** punto de
entrada: el IDE, la CLI y las pruebas lo usan; nadie más instancia
lexer/parser/visitor.

## 2. Estructura del repositorio

```
main.py                CLI (python main.py archivo.cps [--symbols|--tac-only]); sin args abre el IDE
driver.py              analizar(fuente) -> Resultado   (pipeline completo)
build_grammar.py       regenera generated/ desde grammar/Compiscript.g4

grammar/Compiscript.g4 gramática ANTLR de Compiscript
generated/             lexer/parser/visitor generados por ANTLR (VERSIONADO: no hace falta Java para correr)

core/                  contrato compartido
  types.py               sistema de tipos (integer, float, string, boolean, arreglos, clases, funciones)
  symbols.py             Symbol / Scope / SymbolTable  (con los campos de codegen)
  memory.py              tamaños, ActivationRecord, ClassLayout   ← tabla de símbolos extendida
  errors.py              SemanticError / ErrorReporter

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
  interpreter.py         simulador de TAC (solo para validar con la batería)

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

## 7. Limitaciones conocidas

- El lenguaje no tiene tipos de función en las anotaciones: una función no puede
  devolverse desde otra (sí funcionan las funciones anidadas con acceso al
  entorno de definición y las funciones como valores).
- No hay `throw`: `try/catch` captura errores de ejecución (p. ej. índice fuera
  de rango).
- El TAC no tiene optimizaciones más allá del reciclaje de temporales y de las
  fusiones descritas.
