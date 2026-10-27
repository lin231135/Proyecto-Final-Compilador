"""
Lenguaje intermedio (TAC): instrucciones, temporales y programa.

La especificacion completa (con ejemplos) esta en docs/Lenguaje_Intermedio_TAC.md.
Cada instruccion es un `Instr(op, ...)`; `str(instr)` da su forma textual.

    op            campos                      texto
    ------------  --------------------------  ------------------------------
    copy          dst, a                      dst = a
    bin           dst, a, operador, b         dst = a + b
    un            dst, operador, a            dst = - a      /  dst = ! a
    label         name                        L1:
    goto          name                        goto L1
    if_true       a, name                     if a goto L1
    if_false      a, name                     ifFalse a goto L1
    if_rel        a, operador, b, name        if a < b goto L1
    param         a                           param a
    call          dst|None, target, n         dst = call f, n
    callv         dst|None, target, n         dst = callv obj.metodo, n
    callc         dst|None, target, n         dst = callc f, n
    ret           a|None                      return a
    new           dst, clase, size            dst = new Clase, size
    newlist       dst, n                      dst = newlist n
    len           dst, a                      dst = len a
    load_field    dst, obj, campo             dst = obj.campo
    store_field   obj, campo, a               obj.campo = a
    load_index    dst, arr, idx               dst = arr[idx]
    store_index   arr, idx, a                 arr[idx] = a
    closure       dst, label                  dst = closure f
    try           name                        try L1
    endtry        -                           endtry
    catch         dst                         catch e
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_TEMP_RE = re.compile(r"^t\d+$")
_TEMP_USE_RE = re.compile(r"^t(\d+)(?:\.|$)")


def is_temp(place: str | None) -> bool:
    return place is not None and _TEMP_RE.match(place) is not None


# Instrucciones que definen (escriben) `dst`; el peephole de `emit_assign`
# solo puede redirigir el destino de estas.
DEFINING_OPS = frozenset(
    {"copy", "bin", "un", "call", "callv", "callc", "newlist", "len", "load_field", "load_index", "closure"}
)


@dataclass
class Instr:
    op: str
    dst: str | None = None
    a: str | None = None
    operator: str | None = None
    b: str | None = None
    name: str | None = None  # etiqueta, clase, campo o destino de llamada
    n: int | None = None
    c: str | None = None  # tercer operando (valor de store_index)

    def __str__(self) -> str:  # noqa: C901 - tabla de formatos
        o = self.op
        if o == "copy":
            return f"{self.dst} = {self.a}"
        if o == "bin":
            return f"{self.dst} = {self.a} {self.operator} {self.b}"
        if o == "un":
            return f"{self.dst} = {self.operator} {self.a}"
        if o == "label":
            return f"{self.name}:"
        if o == "goto":
            return f"goto {self.name}"
        if o == "if_true":
            return f"if {self.a} goto {self.name}"
        if o == "if_false":
            return f"ifFalse {self.a} goto {self.name}"
        if o == "if_rel":
            return f"if {self.a} {self.operator} {self.b} goto {self.name}"
        if o == "param":
            return f"param {self.a}"
        if o in ("call", "callv", "callc"):
            prefijo = f"{self.dst} = " if self.dst else ""
            return f"{prefijo}{o} {self.name}, {self.n}"
        if o == "ret":
            return "return" if self.a is None else f"return {self.a}"
        if o == "new":
            return f"{self.dst} = new {self.name}, {self.n}"
        if o == "newlist":
            return f"{self.dst} = newlist {self.n}"
        if o == "len":
            return f"{self.dst} = len {self.a}"
        if o == "load_field":
            return f"{self.dst} = {self.a}.{self.name}"
        if o == "store_field":
            return f"{self.a}.{self.name} = {self.b}"
        if o == "load_index":
            return f"{self.dst} = {self.a}[{self.b}]"
        if o == "store_index":
            return f"{self.a}[{self.b}] = {self.c}"
        if o == "closure":
            return f"{self.dst} = closure {self.name}"
        if o == "try":
            return f"try {self.name}"
        if o == "endtry":
            return "endtry"
        if o == "catch":
            return f"catch {self.dst}"
        raise ValueError(f"instruccion desconocida: {o}")


# Constructores con nombre: el generador no arma Instr(...) a mano.
def copy(dst, a):
    return Instr("copy", dst=dst, a=a)


def binop(dst, a, operator, b):
    return Instr("bin", dst=dst, a=a, operator=operator, b=b)


def unop(dst, operator, a):
    return Instr("un", dst=dst, a=a, operator=operator)


def label(name):
    return Instr("label", name=name)


def goto(name):
    return Instr("goto", name=name)


def if_true(a, name):
    return Instr("if_true", a=a, name=name)


def if_false(a, name):
    return Instr("if_false", a=a, name=name)


def if_rel(a, operator, b, name):
    return Instr("if_rel", a=a, operator=operator, b=b, name=name)


def param(a):
    return Instr("param", a=a)


def call(dst, target, n, kind="call"):
    return Instr(kind, dst=dst, name=target, n=n)


def ret(a=None):
    return Instr("ret", a=a)


def new(dst, clase, size):
    return Instr("new", dst=dst, name=clase, n=size)


def newlist(dst, n):
    return Instr("newlist", dst=dst, n=n)


def length(dst, a):
    return Instr("len", dst=dst, a=a)


def load_field(dst, obj, campo):
    return Instr("load_field", dst=dst, a=obj, name=campo)


def store_field(obj, campo, valor):
    return Instr("store_field", a=obj, name=campo, b=valor)


def load_index(dst, arr, idx):
    return Instr("load_index", dst=dst, a=arr, b=idx)


def store_index(arr, idx, valor):
    return Instr("store_index", a=arr, b=idx, c=valor)


def closure(dst, label_):
    return Instr("closure", dst=dst, name=label_)


# Inversion de relacionales para `ifFalse` fusionado: !(a < b) == (a >= b)
INVERSO = {"<": ">=", "<=": ">", ">": "<=", ">=": "<", "==": "!=", "!=": "=="}


# ---------------------------------------------------------------------------
# Temporales
# ---------------------------------------------------------------------------


class TempManager:
    """
    Asigna y recicla temporales `t1`, `t2`, ...

    Algoritmo (ver docs/Lenguaje_Intermedio_TAC.md, "Temporales"):
      - `new_temp()` devuelve el temporal LIBRE de menor numero; si no hay
        ninguno libre acuna uno nuevo (`tN+1`).
      - el generador llama a `free(place)` en cuanto el valor se CONSUME
        (justo despues de emitir la instruccion que lo usa), no al final
        de la sentencia. Asi, `a*b + c*d` usa 2 temporales en vez de 3, y
        `t1 = t1 + t2` reutiliza el operando como destino.
      - `free` ignora lo que no es un temporal (variables, literales) y es
        idempotente, de modo que el generador puede liberar cualquier
        operando sin comprobar su clase.
    """

    def __init__(self) -> None:
        self.count = 0  # cantidad de temporales distintos acunados (= maximo simultaneo)
        self.live: set[int] = set()
        self._free: set[int] = set()

    def new_temp(self) -> str:
        if self._free:
            index = min(self._free)
            self._free.discard(index)
        else:
            self.count += 1
            index = self.count
        self.live.add(index)
        return f"t{index}"

    def free(self, place: str | None) -> None:
        if not is_temp(place):
            return
        index = int(place[1:])
        if index in self.live:
            self.live.discard(index)
            self._free.add(index)

    def release_all(self) -> int:
        """Libera todo lo vivo; devuelve cuantos temporales estaban vivos
        (deberia ser 0 al final de cada sentencia: lo verifican los tests)."""
        leaked = len(self.live)
        self._free |= self.live
        self.live.clear()
        return leaked


# ---------------------------------------------------------------------------
# Programa
# ---------------------------------------------------------------------------


@dataclass
class TACFunction:
    name: str
    params: list[str] = field(default_factory=list)
    instructions: list[Instr] = field(default_factory=list)
    temp_count: int = 0

    def emit(self, instr: Instr) -> Instr:
        self.instructions.append(instr)
        return instr

    def lines(self) -> list[str]:
        return [str(i) for i in self.instructions]

    def used_temp_count(self) -> int:
        """Mayor `tN` que aparece en el codigo emitido. Puede ser menor que
        los temporales que se acunaron: `x = a + b` se fusiona (peephole) y su
        temporal desaparece del TAC, asi que no ocupa ranura en el AR."""
        mayor = 0
        for instr in self.instructions:
            for campo in (instr.dst, instr.a, instr.b, instr.c, instr.name):
                if campo:
                    for m in _TEMP_USE_RE.finditer(campo):
                        mayor = max(mayor, int(m.group(1)))
        return mayor

    def render(self) -> str:
        cabecera = f"func {self.name}({', '.join(self.params)}):"
        cuerpo = []
        for instr in self.instructions:
            sangria = "" if instr.op == "label" else "    "
            cuerpo.append(f"{sangria}{instr}")
        return "\n".join([cabecera, *cuerpo, "endfunc"])


@dataclass
class TACProgram:
    functions: list[TACFunction] = field(default_factory=list)

    def render(self) -> str:
        return "\n\n".join(f.render() for f in self.functions) + "\n"

    def function(self, name: str) -> TACFunction:
        for f in self.functions:
            if f.name == name:
                return f
        raise KeyError(name)

    def all_lines(self) -> list[str]:
        return [line for f in self.functions for line in f.lines()]
