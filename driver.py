"""
Punto de entrada unico del compilador: analizar(fuente) -> Resultado.

Pipeline (enunciado, "Funcionamiento del programa"):
  1. ANTLR: lexer + parser construyen el arbol sintactico.
  2. SemanticVisitor (2 pasadas) valida y construye la tabla de simbolos.
  3. Si NO hay errores, TACGenerator recorre el mismo arbol, complementa la
     tabla de simbolos (offsets, AR, etiquetas) y produce el TAC.

Lo usan el IDE, la CLI (main.py) y pytest. Nadie mas debe instanciar el
lexer/parser/visitor de ANTLR por su cuenta.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener

from core.errors import SemanticError
from codegen.generator import CodegenError, TACGenerator
from codegen.tac import TACProgram
from core.symbols import SymbolTable
from generated.CompiscriptLexer import CompiscriptLexer
from generated.CompiscriptParser import CompiscriptParser
from semantico.prepass import ejecutar_prepass
from semantico.visitor import SemanticVisitor


class _ListenerDeErrores(ErrorListener):
    """
    ANTLR por defecto imprime los errores sintacticos en stderr y sigue el
    analisis. Este listener los acumula como SemanticError(categoria="general")
    en vez de imprimirlos, para que el IDE (y la CLI) los puedan mostrar.
    """

    def __init__(self, errores: list[SemanticError]):
        super().__init__()
        self._errores = errores

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        self._errores.append(SemanticError(line, column, "general", msg))


@dataclass
class Resultado:
    fuente: str
    tree: object | None
    parser: object | None
    errores_sintacticos: list[SemanticError] = field(default_factory=list)
    errores_semanticos: list[SemanticError] = field(default_factory=list)
    table: SymbolTable | None = None
    clases: dict = field(default_factory=dict)
    tac: TACProgram | None = None  # solo si no hubo errores
    generador: TACGenerator | None = None
    error_interno: str = ""

    @property
    def errores(self) -> list[SemanticError]:
        """Todos los errores (sintacticos + semanticos), ordenados por (linea, columna)."""
        return sorted(
            [*self.errores_sintacticos, *self.errores_semanticos],
            key=lambda e: (e.line, e.column),
        )

    @property
    def ok(self) -> bool:
        return not self.errores


def analizar(fuente: str, nombre: str = "<memoria>", generar: bool = True) -> Resultado:
    errores_sintacticos: list[SemanticError] = []

    lexer = CompiscriptLexer(InputStream(fuente))
    lexer.removeErrorListeners()
    lexer.addErrorListener(_ListenerDeErrores(errores_sintacticos))

    tokens = CommonTokenStream(lexer)

    parser = CompiscriptParser(tokens)
    parser.removeErrorListeners()
    parser.addErrorListener(_ListenerDeErrores(errores_sintacticos))

    tree = parser.program()

    visitor = SemanticVisitor()
    # Pasada 1: registra por adelantado funciones globales y
    # clases, para que la recursion mutua y la herencia hacia adelante no
    # dependan del orden de declaracion. Pasada 2: recorrido completo.
    ejecutar_prepass(visitor, tree)
    visitor.visit(tree)

    resultado = Resultado(
        fuente=fuente,
        tree=tree,
        parser=parser,
        errores_sintacticos=errores_sintacticos,
        errores_semanticos=visitor.reporter.all(),
        table=visitor.table,
        clases=visitor.clases,
    )

    if generar and resultado.ok:
        generador = TACGenerator(visitor.table, visitor.clases)
        try:
            resultado.tac = generador.generate(tree)
            resultado.generador = generador
        except CodegenError as e:
            resultado.error_interno = str(e)
    return resultado


def analizar_archivo(ruta: str | pathlib.Path) -> Resultado:
    ruta = pathlib.Path(ruta)
    fuente = ruta.read_text(encoding="utf-8")
    return analizar(fuente, nombre=str(ruta))
