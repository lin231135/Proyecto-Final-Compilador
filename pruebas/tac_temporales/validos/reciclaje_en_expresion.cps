// @caso: (a+b)*(c+d)-(a-b)*(c-d) necesita solo 3 temporales gracias al reciclaje
// @salida: 20
// @max_temporales: 3
function calc(a: integer, b: integer, c: integer, d: integer): integer {
  return (a + b) * (c + d) - (a - b) * (c - d);
}
print(calc(1, 2, 3, 4));
