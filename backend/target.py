"""
Interfaz con el procesador destino. `backend/generador.py` decide QUE hay que
hacer (usando los descriptores de registros); una subclase de `Target` sabe
COMO se escribe en su ensamblador: registros, convencion de llamada, marco y
runtime. Hay dos: `backend/mips.py` (MIPS32, para MARS y SPIM) y
`backend/aarch64.py` (ARMv8, nativo en la Raspberry Pi 4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

ERR_INDICE = "__rt_err_index"
ERR_DIVISION = "__rt_err_div"
ERR_NULL = "__rt_err_null"


def texto_double(valor: str) -> str:
    """Literal de `.double` que aceptan MARS, SPIM y `as`: siempre con punto
    decimal (`1e+16` se escribe `1.0e+16`)."""
    mantisa, separador, exponente = valor.partition("e")
    if "." not in mantisa:
        mantisa += ".0"
    return f"{mantisa}{separador}{exponente}"


@dataclass
class MarcoFuncion:
    """Dimensiones finales del marco de una funcion.

    `tamanio` cubre el AR de la fase 2 mas los manejadores de `try` y los
    registros guardados; `salientes` es la zona de argumentos por pila que hay
    debajo, donde apunta el stack pointer."""

    tamanio_ar: int
    tamanio: int
    salientes: int
    guardados: list[tuple[str, int]] = field(default_factory=list)  # (registro, offset)
    en_heap: bool = False
    usa_enlace: bool = False


class Target:
    nombre = ""
    palabra = 0  # bytes de una referencia
    alineacion_pila = 8
    tamanio_manejador = 0  # bytes de un registro de `try`
    offset_valor_retorno = 24  # ranura `return_value` del AR
    offset_elementos = 8  # los elementos de una lista van tras su longitud

    # Registros (los fijan las subclases)
    temporales: list[str] = []  # los destruye una llamada
    guardados: list[str] = []  # los preserva quien es llamado
    flotantes: list[str] = []  # los destruye una llamada
    reserva_guardados = 2  # registros guardados que se dejan a getReg
    reserva_temporales = 3
    scratch0 = scratch1 = fscratch0 = ""
    zero = fp = sp = global_base = enlace = retorno = retorno_flotante = ""

    def __init__(self) -> None:
        self.lineas: list[str] = []
        self._etiquetas_locales = 0

    # --- salida ---------------------------------------------------------

    def emit(self, texto: str) -> None:
        self.lineas.append("    " + texto)

    def extender(self, lineas: list[str]) -> None:
        self.lineas.extend(lineas)

    def capturar(self, funcion) -> list[str]:
        """Ejecuta `funcion` y devuelve lo que emitio sin dejarlo en la salida
        (el prologo se escribe despues: depende de lo que use el cuerpo)."""
        guardadas, self.lineas = self.lineas, []
        funcion()
        capturadas, self.lineas = self.lineas, guardadas
        return capturadas

    def label(self, nombre: str) -> None:
        self.lineas.append(f"{nombre}:")

    def etiqueta_local(self) -> str:
        self._etiquetas_locales += 1
        return f"__loc_{self._etiquetas_locales}"

    def total_lineas(self) -> int:
        return len(self.lineas)

    def texto(self) -> str:
        return "\n".join(self.lineas) + "\n"

    # --- convencion de llamada ------------------------------------------

    def registro_argumento(self, posicion: int, kind: str) -> str | None:
        """Registro del argumento `posicion`; None si viaja por la pila."""
        raise NotImplementedError

    def registro_argumento_runtime(self, posicion: int, kind: str) -> str | None:
        return self.registro_argumento(posicion, kind)

    def argumento_entrante(self, marco: MarcoFuncion, posicion: int) -> tuple[str, int]:
        """(base, offset) de un argumento que llego por la pila."""
        raise NotImplementedError

    # Las demas primitivas (load, store, li, la, mov, prologo, epilogo, ...)
    # las define cada procesador; el contrato de cada una esta en backend/mips.py.
