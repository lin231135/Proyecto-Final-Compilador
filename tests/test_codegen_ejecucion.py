"""
Ejecucion end-to-end: el TAC generado se corre con el simulador y se compara
la salida del programa. Valida que la traduccion es correcta, no solo
parecida a lo esperado.
"""

import pytest

from codegen.interpreter import ejecutar
from tests.helpers import compilar

PROGRAMAS = [
    (
        "fibonacci",
        "function fib(n: integer): integer { if (n <= 1) { return n; } return fib(n - 1) + fib(n - 2); }"
        "for (let i: integer = 0; i < 8; i = i + 1) { print(fib(i)); }",
        ["0", "1", "1", "2", "3", "5", "8", "13"],
    ),
    (
        "ackermann_pequeno",
        "function ack(m: integer, n: integer): integer {"
        "  if (m == 0) { return n + 1; }"
        "  if (n == 0) { return ack(m - 1, 1); }"
        "  return ack(m - 1, ack(m, n - 1)); }"
        "print(ack(2, 3));",
        ["9"],
    ),
    (
        "contadores_independientes",
        """
        function nuevo(): integer {
          let c: integer = 0;
          function inc(): integer { c = c + 1; return c; }
          inc();
          return inc();
        }
        print(nuevo()); print(nuevo());
        """,
        ["2", "2"],
    ),
    (
        "bubble_sort",
        """
        let xs: integer[] = [5, 2, 9, 1, 7];
        let n: integer = 5;
        for (let i: integer = 0; i < n; i = i + 1) {
          for (let j: integer = 0; j < n - 1 - i; j = j + 1) {
            if (xs[j] > xs[j + 1]) {
              let t: integer = xs[j];
              xs[j] = xs[j + 1];
              xs[j + 1] = t;
            }
          }
        }
        foreach (x in xs) { print(x); }
        """,
        ["1", "2", "5", "7", "9"],
    ),
    (
        "pila_con_objetos",
        """
        class Nodo { let v: integer; let sig: Nodo;
          function constructor(v: integer, sig: Nodo) { this.v = v; this.sig = sig; } }
        class Pila { let tope: Nodo;
          function push(v: integer) { this.tope = new Nodo(v, this.tope); }
          function pop(): integer { let v: integer = this.tope.v; this.tope = this.tope.sig; return v; }
          function vacia(): boolean { return this.tope == null; } }
        let p: Pila = new Pila();
        p.push(1); p.push(2); p.push(3);
        while (!p.vacia()) { print(p.pop()); }
        """,
        ["3", "2", "1"],
    ),
    (
        "polimorfismo_en_lista",
        """
        class Forma { function area(): integer { return 0; } }
        class Cuadrado : Forma { let l: integer;
          function constructor(l: integer) { this.l = l; }
          function area(): integer { return this.l * this.l; } }
        class Rect : Forma { let a: integer; let b: integer;
          function constructor(a: integer, b: integer) { this.a = a; this.b = b; }
          function area(): integer { return this.a * this.b; } }
        let fs: Forma[] = [new Cuadrado(3), new Rect(2, 5), new Forma()];
        let total: integer = 0;
        foreach (f in fs) { total = total + f.area(); }
        print(total);
        """,
        ["19"],
    ),
    (
        "this_y_metodos_entre_si",
        """
        class C { let n: integer = 10;
          function a(): integer { return this.b() + 1; }
          function b(): integer { return this.n; } }
        print(new C().a());
        """,
        ["11"],
    ),
    (
        "switch_en_bucle",
        """
        for (let i: integer = 0; i < 4; i = i + 1) {
          switch (i) { case 0: print("cero"); break; case 2: print("dos"); default: print("resto"); }
        }
        """,
        ["cero", "resto", "dos", "resto", "resto"],
    ),
    (
        "foreach_con_continue_y_break",
        """
        let s: integer = 0;
        foreach (x in [1, 2, 3, 4, 5, 6]) {
          if (x == 2) { continue; }
          if (x > 4) { break; }
          s = s + x;
        }
        print(s);
        """,
        ["8"],
    ),
    (
        "cortocircuito_no_evalua",
        """
        let veces: integer = 0;
        function t(): boolean { veces = veces + 1; return true; }
        function f(): boolean { veces = veces + 1; return false; }
        let r1: boolean = f() && t();
        let r2: boolean = t() || f();
        let r3: boolean = f() || t();
        print(veces);
        print(r1); print(r2); print(r3);
        """,
        ["4", "false", "true", "true"],
    ),
    (
        "variables_de_distintos_bloques",
        """
        let x: integer = 1;
        { let x: integer = 2; { let x: integer = 3; print(x); } print(x); }
        print(x);
        """,
        ["3", "2", "1"],
    ),
    (
        "closure_comparte_estado",
        """
        function f(): integer {
          let n: integer = 0;
          function a() { n = n + 1; }
          function b() { n = n * 10; }
          a(); b(); a();
          return n;
        }
        print(f());
        """,
        ["11"],
    ),
]


@pytest.mark.parametrize("nombre,fuente,salida", PROGRAMAS, ids=[p[0] for p in PROGRAMAS])
def test_ejecucion(nombre, fuente, salida):
    r = compilar(fuente)
    assert ejecutar(r) == salida
    assert r.generador.temp_leaks == 0
