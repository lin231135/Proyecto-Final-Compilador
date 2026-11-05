"""
Simulador de MIPS32 en Python: ensambla y ejecuta el codigo que genera el
compilador, sin Java ni herramientas externas, para que la bateria de pruebas
y el IDE funcionen en cualquier maquina.

Cubre el subconjunto que usa el back-end, con la misma semantica que MARS: las
llamadas al sistema 1, 4, 9, 10, 11 y 17, memoria little-endian, accesos
alineados obligatorios y sin delay slots.

Con `estricto=True` ademas vigila la convencion de llamada. En cada retorno
comprueba que el llamado preservo `$s0-$s7`, `$fp`, `$sp` y `$gp`, y llena de
basura los registros que la llamada puede destruir (`$t*`, `$a*`): un programa
que dependa de ellos falla en lugar de funcionar por casualidad.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field

REGISTROS = {
    n: i
    for i, n in enumerate(
        "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 "
        "s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra".split()
    )
}
ZERO, V0, V1, A0, SP, FP, GP, RA = 0, 2, 3, 4, 29, 30, 28, 31

BASE_TEXTO = 0x00400000
BASE_DATOS = 0x10010000
TOPE_PILA = 0x7FFFEFFC
TAMANIO_PILA = 8 * 1024 * 1024
BASE_PILA = TOPE_PILA + 4 - TAMANIO_PILA
MASCARA = 0xFFFFFFFF
BASURA = 0xDEADBEEF


class ErrorEnsamblado(Exception):
    pass


class ErrorSimulacion(Exception):
    pass


def _s32(v: int) -> int:
    return v - 0x100000000 if v & 0x80000000 else v


_OPERANDOS = {
    **dict.fromkeys(
        "addu subu and or xor slt sltu mul addiu xori andi ori sltiu slti sll srl beq bne blt ble bgt bge "
        "add.d sub.d mul.d div.d".split(),
        3,
    ),
    **dict.fromkeys(
        "li la move div lw lbu sw sb beqz bnez bgez neg.d mov.d l.d s.d mtc1 mfc1 cvt.d.w trunc.w.d "
        "c.lt.d c.le.d c.eq.d".split(),
        2,
    ),
    **dict.fromkeys("mflo mfhi j jal jalr jr bc1t bc1f".split(), 1),
    **dict.fromkeys("syscall nop".split(), 0),
}
_RE_ETIQUETA = re.compile(r"^([A-Za-z_][\w.]*):\s*(.*)$")
_RE_MEMORIA = re.compile(r"^(-?\d+)?\((\$\w+)\)$")


def _quitar_comentario(linea: str) -> str:
    """Quita `# ...` respetando los `#` dentro de un string."""
    en_cadena = False
    for n, c in enumerate(linea):
        if c == '"' and (n == 0 or linea[n - 1] != "\\"):
            en_cadena = not en_cadena
        elif c == "#" and not en_cadena:
            return linea[:n]
    return linea


def _decodificar_cadena(texto: str) -> bytes:
    cuerpo = texto.strip()[1:-1]
    salida = bytearray()
    n = 0
    while n < len(cuerpo):
        c = cuerpo[n]
        if c == "\\":
            n += 1
            salida += {"n": b"\n", "t": b"\t", '"': b'"', "\\": b"\\", "0": b"\0"}[cuerpo[n]]
        else:
            salida += c.encode("utf-8")
        n += 1
    return bytes(salida)


@dataclass
class Instruccion:
    linea: int
    texto: str
    op: str
    args: list[str] = field(default_factory=list)


class Programa:
    """Resultado de ensamblar: instrucciones, imagen de datos y etiquetas."""

    def __init__(self, fuente: str) -> None:
        self.instrucciones: list[Instruccion] = []
        self.datos = bytearray()
        self.etiquetas: dict[str, int] = {}
        self._parches: list[tuple[int, str]] = []  # (offset en datos, etiqueta)
        self._ensamblar(fuente)

    def _alinear(self, n: int) -> None:
        while len(self.datos) % n:
            self.datos.append(0)

    def _ensamblar(self, fuente: str) -> None:
        en_datos = False
        for numero, cruda in enumerate(fuente.splitlines(), 1):
            linea = _quitar_comentario(cruda).strip()
            while True:
                m = _RE_ETIQUETA.match(linea)
                if not m:
                    break
                nombre, linea = m.group(1), m.group(2).strip()
                if nombre in self.etiquetas:
                    raise ErrorEnsamblado(f"linea {numero}: etiqueta repetida '{nombre}'")
                if en_datos and linea.startswith(".word"):
                    self._alinear(4)
                if en_datos and linea.startswith(".double"):
                    self._alinear(8)
                self.etiquetas[nombre] = (
                    BASE_DATOS + len(self.datos) if en_datos else BASE_TEXTO + 4 * len(self.instrucciones)
                )
            if not linea:
                continue
            if linea.startswith("."):
                directiva, _, resto = linea.partition(" ")
                if directiva == ".data":
                    en_datos = True
                elif directiva == ".text":
                    en_datos = False
                elif directiva == ".globl":
                    pass
                elif en_datos:
                    self._directiva(directiva, resto.strip(), numero)
                else:
                    raise ErrorEnsamblado(f"linea {numero}: directiva {directiva} fuera de .data")
                continue
            if en_datos:
                raise ErrorEnsamblado(f"linea {numero}: instruccion dentro de .data: {linea}")
            op, _, resto = linea.partition(" ")
            args = [a.strip() for a in resto.split(",")] if resto.strip() else []
            self.instrucciones.append(Instruccion(numero, linea, op, args))
        for offset, etiqueta in self._parches:
            if etiqueta not in self.etiquetas:
                raise ErrorEnsamblado(f"etiqueta desconocida en .word: {etiqueta}")
            struct.pack_into("<I", self.datos, offset, self.etiquetas[etiqueta])

    def _directiva(self, directiva: str, resto: str, numero: int) -> None:
        if directiva == ".align":
            self._alinear(1 << int(resto))
        elif directiva == ".space":
            self.datos += bytes(int(resto))
        elif directiva == ".asciiz":
            self.datos += _decodificar_cadena(resto) + b"\0"
        elif directiva == ".byte":
            self.datos += bytes(int(x) & 0xFF for x in resto.split(","))
        elif directiva == ".double":
            self._alinear(8)
            self.datos += struct.pack("<d", float(resto))
        elif directiva == ".word":
            self._alinear(4)
            for x in resto.split(","):
                x = x.strip()
                if re.fullmatch(r"-?\d+", x):
                    self.datos += struct.pack("<I", int(x) & MASCARA)
                else:
                    self._parches.append((len(self.datos), x))
                    self.datos += bytes(4)
        else:
            raise ErrorEnsamblado(f"linea {numero}: directiva desconocida {directiva}")


@dataclass
class ResultadoSimulacion:
    salida: str
    codigo_salida: int
    instrucciones: int
    pila_maxima: int  # bytes de pila usados como maximo
    heap_usado: int


class SimuladorMIPS:
    def __init__(self, fuente: str, max_instrucciones: int = 50_000_000, estricto: bool = True) -> None:
        self.programa = Programa(fuente)
        self.max_instrucciones = max_instrucciones
        self.estricto = estricto
        self.R = [0] * 32
        self.F = bytearray(32 * 4)
        self.cond = False
        self.hi = self.lo = 0
        # datos estaticos y heap comparten una region que crece hacia arriba
        self.mem = bytearray(self.programa.datos)
        self.pila = bytearray(TAMANIO_PILA)
        self.fin_estatico = BASE_DATOS + len(self.mem)
        self.sbrk = (self.fin_estatico + 7) & ~7
        self.salida = bytearray()
        self.codigo_salida = 0
        self.terminado = False
        self.pasos = 0
        self.sp_minimo = TOPE_PILA
        self.marcos: list[tuple[int, list[int], str]] = []
        self.cerrar = [self._compilar(i) for i in self.programa.instrucciones]

    # --- memoria --------------------------------------------------------

    def _ubicar(self, direccion: int, n: int) -> tuple[bytearray, int]:
        if direccion % n:
            raise ErrorSimulacion(f"acceso desalineado a 0x{direccion:08x} ({n} bytes)")
        if BASE_DATOS <= direccion < BASE_DATOS + len(self.mem):
            return self.mem, direccion - BASE_DATOS
        if BASE_PILA <= direccion <= TOPE_PILA + 3:
            return self.pila, direccion - BASE_PILA
        raise ErrorSimulacion(f"direccion invalida 0x{direccion:08x}")

    def lw(self, direccion: int) -> int:
        m, o = self._ubicar(direccion, 4)
        return int.from_bytes(m[o:o + 4], "little")

    def sw(self, direccion: int, valor: int) -> None:
        m, o = self._ubicar(direccion, 4)
        m[o:o + 4] = (valor & MASCARA).to_bytes(4, "little")

    def lbu(self, direccion: int) -> int:
        m, o = self._ubicar(direccion, 1)
        return m[o]

    def sb(self, direccion: int, valor: int) -> None:
        m, o = self._ubicar(direccion, 1)
        m[o] = valor & 0xFF

    # --- punto flotante -------------------------------------------------

    def _doble(self, n: int) -> float:
        if n % 2:
            raise ErrorSimulacion(f"registro doble impar $f{n}")
        return struct.unpack_from("<d", self.F, 4 * n)[0]

    def _poner_doble(self, n: int, v: float) -> None:
        if n % 2:
            raise ErrorSimulacion(f"registro doble impar $f{n}")
        struct.pack_into("<d", self.F, 4 * n, v)

    def _palabra_f(self, n: int) -> int:
        return struct.unpack_from("<I", self.F, 4 * n)[0]

    def _poner_palabra_f(self, n: int, v: int) -> None:
        struct.pack_into("<I", self.F, 4 * n, v & MASCARA)

    # --- compilacion de instrucciones a closures ------------------------

    @staticmethod
    def _reg(texto: str) -> int:
        nombre = texto.lstrip("$")
        if nombre not in REGISTROS:
            raise ErrorEnsamblado(f"registro desconocido: {texto}")
        return REGISTROS[nombre]

    @staticmethod
    def _freg(texto: str) -> int:
        if not re.fullmatch(r"\$f\d+", texto):
            raise ErrorEnsamblado(f"registro de punto flotante desconocido: {texto}")
        return int(texto[2:])

    def _destino(self, etiqueta: str) -> int:
        if etiqueta not in self.programa.etiquetas:
            raise ErrorEnsamblado(f"etiqueta desconocida: {etiqueta}")
        direccion = self.programa.etiquetas[etiqueta]
        if not BASE_TEXTO <= direccion < BASE_DATOS:
            raise ErrorEnsamblado(f"la etiqueta '{etiqueta}' no es de codigo")
        return (direccion - BASE_TEXTO) // 4

    def _direccion(self, texto: str):
        """Funcion que calcula la direccion de `off($r)` o de una etiqueta."""
        m = _RE_MEMORIA.match(texto)
        if m:
            offset = int(m.group(1) or 0)
            r = self._reg(m.group(2))
            R = self.R
            return lambda: (R[r] + offset) & MASCARA
        if texto not in self.programa.etiquetas:
            raise ErrorEnsamblado(f"operando de memoria invalido: {texto}")
        direccion = self.programa.etiquetas[texto]
        return lambda: direccion

    @staticmethod
    def _validar_operandos(op: str, a: list[str]) -> None:
        """Rechaza lo que MARS y SPIM no ensamblan aunque se pudiera ejecutar."""
        esperados = _OPERANDOS.get(op)
        if esperados is not None and len(a) != esperados:
            raise ErrorEnsamblado(f"se esperaban {esperados} operandos, hay {len(a)}")
        if op in ("xori", "andi", "ori") and not 0 <= int(a[2]) <= 0xFFFF:
            raise ErrorEnsamblado(f"inmediato sin signo fuera de rango: {a[2]}")
        if op in ("sltiu", "slti") and not -32768 <= int(a[2]) <= 32767:
            raise ErrorEnsamblado(f"inmediato fuera de rango: {a[2]}")
        if op in ("sll", "srl") and not 0 <= int(a[2]) <= 31:
            raise ErrorEnsamblado(f"desplazamiento fuera de rango: {a[2]}")

    def _compilar(self, ins: Instruccion):  # noqa: C901 - tabla de instrucciones
        op, a = ins.op, ins.args
        R = self.R
        try:
            self._validar_operandos(op, a)
            f = self._traducir(op, a, R)
        except ErrorEnsamblado as e:
            raise ErrorEnsamblado(f"linea {ins.linea} ({ins.texto}): {e}") from e
        if f is None:
            raise ErrorEnsamblado(f"linea {ins.linea}: instruccion no soportada: {ins.texto}")
        return f

    def _traducir(self, op: str, a: list[str], R: list[int]):  # noqa: C901
        reg, freg = self._reg, self._freg

        if op in ("addu", "subu", "and", "or", "xor", "slt", "sltu", "mul"):
            d, s, t = reg(a[0]), reg(a[1]), reg(a[2])
            if d == ZERO:
                raise ErrorEnsamblado("escritura en $zero")
            if op == "addu":
                def f(): R[d] = (R[s] + R[t]) & MASCARA
            elif op == "subu":
                def f(): R[d] = (R[s] - R[t]) & MASCARA
            elif op == "and":
                def f(): R[d] = R[s] & R[t]
            elif op == "or":
                def f(): R[d] = R[s] | R[t]
            elif op == "xor":
                def f(): R[d] = R[s] ^ R[t]
            elif op == "slt":
                def f(): R[d] = 1 if _s32(R[s]) < _s32(R[t]) else 0
            elif op == "sltu":
                def f(): R[d] = 1 if R[s] < R[t] else 0
            else:
                def f(): R[d] = (_s32(R[s]) * _s32(R[t])) & MASCARA
            return f
        if op in ("addiu", "xori", "andi", "ori", "sltiu", "slti", "sll", "srl"):
            d, s, v = reg(a[0]), reg(a[1]), int(a[2])
            if op == "addiu":
                def f(): R[d] = (R[s] + v) & MASCARA
            elif op == "xori":
                def f(): R[d] = R[s] ^ (v & 0xFFFF)
            elif op == "andi":
                def f(): R[d] = R[s] & (v & 0xFFFF)
            elif op == "ori":
                def f(): R[d] = R[s] | (v & 0xFFFF)
            elif op == "sltiu":
                def f(): R[d] = 1 if R[s] < (v & MASCARA) else 0
            elif op == "slti":
                def f(): R[d] = 1 if _s32(R[s]) < v else 0
            elif op == "sll":
                def f(): R[d] = (R[s] << v) & MASCARA
            else:
                def f(): R[d] = R[s] >> v
            return f
        if op == "li":
            d, v = reg(a[0]), int(a[1]) & MASCARA
            def f(): R[d] = v
            return f
        if op == "la":
            d = reg(a[0])
            if a[1] not in self.programa.etiquetas:
                raise ErrorEnsamblado(f"etiqueta desconocida: {a[1]}")
            v = self.programa.etiquetas[a[1]]
            def f(): R[d] = v
            return f
        if op == "move":
            d, s = reg(a[0]), reg(a[1])
            def f(): R[d] = R[s]
            return f
        if op == "div":
            s, t = reg(a[0]), reg(a[1])
            def f():
                x, y = _s32(R[s]), _s32(R[t])
                if y == 0:
                    raise ErrorSimulacion("division entre cero sin verificar")
                q = abs(x) // abs(y)
                q = q if (x < 0) == (y < 0) else -q
                self.lo = q & MASCARA
                self.hi = (x - q * y) & MASCARA
            return f
        if op in ("mflo", "mfhi"):
            d = reg(a[0])
            if op == "mflo":
                def f(): R[d] = self.lo
            else:
                def f(): R[d] = self.hi
            return f
        if op in ("lw", "lbu", "sw", "sb"):
            r, direccion = reg(a[0]), self._direccion(a[1])
            if op == "lw":
                def f(): R[r] = self.lw(direccion())
            elif op == "lbu":
                def f(): R[r] = self.lbu(direccion())
            elif op == "sw":
                def f(): self.sw(direccion(), R[r])
            else:
                def f(): self.sb(direccion(), R[r])
            return f
        if op in ("beq", "bne", "blt", "ble", "bgt", "bge"):
            s, t, destino = reg(a[0]), reg(a[1]), self._destino(a[2])
            if op == "beq":
                def f(): return destino if R[s] == R[t] else None
            elif op == "bne":
                def f(): return destino if R[s] != R[t] else None
            elif op == "blt":
                def f(): return destino if _s32(R[s]) < _s32(R[t]) else None
            elif op == "ble":
                def f(): return destino if _s32(R[s]) <= _s32(R[t]) else None
            elif op == "bgt":
                def f(): return destino if _s32(R[s]) > _s32(R[t]) else None
            else:
                def f(): return destino if _s32(R[s]) >= _s32(R[t]) else None
            return f
        if op in ("beqz", "bnez", "bgez"):
            s, destino = reg(a[0]), self._destino(a[1])
            if op == "beqz":
                def f(): return destino if R[s] == 0 else None
            elif op == "bnez":
                def f(): return destino if R[s] != 0 else None
            else:
                def f(): return destino if _s32(R[s]) >= 0 else None
            return f
        if op == "j":
            destino = self._destino(a[0])
            def f(): return destino
            return f
        if op == "jal":
            destino = self._destino(a[0])
            nombre = a[0]
            def f():
                self._entrar(nombre)
                return destino
            return f
        if op == "jalr":
            s = reg(a[0])
            def f():
                self._entrar(f"jalr 0x{R[s]:08x}")
                return self._indice_codigo(R[s])
            return f
        if op == "jr":
            s = reg(a[0])
            if s == RA:
                def f():
                    self._salir()
                    return self._indice_codigo(R[RA])
            else:
                def f(): return self._indice_codigo(R[s])
            return f
        if op == "syscall":
            return self._syscall
        if op == "nop":
            def f(): return None
            return f
        return self._traducir_flotante(op, a, R, reg, freg)

    def _traducir_flotante(self, op: str, a: list[str], R: list[int], reg, freg):  # noqa: C901
        if op in ("add.d", "sub.d", "mul.d", "div.d"):
            d, s, t = freg(a[0]), freg(a[1]), freg(a[2])
            if op == "add.d":
                def f(): self._poner_doble(d, self._doble(s) + self._doble(t))
            elif op == "sub.d":
                def f(): self._poner_doble(d, self._doble(s) - self._doble(t))
            elif op == "mul.d":
                def f(): self._poner_doble(d, self._doble(s) * self._doble(t))
            else:
                def f():
                    divisor = self._doble(t)
                    if divisor == 0:
                        raise ErrorSimulacion("division entre cero sin verificar")
                    self._poner_doble(d, self._doble(s) / divisor)
            return f
        if op in ("neg.d", "mov.d"):
            d, s = freg(a[0]), freg(a[1])
            if op == "neg.d":
                def f(): self._poner_doble(d, -self._doble(s))
            else:
                def f(): self._poner_doble(d, self._doble(s))
            return f
        if op in ("l.d", "s.d"):
            r, direccion = freg(a[0]), self._direccion(a[1])
            if op == "l.d":
                def f():
                    m, o = self._ubicar(direccion(), 8)
                    self.F[4 * r:4 * r + 8] = m[o:o + 8]
            else:
                def f():
                    m, o = self._ubicar(direccion(), 8)
                    m[o:o + 8] = self.F[4 * r:4 * r + 8]
            return f
        if op == "mtc1":
            s, d = reg(a[0]), freg(a[1])
            def f(): self._poner_palabra_f(d, R[s])
            return f
        if op == "mfc1":
            d, s = reg(a[0]), freg(a[1])
            def f(): R[d] = self._palabra_f(s)
            return f
        if op == "cvt.d.w":
            d, s = freg(a[0]), freg(a[1])
            def f(): self._poner_doble(d, float(_s32(self._palabra_f(s))))
            return f
        if op == "trunc.w.d":
            d, s = freg(a[0]), freg(a[1])
            def f(): self._poner_palabra_f(d, int(self._doble(s)) & MASCARA)
            return f
        if op in ("c.lt.d", "c.le.d", "c.eq.d"):
            s, t = freg(a[0]), freg(a[1])
            if op == "c.lt.d":
                def f(): self.cond = self._doble(s) < self._doble(t)
            elif op == "c.le.d":
                def f(): self.cond = self._doble(s) <= self._doble(t)
            else:
                def f(): self.cond = self._doble(s) == self._doble(t)
            return f
        if op in ("bc1t", "bc1f"):
            destino = self._destino(a[0])
            if op == "bc1t":
                def f(): return destino if self.cond else None
            else:
                def f(): return destino if not self.cond else None
            return f
        return None

    # --- convencion de llamada ------------------------------------------

    def _indice_codigo(self, direccion: int) -> int:
        n = (direccion - BASE_TEXTO) // 4
        if direccion % 4 or not 0 <= n < len(self.cerrar):
            raise ErrorSimulacion(f"salto a una direccion que no es codigo: 0x{direccion:08x}")
        return n

    def _entrar(self, nombre: str) -> None:
        retorno = BASE_TEXTO + 4 * (self.pc + 1)
        self.R[RA] = retorno
        if self.estricto:
            self.marcos.append((retorno, self._preservados(), nombre))

    def _preservados(self) -> list[int]:
        R = self.R
        return [*R[16:24], R[GP], R[SP], R[FP]]

    def _salir(self) -> None:
        if not self.estricto:
            return
        retorno = self.R[RA]
        # Un `catch` abandona marcos sin retornar: se descartan hasta el que retorna.
        while self.marcos and self.marcos[-1][0] != retorno:
            self.marcos.pop()
        if not self.marcos:
            return
        _, esperados, nombre = self.marcos.pop()
        if self._preservados() != esperados:
            raise ErrorSimulacion(f"la llamada a {nombre} no preservo $s/$sp/$fp/$gp")
        R = self.R
        for n in (*range(8, 16), 24, 25, 4, 5, 6, 7):  # $t0-$t9, $a0-$a3
            R[n] = BASURA

    # --- llamadas al sistema --------------------------------------------

    def _cadena(self, direccion: int) -> bytes:
        salida = bytearray()
        while True:
            b = self.lbu(direccion)
            if b == 0:
                return bytes(salida)
            salida.append(b)
            direccion += 1

    def _syscall(self):
        R = self.R
        servicio = R[V0]
        if servicio == 1:
            self.salida += str(_s32(R[A0])).encode()
        elif servicio == 4:
            self.salida += self._cadena(R[A0])
        elif servicio == 9:
            n = R[A0]
            R[V0] = self.sbrk
            self.sbrk += n
            faltan = self.sbrk - BASE_DATOS - len(self.mem)
            if faltan > 0:
                self.mem += bytes(faltan)
        elif servicio == 10:
            self.terminado = True
        elif servicio == 11:
            self.salida.append(R[A0] & 0xFF)
        elif servicio == 17:
            self.codigo_salida = _s32(R[A0])
            self.terminado = True
        else:
            raise ErrorSimulacion(f"syscall no soportada: {servicio}")

    # --- ejecucion ------------------------------------------------------

    def ejecutar(self) -> ResultadoSimulacion:
        R = self.R
        R[SP] = TOPE_PILA
        R[GP] = 0x10008000
        R[RA] = 0
        codigo = self.cerrar
        self.pc = 0
        limite = self.max_instrucciones
        pasos = 0
        pc = 0
        total = len(codigo)
        try:
            while not self.terminado:
                if pc >= total:
                    raise ErrorSimulacion("el programa se salio del codigo (falta `exit`)")
                self.pc = pc
                siguiente = codigo[pc]()
                pc = pc + 1 if siguiente is None else siguiente
                pasos += 1
                if R[SP] < self.sp_minimo:
                    self.sp_minimo = R[SP]
                    if self.sp_minimo < BASE_PILA:
                        raise ErrorSimulacion("desbordamiento de pila")
                if pasos >= limite:
                    raise ErrorSimulacion(f"el programa no termino en {limite} instrucciones")
        except ErrorSimulacion as e:
            linea = self.programa.instrucciones[self.pc]
            raise ErrorSimulacion(f"{e} (linea {linea.linea}: {linea.texto})") from e
        self.pasos = pasos
        return ResultadoSimulacion(
            self.salida.decode("utf-8", "replace"),
            self.codigo_salida,
            pasos,
            TOPE_PILA - self.sp_minimo,
            self.sbrk - self.fin_estatico,
        )


def simular(fuente: str, max_instrucciones: int = 50_000_000, estricto: bool = True) -> ResultadoSimulacion:
    return SimuladorMIPS(fuente, max_instrucciones, estricto).ejecutar()
