// @caso: funcion anidada modifica la variable de su entorno de definicion (enlace de acceso)
// @salida: 3
// @contiene: up1.c
function contador(): integer {
  let c: integer = 0;
  function inc(): integer { c = c + 1; return c; }
  inc();
  inc();
  return inc();
}
print(contador());
