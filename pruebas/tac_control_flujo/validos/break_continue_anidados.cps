// @caso: break/continue apuntan al bucle que los contiene (el interno)
// @salida: 20
let s: integer = 0;
for (let i: integer = 0; i < 5; i = i + 1) {
  let j: integer = 0;
  while (true) {
    j = j + 1;
    if (j > 3) { break; }
    if (j == 2) { continue; }
    s = s + j;
  }
}
print(s);
