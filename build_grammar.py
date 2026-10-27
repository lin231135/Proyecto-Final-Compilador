"""
Regenera el lexer/parser/visitor de ANTLR a partir de grammar/Compiscript.g4.

Requisitos: Java en el PATH, y `pip install antlr4-tools` (ver requirements.txt).

Uso:
    python build_grammar.py
"""

import importlib.metadata
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent
GRAMMAR_DIR = ROOT / "grammar"
GRAMMAR_FILE = "Compiscript.g4"
OUT_DIR = ROOT / "generated"

ARCHIVOS_ESPERADOS = [
    "CompiscriptLexer.py",
    "CompiscriptParser.py",
    "CompiscriptVisitor.py",
    "CompiscriptListener.py",
]


def runtime_version() -> str:
    try:
        return importlib.metadata.version("antlr4-python3-runtime")
    except importlib.metadata.PackageNotFoundError:
        sys.exit(
            "No esta instalado antlr4-python3-runtime. Ejecute:\n"
            "    pip install -r requirements.txt"
        )


def main() -> None:
    if shutil.which("antlr4") is None:
        sys.exit(
            "No se encontro el comando 'antlr4'. Instale las dependencias con:\n"
            "    pip install -r requirements.txt\n"
            "y verifique que Java este disponible (`java -version`)."
        )

    version = runtime_version()
    OUT_DIR.mkdir(exist_ok=True)

    # Se fuerza al generador antlr4 (antlr4-tools) a usar la MISMA
    # version del runtime instalado (antlr4-python3-runtime), en vez de
    # descargar "la mas reciente". El desfase generador/runtime es la causa
    # #1 de errores raros en tiempo de ejecucion.
    env = dict(os.environ)
    env["ANTLR4_TOOLS_ANTLR_VERSION"] = version

    # Se corre con cwd=grammar/ y -o ../generated para que la salida
    # quede directamente en generated/, no en generated/grammar/.
    cmd = [
        "antlr4",
        "-v", version,
        "-Dlanguage=Python3",
        "-visitor",
        "-o", "../generated",
        GRAMMAR_FILE,
    ]
    resultado = subprocess.run(cmd, cwd=GRAMMAR_DIR, env=env)
    if resultado.returncode != 0:
        sys.exit(
            f"antlr4 fallo generando con la version {version} (la misma de "
            "antlr4-python3-runtime instalada). Revise que esa version este "
            "disponible en Maven o que grammar/Compiscript.g4 no tenga errores."
        )

    init_file = OUT_DIR / "__init__.py"
    if not init_file.exists():
        init_file.write_text("", encoding="utf-8")

    faltantes = [f for f in ARCHIVOS_ESPERADOS if not (OUT_DIR / f).exists()]
    if faltantes:
        sys.exit(f"Faltan archivos generados en {OUT_DIR}: {faltantes}")

    print(f"Lexer/Parser/Visitor (antlr4=={version}) generados en: {OUT_DIR}")


if __name__ == "__main__":
    main()
