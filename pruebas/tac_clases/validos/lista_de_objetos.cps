// @caso: arreglo de objetos con despacho dinamico en foreach
// @salida: a hace ruido | b ladra
class Animal {
  let nombre: string;
  function constructor(nombre: string) { this.nombre = nombre; }
  function hablar(): string { return this.nombre + " hace ruido"; }
}
class Perro : Animal {
  function hablar(): string { return this.nombre + " ladra"; }
}
let zoo: Animal[] = [new Animal("a"), new Perro("b")];
foreach (z in zoo) { print(z.hablar()); }
