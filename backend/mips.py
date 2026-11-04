"""
MIPS32 (MARS y SPIM). Se usan solo instrucciones y pseudoinstrucciones que los
dos simuladores aceptan y no se depende de los delay slots.

Registros:
    $t0-$t7   valores de un bloque (getReg). Los destruye una llamada.
    $s0-$s7   variables de larga vida y valores que cruzan llamadas. Los
              preserva quien es llamado.
    $t8 $t9   scratch del generador (direcciones); nunca guardan un valor.
    $a0-$a3   cuatro primeros argumentos enteros/referencia.
    $v0       retorno entero/referencia; $f0, retorno float.
    $v1       enlace de acceso hacia el llamado.
    $fp       base del registro de activacion; $sp, tope de la pila.
    $gp       base del area estatica (globales).
    $f4-$f18  valores float (getReg). Los destruye una llamada.
    $f0 $f2   scratch de punto flotante.

Un float (double) y los argumentos a partir del quinto viajan por la pila, en
la ranura `8 * posicion` de la zona saliente del llamador.
"""

from __future__ import annotations

from backend.mips_runtime import RUNTIME_DATOS, RUNTIME_TEXTO
from backend.target import MarcoFuncion, Target, texto_double

_BRANCH = {"<": "blt", "<=": "ble", ">": "bgt", ">=": "bge", "==": "beq", "!=": "bne"}
_FBIN = {"+": "add.d", "-": "sub.d", "*": "mul.d", "/": "div.d"}


def _escapar(texto: str) -> str | None:
    """Texto para `.asciiz`, o None si tiene bytes que no se pueden escribir asi."""
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


