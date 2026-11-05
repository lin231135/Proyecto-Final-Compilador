// @caso: leer un campo, llamar un metodo o indexar null es un error de ejecucion
// @salida: acceso a null | acceso a null | acceso a null | acceso a null | acceso a null
class A { let x: integer; function m(): integer { return this.x; } }
class B : A { function m(): integer { return 2; } }
let a: A = null;
let l: integer[] = null;
try { print(a.x); } catch (e) { print(e); }
try { a.x = 3; } catch (e) { print(e); }
try { print(a.m()); } catch (e) { print(e); }
try { print(l[0]); } catch (e) { print(e); }
try { foreach (v in l) { print(v); } } catch (e) { print(e); }
