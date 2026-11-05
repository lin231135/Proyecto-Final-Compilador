#!/usr/bin/env bash
# Prueba el compilador en una Raspberry Pi 4. Desde la raiz del repositorio:
#
#     bash scripts/probar_en_raspberry.sh
#
# Corre toda la bateria ejecutando el ensamblador en el procesador real (con
# Raspberry Pi OS de 64 bits) y, si SPIM esta instalado, tambien el codigo MIPS.
set -u
cd "$(dirname "$0")/.."

maquina="$(uname -m)"
echo "== Equipo: $(uname -s) $maquina"

if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    echo "Se necesita Python 3.11 o superior (Raspberry Pi OS Bookworm lo trae): $(python3 --version)"
    exit 1
fi

if [ ! -d .venv-pi ]; then
    echo "== Creando el entorno de Python"
    python3 -m venv .venv-pi || exit 1
fi
# shellcheck disable=SC1091
. .venv-pi/bin/activate
pip install --quiet -r requirements-pi.txt || exit 1

fallo=0

if [ "$maquina" = "aarch64" ]; then
    for herramienta in as ld; do
        if ! command -v "$herramienta" >/dev/null; then
            echo "Falta $herramienta: sudo apt install binutils"
            exit 1
        fi
    done
    echo "== Bateria con AArch64 nativo (as + ld + ejecucion directa)"
    python pruebas/runner.py --simulador nativo || fallo=1
else
    echo "== Este sistema no es de 64 bits ($maquina): AArch64 no se puede ejecutar aqui."
    echo "   Con Raspberry Pi OS de 32 bits use el codigo MIPS con SPIM o MARS."
fi

if command -v spim >/dev/null; then
    echo "== Bateria con MIPS en SPIM"
    python pruebas/runner.py --simulador spim || fallo=1
else
    echo "== SPIM no esta instalado; se omite (sudo apt install spim)"
fi

echo "== Pruebas con los simuladores internos"
python -m pytest -q || fallo=1

if [ "$fallo" -eq 0 ]; then
    echo "== Todo paso"
else
    echo "== Hubo fallos: revise la salida anterior"
fi
exit "$fallo"