class MIPS(Target):
    nombre = "mips"
    palabra = 4
    alineacion_pila = 8
    tamanio_manejador = 16

    temporales = ["$t0", "$t1", "$t2", "$t3", "$t4", "$t5", "$t6", "$t7"]
    guardados = ["$s0", "$s1", "$s2", "$s3", "$s4", "$s5", "$s6", "$s7"]
    flotantes = ["$f4", "$f6", "$f8", "$f10", "$f14", "$f16", "$f18"]
    argumentos = ["$a0", "$a1", "$a2", "$a3"]
    scratch0, scratch1, fscratch0 = "$t8", "$t9", "$f0"
    zero, fp, sp, global_base, enlace = "$zero", "$fp", "$sp", "$gp", "$v1"
    retorno, retorno_flotante = "$v0", "$f0"

    # --- salida ---------------------------------------------------------

    def encabezado(self) -> None:
        self.lineas += [
            "# Generado por el compilador de Compiscript (MIPS32, para MARS o SPIM)",
            "    .text",
            "    .globl main",
        ]

    def comentario_seccion(self, texto: str) -> None:
        self.lineas += ["", f"# ---- {texto}"]

    def comentario_tac(self, texto: str) -> None:
        self.lineas.append(f"    # {texto}")

    def etiqueta_global(self, nombre: str) -> None:
        self.label(nombre)

    # --- movimiento de datos --------------------------------------------

    def li(self, r: str, valor: int) -> None:
        self.emit(f"li {r}, {valor}")

    def la(self, r: str, etiqueta: str) -> None:
        self.emit(f"la {r}, {etiqueta}")

    def mov(self, d: str, s: str) -> None:
        if d != s:
            self.emit(f"move {d}, {s}")

    def fmov(self, d: str, s: str) -> None:
        if d != s:
            self.emit(f"mov.d {d}, {s}")

    def fconst(self, r: str, etiqueta: str) -> None:
        self.emit(f"l.d {r}, {etiqueta}")

    def load(self, kind: str, r: str, base: str, offset: int) -> None:
        op = {"float": "l.d", "bool": "lbu"}.get(kind, "lw")
        self.emit(f"{op} {r}, {offset}({base})")

    def store(self, kind: str, r: str, base: str, offset: int) -> None:
        if kind == "float":
            if r == self.zero:  # el literal 0.0 no llega aqui: es por `null`
                self.emit(f"sw $zero, {offset}({base})")
                self.emit(f"sw $zero, {offset + 4}({base})")
            else:
                self.emit(f"s.d {r}, {offset}({base})")
        else:
            self.emit(f"{'sb' if kind == 'bool' else 'sw'} {r}, {offset}({base})")

    def poner_en_cero(self, base: str, offset: int, size: int) -> None:
        if size == 1:
            self.emit(f"sb $zero, {offset}({base})")
        else:
            for delta in range(0, size, 4):
                self.emit(f"sw $zero, {offset + delta}({base})")

    # --- aritmetica entera ----------------------------------------------

    def inmediato_valido(self, operador: str, valor: int) -> bool:
        return operador in ("+", "-") and -32767 <= valor <= 32767

    def bin_inmediato(self, operador: str, d: str, a: str, valor: int) -> None:
        self.emit(f"addiu {d}, {a}, {valor if operador == '+' else -valor}")

    def bin_entero(self, operador: str, d: str, a: str, b: str) -> None:
        if operador == "+":
            self.emit(f"addu {d}, {a}, {b}")
        elif operador == "-":
            self.emit(f"subu {d}, {a}, {b}")
        elif operador == "*":
            self.emit(f"mul {d}, {a}, {b}")
        else:
            self.emit(f"div {a}, {b}")
            self.emit(f"{'mflo' if operador == '/' else 'mfhi'} {d}")

    def negar_entero(self, d: str, a: str) -> None:
        self.emit(f"subu {d}, $zero, {a}")

    def negar_booleano(self, d: str, a: str) -> None:
        self.emit(f"xori {d}, {a}, 1")

    def comparar_a_valor(self, op: str, d: str, a: str, b: str, ancho: str) -> None:
        if op == "<":
            self.emit(f"slt {d}, {a}, {b}")
        elif op == ">":
            self.emit(f"slt {d}, {b}, {a}")
        elif op == "<=":
            self.emit(f"slt {d}, {b}, {a}")
            self.emit(f"xori {d}, {d}, 1")
        elif op == ">=":
            self.emit(f"slt {d}, {a}, {b}")
            self.emit(f"xori {d}, {d}, 1")
        elif op == "==":
            self.emit(f"xor {d}, {a}, {b}")
            self.emit(f"sltiu {d}, {d}, 1")
        else:
            self.emit(f"xor {d}, {a}, {b}")
            self.emit(f"sltu {d}, $zero, {d}")

    # --- punto flotante -------------------------------------------------

    def bin_flotante(self, operador: str, d: str, a: str, b: str) -> None:
        if operador == "%":  # a - b * trunc(a / b)
            self.emit(f"div.d $f0, {a}, {b}")
            self.emit("trunc.w.d $f0, $f0")
            self.emit("cvt.d.w $f0, $f0")
            self.emit(f"mul.d $f0, {b}, $f0")
            self.emit(f"sub.d {d}, {a}, $f0")
        else:
            self.emit(f"{_FBIN[operador]} {d}, {a}, {b}")

    def negar_flotante(self, d: str, a: str) -> None:
        self.emit(f"neg.d {d}, {a}")

    def entero_a_flotante(self, d: str, a: str) -> None:
        self.emit(f"mtc1 {a}, {d}")
        self.emit(f"cvt.d.w {d}, {d}")

    def _comparar_flotantes(self, op: str, a: str, b: str) -> str:
        """Emite la comparacion; devuelve la instruccion de salto si es cierta."""
        if op == "<":
            self.emit(f"c.lt.d {a}, {b}")
        elif op == "<=":
            self.emit(f"c.le.d {a}, {b}")
        elif op == ">":
            self.emit(f"c.lt.d {b}, {a}")
        elif op == ">=":
            self.emit(f"c.le.d {b}, {a}")
        else:
            self.emit(f"c.eq.d {a}, {b}")
        return "bc1f" if op == "!=" else "bc1t"

    def saltar_comparando_flotantes(self, op: str, a: str, b: str, etiqueta: str) -> None:
        self.emit(f"{self._comparar_flotantes(op, a, b)} {etiqueta}")

    def comparar_flotante_a_valor(self, op: str, d: str, a: str, b: str) -> None:
        fin = self.etiqueta_local()
        self.emit(f"li {d}, 1")
        self.emit(f"{self._comparar_flotantes(op, a, b)} {fin}")
        self.emit(f"li {d}, 0")
        self.label(fin)

    def saltar_si_flotante_cero(self, r: str, etiqueta: str) -> None:
        self.emit("mtc1 $zero, $f0")
        self.emit("mtc1 $zero, $f1")
        self.emit(f"c.eq.d {r}, $f0")
        self.emit(f"bc1t {etiqueta}")

    # --- saltos ---------------------------------------------------------

    def jump(self, etiqueta: str) -> None:
        self.emit(f"j {etiqueta}")

    def saltar_comparando(self, op: str, a: str, b: str, etiqueta: str, ancho: str) -> None:
        self.emit(f"{_BRANCH[op]} {a}, {b}, {etiqueta}")

    def saltar_si_cero(self, r: str, kind: str, etiqueta: str) -> None:
        self.emit(f"beqz {r}, {etiqueta}")

    def saltar_si_no_cero(self, r: str, kind: str, etiqueta: str) -> None:
        self.emit(f"bnez {r}, {etiqueta}")

    # --- listas ---------------------------------------------------------

    def direccion_elemento(self, lista: str, indice: str, error: str) -> str:
        """Verifica 0 <= indice < longitud (una comparacion sin signo cubre
        los dos extremos) y devuelve el registro con la direccion del elemento
        menos `offset_elementos`."""
        self.emit(f"lw $t8, 0({lista})")
        self.emit(f"sltu $t9, {indice}, $t8")
        self.emit(f"beqz $t9, {error}")
        self.emit(f"sll $t9, {indice}, 3")
        self.emit(f"addu $t9, $t9, {lista}")
        return "$t9"

    # --- llamadas -------------------------------------------------------

    def registro_argumento(self, posicion: int, kind: str) -> str | None:
        return self.argumentos[posicion] if posicion < 4 and kind != "float" else None

    def registro_argumento_runtime(self, posicion: int, kind: str) -> str | None:
        return "$f12" if kind == "float" else self.argumentos[posicion]

    def argumento_entrante(self, marco: MarcoFuncion, posicion: int) -> tuple[str, int]:
        if marco.en_heap:
            return "$sp", marco.salientes + 8 * posicion
        return "$fp", marco.tamanio + 8 * posicion

    def call(self, etiqueta: str) -> None:
        self.emit(f"jal {etiqueta}")

    def recorrer_enlaces(self, destino: str, saltos: int) -> None:
        """`destino` = marco alcanzado tras `saltos` enlaces de acceso."""
        self.emit(f"lw {destino}, 8($fp)")
        for _ in range(saltos - 1):
            self.emit(f"lw {destino}, 8({destino})")

    def llamar_closure(self, closure: str, error_null: str) -> None:
        """Un closure es el par (codigo, entorno)."""
        self.emit(f"beqz {closure}, {error_null}")
        self.emit(f"lw $v1, 4({closure})")
        self.emit(f"lw $t9, 0({closure})")
        self.emit("jalr $t9")

    def llamar_virtual(self, selector: int, error_null: str) -> None:
        """El receptor es el primer argumento; su palabra 0 apunta al
        descriptor de la clase real (nombre + tabla de metodos)."""
        self.emit(f"beqz $a0, {error_null}")
        self.emit("lw $t9, 0($a0)")
        self.emit(f"lw $t9, {4 * (selector + 1)}($t9)")
        self.emit("jalr $t9")

    def prologo(self, m: MarcoFuncion) -> None:
        if m.en_heap:
            # El marco sobrevive a la funcion (closure): se pide al heap,
            # conservando los argumentos que ya vienen en registros.
            self.emit("addiu $sp, $sp, -24")
            for n, r in enumerate(["$a0", "$a1", "$a2", "$a3", "$v1", "$ra"]):
                self.emit(f"sw {r}, {4 * n}($sp)")
            self.emit(f"li $a0, {m.tamanio}")
            self.emit("jal __rt_alloc")
            self.emit("move $t9, $v0")
            for n, r in enumerate(["$a0", "$a1", "$a2", "$a3", "$v1", "$ra"]):
                self.emit(f"lw {r}, {4 * n}($sp)")
            self.emit("addiu $sp, $sp, 24")
            self.emit("sw $fp, 0($t9)      # enlace de control")
            self.emit("sw $ra, 16($t9)     # direccion de retorno")
            self.emit("move $fp, $t9")
            if m.salientes:
                self.emit(f"addiu $sp, $sp, -{m.salientes}")
        else:
            self.emit(f"addiu $sp, $sp, -{m.tamanio + m.salientes}")
            self.emit(f"sw $fp, {m.salientes}($sp)     # enlace de control")
            self.emit(f"sw $ra, {m.salientes + 16}($sp)     # direccion de retorno")
            self.emit(f"addiu $fp, $sp, {m.salientes}")
        if m.usa_enlace:
            self.emit("sw $v1, 8($fp)      # enlace de acceso")
        for registro, offset in m.guardados:
            self.emit(f"sw {registro}, {offset}($fp)")

    def epilogo(self, m: MarcoFuncion) -> None:
        for registro, offset in m.guardados:
            self.emit(f"lw {registro}, {offset}($fp)")
        self.emit("lw $ra, 16($fp)")
        if m.en_heap:
            if m.salientes:
                self.emit(f"addiu $sp, $sp, {m.salientes}")
        else:
            self.emit(f"addiu $sp, $fp, {m.tamanio}")
        self.emit("lw $fp, 0($fp)")
        self.emit("jr $ra")

    def inicio_programa(self) -> None:
        self.emit("la $gp, __globales")
        self.emit("li $t8, -8")
        self.emit("and $sp, $sp, $t8     # los double exigen alineacion a 8")

    def fin_programa(self) -> None:
        self.emit("j __rt_exit")

    # --- excepciones ----------------------------------------------------

    def activar_manejador(self, offset: int, etiqueta: str) -> None:
        """Registro de `try` en el marco: (anterior, catch, $fp, $sp)."""
        self.emit("lw $t8, __rt_handler")
        self.emit(f"sw $t8, {offset}($fp)")
        self.emit(f"la $t8, {etiqueta}")
        self.emit(f"sw $t8, {offset + 4}($fp)")
        self.emit(f"sw $fp, {offset + 8}($fp)")
        self.emit(f"sw $sp, {offset + 12}($fp)")
        self.emit(f"addiu $t8, $fp, {offset}")
        self.emit("sw $t8, __rt_handler")

    def desactivar_manejador(self) -> None:
        self.emit("lw $t8, __rt_handler")
        self.emit("lw $t8, 0($t8)")
        self.emit("sw $t8, __rt_handler")

    # --- datos y runtime ------------------------------------------------

    def datos(self, p) -> None:
        self.lineas += ["", "# ---- datos", "    .data", "    .align 3"]
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
            self.lineas.append(f"cls_{layout.name}: .word {', '.join([nombre, *metodos])}")
        for nombre, etiqueta in p.closures_estaticos.items():
            self.lineas.append(f"{etiqueta}: .word {p.etiqueta(nombre)}, 0")
        for etiqueta, contenido in p.descriptores_tipo.values():
            self.lineas.append(f"{etiqueta}: .word {contenido[0]}, {contenido[1]}")
        for texto, etiqueta in p.strings.items():
            escapado = _escapar(texto)
            if escapado is not None:
                self.lineas.append(f'{etiqueta}: .asciiz "{escapado}"')
            else:
                octetos = ", ".join(str(b) for b in texto.encode("utf-8"))
                self.lineas.append(f"{etiqueta}: .byte {octetos}, 0")

    def runtime(self) -> None:
        self.lineas += ["", RUNTIME_DATOS, RUNTIME_TEXTO]
