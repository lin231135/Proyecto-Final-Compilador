"""
TAC exacto para cada construccion del enunciado. Cada caso compara la salida
completa de `main` (o de la funcion indicada): si cambia el formato del TAC,
estos tests -y docs/Lenguaje_Intermedio_TAC.md- deben actualizarse juntos.
"""

import pytest

from tests.helpers import compilar, tac


def lineas(texto: str) -> list[str]:
    return [l.strip() for l in texto.strip().splitlines()]


# ----------------------------------------------------------------------
# Expresiones y asignaciones
# ----------------------------------------------------------------------

EXPRESIONES = [
    ("precedencia", "let a: integer = 1 + 2 * 3;", "t1 = 2 * 3\n@a = 1 + t1"),
    ("parentesis", "let a: integer = (1 + 2) * 3;", "t1 = 1 + 2\n@a = t1 * 3"),
    ("asoc_izquierda", "let a: integer = 10 - 4 - 3;", "t1 = 10 - 4\n@a = t1 - 3"),
    ("division_modulo", "let a: integer = 8 / 2 % 3;", "t1 = 8 / 2\n@a = t1 % 3"),
    ("dos_subexpresiones", "let a: integer = 2 * 3 + 4 * 5;", "t1 = 2 * 3\nt2 = 4 * 5\n@a = t1 + t2"),
    ("unario_literal", "let a: integer = -5;", "@a = -5"),
    ("unario_variable", "let b: integer = 1; let a: integer = -b;", "@b = 1\n@a = - @b"),
    ("negacion_logica", "let b: boolean = true; let a: boolean = !b;", "@b = true\n@a = ! @b"),
    ("comparacion_valor", "let x: integer = 1; let a: boolean = x < 3;", "@x = 1\n@a = @x < 3"),
    ("const", "const K: integer = 7;", "@K = 7"),
    ("reasignacion", "let x: integer = 1; x = x + 1;", "@x = 1\n@x = @x + 1"),
    ("string_concat", 'let s: string = "a" + "b";', '@s = "a" + "b"'),
    ("sin_inicializar", "let x: integer; x = 4;", "@x = 4"),
]


@pytest.mark.parametrize("nombre,fuente,esperado", EXPRESIONES, ids=[e[0] for e in EXPRESIONES])
def test_expresiones(nombre, fuente, esperado):
    assert tac(fuente) == lineas(esperado)


LOGICAS = [
    (
        "and_valor",
        "let a: boolean = true; let b: boolean = false; let c: boolean = a && b;",
        """@a = true
@b = false
ifFalse @a goto L2
ifFalse @b goto L2
t1 = true
goto L3
L2:
t1 = false
L3:
@c = t1""",
    ),
    (
        "or_valor",
        "let a: boolean = true; let b: boolean = false; let c: boolean = a || b;",
        """@a = true
@b = false
if @a goto L1
ifFalse @b goto L2
L1:
t1 = true
goto L3
L2:
t1 = false
L3:
@c = t1""",
    ),
]


@pytest.mark.parametrize("nombre,fuente,esperado", LOGICAS, ids=[e[0] for e in LOGICAS])
def test_logicas_valor(nombre, fuente, esperado):
    # Los numeros de etiqueta dependen del orden de creacion: se comparan
    # normalizados por orden de aparicion.
    assert _normalizar(tac(fuente)) == _normalizar(lineas(esperado))


def _normalizar(lines):
    """Renombra las etiquetas Ln por orden de primera aparicion."""
    import re

    mapa: dict[str, str] = {}
    salida = []
    for l in lines:
        def sub(m):
            return mapa.setdefault(m.group(0), f"L{len(mapa) + 1}")

        salida.append(re.sub(r"\bL\d+\b", sub, l))
    return salida


# ----------------------------------------------------------------------
# Control de flujo
# ----------------------------------------------------------------------

