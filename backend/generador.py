"""
Traduccion de TAC a ensamblador, comun a todos los procesadores.

`Programa` hace el analisis de todo el programa (variables capturadas, enlaces
de acceso, marcos en el heap, selectores de metodos). `GeneradorFuncion`
recorre los bloques basicos de una funcion y traduce cada instruccion con ayuda
de los descriptores de `backend/regalloc.py`. Lo que depende del procesador
(instrucciones, registros y convencion) esta detras de `backend/target.py`.

Las ranuras de memoria son las de la tabla de simbolos de la fase 2: un offset
de `ActivationRecord`, `ClassLayout` o del area estatica se usa tal cual en el
ensamblador. La documentacion del diseno esta en docs/Generacion_Codigo.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.cfg import (
    CFG,
    agrupar_parametros,
    construir_cfg,
    es_literal,
    es_llamada_en_ejecucion,
    receptor_de_callv,
    usos,
)
from backend.regalloc import (
    Descriptores,
    EstadisticasRegistros,
    PlanDeRegistros,
    elegir_variables_en_registro,
)
from backend.target import ERR_DIVISION, ERR_INDICE, ERR_NULL, MarcoFuncion, Target
from codegen.tac import Instr, TACFunction, is_temp, unescape
from core.memory import ActivationRecord, _align
from core.runtime import envolver_entero
from core.types import BOOLEAN, ERROR, FLOAT, INTEGER, NULL, STRING, ArrayType, ClassType, FunctionType, Type

_UP = re.compile(r"^up(\d+)\.(.+)$")

COMPARACIONES = frozenset({"<", "<=", ">", ">=", "==", "!="})

# Codigos de los descriptores de tipo que usa `print` para listas y objetos.
TD_ENTERO, TD_FLOTANTE, TD_BOOLEANO, TD_STRING, TD_OBJETO, TD_FUNCION, TD_LISTA = range(7)


class BackendError(Exception):
    """El programa paso el semantico pero no se puede traducir a ensamblador."""


def kind_de(tipo: Type | None) -> str:
    """Clase de valor en la maquina: define ancho y banco de registros."""
    if tipo == INTEGER:
        return "int"
    if tipo == FLOAT:
        return "float"
    if tipo == BOOLEAN:
        return "bool"
    if tipo == STRING:
        return "str"
    return "ref"  # objeto, lista, funcion, null o desconocido


def partir_up(op: str) -> tuple[int, str] | None:
    m = _UP.match(op)
    return (int(m.group(1)), m.group(2)) if m else None


def operandos(i: Instr) -> list[str]:
    extra = [i.dst] if i.dst else []
    if i.op == "callv":
        extra.append(receptor_de_callv(i))
    return [*usos(i), *extra]


class Programa:
    """Informacion global que necesitan las secuencias de llamada."""

    def __init__(self, resultado, target: Target) -> None:
        gen = resultado.generador
        self.target = target
        self.funciones: list[TACFunction] = resultado.tac.functions
        self.ars: dict[str, ActivationRecord] = {ar.name: ar for ar in gen.activation_records}
        self.layouts = gen.layouts
        self.global_area = gen.global_area
        self.codigo = {f.name: agrupar_parametros(f) for f in self.funciones}
        self.capturadas: dict[str, set[str]] = {f.name: set() for f in self.funciones}
        self.necesita_enlace: set[str] = set()
        self.marco_en_heap: set[str] = set()
        self.selectores = self._numerar_metodos()
        self.etiquetas: dict[str, str] = {}
        self._usadas: set[str] = set()
        self.strings: dict[str, str] = {}
        self.flotantes: dict[str, str] = {}
        self.descriptores_tipo: dict[str, tuple[str, list]] = {}
        self.closures_estaticos: dict[str, str] = {}
        self.avisos: list[str] = []
        self._analizar_capturas()
        self._analizar_enlaces()
        self._analizar_marcos_en_heap()

    # --- analisis -------------------------------------------------------

    def profundidad(self, nombre: str) -> int:
        return self.ars[nombre].depth

    def saltos(self, desde: str, hacia: str) -> int:
        """Enlaces de acceso a recorrer desde el marco de `desde` para llegar
        al marco lexicamente envolvente de `hacia`."""
        return self.profundidad(desde) - (self.profundidad(hacia) - 1)

    def _ancestro(self, nombre: str, saltos: int) -> ActivationRecord:
        ar = self.ars[nombre]
        for _ in range(saltos):
            ar = ar.parent
        return ar

    def _analizar_capturas(self) -> None:
        for f in self.funciones:
            for i in self.codigo[f.name]:
                for op in operandos(i):
                    up = partir_up(op)
                    if up is not None:
                        self.capturadas[self._ancestro(f.name, up[0]).name].add(up[1])
                        self._marcar_cadena(f.name, up[0])

    def _marcar_cadena(self, nombre: str, saltos: int) -> bool:
        """Recorrer `saltos` enlaces desde `nombre` lee el enlace de cada marco
        del camino. Devuelve True si alguno aun no estaba marcado."""
        cambio = False
        ar = self.ars[nombre]
        for _ in range(saltos):
            if ar.name not in self.necesita_enlace:
                self.necesita_enlace.add(ar.name)
                cambio = True
            ar = ar.parent
        return cambio

    def implementaciones(self, metodo: str) -> list[str]:
        etiquetas = {
            layout.method_table()[metodo]
            for layout in self.layouts.values()
            if metodo in layout.method_table()
        }
        return sorted(etiquetas)

    def _destinos(self, i: Instr) -> list[str]:
        if i.op == "call" and i.name in self.ars:
            return [i.name]
        if i.op == "closure":
            return [i.name]
        if i.op == "callv":
            return self.implementaciones(i.name.rsplit(".", 1)[1])
        return []

    def _analizar_enlaces(self) -> None:
        """Punto fijo: una funcion necesita su enlace de acceso si lo usa o si
        lo recorre para pasarselo a una funcion que lo necesita."""
        cambio = True
        while cambio:
            cambio = False
            for f in self.funciones:
                for i in self.codigo[f.name]:
                    for destino in self._destinos(i):
                        requerido = destino in self.necesita_enlace or (
                            i.op == "closure" and self.profundidad(destino) >= 2
                        )
                        if requerido and self._marcar_cadena(f.name, self.saltos(f.name, destino)):
                            cambio = True

    def _analizar_marcos_en_heap(self) -> None:
        """Un closure de una funcion anidada puede sobrevivir al marco donde
        se creo (`h = g`): esos marcos se reservan en el heap, no en la pila."""
        for f in self.funciones:
            for i in self.codigo[f.name]:
                if i.op == "closure" and i.name in self.necesita_enlace:
                    ar = self._ancestro(f.name, self.saltos(f.name, i.name))
                    while ar is not None and ar.depth >= 1:
                        self.marco_en_heap.add(ar.name)
                        ar = ar.parent

    def _numerar_metodos(self) -> dict[str, int]:
        """Cada nombre de metodo tiene una entrada fija en todas las tablas de
        metodos, asi `callv` no necesita conocer la clase estatica."""
        nombres = sorted({m for layout in self.layouts.values() for m in layout.method_table()})
        return {m: n for n, m in enumerate(nombres)}

    # --- nombres y constantes -------------------------------------------

    def etiqueta(self, nombre: str) -> str:
        """Etiqueta en ensamblador: prefijo para no chocar con mnemonicos."""
        if nombre not in self.etiquetas:
            base = "fn_" + re.sub(r"\W", "_", nombre.replace(".", "__"))
            etiqueta, n = base, 2
            while etiqueta in self._usadas:
                etiqueta, n = f"{base}_{n}", n + 1
            self._usadas.add(etiqueta)
            self.etiquetas[nombre] = etiqueta
        return self.etiquetas[nombre]

    def string(self, literal: str) -> str:
        texto = unescape(literal)
        return self.string_de_texto(texto)

    def string_de_texto(self, texto: str) -> str:
        if texto not in self.strings:
            self.strings[texto] = f"str_{len(self.strings)}"
        return self.strings[texto]

    def flotante(self, literal: str) -> str:
        clave = repr(float(literal))
        if clave in ("inf", "-inf"):
            raise BackendError(f"el literal {literal[:30]}... no cabe en un float")
        if clave not in self.flotantes:
            self.flotantes[clave] = f"flt_{len(self.flotantes)}"
        return self.flotantes[clave]

    def closure_estatico(self, nombre: str) -> str:
        if nombre not in self.closures_estaticos:
            self.closures_estaticos[nombre] = f"clo_{self.etiqueta(nombre)}"
        return self.closures_estaticos[nombre]

    def descriptor_tipo(self, tipo: Type | None) -> str:
        """Etiqueta del descriptor con el que `print` recorre un valor."""
        if isinstance(tipo, ArrayType):
            elemento = self.descriptor_tipo(tipo.element_type)
            contenido = [TD_LISTA, elemento]
        elif tipo == FLOAT:
            contenido = [TD_FLOTANTE, 0]
        elif tipo == BOOLEAN:
            contenido = [TD_BOOLEANO, 0]
        elif tipo == INTEGER:
            contenido = [TD_ENTERO, 0]
        elif tipo == STRING or tipo == NULL:
            contenido = [TD_STRING, 0]
        elif isinstance(tipo, FunctionType):
            contenido = [TD_FUNCION, 0]
        else:
            contenido = [TD_OBJETO, 0]
        clave = repr(contenido)
        if clave not in self.descriptores_tipo:
            self.descriptores_tipo[clave] = (f"td_{len(self.descriptores_tipo)}", contenido)
        return self.descriptores_tipo[clave][0]


@dataclass
class ReporteFuncion:
    nombre: str
    marco: MarcoFuncion
    plan: PlanDeRegistros
    stats: EstadisticasRegistros
    guardados: list[str] = field(default_factory=list)

    def texto(self) -> str:
        lineas = [
            f"{self.nombre}: marco {self.marco.tamanio} B "
            f"(AR {self.marco.tamanio_ar} B, argumentos salientes {self.marco.salientes} B)"
            + (", marco en el heap" if self.marco.en_heap else "")
        ]
        if self.plan.variables:
            lineas.append(
                "  variables en registro: "
                + ", ".join(f"{v.nombre}->{v.registro} (peso {v.peso})" for v in self.plan.variables)
            )
        if self.guardados:
            lineas.append("  registros guardados en el prologo: " + ", ".join(self.guardados))
        s = self.stats
        lineas.append(
            f"  getReg: {s.llamadas_get_reg} pedidos, {s.libres} libres, {s.desalojos} desalojos, "
            f"{s.derrames} derrames a la pila, {s.salvados} salvados antes de llamadas"
        )
        return "\n".join(lineas)


class GeneradorFuncion:
    def __init__(self, programa: Programa, funcion: TACFunction) -> None:
        self.p = programa
        self.t = programa.target
        self.funcion = funcion
        self.nombre = funcion.name
        self.es_main = funcion.name == "main"
        self.ar = programa.ars[funcion.name]
        self.codigo = programa.codigo[funcion.name]
        self.capturadas = programa.capturadas[funcion.name]
        self.temp_kind: dict[str, str] = {}
        self._marcar_operaciones_de_strings()
        self.cfg: CFG = construir_cfg(self.codigo)
        self.tiene_try = any(i.op == "try" for i in self.codigo)
        self.escritura_directa = self.cfg.vivos_en_manejadores()
        self.es_hoja = not any(es_llamada_en_ejecucion(i) for i in self.codigo)
        self.plan = self._planificar_registros()
        self.fijos = self.plan.por_nombre
        self.d = Descriptores(self.plan.temporales, self.plan.guardados, list(self.t.flotantes), self._guardar)
        self.b = None
        self.salientes = 0
        self.try_base = _align(self.ar.total_size, 8)
        self.try_usados = 0
        self.etiqueta = "main" if self.es_main else programa.etiqueta(self.nombre)
        self.etiqueta_salida = f"{self.etiqueta}_fin"

    # --- preparacion ----------------------------------------------------

    def _marcar_operaciones_de_strings(self) -> None:
        """Las operaciones con strings se traducen a llamadas al runtime: hay
        que saberlo antes de calcular donde cruzan llamadas los valores."""
        for i in self.codigo:
            if i.op in ("bin", "if_rel"):
                i.es_de_strings = "str" in (self.kind(i.a), self.kind(i.b))
            if is_temp(i.dst):
                self.temp_kind[i.dst] = kind_de(i.ty)
        self.temp_kind.clear()

    def _candidatas(self) -> dict[str, int]:
        """Variables que pueden vivir en un registro toda la funcion y su peso."""
        if self.tiene_try:  # un `catch` debe encontrar las variables en memoria
            return {}
        pesos: dict[str, int] = {}
        for i in self.codigo:
            peso = 10 ** min(self.cfg.profundidad_bucle.get(id(i), 0), 3)
            for op in operandos(i):
                if self._es_variable_local(op) and op not in self.capturadas and self.kind(op) != "float":
                    pesos[op] = pesos.get(op, 0) + peso
        return pesos

    def _es_variable_local(self, op: str) -> bool:
        return not (is_temp(op) or es_literal(op) or op.startswith("@") or partir_up(op) or op.startswith("&"))

    def _planificar_registros(self) -> PlanDeRegistros:
        return elegir_variables_en_registro(
            self._candidatas(),
            list(self.t.temporales),
            list(self.t.guardados),
            self.es_hoja,
            minimo_peso=2 if self.es_main else 3,
            reserva_guardados=self.t.reserva_guardados,
            reserva_temporales=self.t.reserva_temporales,
        )

    # --- clases de valor y ubicaciones ----------------------------------

    def _slot_de(self, op: str):
        if op.startswith("@"):
            return self.p.global_area.slot(op[1:])
        up = partir_up(op)
        if up is not None:
            ar = self.ar
            for _ in range(up[0]):
                ar = ar.parent
            return ar.slot(up[1])
        return self.ar.slot(op)

    def kind(self, op: str) -> str:
        if op in ("true", "false"):
            return "bool"
        if op == "null" or op.startswith("&"):
            return "ref"
        if op.startswith('"'):
            return "str"
        if es_literal(op):
            return "float" if "." in op else "int"
        if is_temp(op):
            return self.temp_kind.get(op, "ref")
        slot = self._slot_de(op)
        return kind_de(slot.type if slot is not None else None)

    def _es_memoria(self, nombre: str) -> bool:
        """Globales y variables capturadas: otro codigo las puede leer o
        escribir, asi que cada escritura va directo a memoria."""
        return nombre.startswith("@") or partir_up(nombre) is not None or nombre in self.capturadas

    def _ubicacion(self, nombre: str) -> tuple[str, int]:
        """(registro base, desplazamiento) de la ranura de `nombre`."""
        slot = self._slot_de(nombre)
        if nombre.startswith("@"):
            return self.t.global_base, slot.offset
        up = partir_up(nombre)
        if up is not None:
            self.t.recorrer_enlaces(self.t.scratch0, up[0])
            return self.t.scratch0, slot.offset
        return self.t.fp, slot.offset

    def _guardar(self, nombre: str, registro: str) -> None:
        base, offset = self._ubicacion(nombre)
        self.t.store(self.kind(nombre), registro, base, offset)

    def _cargar(self, registro: str, op: str) -> None:
        """Lleva el valor de `op` (literal o nombre fuera de registro) a `registro`."""
        t = self.t
        if op.startswith("&"):
            t.la(registro, op[1:])
        elif op == "true":
            t.li(registro, 1)
        elif op in ("false", "null"):
            t.li(registro, 0)
        elif op.startswith('"'):
            t.la(registro, self.p.string(op))
        elif es_literal(op):
            if "." in op:
                t.fconst(registro, self.p.flotante(op))
            else:
                t.li(registro, envolver_entero(int(op)))
        else:
            base, offset = self._ubicacion(op)
            t.load(self.kind(op), registro, base, offset)

    # --- operandos: use / def -------------------------------------------

    def _es_cero(self, op: str) -> bool:
        if op in ("false", "null"):
            return True
        return es_literal(op) and op != "true" and not op.startswith('"') and "." not in op and int(op) == 0

    def use(self, op: str, k: int) -> str:
        """Registro que contiene el valor de `op` durante la instruccion k."""
        d = self.d
        if self._es_cero(op):
            return self.t.zero
        if op in self.fijos:
            return self.fijos[op]
        r = d.en_registro(op)
        if r is not None:
            d.fijar(r)
            return r
        flotante = self.kind(op) == "float"
        if es_literal(op):
            r = d.get_reg(flotante, False, self.b, k)
            self._cargar(r, op)
            return r
        r = d.get_reg(flotante, self.b.cruza_llamada(op, k), self.b, k)
        self._cargar(r, op)
        d.ocupar(r, op, sucio=False)
        return r

    def registro_destino(self, nombre: str, kind: str, k: int, reusar: tuple[str, ...] = ()) -> str:
        """Registro donde se calculara el nuevo valor de `nombre`."""
        d = self.d
        if nombre in self.fijos:
            return self.fijos[nombre]
        flotante = kind == "float"
        actual = d.en_registro(nombre)
        if actual is not None and (actual in self.t.flotantes) == flotante:
            d.fijar(actual)
            return actual
        d.olvidar(nombre)
        for op in reusar:  # el destino reutiliza un operando que muere aqui
            r = d.en_registro(op)
            if (
                r is not None
                and op != nombre
                and op not in self.fijos
                and op not in self.b.next_use[k]
                and (r in self.t.flotantes) == flotante
            ):
                d.olvidar(op)
                d.fijar(r)
                return r
        return d.get_reg(flotante, self.b.cruza_llamada(nombre, k), self.b, k)

    def definir(self, nombre: str, registro: str) -> None:
        """`registro` ya tiene el nuevo valor de `nombre`."""
        if nombre not in self.fijos:
            self.d.ocupar(registro, nombre, sucio=True)
            if self._es_memoria(nombre) or nombre in self.escritura_directa:
                self._guardar(nombre, registro)
                self.d.limpiar_nombre(nombre)

    def kind_destino(self, i: Instr) -> str:
        """Clase del valor que define `i`; actualiza la del temporal. Se llama
        despues de leer los operandos: un temporal puede cambiar de clase."""
        if is_temp(i.dst):
            self.temp_kind[i.dst] = kind_de(i.ty)
        return self.kind(i.dst)

    # --- recorrido ------------------------------------------------------

    def generar(self) -> ReporteFuncion:
        t = self.t
        cuerpo = t.capturar(self._cuerpo)
        guardados = list(t.guardados) if self.tiene_try else sorted(
            {v.registro for v in self.plan.variables if v.registro in t.guardados} | self.d.guardados_usados
        )
        if self.es_main:
            guardados = []
        marco = self._marco(guardados)
        t.comentario_seccion(f"funcion {self.nombre}({', '.join(self.funcion.params)})")
        t.etiqueta_global(self.etiqueta) if self.es_main else t.label(self.etiqueta)
        if self.es_main:
            t.inicio_programa()
        t.prologo(marco)
        self._recibir_parametros(marco)
        self._inicializar_locales()
        t.extender(cuerpo)
        t.label(self.etiqueta_salida)
        if self.es_main:
            t.fin_programa()
        else:
            t.epilogo(marco)
        return ReporteFuncion(self.nombre, marco, self.plan, self.d.stats, guardados)

    def _marco(self, guardados: list[str]) -> MarcoFuncion:
        t = self.t
        base_guardados = self.try_base + self.try_usados * t.tamanio_manejador
        final = base_guardados + len(guardados) * t.palabra
        return MarcoFuncion(
            tamanio_ar=self.ar.total_size,
            tamanio=_align_a(final, t.alineacion_pila),
            salientes=_align_a(self.salientes, t.alineacion_pila),
            guardados=[(r, base_guardados + n * t.palabra) for n, r in enumerate(guardados)],
            en_heap=self.nombre in self.p.marco_en_heap,
            usa_enlace=self.nombre in self.p.necesita_enlace,
        )

    def _recibir_parametros(self, marco: MarcoFuncion) -> None:
        """Del lado del llamado: mueve cada argumento a su registro fijo o a
        su ranura del registro de activacion."""
        t = self.t
        leidos = {op for i in self.codigo for op in operandos(i)} | self.capturadas
        for posicion, nombre in enumerate(self.funcion.params):
            if nombre not in leidos:
                continue
            kind = self.kind(nombre)
            registro = t.registro_argumento(posicion, kind)
            if registro is None:
                registro = self.fijos.get(nombre, t.fscratch0 if kind == "float" else t.scratch0)
                base, offset = t.argumento_entrante(marco, posicion)
                t.load(kind, registro, base, offset)
            elif nombre in self.fijos:
                t.mov(self.fijos[nombre], registro)
            if nombre not in self.fijos:
                t.store(kind, registro, t.fp, self.ar.slot(nombre).offset)

    def _inicializar_locales(self) -> None:
        """Pone en cero lo que se podria leer antes de escribirse (`let x:
        integer;`), segun liveness, y las variables capturadas."""
        t = self.t
        nombres = set(self.cfg.entrada.live_in) | self.capturadas
        for nombre in sorted(nombres - set(self.funcion.params)):
            if nombre.startswith("@") or partir_up(nombre):
                continue
            if nombre in self.fijos:
                t.li(self.fijos[nombre], 0)
            else:
                slot = self.ar.slot(nombre)
                t.poner_en_cero(t.fp, slot.offset, slot.size)

    def _cuerpo(self) -> None:
        for b in self.cfg.bloques:
            self.b = b
            termino = False
            for k, i in enumerate(b.instrs):
                self.t.comentario_tac(self._texto_tac(i))
                for u in usos(i):
                    r = self.d.en_registro(u)
                    if r is not None:
                        self.d.fijar(r)
                self._traducir(i, k)
                self.d.soltar_fijados()
                self.d.liberar_muertos(b.next_use[k])
                termino = i.op in ("goto", "if_true", "if_false", "if_rel", "ret")
            if not termino:
                self.d.escribir_vivos(b.live_out)
            self.d.vaciar()

    @staticmethod
    def _texto_tac(i: Instr) -> str:
        if i.args:
            return f"{i}   (args: {', '.join(i.args)})"
        return str(i)

    def _traducir(self, i: Instr, k: int) -> None:
        getattr(self, f"_gen_{i.op}")(i, k)

    # --- datos y aritmetica ---------------------------------------------

    def _gen_label(self, i: Instr, k: int) -> None:
        self.t.label(i.name)

    def _gen_copy(self, i: Instr, k: int) -> None:
        t, d = self.t, self.d
        kind = self.kind(i.dst) if not is_temp(i.dst) else kind_de(i.ty)
        if es_literal(i.a):
            self.kind_destino(i)
            r = self.registro_destino(i.dst, kind, k)
            self._cargar(r, i.a)
            self.definir(i.dst, r)
            return
        fuente = self.use(i.a, k)
        self.kind_destino(i)
        r = self.registro_destino(i.dst, kind, k, (i.a,))
        if r != fuente:
            t.fmov(r, fuente) if kind == "float" else t.mov(r, fuente)
        self.definir(i.dst, r)

    def _gen_bin(self, i: Instr, k: int) -> None:
        if i.operator in COMPARACIONES:
            self._comparacion_a_valor(i, k)
        elif "str" in (self.kind(i.a), self.kind(i.b)):
            self._llamar_runtime("__rt_concat", [i.a, i.b], k, i.dst)
            self._resultado(i, k)
        elif "float" in (self.kind(i.a), self.kind(i.b)):
            self._binario_flotante(i, k)
        else:
            self._binario_entero(i, k)

    def _binario_entero(self, i: Instr, k: int) -> None:
        t = self.t
        a = self.use(i.a, k)
        inmediato = self._inmediato(i.operator, i.b)
        if inmediato is not None:
            kind = self.kind_destino(i)
            r = self.registro_destino(i.dst, kind, k, (i.a,))
            t.bin_inmediato(i.operator, r, a, inmediato)
            self.definir(i.dst, r)
            return
        b = self.use(i.b, k)
        if i.operator in ("/", "%") and not (es_literal(i.b) and not self._es_cero(i.b)):
            t.saltar_si_cero(b, "int", ERR_DIVISION)
        kind = self.kind_destino(i)
        r = self.registro_destino(i.dst, kind, k, (i.a, i.b))
        t.bin_entero(i.operator, r, a, b)
        self.definir(i.dst, r)

    def _inmediato(self, operador: str, op: str) -> int | None:
        if not es_literal(op) or op.startswith('"') or "." in op or op in ("true", "false", "null"):
            return None
        valor = envolver_entero(int(op))
        return valor if self.t.inmediato_valido(operador, valor) else None

    def _exigir_flotantes(self, a: str, b: str) -> None:
        if self.kind(a) != "float" or self.kind(b) != "float":
            raise BackendError(
                f"no se conoce el tipo de un operando de '{a}' y '{b}' en {self.nombre}: "
                "agregue una anotacion de tipo"
            )

    def _binario_flotante(self, i: Instr, k: int) -> None:
        t = self.t
        self._exigir_flotantes(i.a, i.b)
        a, b = self.use(i.a, k), self.use(i.b, k)
        if i.operator in ("/", "%"):
            t.saltar_si_flotante_cero(b, ERR_DIVISION)
        kind = self.kind_destino(i)
        r = self.registro_destino(i.dst, kind, k, (i.a, i.b))
        t.bin_flotante(i.operator, r, a, b)
        self.definir(i.dst, r)

    def _gen_un(self, i: Instr, k: int) -> None:
        t = self.t
        flotante = self.kind(i.a) == "float"
        a = self.use(i.a, k)
        kind = self.kind_destino(i)
        r = self.registro_destino(i.dst, kind, k, (i.a,))
        if i.operator == "!":
            t.negar_booleano(r, a)
        elif flotante:
            t.negar_flotante(r, a)
        else:
            t.negar_entero(r, a)
        self.definir(i.dst, r)

    def _gen_itof(self, i: Instr, k: int) -> None:
        a = self.use(i.a, k)
        kind = self.kind_destino(i)
        r = self.registro_destino(i.dst, kind, k)
        self.t.entero_a_flotante(r, a)
        self.definir(i.dst, r)

    # --- comparaciones y saltos -----------------------------------------

    def _ancho(self, a: str, b: str) -> str:
        """Ancho de una comparacion entera: las referencias ocupan una palabra
        completa de la maquina; enteros y booleanos, 32 bits."""
        kinds = {self.kind(a), self.kind(b)}
        return "ref" if kinds & {"ref", "str"} and not kinds & {"int", "bool"} else "int"

    def _comparacion_a_valor(self, i: Instr, k: int) -> None:
        t = self.t
        kinds = (self.kind(i.a), self.kind(i.b))
        if "str" in kinds:
            self._llamar_runtime("__rt_str_eq", [i.a, i.b], k, i.dst)
            kind = self.kind_destino(i)
            r = self.registro_destino(i.dst, kind, k)
            if i.operator == "==":
                t.mov(r, t.retorno)
            else:
                t.negar_booleano(r, t.retorno)
            self.definir(i.dst, r)
            return
        if "float" in kinds:
            self._exigir_flotantes(i.a, i.b)
        a, b = self.use(i.a, k), self.use(i.b, k)
        ancho = self._ancho(i.a, i.b)
        kind = self.kind_destino(i)
        r = self.registro_destino(i.dst, kind, k, () if "float" in kinds else (i.a, i.b))
        if "float" in kinds:
            t.comparar_flotante_a_valor(i.operator, r, a, b)
        else:
            t.comparar_a_valor(i.operator, r, a, b, ancho)
        self.definir(i.dst, r)

    def _gen_if_rel(self, i: Instr, k: int) -> None:
        t, d = self.t, self.d
        kinds = (self.kind(i.a), self.kind(i.b))
        if "str" in kinds:
            self._llamar_runtime("__rt_str_eq", [i.a, i.b], k)
            d.escribir_vivos(self.b.live_out)
            if i.operator == "==":
                t.saltar_si_no_cero(t.retorno, "int", i.name)
            else:
                t.saltar_si_cero(t.retorno, "int", i.name)
            return
        if "float" in kinds:
            self._exigir_flotantes(i.a, i.b)
        a, b = self.use(i.a, k), self.use(i.b, k)
        d.escribir_vivos(self.b.live_out)
        if "float" in kinds:
            t.saltar_comparando_flotantes(i.operator, a, b, i.name)
        else:
            t.saltar_comparando(i.operator, a, b, i.name, self._ancho(i.a, i.b))

    def _gen_if_true(self, i: Instr, k: int) -> None:
        r = self.use(i.a, k)
        self.d.escribir_vivos(self.b.live_out)
        self.t.saltar_si_no_cero(r, self.kind(i.a), i.name)

    def _gen_if_false(self, i: Instr, k: int) -> None:
        r = self.use(i.a, k)
        self.d.escribir_vivos(self.b.live_out)
        self.t.saltar_si_cero(r, self.kind(i.a), i.name)

    def _gen_goto(self, i: Instr, k: int) -> None:
        self.d.escribir_vivos(self.b.live_out)
        self.t.jump(i.name)

    # --- objetos y listas -----------------------------------------------

    def _offset_campo(self, i: Instr) -> tuple[int, str]:
        layout = self.p.layouts.get(i.clase) if i.clase else None
        if layout is None or i.name not in layout.fields:
            raise BackendError(
                f"no se conoce la clase de '{i.a}.{i.name}' en {self.nombre}: agregue una anotacion de tipo"
            )
        campo = layout.fields[i.name]
        return campo.offset, kind_de(campo.type)

    def _gen_load_field(self, i: Instr, k: int) -> None:
        offset, kind_campo = self._offset_campo(i)
        obj = self.use(i.a, k)
        self.t.saltar_si_cero(obj, "ref", ERR_NULL)
        self.kind_destino(i)
        r = self.registro_destino(i.dst, kind_campo, k, (i.a,))
        self.t.load(kind_campo, r, obj, offset)
        self.definir(i.dst, r)

    def _gen_store_field(self, i: Instr, k: int) -> None:
        offset, kind_campo = self._offset_campo(i)
        obj, valor = self.use(i.a, k), self.use(i.b, k)
        self.t.saltar_si_cero(obj, "ref", ERR_NULL)
        self.t.store(kind_campo, valor, obj, offset)

    def _gen_load_index(self, i: Instr, k: int) -> None:
        t = self.t
        lista, indice = self.use(i.a, k), self.use(i.b, k)
        t.saltar_si_cero(lista, "ref", ERR_NULL)
        direccion = t.direccion_elemento(lista, indice, ERR_INDICE)
        kind = self.kind_destino(i)
        r = self.registro_destino(i.dst, kind, k, (i.a, i.b))
        t.load(kind, r, direccion, t.offset_elementos)
        self.definir(i.dst, r)

    def _gen_store_index(self, i: Instr, k: int) -> None:
        t = self.t
        lista, indice, valor = self.use(i.a, k), self.use(i.b, k), self.use(i.c, k)
        t.saltar_si_cero(lista, "ref", ERR_NULL)
        direccion = t.direccion_elemento(lista, indice, ERR_INDICE)
        t.store(self.kind(i.c), valor, direccion, t.offset_elementos)

    def _gen_len(self, i: Instr, k: int) -> None:
        lista = self.use(i.a, k)
        self.t.saltar_si_cero(lista, "ref", ERR_NULL)
        kind = self.kind_destino(i)
        r = self.registro_destino(i.dst, kind, k, (i.a,))
        self.t.load("int", r, lista, 0)
        self.definir(i.dst, r)

    def _gen_new(self, i: Instr, k: int) -> None:
        t = self.t
        self._llamar_runtime("__rt_alloc", [str(i.n)], k, i.dst)
        self._resultado(i, k, sin_definir=True)
        r = self._registro_resultado
        t.la(t.scratch0, f"cls_{i.name}")
        t.store("ref", t.scratch0, r, 0)
        self.definir(i.dst, r)

    def _gen_newlist(self, i: Instr, k: int) -> None:
        t = self.t
        self._llamar_runtime("__rt_alloc", [str(t.offset_elementos + 8 * i.n)], k, i.dst)
        self._resultado(i, k, sin_definir=True)
        r = self._registro_resultado
        t.li(t.scratch0, i.n)
        t.store("int", t.scratch0, r, 0)
        self.definir(i.dst, r)

    def _gen_closure(self, i: Instr, k: int) -> None:
        t = self.t
        if i.name not in self.p.necesita_enlace and self.p.profundidad(i.name) <= 1:
            kind = self.kind_destino(i)
            r = self.registro_destino(i.dst, kind, k)
            t.la(r, self.p.closure_estatico(i.name))
            self.definir(i.dst, r)
            return
        self._llamar_runtime("__rt_alloc", [str(2 * t.palabra)], k, i.dst)
        self._resultado(i, k, sin_definir=True)
        r = self._registro_resultado
        t.la(t.scratch0, self.p.etiqueta(i.name))
        t.store("ref", t.scratch0, r, 0)
        saltos = self.p.saltos(self.nombre, i.name)
        if saltos == 0:
            t.store("ref", t.fp, r, t.palabra)
        else:
            t.recorrer_enlaces(t.scratch0, saltos)
            t.store("ref", t.scratch0, r, t.palabra)
        self.definir(i.dst, r)

    # --- secuencia de llamada -------------------------------------------

    def _secuencia_de_llamada(self, args: list[str], k: int, saltar, registro_argumento=None,
                              destino: str | None = None) -> None:
        """Lado del llamador:
          1. los argumentos que no van en registro se copian a la zona de
             argumentos salientes (al fondo del marco);
          2. se guardan en sus ranuras los valores vivos en registros que la
             llamada destruye;
          3. se cargan los registros de argumentos;
          4. `saltar` emite el enlace de acceso y el salto;
          5. se olvida lo que la llamada pudo cambiar.
        """
        t, d = self.t, self.d
        registro_argumento = registro_argumento or t.registro_argumento
        en_registro = []
        for posicion, op in enumerate(args):
            kind = self.kind(op)
            registro = registro_argumento(posicion, kind)
            if registro is None:
                t.store(kind, self._sin_ocupar_registros(op), t.sp, 8 * posicion)
                self.salientes = max(self.salientes, 8 * (posicion + 1))
            else:
                en_registro.append((op, registro, kind))
        destruidos = [*self.plan.temporales, *t.flotantes]
        vivos = {n for n in self.b.next_use[k] if n != destino}  # `destino` se reescribe
        d.escribir_vivos(vivos, destruidos)
        for op, registro, kind in en_registro:
            fuente = self.fijos.get(op) or d.en_registro(op)
            if self._es_cero(op):
                t.mov(registro, t.zero)
            elif fuente is None:
                self._cargar(registro, op)
            elif kind == "float":
                t.fmov(registro, fuente)
            else:
                t.mov(registro, fuente)
        saltar()
        d.soltar_fijados()
        d.olvidar_registros(destruidos)
        for nombre in [n for n in d.registro_de if self._es_memoria(n)]:
            d.olvidar(nombre)

    def _sin_ocupar_registros(self, op: str) -> str:
        """Registro con el valor de `op` para una lectura inmediata. Una llamada
        puede tener mas argumentos que registros: lo que no esta en un registro
        pasa por el scratch, sin pedirle nada a getReg."""
        t = self.t
        if self._es_cero(op):
            return t.zero
        registro = self.fijos.get(op) or self.d.en_registro(op)
        if registro is None:
            registro = t.fscratch0 if self.kind(op) == "float" else t.scratch0
            self._cargar(registro, op)
        return registro

    def _llamar_runtime(self, rutina: str, args: list[str], k: int, destino: str | None = None) -> None:
        self._secuencia_de_llamada(args, k, lambda: self.t.call(rutina), self.t.registro_argumento_runtime, destino)

    def _resultado(self, i: Instr, k: int, sin_definir: bool = False) -> None:
        """Lado del llamador tras el retorno: el valor llega en el registro de
        retorno y pasa al destino."""
        t = self.t
        if i.dst is None:
            return
        kind = self.kind_destino(i)
        r = self.registro_destino(i.dst, kind, k)
        if kind == "float":
            t.fmov(r, t.retorno_flotante)
        else:
            t.mov(r, t.retorno)
        self._registro_resultado = r
        if not sin_definir:
            self.definir(i.dst, r)

    def _enlace_para(self, destino: str) -> None:
        """Enlace de acceso del llamado: el marco de su funcion envolvente."""
        t = self.t
        if destino in self.p.necesita_enlace:
            saltos = self.p.saltos(self.nombre, destino)
            if saltos == 0:
                t.mov(t.enlace, t.fp)
            else:
                t.recorrer_enlaces(t.enlace, saltos)

    def _gen_call(self, i: Instr, k: int) -> None:
        if i.name == "print":
            self._gen_print(i, k)
            return

        def saltar() -> None:
            self._enlace_para(i.name)
            self.t.call(self.p.etiqueta(i.name))

        self._secuencia_de_llamada(i.args, k, saltar, destino=i.dst)
        self._resultado(i, k)

    def _gen_callc(self, i: Instr, k: int) -> None:
        def saltar() -> None:
            self.t.llamar_closure(self._sin_ocupar_registros(i.name), ERR_NULL)

        self._secuencia_de_llamada(i.args, k, saltar, destino=i.dst)
        self._resultado(i, k)

    def _gen_callv(self, i: Instr, k: int) -> None:
        metodo = i.name.rsplit(".", 1)[1]
        if metodo not in self.p.selectores:
            raise BackendError(f"no hay ninguna clase con el metodo '{metodo}' ({i.name} en {self.nombre})")

        def saltar() -> None:
            for destino in self.p.implementaciones(metodo):
                if destino in self.p.necesita_enlace:
                    self._enlace_para(destino)
                    break
            self.t.llamar_virtual(self.p.selectores[metodo], ERR_NULL)

        self._secuencia_de_llamada(i.args, k, saltar, destino=i.dst)
        self._resultado(i, k)

    def _gen_print(self, i: Instr, k: int) -> None:
        op = i.args[0]
        kind = self.kind(op)
        tipo = i.ty
        if kind == "float":
            self._llamar_runtime("__rt_print_float", [op], k)
        elif kind == "int":
            self._llamar_runtime("__rt_print_int", [op], k)
        elif kind == "bool":
            self._llamar_runtime("__rt_print_bool", [op], k)
        elif kind == "str" or tipo == NULL:  # `let d = null;` que no recibe otro valor
            self._llamar_runtime("__rt_print_str", [op], k)
        elif tipo in (None, ERROR):
            self.p.avisos.append(
                f"{self.nombre}: no se conoce el tipo de '{op}' en print; se imprime como integer "
                "(agregue una anotacion de tipo)"
            )
            self._llamar_runtime("__rt_print_int", [op], k)
        else:
            self._llamar_runtime("__rt_print_val", [op, "&" + self.p.descriptor_tipo(tipo)], k)

    # --- secuencia de retorno -------------------------------------------

    def _gen_ret(self, i: Instr, k: int) -> None:
        """Lado del llamado: deja el valor en el registro de retorno y en su
        ranura del AR; el epilogo restaura el estado del llamador."""
        t = self.t
        if i.a is not None:
            kind = self.kind(i.a)
            r = self.use(i.a, k)
            if kind == "float":
                t.fmov(t.retorno_flotante, r)
            else:
                t.mov(t.retorno, r)
            t.store(kind, r, t.fp, t.offset_valor_retorno)
        if i is not self.codigo[-1]:
            t.jump(self.etiqueta_salida)

    # --- excepciones ----------------------------------------------------

    def _gen_try(self, i: Instr, k: int) -> None:
        offset = self.try_base + self.try_usados * self.t.tamanio_manejador
        self.try_usados += 1
        self.t.activar_manejador(offset, i.name)

    def _gen_endtry(self, i: Instr, k: int) -> None:
        self.t.desactivar_manejador()

    def _gen_catch(self, i: Instr, k: int) -> None:
        """`__rt_raise` llega aqui con el mensaje en el registro de retorno."""
        kind = self.kind_destino(i)
        r = self.registro_destino(i.dst, kind, k)
        self.t.mov(r, self.t.retorno)
        self.definir(i.dst, r)


def _align_a(valor: int, alineacion: int) -> int:
    return (valor + alineacion - 1) // alineacion * alineacion


@dataclass
class Ensamblado:
    """Resultado de la generacion de codigo."""

    target: str
    codigo: str
    reportes: list[ReporteFuncion]
    avisos: list[str]
    lineas_programa: int  # lineas sin contar el runtime

    def reporte(self) -> str:
        total = EstadisticasRegistros()
        for r in self.reportes:
            total.sumar(r.stats)
        partes = [r.texto() for r in self.reportes]
        partes.append(
            f"TOTAL getReg: {total.llamadas_get_reg} pedidos, {total.libres} libres, {total.desalojos} desalojos, "
            f"{total.derrames} derrames a la pila, {total.salvados} salvados antes de llamadas"
        )
        return "\n".join(partes)


def generar_programa(resultado, target: Target) -> Ensamblado:
    errores = getattr(resultado.generador, "errores_backend", [])
    if errores:
        raise BackendError("; ".join(dict.fromkeys(errores)))
    programa = Programa(resultado, target)
    target.encabezado()
    reportes = []
    # `main` va primero: los simuladores empiezan por la primera instruccion.
    orden = sorted(programa.funciones, key=lambda f: f.name != "main")
    for funcion in orden:
        reportes.append(GeneradorFuncion(programa, funcion).generar())
    lineas = target.total_lineas()
    target.datos(programa)
    target.runtime()
    return Ensamblado(target.nombre, target.texto(), reportes, list(dict.fromkeys(programa.avisos)), lineas)
