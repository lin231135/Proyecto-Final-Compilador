// @caso: mas argumentos que registros tambien en AArch64 (ocho por registro)
// @salida: -5
// @arm: , [sp, #64]
// @arm: , [sp, #72]
function alterna(a: integer, b: integer, c: integer, d: integer, e: integer,
                 f: integer, g: integer, h: integer, i: integer, j: integer): integer {
  return a - b + c - d + e - f + g - h + i - j;
}
print(alterna(1, 2, 3, 4, 5, 6, 7, 8, 9, 10));
