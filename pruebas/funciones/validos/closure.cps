// @caso: R15 funcion anidada resuelve la variable de su entorno de definicion
function externa(): integer {
  let x: integer = 10;
  function interna(): integer {
    return x;
  }
  return interna();
}
