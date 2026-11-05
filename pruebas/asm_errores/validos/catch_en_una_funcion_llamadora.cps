// @caso: el error atraviesa marcos: $sp, $fp y los registros guardados se recuperan
// @salida: 24 | indice fuera de rango | 101 | 11 | 24 | indice fuera de rango | indice fuera de rango | 237
function peligro(l: integer[], i: integer): integer {
  let local: integer = i * 2;
  return l[i] + local;
}
function intermedio(l: integer[], i: integer): integer {
  let a: integer = i + 1;
  let r: integer = peligro(l, i);
  return a + r;
}
function seguro(l: integer[], i: integer): integer {
  let c: integer = 100;
  try {
    c = c + 1;
    return intermedio(l, i);
  } catch (e) {
    print(e);
  }
  return c;
}
function usa(l: integer[]): integer {
  let total: integer = 0;
  for (let i: integer = 0; i < 4; i = i + 1) {
    let parcial: integer = seguro(l, i);
    if (i == 0) { print(parcial); }
    if (i == 1) { print(parcial); }
    total = total + parcial;
  }
  return total;
}
let xs: integer[] = [10, 20];
print(seguro(xs, 1));
print(seguro(xs, 5));
print(usa(xs));
