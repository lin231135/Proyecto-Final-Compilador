// @caso: una funcion hoja usa registros $t para sus variables y no guarda nada
// @salida: 385
// @no_mips: sw $s0
function suma(n: integer): integer {
  let s: integer = 0;
  for (let i: integer = 1; i <= n; i = i + 1) { s = s + i * i; }
  return s;
}
print(suma(10));
