# Simuladores externos

Copie aquí `Mars4_5.jar` para usar MARS desde el compilador, el IDE y la batería:

```bash
python main.py programa.cps --run --simulador mars
python pruebas/runner.py --simulador mars
```

También puede indicar otra ruta con la variable de entorno `MARS_JAR`. SPIM se busca en el
`PATH`. Los simuladores internos (`simulador/`) no necesitan nada de esto.
