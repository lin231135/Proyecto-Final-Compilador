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
  // @mips: texto                            (validos: el ensamblador MIPS contiene ese texto; repetible)
  // @no_mips: texto                         (validos: el ensamblador MIPS NO lo contiene; repetible)
  // @arm: texto                             (validos: el ensamblador AArch64 contiene ese texto; repetible)
  // @derrames: N                            (validos: getReg derrama a la pila al menos N veces)
  // @salvados: N                            (validos: al menos N valores se salvan antes de una llamada)
  // @codigo_salida: N                       (validos: codigo de salida esperado; por defecto 0)
  // @error_backend: texto                   (invalidos: el semantico lo acepta, pero la generacion
                                              de ensamblador lo rechaza con ese mensaje)

  - validos/   -> 0 errores, se genera TAC sin fugas de temporales y se
                  cumplen todas las directivas. Ademas se genera ensamblador
                  MIPS y AArch64, se ejecuta en los simuladores y su salida
                  debe ser identica a la del TAC y a @salida.
  - invalidos/ -> >= 1 error, TODAS las categorias de @error: aparecen, y NO
                  se genera TAC ni ensamblador (el generador solo corre sin
                  errores). Con @error_backend, el error lo da el back-end.

Por defecto el ensamblador se ejecuta en los simuladores internos. Para usar
un simulador real o el procesador de la Raspberry Pi:

  python pruebas/runner.py --simulador mars            (MIPS en MARS)
  python pruebas/runner.py --simulador spim            (MIPS en SPIM)
  python pruebas/runner.py --simulador nativo          (AArch64 en la Raspberry Pi 4)

`pruebas/demo/*.cps` queda fuera de `ejecutar_bateria()` a proposito: es
material de presentacion (ver tests/test_bateria.py).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# permite `python pruebas/runner.py` desde la raiz del repo
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import BackendError, generar_ensamblador
from codegen.interpreter import TACInterpreter
from driver import analizar_archivo
from simulador.aarch64 import ErrorEnsamblado as ErrorEnsambladoArm
from simulador.aarch64 import ErrorSimulacion as ErrorSimulacionArm
from simulador.ejecucion import ErrorEjecucionExterna, ejecutar_codigo
from simulador.mips import ErrorEnsamblado as ErrorEnsambladoMips
from simulador.mips import ErrorSimulacion as ErrorSimulacionMips

RAIZ = Path(__file__).parent
MAX_PASOS_TAC = 2_000_000
ERRORES_DE_EJECUCION = (
    ErrorSimulacionMips,
    ErrorEnsambladoMips,
    ErrorSimulacionArm,
    ErrorEnsambladoArm,
    ErrorEjecucionExterna,
)

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
    mips: list[str] = field(default_factory=list)
    no_mips: list[str] = field(default_factory=list)
    arm: list[str] = field(default_factory=list)
    derrames: int | None = None
    salvados: int | None = None
    codigo_salida: int = 0
    error_backend: str | None = None


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
            elif clave == "mips":
                cab.mips.append(valor)
            elif clave == "no_mips":
                cab.no_mips.append(valor)
            elif clave == "arm":
                cab.arm.append(valor)
            elif clave == "derrames":
                cab.derrames = int(valor)
            elif clave == "salvados":
                cab.salvados = int(valor)
            elif clave == "codigo_salida":
                cab.codigo_salida = int(valor)
            elif clave == "error_backend":
                cab.error_backend = valor
            continue
        if linea.strip() and not linea.strip().startswith("//"):
            break  # termino la cabecera de comentarios
    return cab


def _salida_del_tac(resultado) -> tuple[list[str] | None, int]:
    """Lo que imprime el programa segun el TAC; None si no termina."""
    interprete = TACInterpreter(resultado, MAX_PASOS_TAC)
    try:
        return interprete.run(), interprete.codigo_salida
    except RuntimeError:
        return None, 0


