// @caso: una funcion viaja como argumento (par codigo-entorno) y se llama indirectamente
// @salida: 12
// @contiene: callc
// @mips: clo_fn_doble: .word fn_doble, 0
function doble(x: integer): integer { return x * 2; }
function aplica(f, x: integer): integer { return f(f(x)); }
print(aplica(doble, 3));
