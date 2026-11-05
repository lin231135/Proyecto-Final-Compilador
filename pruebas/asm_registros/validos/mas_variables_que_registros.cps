// @caso: doce variables vivas a traves de llamadas en un bucle
// @salida: 321
function id(x: integer): integer { return x; }
function f(): integer {
  let a: integer = 1; let b: integer = 2; let c: integer = 3; let d: integer = 4;
  let e: integer = 5; let g: integer = 6; let h: integer = 7; let i: integer = 8;
  let j: integer = 9; let k: integer = 10; let l: integer = 11; let m: integer = 12;
  for (let n: integer = 0; n < 3; n = n + 1) {
    a = a + id(m);
    b = b + id(a);
    c = c + id(b);
  }
  return a + b + c + d + e + g + h + i + j + k + l + m;
}
print(f());
