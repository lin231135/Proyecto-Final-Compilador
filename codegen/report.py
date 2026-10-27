"""
Reporte del estado de la tabla de simbolos con la informacion que agrega la
generacion de codigo: entornos con direcciones, area estatica, layout de
objetos (con tabla de metodos), registros de activacion y acceso a variables
de funciones envolventes (closures).
"""

from __future__ import annotations

from codegen.generator import OBJECT_HEADER, TACGenerator
from core.memory import ActivationRecord, type_name
from core.symbols import SymbolTable


def _linea_slot(s) -> str:
    tipo = f": {type_name(s.type)}" if s.type is not None else ""
    return f"    +{s.offset:<4} [{s.kind}] {s.name}{tipo}  ({s.size} B)"


def render_ar(ar: ActivationRecord) -> str:
    padre = f", AR lexico padre = {ar.parent.name}" if ar.parent is not None else ""
    lineas = [f"AR {ar.name}  (profundidad {ar.depth}{padre}, tamano {ar.total_size} B)"]
    lineas += [_linea_slot(s) for s in ar.slots]
    return "\n".join(lineas)


def render_symbols(table: SymbolTable) -> str:
    return table.format_environments()


def render_codegen_report(gen: TACGenerator) -> str:
    secciones: list[str] = []

    if gen.global_area.slots:
        lineas = [f"== Area estatica (globales, {gen.global_area.total_size} B) =="]
        lineas += [_linea_slot(s) for s in gen.global_area.slots]
        secciones.append("\n".join(lineas))

    if gen.layouts:
        lineas = ["== Layout de objetos =="]
        for layout in gen.layouts.values():
            herencia = f" : {layout.parent.name}" if layout.parent else ""
            lineas.append(f"clase {layout.name}{herencia}  (instancia = {layout.instance_size} B)")
            lineas.append(f"    +0    <descriptor_de_clase>  ({OBJECT_HEADER} B)")
            for f in layout.fields.values():
                heredado = f"  [heredado de {f.owner}]" if f.owner != layout.name else ""
                lineas.append(f"    +{f.offset:<4} {f.name}: {type_name(f.type)}  ({f.size} B){heredado}")
            tabla = layout.method_table()
            if tabla:
                lineas.append("    metodos: " + ", ".join(f"{m} -> {lab}" for m, lab in tabla.items()))
            if layout.has_initializers:
                lineas.append(f"    inicializador de campos: {layout.name}._init")
        secciones.append("\n".join(lineas))

    lineas = ["== Registros de activacion =="]
    lineas += ["\n".join(["", render_ar(ar)]) for ar in gen.activation_records]
    secciones.append("\n".join(lineas))

    if gen.closure_accesses:
        vistos: set[tuple] = set()
        lineas = ["== Acceso a variables de funciones envolventes (enlace de acceso) =="]
        for a in gen.closure_accesses:
            clave = (a.variable, a.used_in, a.defined_in, a.hops)
            if clave in vistos:
                continue
            vistos.add(clave)
            lineas.append(
                f"    '{a.variable}' usada en {a.used_in}, definida en {a.defined_in}: "
                f"{a.hops} salto(s) de enlace de acceso, desplazamiento +{a.offset}   (op. up{a.hops}.{a.variable})"
            )
        secciones.append("\n".join(lineas))

    return "\n\n".join(secciones)
