"""
Una prueba por fila de la matriz de tipos, caso valido e invalido.

El indexado (`a[i]`) tambien se prueba llamando `_aplicar_indice` directo,
ademas de las pruebas de punta a punta.
"""

from antlr4 import CommonTokenStream, InputStream

from core.types import ArrayType, BOOLEAN, ERROR, FLOAT, INTEGER, STRING
from driver import analizar
from generated.CompiscriptLexer import CompiscriptLexer
from generated.CompiscriptParser import CompiscriptParser
from semantico.visitor import SemanticVisitor


def _categorias(resultado):
    return {e.category for e in resultado.errores}


def _index_suffix(fuente: str):
    """Extrae el IndexExprContext del suffixOp de un `expressionStatement` como `arr[0];`."""
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
# + : numerico, numerico -> max_tipo(a,b) ; string,string -> string ; otro -> error tipo
# ---------------------------------------------------------------------

def test_suma_numericos_valido():
    assert analizar("1 + 2;").ok
    assert analizar("1 + 2.5;").ok


def test_suma_strings_valido():
    assert analizar('"Hola " + "mundo";').ok


def test_suma_combinacion_invalida():
    r = analizar('1 + "a";')
    assert not r.ok
    assert "tipo" in _categorias(r)


# ---------------------------------------------------------------------
# - * / % : numerico, numerico -> max_tipo(a,b) ; otro -> error tipo
# ---------------------------------------------------------------------

def test_aritmetica_numerico_valido():
    assert analizar("5 - 2;").ok
    assert analizar("5 * 2.0;").ok
    assert analizar("5 / 2;").ok
    assert analizar("5 % 2;").ok


def test_aritmetica_invalida():
    r = analizar('"a" - 1;')
    assert not r.ok
    assert "tipo" in _categorias(r)


# ---------------------------------------------------------------------
# < <= > >= : numerico, numerico -> boolean ; otro -> error tipo
# ---------------------------------------------------------------------

def test_relacional_valido():
    assert analizar("3 < 4;").ok
    assert analizar("3.5 >= 2;").ok


def test_relacional_invalido():
    r = analizar('3 < "a";')
    assert not r.ok
    assert "tipo" in _categorias(r)


# ---------------------------------------------------------------------
# == != : T,T equivalentes -> boolean ; tipos distintos -> error tipo
# ---------------------------------------------------------------------

def test_igualdad_valida():
    assert analizar("3 == 3;").ok
    assert analizar("3 != 3.0;").ok
    assert analizar('"a" == "a";').ok


def test_igualdad_invalida():
    r = analizar('3 == "a";')
    assert not r.ok
    assert "tipo" in _categorias(r)


# ---------------------------------------------------------------------
# && || : boolean, boolean -> boolean ; otro -> error tipo
# ---------------------------------------------------------------------

def test_logicos_validos():
    assert analizar("true && false;").ok
    assert analizar("true || false;").ok


def test_logicos_invalidos():
    r = analizar("1 && true;")
    assert not r.ok
    assert "tipo" in _categorias(r)


# ---------------------------------------------------------------------
# ! : boolean -> boolean ; otro -> error tipo
# ---------------------------------------------------------------------

def test_negacion_valida():
    assert analizar("!true;").ok


def test_negacion_invalida():
    r = analizar("!1;")
    assert not r.ok
    assert "tipo" in _categorias(r)


# ---------------------------------------------------------------------
# - unario : numerico -> mismo tipo ; otro -> error tipo
# ---------------------------------------------------------------------

def test_menos_unario_valido():
    assert analizar("-5;").ok
    assert analizar("-5.5;").ok


def test_menos_unario_invalido():
    r = analizar('-"a";')
    assert not r.ok
    assert "tipo" in _categorias(r)


# ---------------------------------------------------------------------
# ?: : cond boolean, ramas equivalentes -> tipo de las ramas
# ---------------------------------------------------------------------

