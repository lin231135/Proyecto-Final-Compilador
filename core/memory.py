"""
Modelo de memoria para la generacion de codigo: tamanos de tipo, registros
de activacion (AR), area estatica de globales y layout de objetos.

Es la parte "extendida" de la tabla de simbolos que pide el enunciado
(direcciones/desplazamientos, tamanos, etiquetas y registros de activacion).
`core/symbols.py` guarda en cada `Symbol` el resultado de este modelo
(`offset`, `size`, `storage`, `frame`, `tac_name`, `label`).

Convenciones (docentes, no corresponden a una ABI real):
  - integer = 4 bytes, float = 8, boolean = 1; string, arreglos, objetos,
    funciones y null son referencias de 8 bytes.
  - cada ranura se alinea a su propio tamano.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.types import BOOLEAN, FLOAT, INTEGER, Type

POINTER_SIZE = 8
WORD = 8  # tamano de un temporal (guarda cualquier valor)


def size_of(tipo: Type | None) -> int:
    if tipo == INTEGER:
        return 4
    if tipo == FLOAT:
        return 8
    if tipo == BOOLEAN:
        return 1
    return POINTER_SIZE


def type_name(tipo: Type | None) -> str:
    return "?" if tipo is None else repr(tipo)


def _align(offset: int, size: int) -> int:
    a = max(1, min(size, 8))
    return (offset + a - 1) // a * a


# ---------------------------------------------------------------------------
# Registros de activacion
# ---------------------------------------------------------------------------

#: Ranuras fijas al inicio de todo AR (enlaces, retorno).
HEADER = (
    ("control_link", "<enlace_control>"),
    ("access_link", "<enlace_acceso>"),
    ("return_address", "<direccion_retorno>"),
    ("return_value", "<valor_retorno>"),
)


@dataclass
class Slot:
    name: str
    kind: str  # control_link | access_link | return_address | return_value | param | local | temp | global
    type: Type | None
    size: int
    offset: int


class ActivationRecord:
    """
    Registro de activacion de una funcion, metodo, o del programa principal
    (`kind="main"`), o el area estatica de globales (`kind="global"`, sin
    cabecera de enlaces).

    Layout, de menor a mayor desplazamiento:
        control link   -> AR del que llamo (cadena dinamica)
        access link    -> AR del entorno lexico que contiene la definicion
                          (cadena estatica; es lo que usan los closures)
        return address, return value
        parametros (en orden; los metodos llevan `this` primero)
        variables locales (en orden de declaracion)
        temporales (al final, cuando ya se sabe cuantos hicieron falta)

    `parent` es el AR lexico (para el enlace de acceso), `depth` su
    profundidad de anidamiento: main=0, funcion de primer nivel=1, etc.
    """

    def __init__(self, name: str, kind: str = "function", parent: "ActivationRecord | None" = None):
        self.name = name
        self.kind = kind
        self.parent = parent
        self.depth = 0 if parent is None else parent.depth + 1
        self.slots: list[Slot] = []
        self._by_tac_name: dict[str, Slot] = {}
        self._offset = 0
        if kind != "global":
            for slot_kind, slot_name in HEADER:
                self._add(slot_name, slot_kind, None, POINTER_SIZE)

    def _add(self, name: str, kind: str, tipo: Type | None, size: int) -> Slot:
        self._offset = _align(self._offset, size)
        slot = Slot(name, kind, tipo, size, self._offset)
        self._offset += size
        self.slots.append(slot)
        self._by_tac_name[name] = slot
        return slot

    def unique_name(self, name: str) -> str:
        """`x`, y si ya existe (sombra en otro bloque): `x_2`, `x_3`, ..."""
        if name not in self._by_tac_name:
            return name
        n = 2
        while f"{name}_{n}" in self._by_tac_name:
            n += 1
        return f"{name}_{n}"

    def add_param(self, name: str, tipo: Type | None) -> Slot:
        return self._add(self.unique_name(name), "param", tipo, size_of(tipo))

    def add_local(self, name: str, tipo: Type | None) -> Slot:
        return self._add(self.unique_name(name), "local", tipo, size_of(tipo))

    def add_global(self, name: str, tipo: Type | None) -> Slot:
        return self._add(self.unique_name(name), "global", tipo, size_of(tipo))

    def finalize(self, temp_count: int) -> None:
        """Reserva las ranuras de los temporales t1..tN usados por la funcion."""
        for i in range(1, temp_count + 1):
            self._add(f"t{i}", "temp", None, WORD)

    @property
    def total_size(self) -> int:
        return _align(self._offset, 8)

    def __repr__(self) -> str:
        return f"AR({self.name}, depth={self.depth}, size={self.total_size})"


# ---------------------------------------------------------------------------
# Objetos
# ---------------------------------------------------------------------------


@dataclass
class FieldInfo:
    name: str
    type: Type | None
    offset: int
    size: int
    owner: str  # clase que declara el campo


@dataclass
class ClassLayout:
    """Layout de una instancia: campos heredados primero, luego los propios."""

    name: str
    parent: "ClassLayout | None" = None
    fields: dict[str, FieldInfo] = field(default_factory=dict)  # incluye heredados
    own_methods: list[str] = field(default_factory=list)
    has_initializers: bool = False  # tiene `Clase._init` (campos con valor inicial)
    instance_size: int = 0

    def ancestry(self) -> list["ClassLayout"]:
        """[raiz, ..., esta clase]"""
        cadena: list[ClassLayout] = []
        actual: ClassLayout | None = self
        while actual is not None:
            cadena.append(actual)
            actual = actual.parent
        return cadena[::-1]

    def resolve_method(self, nombre: str) -> str | None:
        """Nombre de la clase que define `nombre` (esta o un ancestro)."""
        actual: ClassLayout | None = self
        while actual is not None:
            if nombre in actual.own_methods:
                return actual.name
            actual = actual.parent
        return None

    def method_table(self) -> dict[str, str]:
        """nombre de metodo -> etiqueta `Clase.metodo` efectiva (con herencia)."""
        tabla: dict[str, str] = {}
        for c in self.ancestry():
            for m in c.own_methods:
                tabla[m] = f"{c.name}.{m}"
        return tabla


@dataclass
class ClosureAccess:
    """Uso de una variable declarada en una funcion lexicamente envolvente."""

    variable: str
    used_in: str
    defined_in: str
    hops: int
    offset: int
    line: int
