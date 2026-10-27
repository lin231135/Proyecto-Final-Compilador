// @caso: campos con valor inicial (let/const) se inicializan en Clase._init antes del constructor
// @salida: 15
// @contiene: Caja._init
class Caja {
  let x: integer = 5;
  const K: integer = 10;
}
let o: Caja = new Caja();
print(o.x + o.K);
