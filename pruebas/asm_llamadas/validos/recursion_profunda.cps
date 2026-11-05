// @caso: 5000 marcos en la pila: $sp baja y vuelve exactamente a su lugar
// @salida: 12502500 | 7
// @mips: addiu $sp, $sp, -
// @mips: jr $ra
function suma(n: integer): integer {
  if (n == 0) { return 0; }
  return n + suma(n - 1);
}
print(suma(5000));
print(7);
