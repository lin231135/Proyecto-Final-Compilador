// @caso: campos de todos los tipos, valores por defecto, herencia e identidad
// @salida: 0 | 0.0 | false | null | null | 3 | 2.5 | true | ok | <Punto> | <Punto3D> | [<Punto>, null] | false | true
class Punto {
  let x: integer;
  let y: float;
  let visible: boolean;
  let nombre: string;
  let otro: Punto;
}
class Punto3D : Punto { let z: integer = 9; }
let p: Punto = new Punto();
print(p.x); print(p.y); print(p.visible); print(p.nombre); print(p.otro);
p.x = 3; p.y = 2.5; p.visible = true; p.nombre = "ok";
print(p.x); print(p.y); print(p.visible); print(p.nombre);
print(p);
let q: Punto = new Punto3D();
print(q);
print([p, null]);
print(p == new Punto());
print(p == p);
