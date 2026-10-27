// @caso: DEC-3 null asignable a clase/arreglo y reasignable sin anotacion
class A {}
let a: A = null;
let b: integer[] = null;
let d = null;
d = new A();
d = [1, 2, 3];