def _revisar_ensamblador(resultado, cab: Cabecera, target: str, medio: str, salida_tac, codigo_tac) -> str:
    """Genera y ejecuta el ensamblador. Devuelve el motivo del fallo o ""."""
    ensamblado = generar_ensamblador(resultado, target)
    if ensamblado.avisos:
        return f"avisos del back-end: {ensamblado.avisos}"
    if target == "mips":
        for frag in cab.mips:
            if frag not in ensamblado.codigo:
                return f"el ensamblador MIPS no contiene {frag!r}"
        for frag in cab.no_mips:
            if frag in ensamblado.codigo:
                return f"el ensamblador MIPS contiene {frag!r} y no deberia"
        if cab.derrames is not None:
            derrames = sum(r.stats.derrames for r in ensamblado.reportes)
            if derrames < cab.derrames:
                return f"se esperaban al menos {cab.derrames} derrames a la pila, hubo {derrames}"
        if cab.salvados is not None:
            salvados = sum(r.stats.salvados for r in ensamblado.reportes)
            if salvados < cab.salvados:
                return f"se esperaban al menos {cab.salvados} valores salvados, hubo {salvados}"
    else:
        for frag in cab.arm:
            if frag not in ensamblado.codigo:
                return f"el ensamblador AArch64 no contiene {frag!r}"
    if salida_tac is None:  # el programa no termina a proposito: solo se genera
        return ""
    ejecucion = ejecutar_codigo(ensamblado.codigo, target, medio)
    esperada = "".join(linea + "\n" for linea in salida_tac)
    if ejecucion.salida.rstrip() != esperada.rstrip():
        return f"salida en {target} {ejecucion.salida!r} != TAC {esperada!r}"
    if medio in ("interno", "nativo") and ejecucion.codigo_salida != codigo_tac:
        return f"codigo de salida en {target}: {ejecucion.codigo_salida}, se esperaba {codigo_tac}"
    return ""


def _evaluar(ruta: Path, medios: dict[str, str]) -> ResultadoPrueba:
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
        try:
            obtenida, codigo = _salida_del_tac(resultado)
        except Exception as e:  # noqa: BLE001 - se reporta como fallo de la prueba
            return res(False, f"la ejecucion del TAC fallo: {e!r}")
        if cab.salida is not None and obtenida != cab.salida:
            return res(False, f"salida {obtenida} != esperada {cab.salida}")
        if obtenida is not None and codigo != cab.codigo_salida:
            return res(False, f"codigo de salida {codigo}, se esperaba {cab.codigo_salida}")
        for target, medio in medios.items():
            try:
                motivo = _revisar_ensamblador(resultado, cab, target, medio, obtenida, codigo)
            except BackendError as e:
                return res(False, f"el back-end {target} rechazo el programa: {e}")
            except ERRORES_DE_EJECUCION as e:
                return res(False, f"la ejecucion en {target} fallo: {e}")
            if motivo:
                return res(False, motivo)
        return res(True)

    # invalidos/
    if cab.error_backend is not None:
        if resultado.errores:
            return res(False, f"el error debe darlo el back-end, hubo {[str(e) for e in resultado.errores]}")
        for target in medios:
            try:
                generar_ensamblador(resultado, target)
            except BackendError as e:
                if cab.error_backend not in str(e):
                    return res(False, f"el error del back-end no contiene {cab.error_backend!r}: {e}")
            else:
                return res(False, f"se esperaba un error del back-end {target}")
        return res(True)
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


def ejecutar_bateria(medios: dict[str, str] | None = None) -> list[ResultadoPrueba]:
    """`medios`: procesador -> donde ejecutar su ensamblador."""
    medios = medios if medios is not None else {"mips": "interno", "arm64": "interno"}
    return [_evaluar(ruta, medios) for ruta in listar_archivos()]


def _medios_de_linea_de_comandos(simulador: str) -> dict[str, str]:
    if simulador in ("mars", "spim"):
        return {"mips": simulador}
    if simulador == "nativo":
        return {"arm64": "nativo"}
    return {"mips": "interno", "arm64": "interno"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bateria de pruebas de Compiscript")
    parser.add_argument("--simulador", choices=["interno", "mars", "spim", "nativo"], default="interno")
    args = parser.parse_args()
    resultados = ejecutar_bateria(_medios_de_linea_de_comandos(args.simulador))
    fallos = [r for r in resultados if not r.paso]
    print(f"{len(resultados) - len(fallos)}/{len(resultados)} pasaron")
    for r in fallos:
        print(f"{r}: {r.razon}")
    sys.exit(1 if fallos else 0)
