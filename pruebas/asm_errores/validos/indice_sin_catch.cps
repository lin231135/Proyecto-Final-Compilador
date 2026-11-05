// @caso: un indice fuera de rango sin catch termina el programa con codigo 1
// @salida: antes | Error de ejecucion: indice fuera de rango
// @codigo_salida: 1
// @mips: __rt_err_index
let xs: integer[] = [1, 2];
print("antes");
print(xs[2]);
print("no llega");
