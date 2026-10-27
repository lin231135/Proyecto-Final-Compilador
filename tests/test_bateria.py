"""
Parametriza pruebas/runner.ejecutar_bateria() con pytest: un test por
archivo .cps de la bateria, mas los 2 chequeos dedicados de pruebas/demo/.
"""

import pytest

from core.errors import CATEGORIAS
from driver import analizar_archivo
from pruebas.runner import RAIZ, ejecutar_bateria

RESULTADOS = ejecutar_bateria()


@pytest.mark.parametrize(
    "resultado",
    RESULTADOS,
    ids=[str(r.archivo.relative_to(RAIZ)) for r in RESULTADOS],
)
def test_bateria(resultado):
    assert resultado.paso, resultado.razon


def test_bateria_no_esta_vacia():
    assert len(RESULTADOS) >= 95


def test_demo_programa_completo_sin_errores():
    resultado = analizar_archivo(RAIZ / "demo" / "programa_completo.cps")
    assert resultado.ok, [str(e) for e in resultado.errores]


def test_demo_programa_completo_genera_tac_sin_fugas():
    resultado = analizar_archivo(RAIZ / "demo" / "programa_completo.cps")
    assert resultado.tac is not None
    assert resultado.generador.temp_leaks == 0


def test_bateria_cubre_casos_validos_e_invalidos_de_tac():
    tac = [r for r in RESULTADOS if r.archivo.parent.parent.name.startswith("tac_")]
    assert sum(r.es_valido for r in tac) >= 30
    assert sum(not r.es_valido for r in tac) >= 10


def test_demo_programa_errores_una_por_categoria():
    resultado = analizar_archivo(RAIZ / "demo" / "programa_errores.cps")
    categorias = [e.category for e in resultado.errores]
    assert sorted(categorias) == sorted(CATEGORIAS), [str(e) for e in resultado.errores]
