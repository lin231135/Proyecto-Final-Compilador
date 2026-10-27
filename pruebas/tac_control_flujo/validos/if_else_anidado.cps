// @caso: if / else anidados con return en cada rama
// @salida: neg | cero | pos
function clasif(n: integer): string {
  if (n < 0) { return "neg"; } else {
    if (n == 0) { return "cero"; } else { return "pos"; }
  }
}
print(clasif(-3));
print(clasif(0));
print(clasif(9));
