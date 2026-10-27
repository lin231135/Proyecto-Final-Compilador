// @caso: R20 acceso a atributo y metodo existentes
class Animal {
  let nombre: string;
  function constructor(nombre: string) { this.nombre = nombre; }
  function hablar(): string { return this.nombre; }
}
let a: Animal = new Animal("Rex");
print(a.nombre);
print(a.hablar());
