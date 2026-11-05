// @caso: una variable declarada sin valor vale cero, en la pila y en el area estatica
// @salida: 0 | 0.0 | false | null | 0 | [1] | 7
let g: integer;
function f() {
  let x: integer;
  let y: float;
  let z: boolean;
  let s: string;
  print(x); print(y); print(z); print(s);
}
f();
print(g);
let d = null;
d = [1];
print(d);
function lee(): integer {
  let c: integer;
  function pone() { c = 7; }
  pone();
  return c;
}
print(lee());
