"""
Pasada 1: recorre solo el nivel superior de `program` (y los
miembros de las clases ahi declaradas, sin visitar sus cuerpos) y declara
por adelantado:
  - el FunctionType de cada funcion global, en el scope global.
  - el ClassType de cada clase (padre, campos con anotacion de tipo y
    firmas de metodos), en `visitor.clases`.

Sin esto fallan: recursion mutua entre dos funciones globales, un metodo
que llama a otro declarado mas abajo, y `class Perro : Animal` cuando
`Animal` se declara despues. Con esto, salen gratis.

Integracion con la pasada 2 (function_mixin.py / class_mixin.py): cada
FunctionDeclarationContext/ClassDeclarationContext procesado aqui se marca
por identidad en `visitor._nodos_prepasados`. `visitFunctionDeclaration` /
`visitClassDeclaration` consultan ese conjunto para NO volver a declarar
(y por lo tanto no reportar un falso "ya esta declarado") el mismo nodo que
esta pasada ya registro -tanto si gano como si fue detectado aqui como
duplicado-; solo visitan el cuerpo/los miembros.
"""

from __future__ import annotations

from core.symbols import Symbol
from core.types import ClassType


def ejecutar_prepass(visitor, tree) -> None:
    """`tree` es el ProgramContext raiz devuelto por `parser.program()`."""
    nodos_prepasados: set[int] = set()
    visitor._nodos_prepasados = nodos_prepasados

    declaraciones_funcion = []
    declaraciones_clase = []
    for stmt in tree.statement():
        if stmt.functionDeclaration() is not None:
            declaraciones_funcion.append(stmt.functionDeclaration())
        elif stmt.classDeclaration() is not None:
            declaraciones_clase.append(stmt.classDeclaration())

    _prepasar_clases(visitor, declaraciones_clase, nodos_prepasados)
    _prepasar_funciones(visitor, declaraciones_funcion, nodos_prepasados)


def _prepasar_clases(visitor, declaraciones_clase, nodos_prepasados: set[int]) -> None:
    # 1) shells vacios primero, para que la herencia hacia adelante
    #    (`class Perro : Animal` con Animal declarada despues) se resuelva.
    ganadoras: dict[str, "CompiscriptParser.ClassDeclarationContext"] = {}
    for cd in declaraciones_clase:
        nodos_prepasados.add(id(cd))
        nombre = cd.Identifier(0).getText()
        if nombre in visitor.clases:
            visitor.reporter.error(cd, "clase", f"la clase '{nombre}' ya esta declarada")
            continue
        tipo_clase = ClassType(name=nombre)
        visitor.clases[nombre] = tipo_clase
        simbolo = Symbol(
            name=nombre,
            type=tipo_clase,
            kind="class",
            initialized=True,
            line=cd.Identifier(0).getSymbol().line,
            column=cd.Identifier(0).getSymbol().column,
        )
        visitor.define_or_error(simbolo, cd)
        ganadoras[nombre] = cd

    # 2) padre + campos/metodos, ya con todas las clases creadas.
    for nombre, cd in ganadoras.items():
        tipo_clase = visitor.clases[nombre]

        if cd.Identifier(1) is not None:
            nombre_padre = cd.Identifier(1).getText()
            padre = visitor.clases.get(nombre_padre)
            if padre is None:
                visitor.reporter.error(cd, "clase", f"la clase padre '{nombre_padre}' no esta declarada")
            elif padre is tipo_clase:
                visitor.reporter.error(cd, "clase", f"la clase '{nombre}' no puede heredar de si misma")
            elif _hereda_de(padre, tipo_clase):
                visitor.reporter.error(cd, "clase", f"herencia ciclica: '{nombre}' y '{nombre_padre}' se heredan mutuamente")
            else:
                tipo_clase.parent = padre

        for miembro in cd.classMember():
            if miembro.functionDeclaration() is not None:
                fn_ctx = miembro.functionDeclaration()
                tipo_clase.methods[fn_ctx.Identifier().getText()] = visitor._firma_metodo(fn_ctx)
            else:
                decl = miembro.variableDeclaration() or miembro.constantDeclaration()
                if decl.typeAnnotation() is not None:
                    tipo = visitor.resolve_type_annotation(decl.typeAnnotation().type_())
                    tipo_clase.fields[decl.Identifier().getText()] = tipo
                # Sin anotacion de tipo no hay como resolverlo sin visitar
                # el inicializador (eso es cuerpo, no le toca al prepass);
                # visitClassMember en la pasada 2 lo completa igual.


def _hereda_de(clase: ClassType, ancestro: ClassType) -> bool:
    """True si `ancestro` aparece en la cadena de padres de `clase` (o es ella)."""
    while clase is not None:
        if clase is ancestro:
            return True
        clase = clase.parent
    return False


def _prepasar_funciones(visitor, declaraciones_funcion, nodos_prepasados: set[int]) -> None:
    for fd in declaraciones_funcion:
        nodos_prepasados.add(id(fd))
        nombre = fd.Identifier().getText()
        tipo_funcion = visitor._firma_metodo(fd, es_metodo=False)
        simbolo = Symbol(
            name=nombre,
            type=tipo_funcion,
            kind="function",
            initialized=True,
            line=fd.Identifier().getSymbol().line,
            column=fd.Identifier().getSymbol().column,
        )
        visitor.define_or_error(simbolo, fd)
