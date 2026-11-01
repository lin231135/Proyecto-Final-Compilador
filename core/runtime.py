"""
Contrato del entorno de ejecucion, comun al simulador de TAC y a los dos
back-ends (MIPS32 y AArch64). Las tres formas de ejecutar un programa deben
imprimir exactamente lo mismo: la bateria de pruebas compara sus salidas.

  - `integer` es un entero con signo de 32 bits que da la vuelta al
    desbordarse; `/` trunca hacia cero y `%` lleva el signo del dividendo
    (es lo que hacen `div` en MIPS y `sdiv` en ARM).
  - `float` es un double IEEE-754. Se imprime con hasta 6 decimales, sin ceros
    de sobra y con al menos un decimal (`formato_float`).
  - Los errores de ejecucion llevan un mensaje fijo que recibe `catch`.
"""

from __future__ import annotations

MSG_INDICE = "indice fuera de rango"
MSG_DIVISION = "division entre cero"
MSG_NULL = "acceso a null"
PREFIJO_ERROR = "Error de ejecucion: "

ENTERO_MIN = -(2**31)
ENTERO_MAX = 2**31 - 1

# Limites de la conversion de un double a texto (ver `formato_float`).
FLOAT_MEDIO_ULTIMO_DECIMAL = 0.0000005
FLOAT_LIMITE_ENTERO = 2147483648.0  # a partir de aqui no cabe en 32 bits
FLOAT_LIMITE_IMPRIMIBLE = 2e18  # a partir de aqui se imprime `inf`


def envolver_entero(valor: int) -> int:
    """Reduce `valor` al rango de un entero con signo de 32 bits."""
    return (valor + 2**31) % 2**32 - 2**31


def dividir_enteros(a: int, b: int) -> int:
    """Division truncada hacia cero (Python redondea hacia menos infinito)."""
    cociente = abs(a) // abs(b)
    return cociente if (a < 0) == (b < 0) else -cociente


def residuo_enteros(a: int, b: int) -> int:
    return a - b * dividir_enteros(a, b)


def formato_float(x: float) -> str:
    """Mismo algoritmo, operacion por operacion, que `__rt_print_float` en
    los runtimes de ensamblador: asi la aritmetica IEEE da el mismo resultado."""
    if x != x:
        return "nan"
    signo = ""
    if x < 0:
        signo, x = "-", -x
    x = x + FLOAT_MEDIO_ULTIMO_DECIMAL
    if x >= FLOAT_LIMITE_IMPRIMIBLE:
        return signo + "inf"
    if x >= FLOAT_LIMITE_ENTERO:
        alto = int(x / 1e9)
        bajo = max(int(x - alto * 1e9), 0)
        return f"{signo}{alto}{bajo:09d}.0"
    entero = int(x)
    fraccion = int((x - entero) * 1e6)
    decimales = f"{fraccion:06d}".rstrip("0") or "0"
    return f"{signo}{entero}.{decimales}"
