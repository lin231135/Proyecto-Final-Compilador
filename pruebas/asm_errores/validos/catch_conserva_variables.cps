// @caso: lo escrito antes del error sigue visible en el catch y despues de el
// @salida: 3 | 3 | 7
function f(xs: integer[]): integer {
  let n: integer = 0;
  try {
    n = 3;
    print(xs[9]);
    n = 100;
  } catch (e) {
    print(n);
  }
  print(n);
  return n + 4;
}
print(f([1]));
