"""
Analisis del TAC de una funcion, independiente del procesador destino:

  - agrupa cada `param` con su llamada (`Instr.args`);
  - parte el codigo en bloques basicos y arma el grafo de flujo (CFG);
  - calcula liveness global (`live_in`/`live_out` por bloque) por dataflow;
  - calcula, por instruccion, la proxima ocurrencia de cada nombre dentro del
    bloque (next-use, Dragon Book 8.5.1): `getReg` la usa para decidir que
    registro desalojar y si un valor debe sobrevivir a una llamada.

Con `try` en la funcion, cualquier instruccion puede saltar a un `catch`: se
agregan arcos de todos los bloques a todos los manejadores, de modo que lo que
se usa en un `catch` queda vivo en toda la funcion.
"""

from __future__ import annotations

import bisect
import copy
import re
from dataclasses import dataclass, field

from codegen.tac import Instr, TACFunction

_LITERAL = re.compile(r'^-?\d+(\.\d+)?$|^"')
TERMINADORES = frozenset({"goto", "if_true", "if_false", "if_rel", "ret"})
LLAMADAS = frozenset({"call", "callv", "callc"})
INFINITO = 1 << 30  # next-use de un nombre vivo al salir del bloque


def es_literal(op: str) -> bool:
    return op in ("true", "false", "null") or _LITERAL.match(op) is not None


def lugares(*operandos: str | None) -> list[str]:
    return [op for op in operandos if op is not None and not es_literal(op)]


def receptor_de_callv(instr: Instr) -> str:
    return instr.name.rsplit(".", 1)[0]


def usos(i: Instr) -> list[str]:
    """Nombres (variables y temporales) que lee la instruccion."""
    o = i.op
    if o in ("copy", "un", "len", "itof", "if_true", "if_false", "ret", "load_field"):
        return lugares(i.a)
    if o in ("bin", "if_rel", "load_index", "store_field"):
        return lugares(i.a, i.b)
    if o == "store_index":
        return lugares(i.a, i.b, i.c)
    if o == "callc":
        return lugares(i.name, *(i.args or []))
    if o in ("call", "callv"):
        return lugares(*(i.args or []))
    return []


def definicion(i: Instr) -> str | None:
    """Nombre que escribe la instruccion (si escribe alguno)."""
    return i.dst


def agrupar_parametros(funcion: TACFunction) -> list[Instr]:
    """Copia del codigo sin `param`: cada llamada lleva sus argumentos en
    `args`. Los `param` de una llamada siempre van contiguos antes de ella."""
    resultado: list[Instr] = []
    pendientes: list[str] = []
    for original in funcion.instructions:
        if original.op == "param":
            pendientes.append(original.a)
            continue
        i = copy.copy(original)
        if i.op in LLAMADAS:
            i.args = pendientes[-i.n:] if i.n else []
            pendientes = pendientes[: len(pendientes) - len(i.args)]
        resultado.append(i)
    return resultado


@dataclass
class Bloque:
    indice: int
    instrs: list[Instr]
    sucesores: list["Bloque"] = field(default_factory=list)
    usa: set[str] = field(default_factory=set)  # leidos antes de escribirse
    define: set[str] = field(default_factory=set)
    live_in: set[str] = field(default_factory=set)
    live_out: set[str] = field(default_factory=set)
    # next_use[k]: nombre -> indice de su proximo uso DESPUES de la instruccion
    # k (INFINITO si vive al salir del bloque). Si no esta, el valor murio.
    next_use: list[dict[str, int]] = field(default_factory=list)
    llamadas: list[int] = field(default_factory=list)  # indices con llamada

    def cruza_llamada(self, nombre: str, k: int) -> bool:
        """True si el valor de `nombre` tras la instruccion k debe seguir vivo
        despues de una llamada posterior (hay que guardarlo en un registro
        que la llamada no destruya)."""
        proximo = self.next_use[k].get(nombre)
        if proximo is None:
            return False
        p = bisect.bisect_right(self.llamadas, k)
        return p < len(self.llamadas) and self.llamadas[p] < proximo


