// @caso: una variable capturada vive en memoria: la funcion anidada la ve y la cambia
// @salida: 3 | 8
function f(): integer {
  let c: integer = 1;
  function suma(n: integer) { c = c + n; }
  suma(2);
  print(c);
  suma(5);
  return c;
}
print(f());