FLUJO = [
    (
        "if",
        "let x: integer = 1; if (x < 3) { x = 5; }",
        "@x = 1\nif @x >= 3 goto L1\n@x = 5\nL1:",
    ),
    (
        "if_else",
        "let x: integer = 1; if (x < 3) { x = 5; } else { x = 6; }",
        "@x = 1\nif @x >= 3 goto L1\n@x = 5\ngoto L2\nL1:\n@x = 6\nL2:",
    ),
    (
        "while",
        "let i: integer = 0; while (i < 3) { i = i + 1; }",
        "@i = 0\nL1:\nif @i >= 3 goto L2\n@i = @i + 1\ngoto L1\nL2:",
    ),
    (
        "do_while",
        "let i: integer = 0; do { i = i + 1; } while (i < 3);",
        "@i = 0\nL1:\n@i = @i + 1\nL2:\nif @i < 3 goto L1\nL3:",
    ),
    (
        "for",
        "for (let i: integer = 0; i < 3; i = i + 1) { print(i); }",
        "i = 0\nL1:\nif i >= 3 goto L3\nparam i\ncall print, 1\nL2:\ni = i + 1\ngoto L1\nL3:",
    ),
    (
        "break_continue",
        "let i: integer = 0; while (true) { i = i + 1; if (i == 2) { continue; } if (i > 3) { break; } }",
        """@i = 0
L1:
@i = @i + 1
if @i != 2 goto L3
goto L1
L3:
if @i <= 3 goto L4
goto L2
L4:
goto L1
L2:""",
    ),
    (
        "switch",
        "let x: integer = 1; switch (x) { case 1: print(1); break; default: print(0); }",
        """@x = 1
if @x == 1 goto L2
goto L3
L2:
param 1
call print, 1
goto L1
L3:
param 0
call print, 1
L1:""",
    ),
    (
        "condicion_compuesta",
        "let a: integer = 1; if (a > 0 && a < 5 || a == 9) { print(a); }",
        """@a = 1
if @a <= 0 goto L2
if @a < 5 goto L1
L2:
if @a != 9 goto L3
L1:
param @a
call print, 1
L3:""",
    ),
]


@pytest.mark.parametrize("nombre,fuente,esperado", FLUJO, ids=[e[0] for e in FLUJO])
def test_control_flujo(nombre, fuente, esperado):
    assert _normalizar(tac(fuente)) == _normalizar(lineas(esperado))


def test_break_va_al_final_del_bucle_que_lo_contiene():
    fuente = """
    for (let i: integer = 0; i < 2; i = i + 1) {
      for (let j: integer = 0; j < 2; j = j + 1) { break; }
    }"""
    texto = "\n".join(tac(fuente))
    # el `goto` del break interno salta a la etiqueta de fin del bucle interno
    assert texto.count("goto L") >= 3


# ----------------------------------------------------------------------
# Funciones
# ----------------------------------------------------------------------


def test_funcion_con_parametros_y_retorno():
    fuente = "function suma(a: integer, b: integer): integer { return a + b; }"
    assert tac(fuente, "suma") == ["t1 = a + b", "return t1"]
    assert compilar(fuente).tac.function("suma").params == ["a", "b"]


def test_llamada_param_call_y_retorno_en_temporal():
    fuente = "function f(a: integer): integer { return a; } let r: integer = f(3);"
    assert tac(fuente) == ["param 3", "@r = call f, 1"]


def test_llamada_como_sentencia_con_valor_descartado():
    fuente = "function f(a: integer): integer { return a; } f(1);"
    assert tac(fuente) == ["param 1", "t1 = call f, 1"]


def test_funcion_void_no_tiene_destino():
    fuente = "function f() { print(1); } f();"
    assert tac(fuente) == ["call f, 0"]


def test_recursion():
    fuente = "function fact(n: integer): integer { if (n <= 1) { return 1; } return n * fact(n - 1); }"
    assert _normalizar(tac(fuente, "fact")) == _normalizar(
        lineas("""if n > 1 goto L1
return 1
L1:
t1 = n - 1
param t1
t1 = call fact, 1
t1 = n * t1
return t1""")
    )


def test_return_implicito_al_final():
    assert tac("function f() { print(1); }", "f")[-1] == "return"


def test_funcion_anidada_tiene_etiqueta_calificada():
    fuente = "function f(): integer { function g(): integer { return 1; } return g(); }"
    r = compilar(fuente)
    assert {f.name for f in r.tac.functions} == {"f", "f.g", "main"}
    assert r.tac.function("f").lines() == ["t1 = call f.g, 0", "return t1"]


def test_closure_accede_al_entorno_con_enlace_de_acceso():
    fuente = """
    function f(): integer {
      let x: integer = 1;
      function g(): integer { x = x + 1; return x; }
      return g();
    }"""
    r = compilar(fuente)
    assert r.tac.function("f.g").lines() == ["up1.x = up1.x + 1", "return up1.x"]
    assert r.generador.closure_accesses[0].hops == 1


def test_closure_dos_niveles():
    fuente = """
    function a(): integer {
      let x: integer = 1;
      function b(): integer {
        function c(): integer { return x; }
        return c();
      }
      return b();
    }"""
    assert tac(fuente, "a.b.c") == ["return up2.x"]


