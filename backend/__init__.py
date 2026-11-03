"""
Generacion de codigo final: TAC -> ensamblador.

    from backend import generar_ensamblador
    ensamblado = generar_ensamblador(resultado)              # MIPS32
    ensamblado = generar_ensamblador(resultado, "arm64")     # AArch64 (Raspberry Pi 4)
"""

from __future__ import annotations

from backend.generador import BackendError, Ensamblado, generar_programa

TARGETS = ("mips", "arm64")


def generar_ensamblador(resultado, target: str = "mips") -> Ensamblado:
    """Traduce el TAC de `resultado` (de `driver.analizar`, sin errores)."""
    if target == "mips":
        from backend.mips import MIPS

        return generar_programa(resultado, MIPS())
    if target == "arm64":
        from backend.aarch64 import AArch64

        return generar_programa(resultado, AArch64())
    raise BackendError(f"procesador desconocido: {target} (use {' o '.join(TARGETS)})")


__all__ = ["BackendError", "Ensamblado", "TARGETS", "generar_ensamblador"]
