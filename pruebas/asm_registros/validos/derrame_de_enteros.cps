// @caso: 24 temporales vivos a la vez: mas que registros, getReg derrama a la pila
// @salida: 600
// @derrames: 1
function g(a: integer): integer {
  return ((a * 1) + ((a * 2) + ((a * 3) + ((a * 4) + ((a * 5) + ((a * 6) + ((a * 7) + ((a * 8) + ((a * 9) + ((a * 10) + ((a * 11) + ((a * 12) + ((a * 13) + ((a * 14) + ((a * 15) + ((a * 16) + ((a * 17) + ((a * 18) + ((a * 19) + ((a * 20) + ((a * 21) + ((a * 22) + ((a * 23) + (a * 24))))))))))))))))))))))));
}
print(g(2));
