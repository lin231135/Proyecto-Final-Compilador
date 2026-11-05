// @caso: un error dentro de un catch lo atrapa el try exterior
// @salida: interno division entre cero | externo indice fuera de rango | fin
try {
  try {
    print(1 / 0);
  } catch (a) {
    print("interno " + a);
    let l: integer[] = [];
    print(l[0]);
  }
} catch (b) {
  print("externo " + b);
}
print("fin");
