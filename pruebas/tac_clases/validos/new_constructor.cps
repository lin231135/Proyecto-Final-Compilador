// @caso: new + constructor + acceso a atributos y metodo con this
// @salida: Rex hace ruido | 4
// @contiene: = new Animal, 
// @contiene: call Animal.constructor, 2
// @contiene: call Animal.hablar, 1
// @no_contiene: callv
class Animal {
  let nombre: string;
  let patas: integer = 4;
  function constructor(nombre: string) { this.nombre = nombre; }
  function hablar(): string { return this.nombre + " hace ruido"; }
}
let a: Animal = new Animal("Rex");
print(a.hablar());
print(a.patas);
