"""
Sistema de tipos de Compiscript.

Reglas: `float` es un tipo numerico (integer se ensancha a float), `+` esta
sobrecargado para string+string, `null` solo es asignable a ClassType/ArrayType
y existe un tipo `ERROR` para recuperar errores sin encadenar reportes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class PrimitiveKind(Enum):
    INTEGER = auto()
    FLOAT = auto()
    STRING = auto()
    BOOLEAN = auto()
    NULL = auto()
    VOID = auto()  # tipo de retorno de una funcion sin ": type"
    ERROR = auto()  # recuperacion de errores: nunca se reporta de nuevo


class Type:
    """Clase base. No instanciar directamente."""


@dataclass(frozen=True)
class PrimitiveType(Type):
    kind: PrimitiveKind

    def __repr__(self) -> str:
        return self.kind.name.lower()


@dataclass(frozen=True)
class ArrayType(Type):
    element_type: Type

    def __repr__(self) -> str:
        return f"{self.element_type!r}[]"


@dataclass(frozen=True)
class FunctionType(Type):
    param_types: tuple[Type, ...]
    return_type: Type

    def __repr__(self) -> str:
        params = ", ".join(repr(p) for p in self.param_types)
        return f"({params}) -> {self.return_type!r}"


@dataclass(eq=False)
class ClassType(Type):
    """
    eq=False porque el `__eq__`/`__hash__` que genera @dataclass compara
    (y hashea) recursivamente `fields`/`methods`. Con una clase autoreferente
    (`class Node { let next: Node; }`) eso es recursion infinita. En su lugar
    se compara e identifica por nombre.
    """

    name: str
    parent: "ClassType | None" = None
    fields: dict[str, Type] = field(default_factory=dict)
    methods: dict[str, FunctionType] = field(default_factory=dict)

    def lookup_member(self, name: str) -> Type | None:
        """Busca un campo o metodo en esta clase y, si no esta, en la cadena de herencia."""
        cls: ClassType | None = self
        while cls is not None:
            if name in cls.fields:
                return cls.fields[name]
            if name in cls.methods:
                return cls.methods[name]
            cls = cls.parent
        return None

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ClassType) and self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self) -> str:
        return self.name


# Instancias unicas para los tipos primitivos (comparar con `is` o `==`, son frozen).
INTEGER = PrimitiveType(PrimitiveKind.INTEGER)
FLOAT = PrimitiveType(PrimitiveKind.FLOAT)
STRING = PrimitiveType(PrimitiveKind.STRING)
BOOLEAN = PrimitiveType(PrimitiveKind.BOOLEAN)
NULL = PrimitiveType(PrimitiveKind.NULL)
VOID = PrimitiveType(PrimitiveKind.VOID)
ERROR = PrimitiveType(PrimitiveKind.ERROR)


def is_numeric(t: Type) -> bool:
    return t in (INTEGER, FLOAT)


def max_tipo(a: Type, b: Type) -> Type:
    """
    Tipo resultante de combinar dos tipos numericos: integer op integer ->
    integer; si cualquiera es float, el resultado es float.
    """
    if a == FLOAT or b == FLOAT:
        return FLOAT
    return INTEGER


def is_assignable(target: Type, value: Type) -> bool:
    """True si un valor de tipo `value` se puede asignar a una variable de tipo `target`."""
    if target == ERROR or value == ERROR:
        # el tipo ERROR nunca genera un error nuevo, para no encadenar.
        return True
    if target == value:
        return True
    if value == NULL:
        # null solo es asignable a tipos de clase o arreglo; no hay
        # conversion valida de null a un tipo primitivo (integer/float/
        # string/boolean).
        return isinstance(target, (ClassType, ArrayType))
    if target == NULL:
        # `let d = null;` (sin anotacion) deja el simbolo con tipo
        # NULL, que acepta una reasignacion posterior de clase o arreglo
        # (no de otro primitivo).
        return isinstance(value, (ClassType, ArrayType))
    if target == FLOAT and value == INTEGER:
        # integer -> float es una conversion ampliadora implicita.
        return True
    if isinstance(target, ArrayType) and isinstance(value, ArrayType):
        return is_assignable(target.element_type, value.element_type)
    if isinstance(target, ClassType) and isinstance(value, ClassType):
        cls: ClassType | None = value
        while cls is not None:
            if cls is target or cls.name == target.name:
                return True
            cls = cls.parent
        return False
    return False
