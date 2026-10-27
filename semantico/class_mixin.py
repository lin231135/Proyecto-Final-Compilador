"""
Clases y objetos: declaracion de clases, herencia, `this`, `new` y acceso a
miembros (`obj.campo`, `obj.metodo()`), este ultimo via `_aplicar_propiedad`.

Prepass: `visitClassDeclaration` no vuelve a crear/registrar una clase
cuyo nodo ya proceso `semantico/prepass.py` (marcado por identidad en
`self._nodos_prepasados`) -- si lo hiciera, reportaria un falso "ya esta
declarada" para CADA clase del programa, porque el prepass usa el mismo
`self.clases`/scope global para resolver herencia hacia adelante.
"""

from __future__ import annotations

from core.symbols import Symbol
from core.types import ClassType, ERROR, FunctionType, VOID
from generated.CompiscriptParser import CompiscriptParser


class ClassMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.clases: dict[str, ClassType] -- registro de clases declaradas
        # (lo llena el prepass, asi la herencia hacia adelante se resuelve).
        self.clases: dict[str, ClassType] = {}

    # ------------------------------------------------------------------
    # Declaracion de clases
    # ------------------------------------------------------------------

    def visitClassDeclaration(self, ctx: "CompiscriptParser.ClassDeclarationContext") -> None:
        nombre = ctx.Identifier(0).getText()
        ya_prepasada = id(ctx) in getattr(self, "_nodos_prepasados", ())

        if ya_prepasada:
            # El prepass ya creo el ClassType, resolvio el padre y registro
            # el Symbol (o ya reporto el error correspondiente si tocaba).
            tipo_clase = self.clases[nombre]
        elif nombre in self.clases:
            self.reporter.error(ctx, "clase", f"la clase '{nombre}' ya esta declarada")
            tipo_clase = self.clases[nombre]
        else:
            tipo_clase = ClassType(name=nombre)
            self.clases[nombre] = tipo_clase
            simbolo = Symbol(
                name=nombre,
                type=tipo_clase,
                kind="class",
                initialized=True,
                line=ctx.Identifier(0).getSymbol().line,
                column=ctx.Identifier(0).getSymbol().column,
            )
            self.define_or_error(simbolo, ctx)

            if ctx.Identifier(1) is not None:
                nombre_padre = ctx.Identifier(1).getText()
                padre = self.clases.get(nombre_padre)
                if padre is None:
                    self.reporter.error(ctx, "clase", f"la clase padre '{nombre_padre}' no esta declarada")
                elif padre is tipo_clase:
                    self.reporter.error(ctx, "clase", f"la clase '{nombre}' no puede heredar de si misma")
                else:
                    tipo_clase.parent = padre

        clase_anterior = self.current_class
        self.current_class = tipo_clase
        ctx.scope = self.enter_scope("class", nombre)
        for miembro in ctx.classMember():
            self.visit(miembro)
        self.exit_scope()
        self.current_class = clase_anterior

    def visitClassMember(self, ctx: "CompiscriptParser.ClassMemberContext") -> None:
        if ctx.functionDeclaration() is not None:
            fn_ctx = ctx.functionDeclaration()
            nombre = fn_ctx.Identifier().getText()
            # Se registra ANTES de visitar el cuerpo para que el metodo sea
            # invocable via `this.<nombre>()`; 'constructor' es una
            # functionDeclaration comun con este nombre especial.
            self.current_class.methods[nombre] = self._firma_metodo(fn_ctx)
            self.visit(fn_ctx)
        elif ctx.variableDeclaration() is not None:
            vd_ctx = ctx.variableDeclaration()
            self.visit(vd_ctx)
            simbolo = self.table.current().resolve_local(vd_ctx.Identifier().getText())
            if simbolo is not None:
                self.current_class.fields[simbolo.name] = simbolo.type
        else:
            cd_ctx = ctx.constantDeclaration()
            self.visit(cd_ctx)
            simbolo = self.table.current().resolve_local(cd_ctx.Identifier().getText())
            if simbolo is not None:
                self.current_class.fields[simbolo.name] = simbolo.type

    def _firma_metodo(self, fn_ctx: "CompiscriptParser.FunctionDeclarationContext", es_metodo: bool = True) -> FunctionType:
        """
        Firma de una funcion o metodo (misma logica que
        `visitFunctionDeclaration`, que no devuelve el FunctionType que
        calcula). `semantico/prepass.py` tambien la usa para funciones
        globales, con `es_metodo=False` para que una funcion global llamada
        "constructor" no fuerce VOID (solo el constructor de una clase
        retorna VOID de forma implicita).
        """
        tipos_param = []
        if fn_ctx.parameters() is not None:
            for p in fn_ctx.parameters().parameter():
                tipos_param.append(self._tipo_parametro(p))

        if es_metodo and fn_ctx.Identifier().getText() == "constructor":
            tipo_retorno = VOID  # constructor -> retorno VOID implicito
        elif fn_ctx.type_() is not None:
            tipo_retorno = self.resolve_type_annotation(fn_ctx.type_())
        else:
            tipo_retorno = VOID

        return FunctionType(param_types=tuple(tipos_param), return_type=tipo_retorno)

    # ------------------------------------------------------------------
    # this / new
    # ------------------------------------------------------------------

    def visitThisExpr(self, ctx: "CompiscriptParser.ThisExprContext"):
        if self.current_class is None:
            self.reporter.error(ctx, "clase", "'this' solo es valido dentro de una clase")
            t = ERROR
        else:
            t = self.current_class
        ctx.tipo = t
        return t

    def visitNewExpr(self, ctx: "CompiscriptParser.NewExprContext"):
        nombre = ctx.Identifier().getText()
        tipo_clase = self.clases.get(nombre)
        if tipo_clase is None:
            self.reporter.error(ctx, "clase", f"la clase '{nombre}' no esta declarada")
            if ctx.arguments() is not None:
                for arg in ctx.arguments().expression():
                    self.get_type(arg)
            t = ERROR
            ctx.tipo = t
            return t

        # Busca en la cadena de herencia (no solo en tipo_clase.methods):
        # una subclase sin constructor propio hereda el del padre.
        constructor = tipo_clase.lookup_member("constructor")
        if isinstance(constructor, FunctionType):
            self.check_call_args(constructor, ctx.arguments(), ctx)
        else:
            # sin constructor declarado (ni heredado) se exigen 0 argumentos.
            num_args = len(ctx.arguments().expression()) if ctx.arguments() is not None else 0
            if num_args != 0:
                self.reporter.error(
                    ctx, "clase", f"'{nombre}' no declara constructor, se esperaban 0 argumentos"
                )

        ctx.tipo = tipo_clase
        return tipo_clase

    # ------------------------------------------------------------------
    # Acceso a miembros, fold de leftHandSide
    # ------------------------------------------------------------------

    def _aplicar_propiedad(self, tipo_base, ctx):
        if tipo_base == ERROR:
            return ERROR
        if not isinstance(tipo_base, ClassType):
            self.reporter.error(ctx, "clase", f"no se puede acceder a un miembro de un valor de tipo {tipo_base!r}")
            return ERROR
        nombre = ctx.Identifier().getText()
        miembro = tipo_base.lookup_member(nombre)
        if miembro is None:
            self.reporter.error(ctx, "clase", f"'{tipo_base.name}' no tiene el miembro '{nombre}'")
            return ERROR
        return miembro
