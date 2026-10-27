"""
Visitor combinado del analizador semantico.

El orden de las bases importa (MRO): FunctionMixin y ClassMixin van antes que
TypeMixin para que sus implementaciones de `_aplicar_llamada` y
`_aplicar_propiedad` (las que resuelven `f()` y `obj.x`) sean las que se usan.
Ningun par de mixins define el mismo `visit*` (lo verifica tests/test_mixins.py).
"""

from __future__ import annotations

from semantico.class_mixin import ClassMixin
from semantico.function_mixin import FunctionMixin
from semantico.scope_mixin import ScopeMixin
from semantico.type_mixin import TypeMixin

try:
    from generated.CompiscriptVisitor import CompiscriptVisitor
except ImportError:  # pragma: no cover - generated/ aparece tras `python build_grammar.py`
    class CompiscriptVisitor:  # type: ignore[no-redef]
        pass


class SemanticVisitor(
    ScopeMixin,
    FunctionMixin,
    ClassMixin,
    TypeMixin,
    CompiscriptVisitor,
):
    """Punto de entrada del analisis semantico. El IDE llama a `visit(tree)`."""
