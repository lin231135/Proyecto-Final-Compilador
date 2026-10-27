// @caso: try/catch: el handler captura el acceso fuera de rango
// @salida: antes | capturado | despues
// @contiene: try L
let xs: integer[] = [1, 2];
print("antes");
try { print(xs[10]); } catch (err) { print("capturado"); }
print("despues");
