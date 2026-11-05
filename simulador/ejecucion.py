"""
Ejecuta el ensamblador generado. Cuatro medios, con la misma interfaz:

    interno  simuladores de esta carpeta (Python puro, siempre disponibles)
    mars     MARS 4.5 (`java -jar`); se busca en $MARS_JAR o tools/Mars4_5.jar
    spim     SPIM de linea de comandos (`sudo apt install spim`)
    nativo   solo AArch64: ensambla con `as`/`ld` y ejecuta en el procesador,
             es decir, en la Raspberry Pi 4

`auto` elige `nativo` para AArch64 si el equipo es ARM de 64 bits y `interno`
en los demas casos.
"""

from __future__ import annotations

import os
import pathlib
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MEDIOS = ("auto", "interno", "mars", "spim", "nativo")
TIEMPO_MAXIMO = 60  # segundos, para los medios externos
# Codigos de salida que se le piden a MARS (un programa solo usa 0 y 1).
MARS_ERROR_ENSAMBLADO = 2
MARS_ERROR_SIMULACION = 3


class ErrorEjecucionExterna(Exception):
    """El simulador o las herramientas no estan disponibles o fallaron."""


@dataclass
class Ejecucion:
    salida: str
    codigo_salida: int
    medio: str
    instrucciones: int | None = None
    pila_maxima: int | None = None


def es_arm64_nativo() -> bool:
    return platform.system() == "Linux" and platform.machine() in ("aarch64", "arm64")


def buscar_mars() -> pathlib.Path | None:
    candidatos = [os.environ.get("MARS_JAR"), RAIZ / "tools" / "Mars4_5.jar"]
    for candidato in candidatos:
        if candidato and pathlib.Path(candidato).is_file():
            return pathlib.Path(candidato)
    return None


def medios_disponibles(target: str) -> list[str]:
    disponibles = ["interno"]
    if target == "mips":
        if buscar_mars() is not None and shutil.which("java"):
            disponibles.append("mars")
        if shutil.which("spim"):
            disponibles.append("spim")
    elif es_arm64_nativo() and shutil.which("as") and shutil.which("ld"):
        disponibles.append("nativo")
    return disponibles


def _correr(comando: list[str], directorio: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            comando, cwd=directorio, capture_output=True, timeout=TIEMPO_MAXIMO, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError as e:
        raise ErrorEjecucionExterna(f"no se encontro {comando[0]}") from e
    except subprocess.TimeoutExpired as e:
        raise ErrorEjecucionExterna(f"{comando[0]} no termino en {TIEMPO_MAXIMO} s") from e


def _interno(codigo: str, target: str, max_instrucciones: int, estricto: bool) -> Ejecucion:
    if target == "mips":
        from simulador.mips import simular
    else:
        from simulador.aarch64 import simular
    r = simular(codigo, max_instrucciones, estricto)
    return Ejecucion(r.salida, r.codigo_salida, "interno", r.instrucciones, r.pila_maxima)


def _mars(codigo: str) -> Ejecucion:
    jar = buscar_mars()
    if jar is None:
        raise ErrorEjecucionExterna("no se encontro MARS: defina MARS_JAR o copie Mars4_5.jar en tools/")
    with tempfile.TemporaryDirectory() as directorio:
        ruta = pathlib.Path(directorio) / "programa.asm"
        ruta.write_text(codigo, encoding="utf-8", newline="\n")
        comando = ["java", "-jar", str(jar), "nc", "me", f"ae{MARS_ERROR_ENSAMBLADO}", f"se{MARS_ERROR_SIMULACION}"]
        r = _correr([*comando, "programa.asm"], directorio)
    if r.returncode == MARS_ERROR_ENSAMBLADO:
        raise ErrorEjecucionExterna(f"MARS no pudo ensamblar el programa:\n{r.stderr}")
    if r.returncode == MARS_ERROR_SIMULACION:
        raise ErrorEjecucionExterna(f"error de simulacion en MARS:\n{r.stderr}")
    return Ejecucion(r.stdout, r.returncode, "mars")


def _spim(codigo: str) -> Ejecucion:
    with tempfile.TemporaryDirectory() as directorio:
        ruta = pathlib.Path(directorio) / "programa.asm"
        ruta.write_text(codigo, encoding="utf-8", newline="\n")
        r = _correr(["spim", "-quiet", "-file", "programa.asm"], directorio)
    return Ejecucion(r.stdout, r.returncode, "spim")


def _nativo(codigo: str) -> Ejecucion:
    if not es_arm64_nativo():
        raise ErrorEjecucionExterna(
            f"este equipo es {platform.system()}/{platform.machine()}: el medio `nativo` necesita "
            "Linux de 64 bits en ARM (Raspberry Pi 4). En Raspberry Pi OS de 32 bits use MIPS con SPIM o MARS."
        )
    with tempfile.TemporaryDirectory() as directorio:
        ruta = pathlib.Path(directorio) / "programa.s"
        ruta.write_text(codigo, encoding="utf-8", newline="\n")
        for comando in (["as", "programa.s", "-o", "programa.o"], ["ld", "programa.o", "-o", "programa"]):
            r = _correr(comando, directorio)
            if r.returncode != 0:
                raise ErrorEjecucionExterna(f"fallo {comando[0]}:\n{r.stderr}")
        r = _correr(["./programa"], directorio)
    return Ejecucion(r.stdout, r.returncode, "nativo")


def ejecutar_codigo(
    codigo: str,
    target: str,
    medio: str = "auto",
    max_instrucciones: int = 50_000_000,
    estricto: bool = True,
) -> Ejecucion:
    """Ejecuta `codigo` (texto en ensamblador de `target`)."""
    if medio == "auto":
        medio = "nativo" if target == "arm64" and "nativo" in medios_disponibles(target) else "interno"
    if medio == "interno":
        return _interno(codigo, target, max_instrucciones, estricto)
    if medio in ("mars", "spim") and target != "mips":
        raise ErrorEjecucionExterna(f"{medio} ejecuta codigo MIPS, no {target}")
    if medio == "mars":
        return _mars(codigo)
    if medio == "spim":
        return _spim(codigo)
    if medio == "nativo":
        if target != "arm64":
            raise ErrorEjecucionExterna("el medio `nativo` ejecuta codigo arm64")
        return _nativo(codigo)
    raise ErrorEjecucionExterna(f"medio de ejecucion desconocido: {medio}")
