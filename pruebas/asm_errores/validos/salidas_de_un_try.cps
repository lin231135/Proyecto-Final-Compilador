// @caso: break, continue y return dentro de try desactivan su manejador
// @salida: 1 | 3 | 4 | 1 | Error de ejecucion: indice fuera de rango
// @codigo_salida: 1
// @contiene: endtry
function f(): integer {
  let i: integer = 0;
  while (i < 5) {
    try {
      i = i + 1;
      if (i == 2) { continue; }
      if (i == 4) { break; }
      print(i);
    } catch (e) {
      print("no");
    }
  }
  return i;
}
function g(): integer {
  try { return 1; } catch (e) { return 2; }
}
let xs: integer[] = [1];
print(f());
print(g());
print(xs[3]);
