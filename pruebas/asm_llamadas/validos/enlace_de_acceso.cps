// @caso: los marcos intermedios conservan su enlace de acceso (up2)
// @salida: 18 | 3
// @contiene: up2.a
// @mips: sw $v1, 8($fp)
// @mips: lw $t8, 8($fp)
// @arm: str x15, [x29, #8]
function exterior(): integer {
  let a: integer = 1;
  function medio(): integer {
    let b: integer = 5;
    function interior(): integer { a = a + 1; return a + b; }
    return interior() + interior() + a;
  }
  let r: integer = medio();
  print(r);
  return a;
}
print(exterior());
