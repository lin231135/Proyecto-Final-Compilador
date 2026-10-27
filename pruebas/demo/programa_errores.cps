// @caso: demo - exactamente un error de cada una de las 7 categorias
// @error: tipo
// @error: ambito
// @error: funcion
// @error: control_flujo
// @error: clase
// @error: lista
// @error: general

// tipo: asignar string a integer
let a: integer = "texto";

// ambito: variable no declarada
print(bNoDeclarada);

// funcion: numero de argumentos incorrecto
function suma(x: integer, y: integer): integer { return x + y; }
let s: integer = suma(1);

// control_flujo: break fuera de un bucle
break;

// clase: atributo inexistente
class Animal { let nombre: string; }
let animal: Animal = new Animal();
print(animal.edad);

// lista: indice no entero
let lista: integer[] = [1, 2, 3];
print(lista["cero"]);

// general: codigo muerto
function f(): integer {
  return 1;
  print("inalcanzable");
}
