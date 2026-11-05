"""CLI (main.py) y pipeline completo (driver.analizar)."""

from driver import analizar
from main import main


def escribir(tmp_path, texto, nombre="p.cps"):
    ruta = tmp_path / nombre
    ruta.write_text(texto, encoding="utf-8")
    return str(ruta)


def test_cli_imprime_tac_y_sale_con_0(tmp_path, capsys):
    ruta = escribir(tmp_path, "let a: integer = 1 + 2;")
    assert main([ruta]) == 0
    salida = capsys.readouterr().out
    assert "func main():" in salida and "@a = 1 + 2" in salida


def test_cli_solo_tac(tmp_path, capsys):
    ruta = escribir(tmp_path, "let a: integer = 1;")
    assert main([ruta, "--tac-only"]) == 0
    assert capsys.readouterr().out.startswith("func main():")


def test_cli_con_errores_no_imprime_tac_y_sale_con_1(tmp_path, capsys):
    ruta = escribir(tmp_path, 'let a: integer = "x";')
    assert main([ruta]) == 1
    salida = capsys.readouterr().out
    assert "[tipo]" in salida and "linea 1" in salida
    assert "func main" not in salida


def test_cli_symbols_agrega_tabla_y_registros_de_activacion(tmp_path, capsys):
    ruta = escribir(tmp_path, "function f(a: integer): integer { return a; } let r: integer = f(1);")
    assert main([ruta, "--symbols"]) == 0
    salida = capsys.readouterr().out
    assert "Tabla de simbolos" in salida
    assert "Registros de activacion" in salida
    assert "AR f" in salida


def test_cli_escribe_ensamblador_en_un_archivo(tmp_path, capsys):
    ruta = escribir(tmp_path, "print(1);")
    salida = tmp_path / "p.asm"
    assert main([ruta, "-o", str(salida)]) == 0
    assert "main:" in salida.read_text(encoding="utf-8")


def test_cli_asm_imprime_mips_por_defecto(tmp_path, capsys):
    assert main([escribir(tmp_path, "print(1);"), "--asm"]) == 0
    assert "syscall" in capsys.readouterr().out


def test_cli_target_arm64(tmp_path, capsys):
    assert main([escribir(tmp_path, "print(1);"), "--asm", "--target", "arm64"]) == 0
    assert "_start:" in capsys.readouterr().out


def test_cli_run_ejecuta_el_programa(tmp_path, capsys):
    assert main([escribir(tmp_path, "print(2 + 3);"), "--run", "--simulador", "interno"]) == 0
    assert capsys.readouterr().out == "5\n"


def test_cli_run_devuelve_el_codigo_del_programa(tmp_path, capsys):
    ruta = escribir(tmp_path, "print(1 / 0);")
    assert main([ruta, "--run", "--simulador", "interno"]) == 1
    assert "division entre cero" in capsys.readouterr().out


def test_cli_regs_muestra_el_reporte(tmp_path, capsys):
    assert main([escribir(tmp_path, "print(1);"), "--regs"]) == 0
    assert "TOTAL getReg" in capsys.readouterr().out


def test_cli_con_errores_no_genera_ensamblador(tmp_path, capsys):
    salida = tmp_path / "p.asm"
    assert main([escribir(tmp_path, 'let a: integer = "x";'), "-o", str(salida)]) == 1
    assert not salida.exists()


def test_cli_reporta_error_del_backend(tmp_path, capsys):
    ruta = escribir(tmp_path, 'function m(x) { print(x); } m(1); m("a");')
    assert main([ruta, "--asm"]) == 1
    assert "Error de generacion de codigo" in capsys.readouterr().out


def test_cli_simulador_no_disponible_se_reporta(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("MARS_JAR", raising=False)
    monkeypatch.setattr("simulador.ejecucion.buscar_mars", lambda: None)
    assert main([escribir(tmp_path, "print(1);"), "--run", "--simulador", "mars"]) == 1
    assert "No se pudo ejecutar" in capsys.readouterr().out


def test_error_sintactico_se_reporta_con_linea_y_no_hay_tac():
    r = analizar("let x: integer = 3\nprint(x);")
    assert r.errores and r.errores[0].line == 2
    assert r.tac is None


def test_error_lexico_se_reporta():
    r = analizar("let x: integer = 3 # 4;")
    assert r.errores and r.tac is None


def test_generar_false_solo_analiza():
    r = analizar("let a: integer = 1;", generar=False)
    assert r.ok and r.tac is None and r.generador is None


def test_programa_vacio():
    r = analizar("")
    assert r.ok
    assert r.tac.function("main").lines() == []


def test_solo_comentarios():
    r = analizar("// nada\n/* nada */")
    assert r.ok and r.tac is not None
