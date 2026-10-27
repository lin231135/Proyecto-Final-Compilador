// @caso: foreach recorre el arreglo con un indice oculto
// @salida: 10
// @contiene: = len
let xs: integer[] = [1, 2, 3, 4];
let s: integer = 0;
foreach (x in xs) { s = s + x; }
print(s);
