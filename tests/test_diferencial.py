"""
Pruebas diferenciales: programas aleatorios (reproducibles) deben imprimir lo
mismo en el simulador de TAC, en MIPS y en AArch64. Ademas, una prueba de
mutacion comprueba que esta comparacion de verdad detecta errores del
generador: si se rompe a proposito el derrame de registros, debe fallar.
"""

import pytest

import backend.regalloc as regalloc
from backend import generar_ensamblador
from codegen.interpreter import TACInterpreter
from driver import analizar
from simulador.ejecucion import ejecutar_codigo
from tests.generador_programas import programa_aleatorio

SEMILLAS = range(25)


def salida_tac(resultado) -> tuple[str, int]:
    interprete = TACInterpreter(resultado, 3_000_000)
    return "".join(linea + "\n" for linea in interprete.run()), interprete.codigo_salida


@pytest.mark.parametrize("semilla", SEMILLAS)
def test_tac_mips_y_arm_coinciden(semilla):
    fuente = programa_aleatorio(semilla)
    r = analizar(fuente)
    assert r.ok, [str(e) for e in r.errores]
    esperada, codigo = salida_tac(r)
    for target in ("mips", "arm64"):
        e = generar_ensamblador(r, target)
        resultado = ejecutar_codigo(e.codigo, target, "interno", 30_000_000)
        assert resultado.salida == esperada, f"{target} difiere (semilla {semilla})"
        assert resultado.codigo_salida == codigo


def test_el_generador_de_programas_es_reproducible():
    assert programa_aleatorio(5) == programa_aleatorio(5)
    assert programa_aleatorio(5) != programa_aleatorio(6)


def test_los_programas_generados_agotan_los_registros():
    derrames = 0
    for semilla in SEMILLAS:
        r = analizar(programa_aleatorio(semilla))
        derrames += sum(x.stats.derrames for x in generar_ensamblador(r).reportes)
    assert derrames > 100


def test_sin_derrames_el_programa_daria_otro_resultado(monkeypatch):
    """Mutacion: `getReg` desaloja sin guardar el valor en la pila."""
    monkeypatch.setattr(regalloc.Descriptores, "_desalojar", lambda self, r, bloque, k: self.olvidar(self.duenio[r]))
    distintos = 0
    for semilla in SEMILLAS:
        r = analizar(programa_aleatorio(semilla))
        esperada, _ = salida_tac(r)
        try:
            salida = ejecutar_codigo(generar_ensamblador(r).codigo, "mips", "interno", 30_000_000).salida
        except Exception:  # noqa: BLE001 - un fallo de simulacion tambien es una deteccion
            distintos += 1
            continue
        distintos += salida != esperada
    assert distintos > 0
