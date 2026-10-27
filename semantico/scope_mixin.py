"""
Estado compartido de la tabla de simbolos.

Los demas mixins heredan estos atributos a traves de SemanticVisitor.
Aqui no se definen visitXxx: `visitBlock` (crear scope y detectar codigo
muerto) vive en function_mixin.py y las declaraciones se registran con
`define_or_error`.

Si un mixin posterior define `__init__`, DEBE llamar
`super().__init__(*args, **kwargs)` para no romper el MRO.
"""

from __future__ import annotations

from core.errors import ErrorReporter
from core.symbols import Scope, ScopeHelpers, ScopeKind, Symbol, SymbolTable
from core.types import ClassType, Type


class ScopeMixin:
    """Infraestructura de ambitos. Disponible en el visitor combinado como `self`."""

    table: SymbolTable
    reporter: ErrorReporter
    helpers: ScopeHelpers
    function_stack: list[tuple[str, Type]]
    loop_depth: int
    current_class: ClassType | None

    def __init__(self, *args, reporter: ErrorReporter | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.reporter = reporter or ErrorReporter()
        self.table = SymbolTable()
        self.helpers = ScopeHelpers(table=self.table, reporter=self.reporter)
        # (nombre_funcion, tipo_de_retorno_declarado)
        self.function_stack = []
        self.loop_depth = 0
        # clase que se esta visitando (para `this` y miembros heredados)
        self.current_class = None
        # Etiqueta del proximo visitBlock (if/else/while/...).
        self._etiqueta_bloque = ""

    def enter_scope(self, kind: ScopeKind, name: str = "") -> Scope:
        return self.table.enter_scope(kind, name=name)

    def exit_scope(self) -> None:
        self.table.exit_scope()

    def require_declared(self, name: str, ctx) -> Symbol | None:
        return self.helpers.require_declared(name, ctx)

    def define_or_error(self, symbol: Symbol, ctx) -> bool:
        return self.helpers.define_or_error(symbol, ctx)
