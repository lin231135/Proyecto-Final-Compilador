// @caso: un indice negativo tambien esta fuera de rango, al leer y al escribir
// @salida: indice fuera de rango | indice fuera de rango
let xs: integer[] = [1, 2];
let i: integer = 0 - 1;
try { print(xs[i]); } catch (e) { print(e); }
try { xs[i] = 5; } catch (e) { print(e); }
