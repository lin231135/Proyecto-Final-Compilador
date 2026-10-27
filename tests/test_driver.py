from driver import analizar


def test_programa_valido_sin_errores():
    resultado = analizar("let x: integer = 1;")
    assert resultado.ok is True
    assert resultado.errores == []


def test_error_sintactico_tiene_linea_y_columna():
    resultado = analizar("let x: integer = ;")
    assert resultado.ok is False
    assert len(resultado.errores_sintacticos) >= 1
    error = resultado.errores_sintacticos[0]
    assert error.category == "general"
    assert error.line >= 1
    assert error.column >= 0


def test_no_imprime_en_stderr(capsys):
    analizar("let x: integer = ;")
    captured = capsys.readouterr()
    assert captured.err == ""
