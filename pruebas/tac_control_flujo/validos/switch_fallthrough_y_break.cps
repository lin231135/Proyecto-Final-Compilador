// @caso: switch: sin break cae al siguiente caso; con break sale; default
// @salida: b | c | d | uno | otro
switch (2) {
  case 1: print("a");
  case 2: print("b");
  case 3: print("c");
  default: print("d");
}
let x: integer = 1;
switch (x) {
  case 1: print("uno"); break;
  case 2: print("dos");
  default: print("nunca");
}
switch (9) {
  case 1: print("x");
  default: print("otro");
}
