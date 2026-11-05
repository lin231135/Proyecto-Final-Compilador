// @caso: el quinto argumento en adelante y los float viajan por la pila
// @salida: 91 | hola | 11.75
// @mips: , 32($sp)
// @mips: s.d
function suma6(a: integer, b: integer, c: integer, d: integer, e: integer, f: integer): integer {
  return a + 2 * b + 3 * c + 4 * d + 5 * e + 6 * f;
}
function mezcla(a: integer, x: float, b: boolean, s: string, c: integer, y: float): float {
  if (b) { print(s); }
  return x + y + c - a;
}
print(suma6(1, 2, 3, 4, 5, 6));
print(mezcla(1, 2.5, true, "hola", 10, 0.25));
