// @caso: listas de todos los tipos, anidadas y modificadas
// @salida: [1, 2, 3] | [[1, 2], [3]] | [1.5, 2.0] | [true, false] | [a, b] | [] | [1.0, 2.0] | [10, 2, 3] | 9
let enteros: integer[] = [1, 2, 3];
print(enteros);
print([[1, 2], [3]]);
print([1.5, 2.0]);
print([true, false]);
print(["a", "b"]);
let vacia: integer[] = [];
print(vacia);
let flotantes: float[] = [1, 2];
print(flotantes);
let alias: integer[] = enteros;
alias[0] = 10;
print(enteros);
let m: integer[][] = [[1, 2], [3, 4]];
m[1][1] = 5;
print(m[1][0] + m[0][0] + m[1][1]);
