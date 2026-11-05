// @caso: los valores vivos sobreviven a las llamadas intermedias
// @salida: -27 | 42
// @mips: sw $s0
// @mips: lw $s0
function id(x: integer): integer { return x; }
function pares(n: integer): integer {
  let a: integer = n * 2;
  let b: integer = id(a) + 1;
  let c: integer = id(b) + a;
  return a + b + c;
}
let r: integer = id(1) + id(2) * id(3) - (id(4) + id(5) * id(6));
print(r);
print(pares(5));
