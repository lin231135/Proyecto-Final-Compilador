// @caso: R20 acceso a un atributo inexistente
// @error: clase
class Animal {
  let nombre: string;
}
let a: Animal = new Animal();
print(a.edad);
