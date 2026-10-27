// @caso: for completo y for sin inicializador ni incremento
// @salida: 0 | 1 | 4 | 9 | 0 | 1 | 2
for (let i: integer = 0; i < 4; i = i + 1) { print(i * i); }
let k: integer = 0;
for (; k < 3; ) { print(k); k = k + 1; }
