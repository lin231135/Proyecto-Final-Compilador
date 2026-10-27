// @caso: una funcion se guarda en una variable y se invoca de forma indirecta
// @salida: 3
// @contiene: = closure contador
// @contiene: callc
function contador(): integer {
  let c: integer = 0;
  function inc(): integer { c = c + 1; return c; }
  inc();
  inc();
  return inc();
}
let f = contador;
print(f());
