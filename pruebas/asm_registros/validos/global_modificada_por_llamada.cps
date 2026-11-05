// @caso: una global en registro no se reutiliza tras una llamada que la cambia
// @salida: 2 | 17
let g: integer = 1;
function cambia() { g = g + 1; }
function usa(): integer {
  let a: integer = g;
  cambia();
  return a + g * 5;
}
cambia();
print(g);
print(usa());
