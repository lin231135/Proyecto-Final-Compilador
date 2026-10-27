"""
Ejecuta la bateria de archivos .cps bajo pruebas/<categoria>/{validos,invalidos}/.

Lo usan tests/test_bateria.py (via pytest) y el boton "Correr bateria" del
IDE.

Cabecera de cada archivo (comentarios `//` al inicio):
  // @caso: descripcion                      (obligatoria)
  // @error: categoria                       (invalidos; 1 o mas)
  // @salida: a | b | c                      (validos: salida esperada al EJECUTAR el TAC)
  // @contiene: texto                        (validos: el TAC contiene ese texto; repetible)
  // @no_contiene: texto                     (validos: el TAC NO lo contiene; repetible)
  // @max_temporales: N                      (validos: ninguna funcion usa mas de N temporales)

  - validos/   -> 0 errores, se genera TAC sin fugas de temporales y se
                  cumplen todas las directivas @salida/@contiene/...
  - invalidos/ -> >= 1 error, TODAS las categorias de @error: aparecen, y NO
                  se genera TAC (el generador solo corre sin errores).

`pruebas/demo/*.cps` queda fuera de `ejecutar_bateria()` a proposito: es
material de presentacion (ver tests/test_bateria.py).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# permite `python pruebas/runner.py` desde la raiz del repo
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codegen.interpreter import ejecutar
from driver import analizar_archivo

RAIZ = Path(__file__).parent

@dataclass
class ResultadoPrueba:
    archivo: Path
    es_valido: bool  # True si esta bajo .../validos/
    caso: str
    categorias_esperadas: list[str] = field(default_factory=list)
    paso: bool = False
    razon: str = ""

    def __str__(self) -> str:
        estado = "PASA" if self.paso else "FALLA"
        return f"[{estado}] {self.archivo.relative_to(RAIZ)} - {self.caso}"


@dataclass
class Cabecera:
    caso: str = ""
    errores: list[str] = field(default_factory=list)
    salida: list[str] | None = None
    contiene: list[str] = field(default_factory=list)
    no_contiene: list[str] = field(default_factory=list)
    max_temporales: int | None = None


_RE_DIRECTIVA = re.compile(r"^\s*//\s*@(\w+):\s*(.*?)\s*$")


def _leer_cabecera(ruta: Path) -> Cabecera:
    cab = Cabecera()
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        m = _RE_DIRECTIVA.match(linea)
        if m:
            clave, valor = m.groups()
            if clave == "caso":
                cab.caso = valor
            elif clave == "error":
                cab.errores.append(valor.split()[0])
            elif clave == "salida":
                cab.salida = [x.strip() for x in valor.split("|")] if valor else []
            elif clave == "contiene":
                cab.contiene.append(valor)
            elif clave == "no_contiene":
                cab.no_contiene.append(valor)
            elif clave == "max_temporales":
                cab.max_temporales = int(valor)
            continue
        if linea.strip() and not linea.strip().startswith("//"):
            break  # termino la cabecera de comentarios
    return cab


def _evaluar(ruta: Path) -> ResultadoPrueba:
    es_valido = ruta.parent.name == "validos"
    cab = _leer_cabecera(ruta)
    resultado = analizar_archivo(ruta)

    def res(paso: bool, razon: str = "") -> ResultadoPrueba:
        return ResultadoPrueba(ruta, es_valido, cab.caso, cab.errores, paso, razon)

    if es_valido:
        if not resultado.ok:
            return res(False, f"se esperaban 0 errores, hubo {len(resultado.errores)}: "
                              f"{[str(e) for e in resultado.errores]}")
        if resultado.error_interno:
            return res(False, f"error interno del generador: {resultado.error_interno}")
        if resultado.tac is None:
            return res(False, "no se genero TAC")
        if resultado.generador.temp_leaks:
            return res(False, f"{resultado.generador.temp_leaks} temporal(es) sin liberar al final de una sentencia")
        texto = resultado.tac.render()
        for frag in cab.contiene:
            if frag not in texto:
                return res(False, f"el TAC no contiene {frag!r}")
        for frag in cab.no_contiene:
            if frag in texto:
                return res(False, f"el TAC contiene {frag!r} y no deberia")
        if cab.max_temporales is not None:
            peor = max(f.temp_count for f in resultado.tac.functions)
            if peor > cab.max_temporales:
                return res(False, f"se usaron {peor} temporales (maximo {cab.max_temporales})")
        if cab.salida is not None:
            try:
                obtenida = ejecutar(resultado)
            except Exception as e:  # noqa: BLE001 - se reporta como fallo de la prueba
                return res(False, f"la ejecucion del TAC fallo: {e!r}")
            if obtenida != cab.salida:
                return res(False, f"salida {obtenida} != esperada {cab.salida}")
        return res(True)

    # invalidos/
    if not resultado.errores:
        return res(False, "se esperaba >=1 error, hubo 0")
    if resultado.tac is not None:
        return res(False, "hubo errores pero igual se genero TAC")
    obtenidas = {e.category for e in resultado.errores}
    faltantes = [c for c in cab.errores if c not in obtenidas]
    if faltantes:
        return res(False, f"faltaron las categorias {faltantes} (se obtuvieron {sorted(obtenidas)})")
    return res(True)


def listar_archivos() -> list[Path]:
    """Todos los .cps de la bateria (validos + invalidos), sin pruebas/demo/."""
    return sorted(RAIZ.glob("*/validos/*.cps")) + sorted(RAIZ.glob("*/invalidos/*.cps"))


def ejecutar_bateria() -> list[ResultadoPrueba]:
    return [_evaluar(ruta) for ruta in listar_archivos()]


if __name__ == "__main__":
    resultados = ejecutar_bateria()
    fallos = [r for r in resultados if not r.paso]
    print(f"{len(resultados) - len(fallos)}/{len(resultados)} pasaron")
    for r in fallos:
        print(f"{r}: {r.razon}")
