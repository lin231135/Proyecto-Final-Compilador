"""
AArch64 (ARMv8-A): codigo nativo para la Raspberry Pi 4 con un sistema de 64
bits. Programa estatico y sin libc, que usa directamente las llamadas al
sistema de Linux:

    as programa.s -o programa.o && ld programa.o -o programa && ./programa

Registros (AAPCS64, salvo que el marco y los enlaces son los de Compiscript):
    x9-x14    valores de un bloque (getReg). Los destruye una llamada.
    x19-x27   variables de larga vida y valores que cruzan llamadas. Los
              preserva quien es llamado.
    x16 x17   scratch del generador; x8, scratch para direcciones lejanas.
    x0-x7     ocho primeros argumentos enteros/referencia; x0, retorno.
    d0-d7     ocho primeros argumentos float (por posicion); d0, retorno.
    x15       enlace de acceso hacia el llamado.
    x28       base del area estatica (globales).
    x29       base del registro de activacion; sp, tope de la pila.
    d16-d29   valores float (getReg). Los destruye una llamada.
    d30 d31   scratch de punto flotante.

Un `integer` y un `boolean` usan la mitad de 32 bits del registro (`wN`), asi
la aritmetica da la vuelta igual que en MIPS. La pila va alineada a 16 bytes.
"""

from __future__ import annotations

from backend.aarch64_runtime import RUNTIME_DATOS, RUNTIME_TEXTO
from backend.target import MarcoFuncion, Target, texto_double

_COND = {"<": "lt", "<=": "le", ">": "gt", ">=": "ge", "==": "eq", "!=": "ne"}
# Tras `fcmp`, `lt` y `le` tambien serian ciertas con NaN; `mi` y `ls` no.
_COND_F = {"<": "mi", "<=": "ls", ">": "gt", ">=": "ge", "==": "eq", "!=": "ne"}
_FBIN = {"+": "fadd", "-": "fsub", "*": "fmul", "/": "fdiv"}
_ANCHO_ACCESO = {"bool": 1, "int": 4}


def w(r: str) -> str:
    """Nombre de 32 bits de un registro entero."""
    return "wzr" if r == "xzr" else "w" + r[1:]


def _escapar(texto: str) -> str | None:
    salida = []
    for c in texto:
        if c == "\n":
            salida.append("\\n")
        elif c == "\t":
            salida.append("\\t")
        elif c == '"':
            salida.append('\\"')
        elif c == "\\":
            salida.append("\\\\")
        elif 32 <= ord(c) < 127:
            salida.append(c)
        else:
            return None
    return "".join(salida)


