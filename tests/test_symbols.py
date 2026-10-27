"""
Pruebas de core/symbols.py.

Ejecutar con: pytest tests/test_symbols.py -v

"""

import pytest

from core.errors import ErrorReporter
from core.symbols import ScopeHelpers, Symbol, SymbolTable
from core.types import INTEGER, STRING


def make_var(name: str, type_=INTEGER, kind: str = "var") -> Symbol:
    return Symbol(name=name, type=type_, kind=kind)


def test_define_and_resolve_en_el_mismo_scope():
    table = SymbolTable()
    x = make_var("x")
    assert table.current().define(x) is True
    assert table.current().resolve("x") is x


def test_redeclaracion_en_el_mismo_scope_falla():
    table = SymbolTable()
    table.current().define(make_var("x"))
    ok = table.current().define(make_var("x", type_=STRING))
    assert ok is False


def test_shadowing_en_scopes_anidados_esta_permitido():
    table = SymbolTable()
    table.current().define(make_var("x", type_=INTEGER))

    inner = table.enter_scope("block")
    ok = inner.define(make_var("x", type_=STRING))
    assert ok is True
    assert inner.resolve("x").type == STRING
    table.exit_scope()

    assert table.current().resolve("x").type == INTEGER


def test_resolver_variable_global_desde_scope_anidado():
    table = SymbolTable()
    table.current().define(make_var("global_var"))

    table.enter_scope("function")
    table.enter_scope("block")
    assert table.current().resolve("global_var") is not None
    table.exit_scope()
    table.exit_scope()


def test_bloque_anidado_no_fuga_variables_al_salir():
    table = SymbolTable()
    table.enter_scope("block")
    table.current().define(make_var("local"))
    table.exit_scope()

    assert table.current().resolve("local") is None


def test_resolve_no_encontrado_retorna_none():
    table = SymbolTable()
    assert table.current().resolve("no_existe") is None


def test_scope_helpers_require_declared_reporta_error_si_falta():
    table = SymbolTable()
    reporter = ErrorReporter()
    helpers = ScopeHelpers(table=table, reporter=reporter)

    class FakeToken:
        line = 1
        column = 1

    class FakeCtx:
        start = FakeToken()

    resultado = helpers.require_declared("no_existe", FakeCtx())
    assert resultado is None
    assert reporter.has_errors()
    assert reporter.all()[0].category == "ambito"


def test_scope_helpers_define_or_error_reporta_redeclaracion():
    table = SymbolTable()
    reporter = ErrorReporter()
    helpers = ScopeHelpers(table=table, reporter=reporter)

    class FakeToken:
        line = 1
        column = 1

    class FakeCtx:
        start = FakeToken()

    assert helpers.define_or_error(make_var("x"), FakeCtx()) is True
    assert helpers.define_or_error(make_var("x"), FakeCtx()) is False
    assert reporter.has_errors()


def test_require_declared_retorna_el_simbolo_si_existe():
    table = SymbolTable()
    reporter = ErrorReporter()
    helpers = ScopeHelpers(table=table, reporter=reporter)
    x = make_var("x")
    table.current().define(x)

    class FakeToken:
        line = 1
        column = 1

    class FakeCtx:
        start = FakeToken()

    assert helpers.require_declared("x", FakeCtx()) is x
    assert not reporter.has_errors()


def test_resolve_local_no_sube_a_los_padres():
    table = SymbolTable()
    table.current().define(make_var("x"))
    inner = table.enter_scope("block")
    assert inner.resolve("x") is not None
    assert inner.resolve_local("x") is None
    table.exit_scope()


def test_exit_scope_no_puede_salir_del_global():
    table = SymbolTable()
    with pytest.raises(RuntimeError):
        table.exit_scope()


def test_snapshot_incluye_scopes_vivos_para_el_ide():
    table = SymbolTable()
    table.current().define(make_var("g"))
    table.enter_scope("function")
    table.current().define(make_var("f"))

    snap = table.snapshot()
    assert [kind for kind, _ in snap] == ["global", "function"]
    assert [s.name for s in snap[0][1]] == ["g"]
    assert [s.name for s in snap[1][1]] == ["f"]

    table.exit_scope()
    assert [kind for kind, _ in table.snapshot()] == ["global"]


def test_environments_conserva_scopes_cerrados_para_el_reporte():
    table = SymbolTable()
    table.current().define(make_var("g"))
    table.enter_scope("function")
    table.current().define(make_var("f"))
    table.exit_scope()
    table.enter_scope("class")
    table.current().define(make_var("c"))
    table.exit_scope()
    table.enter_scope("block")
    table.current().define(make_var("b"))
    table.exit_scope()

    kinds = [kind for kind, _ in table.environments()]
    assert kinds == ["global", "function", "class", "block"]
    names = [
        [s.name for s in symbols] for _, symbols in table.environments()
    ]
    assert names == [["g"], ["f"], ["c"], ["b"]]
    assert [kind for kind, _ in table.snapshot()] == ["global"]
    texto = table.format_environments()
    assert "[0] global" in texto
    assert "[1] function" in texto
    assert "var g: integer" in texto


def test_scope_mixin_inicializa_estado_compartido():
    from semantico.scope_mixin import ScopeMixin

    mixin = ScopeMixin()
    assert mixin.table.current().kind == "global"
    assert mixin.loop_depth == 0
    assert mixin.function_stack == []
    assert mixin.current_class is None
    assert mixin.helpers.table is mixin.table


def test_semantic_visitor_combina_mixins_y_se_puede_construir():
    from semantico.visitor import SemanticVisitor

    visitor = SemanticVisitor()
    inner = visitor.enter_scope("block")
    assert inner.kind == "block"
    assert inner.parent is visitor.table.global_scope
    visitor.exit_scope()
    assert visitor.table.current().kind == "global"

