"""
Asignacion de registros: descriptores y `getReg` (Dragon Book 8.6).

Dos niveles, pensados para usar cada tipo de registro en lo que le corresponde:

1. Variables de larga vida (`elegir_variables_en_registro`): antes de generar
   una funcion, sus variables mas usadas (ponderadas por la profundidad de
   bucle) se fijan en un registro guardado para toda la funcion. En una funcion
   hoja se usan registros temporales, que no hay que guardar.

2. Valores de un bloque basico (`Descriptores.get_reg`): el resto de valores y
   los temporales del TAC viven en registros solo dentro del bloque, siguiendo
   el algoritmo clasico con un descriptor de registros (`duenio`) y un
   descriptor de direcciones (`registro_de` + `sucios`):

     a. si el valor ya esta en un registro, se usa ese;
     b. si hay un registro libre, se toma: un guardado si el valor debe
        sobrevivir a una llamada del bloque, si no uno temporal;
     c. si no, se desaloja el registro cuyo valor se vuelve a usar mas tarde
        (Belady, con la informacion next-use). Si esta sucio y sigue vivo se
        guarda antes en su ranura de la pila: ese es el derrame (spill).

Toda variable y temporal tiene ranura en el registro de activacion, asi que
siempre hay a donde derramar. Al terminar el bloque se escriben los valores
sucios que siguen vivos (liveness global) y los descriptores se vacian.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.cfg import INFINITO, Bloque


@dataclass
class EstadisticasRegistros:
    llamadas_get_reg: int = 0
    reutilizados: int = 0  # (a) el valor ya estaba en un registro
    libres: int = 0  # (b) se tomo un registro libre
    desalojos: int = 0  # (c) hubo que desocupar un registro
    derrames: int = 0  # desalojos que escribieron en la pila
    salvados: int = 0  # valores escritos en la pila antes de una llamada

    def sumar(self, otras: "EstadisticasRegistros") -> None:
        self.llamadas_get_reg += otras.llamadas_get_reg
        self.reutilizados += otras.reutilizados
        self.libres += otras.libres
        self.desalojos += otras.desalojos
        self.derrames += otras.derrames
        self.salvados += otras.salvados


class Descriptores:
    """Estado de los registros durante la traduccion de una funcion.

    `temporales`/`guardados` son los registros enteros disponibles para esta
    funcion (ya sin los fijados a variables) y `flotantes` los de punto
    flotante. `guardar(nombre, registro)` escribe un valor en su ranura.
    """

    def __init__(self, temporales: list[str], guardados: list[str], flotantes: list[str], guardar) -> None:
        self.temporales = temporales
        self.guardados = guardados
        self.flotantes = flotantes
        self._guardar = guardar
        self.duenio: dict[str, str | None] = {}  # registro -> nombre que contiene
        self.registro_de: dict[str, str] = {}  # nombre -> registro
        self.sucios: set[str] = set()  # el valor del registro no esta en memoria
        self.fijados: set[str] = set()  # operandos de la instruccion actual
        self.guardados_usados: set[str] = set()
        self.stats = EstadisticasRegistros()

    # --- consultas ------------------------------------------------------

    def en_registro(self, nombre: str) -> str | None:
        return self.registro_de.get(nombre)

    def _es_libre(self, r: str) -> bool:
        return self.duenio.get(r) is None and r not in self.fijados

    # --- getReg ---------------------------------------------------------

    def get_reg(self, flotante: bool, cruza_llamada: bool, bloque: Bloque, k: int) -> str:
        """Devuelve un registro desocupado para un valor nuevo; el llamador lo
        ocupa con `ocupar`. `cruza_llamada`: el valor vive tras una llamada."""
        self.stats.llamadas_get_reg += 1
        if flotante:
            candidatos = self.flotantes
        elif cruza_llamada:
            candidatos = self.guardados + self.temporales
        else:
            candidatos = self.temporales + self.guardados

        for r in candidatos:
            if self._es_libre(r):
                self.stats.libres += 1
                self._tomar(r)
                return r

        victima = max(
            (r for r in candidatos if r not in self.fijados),
            key=lambda r: self._proximo_uso(self.duenio[r], bloque, k),
        )
        self.stats.desalojos += 1
        self._desalojar(victima, bloque, k)
        self._tomar(victima)
        return victima

    def _tomar(self, r: str) -> None:
        self.fijados.add(r)
        if r in self.guardados:
            self.guardados_usados.add(r)

    @staticmethod
    def _proximo_uso(nombre: str | None, bloque: Bloque, k: int) -> int:
        """Distancia al proximo uso. Un valor muerto es la mejor victima."""
        proximo = bloque.next_use[k].get(nombre) if nombre is not None else None
        return INFINITO + 1 if proximo is None else proximo

    def _desalojar(self, r: str, bloque: Bloque, k: int) -> None:
        nombre = self.duenio[r]
        if nombre is not None and nombre in self.sucios and nombre in bloque.next_use[k]:
            self.stats.derrames += 1
            self._guardar(nombre, r)
        self.olvidar(nombre)

    # --- actualizacion de los descriptores -----------------------------

    def ocupar(self, r: str, nombre: str, sucio: bool) -> None:
        self.olvidar(nombre)
        self.duenio[r] = nombre
        self.registro_de[nombre] = r
        if sucio:
            self.sucios.add(nombre)
        else:
            self.sucios.discard(nombre)

    def olvidar(self, nombre: str | None) -> None:
        """El registro de `nombre` queda libre y su valor deja de seguirse."""
        if nombre is None:
            return
        r = self.registro_de.pop(nombre, None)
        if r is not None:
            self.duenio[r] = None
        self.sucios.discard(nombre)

    def limpiar_nombre(self, nombre: str) -> None:
        self.sucios.discard(nombre)

    def fijar(self, r: str) -> None:
        self.fijados.add(r)

    def soltar_fijados(self) -> None:
        self.fijados.clear()

    def liberar_muertos(self, vivos: dict[str, int]) -> None:
        """Tras una instruccion, libera lo que ya no se vuelve a usar."""
        for nombre in [n for n in self.registro_de if n not in vivos]:
            self.olvidar(nombre)

    def escribir_vivos(self, vivos, registros=None) -> None:
        """Escribe en memoria los valores sucios de `vivos` que estan en
        `registros` (por defecto, en todos)."""
        for nombre, r in list(self.registro_de.items()):
            if nombre in self.sucios and nombre in vivos and (registros is None or r in registros):
                self._guardar(nombre, r)
                self.sucios.discard(nombre)
                if registros is not None:
                    self.stats.salvados += 1

    def olvidar_registros(self, registros) -> None:
        for r in registros:
            self.olvidar(self.duenio.get(r))

    def vaciar(self) -> None:
        self.duenio.clear()
        self.registro_de.clear()
        self.sucios.clear()
        self.fijados.clear()


@dataclass
class VariableEnRegistro:
    nombre: str
    registro: str
    peso: int


@dataclass
class PlanDeRegistros:
    """Decision de registros de una funcion (se reporta en el .asm)."""

    variables: list[VariableEnRegistro] = field(default_factory=list)
    temporales: list[str] = field(default_factory=list)
    guardados: list[str] = field(default_factory=list)

    @property
    def por_nombre(self) -> dict[str, str]:
        return {v.nombre: v.registro for v in self.variables}


def elegir_variables_en_registro(
    candidatas: dict[str, int],
    temporales: list[str],
    guardados: list[str],
    es_hoja: bool,
    minimo_peso: int,
    reserva_guardados: int,
    reserva_temporales: int,
) -> PlanDeRegistros:
    """Asigna registros fijos a las variables con mayor peso (usos ponderados
    por 10^profundidad de bucle). Se deja una reserva de registros para `getReg`."""
    plan = PlanDeRegistros(temporales=list(temporales), guardados=list(guardados))
    orden = sorted(candidatas.items(), key=lambda par: (-par[1], par[0]))
    for nombre, peso in orden:
        if peso < minimo_peso:
            break
        if es_hoja:
            if len(plan.temporales) <= reserva_temporales:
                break
            registro = plan.temporales.pop()
        else:
            if len(plan.guardados) <= reserva_guardados:
                break
            registro = plan.guardados.pop(0)
        plan.variables.append(VariableEnRegistro(nombre, registro, peso))
    return plan
