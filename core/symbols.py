"""
Tabla de Simbolos 

Entornos anidados (global, funcion, clase, bloque). Este es el modulo que
consumen el analisis semantico y la generacion de codigo.

Referencia: Libro del Dragon, manejo de ambitos y tabla de simbolos
(seccion de analisis semantico / entornos anidados).

API publica:
  - Symbol(name, type, kind, *, initialized=True, line=0, column=0)
  - Scope.define / Scope.resolve / Scope.resolve_local
  - SymbolTable.enter_scope / exit_scope / current / snapshot / environments
  - ScopeHelpers.require_declared / define_or_error
"""

from __future__ import annotations

from dataclasses import dataclass

from core.errors import ErrorReporter
from core.types import Type

ScopeKind = str  # "global" | "function" | "class" | "block"

# kinds validos de Symbol.kind (los unicos validos).
SYMBOL_KINDS = ("var", "const", "param", "function", "class")
SCOPE_KINDS = ("global", "function", "class", "block")


@dataclass
class Symbol:
    name: str
    type: Type
    kind: str  # "var" | "const" | "param" | "function" | "class"
    initialized: bool = True
    line: int = 0
    column: int = 0
    # --- Informacion para generacion de codigo (la llena codegen/) ---------
    # storage: "global" (area estatica) | "local" | "param" | "function" | "class"
    storage: str = ""
    offset: int | None = None  # desplazamiento dentro de su AR / area estatica
    size: int = 0  # bytes
    label: str | None = None  # etiqueta TAC (funciones: `f`, `f.g`, `Clase.m`)
    tac_name: str = ""  # nombre del operando en el TAC (`x`, `x_2`, `@x`)
    frame: object | None = None  # ActivationRecord que contiene la ranura


class Scope:
    def __init__(self, kind: ScopeKind, parent: "Scope | None" = None, name: str = ""):
        self.kind = kind
        self.parent = parent
        self.name = name
        self.symbols: dict[str, Symbol] = {}

    def define(self, symbol: Symbol) -> bool:
        """
        Inserta `symbol` en ESTE scope (no busca en los padres).

        Retorna True si se insertó correctamente, False si ya existia un
        simbolo con ese nombre en este mismo scope (redeclaracion). Quien
        llama a este metodo es responsable de reportar el error via
        ErrorReporter si retorna False - Scope no conoce el ErrorReporter
        a proposito, para mantenerlo simple de probar.
        """
        if symbol.name in self.symbols:
            return False
        self.symbols[symbol.name] = symbol
        return True

    def resolve(self, name: str) -> Symbol | None:
        """
        Busca `name` en este scope y, si no esta, sube por la cadena de
        `parent` hasta encontrarlo o llegar al scope global sin exito.

        Esta cadena de padres es la que hace que los closures funcionen:
        una funcion anidada resuelve nombres subiendo por el scope donde
        fue DEFINIDA, no por el scope desde donde fue LLAMADA.
        """
        found = self.resolve_local(name)
        if found is not None:
            return found
        if self.parent is not None:
            return self.parent.resolve(name)
        return None

    def resolve_local(self, name: str) -> Symbol | None:
        """Como resolve(), pero sin subir a los padres. Util para chequear redeclaracion."""
        return self.symbols.get(name)

    def __repr__(self) -> str:
        names = ", ".join(self.symbols)
        etiqueta = f"{self.kind} {self.name}".strip()
        return f"Scope(kind={etiqueta!r}, symbols=[{names}])"


class SymbolTable:
    def __init__(self):
        self._global = Scope(kind="global", parent=None)
        self._stack: list[Scope] = [self._global]
        # Entornos creados a lo largo del analisis (no se descartan al salir).
        # El enunciado pide el estado de la tabla por cada entorno, no solo
        # los que siguen abiertos al final del recorrido.
        self._environments: list[Scope] = [self._global]

    @property
    def global_scope(self) -> Scope:
        return self._global

    def current(self) -> Scope:
        return self._stack[-1]

    def enter_scope(self, kind: ScopeKind, name: str = "") -> Scope:
        """Crea un scope hijo del scope actual, lo apila y lo retorna."""
        child = Scope(kind=kind, parent=self.current(), name=name)
        self._stack.append(child)
        self._environments.append(child)
        return child

    def exit_scope(self) -> None:
        """Desapila el scope actual, volviendo al padre."""
        if len(self._stack) <= 1:
            raise RuntimeError("No se puede salir del scope global")
        self._stack.pop()

    def snapshot(self) -> list[tuple[str, list[Symbol]]]:
        """
        Scopes vivos en este momento, de global (indice 0) al actual.

        Util durante el recorrido (por ejemplo para inspeccionar el entorno
        corriente). Cada entrada es `(kind, simbolos_en_ese_scope)`.
        """
        return [(scope.kind, list(scope.symbols.values())) for scope in self._stack]

    def environments(self) -> list[tuple[str, list[Symbol]]]:
        """
        Todos los entornos creados durante el analisis, incluidos los ya
        cerrados: global, funcion, clase y bloque.

        Esta es la salida que pide el enunciado para el panel del IDE:
        estado de la tabla de simbolos por cada entorno.
        """
        return [
            (scope.kind, list(scope.symbols.values()))
            for scope in self._environments
        ]

    def format_environments(self) -> str:
        """Texto legible de `environments()`, para presentacion o el IDE."""
        lines: list[str] = []
        for i, scope in enumerate(self._environments):
            etiqueta = f"{scope.kind} {scope.name}".strip()
            if scope.symbols:
                lines.append(f"[{i}] {etiqueta}")
                for s in scope.symbols.values():
                    lines.append(f"    {s.kind} {s.name}: {s.type!r}{_info_codegen(s)}")
            else:
                lines.append(f"[{i}] {etiqueta}: (sin simbolos locales)")
        return "\n".join(lines)


def _info_codegen(s: "Symbol") -> str:
    """Sufijo con la informacion de codegen de un simbolo (si ya se genero)."""
    if s.label and s.kind == "function":
        return f"   [label={s.label}]"
    if s.storage == "field" and s.offset is not None:
        return f"   [campo +{s.offset}  {s.size}B]"
    if s.offset is not None:
        frame = getattr(s.frame, "name", "estatico")
        return f"   [{s.storage} {s.tac_name}  {frame}+{s.offset}  {s.size}B]"
    return ""


@dataclass
class ScopeHelpers:
    """
    Convenciones compartidas para no duplicar el patron
    "si resolve() da None -> error de variable no declarada" en cada uno
    de sus visit methods.
    """

    table: SymbolTable
    reporter: ErrorReporter

    def require_declared(self, name: str, ctx) -> Symbol | None:
        """
        Busca `name` desde el scope actual. Si no existe, reporta un error
        de categoria "ambito" y retorna None.
        """
        symbol = self.table.current().resolve(name)
        if symbol is None:
            self.reporter.error(
                ctx, "ambito", f"'{name}' no esta declarado en este ambito"
            )
            return None
        return symbol

    def define_or_error(self, symbol: Symbol, ctx) -> bool:
        """
        Intenta declarar `symbol` en el scope actual. Si ya existe en ESE
        scope, reporta un error de categoria "ambito" (redeclaracion) y
        retorna False.
        """
        if self.table.current().define(symbol):
            return True
        self.reporter.error(
            ctx,
            "ambito",
            f"'{symbol.name}' ya esta declarado en este ambito",
        )
        return False
