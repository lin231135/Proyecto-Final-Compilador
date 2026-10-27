// @caso: && || ! con cortocircuito: el operando derecho no se evalua si no hace falta
// @salida: false | true | false | false | true | 0 | true | true | 2 | true
// @contiene: goto
let t: boolean = true;
let f: boolean = false;
let n: integer = 0;
function marca(): boolean { n = n + 1; return true; }
print(t && f);
print(t || f);
print(!t);
print(f && marca());
print(t || marca());
print(n);
print(t && marca());
print(f || marca());
print(n);
print(t && !f || f);
