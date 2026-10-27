"""Tabla de simbolos extendida: direcciones, tamanos, etiquetas, AR y layout de objetos."""

import pytest

from codegen.report import render_codegen_report
from core.memory import ActivationRecord, size_of
from core.types import BOOLEAN, FLOAT, INTEGER, STRING, ArrayType
from tests.helpers import compilar


def ar(r, nombre):
    return next(a for a in r.generador.activation_records if a.name == nombre)


def sym(r, nombre):
    return r.table.global_scope.resolve_local(nombre)


class TestTamanos:
    @pytest.mark.parametrize(
        "tipo,esperado",
        [(INTEGER, 4), (FLOAT, 8), (BOOLEAN, 1), (STRING, 8), (ArrayType(INTEGER), 8), (None, 8)],
    )
    def test_size_of(self, tipo, esperado):
        assert size_of(tipo) == esperado


class TestAreaEstatica:
    def test_globales_con_offset_y_alineacion(self):
        r = compilar('let a: integer = 1; let ok: boolean = true; let s: string = "x"; let f: float = 1.5;')
        g = r.generador.global_area
        assert [(s.name, s.offset, s.size) for s in g.slots] == [
            ("a", 0, 4), ("ok", 4, 1), ("s", 8, 8), ("f", 16, 8),
        ]
        assert g.total_size == 24

    def test_simbolo_global_queda_anotado(self):
        r = compilar("let a: integer = 1; let b: integer = 2;")
        b = sym(r, "b")
        assert (b.storage, b.offset, b.size, b.tac_name) == ("global", 4, 4, "@b")


class TestRegistroDeActivacion:
    def test_cabecera_fija(self):
        r = compilar("function f() { }")
        slots = [(s.kind, s.offset) for s in ar(r, "f").slots]
        assert slots == [
            ("control_link", 0), ("access_link", 8), ("return_address", 16), ("return_value", 24),
        ]

    def test_parametros_locales_y_temporales_en_orden(self):
        r = compilar("function f(a: integer, b: string): integer { let c: integer = a + 1; return c * 2; }")
        f = ar(r, "f")
        resto = [(s.kind, s.name, s.offset, s.size) for s in f.slots[4:]]
        assert resto == [
            ("param", "a", 32, 4),
            ("param", "b", 40, 8),
            ("local", "c", 48, 4),
            ("temp", "t1", 56, 8),
        ]
        assert f.total_size == 64

    def test_simbolos_de_parametros_y_locales_apuntan_a_su_ar(self):
        r = compilar("function f(a: integer): integer { let c: integer = a; return c; }")
        f = ar(r, "f")
        scope = next(s for s in r.table._environments if s.kind == "function" and s.name == "f")
        assert scope.resolve_local("a").frame is f
        assert (scope.resolve_local("c").storage, scope.resolve_local("c").offset) == ("local", 36)

    def test_variables_homonimas_en_bloques_distintos_tienen_ranuras_distintas(self):
        fuente = "function f() { { let x: integer = 1; } { let x: integer = 2; } }"
        r = compilar(fuente)
        nombres = [s.name for s in ar(r, "f").slots if s.kind == "local"]
        assert nombres == ["x", "x_2"]

    def test_profundidad_y_padre_lexico(self):
        r = compilar(
            "function a() { function b() { function c() { } } }"
        )
        assert [(x.name, x.depth) for x in r.generador.activation_records] == [
            ("main", 0), ("a", 1), ("a.b", 2), ("a.b.c", 3),
        ]
        assert ar(r, "a.b.c").parent is ar(r, "a.b")

    def test_metodo_lleva_this_como_primer_parametro(self):
        r = compilar("class A { function m(n: integer): integer { return n; } }")
        m = ar(r, "A.m")
        assert [s.name for s in m.slots if s.kind == "param"] == ["this", "n"]

    def test_acceso_a_variable_de_funcion_envolvente_se_registra(self):
        r = compilar(
            "function f(): integer { let x: integer = 1; function g(): integer { return x; } return g(); }"
        )
        (acceso,) = r.generador.closure_accesses
        assert (acceso.variable, acceso.used_in, acceso.defined_in, acceso.hops) == ("x", "f.g", "f", 1)
        assert acceso.offset == 32


class TestEtiquetas:
    def test_funcion_global_y_anidada(self):
        r = compilar("function f() { function g() { } } function h() { }")
        assert sym(r, "f").label == "f"
        assert sym(r, "h").label == "h"
        scope_f = next(s for s in r.table._environments if s.kind == "function" and s.name == "f")
        assert scope_f.resolve_local("g").label == "f.g"

    def test_etiquetas_duplicadas_se_desambiguan(self):
        fuente = "function a() { function g() { } } function b() { function g() { } }"
        r = compilar(fuente)
        etiquetas = {f.name for f in r.tac.functions}
        assert {"a.g", "b.g"} <= etiquetas


class TestLayoutDeObjetos:
    FUENTE = """
    class A { let x: integer = 1; let nombre: string; function f(): integer { return 1; } function g(): integer { return 2; } }
    class B : A { let y: boolean; let z: float; function f(): integer { return 3; } }
    """

    def test_encabezado_y_campos_propios(self):
        r = compilar(self.FUENTE)
        a = r.generador.layouts["A"]
        assert [(f.name, f.offset, f.size) for f in a.fields.values()] == [("x", 8, 4), ("nombre", 16, 8)]
        assert a.instance_size == 24

    def test_campos_heredados_primero(self):
        r = compilar(self.FUENTE)
        b = r.generador.layouts["B"]
        assert [(f.name, f.offset, f.owner) for f in b.fields.values()] == [
            ("x", 8, "A"), ("nombre", 16, "A"), ("y", 24, "B"), ("z", 32, "B"),
        ]
        assert b.instance_size == 40

    def test_tabla_de_metodos_con_herencia_y_override(self):
        r = compilar(self.FUENTE)
        assert r.generador.layouts["B"].method_table() == {"f": "B.f", "g": "A.g"}

    def test_simbolos_de_campo_quedan_anotados(self):
        r = compilar(self.FUENTE)
        scope_b = next(s for s in r.table._environments if s.kind == "class" and s.name == "B")
        y = scope_b.resolve_local("y")
        assert (y.storage, y.offset, y.size) == ("field", 24, 1)

    def test_clase_con_inicializadores(self):
        r = compilar(self.FUENTE)
        assert r.generador.layouts["A"].has_initializers
        assert not r.generador.layouts["B"].has_initializers


class TestReporte:
    def test_secciones_del_reporte(self):
        r = compilar(
            "class A { let x: integer = 1; } let a: A = new A(); "
            "function f(): integer { let c: integer = 0; function g(): integer { c = c + 1; return c; } return g(); }"
        )
        texto = render_codegen_report(r.generador)
        for seccion in ("Area estatica", "Layout de objetos", "Registros de activacion", "enlace de acceso"):
            assert seccion in texto
        assert "AR f.g" in texto and "up1.c" in texto

    def test_format_environments_muestra_offsets(self):
        r = compilar("let a: integer = 1; function f(p: integer) { }")
        texto = r.table.format_environments()
        assert "[global @a  <globales>+0  4B]" in texto
        assert "[param p  f+32  4B]" in texto
        assert "[label=f]" in texto


def test_activation_record_independiente():
    a = ActivationRecord("x", parent=None)
    p = a.add_param("n", INTEGER)
    l = a.add_local("n", INTEGER)  # mismo nombre -> n_2
    assert (p.name, p.offset) == ("n", 32)
    assert (l.name, l.offset) == ("n_2", 36)
    a.finalize(2)
    assert a.total_size == 56
