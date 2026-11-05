// @caso: mas argumentos que registros disponibles: enteros, float e indirectos
// @salida: 210 | 45.0 | 210 | 210 | 20
function veinte(a: integer, b: integer, c: integer, d: integer, e: integer,
                f: integer, g: integer, h: integer, i: integer, j: integer,
                k: integer, l: integer, m: integer, n: integer, o: integer,
                p: integer, q: integer, r: integer, s: integer, t: integer): integer {
  return a + b + c + d + e + f + g + h + i + j + k + l + m + n + o + p + q + r + s + t;
}
function diezFloat(a: float, b: float, c: float, d: float, e: float,
                   f: float, g: float, h: float, i: float, j: float): float {
  return a + b + c + d + e + f + g + h + i + j;
}
function id(x: integer): integer { return x; }
print(veinte(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20));
print(diezFloat(0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0));
// todos los argumentos son temporales vivos en registros al llamar
print(veinte(id(1), id(2), id(3), id(4), id(5), id(6), id(7), id(8), id(9), id(10),
             id(11), id(12), id(13), id(14), id(15), id(16), id(17), id(18), id(19), id(20)));
// llamada indirecta con todos los registros ocupados
let f = veinte;
print(f(id(1), id(2), id(3), id(4), id(5), id(6), id(7), id(8), id(9), id(10),
        id(11), id(12), id(13), id(14), id(15), id(16), id(17), id(18), id(19), id(20)));
function ultimo(a: integer, b: integer, c: integer, d: integer, e: integer,
                f: integer, g: integer, h: integer, i: integer, j: integer,
                k: integer, l: integer, m: integer, n: integer, o: integer,
                p: integer, q: integer, r: integer, s: integer, t: integer): integer {
  return t;
}
print(ultimo(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20));
