// @caso: 19 valores cruzan llamadas: se agotan los registros $s y el resto se salva en la pila
// @salida: 210
// @salvados: 5
// @mips: sw $s7
function id(x: integer): integer { return x; }
function f(): integer {
  return (id(1) + (id(2) + (id(3) + (id(4) + (id(5) + (id(6) + (id(7) + (id(8) + (id(9) + (id(10) + (id(11) + (id(12) + (id(13) + (id(14) + (id(15) + (id(16) + (id(17) + (id(18) + (id(19) + id(20))))))))))))))))))));
}
print(f());
