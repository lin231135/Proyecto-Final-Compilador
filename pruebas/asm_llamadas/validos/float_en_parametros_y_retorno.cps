// @caso: float como argumento y retorno, con conversion implicita de integer
// @salida: 1.5 | 3.0 | 6.0
// @contiene: itof
// @mips: cvt.d.w
// @mips: add.d
// @arm: scvtf
function media(a: float, b: float): float { return (a + b) / 2; }
function aFloat(n: integer): float { return n; }
print(media(1, 2));
print(aFloat(3));
let f: float = aFloat(4) * 1.5;
print(f);
