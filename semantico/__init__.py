# Mixins del analizador semantico, combinados en semantico/visitor.py:
#   - scope_mixin.py      -> tabla de simbolos y estado compartido
#   - type_mixin.py       -> tipos, expresiones, listas
#   - function_mixin.py   -> funciones, ambitos, control de flujo
#   - class_mixin.py      -> clases y objetos
#
# Ver docs/ARCHITECTURE.md para el detalle.

from semantico.visitor import SemanticVisitor

__all__ = ["SemanticVisitor"]
