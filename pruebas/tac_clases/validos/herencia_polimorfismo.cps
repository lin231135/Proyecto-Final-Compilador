// @caso: herencia, override y despacho dinamico: el metodo depende de la clase real
// @salida: Rex hace ruido | Fido ladra
// @contiene: callv
// @contiene: call Animal.constructor, 2
class Animal {
  let nombre: string;
  function constructor(nombre: string) { this.nombre = nombre; }
  function hablar(): string { return this.nombre + " hace ruido"; }
}
class Perro : Animal {
  function hablar(): string { return this.nombre + " ladra"; }
}
function describir(a: Animal): string { return a.hablar(); }
print(describir(new Animal("Rex")));
print(describir(new Perro("Fido")));
