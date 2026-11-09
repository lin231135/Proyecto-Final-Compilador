"""
Compara el simulador de MIPSTATION 3000 (JavaScript) con el simulador interno
del compilador (Python) sobre toda la bateria.

    python simulador_retro/verificar.py

Compila a MIPS cada programa valido de pruebas/ (y los de pruebas/demo), lo
ejecuta en los dos simuladores y exige la misma salida y el mismo codigo de
salida. Necesita Node.js en el PATH.

Son dos implementaciones independientes: si coinciden, es poco probable que las
dos tengan el mismo error. Aun asi no reemplaza la prueba en MARS o SPIM.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

CARPETA = pathlib.Path(__file__).resolve().parent
RAIZ = CARPETA.parent
sys.path.insert(0, str(RAIZ))

from backend import BackendError, generar_ensamblador  # noqa: E402
from driver import analizar_archivo  # noqa: E402
from simulador.mips import ErrorSimulacion, simular  # noqa: E402

LIMITE = 50_000_000  # instrucciones, igual que el simulador interno


def programas() -> list[pathlib.Path]:
    validos = sorted((RAIZ / "pruebas").glob("*/validos/*.cps"))
    return validos + sorted((RAIZ / "pruebas" / "demo").glob("*.cps"))


def main() -> int:
    if shutil.which("node") is None:
        print("Se necesita Node.js (https://nodejs.org) para correr el simulador de JavaScript.")
        return 2
    casos: dict[str, tuple[pathlib.Path, str | None, int | None]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for n, ruta in enumerate(programas()):
            resultado = analizar_archivo(ruta)
            if not resultado.ok or resultado.tac is None:
                continue
            try:
                codigo = generar_ensamblador(resultado, "mips").codigo
            except BackendError:
                continue
            asm = pathlib.Path(tmp) / f"p{n}.asm"
            asm.write_text(codigo, encoding="utf-8", newline="\n")
            try:
                r = simular(codigo, LIMITE, estricto=False)
                casos[str(asm)] = (ruta, r.salida, r.codigo_salida)
            except ErrorSimulacion as e:
                casos[str(asm)] = (ruta, None, str(e))

        proceso = subprocess.run(
            ["node", str(CARPETA / "probar.js"), "--json", f"--max={LIMITE}", *casos],
            capture_output=True, text=True, encoding="utf-8",
        )
        if proceso.returncode != 0:
            print(proceso.stderr)
            return 2
        js = json.loads(proceso.stdout)

    fallos = 0
    instrucciones = 0
    milisegundos = 0.0
    for asm, (ruta, salida, codigo) in casos.items():
        r = js[asm]
        nombre = ruta.relative_to(RAIZ).as_posix()
        if salida is None:
            # Python no termino o fallo: el JS tambien debe fallar.
            if r["ok"]:
                fallos += 1
                print(f"FALLO {nombre}: Python fallo ({codigo}) y JS no")
            continue
        if not r["ok"]:
            fallos += 1
            print(f"FALLO {nombre}: el simulador JS dio error: {r['error']}")
        elif (r["salida"] != salida or r["codigo"] != codigo):
            fallos += 1
            print(f"FALLO {nombre}: salidas distintas")
            print(f"   Python ({codigo}): {salida[:300]!r}")
            print(f"   JS     ({r['codigo']}): {r['salida'][:300]!r}")
        else:
            instrucciones += r["instrucciones"]
            milisegundos += r["ms"]
    total = len(casos)
    print(f"{total - fallos}/{total} programas con la misma salida en los dos simuladores")
    if milisegundos:
        print(f"Simulador JS: {instrucciones:,} instrucciones en {milisegundos / 1000:.2f} s "
              f"({instrucciones / milisegundos / 1000:.1f} M instr/s)")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
