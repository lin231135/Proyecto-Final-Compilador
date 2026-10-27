"""
Caso valido e invalido para cada regla de ambitos, funciones y control de
flujo.

El numero y tipo de argumentos se prueba tambien llamando `check_call_args`
directo, ademas de las llamadas reales `f(1);`.
"""

from antlr4 import CommonTokenStream, InputStream

from core.types import ERROR, FunctionType, INTEGER, STRING
from driver import analizar
from generated.CompiscriptLexer import CompiscriptLexer
from generated.CompiscriptParser import CompiscriptParser
from semantico.visitor import SemanticVisitor


def _categorias(resultado):
    return {e.category for e in resultado.errores}


def _call_arguments(fuente: str):
    """Extrae el ArgumentsContext de un `expressionStatement` como `f(1, 2);`."""
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
    call = lhs.suffixOp(0)
    return call, call.arguments()


# ---------------------------------------------------------------------
# resolucion de nombres local/global
# ---------------------------------------------------------------------

def test_r7_resolucion_valida():
    assert analizar("let x: integer = 1; let y: integer = x + 1;").ok


def test_r7_no_declarada_invalido():
    r = analizar("let y: integer = z + 1;")
    assert not r.ok
    assert "ambito" in _categorias(r)


# ---------------------------------------------------------------------
# acceso en bloques anidados (un bloque no fuga variables al salir)
# ---------------------------------------------------------------------

def test_r10_bloque_anidado_valido():
    assert analizar("let x: integer = 1; { let y: integer = x; }").ok


def test_r10_variable_de_bloque_no_fuga_invalido():
    r = analizar("{ let y: integer = 1; } let z: integer = y;")
    assert not r.ok
    assert "ambito" in _categorias(r)


# ---------------------------------------------------------------------
# numero y tipo de argumentos (posicional)
# ---------------------------------------------------------------------

def test_r12_argumentos_correctos_valido():
    visitor = SemanticVisitor()
    _, args = _call_arguments("f(1, 2);")
    tipo_f = FunctionType(param_types=(INTEGER, INTEGER), return_type=INTEGER)
    visitor.check_call_args(tipo_f, args, args)
    assert not visitor.reporter.has_errors()


def test_r12_numero_de_argumentos_invalido():
    visitor = SemanticVisitor()
    call, args = _call_arguments("f(1, 2, 3);")
    tipo_f = FunctionType(param_types=(INTEGER,), return_type=INTEGER)
    visitor.check_call_args(tipo_f, args, call)
    assert "funcion" in {e.category for e in visitor.reporter.all()}


def test_r12_tipo_de_argumento_invalido():
    visitor = SemanticVisitor()
    call, args = _call_arguments('f("a");')
    tipo_f = FunctionType(param_types=(INTEGER,), return_type=INTEGER)
    visitor.check_call_args(tipo_f, args, call)
    assert "funcion" in {e.category for e in visitor.reporter.all()}


# ---------------------------------------------------------------------
# tipo de retorno vs declarado
# ---------------------------------------------------------------------

def test_r13_retorno_correcto_valido():
    assert analizar("function f(): integer { return 1; }").ok


def test_r13_retorno_incorrecto_invalido():
    r = analizar('function f(): integer { return "a"; }')
    assert not r.ok
    assert "funcion" in _categorias(r)


# ---------------------------------------------------------------------
# recursion
# ---------------------------------------------------------------------

def test_r14_recursion_valida():
    src = "function fact(n: integer): integer { if (n <= 1) { return 1; } return n * fact(n - 1); }"
    assert analizar(src).ok


def test_r14_llamada_a_no_declarada_invalido():
    r = analizar("function f(): integer { return sinDeclarar(); }")
    assert not r.ok
    assert "ambito" in _categorias(r)


# ---------------------------------------------------------------------
# funciones anidadas y closures
# ---------------------------------------------------------------------

def test_r15_funcion_anidada_valida():
    src = (
        "function outer(): integer { "
        "let x: integer = 10; "
        "function inner(): integer { return x; } "
        "return inner(); }"
    )
    assert analizar(src).ok


def test_r15_variable_de_funcion_anidada_no_fuga_invalido():
    src = "function outer(): integer { function inner(): integer { let y: integer = 1; return y; } return y; }"
    r = analizar(src)
    assert not r.ok
    assert "ambito" in _categorias(r)


# ---------------------------------------------------------------------
# redeclaracion de funciones
# ---------------------------------------------------------------------

def test_r16_funcion_unica_valida():
    assert analizar("function f() {} function g() {}").ok


def test_r16_funcion_redeclarada_invalido():
    r = analizar("function f() {} function f() {}")
    assert not r.ok
    assert "ambito" in _categorias(r)


# ---------------------------------------------------------------------
# condiciones if/while/do-while/for boolean
# ---------------------------------------------------------------------

def test_r17_condiciones_booleanas_validas():
    assert analizar("if (true) { print(1); }").ok
    assert analizar("while (true) { print(1); }").ok
    assert analizar("do { print(1); } while (true);").ok
    assert analizar("for (let i: integer = 0; i < 10; i = i + 1) { print(i); }").ok


def test_r17_condicion_no_booleana_invalido():
    r = analizar("if (1) { print(1); }")
    assert not r.ok
    assert "control_flujo" in _categorias(r)


# ---------------------------------------------------------------------
# break/continue solo en bucles
# ---------------------------------------------------------------------

def test_r18_break_en_bucle_valido():
    assert analizar("while (true) { break; }").ok
    assert analizar("while (true) { continue; }").ok


def test_r18_break_fuera_de_bucle_invalido():
    r = analizar("break;")
    assert not r.ok
    assert "control_flujo" in _categorias(r)


def test_r18_continue_fuera_de_bucle_invalido():
    r = analizar("continue;")
    assert not r.ok
    assert "control_flujo" in _categorias(r)


# ---------------------------------------------------------------------
# return solo dentro de una funcion
# ---------------------------------------------------------------------

def test_r19_return_en_funcion_valido():
    assert analizar("function f(): integer { return 1; }").ok


def test_r19_return_fuera_de_funcion_invalido():
    r = analizar("return 1;")
    assert not r.ok
    assert "control_flujo" in _categorias(r)


# ---------------------------------------------------------------------
# codigo muerto tras return/break/continue
# ---------------------------------------------------------------------

def test_r25_sin_codigo_muerto_valido():
    assert analizar("function f(): integer { let x: integer = 1; return x; }").ok


def test_r25_codigo_muerto_invalido():
    r = analizar("function f(): integer { return 1; let x: integer = 2; }")
    assert not r.ok
    assert "general" in _categorias(r)


def test_r25_codigo_muerto_en_switch_case_invalido():
    r = analizar("let x: integer = 1; switch (x) { case 1: break; print(1); }")
    assert not r.ok
    assert "general" in _categorias(r)


# ---------------------------------------------------------------------
# declaraciones duplicadas (variables, parametros)
# ---------------------------------------------------------------------

def test_r27_sin_duplicados_valido():
    assert analizar("let x: integer = 1; let y: integer = 2;").ok


def test_r27_variable_duplicada_invalido():
    r = analizar("let x: integer = 1; let x: integer = 2;")
    assert not r.ok
    assert "ambito" in _categorias(r)


def test_r27_parametro_duplicado_invalido():
    r = analizar("function f(a: integer, a: integer) {}")
    assert not r.ok
    assert "ambito" in _categorias(r)
