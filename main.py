"""
CLI del compilador de Compiscript.

    python main.py                       abre el IDE
    python main.py archivo.cps           TAC (o los errores si los hay)
    python main.py archivo.cps --symbols TAC + tabla de simbolos extendida
    python main.py archivo.cps --tac-only  solo el TAC (para redirigir a un archivo)

Codigo de salida: 0 si compilo, 1 si hubo errores.
"""

from __future__ import annotations

import sys

from codegen.report import render_codegen_report, render_symbols
from driver import analizar_archivo


def main(argv: list[str]) -> int:
    banderas = {a for a in argv if a.startswith("--")}
    archivos = [a for a in argv if not a.startswith("--")]

    if not archivos:
        from ide.app import main as lanzar_ide

        lanzar_ide()
        return 0

    resultado = analizar_archivo(archivos[0])

    if resultado.errores:
        print(f"Errores de compilacion ({len(resultado.errores)}):")
        for error in resultado.errores:
            print(f"  {error}")
        return 1
    if resultado.error_interno:
        print(f"Error interno del generador: {resultado.error_interno}")
        return 1

    if "--tac-only" not in banderas:
        print("== Codigo intermedio (TAC) ==")
    print(resultado.tac.render())

    if "--symbols" in banderas:
        print("== Tabla de simbolos (entornos) ==")
        print(render_symbols(resultado.table))
        print()
        print(render_codegen_report(resultado.generador))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
