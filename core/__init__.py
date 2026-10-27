"""API compartida del analizador semantico: tabla de simbolos, tipos y errores."""

from core.errors import CATEGORIAS, ErrorReporter, SemanticError
from core.symbols import (
    SCOPE_KINDS,
    SYMBOL_KINDS,
    Scope,
    ScopeHelpers,
    ScopeKind,
    Symbol,
    SymbolTable,
)
from core.types import (
    BOOLEAN,
    INTEGER,
    NULL,
    STRING,
    VOID,
    ArrayType,
    ClassType,
    FunctionType,
    PrimitiveKind,
    PrimitiveType,
    Type,
    is_assignable,
    is_numeric,
)

__all__ = [
    "CATEGORIAS",
    "ErrorReporter",
    "SemanticError",
    "SCOPE_KINDS",
    "SYMBOL_KINDS",
    "Scope",
    "ScopeHelpers",
    "ScopeKind",
    "Symbol",
    "SymbolTable",
    "BOOLEAN",
    "INTEGER",
    "NULL",
    "STRING",
    "VOID",
    "ArrayType",
    "ClassType",
    "FunctionType",
    "PrimitiveKind",
    "PrimitiveType",
    "Type",
    "is_assignable",
    "is_numeric",
]
