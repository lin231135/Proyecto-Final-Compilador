// @caso: una lista se pasa a una funcion (por referencia) y se modifica
// @salida: 6 | 100
function suma(xs: integer[]): integer {
  let s: integer = 0;
  foreach (x in xs) { s = s + x; }
  return s;
}
function pon(xs: integer[], i: integer, v: integer) { xs[i] = v; }
let a: integer[] = [1, 2, 3];
print(suma(a));
pon(a, 0, 100);
print(a[0]);
