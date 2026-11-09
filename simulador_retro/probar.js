// Ejecuta archivos .asm con el simulador de MIPSTATION 3000 desde Node.
//
//     node simulador_retro/probar.js programa.asm [otro.asm ...]
//     node simulador_retro/probar.js --json --max=N a.asm b.asm   (lo usa verificar.py)
//
// Sin --json imprime la salida del programa y termina con su codigo de salida.
'use strict';
const fs = require('fs');
const MIPS = require('./mips.js');

const args = process.argv.slice(2);
const json = args.includes('--json');
const opcionMax = args.find((a) => a.startsWith('--max='));
const maxInstrucciones = opcionMax ? Number(opcionMax.slice(6)) : undefined;
const archivos = args.filter((a) => !a.startsWith('--'));
if (!archivos.length) {
  console.error('uso: node probar.js [--json] programa.asm ...');
  process.exit(2);
}

const resultados = {};
let codigo = 0;
for (const ruta of archivos) {
  const fuente = fs.readFileSync(ruta, 'utf8');
  const inicio = process.hrtime.bigint();
  try {
    const r = MIPS.simular(fuente, { maxInstrucciones });
    const ms = Number(process.hrtime.bigint() - inicio) / 1e6;
    resultados[ruta] = { ok: true, salida: r.salida, codigo: r.codigoSalida, instrucciones: r.instrucciones, ms };
    if (!json) {
      process.stdout.write(r.salida);
      codigo = r.codigoSalida;
    }
  } catch (e) {
    const linea = e.linea ? `linea ${e.linea}: ` : '';
    resultados[ruta] = { ok: false, error: linea + e.message };
    if (!json) {
      console.error(`ERROR ${linea}${e.message}`);
      codigo = 3;
    }
  }
}
if (json) process.stdout.write(JSON.stringify(resultados));
process.exit(json ? 0 : codigo);
