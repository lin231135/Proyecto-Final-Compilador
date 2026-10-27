"""
Reporte de errores semanticos, compartido por todos los modulos del analizador.

Todos los visitors (tabla de simbolos, tipos, ambito/funciones/control de
flujo, clases) reportan aqui en vez de lanzar excepciones o hacer print():
asi el IDE puede mostrar la lista completa de errores de una sola pasada,
"""

from dataclasses import dataclass, field

from antlr4.Token import Token
from antlr4.tree.Tree import TerminalNode


CATEGORIAS = (
    "tipo",
    "ambito",
    "funcion",
    "control_flujo",
    "clase",
    "lista",
    "general",
)


@dataclass
class SemanticError:
    line: int
    column: int
    category: str
    message: str

    def __str__(self) -> str:
        return f"[{self.category}] linea {self.line}:{self.column} - {self.message}"


@dataclass
class ErrorReporter:
    errors: list[SemanticError] = field(default_factory=list)

    def error(self, ctx, category: str, message: str) -> None:
        """
        `ctx` puede ser un ParserRuleContext (usa `.start`), un TerminalNode
        de ANTLR (p. ej. un Identifier suelto; usa `.symbol`) o un Token
        directo. Los TerminalNode se normalizan a su Token antes de leer la
        linea y la columna.
        """
        assert category in CATEGORIAS, f"categoria desconocida: {category}"
        if isinstance(ctx, Token):
            token = ctx
        elif isinstance(ctx, TerminalNode):
            token = ctx.symbol
        else:
            token = ctx.start
        self.errors.append(SemanticError(token.line, token.column, category, message))

    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def all(self) -> list[SemanticError]:
        return list(self.errors)
