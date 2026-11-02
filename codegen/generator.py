"""
Generador de codigo intermedio (TAC): Visitor de ANTLR sobre el arbol
sintactico que ya valido el analizador semantico (`semantico/`).

Contrato con la fase semantica
  - Solo se ejecuta si el analisis no reporto errores.
  - Reusa los `Scope` del analisis: el semantico deja en cada contexto que
    abre un entorno (`function`, `class`, `block`, `for`, `foreach`, `catch`)
    el atributo `ctx.scope`. Asi `scope.resolve(nombre)` devuelve el MISMO
    `Symbol` que creo el semantico, y este generador lo completa con
    storage/offset/size/etiqueta/AR (tabla de simbolos extendida).
  - Usa los tipos que el semantico anota en `ctx.tipo`.

Cada visit* de expresion devuelve un *lugar* (place): variable, temporal,
literal o `@global` / `upN.var` / `this`. Las sentencias no devuelven nada.

Reciclaje de temporales: cada operando se libera en cuanto se consume
(`free` justo despues de emitir la instruccion que lo usa) y el resultado se
asigna despues, de modo que puede reutilizar el temporal de un operando.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from codegen import tac as T
from codegen.tac import TACFunction, TACProgram, TempManager, is_temp
from core.memory import (
    ActivationRecord,
    ClassLayout,
    ClosureAccess,
    FieldInfo,
    _align,
    size_of,
)
from core.symbols import Scope, Symbol, SymbolTable
from core.types import (
    BOOLEAN,
    ERROR,
    FLOAT,
    INTEGER,
    NULL,
    STRING,
    VOID,
    ArrayType,
    ClassType,
    FunctionType,
    Type,
    is_numeric,
    max_tipo,
)
from generated.CompiscriptParser import CompiscriptParser as P
from generated.CompiscriptVisitor import CompiscriptVisitor

_NUM_RE = re.compile(r"^\d+(\.\d+)?$")
_UP_RE = re.compile(r"^up(\d+)\.(.+)$")
OBJECT_HEADER = 8  # puntero al descriptor de clase (despacho virtual)


def _base_de_lista(tipo: Type | None) -> Type | None:
    """Tipo escalar de una lista (de cualquier dimension); None si no es lista."""
    if not isinstance(tipo, ArrayType):
        return None
    while isinstance(tipo, ArrayType):
        tipo = tipo.element_type
    return tipo


def _hereda(clase: ClassType | None, ancestro: ClassType) -> bool:
    while clase is not None:
        if clase == ancestro:
            return True
        clase = clase.parent
    return False


class CodegenError(Exception):
    """Error interno del generador (el programa paso el semantico pero usa algo no soportado)."""


@dataclass
class FuncState:
    name: str
    ar: ActivationRecord
    tac: TACFunction
    temps: TempManager = field(default_factory=TempManager)
    # (etiqueta de break, etiqueta de continue, try abiertos al entrar al bucle)
    loops: list[tuple[str, str | None, int]] = field(default_factory=list)
    is_main: bool = False
    ret_type: Type | None = None
    temp_tipos: dict[str, Type | None] = field(default_factory=dict)  # tipo actual de cada temporal
    try_depth: int = 0  # bloques `try` abiertos en este punto


class TACGenerator(CompiscriptVisitor):
    def __init__(self, table: SymbolTable, clases: dict[str, ClassType] | None = None):
        super().__init__()
        self.table = table
        self.clases = clases or {}
        self.scope: Scope = table.global_scope
        self.program = TACProgram()
        self.layouts: dict[str, ClassLayout] = {}
        self.class_decls: dict[str, P.ClassDeclarationContext] = {}
        self.global_area = ActivationRecord("<globales>", kind="global")
        self.activation_records: list[ActivationRecord] = []
        self.closure_accesses: list[ClosureAccess] = []
        self.temp_leaks = 0  # temporales vivos al terminar una sentencia (debe ser 0)
        self._label_count = 0
        self._labels_usados: set[str] = {"main"}  # `main` es el programa principal
        # Construcciones que el TAC representa pero que no se pueden traducir
        # a un back-end con tipos estaticos; `backend/` las reporta como error.
        self.errores_backend: list[str] = []
        self.fn: FuncState = None  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Punto de entrada
    # ------------------------------------------------------------------

    def generate(self, tree: P.ProgramContext) -> TACProgram:
        self._collect_classes(tree)
        for nombre in self.class_decls:
            self._layout_of(nombre, set())

        main_ar = ActivationRecord("main", kind="main")
        self.activation_records.append(main_ar)
        main = FuncState("main", main_ar, TACFunction("main"), is_main=True)
        self.fn = main

        # Las funciones globales llevan su propio nombre como etiqueta, asi
        # una llamada puede preceder (en el texto) a la declaracion.
        for layout in self.layouts.values():
            self._labels_usados.update(f"{layout.name}.{m}" for m in layout.own_methods)
        for stmt in tree.statement():
            fd = stmt.functionDeclaration()
            if fd is not None:
                sym = self.table.global_scope.resolve_local(fd.Identifier().getText())
                if sym is not None:
                    sym.label = self._etiqueta_unica(sym.name)
                    sym.storage = "function"

        for stmt in tree.statement():
            self.visit(stmt)

        main.tac.temp_count = main.tac.used_temp_count()
        main_ar.finalize(main.tac.temp_count)
        self.program.functions.append(main.tac)
        return self.program

    # ------------------------------------------------------------------
    # Clases: coleccion y layout
    # ------------------------------------------------------------------

    def _collect_classes(self, node) -> None:
        if isinstance(node, P.ClassDeclarationContext):
            self.class_decls.setdefault(node.Identifier(0).getText(), node)
        for hijo in getattr(node, "children", None) or []:
            self._collect_classes(hijo)

    def _layout_of(self, nombre: str, en_proceso: set[str]) -> ClassLayout | None:
        if nombre in self.layouts:
            return self.layouts[nombre]
        cd = self.class_decls.get(nombre)
        if cd is None or nombre in en_proceso:
            return None
        en_proceso.add(nombre)
        padre = None
        if cd.Identifier(1) is not None:
            padre = self._layout_of(cd.Identifier(1).getText(), en_proceso)
        layout = ClassLayout(name=nombre, parent=padre)
        offset = padre.instance_size if padre else OBJECT_HEADER
        if padre:
            layout.fields.update(padre.fields)
        ct = self.clases.get(nombre)
        for miembro in cd.classMember():
            decl = miembro.variableDeclaration() or miembro.constantDeclaration()
            if decl is not None:
                fname = decl.Identifier().getText()
                tipo = ct.fields.get(fname) if ct is not None else None
                size = size_of(tipo)
                offset = _align(offset, size)
                layout.fields[fname] = FieldInfo(fname, tipo, offset, size, nombre)
                offset += size
                if miembro.constantDeclaration() is not None or decl.initializer() is not None:
                    layout.has_initializers = True
            else:
                layout.own_methods.append(miembro.functionDeclaration().Identifier().getText())
        layout.instance_size = _align(offset, 8)
        self.layouts[nombre] = layout
        return layout

    def _es_sobreescrito(self, estatica: ClassLayout, metodo: str) -> bool:
        """True si alguna subclase estricta de `estatica` redefine `metodo`
        (entonces la llamada debe despacharse en tiempo de ejecucion)."""
        for otra in self.layouts.values():
            if otra is not estatica and estatica in otra.ancestry() and metodo in otra.own_methods:
                return True
        return False

    # ------------------------------------------------------------------
    # Utilidades de emision
    # ------------------------------------------------------------------

    def emit(self, instr: T.Instr, tipo: Type | None = None) -> T.Instr:
        """Agrega `instr` anotada con el tipo del valor que define."""
        instr.ty = tipo
        if is_temp(instr.dst):
            self.fn.temp_tipos[instr.dst] = tipo
        return self.fn.tac.emit(instr)

    def temp(self) -> str:
        return self.fn.temps.new_temp()

    def free(self, *places: str | None) -> None:
        for p in places:
            self.fn.temps.free(p)

    def new_label(self) -> str:
        self._label_count += 1
        return f"L{self._label_count}"

    def emit_assign(self, destino: str, lugar: str) -> None:
        """`destino = lugar`, fusionando con la instruccion que produjo el
        temporal `lugar` si esa fue la ultima (`t1 = a + b; x = t1` -> `x = a + b`)."""
        instrs = self.fn.tac.instructions
        if (
            is_temp(lugar)
            and instrs
            and instrs[-1].op in T.DEFINING_OPS
            and instrs[-1].dst == lugar
        ):
            instrs[-1].dst = destino
            if is_temp(destino):
                self.fn.temp_tipos[destino] = instrs[-1].ty
        else:
            self.emit(T.copy(destino, lugar), self._tipo_lugar(lugar))
        self.free(lugar)

    # ------------------------------------------------------------------
    # Tipos: el TAC se imprime sin tipos, pero cada instruccion los lleva
    # anotados y la conversion integer -> float se hace explicita (`itof`)
    # ------------------------------------------------------------------

    def _tipo_lugar(self, lugar: str | None) -> Type | None:
        """Tipo estatico del valor que hay en `lugar`."""
        if lugar is None:
            return None
        if lugar in ("true", "false"):
            return BOOLEAN
        if lugar == "null":
            return NULL
        if lugar.startswith('"'):
            return STRING
        if _NUM_RE.match(lugar.lstrip("-")):
            return FLOAT if "." in lugar else INTEGER
        if is_temp(lugar):
            return self.fn.temp_tipos.get(lugar)
        if lugar.startswith("@"):
            return self.global_area.slot(lugar[1:]).type
        m = _UP_RE.match(lugar)
        ar, nombre = self.fn.ar, lugar
        if m:
            for _ in range(int(m.group(1))):
                ar = ar.parent
            nombre = m.group(2)
        ranura = ar.slot(nombre)
        return ranura.type if ranura is not None else None

    def _convertir(self, lugar: str, destino: Type | None) -> str:
        """Conversion implicita de `lugar` al tipo `destino` (integer -> float)."""
        tipo = self._tipo_lugar(lugar)
        if destino == FLOAT and tipo == INTEGER:
            if not is_temp(lugar) and _NUM_RE.match(lugar.lstrip("-")):
                return f"{lugar}.0"
            self.free(lugar)
            dst = self.temp()
            self.emit(T.itof(dst, lugar), FLOAT)
            return dst
        if _base_de_lista(destino) == FLOAT and _base_de_lista(tipo) == INTEGER:
            self.errores_backend.append(
                f"no se puede convertir la lista de tipo {tipo!r} a {destino!r} sin copiarla: "
                "use una lista de float desde el inicio"
            )
        return lugar

    def _visitar_como(self, ctx, destino: Type | None) -> str:
        """Evalua `ctx` y lo convierte a `destino`. Un literal de lista toma
        directamente el tipo de elemento esperado (`let a: float[] = [1, 2]`)."""
        n = self._peel(ctx)
        if isinstance(n, P.LiteralExprContext) and n.arrayLiteral() is not None and isinstance(destino, ArrayType):
            return self._lista(n.arrayLiteral(), destino.element_type)
        return self._convertir(self.visit(ctx), destino)

    def _unificar_numericos(self, a: str, b: str) -> tuple[str, str]:
        """En una operacion integer-float el integer se convierte a float."""
        ta, tb = self._tipo_lugar(a), self._tipo_lugar(b)
        if ta == FLOAT and tb == INTEGER:
            return a, self._convertir(b, FLOAT)
        if ta == INTEGER and tb == FLOAT:
            return self._convertir(a, FLOAT), b
        return a, b

    def _tipo_de_parametro(self, firma: FunctionType | None, i: int) -> Type | None:
        """Tipo del parametro `i`; si no tiene anotacion, el de sus argumentos."""
        if firma is None or i >= len(firma.param_types):
            return None
        tipo = firma.param_types[i]
        if tipo == ERROR and firma.decl is not None:
            return self._tipo_deducido(firma.decl.parameters().parameter(i))
        return tipo

    def _tipo_deducido(self, parametro: P.ParameterContext) -> Type | None:
        """Combina los tipos de los argumentos con los que se llama a un
        parametro sin anotacion (los anota el semantico)."""
        if hasattr(parametro, "tipo_deducido"):
            return parametro.tipo_deducido
        resultado: Type | None = None
        for tipo in getattr(parametro, "tipos_de_llamada", []):
            resultado = self._combinar(resultado, tipo, parametro)
        parametro.tipo_deducido = resultado
        return resultado

    def _combinar(self, a: Type | None, b: Type, parametro: P.ParameterContext) -> Type | None:
        if a is None or a == NULL or a == b:
            return b
        if b == NULL:
            return a
        if is_numeric(a) and is_numeric(b):
            return max_tipo(a, b)
        if isinstance(a, ClassType) and isinstance(b, ClassType):
            ancestro = a
            while ancestro is not None:
                if _hereda(b, ancestro):
                    return ancestro
                ancestro = ancestro.parent
        self.errores_backend.append(
            f"linea {parametro.start.line}: el parametro '{parametro.Identifier().getText()}' recibe "
            f"argumentos de tipos distintos ({a!r} y {b!r}); agregue una anotacion de tipo"
        )
        return a

    def _campo(self, tipo: Type | None, nombre: str) -> tuple[str | None, Type | None]:
        """(clase, tipo del campo) de `tipo.nombre`, para anotar load/store_field."""
        if isinstance(tipo, ClassType):
            miembro = tipo.lookup_member(nombre)
            if isinstance(miembro, FunctionType):
                self.errores_backend.append(f"el metodo '{tipo.name}.{nombre}' no se puede usar como valor")
            return tipo.name, miembro
        # receptor de tipo desconocido (parametro sin anotacion y sin llamadas)
        duenos = [c for c in self.layouts.values() if nombre in c.fields]
        if duenos:
            return duenos[0].name, duenos[0].fields[nombre].type
        return None, None

    def _entrar(self, ctx):
        """Cambia al `Scope` que el semantico asocio a `ctx` (si lo hay)."""
        anterior = self.scope
        self.scope = getattr(ctx, "scope", None) or anterior
        return anterior

    # ------------------------------------------------------------------
    # Simbolos: enlace a memoria (tabla de simbolos extendida)
    # ------------------------------------------------------------------

    def _bind(self, sym: Symbol, kind: str) -> None:
        """Asigna a `sym` su ranura: area estatica (globales) o AR actual."""
        tipo = sym.tipo_asignado if sym.type == NULL and sym.tipo_asignado is not None else sym.type
        if kind == "local" and self.scope is self.table.global_scope and self.fn.is_main:
            slot = self.global_area.add_global(sym.name, tipo)
            sym.storage, sym.frame, sym.tac_name = "global", self.global_area, "@" + slot.name
        else:
            ar = self.fn.ar
            slot = ar.add_param(sym.name, tipo) if kind == "param" else ar.add_local(sym.name, tipo)
            sym.storage, sym.frame, sym.tac_name = kind, ar, slot.name
        sym.offset, sym.size = slot.offset, slot.size

    def _declare(self, nombre: str, kind: str = "local") -> Symbol:
        sym = self.scope.resolve_local(nombre)
        if sym is None:
            raise CodegenError(f"simbolo '{nombre}' sin declarar en el analisis semantico")
        self._bind(sym, kind)
        return sym

    def _place(self, sym: Symbol, linea: int = 0) -> str:
        """Operando con el que se nombra `sym` desde la funcion actual."""
        if sym.frame is None and sym.kind in ("var", "const", "param"):
            self._bind(sym, "local")  # no deberia pasar; red de seguridad
        if sym.storage == "global" or sym.frame is self.fn.ar:
            return sym.tac_name
        saltos = self.fn.ar.depth - sym.frame.depth  # type: ignore[union-attr]
        self.closure_accesses.append(
            ClosureAccess(sym.name, self.fn.name, sym.frame.name, saltos, sym.offset or 0, linea)  # type: ignore[union-attr]
        )
        return f"up{saltos}.{sym.tac_name}"

    def _value_of(self, sym: Symbol, nombre: str, linea: int) -> str:
        if sym.kind == "function":
            dst = self.temp()
            self.emit(T.closure(dst, sym.label or nombre), sym.type)
            return dst
        return self._place(sym, linea)

    # ------------------------------------------------------------------
    # Sentencias
    # ------------------------------------------------------------------

    def visitStatement(self, ctx: P.StatementContext):
        antes = set(self.fn.temps.live)
        self.visitChildren(ctx)
        fugas = self.fn.temps.live - antes
        if fugas:
            self.temp_leaks += len(fugas)
            for i in fugas:
                self.fn.temps.free(f"t{i}")

    def visitBlock(self, ctx: P.BlockContext):
        anterior = self._entrar(ctx)
        for stmt in ctx.statement():
            self.visit(stmt)
        self.scope = anterior

    def _declaracion(self, ctx, expr_ctx) -> None:
        nombre = ctx.Identifier().getText()
        sym = self._declare(nombre)
        if expr_ctx is not None:
            self.emit_assign(sym.tac_name, self._visitar_como(expr_ctx, sym.type))

    def visitVariableDeclaration(self, ctx: P.VariableDeclarationContext):
        init = ctx.initializer()
        self._declaracion(ctx, init.expression() if init is not None else None)

    def visitConstantDeclaration(self, ctx: P.ConstantDeclarationContext):
        self._declaracion(ctx, ctx.expression())

    def visitAssignment(self, ctx: P.AssignmentContext):
        expresiones = ctx.expression()
        nombre = ctx.Identifier().getText()
        if len(expresiones) == 1:
            sym = self.scope.resolve(nombre)
            destino = self._place(sym, ctx.start.line)
            self.emit_assign(destino, self._visitar_como(expresiones[0], sym.type))
            return
        obj = self.visit(expresiones[0])
        clase, tipo_campo = self._campo(self._tipo_lugar(obj), nombre)
        valor = self._visitar_como(expresiones[1], tipo_campo)
        self.emit(T.store_field(obj, nombre, valor)).clase = clase
        self.free(obj, valor)

    def visitExpressionStatement(self, ctx: P.ExpressionStatementContext):
        self.free(self.visit(ctx.expression()))

    def visitPrintStatement(self, ctx: P.PrintStatementContext):
        valor = self.visit(ctx.expression())
        tipo = self._tipo_lugar(valor)
        self.emit(T.param(valor))
        self.free(valor)
        self.emit(T.call(None, "print", 1), tipo)

    def visitIfStatement(self, ctx: P.IfStatementContext):
        bloques = ctx.block()
        l_else = self.new_label()
        self.jump_if_false(ctx.expression(), l_else)
        self.visit(bloques[0])
        if len(bloques) > 1:
            l_fin = self.new_label()
            self.emit(T.goto(l_fin))
            self.emit(T.label(l_else))
            self.visit(bloques[1])
            self.emit(T.label(l_fin))
        else:
            self.emit(T.label(l_else))

    def visitWhileStatement(self, ctx: P.WhileStatementContext):
        l_ini, l_fin = self.new_label(), self.new_label()
        self.emit(T.label(l_ini))
        self.jump_if_false(ctx.expression(), l_fin)
        self.fn.loops.append((l_fin, l_ini, self.fn.try_depth))
        self.visit(ctx.block())
        self.fn.loops.pop()
        self.emit(T.goto(l_ini))
        self.emit(T.label(l_fin))

    def visitDoWhileStatement(self, ctx: P.DoWhileStatementContext):
        l_ini, l_cont, l_fin = self.new_label(), self.new_label(), self.new_label()
        self.emit(T.label(l_ini))
        self.fn.loops.append((l_fin, l_cont, self.fn.try_depth))
        self.visit(ctx.block())
        self.fn.loops.pop()
        self.emit(T.label(l_cont))
        self.jump_if_true(ctx.expression(), l_ini)
        self.emit(T.label(l_fin))

    @staticmethod
    def _partir_for(ctx: P.ForStatementContext):
        """Separa condicion e incremento: son los dos `expression?` del for,
        distinguibles por su posicion respecto al ultimo ';' hijo directo."""
        hijos = list(ctx.children)
        puntos = [i for i, h in enumerate(hijos) if h.getText() == ";" and not hasattr(h, "children")]
        medio = puntos[-1]
        cond = incr = None
        for i, h in enumerate(hijos):
            if isinstance(h, P.ExpressionContext):
                if i < medio:
                    cond = h
                else:
                    incr = h
        return cond, incr

    def visitForStatement(self, ctx: P.ForStatementContext):
        anterior = self._entrar(ctx)
        if ctx.variableDeclaration() is not None:
            self.visit(ctx.variableDeclaration())
        elif ctx.assignment() is not None:
            self.visit(ctx.assignment())
        cond, incr = self._partir_for(ctx)
        l_ini, l_cont, l_fin = self.new_label(), self.new_label(), self.new_label()
        self.emit(T.label(l_ini))
        if cond is not None:
            self.jump_if_false(cond, l_fin)
        self.fn.loops.append((l_fin, l_cont, self.fn.try_depth))
        self.visit(ctx.block())
        self.fn.loops.pop()
        self.emit(T.label(l_cont))
        if incr is not None:
            self.free(self.visit(incr))
        self.emit(T.goto(l_ini))
        self.emit(T.label(l_fin))
        self.scope = anterior

    def visitForeachStatement(self, ctx: P.ForeachStatementContext):
        coleccion = self.visit(ctx.expression())  # vive hasta el final del bucle
        anterior = self._entrar(ctx)
        sym = self._declare(ctx.Identifier().getText())
        idx, largo = self.temp(), self.temp()
        l_ini, l_cont, l_fin = self.new_label(), self.new_label(), self.new_label()
        self.emit(T.copy(idx, "0"), INTEGER)
        self.emit(T.length(largo, coleccion), INTEGER)
        self.emit(T.label(l_ini))
        self.emit(T.if_rel(idx, ">=", largo, l_fin))
        self.emit(T.load_index(sym.tac_name, coleccion, idx), sym.type)
        self.fn.loops.append((l_fin, l_cont, self.fn.try_depth))
        self.visit(ctx.block())
        self.fn.loops.pop()
        self.emit(T.label(l_cont))
        self.emit(T.binop(idx, idx, "+", "1"), INTEGER)
        self.emit(T.goto(l_ini))
        self.emit(T.label(l_fin))
        self.free(coleccion, idx, largo)
        self.scope = anterior

    def visitTryCatchStatement(self, ctx: P.TryCatchStatementContext):
        l_catch, l_fin = self.new_label(), self.new_label()
        self.emit(T.Instr("try", name=l_catch))
        self.fn.try_depth += 1
        self.visit(ctx.block(0))
        self.fn.try_depth -= 1
        self.emit(T.Instr("endtry"))
        self.emit(T.goto(l_fin))
        self.emit(T.label(l_catch))
        anterior = self._entrar(ctx)
        sym = self._declare(ctx.Identifier().getText())
        self.emit(T.Instr("catch", dst=sym.tac_name), STRING)
        for stmt in ctx.block(1).statement():
            self.visit(stmt)
        self.scope = anterior
        self.emit(T.label(l_fin))

    def visitSwitchStatement(self, ctx: P.SwitchStatementContext):
        sujeto = self.visit(ctx.expression())
        casos = ctx.switchCase()
        defecto = ctx.defaultCase()
        l_fin = self.new_label()
        l_casos = [self.new_label() for _ in casos]
        l_defecto = self.new_label() if defecto is not None else l_fin
        for caso, destino in zip(casos, l_casos):
            valor = self.visit(caso.expression())
            self.emit(T.if_rel(sujeto, "==", valor, destino))
            self.free(valor)
        self.emit(T.goto(l_defecto))
        self.free(sujeto)
        self.fn.loops.append((l_fin, None, self.fn.try_depth))
        for caso, destino in zip(casos, l_casos):
            self.emit(T.label(destino))
            for stmt in caso.statement():
                self.visit(stmt)
        if defecto is not None:
            self.emit(T.label(l_defecto))
            for stmt in defecto.statement():
                self.visit(stmt)
        self.fn.loops.pop()
        self.emit(T.label(l_fin))

    def _cerrar_try(self, hasta: int) -> None:
        """Un salto que abandona bloques `try` debe desactivar sus manejadores."""
        for _ in range(self.fn.try_depth - hasta):
            self.emit(T.Instr("endtry"))

    def visitBreakStatement(self, ctx: P.BreakStatementContext):
        l_fin, _, profundidad = self.fn.loops[-1]
        self._cerrar_try(profundidad)
        self.emit(T.goto(l_fin))

    def visitContinueStatement(self, ctx: P.ContinueStatementContext):
        for _, l_cont, profundidad in reversed(self.fn.loops):
            if l_cont is not None:
                self._cerrar_try(profundidad)
                self.emit(T.goto(l_cont))
                return
        raise CodegenError("'continue' fuera de un bucle")

    def visitReturnStatement(self, ctx: P.ReturnStatementContext):
        if ctx.expression() is None:
            self._cerrar_try(0)
            self.emit(T.ret())
            return
        valor = self._visitar_como(ctx.expression(), self.fn.ret_type)
        self._cerrar_try(0)
        self.emit(T.ret(valor))
        self.free(valor)

    # ------------------------------------------------------------------
    # Funciones, metodos y clases
    # ------------------------------------------------------------------

    def _etiqueta_unica(self, base: str) -> str:
        etiqueta, n = base, 2
        while etiqueta in self._labels_usados:
            etiqueta = f"{base}_{n}"
            n += 1
        self._labels_usados.add(etiqueta)
        return etiqueta

    def _begin_function(self, etiqueta: str, scope: Scope | None, kind: str):
        ar = ActivationRecord(etiqueta, kind=kind, parent=self.fn.ar)
        self.activation_records.append(ar)
        tac = TACFunction(etiqueta)
        self.program.functions.append(tac)
        guardado = (self.fn, self.scope)
        self.fn = FuncState(etiqueta, ar, tac)
        if scope is not None:
            self.scope = scope
        return guardado

    def _end_function(self, guardado) -> None:
        fn = self.fn
        if not fn.tac.instructions or fn.tac.instructions[-1].op != "ret":
            fn.tac.emit(T.ret())
        fn.tac.temp_count = fn.tac.used_temp_count()
        fn.ar.finalize(fn.tac.temp_count)
        self.fn, self.scope = guardado

    def _gen_function(self, ctx: P.FunctionDeclarationContext, etiqueta: str, clase: str | None,
                      ret_type: Type | None) -> None:
        guardado = self._begin_function(etiqueta, ctx.scope, "method" if clase else "function")
        ar, tac = self.fn.ar, self.fn.tac
        self.fn.ret_type = ret_type
        if clase:
            ar.add_param("this", self.clases.get(clase))
            tac.params.append("this")
        if ctx.parameters() is not None:
            for p in ctx.parameters().parameter():
                sym = self.scope.resolve_local(p.Identifier().getText())
                if sym is not None and sym.type == ERROR:
                    sym.type = self._tipo_deducido(p) or ERROR
                sym = self._declare(p.Identifier().getText(), "param")
                tac.params.append(sym.tac_name)
        for stmt in ctx.block().statement():
            self.visit(stmt)
        self._end_function(guardado)

    def visitFunctionDeclaration(self, ctx: P.FunctionDeclarationContext):
        nombre = ctx.Identifier().getText()
        sym = self.scope.resolve_local(nombre)
        if sym is not None and sym.label is None:
            sym.label = self._etiqueta_unica(nombre if self.fn.is_main else f"{self.fn.name}.{nombre}")
            sym.storage, sym.frame = "function", self.fn.ar
        etiqueta = sym.label if sym is not None and sym.label else self._etiqueta_unica(nombre)
        ret_type = sym.type.return_type if sym is not None and isinstance(sym.type, FunctionType) else None
        self._gen_function(ctx, etiqueta, None, ret_type)

    def visitClassDeclaration(self, ctx: P.ClassDeclarationContext):
        nombre = ctx.Identifier(0).getText()
        layout = self.layouts[nombre]
        anterior = self._entrar(ctx)
        sym = self.scope.resolve(nombre)
        if sym is not None:
            sym.storage, sym.label = "class", nombre
        for campo in layout.fields.values():
            if campo.owner == nombre:
                fsym = ctx.scope.resolve_local(campo.name)
                if fsym is not None:
                    fsym.storage, fsym.offset, fsym.size, fsym.tac_name = "field", campo.offset, campo.size, campo.name

        if layout.has_initializers:
            guardado = self._begin_function(f"{nombre}._init", None, "method")
            self.fn.ar.add_param("this", self.clases.get(nombre))
            self.fn.tac.params.append("this")
            for miembro in ctx.classMember():
                decl = miembro.variableDeclaration() or miembro.constantDeclaration()
                if decl is None:
                    continue
                expr = decl.initializer().expression() if miembro.variableDeclaration() is not None and decl.initializer() is not None else (
                    decl.expression() if miembro.constantDeclaration() is not None else None
                )
                if expr is not None:
                    campo = decl.Identifier().getText()
                    valor = self._visitar_como(expr, layout.fields[campo].type)
                    self.emit(T.store_field("this", campo, valor)).clase = nombre
                    self.free(valor)
            self._end_function(guardado)

        for miembro in ctx.classMember():
            fd = miembro.functionDeclaration()
            if fd is not None:
                metodo = fd.Identifier().getText()
                firma = self.clases[nombre].methods.get(metodo) if nombre in self.clases else None
                self._gen_function(fd, f"{nombre}.{metodo}", nombre, firma.return_type if firma else None)
        self.scope = anterior

    # ------------------------------------------------------------------
    # Expresiones: saltos condicionales
    # ------------------------------------------------------------------

    def _peel(self, ctx):
        """Colapsa las reglas de paso (cadena de precedencia con un solo
        operando, parentesis, `expression`) hasta el primer nodo con
        estructura propia."""
        while True:
            if isinstance(ctx, P.ExpressionContext):
                ctx = ctx.assignmentExpr()
            elif isinstance(ctx, P.ExprNoAssignContext):
                ctx = ctx.conditionalExpr()
            elif isinstance(ctx, P.TernaryExprContext) and ctx.getChildCount() == 1:
                ctx = ctx.logicalOrExpr()
            elif isinstance(ctx, P.LogicalOrExprContext) and len(ctx.logicalAndExpr()) == 1:
                ctx = ctx.logicalAndExpr(0)
            elif isinstance(ctx, P.LogicalAndExprContext) and len(ctx.equalityExpr()) == 1:
                ctx = ctx.equalityExpr(0)
            elif isinstance(ctx, P.EqualityExprContext) and len(ctx.relationalExpr()) == 1:
                ctx = ctx.relationalExpr(0)
            elif isinstance(ctx, P.RelationalExprContext) and len(ctx.additiveExpr()) == 1:
                ctx = ctx.additiveExpr(0)
            elif isinstance(ctx, P.AdditiveExprContext) and len(ctx.multiplicativeExpr()) == 1:
                ctx = ctx.multiplicativeExpr(0)
            elif isinstance(ctx, P.MultiplicativeExprContext) and len(ctx.unaryExpr()) == 1:
                ctx = ctx.unaryExpr(0)
            elif isinstance(ctx, P.UnaryExprContext) and ctx.primaryExpr() is not None:
                ctx = ctx.primaryExpr()
            elif isinstance(ctx, P.PrimaryExprContext):
                if ctx.expression() is not None:
                    ctx = ctx.expression()
                else:
                    ctx = ctx.leftHandSide() or ctx.literalExpr()
            else:
                return ctx

    def jump_if_false(self, ctx, destino: str) -> None:
        """Emite codigo que salta a `destino` si `ctx` es falso y sigue de largo si es verdadero."""
        n = self._peel(ctx)
        if isinstance(n, P.LogicalOrExprContext):
            operandos = n.logicalAndExpr()
            salto = self.new_label()
            for op in operandos[:-1]:
                self.jump_if_true(op, salto)
            self.jump_if_false(operandos[-1], destino)
            self.emit(T.label(salto))
        elif isinstance(n, P.LogicalAndExprContext):
            for op in n.equalityExpr():
                self.jump_if_false(op, destino)
        elif isinstance(n, P.UnaryExprContext) and n.getChild(0).getText() == "!":
            self.jump_if_true(n.unaryExpr(), destino)
        elif self._es_comparacion_binaria(n):
            self._salto_relacional(n, destino, invertir=True)
        elif n.getText() == "true":
            pass
        elif n.getText() == "false":
            self.emit(T.goto(destino))
        else:
            lugar = self.visit(n)
            self.emit(T.if_false(lugar, destino))
            self.free(lugar)

    def jump_if_true(self, ctx, destino: str) -> None:
        n = self._peel(ctx)
        if isinstance(n, P.LogicalOrExprContext):
            for op in n.logicalAndExpr():
                self.jump_if_true(op, destino)
        elif isinstance(n, P.LogicalAndExprContext):
            operandos = n.equalityExpr()
            salto = self.new_label()
            for op in operandos[:-1]:
                self.jump_if_false(op, salto)
            self.jump_if_true(operandos[-1], destino)
            self.emit(T.label(salto))
        elif isinstance(n, P.UnaryExprContext) and n.getChild(0).getText() == "!":
            self.jump_if_false(n.unaryExpr(), destino)
        elif self._es_comparacion_binaria(n):
            self._salto_relacional(n, destino, invertir=False)
        elif n.getText() == "true":
            self.emit(T.goto(destino))
        elif n.getText() == "false":
            pass
        else:
            lugar = self.visit(n)
            self.emit(T.if_true(lugar, destino))
            self.free(lugar)

    @staticmethod
    def _es_comparacion_binaria(n) -> bool:
        if isinstance(n, P.RelationalExprContext):
            return len(n.additiveExpr()) == 2
        if isinstance(n, P.EqualityExprContext):
            return len(n.relationalExpr()) == 2
        return False

    def _salto_relacional(self, n, destino: str, invertir: bool) -> None:
        izq_ctx, der_ctx = (
            n.additiveExpr() if isinstance(n, P.RelationalExprContext) else n.relationalExpr()
        )
        op = n.getChild(1).getText()
        a = self.visit(izq_ctx)
        b = self.visit(der_ctx)
        a, b = self._unificar_numericos(a, b)
        self.free(a, b)
        self.emit(T.if_rel(a, T.INVERSO[op] if invertir else op, b, destino))

    def _materializar_booleano(self, ctx) -> str:
        """Valor (true/false) de una expresion logica compuesta, via saltos."""
        resultado = self.temp()
        l_falso, l_fin = self.new_label(), self.new_label()
        self.jump_if_false(ctx, l_falso)
        self.emit(T.copy(resultado, "true"), BOOLEAN)
        self.emit(T.goto(l_fin))
        self.emit(T.label(l_falso))
        self.emit(T.copy(resultado, "false"), BOOLEAN)
        self.emit(T.label(l_fin))
        return resultado

    # ------------------------------------------------------------------
    # Expresiones: valores
    # ------------------------------------------------------------------

    def visitExpression(self, ctx: P.ExpressionContext):
        return self.visit(ctx.assignmentExpr())

    def visitExprNoAssign(self, ctx: P.ExprNoAssignContext):
        return self.visit(ctx.conditionalExpr())

    def visitTernaryExpr(self, ctx: P.TernaryExprContext):
        if ctx.getChildCount() == 1:
            return self.visit(ctx.logicalOrExpr())
        resultado = self.temp()
        tipo = getattr(ctx, "tipo", None)
        l_else, l_fin = self.new_label(), self.new_label()
        self.jump_if_false(ctx.logicalOrExpr(), l_else)
        self.emit_assign(resultado, self._visitar_como(ctx.expression(0), tipo))
        self.emit(T.goto(l_fin))
        self.emit(T.label(l_else))
        self.emit_assign(resultado, self._visitar_como(ctx.expression(1), tipo))
        self.emit(T.label(l_fin))
        return resultado

    def visitLogicalOrExpr(self, ctx: P.LogicalOrExprContext):
        if len(ctx.logicalAndExpr()) == 1:
            return self.visit(ctx.logicalAndExpr(0))
        return self._materializar_booleano(ctx)

    def visitLogicalAndExpr(self, ctx: P.LogicalAndExprContext):
        if len(ctx.equalityExpr()) == 1:
            return self.visit(ctx.equalityExpr(0))
        return self._materializar_booleano(ctx)

    def _plegar_binario(self, ctx, operandos) -> str:
        """`a op b op c ...` asociativo a la izquierda."""
        acumulado = self.visit(operandos[0])
        for i in range(1, len(operandos)):
            op = ctx.getChild(2 * i - 1).getText()
            derecho = self.visit(operandos[i])
            acumulado, derecho = self._unificar_numericos(acumulado, derecho)
            tipo = self._tipo_binario(op, acumulado, derecho)
            self.free(acumulado, derecho)
            dst = self.temp()
            self.emit(T.binop(dst, acumulado, op, derecho), tipo)
            acumulado = dst
        return acumulado

    def _tipo_binario(self, op: str, a: str, b: str) -> Type | None:
        if op in T.INVERSO:
            return BOOLEAN
        ta, tb = self._tipo_lugar(a), self._tipo_lugar(b)
        conocido = ta if ta not in (None, ERROR) else tb
        return FLOAT if FLOAT in (ta, tb) else conocido

    def visitEqualityExpr(self, ctx: P.EqualityExprContext):
        return self._plegar_binario(ctx, ctx.relationalExpr())

    def visitRelationalExpr(self, ctx: P.RelationalExprContext):
        return self._plegar_binario(ctx, ctx.additiveExpr())

    def visitAdditiveExpr(self, ctx: P.AdditiveExprContext):
        return self._plegar_binario(ctx, ctx.multiplicativeExpr())

    def visitMultiplicativeExpr(self, ctx: P.MultiplicativeExprContext):
        return self._plegar_binario(ctx, ctx.unaryExpr())

    def visitUnaryExpr(self, ctx: P.UnaryExprContext):
        if ctx.primaryExpr() is not None:
            return self.visit(ctx.primaryExpr())
        op = ctx.getChild(0).getText()
        interior = self.visit(ctx.unaryExpr())
        if op == "-" and _NUM_RE.match(interior.lstrip("-")):
            return interior[1:] if interior.startswith("-") else "-" + interior
        if op == "!" and interior in ("true", "false"):
            return "false" if interior == "true" else "true"
        tipo = BOOLEAN if op == "!" else self._tipo_lugar(interior)
        self.free(interior)
        dst = self.temp()
        self.emit(T.unop(dst, op, interior), tipo)
        return dst

    def visitPrimaryExpr(self, ctx: P.PrimaryExprContext):
        if ctx.literalExpr() is not None:
            return self.visit(ctx.literalExpr())
        if ctx.leftHandSide() is not None:
            return self.visit(ctx.leftHandSide())
        return self.visit(ctx.expression())

    def visitLiteralExpr(self, ctx: P.LiteralExprContext):
        if ctx.arrayLiteral() is not None:
            return self.visit(ctx.arrayLiteral())
        return ctx.getText()

    def visitArrayLiteral(self, ctx: P.ArrayLiteralContext):
        tipo = getattr(ctx, "tipo", None)
        return self._lista(ctx, tipo.element_type if isinstance(tipo, ArrayType) else None)

    def _lista(self, ctx: P.ArrayLiteralContext, tipo_elemento: Type | None) -> str:
        elementos = ctx.expression()
        dst = self.temp()
        self.emit(T.newlist(dst, len(elementos)), ArrayType(tipo_elemento or ERROR))
        for i, e in enumerate(elementos):
            valor = self._visitar_como(e, tipo_elemento)
            self.emit(T.store_index(dst, str(i), valor))
            self.free(valor)
        return dst

    # --- atomos ------------------------------------------------------

    def visitIdentifierExpr(self, ctx: P.IdentifierExprContext):
        nombre = ctx.Identifier().getText()
        return self._value_of(self.scope.resolve(nombre), nombre, ctx.start.line)

    def visitThisExpr(self, ctx: P.ThisExprContext):
        return self._this()

    def _this(self) -> str:
        """`this` de un metodo; desde una funcion anidada en el, via enlace de acceso."""
        ar, saltos = self.fn.ar, 0
        while ar is not None and ar.slot("this") is None:
            ar, saltos = ar.parent, saltos + 1
        return f"up{saltos}.this" if ar is not None and saltos else "this"

    def visitNewExpr(self, ctx: P.NewExprContext):
        nombre = ctx.Identifier().getText()
        layout = self.layouts[nombre]
        obj = self.temp()
        self.emit(T.new(obj, nombre, layout.instance_size), self.clases.get(nombre))
        for c in layout.ancestry():
            if c.has_initializers:
                self.emit(T.param(obj))
                self.emit(T.call(None, f"{c.name}._init", 1))
        definidor = layout.resolve_method("constructor")
        if definidor is not None:
            firma = self.clases[nombre].lookup_member("constructor") if nombre in self.clases else None
            args = self._args(ctx.arguments(), firma)
            self.emit(T.param(obj))
            for a in args:
                self.emit(T.param(a))
            self.free(*args)
            self.emit(T.call(None, f"{definidor}.constructor", len(args) + 1))
        return obj

    # --- leftHandSide: atomo + sufijos ------------------------------

    def visitLeftHandSide(self, ctx: P.LeftHandSideContext):
        return self._eval_lhs(ctx)[0]

    def _args(self, args_ctx, firma: Type | None = None) -> list[str]:
        if args_ctx is None:
            return []
        firma = firma if isinstance(firma, FunctionType) else None
        return [self._visitar_como(e, self._tipo_de_parametro(firma, i)) for i, e in enumerate(args_ctx.expression())]

    def _emit_llamada(self, tipo_llamada: str, destino: str, receptor: str | None, args: list[str],
                      ret: Type | None, liberar: tuple = ()) -> str | None:
        n = len(args) + (1 if receptor is not None else 0)
        if receptor is not None:
            self.emit(T.param(receptor))
        for a in args:
            self.emit(T.param(a))
        self.free(receptor, *args, *liberar)
        dst = None if ret == VOID else self.temp()
        self.emit(T.call(dst, destino, n, tipo_llamada), ret)
        return dst

    def _eval_lhs(self, ctx: P.LeftHandSideContext, hasta: int | None = None) -> tuple[str, Type | None]:
        """Evalua el atomo y los primeros `hasta` sufijos (todos si None)."""
        sufijos = list(ctx.suffixOp())
        n = len(sufijos) if hasta is None else hasta
        atomo = ctx.primaryAtom()
        i = 0
        if isinstance(atomo, P.IdentifierExprContext):
            nombre = atomo.Identifier().getText()
            sym = self.scope.resolve(nombre)
            if n > 0 and isinstance(sufijos[0], P.CallExprContext):
                lugar, tipo = self._llamada_por_nombre(sym, nombre, sufijos[0])
                i = 1
            else:
                lugar, tipo = self._value_of(sym, nombre, atomo.start.line), sym.type
        elif isinstance(atomo, P.NewExprContext):
            lugar, tipo = self.visit(atomo), getattr(atomo, "tipo", None)
        else:  # this
            lugar, tipo = self._this(), getattr(atomo, "tipo", None)

        while i < n:
            s = sufijos[i]
            if isinstance(s, P.PropertyAccessExprContext):
                nombre = s.Identifier().getText()
                if i + 1 < n and isinstance(sufijos[i + 1], P.CallExprContext):
                    lugar, tipo = self._llamada_metodo(lugar, tipo, nombre, sufijos[i + 1])
                    i += 2
                    continue
                clase, tipo = self._campo(tipo, nombre)
                self.free(lugar)
                dst = self.temp()
                self.emit(T.load_field(dst, lugar, nombre), tipo).clase = clase
                lugar = dst
            elif isinstance(s, P.IndexExprContext):
                idx = self.visit(s.expression())
                tipo = tipo.element_type if isinstance(tipo, ArrayType) else None
                self.free(lugar, idx)
                dst = self.temp()
                self.emit(T.load_index(dst, lugar, idx), tipo)
                lugar = dst
            else:  # llamada sobre el valor anterior (funcion como valor)
                args = self._args(s.arguments(), tipo)
                ret = tipo.return_type if isinstance(tipo, FunctionType) else None
                resultado = self._emit_llamada("callc", lugar, None, args, ret, liberar=(lugar,))
                lugar, tipo = resultado, ret
            i += 1
        return lugar, tipo

    def _llamada_por_nombre(self, sym: Symbol, nombre: str, llamada: P.CallExprContext):
        args = self._args(llamada.arguments(), sym.type)
        ret = sym.type.return_type if isinstance(sym.type, FunctionType) else None
        if sym.kind == "function":
            return self._emit_llamada("call", sym.label or nombre, None, args, ret), ret
        # variable/parametro que contiene una funcion: llamada indirecta
        funcion = self._place(sym, llamada.start.line)
        return self._emit_llamada("callc", funcion, None, args, ret), ret

    def _llamada_metodo(self, receptor: str, tipo: Type | None, nombre: str, llamada: P.CallExprContext):
        firma = tipo.lookup_member(nombre) if isinstance(tipo, ClassType) else None
        args = self._args(llamada.arguments(), firma)
        ret = firma.return_type if isinstance(firma, FunctionType) else None
        layout = self.layouts.get(tipo.name) if isinstance(tipo, ClassType) else None
        definidor = layout.resolve_method(nombre) if layout is not None else None
        if definidor is not None and not self._es_sobreescrito(layout, nombre):
            return self._emit_llamada("call", f"{definidor}.{nombre}", receptor, args, ret), ret
        # despacho dinamico: el metodo se busca en la clase real del objeto
        destino = f"{receptor}.{nombre}"
        n = len(args) + 1
        self.emit(T.param(receptor))
        for a in args:
            self.emit(T.param(a))
        self.free(receptor, *args)
        dst = None if ret == VOID else self.temp()
        self.emit(T.call(dst, destino, n, "callv"), ret)
        return dst, ret

    # --- asignaciones como expresion -------------------------------

    def visitAssignExpr(self, ctx: P.AssignExprContext):
        lhs = ctx.lhs
        sufijos = list(lhs.suffixOp())
        if not sufijos:
            sym = self.scope.resolve(lhs.primaryAtom().getText())
            destino = self._place(sym, ctx.start.line)
            self.emit_assign(destino, self._visitar_como(ctx.assignmentExpr(), sym.type))
            return destino
        base, tipo_base = self._eval_lhs(lhs, len(sufijos) - 1)
        ultimo = sufijos[-1]
        if isinstance(ultimo, P.IndexExprContext):
            idx = self.visit(ultimo.expression())
            elemento = tipo_base.element_type if isinstance(tipo_base, ArrayType) else None
            valor = self._visitar_como(ctx.assignmentExpr(), elemento)
            self.emit(T.store_index(base, idx, valor))
            self.free(base, idx)
        else:
            campo = ultimo.Identifier().getText()
            clase, tipo_campo = self._campo(tipo_base, campo)
            valor = self._visitar_como(ctx.assignmentExpr(), tipo_campo)
            self.emit(T.store_field(base, campo, valor)).clase = clase
            self.free(base)
        return valor

    def visitPropertyAssignExpr(self, ctx: P.PropertyAssignExprContext):
        base = self.visit(ctx.lhs)
        campo = ctx.Identifier().getText()
        clase, tipo_campo = self._campo(self._tipo_lugar(base), campo)
        valor = self._visitar_como(ctx.assignmentExpr(), tipo_campo)
        self.emit(T.store_field(base, campo, valor)).clase = clase
        self.free(base)
        return valor
