// @caso: variables de dos entornos distintos (up1 y up2)
// @salida: 25
// @contiene: up2.a
// @contiene: up1.b
function nivel1(): integer {
  let a: integer = 1;
  function nivel2(): integer {
    let b: integer = 10;
    function nivel3(): integer { a = a + 1; return a + b; }
    return nivel3();
  }
  return nivel2() + nivel2();
}
print(nivel1());
