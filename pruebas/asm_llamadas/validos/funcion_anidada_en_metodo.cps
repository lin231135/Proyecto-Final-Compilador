// @caso: una funcion anidada en un metodo se puede llamar y ve this por el enlace de acceso
// @salida: 15
// @contiene: up1.this
class Caja {
  let v: integer = 10;
  function mas(n: integer): integer {
    function suma(): integer { return n + this.v; }
    return suma();
  }
}
print(new Caja().mas(5));
