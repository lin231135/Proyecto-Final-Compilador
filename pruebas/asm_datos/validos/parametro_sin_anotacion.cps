// @caso: el tipo de un parametro sin anotacion se deduce de sus llamadas
// @salida: hola | 42 | 2.5
function muestra(x) { print(x); }
muestra("hola");
function siguiente(n) { print(n + 1); }
siguiente(41);
function medio(v) { print(v / 2); }
medio(5.0);
