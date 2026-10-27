"""
Simulador minimo de TAC: ejecuta el codigo intermedio que genera el
compilador y devuelve lo que imprime el programa. No es un backend: se usa
en la bateria de pruebas (`// @salida:`) para comprobar que la traduccion es
*semanticamente* correcta (fib(10) == 55, un closure ve el estado de su
entorno, el despacho virtual elige el metodo de la clase real, etc.) y no
solo que "se parezca" al TAC esperado.

Modela el entorno de ejecucion descrito en docs/Tabla de Simbolos.md:
  - un marco (frame) por llamada, con enlace de acceso al marco de la
    funcion lexicamente envolvente (`upN.x` sube N enlaces de acceso);
  - area estatica para las globales (`@x`);
  - objetos como dict, listas como list, closures como (etiqueta, marco).
"""

from __future__ import annotations

import re


_NUM = re.compile(r"^-?\d+(\.\d+)?$")
_UP = re.compile(r"^up(\d+)\.(.+)$")


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
        self.depth = {ar.name: ar.depth for ar in gen.activation_records}
        self.layouts = gen.layouts
        self.globals: dict[str, object] = {}
        self.salida: list[str] = []
        self.max_pasos = max_pasos
        self.pasos = 0
        self._params: list = []
        self._ultimo_error = ""

    # --- operandos ------------------------------------------------------

    def _frame_up(self, frame: Frame, saltos: int) -> Frame:
        for _ in range(saltos):
            frame = frame.link
        return frame

    def get(self, op: str, frame: Frame):
        if op == "true":
            return True
        if op == "false":
            return False
        if op == "null":
            return None
        if _NUM.match(op):
            return float(op) if "." in op else int(op)
        if op.startswith('"'):
            return op[1:-1].replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
        if op.startswith("@"):
            return self.globals[op[1:]]
        m = _UP.match(op)
        if m:
            return self._frame_up(frame, int(m.group(1))).vars[m.group(2)]
        return frame.vars[op]

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
        self.call("main", [], None, Frame("<raiz>", None))
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
                    self.put(i.dst, (-v) if i.operator == "-" else (not v), frame)
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
                    self.put(i.dst, {"__clase__": i.name, **{f: None for f in self.layouts[i.name].fields}}, frame)
                elif o == "newlist":
                    self.put(i.dst, [None] * i.n, frame)
                elif o == "len":
                    self.put(i.dst, len(self.get(i.a, frame)), frame)
                elif o == "load_field":
                    self.put(i.dst, self.get(i.a, frame)[i.name], frame)
                elif o == "store_field":
                    self.get(i.a, frame)[i.name] = self.get(i.b, frame)
                elif o == "load_index":
                    idx = self.get(i.b, frame)
                    arr = self.get(i.a, frame)
                    if not 0 <= idx < len(arr):
                        raise IndexError(f"indice {idx} fuera de rango")
                    self.put(i.dst, arr[idx], frame)
                elif o == "store_index":
                    self.get(i.a, frame)[self.get(i.b, frame)] = self.get(i.c, frame)
                elif o == "closure":
                    self.put(i.dst, ("closure", i.name, frame), frame)
                elif o == "try":
                    manejadores.append(i.name)
                elif o == "endtry":
                    manejadores.pop()
                elif o == "catch":
                    self.put(i.dst, self._ultimo_error, frame)
                # label: sin efecto
            except (IndexError, ZeroDivisionError) as e:
                if not manejadores:
                    raise
                self._ultimo_error = str(e)
                pc = etiquetas[manejadores.pop()]
        return None

    def _llamar(self, tipo: str, i, args: list, frame: Frame):
        if i.name == "print":
            self.salida.append(self._texto(args[0]))
            return None
        if tipo == "call":
            return self.call(i.name, args, None, frame)
        if tipo == "callc":
            _, etiqueta, entorno = self.get(i.name, frame)
            return self.call(etiqueta, args, self._enlace_closure(etiqueta, entorno), frame)
        # callv: `obj.metodo` -> se busca en la clase REAL del objeto
        receptor, metodo = i.name.rsplit(".", 1)
        obj = self.get(receptor, frame)
        etiqueta = self.layouts[obj["__clase__"]].method_table()[metodo]
        return self.call(etiqueta, args, None, frame)

    def _enlace_closure(self, etiqueta: str, entorno: Frame) -> Frame:
        d = self.depth[etiqueta]
        saltos = self.depth.get(entorno.name, 0) - (d - 1)
        return self._frame_up(entorno, max(saltos, 0))

    @staticmethod
    def _texto(v) -> str:
        if v is True:
            return "true"
        if v is False:
            return "false"
        if v is None:
            return "null"
        return str(v)

    @staticmethod
    def _bin(a, op, b):
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return a // b if isinstance(a, int) and isinstance(b, int) else a / b
        if op == "%":
            return a % b
        return {
            "==": lambda: a == b, "!=": lambda: a != b, "<": lambda: a < b,
            "<=": lambda: a <= b, ">": lambda: a > b, ">=": lambda: a >= b,
        }[op]()


def ejecutar(resultado) -> list[str]:
    return TACInterpreter(resultado).run()
