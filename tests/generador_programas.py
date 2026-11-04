"""
Generador de programas Compiscript aleatorios (y reproducibles por semilla)
para las pruebas diferenciales: cada programa se ejecuta en el simulador de
TAC, en MIPS y en AArch64, y las tres salidas deben coincidir.

Los programas siempre terminan (bucles acotados) y buscan los casos dificiles
del back-end: muchos argumentos (por registro y por pila), expresiones profundas
que agotan los registros, valores que cruzan llamadas, closures, herencia y
errores de ejecucion capturados en otra funcion.
"""

from __future__ import annotations

import random

TIPOS = ["integer", "float", "boolean", "string"]


class Generador:
    def __init__(self, semilla: int) -> None:
        self.r = random.Random(semilla)
        self.lineas: list[str] = []
        self.sangria = 0
        self.funciones: list[tuple[str, list[str], str]] = []
        self.n = 0

    def nombre(self, prefijo: str) -> str:
        self.n += 1
        return f"{prefijo}{self.n}"

    def w(self, texto: str) -> None:
        self.lineas.append("  " * self.sangria + texto)

    # --- expresiones ----------------------------------------------------

    def expr(self, tipo: str, vars_: dict[str, list[str]], prof: int = 0) -> str:
        r = self.r
        candidatos = vars_.get(tipo, [])
        if prof > 3 or r.random() < 0.25:
            if candidatos and r.random() < 0.75:
                return r.choice(candidatos)
            return self.literal(tipo)
        if tipo == "integer":
            return self.expr_entera(vars_, prof)
        if tipo == "float":
            a, b = self.expr("float", vars_, prof + 1), self.expr("float", vars_, prof + 1)
            opcion = r.randrange(5)
            if opcion == 0:
                return f"({a} + {b})"
            if opcion == 1:
                return f"({a} - {b})"
            if opcion == 2:
                return f"({a} * 0.5)"
            if opcion == 3:
                return f"({a} + {self.expr('integer', vars_, prof + 1)})"
            return f"(-{a})"
        if tipo == "boolean":
            opcion = r.randrange(6)
            if opcion == 0:
                return f"({self.expr('integer', vars_, prof + 1)} < {self.expr('integer', vars_, prof + 1)})"
            if opcion == 1:
                return f"({self.expr('float', vars_, prof + 1)} >= {self.expr('float', vars_, prof + 1)})"
            if opcion == 2:
                return f"({self.expr('boolean', vars_, prof + 1)} && {self.expr('boolean', vars_, prof + 1)})"
            if opcion == 3:
                return f"({self.expr('boolean', vars_, prof + 1)} || {self.expr('boolean', vars_, prof + 1)})"
            if opcion == 4:
                return f"(!{self.expr('boolean', vars_, prof + 1)})"
            return f"({self.expr('string', vars_, prof + 1)} == {self.expr('string', vars_, prof + 1)})"
        if r.random() < 0.5:
            return f"({self.expr('string', vars_, prof + 1)} + {self.expr('string', vars_, prof + 1)})"
        return self.literal("string")

    def expr_entera(self, vars_: dict[str, list[str]], prof: int) -> str:
        r = self.r
        a, b = self.expr("integer", vars_, prof + 1), self.expr("integer", vars_, prof + 1)
        opcion = r.randrange(9)
        if opcion <= 2:
            return f"({a} + {b})"
        if opcion == 3:
            return f"({a} - {b})"
        if opcion == 4:
            return f"({a} * {b})"
        if opcion == 5:
            return f"({a} / {r.choice([1, 2, 3, 7, -5])})"
        if opcion == 6:
            return f"({a} % {r.choice([2, 3, 10, -7])})"
        if opcion == 7:
            return f"(-{a})"
        return f"({self.expr('boolean', vars_, prof + 1)} ? {a} : {b})"

    def literal(self, tipo: str) -> str:
        r = self.r
        if tipo == "integer":
            return str(r.choice([0, 1, 2, 3, 7, 10, 100, 1000, 65536, 2147483647]))
        if tipo == "float":
            return r.choice(["0.0", "0.5", "1.25", "2.0", "3.5", "10.75"])
        if tipo == "boolean":
            return r.choice(["true", "false"])
        return '"' + r.choice(["", "a", "hola", "mundo", "x y"]) + '"'

    def llamada(self, tipo: str, vars_: dict[str, list[str]]) -> str | None:
        opciones = [f for f in self.funciones if f[2] == tipo]
        if not opciones:
            return None
        nombre, params, _ = self.r.choice(opciones)
        return f"{nombre}({', '.join(self.expr(p, vars_, 2) for p in params)})"

    # --- sentencias -----------------------------------------------------

    def declarar(self, vars_: dict[str, list[str]], tipo: str | None = None) -> None:
        tipo = tipo or self.r.choice(TIPOS)
        nombre = self.nombre("v")
        valor = self.llamada(tipo, vars_) if self.r.random() < 0.3 else None
        self.w(f"let {nombre}: {tipo} = {valor or self.expr(tipo, vars_)};")
        vars_.setdefault(tipo, []).append(nombre)

    def sentencia(self, vars_: dict[str, list[str]], prof: int) -> None:  # noqa: C901
        r = self.r
        opcion = r.randrange(14)
        locales = {k: list(v) for k, v in vars_.items()}
        if opcion <= 2:
            self.declarar(vars_)
        elif opcion == 3 and vars_.get("integer"):
            self.w(f"{r.choice(vars_['integer'])} = {self.expr('integer', vars_)};")
        elif opcion == 4:
            tipo = r.choice(TIPOS)
            self.w(f"print({self.expr(tipo, vars_)});")
        elif opcion == 5 and prof < 3:
            self.w(f"if ({self.expr('boolean', vars_)}) {{")
            self.bloque(locales, prof + 1)
            self.w("} else {")
            self.bloque({k: list(v) for k, v in vars_.items()}, prof + 1)
            self.w("}")
        elif opcion == 6 and prof < 3:
            i = self.nombre("i")
            self.w(f"for (let {i}: integer = 0; {i} < {r.randrange(1, 5)}; {i} = {i} + 1) {{")
            locales.setdefault("integer", [])
            self.bloque(locales, prof + 1)
            self.w("}")
        elif opcion == 7 and prof < 3:
            c = self.nombre("c")
            self.w(f"let {c}: integer = {r.randrange(1, 4)};")
            self.w(f"while ({c} > 0) {{")
            self.sangria += 1
            self.w(f"{c} = {c} - 1;")
            self.sangria -= 1
            self.bloque(locales, prof + 1)
            self.w("}")
        elif opcion == 8 and prof < 3:
            self.lista(vars_)
        elif opcion == 9 and prof < 3:
            self.try_catch(locales, prof)
        elif opcion == 10:
            llamada = self.llamada(r.choice(TIPOS), vars_)
            if llamada:
                self.w(f"print({llamada});")
        elif opcion == 11 and prof < 2:
            self.switch(locales, prof)
        elif opcion == 12 and vars_.get("float"):
            self.w(f"{r.choice(vars_['float'])} = {self.expr('float', vars_)};")
        elif r.random() < 0.5:
            self.w(f"print({self.expresion_profunda(r.choice(['integer', 'float']), vars_)});")
        else:
            self.w(f"print({self.expresion_ancha(vars_)});")

    def bloque(self, vars_: dict[str, list[str]], prof: int) -> None:
        self.sangria += 1
        for _ in range(self.r.randrange(1, 4)):
            self.sentencia(vars_, prof)
        self.sangria -= 1

    def expresion_ancha(self, vars_: dict[str, list[str]]) -> str:
        """Muchos valores vivos a la vez: agota los registros (`getReg` derrama)."""
        hojas = [self.expr("integer", vars_, 3) for _ in range(self.r.randrange(8, 20))]
        while len(hojas) > 1:
            n = self.r.randrange(len(hojas) - 1)
            hojas[n:n + 2] = [f"({hojas[n]} + {hojas[n + 1]})"]
        return f"({' * 1 + '.join(f'({h})' for h in hojas)})"

    def expresion_profunda(self, tipo: str, vars_: dict[str, list[str]]) -> str:
        """`(a*b) + ((c*d) + (...))`: cada operando izquierdo es un temporal que
        sigue vivo mientras se evalua el derecho, asi que hay mas valores vivos
        que registros. Con llamadas, ademas cruzan llamadas."""
        r = self.r
        limite = r.randrange(12, 30)
        texto = self.expr(tipo, vars_, 3)
        for _ in range(limite):
            izquierdo = None
            if r.random() < 0.25:
                izquierdo = self.llamada(tipo, vars_)
            if izquierdo is None:
                a = self.expr(tipo, vars_, 3)
                izquierdo = f"({a} * 1)" if tipo == "integer" else f"({a} * 0.5)"
            texto = f"({izquierdo} + {texto})"
        return texto

    def lista(self, vars_: dict[str, list[str]]) -> None:
        r = self.r
        tipo = r.choice(["integer", "float", "boolean", "string"])
        nombre = self.nombre("l")
        elementos = [self.expr(tipo, vars_, 2) for _ in range(r.randrange(1, 5))]
        self.w(f"let {nombre}: {tipo}[] = [{', '.join(elementos)}];")
        self.w(f"print({nombre});")
        self.w(f"{nombre}[{r.randrange(len(elementos))}] = {self.expr(tipo, vars_, 2)};")
        x = self.nombre("e")
        self.w(f"foreach ({x} in {nombre}) {{ print({x}); }}")

    def try_catch(self, vars_: dict[str, list[str]], prof: int) -> None:
        r = self.r
        e = self.nombre("err")
        self.w("try {")
        self.bloque({k: list(v) for k, v in vars_.items()}, prof + 1)
        self.sangria += 1
        opcion = r.randrange(4)
        if opcion == 0:
            self.w(f"print({self.expr('integer', vars_, 2)} / {r.choice(['0', '(1 - 1)'])});")
        elif opcion == 1:
            self.w(f"let m{self.n}: integer[] = [1, 2]; print(m{self.n}[{r.choice(['2', '-1', '50'])}]);")
        elif opcion == 2 and self.funciones:
            nombre, params, _ = r.choice(self.funciones)
            self.w(f"{nombre}({', '.join(self.expr(p, vars_, 2) for p in params)});")
        self.sangria -= 1
        self.w(f"}} catch ({e}) {{")
        self.sangria += 1
        self.w(f"print({e});")
        self.sangria -= 1
        self.w("}")

    def switch(self, vars_: dict[str, list[str]], prof: int) -> None:
        r = self.r
        self.w(f"switch ({self.expr('integer', vars_)} % 3) {{")
        for valor in range(3):
            self.w(f"case {valor}:")
            self.bloque({k: list(v) for k, v in vars_.items()}, prof + 1)
            if r.random() < 0.6:
                self.sangria += 1
                self.w("break;")
                self.sangria -= 1
        self.w("default:")
        self.bloque({k: list(v) for k, v in vars_.items()}, prof + 1)
        self.w("}")

    def funcion(self, globales: dict[str, list[str]]) -> None:
        r = self.r
        nombre = self.nombre("f")
        cantidad = r.choice([0, 1, 2, 3, 4, 5, 6, 9, 10, 14, 20])
        params = [r.choice(TIPOS) for _ in range(cantidad)]
        retorno = r.choice(TIPOS)
        nombres = [self.nombre("p") for _ in params]
        firma = ", ".join(f"{n}: {t}" for n, t in zip(nombres, params))
        self.w(f"function {nombre}({firma}): {retorno} {{")
        self.sangria += 1
        vars_ = {k: list(v) for k, v in globales.items()}
        for n, t in zip(nombres, params):
            vars_.setdefault(t, []).append(n)
        for _ in range(r.randrange(1, 5)):
            self.sentencia(vars_, 1)
        if r.random() < 0.4:  # funcion anidada que usa variables del entorno
            interna = self.nombre("g")
            self.w(f"function {interna}(q: integer): {retorno} {{")
            self.sangria += 1
            internas = {k: list(v) for k, v in vars_.items()}
            internas.setdefault("integer", []).append("q")
            if vars_.get("integer"):
                self.w(f"{r.choice(vars_['integer'])} = q + 1;")
            self.w(f"return {self.expr(retorno, internas)};")
            self.sangria -= 1
            self.w("}")
            self.w(f"return {interna}({self.expr('integer', vars_)});")
        else:
            self.w(f"return {self.expr(retorno, vars_)};")
        self.sangria -= 1
        self.w("}")
        self.funciones.append((nombre, params, retorno))

    def clases(self, globales: dict[str, list[str]]) -> None:
        r = self.r
        self.w("class Base {")
        self.w("  let a: integer = 3;")
        self.w("  let b: float = 1.5;")
        self.w("  let s: string;")
        self.w('  function constructor(a: integer) { this.a = a; this.s = "base"; }')
        self.w("  function valor(): integer { return this.a; }")
        self.w("  function nombre(): string { return this.s; }")
        self.w("}")
        self.w("class Hija : Base {")
        self.w("  let c: boolean = true;")
        self.w(f"  function valor(): integer {{ return this.a * {r.randrange(2, 9)}; }}")
        self.w('  function nombre(): string { return "hija " + this.s; }')
        self.w("}")
        self.w("let objetos: Base[] = [new Base(2), new Hija(5), new Base(7)];")
        self.w("foreach (o in objetos) { print(o.valor()); print(o.nombre()); print(o.b); print(o); }")

    def programa(self) -> str:
        r = self.r
        globales: dict[str, list[str]] = {}
        for _ in range(r.randrange(2, 6)):
            self.declarar(globales)
        if r.random() < 0.5:
            self.clases(globales)
        for _ in range(r.randrange(1, 5)):
            self.funcion(globales)
        for _ in range(r.randrange(4, 10)):
            self.sentencia(globales, 0)
        for nombres in globales.values():
            for nombre in nombres:
                self.w(f"print({nombre});")
        return "\n".join(self.lineas) + "\n"


def programa_aleatorio(semilla: int) -> str:
    return Generador(semilla).programa()
