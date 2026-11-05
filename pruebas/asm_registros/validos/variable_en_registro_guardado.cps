// @caso: las variables de un bucle con llamadas viven en registros $s
// @salida: 20
// @mips: sw $s0
// @mips: lw $s0
// @arm: x19
function doble(i: integer): integer { return i * 2; }
function f(n: integer): integer {
  let s: integer = 0;
  for (let i: integer = 1; i <= n; i = i + 1) { s = s + doble(i); }
  return s;
}
print(f(4));
