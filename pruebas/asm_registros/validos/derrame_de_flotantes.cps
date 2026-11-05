// @caso: 12 float vivos a la vez con 7 registros de punto flotante
// @salida: 39.0
// @derrames: 1
// @mips: s.d
function g(x: float): float {
  return ((x * 1.0) + ((x * 2.0) + ((x * 3.0) + ((x * 4.0) + ((x * 5.0) + ((x * 6.0) + ((x * 7.0) + ((x * 8.0) + ((x * 9.0) + ((x * 10.0) + ((x * 11.0) + (x * 12.0))))))))))));
}
print(g(0.5));
