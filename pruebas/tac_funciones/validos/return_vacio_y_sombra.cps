// @caso: return sin valor; parametro que sombrea a una global
// @salida: 10 | 1
let x: integer = 10;
function f(x: integer) { if (x > 3) { return; } print(x); }
print(x);
f(1);
f(5);
