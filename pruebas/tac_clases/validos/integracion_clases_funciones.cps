// @caso: integracion: clases, herencia, despacho dinamico, globales, listas anidadas, bloques y clase local
// @salida: 26 | 84 | 54 | 1011 | 26 | 3 | 6 | con "comillas" y // nada | 10 | 20 | 30 | 40 | 7 | 8
let g: integer = 10;
function dobla(x: integer): integer { return x * 2; }
class Caja {
  let v: integer;
  function constructor(v: integer) { this.v = v; if (v < 0) { return; } this.v = v + g; }
  function otra(): Caja { return new Caja(this.v + 1); }
  function usa(): integer { return dobla(this.v) + g; }
  function interna(): integer {
    function aux(n: integer): integer { return n + this.v; }
    return 1;
  }
}
class Sub : Caja {
  function usa(): integer { return this.v + 1000; }
  function supera(): integer { return this.otra().usa(); }
}
let c: Caja = new Caja(5);
print(c.otra().v);
print(c.otra().otra().usa());
let s: Sub = new Sub(1);
print(s.supera());
let cajas: Caja[] = [c, s];
print(cajas[1].usa());
print(cajas[0].otra().v);
let a: integer = 0;
print(a = 3);
print(a > 2 ? dobla(a) : dobla(a + 1));
print("con \"comillas\" y // nada");
let m: integer[][] = [[1, 2], [3, 4]];
foreach (fila in m) { foreach (x in fila) { print(x * g); } }
{ class Local { let q: integer = 7; } let l: Local = new Local(); print(l.q); }
function vacio() { }
vacio();
print(dobla(dobla(dobla(1))));
