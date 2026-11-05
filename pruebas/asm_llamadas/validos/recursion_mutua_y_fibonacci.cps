// @caso: llamadas hacia adelante y recursion doble
// @salida: true | true | 610
function esPar(n: integer): boolean {
  if (n == 0) { return true; }
  return esImpar(n - 1);
}
function esImpar(n: integer): boolean {
  if (n == 0) { return false; }
  return esPar(n - 1);
}
function fib(n: integer): integer {
  if (n < 2) { return n; }
  return fib(n - 1) + fib(n - 2);
}
print(esPar(10));
print(esImpar(7));
print(fib(15));
