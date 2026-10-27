// @caso: R11 nuevo entorno por cada funcion, clase y bloque
let global: integer = 1;

function f(): integer {
  let local: integer = 2;
  return local;
}

class C {
  let campo: integer;
}

{
  let bloque: integer = 3;
}
