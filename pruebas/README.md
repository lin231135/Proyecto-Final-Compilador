# Batería de pruebas `.cps`

```
pruebas/<categoría>/{validos,invalidos}/<nombre>.cps
```

La batería la ejecuta `pruebas/runner.py` (también desde pytest, `tests/test_bateria.py`,
y desde el IDE con **Correr batería**):

```bash
python pruebas/runner.py            # imprime "N/N pasaron" y los fallos
python -m pytest tests/test_bateria.py -q
```

## Categorías

| Categoría | Qué prueba |
|---|---|
| `tac_expresiones`, `tac_control_flujo`, `tac_funciones`, `tac_clases`, `tac_listas`, `tac_temporales` | **generación de TAC**: cada válido se compila, se ejecuta en el simulador y se comprueba su salida/TAC; cada inválido no debe producir TAC |
| `tipos`, `ambito`, `funciones`, `control_flujo`, `clases`, `listas`, `tabla_simbolos`, `generales` | análisis semántico (heredada del proyecto anterior); además, todo válido debe generar TAC sin fugas de temporales |
| `demo/` | programas para la presentación, fuera de la batería (ver abajo) |

## Cabecera de cada archivo

Comentarios `//` al inicio del archivo:

```cps
// @caso: descripción corta                       (obligatoria)
// @error: categoria                              (inválidos; una o más)
// @salida: a | b | c                             (válidos: lo que imprime el programa al EJECUTAR el TAC)
// @contiene: texto                               (válidos: el TAC contiene ese texto; repetible)
// @no_contiene: texto                            (válidos: el TAC NO lo contiene; repetible)
// @max_temporales: N                             (válidos: ninguna función usa más de N temporales)
```

**`validos/`** exige:
1. 0 errores (léxicos, sintácticos y semánticos);
2. que se genere TAC sin error interno del generador;
3. 0 temporales vivos al final de cada sentencia (sin fugas);
4. todas las directivas `@salida`, `@contiene`, `@no_contiene` y `@max_temporales`.

**`invalidos/`** exige: al menos 1 error, que **todas** las categorías de
`@error:` aparezcan (para no dar un falso positivo de “falló, pero por otra
razón”) y que **no** se genere TAC.

Categorías de error: `tipo`, `ambito`, `funcion`, `control_flujo`, `clase`,
`lista`, `general` (errores léxicos/sintácticos y código muerto).

## `pruebas/demo/`

- `programa_completo.cps` — clases, herencia, closures, recursión, arreglos y todo
  el control de flujo. Debe dar **0 errores** y generar TAC.
- `programa_errores.cps` — exactamente **un error de cada una** de las 7
  categorías.

```bash
python main.py pruebas/demo/programa_completo.cps --symbols
python main.py pruebas/demo/programa_errores.cps
```
