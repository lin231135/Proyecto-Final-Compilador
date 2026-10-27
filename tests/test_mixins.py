"""
Ningun par de mixins define el mismo `visit*`. Una colision la gana en
silencio el mixin mas a la izquierda del MRO en semantico/visitor.py y el
otro nunca corre.
"""

from semantico.class_mixin import ClassMixin
from semantico.function_mixin import FunctionMixin
from semantico.scope_mixin import ScopeMixin
from semantico.type_mixin import TypeMixin
from driver import analizar

MIXINS = {
    "ScopeMixin": ScopeMixin,
    "TypeMixin": TypeMixin,
    "FunctionMixin": FunctionMixin,
    "ClassMixin": ClassMixin,
}


def _visit_methods(cls) -> set[str]:
    return {nombre for nombre in vars(cls) if nombre.startswith("visit")}


def test_ningun_par_de_mixins_define_el_mismo_visit():
    visitas_por_mixin = {nombre: _visit_methods(cls) for nombre, cls in MIXINS.items()}
    nombres = list(MIXINS)
    colisiones = []
    for i in range(len(nombres)):
        for j in range(i + 1, len(nombres)):
            a, b = nombres[i], nombres[j]
            interseccion = visitas_por_mixin[a] & visitas_por_mixin[b]
            if interseccion:
                colisiones.append((a, b, sorted(interseccion)))

    assert not colisiones, f"colision de visit* entre mixins (silenciosa por MRO): {colisiones}"


def test_cada_mixin_define_al_menos_un_visit_salvo_scope():
    """Sanity check: si un mixin quedo vacio por error, aqui se nota."""
    for nombre, cls in MIXINS.items():
        if nombre == "ScopeMixin":
            continue  # es infraestructura, no define visit*
        assert _visit_methods(cls), f"{nombre} no define ningun visit*"


# ---------------------------------------------------------------------
# Prepass: estos casos fallarian con "ambito"/"clase" (nombre no declarado)
# sin la pasada 1.
# ---------------------------------------------------------------------

def test_recursion_mutua_entre_funciones_globales():
    src = """
    function esPar(n: integer): boolean { if (n == 0) { return true; } return esImpar(n - 1); }
    function esImpar(n: integer): boolean { if (n == 0) { return false; } return esPar(n - 1); }
    """
    assert analizar(src).ok


def test_metodo_llama_a_otro_declarado_mas_abajo():
    src = """
    class Calculadora {
      function doble(x: integer): integer { return this.multiplicar(x, 2); }
      function multiplicar(a: integer, b: integer): integer { return a * b; }
    }
    """
    assert analizar(src).ok


def test_herencia_con_clase_padre_declarada_despues():
    assert analizar("class Perro : Animal {} class Animal {}").ok


def test_prepass_no_genera_falsos_duplicados():
    """El prepass no debe hacer que una funcion/clase unica parezca declarada dos veces."""
    assert analizar("function f() {} class A {}").ok


def test_prepass_no_esconde_duplicados_reales():
    r1 = analizar("function f() {} function f() {}")
    assert not r1.ok and "ambito" in {e.category for e in r1.errores}

    r2 = analizar("class A {} class A {}")
    assert not r2.ok and "clase" in {e.category for e in r2.errores}
