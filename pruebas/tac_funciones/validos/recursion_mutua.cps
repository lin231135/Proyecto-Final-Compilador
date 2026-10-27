// @caso: par/impar se llaman entre si (la declaracion posterior se resuelve por el prepass)
// @salida: true | false
function par(n: integer): boolean { if (n == 0) { return true; } return impar(n - 1); }
function impar(n: integer): boolean { if (n == 0) { return false; } return par(n - 1); }
print(par(10));
print(par(7));