class AArch64(Target):
    nombre = "arm64"
    palabra = 8
    alineacion_pila = 16
    tamanio_manejador = 32

    temporales = ["x9", "x10", "x11", "x12", "x13", "x14"]
    guardados = ["x19", "x20", "x21", "x22", "x23", "x24", "x25", "x26", "x27"]
    flotantes = [f"d{n}" for n in range(16, 30)]
    scratch0, scratch1, fscratch0 = "x16", "x17", "d31"
    zero, fp, sp, global_base, enlace = "xzr", "x29", "sp", "x28", "x15"
    retorno, retorno_flotante = "x0", "d0"

    # --- salida ---------------------------------------------------------

    def encabezado(self) -> None:
        self.lineas += [
            "// Generado por el compilador de Compiscript (AArch64, Linux, sin libc)",
            "// as programa.s -o programa.o && ld programa.o -o programa && ./programa",
            "    .text",
            "    .global _start",
        ]

    def comentario_seccion(self, texto: str) -> None:
        self.lineas += ["", f"// ---- {texto}"]

    def comentario_tac(self, texto: str) -> None:
        self.lineas.append(f"    // {texto}")

    def etiqueta_global(self, nombre: str) -> None:
        self.label("_start")
        self.label(nombre)

    # --- movimiento de datos --------------------------------------------

    def li(self, r: str, valor: int) -> None:
        bits = valor & 0xFFFFFFFF
        self.emit(f"movz {w(r)}, #{bits & 0xFFFF}")
        if bits >> 16:
            self.emit(f"movk {w(r)}, #{bits >> 16}, lsl #16")

    def la(self, r: str, etiqueta: str) -> None:
        self.emit(f"adrp {r}, {etiqueta}")
        self.emit(f"add {r}, {r}, :lo12:{etiqueta}")

    def mov(self, d: str, s: str) -> None:
        if d != s:
            self.emit(f"mov {d}, {s}")

    def fmov(self, d: str, s: str) -> None:
        if d != s:
            self.emit(f"fmov {d}, {s}")

    def fconst(self, r: str, etiqueta: str) -> None:
        self.la("x8", etiqueta)
        self.emit(f"ldr {r}, [x8]")

    def _memoria(self, base: str, offset: int, ancho: int) -> str:
        """Operando de memoria; un offset que no cabe se calcula en x8."""
        if 0 <= offset < 4096 * ancho and offset % ancho == 0:
            return f"[{base}, #{offset}]" if offset else f"[{base}]"
        if -256 <= offset < 256:
            return f"[{base}, #{offset}]"
        self.li("x8", offset)
        self.emit(f"add x8, {base}, w8, sxtw")
        return "[x8]"

    def _acceso(self, op_byte: str, op: str, kind: str, r: str, base: str, offset: int) -> None:
        ancho = _ANCHO_ACCESO.get(kind, 8)
        memoria = self._memoria(base, offset, ancho)
        if kind == "bool":
            self.emit(f"{op_byte} {w(r)}, {memoria}")
        elif kind == "int":
            self.emit(f"{op} {w(r)}, {memoria}")
        else:
            self.emit(f"{op} {r}, {memoria}")

    def load(self, kind: str, r: str, base: str, offset: int) -> None:
        self._acceso("ldrb", "ldr", kind, r, base, offset)

    def store(self, kind: str, r: str, base: str, offset: int) -> None:
        self._acceso("strb", "str", kind, r, base, offset)

    def poner_en_cero(self, base: str, offset: int, size: int) -> None:
        self.store({1: "bool", 4: "int"}.get(size, "ref"), "xzr", base, offset)

    # --- aritmetica entera ----------------------------------------------

    def inmediato_valido(self, operador: str, valor: int) -> bool:
        return operador in ("+", "-") and -4095 <= valor <= 4095

    def bin_inmediato(self, operador: str, d: str, a: str, valor: int) -> None:
        if operador == "-":
            valor = -valor
        if a == self.zero:  # `wzr` no es valido como fuente de add inmediato
            self.li(d, valor)
        elif valor >= 0:
            self.emit(f"add {w(d)}, {w(a)}, #{valor}")
        else:
            self.emit(f"sub {w(d)}, {w(a)}, #{-valor}")

    def bin_entero(self, operador: str, d: str, a: str, b: str) -> None:
        if operador == "%":
            self.emit(f"sdiv w16, {w(a)}, {w(b)}")
            self.emit(f"msub {w(d)}, w16, {w(b)}, {w(a)}")
        else:
            op = {"+": "add", "-": "sub", "*": "mul", "/": "sdiv"}[operador]
            self.emit(f"{op} {w(d)}, {w(a)}, {w(b)}")

    def negar_entero(self, d: str, a: str) -> None:
        self.emit(f"neg {w(d)}, {w(a)}")

    def negar_booleano(self, d: str, a: str) -> None:
        self.emit(f"eor {w(d)}, {w(a)}, #1")

    def _cmp(self, a: str, b: str, ancho: str) -> None:
        if ancho == "ref":
            self.emit(f"cmp {a}, {b}")
        else:
            self.emit(f"cmp {w(a)}, {w(b)}")

    def comparar_a_valor(self, op: str, d: str, a: str, b: str, ancho: str) -> None:
        self._cmp(a, b, ancho)
        self.emit(f"cset {w(d)}, {_COND[op]}")

    # --- punto flotante -------------------------------------------------

    def bin_flotante(self, operador: str, d: str, a: str, b: str) -> None:
        if operador == "%":  # a - b * trunc(a / b)
            self.emit(f"fdiv d31, {a}, {b}")
            self.emit("frintz d31, d31")
            self.emit(f"fmul d31, {b}, d31")
            self.emit(f"fsub {d}, {a}, d31")
        else:
            self.emit(f"{_FBIN[operador]} {d}, {a}, {b}")

    def negar_flotante(self, d: str, a: str) -> None:
        self.emit(f"fneg {d}, {a}")

    def entero_a_flotante(self, d: str, a: str) -> None:
        self.emit(f"scvtf {d}, {w(a)}")

    def saltar_comparando_flotantes(self, op: str, a: str, b: str, etiqueta: str) -> None:
        self.emit(f"fcmp {a}, {b}")
        self.emit(f"b.{_COND_F[op]} {etiqueta}")

    def comparar_flotante_a_valor(self, op: str, d: str, a: str, b: str) -> None:
        self.emit(f"fcmp {a}, {b}")
        self.emit(f"cset {w(d)}, {_COND_F[op]}")

    def saltar_si_flotante_cero(self, r: str, etiqueta: str) -> None:
        self.emit(f"fcmp {r}, #0.0")
        self.emit(f"b.eq {etiqueta}")

    # --- saltos ---------------------------------------------------------

    def jump(self, etiqueta: str) -> None:
        self.emit(f"b {etiqueta}")

    def saltar_comparando(self, op: str, a: str, b: str, etiqueta: str, ancho: str) -> None:
        self._cmp(a, b, ancho)
        self.emit(f"b.{_COND[op]} {etiqueta}")

    def _registro_para(self, r: str, kind: str) -> str:
        return w(r) if kind in ("int", "bool") else r

    def saltar_si_cero(self, r: str, kind: str, etiqueta: str) -> None:
        self.emit(f"cbz {self._registro_para(r, kind)}, {etiqueta}")

    def saltar_si_no_cero(self, r: str, kind: str, etiqueta: str) -> None:
        self.emit(f"cbnz {self._registro_para(r, kind)}, {etiqueta}")

    # --- listas ---------------------------------------------------------

    def direccion_elemento(self, lista: str, indice: str, error: str) -> str:
        """Verifica 0 <= indice < longitud (comparacion sin signo) y devuelve
        el registro con la direccion del elemento menos `offset_elementos`."""
        self.emit(f"ldr w16, [{lista}]")
        self.emit(f"cmp {w(indice)}, w16")
        self.emit(f"b.hs {error}")
        self.emit(f"add x17, {lista}, {w(indice)}, uxtw #3")
        return "x17"

    # --- llamadas -------------------------------------------------------

    def registro_argumento(self, posicion: int, kind: str) -> str | None:
        if posicion >= 8:
            return None
        return f"d{posicion}" if kind == "float" else f"x{posicion}"

    def argumento_entrante(self, marco: MarcoFuncion, posicion: int) -> tuple[str, int]:
        if marco.en_heap:
            return "sp", marco.salientes + 8 * posicion
        return "x29", marco.tamanio + 8 * posicion

    def call(self, etiqueta: str) -> None:
        self.emit(f"bl {etiqueta}")

    def recorrer_enlaces(self, destino: str, saltos: int) -> None:
        """`destino` = marco alcanzado tras `saltos` enlaces de acceso."""
        self.emit(f"ldr {destino}, [x29, #8]")
        for _ in range(saltos - 1):
            self.emit(f"ldr {destino}, [{destino}, #8]")

    def llamar_closure(self, closure: str, error_null: str) -> None:
        """Un closure es el par (codigo, entorno)."""
        self.emit(f"cbz {closure}, {error_null}")
        self.emit(f"ldr x15, [{closure}, #8]")
        self.emit(f"ldr x16, [{closure}]")
        self.emit("blr x16")

    def llamar_virtual(self, selector: int, error_null: str) -> None:
        """El receptor es el primer argumento; su palabra 0 apunta al
        descriptor de la clase real (nombre + tabla de metodos)."""
        self.emit(f"cbz x0, {error_null}")
        self.emit("ldr x16, [x0]")
        self.emit(f"ldr x16, [x16, #{8 * (selector + 1)}]")
        self.emit("blr x16")

    def _ajustar_sp(self, delta: int) -> None:
        if delta == 0:
            return
        op = "add" if delta > 0 else "sub"
        if abs(delta) < 4096:
            self.emit(f"{op} sp, sp, #{abs(delta)}")
        else:
            self.li("x16", abs(delta))
            self.emit(f"{op} sp, sp, x16")

    def _sumar_a_registro(self, d: str, base: str, offset: int, scratch: str = "x16") -> None:
        if offset < 4096:
            self.emit(f"add {d}, {base}, #{offset}")
        else:
            self.li(scratch, offset)
            self.emit(f"add {d}, {base}, {scratch}")

    def prologo(self, m: MarcoFuncion) -> None:
        if m.en_heap:
            # El marco sobrevive a la funcion (closure): se pide al heap,
            # conservando los argumentos que ya vienen en registros.
            salvar = [*(f"x{n}" for n in range(8)), "x15", "x30", *(f"d{n}" for n in range(8))]
            self.emit(f"sub sp, sp, #{8 * len(salvar)}")
            for n, r in enumerate(salvar):
                self.emit(f"str {r}, [sp, #{8 * n}]")
            self.li("x0", m.tamanio)
            self.emit("bl __rt_alloc")
            self.emit("mov x16, x0")
            for n, r in enumerate(salvar):
                self.emit(f"ldr {r}, [sp, #{8 * n}]")
            self.emit(f"add sp, sp, #{8 * len(salvar)}")
            self.emit("str x29, [x16]         // enlace de control")
            self.emit("str x30, [x16, #16]    // direccion de retorno")
            self.emit("mov x29, x16")
            self._ajustar_sp(-m.salientes)
        else:
            self._ajustar_sp(-(m.tamanio + m.salientes))
            self.emit(f"str x29, {self._memoria('sp', m.salientes, 8)}     // enlace de control")
            self.emit(f"str x30, {self._memoria('sp', m.salientes + 16, 8)}     // direccion de retorno")
            self._sumar_a_registro("x29", "sp", m.salientes)
        if m.usa_enlace:
            self.emit("str x15, [x29, #8]     // enlace de acceso")
        for registro, offset in m.guardados:
            self.store("ref", registro, "x29", offset)

    def epilogo(self, m: MarcoFuncion) -> None:
        for registro, offset in m.guardados:
            self.load("ref", registro, "x29", offset)
        self.emit("ldr x30, [x29, #16]")
        if m.en_heap:
            self.emit("ldr x29, [x29]")
            self._ajustar_sp(m.salientes)
        else:
            self._sumar_a_registro("x17", "x29", m.tamanio)
            self.emit("mov sp, x17")
            self.emit("ldr x29, [x29]")
        self.emit("ret")

    def inicio_programa(self) -> None:
        self.la("x28", "__globales")

    def fin_programa(self) -> None:
        self.emit("b __rt_exit")

    # --- excepciones ----------------------------------------------------

    def activar_manejador(self, offset: int, etiqueta: str) -> None:
        """Registro de `try` en el marco: (anterior, catch, x29, sp)."""
        self.la("x16", "__rt_handler")
        self.emit("ldr x17, [x16]")
        self.store("ref", "x17", "x29", offset)
        self.la("x17", etiqueta)
        self.store("ref", "x17", "x29", offset + 8)
        self.store("ref", "x29", "x29", offset + 16)
        self.emit("mov x17, sp")
        self.store("ref", "x17", "x29", offset + 24)
        self._sumar_a_registro("x17", "x29", offset, "x8")
        self.emit("str x17, [x16]")

    def desactivar_manejador(self) -> None:
        self.la("x16", "__rt_handler")
        self.emit("ldr x17, [x16]")
        self.emit("ldr x17, [x17]")
        self.emit("str x17, [x16]")

    # --- datos y runtime ------------------------------------------------

    def datos(self, p) -> None:
        self.lineas += ["", "// ---- datos", "    .data", "    .balign 8"]
        self.lineas.append(f"__globales: .space {max(p.global_area.total_size, 8)}")
        for clave, etiqueta in p.flotantes.items():
            self.lineas.append(f"{etiqueta}: .double {texto_double(clave)}")
        for layout in p.layouts.values():
            nombre = p.string_de_texto(layout.name)
            tabla = layout.method_table()
            metodos = [
                p.etiqueta(tabla[m]) if m in tabla else "0"
                for m, _ in sorted(p.selectores.items(), key=lambda par: par[1])
            ]
            self.lineas.append(f"cls_{layout.name}: .quad {', '.join([nombre, *metodos])}")
        for nombre, etiqueta in p.closures_estaticos.items():
            self.lineas.append(f"{etiqueta}: .quad {p.etiqueta(nombre)}, 0")
        for etiqueta, contenido in p.descriptores_tipo.values():
            self.lineas.append(f"{etiqueta}: .quad {contenido[0]}, {contenido[1]}")
        for texto, etiqueta in p.strings.items():
            escapado = _escapar(texto)
            if escapado is not None:
                self.lineas.append(f'{etiqueta}: .asciz "{escapado}"')
            else:
                octetos = ", ".join(str(b) for b in texto.encode("utf-8"))
                self.lineas.append(f"{etiqueta}: .byte {octetos}, 0")

    def runtime(self) -> None:
        self.lineas += ["", RUNTIME_DATOS, RUNTIME_TEXTO]
        self.lineas.append('    .section .note.GNU-stack,"",%progbits')  # pila no ejecutable