def test_ternario_valido():
    assert analizar("true ? 1 : 2;").ok
    assert analizar("true ? 1 : 2.5;").ok


def test_ternario_condicion_no_booleana_invalida():
    r = analizar("1 ? 1 : 2;")
    assert not r.ok
    assert "tipo" in _categorias(r)


def test_ternario_ramas_distintas_invalido():
    r = analizar('true ? 1 : "a";')
    assert not r.ok
    assert "tipo" in _categorias(r)


# ---------------------------------------------------------------------
# indexado a[i] : a ArrayType, i integer -> element_type
# ---------------------------------------------------------------------

def test_indexado_valido():
    visitor = SemanticVisitor()
    sufijo = _index_suffix("arr[0];")
    assert visitor._aplicar_indice(ArrayType(INTEGER), sufijo) == INTEGER
    assert not visitor.reporter.has_errors()


def test_indexado_base_no_arreglo_invalido():
    visitor = SemanticVisitor()
    sufijo = _index_suffix("arr[0];")
    assert visitor._aplicar_indice(INTEGER, sufijo) == ERROR
    assert "lista" in {e.category for e in visitor.reporter.all()}


def test_indexado_indice_no_entero_invalido():
    visitor = SemanticVisitor()
    sufijo = _index_suffix('arr["x"];')
    assert visitor._aplicar_indice(ArrayType(INTEGER), sufijo) == ERROR
    assert "lista" in {e.category for e in visitor.reporter.all()}


# ---------------------------------------------------------------------
# null: asignable solo a ClassType/ArrayType; `let d = null;` (sin
# anotacion) deja el simbolo en NULL, que acepta una reasignacion posterior
# de clase o arreglo (no de otro primitivo).
# ---------------------------------------------------------------------

def test_null_no_asignable_a_primitivo_invalido():
    r = analizar("let x: integer = null;")
    assert not r.ok
    assert "tipo" in _categorias(r)


def test_null_asignable_a_clase_valido():
    assert analizar("class A {} let a: A = null;").ok


def test_null_asignable_a_arreglo_valido():
    assert analizar("let a: integer[] = null;").ok


def test_null_sin_anotacion_reasignable_a_clase_valido():
    assert analizar("class A {} let d = null; d = new A();").ok


def test_null_sin_anotacion_reasignable_a_arreglo_valido():
    assert analizar("let d = null; d = [1, 2, 3];").ok


def test_null_sin_anotacion_no_reasignable_a_primitivo_invalido():
    r = analizar("let d = null; d = 5;")
    assert not r.ok
    assert "tipo" in _categorias(r)


# ---------------------------------------------------------------------
# Un tipo desconocido en una anotacion se resuelve mas de una vez entre el
# prepass y la pasada 2 (parametro/retorno de una funcion, campo de
# una clase): sin memoizar por identidad de ctx, se reportaba 2 o 3 veces
# por la misma causa.
# ---------------------------------------------------------------------

def test_tipo_desconocido_en_parametro_reporta_una_sola_vez():
    r = analizar("function f(x: NoExiste) {}")
    assert len(r.errores) == 1


def test_tipo_desconocido_en_retorno_de_funcion_global_reporta_una_sola_vez():
    r = analizar("function f(): NoExiste { return null; }")
    assert len(r.errores) == 1


def test_tipo_desconocido_en_retorno_de_metodo_reporta_una_sola_vez():
    r = analizar("class A { function f(): NoExiste { return null; } }")
    assert len(r.errores) == 1


def test_tipo_desconocido_en_campo_de_clase_reporta_una_sola_vez():
    r = analizar("class A { let x: NoExiste; }")
    assert len(r.errores) == 1


def test_dos_tipos_desconocidos_distintos_reportan_dos_errores():
    r = analizar("function f(a: NoExiste1, b: NoExiste2) {}")
    assert len(r.errores) == 2
