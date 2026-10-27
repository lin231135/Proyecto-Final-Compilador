"""
ParseTree de ANTLR -> PNG, en memoria (graphviz `.pipe()`, sin archivos
temporales en disco). Lo usa la pestana "Arbol sintactico" del IDE.

Nodo de regla = `parser.ruleNames[ctx.getRuleIndex()]`; hoja = texto del
token, en otro color. `max_nodos` corta el recorrido para no colgar el IDE
con archivos grandes.
"""

from __future__ import annotations

import shutil

import graphviz
from antlr4.tree.Tree import TerminalNode


def dot_disponible() -> bool:
    """True si el binario `dot` de Graphviz esta en el PATH."""
    return shutil.which("dot") is not None


def render_png(tree, rule_names: list[str], max_nodos: int = 400) -> bytes:
    """
    Renderiza `tree` a PNG en memoria. Lanza la excepcion de graphviz
    (ExecutableNotFound) si el binario `dot` no esta disponible; quien
    llama decide el fallback (ver `render_texto`).
    """
    grafo = graphviz.Digraph(format="png")
    contador = [0]

    def agregar(nodo, id_padre: str | None) -> None:
        if contador[0] >= max_nodos:
            return
        id_actual = str(contador[0])
        contador[0] += 1

        if isinstance(nodo, TerminalNode):
            grafo.node(id_actual, nodo.getText(), shape="box", style="filled", fillcolor="lightyellow")
        else:
            nombre_regla = rule_names[nodo.getRuleIndex()]
            grafo.node(id_actual, nombre_regla, shape="ellipse", style="filled", fillcolor="lightblue")

        if id_padre is not None:
            grafo.edge(id_padre, id_actual)

        if not isinstance(nodo, TerminalNode):
            for i in range(nodo.getChildCount()):
                if contador[0] >= max_nodos:
                    break
                agregar(nodo.getChild(i), id_actual)

    agregar(tree, None)
    return grafo.pipe(format="png")


def render_texto(tree, parser) -> str:
    """Fallback cuando el binario `dot` no esta disponible ."""
    return tree.toStringTree(recog=parser)
