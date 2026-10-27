// @caso: let/const, reasignacion, asignacion encadenada, declaracion sin inicializar
// @salida: 3 | 3 | 7 | 3.14 | hola mundo
// @contiene: @PI = 3.14
let a: integer = 1;
const PI: float = 3.14;
let b = a + 1;
let c: integer;
c = 7;
a = b = 3;
print(a);
print(b);
print(c);
print(PI);
let s: string = "hola " + "mundo";
print(s);
