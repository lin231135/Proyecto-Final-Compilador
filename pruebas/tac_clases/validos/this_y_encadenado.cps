// @caso: metodos que devuelven this permiten encadenar llamadas
// @salida: 3
// @contiene: call Contador.inc, 1
class Contador {
  let n: integer = 0;
  function inc(): Contador { this.n = this.n + 1; return this; }
}
let c: Contador = new Contador();
c.inc().inc().inc();
print(c.n);
