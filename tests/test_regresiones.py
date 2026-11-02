"""
Errores de las fases 1 y 2 que aparecieron al generar codigo real. Cada prueba
fija el comportamiento correcto del compilador y del simulador de TAC.
"""

import pytest

from codegen.interpreter import ejecutar
from codegen.tac import unescape
from core.runtime import dividir_enteros, envolver_entero, formato_float, residuo_enteros
from driver import analizar
from tests.helpers import compilar, tac


def salida(fuente: str) -> list[str]:
    return ejecutar(compilar(fuente))


# --- nombres --------------------------------------------------------------


def test_variable_llamada_como_un_temporal():
    fuente = "function f(): integer { let t1: integer = 1; return t1 + 2 * 3; } print(f());"
    assert salida(fuente) == ["7"]
    assert "t1_2" in " ".join(tac(fuente, "f"))


def test_parametro_llamado_como_un_temporal():
    assert salida("function f(t1: integer): integer { return t1 + 2 * 3; } print(f(1));") == ["7"]


def test_funcion_del_usuario_llamada_main():
    assert salida("function main(): integer { return 7; } print(main());") == ["7"]


def test_expresion_muy_anidada_no_rompe_el_compilador():
    fuente = "print(" + "(" * 100 + "1" + ")" * 100 + ");"
    assert salida(fuente) == ["1"]


# --- funciones anidadas en metodos ---------------------------------------


def test_funcion_anidada_en_metodo_se_puede_llamar():
    fuente = """
    class C { let v: integer = 2;
      function m(n: integer): integer {
        function doble(): integer { return n * this.v; }
        return doble();
      }
    }
    print(new C().m(4));
    """
    assert salida(fuente) == ["8"]


def test_dos_metodos_con_funciones_anidadas_del_mismo_nombre():
    fuente = """
    class C {
      function a(): integer { function x(): integer { return 1; } return x(); }
      function b(): integer { function x(): integer { return 2; } return x(); }
    }
    print(new C().a() + new C().b());
    """
    assert salida(fuente) == ["3"]


def test_constructor_anidado_no_es_un_constructor():
    r = analizar("class C { function m(): integer { function constructor(): integer { return 1; } return constructor(); } }")
    assert r.ok, [str(e) for e in r.errores]


# --- `let d = null` -------------------------------------------------------


def test_null_sigue_aceptando_clases_y_listas_distintas():
    r = analizar("class A {} let d = null; d = new A(); d = [1, 2];")
    assert r.ok


def test_null_anota_el_tipo_asignado_para_el_backend():
    assert salida("let d = null; d = [1, 2]; print(d);") == ["[1, 2]"]


# --- try ------------------------------------------------------------------


def test_return_en_try_desactiva_el_manejador():
    instrucciones = tac("function f(): integer { try { return 1; } catch (e) { return 2; } } print(f());", "f")
    assert instrucciones[:3] == ["try L1", "endtry", "return 1"]


def test_break_en_try_desactiva_el_manejador():
    fuente = 'let x: integer[] = [1]; while (true) { try { break; } catch (e) { print("mal"); } } print(x[5]);'
    assert salida(fuente) == ["Error de ejecucion: indice fuera de rango"]


def test_continue_cierra_solo_los_try_del_bucle():
    fuente = """
    let n: integer = 0;
    try {
      while (n < 2) {
        try { n = n + 1; continue; } catch (e) { print("mal"); }
      }
      let l: integer[] = [1];
      print(l[7]);
    } catch (e) { print(e); }
    """
    assert salida(fuente) == ["indice fuera de rango"]


# --- semantica del simulador de TAC --------------------------------------


@pytest.mark.parametrize("a,b,cociente,residuo", [(7, 2, 3, 1), (-7, 2, -3, -1), (7, -2, -3, 1), (-7, -2, 3, -1)])
def test_division_truncada(a, b, cociente, residuo):
    assert dividir_enteros(a, b) == cociente
    assert residuo_enteros(a, b) == residuo


@pytest.mark.parametrize(
    "valor,esperado", [(2**31, -(2**31)), (-(2**31) - 1, 2**31 - 1), (2**32, 0), (5, 5), (-5, -5)]
)
def test_envolver_entero(valor, esperado):
    assert envolver_entero(valor) == esperado


@pytest.mark.parametrize(
    "valor,texto",
    [
        (0.0, "0.0"),
        (1.0, "1.0"),
        (-2.5, "-2.5"),
        (0.1 + 0.2, "0.3"),
        (1 / 3, "0.333333"),
        (0.0000001, "0.0"),
        (0.9999999, "1.0"),
        (3000000000.0, "3000000000.0"),
        (1e19, "inf"),
        (float("nan"), "nan"),
    ],
)
def test_formato_float(valor, texto):
    assert formato_float(valor) == texto


def test_integer_se_convierte_a_float_al_asignar():
    assert salida("let f: float = 1; print(f);") == ["1.0"]


def test_operacion_mixta_usa_itof():
    assert "t1 = itof @a" in tac("let a: integer = 1; let b: float = 2.5; print(a + b);")


def test_literal_no_necesita_itof():
    assert not any("itof" in linea for linea in tac("let b: float = 1;"))


def test_ternario_mixto_es_float():
    assert salida("print(true ? 1 : 2.5);") == ["1.0"]


def test_float_en_lista_de_literales_enteros():
    assert salida("let a: float[] = [1, 2]; print(a[0] + 0.5);") == ["1.5"]


def test_objetos_se_comparan_por_identidad():
    assert salida("class A { let x: integer; } let a: A = new A(); print(a == new A()); print(a == a);") == [
        "false",
        "true",
    ]


def test_strings_se_comparan_por_contenido():
    assert salida('print("a" + "b" == "ab");') == ["true"]


def test_campo_sin_valor_vale_cero_segun_su_tipo():
    fuente = "class A { let n: integer; let f: float; let b: boolean; let s: string; } let a: A = new A();"
    assert salida(fuente + "print(a.n); print(a.f); print(a.b); print(a.s);") == ["0", "0.0", "false", "null"]


def test_local_sin_valor_vale_cero():
    assert salida("function f(): integer { let x: integer; return x; } print(f());") == ["0"]


def test_barra_escapada_seguida_de_n_no_es_salto_de_linea():
    assert unescape('"a\\\\nb"') == "a\\nb"
    assert unescape('"a\\nb"') == "a\nb"
    assert unescape('"\\t\\"\\\\"') == '\t"\\'


def test_print_de_lista_y_objeto():
    assert salida('class Foo { } print([1, 2]); print(["a"]); print(new Foo());') == ["[1, 2]", "[a]", "<Foo>"]


def test_error_sin_catch_detiene_el_programa():
    fuente = 'print("a"); print(1 / 0); print("b");'
    assert salida(fuente) == ["a", "Error de ejecucion: division entre cero"]


def test_acceso_a_null_se_puede_capturar():
    fuente = "class A { let x: integer; } let a: A = null; try { print(a.x); } catch (e) { print(e); }"
    assert salida(fuente) == ["acceso a null"]
