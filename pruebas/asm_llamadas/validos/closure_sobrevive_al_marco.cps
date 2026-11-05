// @caso: un closure guardado en una global sobrevive a su funcion (marco en el heap)
// @salida: 11 | 12 | 101
// @mips: jalr
// @mips: jal __rt_alloc
function cero(): integer { return 0; }
let h = cero;
function crear(inicio: integer) {
  let c: integer = inicio;
  function siguiente(): integer { c = c + 1; return c; }
  h = siguiente;
}
crear(10);
print(h());
print(h());
crear(100);
print(h());