@dataclass
class CFG:
    bloques: list[Bloque]
    manejadores: list[Bloque]  # bloques que empiezan en la etiqueta de un `catch`
    profundidad_bucle: dict[int, int]  # id(instr) -> bucles que la contienen

    @property
    def entrada(self) -> Bloque:
        return self.bloques[0]

    def vivos_en_manejadores(self) -> set[str]:
        vivos: set[str] = set()
        for b in self.manejadores:
            vivos |= b.live_in
        return vivos


def _partir(codigo: list[Instr]) -> list[Bloque]:
    lideres = {0}
    for k, i in enumerate(codigo):
        if i.op == "label":
            lideres.add(k)
        elif i.op in TERMINADORES:
            lideres.add(k + 1)
    orden = sorted(x for x in lideres if x < len(codigo)) or [0]
    return [
        Bloque(n, codigo[inicio:fin])
        for n, (inicio, fin) in enumerate(zip(orden, [*orden[1:], len(codigo)]))
    ]


def _enlazar(bloques: list[Bloque]) -> list[Bloque]:
    por_etiqueta = {b.instrs[0].name: b for b in bloques if b.instrs and b.instrs[0].op == "label"}
    manejadores = []
    for b in bloques:
        ultima = b.instrs[-1] if b.instrs else None
        for i in b.instrs:
            if i.op == "try":
                manejadores.append(por_etiqueta[i.name])
        if ultima is not None and ultima.op in ("goto", "if_true", "if_false", "if_rel"):
            b.sucesores.append(por_etiqueta[ultima.name])
        if (ultima is None or ultima.op not in ("goto", "ret")) and b.indice + 1 < len(bloques):
            b.sucesores.append(bloques[b.indice + 1])
    for b in bloques:
        for m in manejadores:
            if m not in b.sucesores:
                b.sucesores.append(m)
    return manejadores


def _liveness(bloques: list[Bloque]) -> None:
    for b in bloques:
        for i in b.instrs:
            b.usa |= {u for u in usos(i) if u not in b.define}
            d = definicion(i)
            if d is not None:
                b.define.add(d)
    cambio = True
    while cambio:
        cambio = False
        for b in reversed(bloques):
            salida = set().union(*(s.live_in for s in b.sucesores)) if b.sucesores else set()
            entrada = b.usa | (salida - b.define)
            if salida != b.live_out or entrada != b.live_in:
                b.live_out, b.live_in = salida, entrada
                cambio = True


def _next_use(b: Bloque) -> None:
    proximo = {nombre: INFINITO for nombre in b.live_out}
    b.next_use = [{} for _ in b.instrs]
    for k in range(len(b.instrs) - 1, -1, -1):
        b.next_use[k] = dict(proximo)
        i = b.instrs[k]
        d = definicion(i)
        if d is not None:
            proximo.pop(d, None)
        for u in usos(i):
            proximo[u] = k
    b.llamadas = [k for k, i in enumerate(b.instrs) if es_llamada_en_ejecucion(i)]


def es_llamada_en_ejecucion(i: Instr) -> bool:
    """La instruccion se traduce a una llamada (al programa o al runtime) y
    por lo tanto destruye los registros que guarda quien llama."""
    if i.op in LLAMADAS or i.op in ("new", "newlist", "closure"):
        return True
    return i.op in ("bin", "if_rel") and getattr(i, "es_de_strings", False)


def _profundidades(codigo: list[Instr]) -> dict[int, int]:
    """Cuantos bucles rodean cada instruccion: un salto hacia una etiqueta
    anterior delimita un bucle."""
    posicion = {i.name: k for k, i in enumerate(codigo) if i.op == "label"}
    profundidad = [0] * (len(codigo) + 1)
    for k, i in enumerate(codigo):
        if i.op in ("goto", "if_true", "if_false", "if_rel") and posicion[i.name] <= k:
            for j in range(posicion[i.name], k + 1):
                profundidad[j] += 1
    return {id(i): profundidad[k] for k, i in enumerate(codigo)}


def construir_cfg(codigo: list[Instr]) -> CFG:
    bloques = _partir(codigo)
    manejadores = _enlazar(bloques)
    _liveness(bloques)
    for b in bloques:
        _next_use(b)
    return CFG(bloques, manejadores, _profundidades(codigo))
