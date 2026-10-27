"""
Casos de clases: atributo inexistente, metodo inexistente, aridad del
constructor, `this` fuera de clase, herencia y asignabilidad de subclase a
superclase.

El acceso a miembros tambien se prueba llamando `_aplicar_propiedad` directo
(mismo patron que `_aplicar_indice` en test_tipos.py y `check_call_args` en
test_funciones.py), ademas de las pruebas de punta a punta.
"""

from antlr4 import CommonTokenStream, InputStream

from core.types import ClassType, ERROR, FunctionType, INTEGER, VOID
from driver import analizar
from generated.CompiscriptLexer import CompiscriptLexer
from generated.CompiscriptParser import CompiscriptParser
from semantico.class_mixin import ClassMixin
from semantico.scope_mixin import ScopeMixin


class _ClasesAisladas(ScopeMixin, ClassMixin):
    """
    Harness para probar `_aplicar_propiedad` sin pasar por el MRO completo
    de SemanticVisitor: ahi TypeMixin queda antes que ClassMixin y su
    stub del mismo nombre gana en silencio (ver la nota en class_mixin.py).
    Con MRO (ScopeMixin, ClassMixin) no hay colision.
    """


def _categorias(resultado):
    return {e.category for e in resultado.errores}


def _property_suffix(fuente: str):
    """Extrae el sufijo `.Identifier` (o `.Identifier(...)`) de `obj.algo;` / `obj.algo();`."""
    lexer = CompiscriptLexer(InputStream(fuente))
    tokens = CommonTokenStream(lexer)
    parser = CompiscriptParser(tokens)
    tree = parser.program()
    expr = tree.statement(0).expressionStatement().expression()
    lhs = (
        expr.assignmentExpr()
        .conditionalExpr()
        .logicalOrExpr()
        .logicalAndExpr(0)
        .equalityExpr(0)
        .relationalExpr(0)
        .additiveExpr(0)
        .multiplicativeExpr(0)
        .unaryExpr(0)
        .primaryExpr()
        .leftHandSide()
    )
    return lhs.suffixOp(0)


# ---------------------------------------------------------------------
# atributos/metodos accedidos con '.'
# ---------------------------------------------------------------------

def test_r20_atributo_existente_valido():
    visitor = _ClasesAisladas()
    animal = ClassType(name="Animal")
    animal.fields["edad"] = INTEGER
    sufijo = _property_suffix("obj.edad;")
    assert visitor._aplicar_propiedad(animal, sufijo) == INTEGER
    assert not visitor.reporter.has_errors()


def test_r20_atributo_inexistente_invalido():
    visitor = _ClasesAisladas()
    animal = ClassType(name="Animal")
    sufijo = _property_suffix("obj.noExiste;")
    assert visitor._aplicar_propiedad(animal, sufijo) == ERROR
    assert "clase" in {e.category for e in visitor.reporter.all()}


def test_r20_metodo_inexistente_invalido():
    visitor = _ClasesAisladas()
    animal = ClassType(name="Animal")
    sufijo = _property_suffix("obj.correr();")
    assert visitor._aplicar_propiedad(animal, sufijo) == ERROR
    assert "clase" in {e.category for e in visitor.reporter.all()}


def test_r20_herencia_metodo_del_padre_accesible_desde_el_hijo():
    visitor = _ClasesAisladas()
    animal = ClassType(name="Animal")
    animal.methods["hablar"] = FunctionType(param_types=(), return_type=VOID)
    perro = ClassType(name="Perro", parent=animal)
    sufijo = _property_suffix("obj.hablar();")
    assert visitor._aplicar_propiedad(perro, sufijo) == FunctionType(param_types=(), return_type=VOID)
    assert not visitor.reporter.has_errors()


# ---------------------------------------------------------------------
# invocacion correcta del constructor
# ---------------------------------------------------------------------

def test_r21_constructor_aridad_correcta_valido():
    src = "class P { function constructor(x: integer) {} } let p: P = new P(1);"
    assert analizar(src).ok


def test_r21_constructor_aridad_mala_invalido():
    src = "class P { function constructor(x: integer) {} } let p: P = new P();"
    r = analizar(src)
    assert not r.ok
    assert "funcion" in _categorias(r)


def test_r21_sin_constructor_exige_cero_argumentos_invalido():
    r = analizar("class P {} let p: P = new P(1);")
    assert not r.ok
    assert "clase" in _categorias(r)


def test_r21_sin_constructor_cero_argumentos_valido():
    assert analizar("class P {} let p: P = new P();").ok


# ---------------------------------------------------------------------
# 'this' dentro del ambito de la clase
# ---------------------------------------------------------------------

def test_r22_this_dentro_de_metodo_valido():
    src = "class P { function identidad(): P { return this; } }"
    assert analizar(src).ok


def test_r22_this_fuera_de_clase_invalido():
    r = analizar("function f(): integer { return this; }")
    assert not r.ok
    assert "clase" in _categorias(r)


# ---------------------------------------------------------------------
# Herencia / asignabilidad de subclase a superclase
# ---------------------------------------------------------------------

def test_herencia_subclase_asignable_a_superclase_valido():
    src = "class Animal {} class Perro : Animal {} let a: Animal = new Perro();"
    assert analizar(src).ok


def test_herencia_superclase_no_asignable_a_subclase_invalido():
    src = "class Animal {} class Perro : Animal {} let p: Perro = new Animal();"
    r = analizar(src)
    assert not r.ok
    assert "tipo" in _categorias(r)


def test_clase_padre_no_declarada_invalido():
    r = analizar("class Perro : Fantasma {}")
    assert not r.ok
    assert "clase" in _categorias(r)
