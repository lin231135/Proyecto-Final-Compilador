"""Utilidades para las pruebas del generador de TAC."""

from __future__ import annotations

from driver import Resultado, analizar


def compilar(fuente: str) -> Resultado:
    """Compila `fuente` y exige que no haya errores (ni internos)."""
    r = analizar(fuente)
    assert not r.errores, [str(e) for e in r.errores]
    assert not r.error_interno, r.error_interno
    assert r.tac is not None
    return r


def tac(fuente: str, funcion: str = "main") -> list[str]:
    """Instrucciones (texto, sin sangria) de una funcion del TAC generado."""
    return compilar(fuente).tac.function(funcion).lines()
