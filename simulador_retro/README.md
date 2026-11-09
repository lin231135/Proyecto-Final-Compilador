# MIPSTATION 3000 — simulador MIPS32 retro

IDE en el navegador con forma de computadora antigua (monitor de fósforo verde, ámbar o
blanco, disquetera y perillas) para **pegar código MIPS32 y simularlo**: ensamblar,
ejecutar, avanzar paso a paso, poner puntos de ruptura y ver los registros, la pila y la
memoria.

No necesita Java, Python ni servidor: **abra `index.html` con doble clic** (Chrome, Edge o
Firefox). Solo la tipografía se descarga de Google Fonts; sin internet usa una monoespaciada.

## Uso

1. Genere el ensamblador con el compilador:
   ```bash
   python main.py programa.cps -o programa.asm
   ```
2. Péguelo en el editor (Ctrl+V), ábralo con Ctrl+O o arrastre el `.asm` a la pantalla o a la
   disquetera.
3. Ejecútelo:

| Tecla | Acción |
|---|---|
| **F3** | Ensamblar (los errores marcan su línea) |
| **F5** o Ctrl+Enter | Ejecutar o continuar |
| **F7** | Paso a paso: la barra marca la siguiente instrucción y los registros que cambian se ven en video inverso |
| **F8** / Esc | Pausa |
| **F9** | Reiniciar |
| Clic en un número de línea | Punto de ruptura ● |
| Ctrl+S | Guardar como `.asm` |
| F1 | Ayuda |

- **VEL** (abajo a la derecha) cambia la velocidad: al máximo, o de 1 a 1000 instrucciones
  por segundo, para ver el programa correr línea por línea.
- Las pestañas **CPU / FPU / MEMORIA** muestran los registros enteros con la pila, los de
  punto flotante (simple y double) y un volcado de memoria. **HEX/DEC** cambia la base.
- Si el programa lee datos (syscalls 5, 6, 7, 8, 12), la consola los pide.
- El menú **Ejemplos** trae programas escritos a mano (factorial, burbuja, entrada, flotantes,
  una melodía con las syscalls MIDI, dados aleatorios, un error) y programas de Compiscript
  compilados por el proyecto.
- **Ver** cambia el color del fósforo y quita los efectos del tubo.

## Qué simula

Se comporta como MARS 4.5 con sus opciones por defecto: sin delay slots, memoria
little-endian con accesos alineados, `.data` en `0x10010000`, `$gp = 0x10008000`,
`$sp = 0x7fffeffc`, el programa empieza en la primera instrucción de `.text` (se puede
cambiar a `main` en el menú Ejecutar), `add/addi/sub` detectan desbordamiento.

- Instrucciones enteras, de memoria, saltos y las pseudoinstrucciones habituales (`li`, `la`,
  `move`, `blt`, `bge`, `mul`, `div` de 3 operandos, `rem`, `not`, `neg`, `seq`…), con
  inmediatos en lugar de registros donde MARS los acepta.
- Coprocesador 1: `.s` y `.d`, conversiones, comparaciones y `bc1t/bc1f`.
- Directivas `.data .text .globl .align .space .ascii .asciiz .byte .half .word .float .double .eqv`.
- Syscalls 1–12, 17, 30–36, 40–42 (la 31 y la 33 suenan).

La referencia completa está en **Ayuda ▸ Instrucciones y syscalls**.

Diferencia con MARS: cada línea de código ocupa una dirección; las pseudoinstrucciones no se
expanden en varias instrucciones, así que las direcciones de `.text` pueden no coincidir con
las de MARS (los saltos, `jal`, `la` de etiquetas de código y las tablas `.word` siguen
funcionando).

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html`, `estilo.css`, `ide.js` | la interfaz |
| `mips.js` | ensamblador de dos pasadas y CPU (funciona en el navegador y en Node) |
| `ejemplos.js` | ejemplos escritos a mano |
| `ejemplos_compiscript.js` | ejemplos compilados; se regeneran con `python simulador_retro/generar_ejemplos.py` |
| `probar.js` | ejecuta un `.asm` desde la terminal: `node simulador_retro/probar.js programa.asm` |
| `verificar.py` | compara este simulador con el simulador interno del compilador en toda la batería |

## Verificación

```bash
python simulador_retro/verificar.py
```

Compila a MIPS cada programa válido de `pruebas/` y exige que este simulador (JavaScript) y el
interno (Python) den la misma salida y el mismo código de salida. Necesita Node.js. Hoy:
105/105.

Son dos implementaciones independientes, pero las escribió el mismo equipo: para la entrega,
valide también en MARS o SPIM (`python pruebas/runner.py --simulador mars`).
