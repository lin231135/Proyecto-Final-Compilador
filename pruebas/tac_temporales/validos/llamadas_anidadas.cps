// @caso: f(g(h(1))): el resultado de cada llamada se consume como argumento y se recicla
// @salida: 7
// @max_temporales: 1
function h(x: integer): integer { return x + 1; }
function g(x: integer): integer { return x * 2; }
function f(x: integer): integer { return x + 3; }
print(f(g(h(1))));
