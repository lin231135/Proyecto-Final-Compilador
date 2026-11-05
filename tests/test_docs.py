"""
Los ejemplos de docs/Lenguaje_Intermedio_TAC.md (pares ```cps / ```tac) deben
ser exactamente lo que genera el compilador: si cambia el formato del TAC y
no se actualiza el documento, esta prueba falla.
"""

import re
from pathlib import Path

import pytest

from driver import analizar

DOC = Path(__file__).resolve().parent.parent / "docs" / "Lenguaje_Intermedio_TAC.md"
_PARES = re.compile(r"```cps\n(.*?)\n```\s*```tac\n(.*?)\n```", re.S)


def ejemplos():
    return _PARES.findall(DOC.read_text(encoding="utf-8"))


def test_el_documento_tiene_ejemplos_de_cada_construccion():
    assert len(ejemplos()) >= 15


@pytest.mark.parametrize("fuente,esperado", ejemplos(), ids=lambda v: v.splitlines()[0][:40] if isinstance(v, str) else None)
def test_ejemplo_del_documento_coincide_con_el_compilador(fuente, esperado):
    r = analizar(fuente)
    assert r.ok, [str(e) for e in r.errores]
    assert r.tac.render().rstrip() == esperado.rstrip()


DOC_SIMBOLOS = DOC.parent / "Tabla de Simbolos.md"
DOC_GENERACION = DOC.parent / "Generacion_Codigo.md"


def test_ejemplo_de_ensamblador_coincide_con_el_compilador():
    from backend import generar_ensamblador

    texto = DOC_GENERACION.read_text(encoding="utf-8")
    m = re.search(r"```cps\n([^`]*?)\n```\s*```mips\n(.*?)\n```", texto, re.S)
    assert m, "falta el ejemplo ```cps/```mips en Generacion_Codigo.md"
    ensamblado = generar_ensamblador(analizar(m.group(1)))
    programa = ensamblado.codigo.splitlines()[: ensamblado.lineas_programa]
    assert "\n".join(programa) == m.group(2)


def test_reporte_de_registros_del_documento_coincide_con_el_compilador():
    from backend import generar_ensamblador

    texto = DOC_GENERACION.read_text(encoding="utf-8")
    fuente = re.search(r"```cps\n([^`]*?)\n```\s*```mips", texto, re.S).group(1)
    reporte = re.search(r"```regs\n(.*?)\n```", texto, re.S).group(1)
    assert generar_ensamblador(analizar(fuente)).reporte() == reporte


def test_reporte_de_simbolos_del_documento_coincide_con_el_compilador():
    from codegen.report import render_codegen_report, render_symbols

    m = re.search(r"```cps\n(.*?)\n```\s*```symbols\n(.*?)\n```", DOC_SIMBOLOS.read_text(encoding="utf-8"), re.S)
    assert m, "falta el ejemplo ```cps/```symbols en Tabla de Simbolos.md"
    r = analizar(m.group(1))
    assert r.ok
    esperado = render_symbols(r.table) + "\n\n" + render_codegen_report(r.generador)
    assert esperado.rstrip() == m.group(2).rstrip()
