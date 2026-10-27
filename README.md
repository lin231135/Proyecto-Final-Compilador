# Proyecto 2 — Generación de código intermedio para Compiscript

Construcción de Compiladores · UVG 2026

Compilador de **Compiscript** (subconjunto de TypeScript) que, a partir del
árbol sintáctico y la tabla de símbolos del análisis semántico, genera código
intermedio de tres direcciones (**TAC**). Continúa el
[proyecto anterior](https://github.com/lin231135/CC3032-Proyecto) (análisis
léxico, sintáctico y semántico con ANTLR).

| Entregable del enunciado | Dónde está |
|---|---|
| Generación de TAC (expresiones, control de flujo, funciones, clases, listas) | `codegen/generator.py` |
| Manejo y reciclaje de temporales | `codegen/tac.py` (`TempManager`), `docs/Lenguaje_Intermedio_TAC.md` §5 |
| Tabla de símbolos extendida y registros de activación | `core/memory.py`, `core/symbols.py`, `docs/Tabla de Simbolos.md` |
| Documentación del lenguaje intermedio (con ejemplos y supuestos) | `docs/Lenguaje_Intermedio_TAC.md` |
| Documentación de la arquitectura | `docs/ARCHITECTURE.md` |
| Batería de pruebas (casos exitosos y fallidos) | `pruebas/`, `tests/` |
| IDE funcional | `ide/app.py` (`python main.py`) |

## Requisitos e instalación

- Python 3.11+
- (Opcional) Java, solo si se modifica la gramática y hay que regenerar el parser
- (Opcional) Graphviz (`dot` en el `PATH`) para ver el árbol sintáctico como
  imagen en el IDE; sin él se muestra como texto

```bash
pip install -r requirements.txt
```

El parser de ANTLR **ya viene generado** en `generated/` (versionado), así que
no hace falta Java para ejecutar el compilador. Solo si se cambia
`grammar/Compiscript.g4`:

```bash
python build_grammar.py
```

## Cómo ejecutar

```bash
# IDE gráfico: editar, compilar, ver TAC / errores / tabla de símbolos / árbol / batería
python main.py

# Línea de comandos
python main.py programa.cps               # imprime el TAC (o los errores y sale con código 1)
python main.py programa.cps --symbols     # + tabla de símbolos, registros de activación, layout de objetos
python main.py programa.cps --tac-only    # solo el TAC (para redirigir a un archivo)

# Batería de pruebas .cps (válidos e inválidos)
python pruebas/runner.py

# Todas las pruebas unitarias
python -m pytest -q
```

El IDE tiene estilo oscuro tipo Visual Studio Code: editor con resaltado de sintaxis,
numeración de líneas, línea actual y errores marcados, explorador de casos de prueba
(doble clic para abrir), panel inferior con pestañas y barra de estado.

| Atajo | Acción |
|---|---|
| **F5** (o Ctrl+Enter) | Compilar: genera el TAC y llena los paneles *Código intermedio*, *Problemas* (doble clic salta a la línea), *Tabla de símbolos* y *Árbol sintáctico* |
| **F6** | Ejecutar el TAC en el simulador y mostrar la salida del programa |
| **F7** | Correr la batería de pruebas de `pruebas/` |
| Ctrl+S / Ctrl+O | Guardar / abrir |
| Ctrl+/ | Comentar o descomentar las líneas |
| Ctrl + rueda, Ctrl +/-, Ctrl+0 | Zoom de la letra del editor |

## Ejemplo

```cps
function fact(n: integer): integer {
  if (n <= 1) { return 1; }
  return n * fact(n - 1);
}
print(fact(5));
```

```
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

## Qué soporta

Todo lo que pide el enunciado y el resto del lenguaje de `docs/Especificaciones.md`:

- **Expresiones**: `+ - * / %`, comparaciones, `&& || !` con cortocircuito,
  `?:`, unarios; `let`/`var`/`const`, asignaciones (también encadenadas).
- **Control de flujo**: `if/else`, `while`, `do-while`, `for`, `foreach`,
  `switch` (con *fallthrough*), `break`, `continue`, `try/catch`.
- **Funciones**: parámetros, retorno, recursión (directa y mutua), funciones
  anidadas y **closures** (acceso al entorno de definición por enlace de
  acceso), funciones como valores.
- **Clases**: `new` + constructor, atributos (con valores iniciales), métodos,
  `this`, herencia, sobrescritura con despacho dinámico.
- **Listas**: creación, indexación, asignación indexada, listas anidadas.
- **Errores**: léxicos, sintácticos y semánticos con su tipo y ubicación
  (línea:columna); si hay errores no se genera TAC.

## Documentación

- [`docs/Lenguaje_Intermedio_TAC.md`](docs/Lenguaje_Intermedio_TAC.md): el lenguaje
  intermedio, la traducción de cada construcción (ejemplos reales), los temporales
  y los supuestos de diseño.
- [`docs/Tabla de Simbolos.md`](docs/Tabla%20de%20Simbolos.md): direcciones,
  tamaños, registros de activación, layout de objetos, closures.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): arquitectura, contrato entre fases,
  estructura del repositorio y cómo se prueba.
- [`docs/Especificaciones.md`](docs/Especificaciones.md): el lenguaje Compiscript.
- [`pruebas/README.md`](pruebas/README.md): convención de la batería de pruebas.
