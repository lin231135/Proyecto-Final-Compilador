// @caso: lista de listas: lectura y escritura con doble indice
// @salida: 2 | 42
let m: integer[][] = [[1, 2], [3, 4]];
print(m[0][1]);
m[1][0] = m[0][1] + 40;
print(m[1][0]);
