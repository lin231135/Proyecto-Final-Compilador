// @caso: objetos que referencian objetos; null; asignacion a atributo anidado
// @salida: 24 | 48
class Nodo {
  let val: integer;
  let sig: Nodo;
  function constructor(v: integer) { this.val = v; this.sig = null; }
  function suma(): integer {
    if (this.sig == null) { return this.val; }
    return this.val + this.sig.suma();
  }
  function doble(): integer { return this.suma() * 2; }
}
let n1: Nodo = new Nodo(1);
n1.sig = new Nodo(2);
n1.sig.sig = new Nodo(3);
n1.sig.val = 20;
print(n1.suma());
print(n1.doble());
