// @caso: los argumentos de llamadas anidadas se emiten en orden y sin mezclarse
// @salida: 9 | 5
// @contiene: call max, 2
function max(a: integer, b: integer): integer { if (a > b) { return a; } return b; }
print(max(3, 9));
print(max(max(1, 2), max(5, 4)));
