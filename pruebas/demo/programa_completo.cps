// @caso: demo - clases, herencia, closures, recursion, arreglos y control de flujo completo (0 errores)
class Animal {
  let nombre: string;

  function constructor(nombre: string) {
    this.nombre = nombre;
  }

  function hablar(): string {
    return this.nombre + " hace ruido.";
  }
}

class Perro : Animal {
  function hablar(): string {
    return this.nombre + " ladra.";
  }
}

function saludar(nombre: string): string {
  return "Hola " + nombre;
}

function crearContador(): integer {
  function siguiente(): integer {
    return 1;
  }
  return siguiente();
}

function factorial(n: integer): integer {
  if (n <= 1) { return 1; }
  return n * factorial(n - 1);
}

function suma(a: integer, b: integer): integer {
  return a + b;
}

let a: integer = 10;
let b: string = "hola";
let c: boolean = true;
let d = null;

let x = 5 + 3 * 2;
let y = !(x < 10 || x > 20);
let z = (1 + 2) * 3;

let nombreVar: string;
nombreVar = "Compiscript";

const PI: integer = 314;

let mensaje = saludar("Mundo");

let dog: Animal = new Animal("Rex");
print(dog.nombre);

let lista = [1, 2, 3];
print(lista[0]);

let notas: integer[] = [90, 85, 100];
let matriz: integer[][] = [[1, 2], [3, 4]];

let contadorResultado: integer = crearContador();

let perro: Perro = new Perro("Toby");

{
  let bloqueX = 42;
  print(bloqueX);
}

if (x > 10) {
  print("Mayor a 10");
} else {
  print("Menor o igual");
}

while (x < 5) {
  x = x + 1;
}

do {
  x = x - 1;
} while (x > 0);

for (let i: integer = 0; i < 3; i = i + 1) {
  print(i);
}

foreach (item in lista) {
  print(item);
}

foreach (n in notas) {
  if (n < 60) { continue; }
  if (n == 100) { break; }
  print(n);
}

switch (x) {
  case 1:
    print("uno");
  case 2:
    print("dos");
  default:
    print("otro");
}

try {
  let peligro = lista[100];
} catch (err) {
  print("Error atrapado: " + err);
}

let resultadoSuma: integer = suma(2, 3);
let resultadoFactorial: integer = factorial(5);
