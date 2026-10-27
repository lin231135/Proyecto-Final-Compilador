# 🧪 Compiscript

## 📋 Descripción General

Este lenguaje se encuentra basado en Typescript, por lo que representa un subset del mismo, con algunas diferencias.

## 🧩 Características del Lenguaje

Compiscript soporta los siguientes conceptos fundamentales:

### ✅ Tipos de Datos

```cps
let a: integer = 10;
let b: string = "hola";
let c: boolean = true;
let d = null;
```

### ✅ Literales

```cps
123          // integer
"texto"      // string
true, false  // boolean
null         // nulo
```

### ✅ Expresiones Aritméticas y Lógicas

```cps
let x = 5 + 3 * 2;
let y = !(x < 10 || x > 20);
```

### ✅ Precedencia y Agrupamiento

```cps
let z = (1 + 2) * 3;
```

### ✅ Declaración y Asignación de Variables

```cps
let nombre: string;
nombre = "Compiscript";
```

### ✅ Constantes (`const`)

```cps
const PI: integer = 314;
```

### ✅ Funciones y Parámetros

```cps
function saludar(nombre: string): string {
  return "Hola " + nombre;
}
```

### ✅ Expresiones de Llamada

```cps
let mensaje = saludar("Mundo");
```

### ✅ Acceso a Propiedades (`.`)

```cps
print(dog.nombre);
```

### ✅ Acceso a Elementos de Arreglo (`[]`)

```cps
let lista = [1, 2, 3];
print(lista[0]);
```

### ✅ Arreglos

```cps
let notas: integer[] = [90, 85, 100];
let matriz: integer[][] = [[1, 2], [3, 4]];
```

### ✅ Funciones como Closures

```cps
function crearContador(): integer {
  function siguiente(): integer {
    return 1;
  }
  return siguiente();
}
```

### ✅ Clases y Constructores

```cps
class Animal {
  let nombre: string;

  function constructor(nombre: string) {
    this.nombre = nombre;
  }

  function hablar(): string {
    return this.nombre + " hace ruido.";
  }
}
```

### ✅ Herencia

```cps
class Perro : Animal {
  function hablar(): string {
    return this.nombre + " ladra.";
  }
}
```

### ✅ `this`

```cps
this.nombre = "Firulais";
```

### ✅ Instanciación con `new`

```cps
let perro: Perro = new Perro("Toby");
```

### ✅ Bloques y Ámbitos

```cps
{
  let x = 42;
  print(x);
}
```

### ✅ Control de Flujo

#### `if` / `else`

```cps
if (x > 10) {
  print("Mayor a 10");
} else {
  print("Menor o igual");
}
```

#### `while`

```cps
while (x < 5) {
  x = x + 1;
}
```

#### `do-while`

```cps
do {
  x = x - 1;
} while (x > 0);
```

#### `for`

```cps
for (let i: integer = 0; i < 3; i = i + 1) {
  print(i);
}
```

#### `foreach`

```cps
foreach (item in lista) {
  print(item);
}
```

#### `break` / `continue`

```cps
foreach (n in notas) {
  if (n < 60) continue;
  if (n == 100) break;
  print(n);
}
```

### ✅ `switch / case`

```cps
switch (x) {
  case 1:
    print("uno");
  case 2:
    print("dos");
  default:
    print("otro");
}
```

### ✅ `try / catch`

```cps
try {
  let peligro = lista[100];
} catch (err) {
  print("Error atrapado: " + err);
}
```

### ✅ `return`

```cps
function suma(a: integer, b: integer): integer {
  return a + b;
}
```

### ✅ Recursión

```cps
function factorial(n: integer): integer {
  if (n <= 1) return 1;
  return n * factorial(n - 1);
}
```

---

## 📦 Extensión de Archivo

Todos los archivos fuente de Compiscript deben usar la extensión:

```bash
program.cps
```
