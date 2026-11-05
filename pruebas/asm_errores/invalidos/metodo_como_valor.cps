// @caso: un metodo no es un valor (necesitaria su receptor)
// @error_backend: no se puede usar como valor
class C { function m(): integer { return 1; } }
let c: C = new C();
let f = c.m;
