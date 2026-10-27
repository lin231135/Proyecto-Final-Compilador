"""
Ambitos, funciones y control de flujo: bloques, resolucion de nombres,
declaracion y llamada de funciones, return/break/continue, condiciones,
for/foreach/try-catch/switch y deteccion de codigo muerto.

Prepass: `visitFunctionDeclaration` no vuelve a declarar (ni a reportar un
falso "ya esta declarado" de) una funcion global cuyo nodo ya proceso
`semantico/prepass.py` (marcado por identidad en `self._nodos_prepasados`);
es lo que permite la recursion mutua entre funciones globales sin que la
funcion se declare dos veces.
"""

from __future__ import annotations

from antlr4.tree.Tree import TerminalNode

from core.symbols import Symbol
from core.types import (
    ArrayType,
    BOOLEAN,
    ERROR,
    FunctionType,
    STRING,
    VOID,
    is_assignable,
)
from generated.CompiscriptParser import CompiscriptParser
from semantico import config


class FunctionMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Puesta por visitFunctionDeclaration antes de visitar el cuerpo:
        # el bloque de una funcion no debe abrir OTRO scope (si no, un
        # parametro redeclarado en el cuerpo no se detectaria).
        self._omitir_scope_de_bloque = False
        # 'break' tambien es valido dentro de un switch (corta el fallthrough).
        self.switch_depth = 0

    # ------------------------------------------------------------------
    # Bloques y codigo muerto
    # ------------------------------------------------------------------

    def visitBlock(self, ctx: "CompiscriptParser.BlockContext") -> None:
        omitir = self._omitir_scope_de_bloque
        self._omitir_scope_de_bloque = False
        if not omitir:
            etiqueta = self._etiqueta_bloque
            self._etiqueta_bloque = ""
            ctx.scope = self.enter_scope("block", etiqueta)
        self._visitar_y_escanear(ctx.statement())
        if not omitir:
            self.exit_scope()

    def _visitar_y_escanear(self, statements) -> None:
        for stmt in statements:
            self.visit(stmt)
        self._escanear_codigo_muerto(statements)

    def _escanear_codigo_muerto(self, statements) -> None:
        """Una sentencia despues de return/break/continue nunca se alcanza."""
        for i, stmt in enumerate(statements):
            if self._es_terminador(stmt) and i + 1 < len(statements):
                self.reporter.error(
                    statements[i + 1], "general", "codigo muerto: esta sentencia nunca se ejecuta"
                )
                break

    def _es_terminador(self, stmt: "CompiscriptParser.StatementContext") -> bool:
        return (
            stmt.returnStatement() is not None
            or stmt.breakStatement() is not None
            or stmt.continueStatement() is not None
        )

    # ------------------------------------------------------------------
    # Resolucion de identificadores
    # ------------------------------------------------------------------

    def visitIdentifierExpr(self, ctx: "CompiscriptParser.IdentifierExprContext"):
        nombre = ctx.Identifier().getText()
        simbolo = self.require_declared(nombre, ctx)
        t = simbolo.type if simbolo is not None else ERROR
        ctx.tipo = t
        return t

    # ------------------------------------------------------------------
    # Funciones
    # ------------------------------------------------------------------

    def visitFunctionDeclaration(self, ctx: "CompiscriptParser.FunctionDeclarationContext") -> None:
        nombre = ctx.Identifier().getText()

        tipos_param = []
        if ctx.parameters() is not None:
            for p in ctx.parameters().parameter():
                tipos_param.append(self._tipo_parametro(p))

        if self.current_class is not None and nombre == "constructor":
            # constructor -> retorno VOID implicito, sin importar
            # lo que se haya escrito despues de ':'.
            tipo_retorno = VOID
        elif ctx.type_() is not None:
            tipo_retorno = self.resolve_type_annotation(ctx.type_())
        else:
            tipo_retorno = VOID  # sin ': type' -> VOID

        tipo_funcion = FunctionType(param_types=tuple(tipos_param), return_type=tipo_retorno)

        ya_prepasada = id(ctx) in getattr(self, "_nodos_prepasados", ())
        if self.current_class is None and not ya_prepasada:
            # el nombre queda visible ANTES de visitar el cuerpo,
            # en el scope donde se declara (global o el de una funcion
            # contenedora) -> recursion directa/mutua y funciones anidadas.
            # Una funcion global ya la declara el prepass para que la
            # recursion mutua no dependa del orden de declaracion; aqui solo
            # falta visitar su cuerpo.
            simbolo = Symbol(
                name=nombre,
                type=tipo_funcion,
                kind="function",
                initialized=True,
                line=ctx.Identifier().getSymbol().line,
                column=ctx.Identifier().getSymbol().column,
            )
            self.define_or_error(simbolo, ctx)
        # Si current_class no es None, el metodo lo registra el prepass o
        # class_mixin directamente en ClassType.methods; aqui solo se visita el
        # cuerpo.

        ctx.scope = self.enter_scope("function", nombre)
        if ctx.parameters() is not None:
            self.visit(ctx.parameters())

        self.function_stack.append((nombre, tipo_retorno))
        self._omitir_scope_de_bloque = True
        self.visit(ctx.block())
        self.function_stack.pop()

        self.exit_scope()

    def visitParameters(self, ctx: "CompiscriptParser.ParametersContext") -> None:
        for p in ctx.parameter():
            self.visit(p)

    def visitParameter(self, ctx: "CompiscriptParser.ParameterContext") -> None:
        nombre = ctx.Identifier().getText()
        tipo = self._tipo_parametro(ctx)
        simbolo = Symbol(
            name=nombre,
            type=tipo,
            kind="param",
            initialized=True,
            line=ctx.Identifier().getSymbol().line,
            column=ctx.Identifier().getSymbol().column,
        )
        self.define_or_error(simbolo, ctx)

    def _tipo_parametro(self, ctx: "CompiscriptParser.ParameterContext"):
        if ctx.type_() is not None:
            return self.resolve_type_annotation(ctx.type_())
        # Sin anotacion no hay con que validar los argumentos de una
        # llamada; ERROR actua como comodin sin reportar nada aqui.
        return ERROR

    def check_call_args(self, tipo_funcion: FunctionType, args_ctx, ctx) -> None:
        """Valida cantidad y tipo (posicional) de los argumentos de una llamada."""
        argumentos = args_ctx.expression() if args_ctx is not None else []
        esperados = tipo_funcion.param_types
        if len(argumentos) != len(esperados):
            self.reporter.error(
                ctx,
                "funcion",
                f"se esperaban {len(esperados)} argumento(s), se recibieron {len(argumentos)}",
            )
            return
        for esperado, arg in zip(esperados, argumentos):
            tipo_arg = self.get_type(arg)
            if esperado != ERROR and tipo_arg != ERROR and not is_assignable(esperado, tipo_arg):
                self.reporter.error(
                    arg,
                    "funcion",
                    f"argumento de tipo {tipo_arg!r} no es asignable al parametro de tipo {esperado!r}",
                )

    def _aplicar_llamada(self, tipo_base, ctx: "CompiscriptParser.CallExprContext"):
        if tipo_base == ERROR:
            return ERROR
        if not isinstance(tipo_base, FunctionType):
            self.reporter.error(ctx, "funcion", f"no se puede invocar un valor de tipo {tipo_base!r}")
            return ERROR
        self.check_call_args(tipo_base, ctx.arguments(), ctx)
        return tipo_base.return_type

    # ------------------------------------------------------------------
    # return / break / continue
    # ------------------------------------------------------------------

    def visitReturnStatement(self, ctx: "CompiscriptParser.ReturnStatementContext") -> None:
        if not self.function_stack:
            self.reporter.error(ctx, "control_flujo", "'return' solo es valido dentro de una funcion")
            if ctx.expression() is not None:
                self.get_type(ctx.expression())
            return

        _, tipo_retorno_declarado = self.function_stack[-1]

        if ctx.expression() is None:
            if tipo_retorno_declarado != VOID:
                self.reporter.error(
                    ctx,
                    "funcion",
                    f"la funcion debe retornar {tipo_retorno_declarado!r}, 'return;' no retorna nada",
                )
            return

        tipo_valor = self.get_type(ctx.expression())
        if tipo_valor == ERROR:
            return
        if not is_assignable(tipo_retorno_declarado, tipo_valor):
            self.reporter.error(
                ctx,
                "funcion",
                f"la funcion declara retorno {tipo_retorno_declarado!r}, se retorno {tipo_valor!r}",
            )

    def visitBreakStatement(self, ctx: "CompiscriptParser.BreakStatementContext") -> None:
        if self.loop_depth <= 0 and self.switch_depth <= 0:
            self.reporter.error(ctx, "control_flujo", "'break' solo es valido dentro de un bucle o un switch")

    def visitContinueStatement(self, ctx: "CompiscriptParser.ContinueStatementContext") -> None:
        if self.loop_depth <= 0:
            self.reporter.error(ctx, "control_flujo", "'continue' solo es valido dentro de un bucle")

    # ------------------------------------------------------------------
    # Condiciones de control de flujo
    # ------------------------------------------------------------------

    def _verificar_condicion_booleana(self, expr_ctx, nombre_sentencia: str) -> None:
        t = self.get_type(expr_ctx)
        if t != ERROR and t != BOOLEAN:
            self.reporter.error(
                expr_ctx, "control_flujo", f"la condicion de '{nombre_sentencia}' debe ser boolean, se recibio {t!r}"
            )

    def visitIfStatement(self, ctx: "CompiscriptParser.IfStatementContext") -> None:
        self._verificar_condicion_booleana(ctx.expression(), "if")
        bloques = ctx.block()
        self._etiqueta_bloque = "if"
        self.visit(bloques[0])
        if len(bloques) > 1:
            self._etiqueta_bloque = "else"
            self.visit(bloques[1])

    def visitWhileStatement(self, ctx: "CompiscriptParser.WhileStatementContext") -> None:
        self._verificar_condicion_booleana(ctx.expression(), "while")
        self.loop_depth += 1
        self._etiqueta_bloque = "while"
        self.visit(ctx.block())
        self.loop_depth -= 1

    def visitDoWhileStatement(self, ctx: "CompiscriptParser.DoWhileStatementContext") -> None:
        self.loop_depth += 1
        self._etiqueta_bloque = "do-while"
        self.visit(ctx.block())
        self.loop_depth -= 1
        self._verificar_condicion_booleana(ctx.expression(), "do-while")

    def _partir_for(self, ctx: "CompiscriptParser.ForStatementContext"):
        """
        `forStatement` siempre tiene dos slots `expression?` (condicion e
        incremento) separados por un ';' explicito propio de la regla. Ese
        ';' es el ULTIMO terminal ';' que es hijo directo del contexto: si
        el init es vacio hay dos (el del init y el de la regla); si el init
        es variableDeclaration/assignment, el ';' de esos ya queda dentro de
        su propio subarbol, asi que solo aparece el de la regla.
        """
        hijos = list(ctx.children)
        indices_punto_y_coma = [
            i for i, h in enumerate(hijos) if isinstance(h, TerminalNode) and h.getText() == ";"
        ]
        indice_medio = indices_punto_y_coma[-1]
        cond = None
        incr = None
        for i, h in enumerate(hijos):
            if isinstance(h, CompiscriptParser.ExpressionContext):
                if i < indice_medio:
                    cond = h
                else:
                    incr = h
        return cond, incr

    def visitForStatement(self, ctx: "CompiscriptParser.ForStatementContext") -> None:
        # Scope propio para el init (`let i`), antes de la condicion.
        ctx.scope = self.enter_scope("block", "for")
        if ctx.variableDeclaration() is not None:
            self.visit(ctx.variableDeclaration())
        elif ctx.assignment() is not None:
            self.visit(ctx.assignment())

        cond, incr = self._partir_for(ctx)
        if cond is not None:
            self._verificar_condicion_booleana(cond, "for")
        if incr is not None:
            self.get_type(incr)

        self.loop_depth += 1
        self._etiqueta_bloque = "cuerpo for"
        self.visit(ctx.block())  # el cuerpo abre su propio scope
        self.loop_depth -= 1

        self.exit_scope()

    def visitForeachStatement(self, ctx: "CompiscriptParser.ForeachStatementContext") -> None:
        nombre = ctx.Identifier().getText()
        tipo_iterable = self.get_type(ctx.expression())
        if isinstance(tipo_iterable, ArrayType):
            tipo_elemento = tipo_iterable.element_type
        elif tipo_iterable == ERROR:
            tipo_elemento = ERROR
        else:
            self.reporter.error(ctx, "control_flujo", f"'foreach' espera un arreglo, se recibio {tipo_iterable!r}")
            tipo_elemento = ERROR

        ctx.scope = self.enter_scope("block", f"foreach {nombre}")
        simbolo = Symbol(
            name=nombre,
            type=tipo_elemento,
            kind="var",
            initialized=True,
            line=ctx.Identifier().getSymbol().line,
            column=ctx.Identifier().getSymbol().column,
        )
        self.define_or_error(simbolo, ctx)

        self.loop_depth += 1
        self._etiqueta_bloque = "cuerpo foreach"
        self.visit(ctx.block())
        self.loop_depth -= 1

        self.exit_scope()

    def visitTryCatchStatement(self, ctx: "CompiscriptParser.TryCatchStatementContext") -> None:
        self._etiqueta_bloque = "try"
        self.visit(ctx.block(0))

        ctx.scope = self.enter_scope("block", "catch")
        nombre = ctx.Identifier().getText()
        # el parametro de catch(err) se declara como string.
        simbolo = Symbol(
            name=nombre,
            type=STRING,
            kind="var",
            initialized=True,
            line=ctx.Identifier().getSymbol().line,
            column=ctx.Identifier().getSymbol().column,
        )
        self.define_or_error(simbolo, ctx)
        self._omitir_scope_de_bloque = True
        self.visit(ctx.block(1))
        self.exit_scope()

    # ------------------------------------------------------------------
    # switch
    # ------------------------------------------------------------------

    def visitSwitchStatement(self, ctx: "CompiscriptParser.SwitchStatementContext") -> None:
        tipo_switch = self.get_type(ctx.expression())
        if config.SWITCH_EXIGE_BOOLEAN and tipo_switch != ERROR and tipo_switch != BOOLEAN:
            self.reporter.error(
                ctx, "control_flujo", f"la expresion del switch debe ser boolean, se recibio {tipo_switch!r}"
            )

        self.switch_depth += 1
        for caso in ctx.switchCase():
            tipo_caso = self.get_type(caso.expression())
            if tipo_switch != ERROR and tipo_caso != ERROR and tipo_switch != tipo_caso:
                self.reporter.error(
                    caso, "control_flujo", f"el 'case' es de tipo {tipo_caso!r}, se esperaba {tipo_switch!r}"
                )
            self.visit(caso)

        if ctx.defaultCase() is not None:
            self.visit(ctx.defaultCase())
        self.switch_depth -= 1

    def visitSwitchCase(self, ctx: "CompiscriptParser.SwitchCaseContext") -> None:
        self._visitar_y_escanear(ctx.statement())

    def visitDefaultCase(self, ctx: "CompiscriptParser.DefaultCaseContext") -> None:
        self._visitar_y_escanear(ctx.statement())
