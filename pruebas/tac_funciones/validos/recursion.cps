// @caso: factorial y fibonacci recursivos
// @salida: 120 | 55
// @contiene: call fib, 1
function fact(n: integer): integer { if (n <= 1) { return 1; } return n * fact(n - 1); }
function fib(n: integer): integer { if (n <= 1) { return n; } return fib(n - 1) + fib(n - 2); }
print(fact(5));
print(fib(10));
