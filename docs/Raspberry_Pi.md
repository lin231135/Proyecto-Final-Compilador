# Probar en la Raspberry Pi 4

La Raspberry Pi 4 tiene un procesador ARM Cortex-A72: **no ejecuta instrucciones MIPS**.
Hay dos formas de probar el compilador en ella, y conviene mostrar las dos:

| Código | Cómo corre en la Raspberry | Requisito |
|---|---|---|
| **AArch64** | directamente en el procesador | Raspberry Pi OS de **64 bits** |
| **MIPS32** (lo que pide el enunciado) | dentro de un simulador | SPIM o MARS, en 32 o 64 bits |

Para saber cuál sistema tiene:

```bash
uname -m      # aarch64 = 64 bits; armv7l = 32 bits
```

Con `armv7l` el código AArch64 no corre: use MIPS con SPIM o instale la versión de 64
bits del sistema.

## Preparación

```bash
sudo apt update
sudo apt install -y git python3-venv binutils spim
git clone <url-del-repositorio>
cd Proyecto-Final-Compilador
```

## Probar todo con un comando

```bash
bash scripts/probar_en_raspberry.sh
```

Crea un entorno de Python, corre toda la batería ensamblando y ejecutando cada programa
en el procesador real, la repite con MIPS en SPIM y termina con las pruebas unitarias.

## Compilar y ejecutar un programa

En la Raspberry `--run` usa el procesador real para `arm64`:

```bash
python3 -m venv .venv-pi && . .venv-pi/bin/activate
pip install -r requirements-pi.txt

python main.py pruebas/demo/programa_completo.cps --target arm64 --run
```

Paso a paso, para ver cada herramienta:

```bash
python main.py programa.cps --target arm64 -o programa.s
as programa.s -o programa.o
ld programa.o -o programa
./programa
echo $?          # 0, o 1 si hubo un error de ejecución sin catch
```

El programa es estático y no usa libc: solo llamadas al sistema de Linux (`write`,
`exit`, `mmap`). Se puede inspeccionar con `objdump -d programa`.

MIPS en SPIM:

```bash
python main.py programa.cps -o programa.asm
spim -quiet -file programa.asm
```

MIPS en MARS (necesita `sudo apt install default-jre` y `Mars4_5.jar`):

```bash
java -jar Mars4_5.jar nc programa.asm
```

## Sin la Raspberry a mano

`simulador/aarch64.py` ejecuta el ensamblador AArch64 en cualquier equipo:

```bash
python main.py programa.cps --target arm64 --run --simulador interno
```

Encuentra errores de generación de código, pero no reemplaza la prueba en el
procesador real: no ensambla con `as`, solo interpreta el subconjunto de instrucciones
que emite el compilador.
