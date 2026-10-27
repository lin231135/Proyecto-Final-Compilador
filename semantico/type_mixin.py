"""
Sistema de tipos: expresiones, arreglos, declaraciones y asignaciones.

Punto clave de la gramatica: los `suffixOp` de `leftHandSide` son hermanos,
no anidados. `visitLeftHandSide` es un fold de izquierda a derecha que
delega en `_aplicar_llamada` (function_mixin.py), `_aplicar_indice` (aqui) y
`_aplicar_propiedad` (class_mixin.py).

Todo visit* de una regla de expresion devuelve un
`core.types.Type`, nunca None; se guarda ademas `ctx.tipo = t` para que el
IDE pueda mostrarlo. `get_type(ctx)` es `self.visit(ctx) or ERROR`.
"""

from __future__ import annotations

from core.symbols import Symbol
from core.types import (
    ClassType,
    BOOLEAN,
    ERROR,
    FLOAT,
    INTEGER,
    NULL,
    STRING,
    ArrayType,
    Type,
    is_assignable,
    is_numeric,
    max_tipo,
)
from generated.CompiscriptParser import CompiscriptParser


class TypeMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def get_type(self, ctx) -> Type:
        """`self.visit(ctx)` normalizado: nunca None, `ctx=None` -> ERROR."""
        if ctx is None:
            return ERROR
        t = self.visit(ctx)
        return t if t is not None else ERROR

    def _operador_binario(self, ctx, indice: int) -> str:
        """
        Texto del operador entre el operando `indice-1` y el `indice` en una
        regla con el patron `operando (OP operando)*` (los hijos quedan
        intercalados operando, OP, operando, OP, operando, ...).
        """
        return ctx.getChild(2 * indice - 1).getText()

    def resolve_type_annotation(self, ctx: "CompiscriptParser.TypeContext") -> Type:
        """
        Resuelve una regla `type` (baseType ('[' ']')*) a un core.types.Type.

        Memoizado por identidad de `ctx`: el prepass y la pasada 2
        resuelven la MISMA anotacion mas de una vez (parametro/retorno via
        `_firma_metodo` y de nuevo en `visitFunctionDeclaration`; campo de
        clase via el prepass y de nuevo en `visitVariableDeclaration`). Sin
        el cache, un tipo desconocido se reporta 2 o 3 veces por la misma
        causa.
        """
        cache = getattr(self, "_cache_tipos_resueltos", None)
        if cache is None:
            cache = {}
            self._cache_tipos_resueltos = cache
        clave = id(ctx)
        if clave in cache:
            return cache[clave]

        t = self._resolve_base_type(ctx.baseType())
        dims = (ctx.getChildCount() - 1) // 2
        for _ in range(dims):
            t = ArrayType(t)

        cache[clave] = t
        return t

    def _resolve_base_type(self, ctx: "CompiscriptParser.BaseTypeContext") -> Type:
        txt = ctx.getText()
        if txt == "boolean":
            return BOOLEAN
        if txt == "integer":
            return INTEGER
        if txt == "float":
            return FLOAT
        if txt == "string":
            return STRING
        # Identifier: nombre de clase. self.clases lo registra el prepass
        # o class_mixin.
        clase = getattr(self, "clases", {}).get(txt)
        if clase is not None:
            return clase
        self.reporter.error(ctx, "tipo", f"tipo desconocido '{txt}'")
        return ERROR

    def _check_assignment(self, ctx, tipo_destino: Type, tipo_valor: Type, es_const: bool, descripcion: str) -> None:
        """Valida una asignacion. No reporta si algun tipo ya es ERROR."""
        if es_const:
            self.reporter.error(ctx, "tipo", f"no se puede reasignar '{descripcion}': es const")
            return
        if tipo_destino == ERROR or tipo_valor == ERROR:
            return
        if not is_assignable(tipo_destino, tipo_valor):
            self.reporter.error(
                ctx,
                "tipo",
                f"no se puede asignar {tipo_valor!r} a '{descripcion}' de tipo {tipo_destino!r}",
            )

    # ------------------------------------------------------------------
    # leftHandSide (fold) y destino de asignacion
    # ------------------------------------------------------------------

    def visitLeftHandSide(self, ctx: "CompiscriptParser.LeftHandSideContext") -> Type:
        t = self.get_type(ctx.primaryAtom())
        for sufijo in ctx.suffixOp():
            if isinstance(sufijo, CompiscriptParser.CallExprContext):
                t = self._aplicar_llamada(t, sufijo)
            elif isinstance(sufijo, CompiscriptParser.IndexExprContext):
                t = self._aplicar_indice(t, sufijo)
            else:
                t = self._aplicar_propiedad(t, sufijo)
        ctx.tipo = t
        return t

    def _aplicar_indice(self, tipo_base: Type, ctx: "CompiscriptParser.IndexExprContext") -> Type:
        """`a[i]` exige `a: ArrayType` e `i: integer`; devuelve element_type."""
        tipo_indice = self.get_type(ctx.expression())
        if tipo_base == ERROR:
            return ERROR
        if not isinstance(tipo_base, ArrayType):
            self.reporter.error(ctx, "lista", f"no se puede indexar un valor de tipo {tipo_base!r}")
            return ERROR
        if tipo_indice != ERROR and tipo_indice != INTEGER:
            self.reporter.error(ctx, "lista", f"el indice debe ser integer, se recibio {tipo_indice!r}")
            return ERROR
        return tipo_base.element_type

    def resolver_destino(self, ctx: "CompiscriptParser.LeftHandSideContext") -> tuple[Type, bool, str]:
        """
        Mismo fold que visitLeftHandSide, pero se detiene antes del ultimo
        sufijo: usado por las asignaciones para saber a que se esta
        asignando (tipo, si es const, descripcion para el mensaje de error).
        """
        sufijos = ctx.suffixOp()
        atomo = ctx.primaryAtom()

        if not sufijos:
            if isinstance(atomo, CompiscriptParser.IdentifierExprContext):
                nombre = atomo.Identifier().getText()
                simbolo = self.require_declared(nombre, atomo)
                if simbolo is None:
                    return ERROR, False, nombre
                return simbolo.type, simbolo.kind == "const", nombre
            self.reporter.error(ctx, "tipo", "el destino de la asignacion no es una variable")
            return ERROR, False, "el destino"

        contenedor = self.get_type(atomo)
        for sufijo in sufijos[:-1]:
            if isinstance(sufijo, CompiscriptParser.CallExprContext):
                contenedor = self._aplicar_llamada(contenedor, sufijo)
            elif isinstance(sufijo, CompiscriptParser.IndexExprContext):
                contenedor = self._aplicar_indice(contenedor, sufijo)
            else:
                contenedor = self._aplicar_propiedad(contenedor, sufijo)

        ultimo = sufijos[-1]
        if isinstance(ultimo, CompiscriptParser.IndexExprContext):
            return self._aplicar_indice(contenedor, ultimo), False, "el elemento indexado"
        if isinstance(ultimo, CompiscriptParser.PropertyAccessExprContext):
            nombre = ultimo.Identifier().getText()
            return self._aplicar_propiedad(contenedor, ultimo), False, nombre
        self.reporter.error(ctx, "tipo", "el resultado de una llamada no es un destino valido de asignacion")
        return ERROR, False, "el destino"

    # ------------------------------------------------------------------
    # Literales y arreglos
    # ------------------------------------------------------------------

    def visitLiteralExpr(self, ctx: "CompiscriptParser.LiteralExprContext") -> Type:
        if ctx.Literal() is not None:
            # Literal es un solo token (Integer o
            # String); distinguir el tipo por el texto, no por el nombre.
            txt = ctx.Literal().getText()
            if txt.startswith('"'):
                t = STRING
            elif "." in txt:
                t = FLOAT
            else:
                t = INTEGER
        elif ctx.arrayLiteral() is not None:
            t = self.get_type(ctx.arrayLiteral())
        else:
            t = NULL if ctx.getText() == "null" else BOOLEAN
        ctx.tipo = t
        return t

    def visitArrayLiteral(self, ctx: "CompiscriptParser.ArrayLiteralContext") -> Type:
        """Todos los elementos deben tener tipos equivalentes (o numericos combinables)."""
        elementos = ctx.expression()
        if not elementos:
            # Arreglo vacio: sin informacion de tipo. ERROR aqui no reporta
            # nada y is_assignable lo trata como comodin, asi que
            # `let x: integer[] = [];` queda permitido.
            t = ArrayType(ERROR)
            ctx.tipo = t
            return t

        tipos = [self.get_type(e) for e in elementos]
        elemento = tipos[0]
        for otro in tipos[1:]:
            if elemento == ERROR or otro == ERROR:
                elemento = ERROR
                continue
            if is_numeric(elemento) and is_numeric(otro):
                elemento = max_tipo(elemento, otro)
            elif elemento != otro and self._unificar_referencias(elemento, otro) is not None:
                elemento = self._unificar_referencias(elemento, otro)
            elif elemento != otro:
                self.reporter.error(
                    ctx,
                    "lista",
                    f"elementos de tipos distintos en la lista: {elemento!r} y {otro!r}",
                )
                elemento = ERROR

        t = ArrayType(elemento)
        ctx.tipo = t
        return t

    @staticmethod
    def _unificar_referencias(a: Type, b: Type) -> Type | None:
        """Tipo comun de dos elementos de una lista cuando son referencias:
        dos clases se unifican en su ancestro comun mas cercano
        (`[new Animal(), new Perro()]` es `Animal[]`) y `null` con cualquier clase/arreglo. None si no hay."""
        refs = (ClassType, ArrayType)
        if a == NULL and isinstance(b, refs):
            return b
        if b == NULL and isinstance(a, refs):
            return a
        if isinstance(a, ClassType) and isinstance(b, ClassType):
            # ancestro comun mas cercano (a, su padre, su abuelo, ...)
            candidato = a
            while candidato is not None:
                if is_assignable(candidato, b):
                    return candidato
                candidato = candidato.parent
        return None

    # ------------------------------------------------------------------
    # Cadena aritmetico-logica
    # ------------------------------------------------------------------

    def _chequear_aritmetico(self, izq: Type, der: Type, operador: str, ctx) -> Type:
        """`+ - * %` y `/`. `+` esta sobrecargado para string+string."""
        if izq == ERROR or der == ERROR:
            return ERROR
        if operador == "+":
            if is_numeric(izq) and is_numeric(der):
                return max_tipo(izq, der)
            if izq == STRING and der == STRING:
                return STRING
            self.reporter.error(ctx, "tipo", f"el operador '+' no admite {izq!r} y {der!r}")
            return ERROR
        if is_numeric(izq) and is_numeric(der):
            return max_tipo(izq, der)
        self.reporter.error(
            ctx, "tipo", f"el operador '{operador}' requiere operandos numericos, se recibio {izq!r} y {der!r}"
        )
        return ERROR

    def visitAdditiveExpr(self, ctx: "CompiscriptParser.AdditiveExprContext") -> Type:
        operandos = ctx.multiplicativeExpr()
        t = self.get_type(operandos[0])
        for i in range(1, len(operandos)):
            operador = self._operador_binario(ctx, i)
            t = self._chequear_aritmetico(t, self.get_type(operandos[i]), operador, ctx)
        ctx.tipo = t
        return t

    def visitMultiplicativeExpr(self, ctx: "CompiscriptParser.MultiplicativeExprContext") -> Type:
        operandos = ctx.unaryExpr()
        t = self.get_type(operandos[0])
        for i in range(1, len(operandos)):
            operador = self._operador_binario(ctx, i)
            t = self._chequear_aritmetico(t, self.get_type(operandos[i]), operador, ctx)
        ctx.tipo = t
        return t

    def visitUnaryExpr(self, ctx: "CompiscriptParser.UnaryExprContext") -> Type:
        if ctx.primaryExpr() is not None:
            t = self.get_type(ctx.primaryExpr())
            ctx.tipo = t
            return t

        operando = self.get_type(ctx.unaryExpr())
        operador = ctx.getChild(0).getText()
        if operando == ERROR:
            t = ERROR
        elif operador == "-":
            if is_numeric(operando):
                t = operando
            else:
                self.reporter.error(
                    ctx, "tipo", f"el operador unario '-' requiere un operando numerico, se recibio {operando!r}"
                )
                t = ERROR
        else:  # '!'
            if operando == BOOLEAN:
                t = BOOLEAN
            else:
                self.reporter.error(ctx, "tipo", f"el operador '!' requiere boolean, se recibio {operando!r}")
                t = ERROR
        ctx.tipo = t
        return t

    # ------------------------------------------------------------------
    # Comparaciones
    # ------------------------------------------------------------------

    def visitRelationalExpr(self, ctx: "CompiscriptParser.RelationalExprContext") -> Type:
        operandos = ctx.additiveExpr()
        if len(operandos) == 1:
            # Sin operador de comparacion: esta regla solo esta de paso en
            # la cadena de precedencia, el tipo es el del operando.
            t = self.get_type(operandos[0])
            ctx.tipo = t
            return t
        tipos = [self.get_type(o) for o in operandos]
        hubo_error = False
        for i in range(1, len(tipos)):
            izq, der = tipos[i - 1], tipos[i]
            if izq == ERROR or der == ERROR:
                hubo_error = True
                continue
            if not (is_numeric(izq) and is_numeric(der)):
                operador = self._operador_binario(ctx, i)
                self.reporter.error(
                    ctx,
                    "tipo",
                    f"el operador '{operador}' requiere operandos numericos, se recibio {izq!r} y {der!r}",
                )
                hubo_error = True
        t = ERROR if hubo_error else BOOLEAN
        ctx.tipo = t
        return t

    def visitEqualityExpr(self, ctx: "CompiscriptParser.EqualityExprContext") -> Type:
        operandos = ctx.relationalExpr()
        if len(operandos) == 1:
            t = self.get_type(operandos[0])
            ctx.tipo = t
            return t
        tipos = [self.get_type(o) for o in operandos]
        hubo_error = False
        for i in range(1, len(tipos)):
            izq, der = tipos[i - 1], tipos[i]
            if izq == ERROR or der == ERROR:
                hubo_error = True
                continue
            # tipos equivalentes; numerico-numerico se acepta aunque
            # sean integer/float distintos (mismo dominio numerico).
            equivalentes = (is_numeric(izq) and is_numeric(der)) or izq == der
            # `obj == null` / `lista != null`: null es comparable con
            # referencias (clases y arreglos), igual que es asignable a ellas.
            if not equivalentes and NULL in (izq, der):
                otro = der if izq == NULL else izq
                equivalentes = isinstance(otro, (ClassType, ArrayType))
            if not equivalentes:
                operador = self._operador_binario(ctx, i)
                self.reporter.error(
                    ctx, "tipo", f"el operador '{operador}' compara tipos distintos: {izq!r} y {der!r}"
                )
                hubo_error = True
        t = ERROR if hubo_error else BOOLEAN
        ctx.tipo = t
        return t

    # ------------------------------------------------------------------
    # Logicos
    # ------------------------------------------------------------------

    def _fold_logico(self, ctx, operandos, operador: str) -> Type:
        if len(operandos) == 1:
            return self.get_type(operandos[0])
        tipos = [self.get_type(o) for o in operandos]
        hubo_error = False
        for t in tipos:
            if t == ERROR:
                hubo_error = True
            elif t != BOOLEAN:
                self.reporter.error(ctx, "tipo", f"el operador '{operador}' requiere operandos boolean, se recibio {t!r}")
                hubo_error = True
        return ERROR if hubo_error else BOOLEAN

    def visitLogicalAndExpr(self, ctx: "CompiscriptParser.LogicalAndExprContext") -> Type:
        t = self._fold_logico(ctx, ctx.equalityExpr(), "&&")
        ctx.tipo = t
        return t

    def visitLogicalOrExpr(self, ctx: "CompiscriptParser.LogicalOrExprContext") -> Type:
        t = self._fold_logico(ctx, ctx.logicalAndExpr(), "||")
        ctx.tipo = t
        return t

    # ------------------------------------------------------------------
    # Ternario / passthrough de expresiones
    # ------------------------------------------------------------------

    def visitTernaryExpr(self, ctx: "CompiscriptParser.TernaryExprContext") -> Type:
        cond = self.get_type(ctx.logicalOrExpr())
        ramas = ctx.expression()

        if not ramas:
            ctx.tipo = cond
            return cond

        if cond != ERROR and cond != BOOLEAN:
            self.reporter.error(ctx, "tipo", f"la condicion del operador ternario debe ser boolean, se recibio {cond!r}")

        entonces = self.get_type(ramas[0])
        sino = self.get_type(ramas[1])
        if entonces == ERROR or sino == ERROR:
            t = ERROR
        elif is_numeric(entonces) and is_numeric(sino):
            t = max_tipo(entonces, sino)
        elif entonces == sino:
            t = entonces
        else:
            self.reporter.error(
                ctx, "tipo", f"las ramas del operador ternario tienen tipos distintos: {entonces!r} y {sino!r}"
            )
            t = ERROR
        ctx.tipo = t
        return t

    def visitExprNoAssign(self, ctx: "CompiscriptParser.ExprNoAssignContext") -> Type:
        t = self.get_type(ctx.conditionalExpr())
        ctx.tipo = t
        return t

    def visitPrimaryExpr(self, ctx: "CompiscriptParser.PrimaryExprContext") -> Type:
        if ctx.literalExpr() is not None:
            t = self.get_type(ctx.literalExpr())
        elif ctx.leftHandSide() is not None:
            t = self.get_type(ctx.leftHandSide())
        else:
            t = self.get_type(ctx.expression())
        ctx.tipo = t
        return t

    # ------------------------------------------------------------------
    # Declaraciones y asignaciones
    # ------------------------------------------------------------------

    def visitVariableDeclaration(self, ctx: "CompiscriptParser.VariableDeclarationContext") -> None:
        nombre = ctx.Identifier().getText()

        tipo_anotado = None
        if ctx.typeAnnotation() is not None:
            tipo_anotado = self.resolve_type_annotation(ctx.typeAnnotation().type_())

        tipo_valor = None
        if ctx.initializer() is not None:
            tipo_valor = self.get_type(ctx.initializer().expression())

        if tipo_anotado is not None and tipo_valor is not None:
            self._check_assignment(ctx, tipo_anotado, tipo_valor, False, nombre)
            tipo_final = tipo_anotado
        elif tipo_anotado is not None:
            tipo_final = tipo_anotado
        elif tipo_valor is not None:
            # `let d = null;` sin anotacion -> el simbolo queda con
            # tipo NULL y acepta reasignacion posterior de clase/arreglo.
            tipo_final = tipo_valor
        else:
            tipo_final = ERROR
            self.reporter.error(ctx, "tipo", f"'{nombre}' necesita anotacion de tipo o inicializador")

        simbolo = Symbol(
            name=nombre,
            type=tipo_final,
            kind="var",
            initialized=ctx.initializer() is not None,
            line=ctx.Identifier().getSymbol().line,
            column=ctx.Identifier().getSymbol().column,
        )
        self.define_or_error(simbolo, ctx)

    def visitConstantDeclaration(self, ctx: "CompiscriptParser.ConstantDeclarationContext") -> None:
        nombre = ctx.Identifier().getText()

        tipo_anotado = None
        if ctx.typeAnnotation() is not None:
            tipo_anotado = self.resolve_type_annotation(ctx.typeAnnotation().type_())

        tipo_valor = self.get_type(ctx.expression())

        if tipo_anotado is not None:
            self._check_assignment(ctx, tipo_anotado, tipo_valor, False, nombre)
            tipo_final = tipo_anotado
        else:
            tipo_final = tipo_valor

        simbolo = Symbol(
            name=nombre,
            type=tipo_final,
            kind="const",
            initialized=True,
            line=ctx.Identifier().getSymbol().line,
            column=ctx.Identifier().getSymbol().column,
        )
        self.define_or_error(simbolo, ctx)

    def visitAssignment(self, ctx: "CompiscriptParser.AssignmentContext") -> None:
        expresiones = ctx.expression()
        if len(expresiones) == 1:
            nombre = ctx.Identifier().getText()
            tipo_valor = self.get_type(expresiones[0])
            simbolo = self.require_declared(nombre, ctx)
            if simbolo is None:
                return
            self._check_assignment(ctx, simbolo.type, tipo_valor, simbolo.kind == "const", nombre)
            return

        # expression '.' Identifier '=' expression
        contenedor = self.get_type(expresiones[0])
        nombre = ctx.Identifier().getText()
        tipo_destino = self._aplicar_propiedad(contenedor, ctx)
        tipo_valor = self.get_type(expresiones[1])
        self._check_assignment(ctx, tipo_destino, tipo_valor, False, nombre)

    def visitAssignExpr(self, ctx: "CompiscriptParser.AssignExprContext") -> Type:
        tipo_destino, es_const, descripcion = self.resolver_destino(ctx.lhs)
        tipo_valor = self.get_type(ctx.assignmentExpr())
        self._check_assignment(ctx, tipo_destino, tipo_valor, es_const, descripcion)
        t = ERROR if tipo_destino == ERROR else tipo_destino
        ctx.tipo = t
        return t

    def visitPropertyAssignExpr(self, ctx: "CompiscriptParser.PropertyAssignExprContext") -> Type:
        contenedor = self.get_type(ctx.lhs)
        nombre = ctx.Identifier().getText()
        tipo_destino = self._aplicar_propiedad(contenedor, ctx)
        tipo_valor = self.get_type(ctx.assignmentExpr())
        self._check_assignment(ctx, tipo_destino, tipo_valor, False, nombre)
        t = ERROR if tipo_destino == ERROR else tipo_destino
        ctx.tipo = t
        return t
