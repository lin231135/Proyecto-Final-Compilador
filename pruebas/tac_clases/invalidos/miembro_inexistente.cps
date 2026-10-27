// @caso: acceso a un atributo que no existe
// @error: clase
class P { let x: integer = 1; }
let p: P = new P();
print(p.y);
