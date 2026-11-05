// @caso: la tabla de metodos elige el metodo de la clase real
// @salida: Rex dice guau | Tom dice miau | Zoo dice ...
// @mips: cls_Perro: .word
// @mips: jalr $t9
// @arm: blr x16
class Animal {
  let n: string;
  function constructor(n: string) { this.n = n; }
  function sonido(): string { return "..."; }
  function hablar(): string { return this.n + " dice " + this.sonido(); }
}
class Perro : Animal { function sonido(): string { return "guau"; } }
class Gato : Animal { function sonido(): string { return "miau"; } }
let animales: Animal[] = [new Perro("Rex"), new Gato("Tom"), new Animal("Zoo")];
foreach (x in animales) { print(x.hablar()); }
