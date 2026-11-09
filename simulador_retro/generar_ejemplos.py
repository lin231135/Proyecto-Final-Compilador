"""
Genera simulador_retro/ejemplos_compiscript.js: programas de Compiscript
compilados a MIPS con el compilador del proyecto, para el menu EJEMPLOS.

    python simulador_retro/generar_ejemplos.py

Vuelva a correrlo si cambia el generador de codigo.
"""

from __future__ import annotations

import json
import pathlib
import sys

CARPETA = pathlib.Path(__file__).resolve().parent
RAIZ = CARPETA.parent
sys.path.insert(0, str(RAIZ))

from backend import generar_ensamblador  # noqa: E402
from driver import analizar, analizar_archivo  # noqa: E402

FACTORIAL = """\
function fact(n: integer): integer {
  if (n <= 1) { return 1; }
  return n * fact(n - 1);
}
print(fact(5));
"""

PROGRAMAS = [
    ("Compiscript: factorial", "factorial_cps.asm", "El ejemplo del README: fact(5) compilado con getReg y secuencias de llamada.", None, FACTORIAL),
    ("Compiscript: programa completo", "programa_completo.asm", "Clases, herencia, closures, recursión, listas y control de flujo (pruebas/demo).",
     "pruebas/demo/programa_completo.cps", None),
    ("Compiscript: despacho virtual", "despacho_virtual.asm", "Herencia y métodos sobrescritos con tabla virtual (.word con etiquetas).",
     "pruebas/asm_llamadas/validos/despacho_virtual.cps", None),
    ("Compiscript: recursión mutua", "recursion_mutua.asm", "par/impar mutuamente recursivos y Fibonacci.",
     "pruebas/asm_llamadas/validos/recursion_mutua_y_fibonacci.cps", None),
    ("Compiscript: try/catch", "catch.asm", "Un error de ejecución en otra función atrapado por catch.",
     "pruebas/asm_errores/validos/catch_en_una_funcion_llamadora.cps", None),
    ("Compiscript: flotantes", "flotantes_cps.asm", "Operaciones con float (double en MIPS).",
     "pruebas/asm_datos/validos/flotantes.cps", None),
]


def main() -> int:
    ejemplos = []
    for nombre, archivo, descripcion, ruta, fuente in PROGRAMAS:
        if ruta is not None:
            camino = RAIZ / ruta
            if not camino.is_file():
                print(f"(se omite {ruta}: no existe)")
                continue
            fuente = camino.read_text(encoding="utf-8")
            resultado = analizar_archivo(camino)
        else:
            resultado = analizar(fuente)
        if not resultado.ok:
            print(f"(se omite {nombre}: tiene errores)")
            continue
        codigo = generar_ensamblador(resultado, "mips").codigo
        cabecera = "\n".join("#   " + linea for linea in fuente.rstrip().splitlines())
        texto = (
            f"# {nombre} · {ruta or 'ejemplo del README'}\n"
            f"# Fuente Compiscript:\n#\n{cabecera}\n#\n"
            f"# Ensamblador generado por: python main.py programa.cps -o {archivo}\n\n{codigo}"
        )
        ejemplos.append({"nombre": nombre, "archivo": archivo, "descripcion": descripcion, "codigo": texto})
        print(f"{nombre}: {codigo.count(chr(10))} lineas")
    destino = CARPETA / "ejemplos_compiscript.js"
    destino.write_text(
        "/* Generado por generar_ejemplos.py: no editar a mano. */\n"
        f"window.EJEMPLOS_COMPISCRIPT = {json.dumps(ejemplos, ensure_ascii=False, indent=1)};\n",
        encoding="utf-8", newline="\n",
    )
    print(f"escrito {destino.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
