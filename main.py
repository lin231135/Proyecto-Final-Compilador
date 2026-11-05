"""
CLI del compilador de Compiscript.

    python main.py                             abre el IDE
    python main.py archivo.cps                 TAC (o los errores si los hay)
    python main.py archivo.cps --symbols       TAC + tabla de simbolos extendida
    python main.py archivo.cps --tac-only      solo el TAC

    python main.py archivo.cps --asm           ensamblador MIPS en la salida estandar
    python main.py archivo.cps -o salida.asm   ensamblador MIPS en un archivo
    python main.py archivo.cps --target arm64 -o salida.s    AArch64 (Raspberry Pi 4)
    python main.py archivo.cps --regs          marcos y asignacion de registros
    python main.py archivo.cps --run           compila y ejecuta
    python main.py archivo.cps --run --simulador mars|spim|interno|nativo

Codigo de salida: 0 si compilo, 1 si hubo errores; con --run, el del programa.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from backend import TARGETS, BackendError, generar_ensamblador
from codegen.report import render_codegen_report, render_symbols
from driver import analizar_archivo
from simulador.ejecucion import MEDIOS, ErrorEjecucionExterna, ejecutar_codigo


def _argumentos(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="main.py", description="Compilador de Compiscript")
    parser.add_argument("archivo", nargs="?", help="programa .cps (sin archivo se abre el IDE)")
    parser.add_argument("--symbols", action="store_true", help="agrega la tabla de simbolos extendida")
    parser.add_argument("--tac-only", action="store_true", help="imprime solo el TAC")
    parser.add_argument("--asm", action="store_true", help="imprime el ensamblador")
    parser.add_argument("-o", "--salida", help="escribe el ensamblador en este archivo")
    parser.add_argument("--target", choices=TARGETS, default="mips", help="procesador destino (por defecto mips)")
    parser.add_argument("--regs", action="store_true", help="reporte de marcos y registros")
    parser.add_argument("--run", action="store_true", help="ejecuta el codigo generado")
    parser.add_argument("--simulador", choices=MEDIOS, default="auto", help="donde ejecutar con --run")
    return parser.parse_args(argv)


def _reportar_errores(resultado) -> bool:
    if resultado.errores:
        print(f"Errores de compilacion ({len(resultado.errores)}):")
        for error in resultado.errores:
            print(f"  {error}")
        return True
    if resultado.error_interno:
        print(f"Error interno del generador: {resultado.error_interno}")
        return True
    return False


def _imprimir_tac(resultado, args: argparse.Namespace) -> None:
    if not args.tac_only:
        print("== Codigo intermedio (TAC) ==")
    print(resultado.tac.render())
    if args.symbols:
        print("== Tabla de simbolos (entornos) ==")
        print(render_symbols(resultado.table))
        print()
        print(render_codegen_report(resultado.generador))


def _generar(resultado, args: argparse.Namespace) -> int:
    try:
        ensamblado = generar_ensamblador(resultado, args.target)
    except BackendError as e:
        print(f"Error de generacion de codigo: {e}")
        return 1
    for aviso in ensamblado.avisos:
        print(f"Aviso: {aviso}", file=sys.stderr)
    if args.salida:
        pathlib.Path(args.salida).write_text(ensamblado.codigo, encoding="utf-8", newline="\n")
        print(f"Ensamblador {args.target} escrito en {args.salida}")
    if args.asm:
        print(ensamblado.codigo, end="")
    if args.regs:
        print(ensamblado.reporte())
    if not args.run:
        return 0
    try:
        ejecucion = ejecutar_codigo(ensamblado.codigo, args.target, args.simulador)
    except ErrorEjecucionExterna as e:
        print(f"No se pudo ejecutar: {e}")
        return 1
    print(ejecucion.salida, end="")
    return ejecucion.codigo_salida


def main(argv: list[str]) -> int:
    # La consola de Windows no es UTF-8: un caracter raro no debe tumbar la salida.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = _argumentos(argv)
    if args.archivo is None:
        from ide.app import main as lanzar_ide

        lanzar_ide()
        return 0

    resultado = analizar_archivo(args.archivo)
    if _reportar_errores(resultado):
        return 1
    if args.asm or args.salida or args.regs or args.run:
        return _generar(resultado, args)
    _imprimir_tac(resultado, args)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
