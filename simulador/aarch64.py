"""
Simulador de AArch64 en Python: ejecuta el ensamblador que genera el compilador
para la Raspberry Pi 4 sin necesidad de tenerla a mano. Cubre el subconjunto que
emite el back-end y las llamadas al sistema `write`, `exit` y `mmap` de Linux.

No sustituye la prueba en la Raspberry: sirve para encontrar errores de
generacion de codigo en cualquier maquina. Igual que `simulador/mips.py`, con
`estricto=True` vigila la convencion: pila alineada a 16 bytes, registros
guardados preservados y basura en los registros que una llamada destruye.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass

BASE_TEXTO = 0x400000
BASE_DATOS = 0x10000000
BASE_HEAP = 0x20000000
TOPE_PILA = 0x7FFF0000
TAMANIO_PILA = 8 * 1024 * 1024
BASE_PILA = TOPE_PILA - TAMANIO_PILA
M64 = (1 << 64) - 1
M32 = 0xFFFFFFFF
BASURA = 0xDEADBEEFDEADBEEF
SP, ZR = 31, 32  # indices internos


class ErrorEnsamblado(Exception):
    pass


class ErrorSimulacion(Exception):
    pass


def _s32(v: int) -> int:
    return v - (1 << 32) if v & 0x80000000 else v


def _s64(v: int) -> int:
    return v - (1 << 64) if v & (1 << 63) else v


def _quitar_comentario(linea: str) -> str:
    en_cadena = False
    for n, c in enumerate(linea):
        if c == '"' and (n == 0 or linea[n - 1] != "\\"):
            en_cadena = not en_cadena
        elif not en_cadena and linea[n:n + 2] == "//":
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


_MISMO_ANCHO = frozenset({"add", "sub", "mul", "sdiv", "udiv", "msub", "neg", "csel", "cmp", "mov", "eor", "and"})
_ANCHO_ACCESO = {"ldrb": 1, "strb": 1}


def _es_registro_entero(texto: str) -> bool:
    return re.fullmatch(r"[xw]\d+|xzr|wzr|sp", texto) is not None


def _validar_codificacion(op: str, a: list[str]) -> None:  # noqa: C901 - tabla de reglas
    """Rechaza lo que `as` no acepta aunque el simulador supiera ejecutarlo:
    inmediatos fuera de rango, anchos mezclados y `sp`/`xzr` donde no se puede."""
    if op in _MISMO_ANCHO:
        regs = [x for x in a[:4] if _es_registro_entero(x)]
        if op == "add" and len(a) == 4 and ("uxtw" in a[3] or "sxtw" in a[3]):
            regs = regs[:2]  # forma extendida: el indice es de 32 bits
        anchos = {"w" if r.startswith("w") else "x" for r in regs}
        if len(anchos) > 1:
            raise ErrorEnsamblado("registros de distinto ancho")
    if op in ("add", "sub"):
        if a[2].startswith("#"):
            if not 0 <= int(a[2][1:], 0) <= 4095:
                raise ErrorEnsamblado(f"inmediato fuera de rango: {a[2]}")
            if a[1] in ("xzr", "wzr") or a[0] in ("xzr", "wzr"):
                raise ErrorEnsamblado("xzr no es valido en add/sub inmediato")
        elif len(a) == 3 and not a[2].startswith(":lo12:"):
            if a[2] == "sp":
                raise ErrorEnsamblado("sp no es valido como segundo operando")
        elif len(a) == 4 and "xtw" in a[3]:
            if a[1] == "xzr" or not a[2].startswith("w"):
                raise ErrorEnsamblado("forma extendida invalida")
    elif op == "cmp":
        if a[1].startswith("#"):
            if a[0] in ("xzr", "wzr") or not 0 <= int(a[1][1:], 0) <= 4095:
                raise ErrorEnsamblado("cmp inmediato invalido")
    elif op in ("movz", "movk"):
        if not 0 <= int(a[1][1:], 0) <= 0xFFFF:
            raise ErrorEnsamblado(f"inmediato de 16 bits fuera de rango: {a[1]}")
        if len(a) > 2 and a[0].startswith("w") and a[2] not in ("lsl #0", "lsl #16"):
            raise ErrorEnsamblado("desplazamiento invalido para un registro w")
    elif op == "mov" and a[1].startswith("#"):
        if not -65536 < int(a[1][1:], 0) <= 0xFFFF:
            raise ErrorEnsamblado(f"mov inmediato no codificable: {a[1]}")
    elif op in ("ldr", "str", "ldrb", "strb"):
        _validar_acceso(op, a)
    elif op in ("cbz", "cbnz", "blr", "br") and a[0] == "sp":
        raise ErrorEnsamblado("sp no es valido aqui")
    elif op == "scvtf" and not a[1].startswith("w"):
        raise ErrorEnsamblado("scvtf usa un registro w")
    elif op == "fcvtzs" and not a[0].startswith("w"):
        raise ErrorEnsamblado("fcvtzs usa un registro w")
    elif op == "sxtw" and not (a[0].startswith("x") and a[1].startswith("w")):
        raise ErrorEnsamblado("sxtw va de w a x")


def _validar_acceso(op: str, a: list[str]) -> None:
    dato, memoria = a[0], a[1]
    if dato == "sp":
        raise ErrorEnsamblado("sp no es valido como dato")
    m = re.fullmatch(r"\[\s*(\w+)\s*(?:,\s*#(-?\d+)\s*)?\]!?", memoria)
    if m is None:
        raise ErrorEnsamblado(f"direccionamiento invalido: {memoria}")
    if m.group(1) in ("xzr", "wzr") or m.group(1).startswith("w"):
        raise ErrorEnsamblado(f"base invalida: {memoria}")
    if op in _ANCHO_ACCESO:
        if not dato.startswith("w"):
            raise ErrorEnsamblado("ldrb/strb usan un registro w")
        ancho = 1
    else:
        ancho = 4 if dato.startswith("w") else 8
    offset = int(m.group(2) or 0)
    escalado = 0 <= offset <= 4095 * ancho and offset % ancho == 0
    if not (escalado or -256 <= offset <= 255):
        raise ErrorEnsamblado(f"offset no codificable: {memoria}")


def _partir_argumentos(texto: str) -> list[str]:
    args, actual, nivel = [], "", 0
    for c in texto:
        if c == "[":
            nivel += 1
        elif c == "]":
            nivel -= 1
        if c == "," and nivel == 0:
            args.append(actual.strip())
            actual = ""
        else:
            actual += c
    if actual.strip():
        args.append(actual.strip())
    return args


_RE_ETIQUETA = re.compile(r"^([A-Za-z_][\w.]*):\s*(.*)$")


class Programa:
    def __init__(self, fuente: str) -> None:
        self.instrucciones: list[tuple[int, str, str, list[str]]] = []
        self.datos = bytearray()
        self.etiquetas: dict[str, int] = {}
        self._parches: list[tuple[int, str]] = []
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
                elif directiva in (".global", ".section"):
                    pass
                elif en_datos:
                    self._directiva(directiva, resto.strip(), numero)
                else:
                    raise ErrorEnsamblado(f"linea {numero}: directiva {directiva} fuera de .data")
                continue
            if en_datos:
                raise ErrorEnsamblado(f"linea {numero}: instruccion dentro de .data: {linea}")
            op, _, resto = linea.partition(" ")
            self.instrucciones.append((numero, linea, op, _partir_argumentos(resto)))
        for offset, etiqueta in self._parches:
            if etiqueta not in self.etiquetas:
                raise ErrorEnsamblado(f"etiqueta desconocida en .quad: {etiqueta}")
            struct.pack_into("<Q", self.datos, offset, self.etiquetas[etiqueta])

    def _directiva(self, directiva: str, resto: str, numero: int) -> None:
        if directiva == ".balign":
            self._alinear(int(resto))
        elif directiva == ".space":
            self.datos += bytes(int(resto))
        elif directiva == ".asciz":
            self.datos += _decodificar_cadena(resto) + b"\0"
        elif directiva == ".byte":
            self.datos += bytes(int(x) & 0xFF for x in resto.split(","))
        elif directiva == ".double":
            if len(self.datos) % 8:
                raise ErrorEnsamblado(f"linea {numero}: .double desalineado")
            self.datos += struct.pack("<d", float(resto))
        elif directiva == ".quad":
            if len(self.datos) % 8:
                raise ErrorEnsamblado(f"linea {numero}: .quad desalineado")
            for x in resto.split(","):
                x = x.strip()
                if re.fullmatch(r"-?\d+", x):
                    self.datos += struct.pack("<Q", int(x) & M64)
                else:
                    self._parches.append((len(self.datos), x))
                    self.datos += bytes(8)
        else:
            raise ErrorEnsamblado(f"linea {numero}: directiva desconocida {directiva}")


@dataclass
class ResultadoSimulacion:
    salida: str
    codigo_salida: int
    instrucciones: int
    pila_maxima: int
    heap_usado: int


class SimuladorAArch64:
    def __init__(self, fuente: str, max_instrucciones: int = 50_000_000, estricto: bool = True) -> None:
        self.programa = Programa(fuente)
        self.max_instrucciones = max_instrucciones
        self.estricto = estricto
        self.X = [0] * 33  # 0-30, 31 = sp, 32 = cero
        self.D = [0.0] * 32
        self.N = self.Z = self.C = self.V = False
        self.datos = bytearray(self.programa.datos)
        self.heap = bytearray()
        self.pila = bytearray(TAMANIO_PILA)
        self.salida = bytearray()
        self.codigo_salida = 0
        self.terminado = False
        self.sp_minimo = TOPE_PILA
        self.marcos: list[tuple[int, list[int], str]] = []
        self.pc = 0
        self.codigo = [self._compilar(*i) for i in self.programa.instrucciones]

    # --- memoria --------------------------------------------------------

    def _ubicar(self, direccion: int, n: int) -> tuple[bytearray, int]:
        if BASE_DATOS <= direccion < BASE_DATOS + len(self.datos):
            return self.datos, direccion - BASE_DATOS
        if BASE_HEAP <= direccion < BASE_HEAP + len(self.heap):
            return self.heap, direccion - BASE_HEAP
        if BASE_PILA <= direccion < TOPE_PILA:
            return self.pila, direccion - BASE_PILA
        raise ErrorSimulacion(f"direccion invalida 0x{direccion:x}")

    def leer(self, direccion: int, n: int) -> int:
        m, o = self._ubicar(direccion, n)
        return int.from_bytes(m[o:o + n], "little")

    def escribir(self, direccion: int, n: int, valor: int) -> None:
        m, o = self._ubicar(direccion, n)
        m[o:o + n] = (valor & ((1 << (8 * n)) - 1)).to_bytes(n, "little")

    # --- operandos ------------------------------------------------------

    @staticmethod
    def _xreg(texto: str) -> int:
        if texto == "sp":
            return SP
        if texto in ("xzr", "wzr"):
            return ZR
        m = re.fullmatch(r"[xw](\d+)", texto)
        if not m or int(m.group(1)) > 30:
            raise ErrorEnsamblado(f"registro invalido: {texto}")
        return int(m.group(1))

    @staticmethod
    def _dreg(texto: str) -> int:
        m = re.fullmatch(r"d(\d+)", texto)
        if not m or int(m.group(1)) > 31:
            raise ErrorEnsamblado(f"registro de punto flotante invalido: {texto}")
        return int(m.group(1))

    @staticmethod
    def _imm(texto: str) -> int:
        return int(texto.lstrip("#"), 0)

    def _etiqueta(self, nombre: str) -> int:
        if nombre not in self.programa.etiquetas:
            raise ErrorEnsamblado(f"etiqueta desconocida: {nombre}")
        return self.programa.etiquetas[nombre]

    def _destino(self, nombre: str) -> int:
        direccion = self._etiqueta(nombre)
        if direccion >= BASE_DATOS:
            raise ErrorEnsamblado(f"la etiqueta '{nombre}' no es de codigo")
        return (direccion - BASE_TEXTO) // 4

    def _direccionamiento(self, args: list[str]):
        """Devuelve f() -> direccion efectiva, aplicando pre/post indice sobre sp."""
        X = self.X
        texto = args[0]
        pre = texto.endswith("!")
        m = re.fullmatch(r"\[\s*(\w+)\s*(?:,\s*#(-?\d+)\s*)?\]!?", texto)
        if not m:
            raise ErrorEnsamblado(f"direccionamiento invalido: {texto}")
        base = self._xreg(m.group(1))
        offset = int(m.group(2) or 0)
        posterior = self._imm(args[1]) if len(args) > 1 else None
        comprobar = base == SP and self.estricto

        def f():
            direccion = X[base]
            if pre:
                direccion = X[base] = (direccion + offset) & M64
            elif posterior is None:
                if comprobar and X[SP] % 16:
                    raise ErrorSimulacion("sp desalineado al acceder a memoria")
                return (direccion + offset) & M64
            if comprobar and X[SP] % 16:
                raise ErrorSimulacion("sp desalineado al acceder a memoria")
            if posterior is not None:
                X[base] = (direccion + posterior) & M64
            return direccion

        return f

    def _condicion(self, c: str):
        s = self
        tabla = {
            "eq": lambda: s.Z, "ne": lambda: not s.Z,
            "lt": lambda: s.N != s.V, "ge": lambda: s.N == s.V,
            "gt": lambda: not s.Z and s.N == s.V, "le": lambda: s.Z or s.N != s.V,
            "hs": lambda: s.C, "lo": lambda: not s.C,
            "hi": lambda: s.C and not s.Z, "ls": lambda: not s.C or s.Z,
            "mi": lambda: s.N, "pl": lambda: not s.N,
            "vs": lambda: s.V, "vc": lambda: not s.V,
        }
        if c not in tabla:
            raise ErrorEnsamblado(f"condicion desconocida: {c}")
        return tabla[c]

    def _flags_resta(self, a: int, b: int, bits: int) -> None:
        mascara = (1 << bits) - 1
        signo = 1 << (bits - 1)
        r = (a - b) & mascara
        self.N = bool(r & signo)
        self.Z = r == 0
        self.C = a >= b
        self.V = bool((a ^ b) & (a ^ r) & signo)

    # --- compilacion a closures -----------------------------------------

    def _compilar(self, linea: int, texto: str, op: str, a: list[str]):
        try:
            _validar_codificacion(op, a)
            f = self._traducir(op, a)
        except (ErrorEnsamblado, ValueError, IndexError) as e:
            raise ErrorEnsamblado(f"linea {linea} ({texto}): {e}") from e
        if f is None:
            raise ErrorEnsamblado(f"linea {linea}: instruccion no soportada: {texto}")
        return f

    def _traducir(self, op: str, a: list[str]):  # noqa: C901 - tabla de instrucciones
        X, D = self.X, self.D
        reg = self._xreg

        def es_w(texto: str) -> bool:
            return texto.startswith("w")

        if op in ("movz", "movk"):
            d = reg(a[0])
            valor = self._imm(a[1])
            desplazamiento = int(a[2].split("#")[1]) if len(a) > 2 else 0
            mascara = M32 if es_w(a[0]) else M64
            if op == "movz":
                resultado = (valor << desplazamiento) & mascara
                def f(): X[d] = resultado
            else:
                limpia = ~(0xFFFF << desplazamiento) & mascara
                parte = (valor << desplazamiento) & mascara
                def f(): X[d] = (X[d] & limpia) | parte
            return f
        if op == "mov":
            d = reg(a[0])
            mascara = M32 if es_w(a[0]) else M64
            if a[1].startswith("#"):
                valor = self._imm(a[1]) & mascara
                def f(): X[d] = valor
            else:
                s = reg(a[1])
                def f(): X[d] = X[s] & mascara
            return f
        if op in ("add", "sub"):
            return self._add_sub(op, a)
        if op == "adrp":
            d, direccion = reg(a[0]), self._etiqueta(a[1]) & ~0xFFF
            def f(): X[d] = direccion
            return f
        if op in ("mul", "sdiv", "udiv"):
            d, n, m = reg(a[0]), reg(a[1]), reg(a[2])
            ancho32 = es_w(a[0])
            if op == "mul":
                mascara = M32 if ancho32 else M64
                def f(): X[d] = (X[n] * X[m]) & mascara
            elif op == "udiv":
                mascara = M32 if ancho32 else M64
                def f():
                    x, y = X[n] & mascara, X[m] & mascara
                    X[d] = x // y if y else 0
            else:
                if not ancho32:
                    return None
                def f():
                    x, y = _s32(X[n] & M32), _s32(X[m] & M32)
                    if y == 0:
                        raise ErrorSimulacion("division entre cero sin verificar")
                    q = abs(x) // abs(y)
                    X[d] = (q if (x < 0) == (y < 0) else -q) & M32
            return f
        if op == "msub":
            d, n, m, s = reg(a[0]), reg(a[1]), reg(a[2]), reg(a[3])
            mascara = M32 if es_w(a[0]) else M64
            def f(): X[d] = (X[s] - X[n] * X[m]) & mascara
            return f
        if op == "neg":
            d, s = reg(a[0]), reg(a[1])
            mascara = M32 if es_w(a[0]) else M64
            def f(): X[d] = (-X[s]) & mascara
            return f
        if op == "eor":
            d, s, valor = reg(a[0]), reg(a[1]), self._imm(a[2])
            def f(): X[d] = (X[s] & M32) ^ valor
            return f
        if op == "and":
            d, s, valor = reg(a[0]), reg(a[1]), self._imm(a[2])
            def f(): X[d] = X[s] & valor
            return f
        if op == "sxtw":
            d, s = reg(a[0]), reg(a[1])
            def f(): X[d] = _s32(X[s] & M32) & M64
            return f
        if op == "cmp":
            bits = 32 if es_w(a[0]) else 64
            mascara = M32 if bits == 32 else M64
            n = reg(a[0])
            if a[1].startswith("#"):
                valor = self._imm(a[1])
                def f(): self._flags_resta(X[n] & mascara, valor, bits)
            else:
                m = reg(a[1])
                def f(): self._flags_resta(X[n] & mascara, X[m] & mascara, bits)
            return f
        if op == "cset":
            d, cond = reg(a[0]), self._condicion(a[1])
            def f(): X[d] = 1 if cond() else 0
            return f
        if op == "csel":
            d, n, m, cond = reg(a[0]), reg(a[1]), reg(a[2]), self._condicion(a[3])
            def f(): X[d] = X[n] if cond() else X[m]
            return f
        if op in ("ldr", "str", "ldrb", "strb"):
            return self._memoria(op, a)
        if op == "b":
            destino = self._destino(a[0])
            def f(): return destino
            return f
        if op.startswith("b."):
            cond, destino = self._condicion(op[2:]), self._destino(a[0])
            def f(): return destino if cond() else None
            return f
        if op in ("cbz", "cbnz"):
            s, destino = reg(a[0]), self._destino(a[1])
            mascara = M32 if es_w(a[0]) else M64
            if op == "cbz":
                def f(): return destino if X[s] & mascara == 0 else None
            else:
                def f(): return destino if X[s] & mascara != 0 else None
            return f
        if op == "bl":
            destino, nombre = self._destino(a[0]), a[0]
            def f():
                self._entrar(nombre)
                return destino
            return f
        if op == "blr":
            s = reg(a[0])
            def f():
                objetivo = X[s]
                self._entrar(f"blr 0x{objetivo:x}")
                return self._indice_codigo(objetivo)
            return f
        if op == "br":
            s = reg(a[0])
            def f(): return self._indice_codigo(X[s])
            return f
        if op == "ret":
            def f():
                self._salir()
                return self._indice_codigo(X[30])
            return f
        if op == "svc":
            return self._syscall
        return self._flotante(op, a)

    def _add_sub(self, op: str, a: list[str]):
        X = self.X
        reg = self._xreg
        d, n = reg(a[0]), reg(a[1])
        ancho32 = a[0].startswith("w")
        mascara = M32 if ancho32 else M64
        signo = 1 if op == "add" else -1
        if a[2].startswith(":lo12:"):
            valor = self._etiqueta(a[2][6:]) & 0xFFF
            def f(): X[d] = (X[n] + valor) & M64
            return f
        if a[2].startswith("#"):
            valor = signo * self._imm(a[2])
            def f(): X[d] = (X[n] + valor) & mascara
            return f
        m = reg(a[2])
        if len(a) == 3:
            def f(): X[d] = (X[n] + signo * X[m]) & mascara
            return f
        extension = a[3]
        if extension == "sxtw":
            def f(): X[d] = (X[n] + _s32(X[m] & M32)) & M64
            return f
        desplazamiento = int(extension.split("#")[1])
        if extension.startswith("uxtw"):
            def f(): X[d] = (X[n] + ((X[m] & M32) << desplazamiento)) & M64
            return f
        if extension.startswith("lsl"):
            def f(): X[d] = (X[n] + (X[m] << desplazamiento)) & mascara
            return f
        return None

    def _memoria(self, op: str, a: list[str]):
        X, D = self.X, self.D
        direccion = self._direccionamiento(a[1:])
        destino = a[0]
        if destino.startswith("d"):
            r = self._dreg(destino)
            if op == "ldr":
                def f():
                    D[r] = struct.unpack("<d", self.leer(direccion(), 8).to_bytes(8, "little"))[0]
            else:
                def f():
                    self.escribir(direccion(), 8, int.from_bytes(struct.pack("<d", D[r]), "little"))
            return f
        r = self._xreg(destino)
        if op in ("ldrb", "strb"):
            ancho = 1
        else:
            ancho = 4 if destino.startswith("w") else 8
        if op.startswith("ldr"):
            def f(): X[r] = self.leer(direccion(), ancho)
        else:
            def f(): self.escribir(direccion(), ancho, X[r])
        return f

    def _flotante(self, op: str, a: list[str]):
        X, D = self.X, self.D
        dreg, reg = self._dreg, self._xreg
        if op in ("fadd", "fsub", "fmul", "fdiv"):
            d, n, m = dreg(a[0]), dreg(a[1]), dreg(a[2])
            if op == "fadd":
                def f(): D[d] = D[n] + D[m]
            elif op == "fsub":
                def f(): D[d] = D[n] - D[m]
            elif op == "fmul":
                def f(): D[d] = D[n] * D[m]
            else:
                def f():
                    if D[m] == 0:
                        raise ErrorSimulacion("division entre cero sin verificar")
                    D[d] = D[n] / D[m]
            return f
        if op in ("fmov", "fneg", "frintz"):
            d, n = dreg(a[0]), dreg(a[1])
            if op == "fmov":
                def f(): D[d] = D[n]
            elif op == "fneg":
                def f(): D[d] = -D[n]
            else:
                def f(): D[d] = float(int(D[n]))
            return f
        if op == "scvtf":
            d, n = dreg(a[0]), reg(a[1])
            def f(): D[d] = float(_s32(X[n] & M32))
            return f
        if op == "fcvtzs":
            d, n = reg(a[0]), dreg(a[1])
            def f(): X[d] = int(D[n]) & M32
            return f
        if op == "fcmp":
            n = dreg(a[0])
            if a[1].startswith("#"):
                m = None
            else:
                m = dreg(a[1])

            def f():
                x, y = D[n], (0.0 if m is None else D[m])
                if x != x or y != y:
                    self.N, self.Z, self.C, self.V = False, False, True, True
                elif x == y:
                    self.N, self.Z, self.C, self.V = False, True, True, False
                elif x < y:
                    self.N, self.Z, self.C, self.V = True, False, False, False
                else:
                    self.N, self.Z, self.C, self.V = False, False, True, False
            return f
        return None

    # --- convencion de llamada ------------------------------------------

    def _indice_codigo(self, direccion: int) -> int:
        n = (direccion - BASE_TEXTO) // 4
        if direccion % 4 or not 0 <= n < len(self.codigo):
            raise ErrorSimulacion(f"salto a una direccion que no es codigo: 0x{direccion:x}")
        return n

    def _preservados(self) -> list[int]:
        X = self.X
        return [*X[19:30], X[SP]]

    def _entrar(self, nombre: str) -> None:
        retorno = BASE_TEXTO + 4 * (self.pc + 1)
        self.X[30] = retorno
        if self.estricto:
            self.marcos.append((retorno, self._preservados(), nombre))

    def _salir(self) -> None:
        if not self.estricto:
            return
        retorno = self.X[30]
        while self.marcos and self.marcos[-1][0] != retorno:
            self.marcos.pop()
        if not self.marcos:
            return
        _, esperados, nombre = self.marcos.pop()
        if self._preservados() != esperados:
            raise ErrorSimulacion(f"la llamada a {nombre} no preservo x19-x29/sp")
        X = self.X
        for n in (*range(1, 8), *range(9, 15), 16, 17):
            X[n] = BASURA

    # --- llamadas al sistema --------------------------------------------

    def _syscall(self):
        X = self.X
        servicio = X[8]
        if servicio == 64:  # write(fd, buffer, largo)
            if X[0] != 1:
                raise ErrorSimulacion("write a un descriptor distinto de stdout")
            for n in range(X[2]):
                self.salida.append(self.leer(X[1] + n, 1))
            X[0] = X[2]
        elif servicio == 93:  # exit(codigo)
            self.codigo_salida = _s32(X[0] & M32)
            self.terminado = True
        elif servicio == 222:  # mmap(0, largo, ...)
            largo = (X[1] + 4095) & ~4095
            X[0] = BASE_HEAP + len(self.heap)
            self.heap += bytes(largo)
        else:
            raise ErrorSimulacion(f"llamada al sistema no soportada: {servicio}")

    # --- ejecucion ------------------------------------------------------

    def ejecutar(self) -> ResultadoSimulacion:
        X = self.X
        X[SP] = TOPE_PILA
        etiquetas = self.programa.etiquetas
        pc = (etiquetas["_start"] - BASE_TEXTO) // 4
        codigo = self.codigo
        limite = self.max_instrucciones
        pasos = 0
        total = len(codigo)
        try:
            while not self.terminado:
                if pc >= total:
                    raise ErrorSimulacion("el programa se salio del codigo")
                self.pc = pc
                siguiente = codigo[pc]()
                X[ZR] = 0
                pc = pc + 1 if siguiente is None else siguiente
                pasos += 1
                if X[SP] < self.sp_minimo:
                    self.sp_minimo = X[SP]
                    if self.sp_minimo < BASE_PILA:
                        raise ErrorSimulacion("desbordamiento de pila")
                if pasos >= limite:
                    raise ErrorSimulacion(f"el programa no termino en {limite} instrucciones")
        except ErrorSimulacion as e:
            _, texto = self.programa.instrucciones[self.pc][:2]
            numero = self.programa.instrucciones[self.pc][0]
            raise ErrorSimulacion(f"{e} (linea {numero}: {texto})") from e
        return ResultadoSimulacion(
            self.salida.decode("utf-8", "replace"), self.codigo_salida, pasos, TOPE_PILA - self.sp_minimo, len(self.heap)
        )


def simular(fuente: str, max_instrucciones: int = 50_000_000, estricto: bool = True) -> ResultadoSimulacion:
    return SimuladorAArch64(fuente, max_instrucciones, estricto).ejecutar()
