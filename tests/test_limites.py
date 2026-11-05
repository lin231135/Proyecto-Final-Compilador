"""
Casos en los limites de lo que un procesador puede codificar: un marco enorme
obliga a calcular direcciones que no caben en un inmediato. Los simuladores
rechazan lo que `as`, MARS y SPIM no ensamblarian, asi que aqui un fallo de
codificacion aparece como `ErrorEnsamblado`.
"""

import pytest

from backend import BackendError, generar_ensamblador
from backend.target import texto_double
from main import main
from simulador import aarch64
from simulador.ejecucion import ejecutar_codigo
from tests.helpers import compilar

TARGETS = ["mips", "arm64"]


def locales(n: int) -> str:
    return "".join(f"let v{i}: integer = {i};" for i in range(n))


def correr(fuente: str, target: str) -> str:
    return ejecutar_codigo(generar_ensamblador(compilar(fuente), target).codigo, target, "interno").salida


@pytest.mark.parametrize("target", TARGETS)
def test_marco_enorme_con_llamadas(target):
    fuente = f"""
    function id(x: integer): integer {{ return x; }}
    function f(): integer {{
      {locales(9000)}
      return id(v8999) + v0;
    }}
    print(f());
    """
    assert correr(fuente, target) == "8999\n"


@pytest.mark.parametrize("target", TARGETS)
def test_try_en_un_marco_enorme(target):
    fuente = f"""
    function f(): integer {{
      {locales(2000)}
      let n: integer = v1999;
      try {{ print(1 / (n - n)); }} catch (e) {{ print(e); }}
      return n;
    }}
    print(f());
    """
    assert correr(fuente, target) == "division entre cero\n1999\n"


@pytest.mark.parametrize("target", TARGETS)
def test_float_y_booleano_en_un_marco_enorme(target):
    fuente = f"""
    function f(): float {{
      {locales(9000)}
      let x: float = 1.5;
      let b: boolean = v1 == 1;
      if (b) {{ x = x + 1; }}
      return x;
    }}
    print(f());
    """
    assert correr(fuente, target) == "2.5\n"


@pytest.mark.parametrize("target", TARGETS)
def test_muchas_globales(target):
    declaraciones = "".join(f"let g{i}: integer = {i};" for i in range(9000))
    assert correr(declaraciones + "print(g8999 + g1);", target) == "9000\n"


@pytest.mark.parametrize("target", TARGETS)
def test_constantes_de_32_bits(target):
    assert correr("print(70000); print(2147483647); print(-2147483647); print(65536);", target) == (
        "70000\n2147483647\n-2147483647\n65536\n"
    )


@pytest.mark.parametrize("target", TARGETS)
def test_suma_con_literal_grande_y_con_cero_a_la_izquierda(target):
    assert correr("let a: integer = 5; print(a + 70000); print(a - 70000); print(0 + 5); print(0 - 5);", target) == (
        "70005\n-69995\n5\n-5\n"
    )


@pytest.mark.parametrize("target", TARGETS)
def test_flotantes_con_exponente_en_el_ensamblador(target):
    assert correr("print(10000000000000000.0 / 10000000000000000.0);", target) == "1.0\n"


@pytest.mark.parametrize(
    "valor,texto",
    [("1e+16", "1.0e+16"), ("1.5e-07", "1.5e-07"), ("3.14", "3.14"), ("-2e+20", "-2.0e+20"), ("0.0", "0.0")],
)
def test_todo_double_lleva_punto_decimal(valor, texto):
    assert texto_double(valor) == texto


def test_literal_que_no_cabe_en_float():
    with pytest.raises(BackendError, match="no cabe"):
        generar_ensamblador(compilar("print(" + "9" * 400 + ".0);"))


def test_el_archivo_generado_usa_finales_de_linea_de_unix(tmp_path, capsys):
    fuente = tmp_path / "p.cps"
    fuente.write_text("print(1);", encoding="utf-8")
    salida = tmp_path / "p.s"
    assert main([str(fuente), "--target", "arm64", "-o", str(salida)]) == 0
    assert b"\r" not in salida.read_bytes()


@pytest.mark.parametrize(
    "instruccion",
    [
        "add x9, x9, #4096",
        "add w9, wzr, #5",
        "add w9, w10, x11",
        "mov x9, w10",
        "movz w9, #70000",
        "cmp w9, #5000",
        "ldr x9, [xzr]",
        "ldr x9, [x10, #40000]",
        "ldr x9, [x10, #300001]",
        "ldrb x9, [x10]",
        "str sp, [x10]",
        "scvtf d1, x9",
        "add x9, x9, sp",
    ],
)
def test_arm_rechaza_lo_que_as_no_puede_codificar(instruccion):
    with pytest.raises(aarch64.ErrorEnsamblado):
        aarch64.simular(f".text\n_start:\n {instruccion}\n")