def test_funcion_como_valor():
    fuente = "function f(): integer { return 1; } let g = f; let r: integer = g();"
    assert tac(fuente) == ["@g = closure f", "@r = callc @g, 0"]


def test_variable_global_desde_funcion():
    fuente = "let g: integer = 0; function f() { g = g + 1; }"
    assert tac(fuente, "f") == ["@g = @g + 1", "return"]


def test_parametro_sombrea_global():
    fuente = "let x: integer = 1; function f(x: integer): integer { return x; }"
    assert tac(fuente, "f") == ["return x"]


# ----------------------------------------------------------------------
# Clases y objetos
# ----------------------------------------------------------------------

CLASE = """
class A {
  let x: integer = 5;
  let nombre: string;
  function constructor(nombre: string) { this.nombre = nombre; }
  function dame(): integer { return this.x; }
  function suma(n: integer): integer { return this.x + n; }
}
"""


def test_new_con_constructor():
    assert tac(CLASE + 'let a: A = new A("z");') == [
        "t1 = new A, 24",
        "param t1",
        "call A._init, 1",
        "param t1",
        'param "z"',
        "call A.constructor, 2",
        "@a = t1",
    ]


def test_metodo_usa_this_y_atributos():
    r = compilar(CLASE)
    assert r.tac.function("A.constructor").lines() == ["this.nombre = nombre", "return"]
    assert r.tac.function("A.constructor").params == ["this", "nombre"]
    assert r.tac.function("A.dame").lines() == ["t1 = this.x", "return t1"]
    assert r.tac.function("A._init").lines() == ["this.x = 5", "return"]


def test_invocacion_de_metodo_pasa_el_receptor_como_primer_parametro():
    fuente = CLASE + 'let a: A = new A("z"); let r: integer = a.suma(3);'
    assert tac(fuente)[-3:] == ["param @a", "param 3", "@r = call A.suma, 2"]


def test_lectura_y_escritura_de_atributo():
    fuente = CLASE + 'let a: A = new A("z"); a.x = 9; let r: integer = a.x;'
    assert tac(fuente)[-2:] == ["@a.x = 9", "@r = @a.x"]


def test_herencia_resuelve_metodo_del_padre_estaticamente():
    fuente = CLASE + 'class B : A { } let b: B = new B("q"); let r: integer = b.dame();'
    t = tac(fuente)
    assert "call A.constructor, 2" in t
    assert t[-2:] == ["param @b", "@r = call A.dame, 1"]


def test_override_usa_despacho_dinamico_solo_cuando_hace_falta():
    fuente = """
    class A { function f(): integer { return 1; } function g(): integer { return 2; } }
    class B : A { function f(): integer { return 3; } }
    let a: A = new B();
    let x: integer = a.f();
    let y: integer = a.g();
    """
    t = tac(fuente)
    assert "@x = callv @a.f, 1" in t
    assert "@y = call A.g, 1" in t


def test_clase_sin_constructor_ni_inicializadores_no_genera_llamadas():
    assert tac("class A { let x: integer; } let a: A = new A();") == ["t1 = new A, 16", "@a = t1"]


# ----------------------------------------------------------------------
# Listas
# ----------------------------------------------------------------------


def test_creacion_de_lista():
    assert tac("let xs: integer[] = [1, 2, 3];") == [
        "t1 = newlist 3",
        "t1[0] = 1",
        "t1[1] = 2",
        "t1[2] = 3",
        "@xs = t1",
    ]


def test_lista_vacia():
    assert tac("let xs: integer[] = [];") == ["@xs = newlist 0"]


def test_acceso_y_asignacion_indexados():
    fuente = "let xs: integer[] = [1, 2]; let a: integer = xs[1]; xs[0] = a + 1;"
    assert tac(fuente)[-3:] == ["@a = @xs[1]", "t1 = @a + 1", "@xs[0] = t1"]


def test_indice_calculado():
    fuente = "let xs: integer[] = [1, 2]; let i: integer = 0; let a: integer = xs[i + 1];"
    assert tac(fuente)[-2:] == ["t1 = @i + 1", "@a = @xs[t1]"]


def test_lista_de_listas():
    fuente = "let m: integer[][] = [[1], [2]]; let a: integer = m[1][0];"
    assert tac(fuente)[-2:] == ["t1 = @m[1]", "@a = t1[0]"]


def test_foreach_usa_longitud_e_indice_ocultos():
    fuente = "let xs: integer[] = [1]; foreach (x in xs) { print(x); }"
    t = tac(fuente)
    assert "t1 = 0" in t and "t2 = len @xs" in t and "x = @xs[t1]" in t
