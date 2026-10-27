"""Asignacion y reciclaje de temporales."""

import pytest

from codegen.tac import TempManager, is_temp
from driver import analizar
from tests.helpers import compilar, tac


class TestTempManager:
    def test_acuna_en_orden(self):
        tm = TempManager()
        assert [tm.new_temp(), tm.new_temp(), tm.new_temp()] == ["t1", "t2", "t3"]
        assert tm.count == 3

    def test_reutiliza_el_libre_de_menor_numero(self):
        tm = TempManager()
        t1, t2, t3 = tm.new_temp(), tm.new_temp(), tm.new_temp()
        tm.free(t3)
        tm.free(t1)
        assert tm.new_temp() == "t1"
        assert tm.new_temp() == "t3"
        assert tm.new_temp() == "t4"  # ya no quedan libres
        assert tm.count == 4

    def test_free_ignora_lo_que_no_es_temporal(self):
        tm = TempManager()
        tm.new_temp()
        for x in ("x", "@g", "5", '"t1"', "up1.t1", None, "this"):
            tm.free(x)
        assert tm.new_temp() == "t2"  # t1 sigue vivo

    def test_free_es_idempotente(self):
        tm = TempManager()
        t = tm.new_temp()
        tm.free(t)
        tm.free(t)
        assert [tm.new_temp(), tm.new_temp()] == ["t1", "t2"]

    def test_release_all_informa_fugas(self):
        tm = TempManager()
        tm.new_temp()
        tm.new_temp()
        assert tm.release_all() == 2
        assert tm.release_all() == 0

    @pytest.mark.parametrize("s,esperado", [("t1", True), ("t12", True), ("x", False), ("t", False), ("t1x", False), ("@t1", False)])
    def test_is_temp(self, s, esperado):
        assert is_temp(s) is esperado


class TestReciclajeEnElGenerador:
    def test_operando_se_libera_antes_de_asignar_el_resultado(self):
        # t1 + t2 -> el resultado reutiliza t1
        assert tac("let a: integer = 2 * 3 + 4 * 5;") == ["t1 = 2 * 3", "t2 = 4 * 5", "@a = t1 + t2"]

    def test_expresion_larga_usa_pocos_temporales(self):
        # ((((1+2)+3)+4)+5)+6 es una cadena: un solo temporal
        r = compilar("let a: integer = 1 + 2 + 3 + 4 + 5 + 6;")
        assert r.tac.function("main").temp_count == 1

    def test_arbol_balanceado_necesita_log_n(self):
        # (a+b)*(c+d) -> 2 temporales
        r = compilar("let a: integer = 1; let b: integer = 2; let c: integer = (a + b) * (a - b);")
        assert r.tac.function("main").temp_count == 2

    def test_sentencias_reutilizan_los_mismos_nombres(self):
        r = compilar("let a: integer = 1; print(a + 1); print(a + 2); print(a + 3);")
        assert r.tac.function("main").temp_count == 1

    def test_argumentos_de_llamada_viven_hasta_el_param(self):
        fuente = "function f(a: integer, b: integer): integer { return a; } let r: integer = f(1 + 2, 3 * 4);"
        assert tac(fuente) == ["t1 = 1 + 2", "t2 = 3 * 4", "param t1", "param t2", "@r = call f, 2"]

    def test_valor_de_retorno_reusa_el_temporal_de_un_argumento(self):
        fuente = "function f(a: integer): integer { return a; } print(f(1 + 2));"
        assert tac(fuente) == ["t1 = 1 + 2", "param t1", "t1 = call f, 1", "param t1", "call print, 1"]

    def test_peephole_elimina_el_temporal_de_una_asignacion_directa(self):
        r = compilar("let a: integer = 3; let b: integer = 4; let x: integer; x = a + b;")
        assert "@x = @a + @b" in r.tac.function("main").lines()
        assert r.tac.function("main").temp_count == 0

    def test_temporales_vivos_durante_un_foreach_no_se_pisan(self):
        fuente = "let xs: integer[] = [1, 2]; let s: integer = 0; foreach (x in xs) { s = s + x * 2; }"
        t = tac(fuente)
        # indice y largo ocupan t1 y t2; el cuerpo usa t3
        assert "t3 = x * 2" in t

    @pytest.mark.parametrize(
        "fuente",
        [
            "let a: integer = 1; let b: boolean = a < 2 && a > 0 || a == 5;",
            "let a: integer = 1; let c: integer = a > 0 ? a + 1 : a * 2;",
            "function f(x: integer): integer { return x; } let r: integer = f(f(f(1) + 2) * 3);",
            "let xs: integer[] = [1 + 1, 2 * 2, 3]; let y: integer = xs[xs[0] - 1];",
            "class P { let v: integer = 1; function m(a: integer): integer { return a + this.v; } } "
            "let p: P = new P(); let z: integer = p.m(p.m(1) + 2);",
        ],
    )
    def test_ninguna_sentencia_deja_temporales_sin_liberar(self, fuente):
        r = compilar(fuente)
        assert r.generador.temp_leaks == 0


def test_temporales_distintos_ocupan_ranuras_en_el_ar():
    r = compilar("let a: integer = 1; print((a + 1) * (a + 2));")
    ar = next(a for a in r.generador.activation_records if a.name == "main")
    nombres = [s.name for s in ar.slots if s.kind == "temp"]
    assert nombres == ["t1", "t2"]
