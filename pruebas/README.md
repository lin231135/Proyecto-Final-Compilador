# Batería de pruebas `.cps`

```
pruebas/<categoría>/{validos,invalidos}/<nombre>.cps
```

La batería la ejecuta `pruebas/runner.py` (también desde pytest, `tests/test_bateria.py`,
y desde el IDE con **Correr batería**):

```bash
python pruebas/runner.py                       # imprime "N/N pasaron" y los fallos
python pruebas/runner.py --simulador mars      # MIPS en MARS (MARS_JAR o tools/Mars4_5.jar)
python pruebas/runner.py --simulador spim      # MIPS en SPIM
python pruebas/runner.py --simulador nativo    # AArch64 en la Raspberry Pi 4
python -m pytest tests/test_bateria.py -q
```

Cada programa válido se compila a MIPS y a AArch64, se ejecuta y su salida debe ser
idéntica a la del TAC. Sin `--simulador` se usan los simuladores internos.

## Categorías

| Categoría | Qué prueba |
|---|---|
| `asm_llamadas` | **secuencias de llamada y retorno**: argumentos por registro y por pila, `float`, recursión profunda, recursión mutua, enlaces de acceso, closures que sobreviven a su marco, despacho virtual |
| `asm_registros` | **asignación de registros**: derrames a la pila de enteros y `float`, valores que cruzan llamadas, variables en `$s`, funciones hoja, globales y capturadas que cambian en una llamada |
| `asm_datos` | **representación**: enteros de 32 bits, `float`, strings, booleanos, listas, objetos, valores sin inicializar |
| `asm_errores` | **errores**: de ejecución (con y sin `catch`, atravesando marcos) y programas que no se pueden traducir (`invalidos/`) |
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
// @mips: texto                                   (válidos: el ensamblador MIPS contiene ese texto; repetible)
// @no_mips: texto                                (válidos: el ensamblador MIPS NO lo contiene; repetible)
// @arm: texto                                    (válidos: el ensamblador AArch64 contiene ese texto; repetible)
// @derrames: N                                   (válidos: getReg derrama a la pila al menos N veces)
// @salvados: N                                   (válidos: al menos N valores se salvan antes de una llamada)
// @codigo_salida: N                              (válidos: código de salida esperado; por defecto 0)
// @error_backend: texto                          (inválidos: lo acepta el semántico, lo rechaza el back-end)
```

**`validos/`** exige:
1. 0 errores (léxicos, sintácticos y semánticos);
2. que se genere TAC sin error interno del generador;
3. 0 temporales vivos al final de cada sentencia (sin fugas);
4. todas las directivas `@salida`, `@contiene`, `@no_contiene` y `@max_temporales`;
5. que MIPS y AArch64 se generen sin avisos y cumplan `@mips`, `@no_mips`, `@arm`,
   `@derrames` y `@salvados`;
6. que el ensamblador, al ejecutarse, imprima lo mismo que el TAC. Si el TAC no termina
   (un `while (true)` a propósito), solo se comprueba que se genere.

**`invalidos/`** exige: al menos 1 error, que **todas** las categorías de
`@error:` aparezcan (para no dar un falso positivo de “falló, pero por otra
razón”) y que **no** se genere TAC ni ensamblador. Con `@error_backend`, el programa
pasa el semántico pero el back-end debe rechazarlo con ese mensaje.

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
