"""
Simulador de TAC: ejecuta el codigo intermedio que genera el compilador y
devuelve lo que imprime el programa. No es un backend: es la referencia con la
que la bateria comprueba que la traduccion es *semanticamente* correcta
(fib(10) == 55, un closure ve el estado de su entorno, el despacho virtual
elige el metodo de la clase real, etc.) y con la que se comparan las salidas
del codigo MIPS y AArch64.

Modela el entorno de ejecucion descrito en docs/Tabla de Simbolos.md y el
contrato de core/runtime.py:
  - un marco (frame) por llamada, con enlace de acceso al marco de la
    funcion lexicamente envolvente (`upN.x` sube N enlaces de acceso);
  - area estatica para las globales (`@x`);
  - objetos como dict, listas como list, closures como (etiqueta, marco);
  - enteros de 32 bits, division truncada y errores de ejecucion con mensaje.
"""

from __future__ import annotations

import math
import re
import sys

from codegen.tac import unescape
from core.runtime import (
    MSG_DIVISION,
    MSG_INDICE,
    MSG_NULL,
    PREFIJO_ERROR,
    dividir_enteros,
    envolver_entero,
    formato_float,
    residuo_enteros,
)
from core.types import BOOLEAN, FLOAT, INTEGER

_NUM = re.compile(r"^-?\d+(\.\d+)?$")
_UP = re.compile(r"^up(\d+)\.(.+)$")


class ErrorEjecucion(Exception):
    """Error de ejecucion del programa (lo atrapa `try/catch`)."""


def valor_por_defecto(tipo):
    """Valor de una variable o campo declarado sin inicializar: ceros, como
    la memoria que reserva el codigo nativo."""
    if tipo == INTEGER:
        return 0
    if tipo == FLOAT:
        return 0.0
    if tipo == BOOLEAN:
        return False
    return None


class Frame:
    def __init__(self, name: str, link: "Frame | None"):
        self.name = name
        self.link = link  # enlace de acceso
        self.vars: dict[str, object] = {}


