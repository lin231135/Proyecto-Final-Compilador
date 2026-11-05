// @caso: concatenacion, comparacion por contenido y switch sobre strings
// @salida: ab | x | true | false | true | dos | nulo: null
function nombre(n: string): string { return n + ""; }
print("a" + "b");
print("" + "x");
print("a" + "b" == "ab");
print("abc" == "abd");
print(nombre("hola") != "chao");
let s: string = "b";
switch (s) {
  case "a":
    print("uno");
    break;
  case "b":
    print("dos");
    break;
  default:
    print("otro");
}
let vacio: string;
print("nulo: " + vacio);