class TACInterpreter:
    def __init__(self, resultado, max_pasos: int = 200_000):
        self.tac = resultado.tac
        gen = resultado.generador
        self.funcs = {f.name: f for f in self.tac.functions}
        self.ars = {ar.name: ar for ar in gen.activation_records}
        self.depth = {ar.name: ar.depth for ar in gen.activation_records}
        self.layouts = gen.layouts
        self.global_area = gen.global_area
        self.globals: dict[str, object] = {}
        self.salida: list[str] = []
        self.codigo_salida = 0
        self.max_pasos = max_pasos
        self.pasos = 0
        self._params: list = []
        self._ultimo_error = ""

    # --- operandos ------------------------------------------------------

    def _frame_up(self, frame: Frame, saltos: int) -> Frame:
        for _ in range(saltos):
            frame = frame.link
        return frame

    def _local(self, frame: Frame, nombre: str):
        if nombre in frame.vars:
            return frame.vars[nombre]
        ranura = self.ars[frame.name].slot(nombre)
        return valor_por_defecto(ranura.type if ranura is not None else None)

    def get(self, op: str, frame: Frame):
        if op == "true":
            return True
        if op == "false":
            return False
        if op == "null":
            return None
        if _NUM.match(op):
            return float(op) if "." in op else envolver_entero(int(op))
        if op.startswith('"'):
            return unescape(op)
        if op.startswith("@"):
            nombre = op[1:]
            if nombre not in self.globals:
                return valor_por_defecto(self.global_area.slot(nombre).type)
            return self.globals[nombre]
        m = _UP.match(op)
        if m:
            return self._local(self._frame_up(frame, int(m.group(1))), m.group(2))
        return self._local(frame, op)

    def put(self, op: str, valor, frame: Frame) -> None:
        if op.startswith("@"):
            self.globals[op[1:]] = valor
            return
        m = _UP.match(op)
        if m:
            self._frame_up(frame, int(m.group(1))).vars[m.group(2)] = valor
        else:
            frame.vars[op] = valor

    # --- ejecucion ------------------------------------------------------

    def run(self) -> list[str]:
        limite = sys.getrecursionlimit()
        sys.setrecursionlimit(max(limite, 20_000))
        try:
            self.call("main", [], None, Frame("<raiz>", None))
        except ErrorEjecucion as e:
            self.salida.append(PREFIJO_ERROR + str(e))
            self.codigo_salida = 1
        finally:
            sys.setrecursionlimit(limite)
        return self.salida

    def _enlace_para(self, etiqueta: str, llamador: Frame) -> Frame:
        """Marco que sera el enlace de acceso de `etiqueta`: el de su padre lexico."""
        d = self.depth[etiqueta]
        actual = llamador
        # el llamador esta a profundidad `self.depth[actual.name]`; hay que
        # llegar al marco de profundidad d-1
        saltos = self.depth.get(llamador.name, 0) - (d - 1)
        return self._frame_up(actual, max(saltos, 0))

    def call(self, etiqueta: str, args: list, enlace: Frame | None, llamador: Frame):
        func = self.funcs[etiqueta]
        if enlace is None:
            enlace = llamador if etiqueta == "main" else self._enlace_para(etiqueta, llamador)
        frame = Frame(etiqueta, enlace)
        for nombre, valor in zip(func.params, args):
            frame.vars[nombre] = valor
        instrs = func.instructions
        etiquetas = {i.name: k for k, i in enumerate(instrs) if i.op == "label"}
        manejadores: list[str] = []
        pc = 0
        while pc < len(instrs):
            self.pasos += 1
            if self.pasos > self.max_pasos:
                raise RuntimeError("TAC no termina (limite de pasos)")
            i = instrs[pc]
            pc += 1
            o = i.op
            try:
                if o == "copy":
                    self.put(i.dst, self.get(i.a, frame), frame)
                elif o == "bin":
                    self.put(i.dst, self._bin(self.get(i.a, frame), i.operator, self.get(i.b, frame)), frame)
                elif o == "un":
                    v = self.get(i.a, frame)
                    if i.operator == "-":
                        self.put(i.dst, -v if isinstance(v, float) else envolver_entero(-v), frame)
                    else:
                        self.put(i.dst, not v, frame)
                elif o == "itof":
                    self.put(i.dst, float(self.get(i.a, frame)), frame)
                elif o == "goto":
                    pc = etiquetas[i.name]
                elif o == "if_true":
                    if self.get(i.a, frame):
                        pc = etiquetas[i.name]
                elif o == "if_false":
                    if not self.get(i.a, frame):
                        pc = etiquetas[i.name]
                elif o == "if_rel":
                    if self._bin(self.get(i.a, frame), i.operator, self.get(i.b, frame)):
                        pc = etiquetas[i.name]
                elif o == "param":
                    self._params.append(self.get(i.a, frame))
                elif o in ("call", "callv", "callc"):
                    args, self._params = self._params, []
                    args = args[-i.n:] if i.n else []
                    resultado = self._llamar(o, i, args, frame)
                    if i.dst:
                        self.put(i.dst, resultado, frame)
                elif o == "ret":
                    return self.get(i.a, frame) if i.a is not None else None
                elif o == "new":
                    campos = {f.name: valor_por_defecto(f.type) for f in self.layouts[i.name].fields.values()}
                    self.put(i.dst, {"__clase__": i.name, **campos}, frame)
                elif o == "newlist":
                    self.put(i.dst, [None] * i.n, frame)
                elif o == "len":
                    self.put(i.dst, len(self._no_nulo(self.get(i.a, frame))), frame)
                elif o == "load_field":
                    self.put(i.dst, self._no_nulo(self.get(i.a, frame))[i.name], frame)
                elif o == "store_field":
                    self._no_nulo(self.get(i.a, frame))[i.name] = self.get(i.b, frame)
                elif o == "load_index":
                    arr, idx = self._lista_e_indice(i.a, i.b, frame)
                    self.put(i.dst, arr[idx], frame)
                elif o == "store_index":
                    arr, idx = self._lista_e_indice(i.a, i.b, frame)
                    arr[idx] = self.get(i.c, frame)
                elif o == "closure":
                    self.put(i.dst, ("closure", i.name, frame), frame)
                elif o == "try":
                    manejadores.append(i.name)
                elif o == "endtry":
                    manejadores.pop()
                elif o == "catch":
                    self.put(i.dst, self._ultimo_error, frame)
                # label: sin efecto
            except ErrorEjecucion as e:
                if not manejadores:
                    raise
                self._ultimo_error = str(e)
                pc = etiquetas[manejadores.pop()]
        return None

    @staticmethod
    def _no_nulo(valor):
        if valor is None:
            raise ErrorEjecucion(MSG_NULL)
        return valor

    def _lista_e_indice(self, lista: str, indice: str, frame: Frame):
        arr = self._no_nulo(self.get(lista, frame))
        idx = self.get(indice, frame)
        if not 0 <= idx < len(arr):
            raise ErrorEjecucion(MSG_INDICE)
        return arr, idx

    def _llamar(self, tipo: str, i, args: list, frame: Frame):
        if i.name == "print":
            self.salida.append(self._texto(args[0]))
            return None
        if tipo == "call":
            return self.call(i.name, args, None, frame)
        if tipo == "callc":
            _, etiqueta, entorno = self._no_nulo(self.get(i.name, frame))
            return self.call(etiqueta, args, self._enlace_closure(etiqueta, entorno), frame)
        # callv: `obj.metodo` -> se busca en la clase REAL del objeto
        receptor, metodo = i.name.rsplit(".", 1)
        obj = self._no_nulo(self.get(receptor, frame))
        etiqueta = self.layouts[obj["__clase__"]].method_table()[metodo]
        return self.call(etiqueta, args, None, frame)

    def _enlace_closure(self, etiqueta: str, entorno: Frame) -> Frame:
        d = self.depth[etiqueta]
        saltos = self.depth.get(entorno.name, 0) - (d - 1)
        return self._frame_up(entorno, max(saltos, 0))

    @classmethod
    def _texto(cls, v) -> str:
        if v is True:
            return "true"
        if v is False:
            return "false"
        if v is None:
            return "null"
        if isinstance(v, float):
            return formato_float(v)
        if isinstance(v, list):
            return "[" + ", ".join(cls._texto(x) for x in v) + "]"
        if isinstance(v, dict):
            return f"<{v['__clase__']}>"
        if isinstance(v, tuple):
            return "<funcion>"
        return str(v)

    @classmethod
    def _bin(cls, a, op, b):
        if op == "+":
            if isinstance(a, str) or isinstance(b, str):
                return cls._texto(a) + cls._texto(b)
            return cls._numero(a + b)
        if op == "-":
            return cls._numero(a - b)
        if op == "*":
            return cls._numero(a * b)
        if op in ("/", "%"):
            return cls._division(a, op, b)
        if op == "==":
            return cls._iguales(a, b)
        if op == "!=":
            return not cls._iguales(a, b)
        return {"<": lambda: a < b, "<=": lambda: a <= b, ">": lambda: a > b, ">=": lambda: a >= b}[op]()

    @staticmethod
    def _numero(v):
        return v if isinstance(v, float) else envolver_entero(v)

    @staticmethod
    def _division(a, op, b):
        if b == 0:
            raise ErrorEjecucion(MSG_DIVISION)
        if isinstance(a, float) or isinstance(b, float):
            return a / b if op == "/" else a - b * math.trunc(a / b)
        return envolver_entero(dividir_enteros(a, b) if op == "/" else residuo_enteros(a, b))

    @staticmethod
    def _iguales(a, b) -> bool:
        """Objetos y listas se comparan por identidad, como las direcciones
        en el codigo nativo; el resto, por valor."""
        if isinstance(a, (list, dict)) or isinstance(b, (list, dict)):
            return a is b
        return a == b


def ejecutar(resultado, max_pasos: int = 200_000) -> list[str]:
    return TACInterpreter(resultado, max_pasos).run()
