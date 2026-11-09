/*
 * MIPSTATION 3000 — ensamblador y simulador de MIPS32 en JavaScript.
 *
 * Funciona en el navegador (window.MIPS) y en Node (require('./mips.js')).
 * Sigue el comportamiento por defecto de MARS 4.5:
 *   - sin delay slots, memoria little-endian, accesos alineados obligatorios;
 *   - .text en 0x00400000, .data en 0x10010000, $gp = 0x10008000,
 *     $sp = 0x7fffeffc; el programa empieza en la primera instruccion de .text;
 *   - add/addi/sub disparan excepcion por desbordamiento;
 *   - `div` de dos operandos entre cero no hace nada (como MARS);
 *   - syscalls 1-12, 17, 30-36, 40-42 (incluye MIDI 31/33).
 *
 * Cada linea de codigo ocupa una "ranura" de 4 bytes: las pseudoinstrucciones
 * no se expanden, asi que las direcciones de codigo pueden diferir de MARS,
 * pero `la`, `jal`, `jalr` y `.word etiqueta` son consistentes entre si.
 */
(function (raiz) {
  'use strict';

  const NOMBRES = ('zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 ' +
    's0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra').split(' ');
  const REG = {};
  NOMBRES.forEach((n, i) => { REG[n] = i; REG[String(i)] = i; });
  REG.s8 = 30;

  const BASE_TEXTO = 0x00400000;
  const BASE_SEGMENTO = 0x10000000; // incluye el area de $gp
  const BASE_DATOS = 0x10010000;
  const GP_INICIAL = 0x10008000;
  const SP_INICIAL = 0x7fffeffc;
  const FIN_PILA = 0x7ffff000; // exclusivo
  const TAMANIO_PILA = 8 * 1024 * 1024;
  const BASE_PILA = FIN_PILA - TAMANIO_PILA;
  const MAX_SEGMENTO = 256 * 1024 * 1024;
  const SUMIDERO = 32; // indice donde caen las escrituras a $zero
  const PAUSA = -2;

  class ErrorMIPS extends Error {
    constructor(mensaje, linea) {
      super(mensaje);
      this.linea = linea;
    }
  }

  const hex = (v) => '0x' + (v >>> 0).toString(16).padStart(8, '0');

  // ------------------------------------------------------------------
  // Lexico
  // ------------------------------------------------------------------

  function quitarComentario(linea) {
    let comilla = null;
    for (let i = 0; i < linea.length; i++) {
      const c = linea[i];
      if (comilla) {
        if (c === '\\') i++;
        else if (c === comilla) comilla = null;
      } else if (c === '"' || c === "'") {
        comilla = c;
      } else if (c === '#') {
        return linea.slice(0, i);
      }
    }
    return linea;
  }

  function separarOperandos(texto) {
    const partes = [];
    let actual = '';
    let comilla = null;
    for (let i = 0; i < texto.length; i++) {
      const c = texto[i];
      if (comilla) {
        actual += c;
        if (c === '\\' && i + 1 < texto.length) { actual += texto[++i]; continue; }
        if (c === comilla) comilla = null;
      } else if (c === '"' || c === "'") {
        comilla = c;
        actual += c;
      } else if (c === ',') {
        partes.push(actual.trim());
        actual = '';
      } else {
        actual += c;
      }
    }
    if (actual.trim() !== '' || partes.length) partes.push(actual.trim());
    return partes.filter((p, i) => p !== '' || i < partes.length - 1);
  }

  const ESCAPES = { n: 10, t: 9, r: 13, '0': 0, '\\': 92, '"': 34, "'": 39, b: 8, f: 12, v: 11, a: 7 };

  function decodificarCadena(texto, linea) {
    const t = texto.trim();
    if (t.length < 2 || t[0] !== '"' || t[t.length - 1] !== '"') {
      throw new ErrorMIPS('se esperaba una cadena entre comillas', linea);
    }
    const cuerpo = t.slice(1, -1);
    const bytes = [];
    const codificador = new TextEncoder();
    for (let i = 0; i < cuerpo.length; i++) {
      const c = cuerpo[i];
      if (c === '\\') {
        const e = cuerpo[++i];
        if (!(e in ESCAPES)) throw new ErrorMIPS(`secuencia de escape desconocida \\${e}`, linea);
        bytes.push(ESCAPES[e]);
      } else {
        for (const b of codificador.encode(c)) bytes.push(b);
      }
    }
    return bytes;
  }

  // Entero: decimal, 0x hex, 0b binario, 'c' caracter.
  function numero(tok) {
    const t = tok.trim();
    let m;
    if ((m = /^([+-]?)0x([0-9a-f]+)$/i.exec(t))) {
      const v = parseInt(m[2], 16);
      return m[1] === '-' ? -v : v;
    }
    if ((m = /^([+-]?)0b([01]+)$/i.exec(t))) {
      const v = parseInt(m[2], 2);
      return m[1] === '-' ? -v : v;
    }
    if (/^[+-]?\d+$/.test(t)) return parseInt(t, 10);
    if ((m = /^'(\\.|[^\\'])'$/.exec(t))) {
      const c = m[1];
      if (c[0] === '\\') {
        if (!(c[1] in ESCAPES)) return null;
        return ESCAPES[c[1]];
      }
      return c.charCodeAt(0);
    }
    return null;
  }

  // ------------------------------------------------------------------
  // Formato de flotantes como Java (lo que imprime MARS)
  // ------------------------------------------------------------------

  function formatoJava(x, simple) {
    if (Number.isNaN(x)) return 'NaN';
    if (x === Infinity) return 'Infinity';
    if (x === -Infinity) return '-Infinity';
    if (x === 0) return Object.is(x, -0) ? '-0.0' : '0.0';
    let digitos;
    if (simple) {
      for (let p = 1; p <= 9; p++) {
        const s = x.toPrecision(p);
        if (Math.fround(parseFloat(s)) === x) { digitos = parseFloat(s); break; }
      }
    } else {
      digitos = x;
    }
    const a = Math.abs(digitos);
    if (a >= 1e-3 && a < 1e7) {
      const s = String(digitos);
      if (/e/i.test(s)) return digitos.toFixed(20).replace(/0+$/, '').replace(/\.$/, '.0');
      return s.includes('.') ? s : s + '.0';
    }
    let [mantisa, exp] = digitos.toExponential().split('e');
    if (!mantisa.includes('.')) mantisa += '.0';
    return mantisa + 'E' + parseInt(exp, 10);
  }

  // ------------------------------------------------------------------
  // Ensamblador: dos pasadas
  // ------------------------------------------------------------------

  const ALINEACION = { '.half': 2, '.word': 4, '.float': 4, '.double': 8 };

  function ensamblar(fuente) {
    const lineas = fuente.replace(/\r\n?/g, '\n').split('\n');
    const instrucciones = []; // {linea, texto, op, args}
    const etiquetas = new Map();
    const datos = [];
    const parches = []; // {offset, expr, linea}
    const eqv = new Map();
    let enDatos = false;
    let pendientes = [];

    const dirDatos = () => BASE_DATOS + datos.length;
    const alinear = (n) => { while (datos.length % n) datos.push(0); };
    const fijarPendientes = (direccion) => {
      for (const p of pendientes) etiquetas.set(p, direccion);
      pendientes = [];
    };
    const reemplazarEqv = (texto) => {
      if (!eqv.size) return texto;
      return texto.replace(/[A-Za-z_][\w.]*/g, (w) => (eqv.has(w) ? eqv.get(w) : w));
    };

    for (let n = 0; n < lineas.length; n++) {
      const numLinea = n + 1;
      let linea = quitarComentario(lineas[n]).trim();
      let m;
      while ((m = /^([A-Za-z_.$][\w.$]*)\s*:\s*(.*)$/.exec(linea))) {
        const nombre = m[1];
        if (etiquetas.has(nombre) || pendientes.includes(nombre)) {
          throw new ErrorMIPS(`etiqueta repetida '${nombre}'`, numLinea);
        }
        pendientes.push(nombre);
        linea = m[2].trim();
      }
      if (!linea) continue;

      if (linea[0] === '.') {
        const mm = /^(\.\w+)\s*(.*)$/.exec(linea);
        const dir = mm[1].toLowerCase();
        const resto = mm[2].trim();
        if (dir === '.data' || dir === '.kdata') {
          if (!enDatos) fijarPendientes(BASE_TEXTO + 4 * instrucciones.length);
          enDatos = true;
          continue;
        }
        if (dir === '.text' || dir === '.ktext') {
          if (enDatos) fijarPendientes(dirDatos());
          enDatos = false;
          continue;
        }
        if (dir === '.globl' || dir === '.global' || dir === '.extern' || dir === '.set' || dir === '.ent' || dir === '.end') continue;
        if (dir === '.eqv') {
          const e = /^([A-Za-z_][\w.]*)\s*,?\s*(.+)$/.exec(resto);
          if (!e) throw new ErrorMIPS('.eqv necesita un nombre y un valor', numLinea);
          eqv.set(e[1], e[2].trim());
          continue;
        }
        if (!enDatos) throw new ErrorMIPS(`la directiva ${dir} solo se permite en .data`, numLinea);
        directiva(dir, reemplazarEqv(resto), numLinea);
        continue;
      }

      if (enDatos) throw new ErrorMIPS(`instruccion dentro de .data: ${linea}`, numLinea);
      fijarPendientes(BASE_TEXTO + 4 * instrucciones.length);
      linea = reemplazarEqv(linea);
      const im = /^(\S+)\s*(.*)$/.exec(linea);
      instrucciones.push({ linea: numLinea, texto: linea, op: im[1].toLowerCase(), args: im[2] ? separarOperandos(im[2]) : [] });
    }
    fijarPendientes(enDatos ? dirDatos() : BASE_TEXTO + 4 * instrucciones.length);

    function directiva(dir, resto, numLinea) {
      if (ALINEACION[dir]) alinear(ALINEACION[dir]);
      if (dir === '.align') {
        const k = numero(resto);
        if (k === null || k < 0 || k > 3) throw new ErrorMIPS('.align necesita 0, 1, 2 o 3', numLinea);
        alinear(1 << k);
        fijarPendientes(dirDatos());
        return;
      }
      fijarPendientes(dirDatos());
      if (dir === '.space') {
        const k = numero(resto);
        if (k === null || k < 0) throw new ErrorMIPS('.space necesita un tamanio', numLinea);
        for (let i = 0; i < k; i++) datos.push(0);
      } else if (dir === '.ascii' || dir === '.asciiz') {
        for (const parte of separarOperandos(resto)) {
          datos.push(...decodificarCadena(parte, numLinea));
          if (dir === '.asciiz') datos.push(0);
        }
      } else if (dir === '.byte' || dir === '.half' || dir === '.word') {
        const tam = { '.byte': 1, '.half': 2, '.word': 4 }[dir];
        for (const [valor, veces] of valoresRepetidos(resto, numLinea)) {
          for (let r = 0; r < veces; r++) {
            const v = numero(valor);
            if (v === null) {
              if (dir !== '.word') throw new ErrorMIPS(`valor invalido: ${valor}`, numLinea);
              parches.push({ offset: datos.length, expr: valor, linea: numLinea });
              datos.push(0, 0, 0, 0);
            } else {
              for (let b = 0; b < tam; b++) datos.push((v >> (8 * b)) & 0xff);
            }
          }
        }
      } else if (dir === '.float' || dir === '.double') {
        for (const [valor, veces] of valoresRepetidos(resto, numLinea)) {
          const v = Number(valor);
          if (Number.isNaN(v) && !/^[+-]?nan$/i.test(valor)) throw new ErrorMIPS(`numero invalido: ${valor}`, numLinea);
          const buf = new DataView(new ArrayBuffer(8));
          for (let r = 0; r < veces; r++) {
            if (dir === '.float') {
              buf.setFloat32(0, v, true);
              for (let b = 0; b < 4; b++) datos.push(buf.getUint8(b));
            } else {
              buf.setFloat64(0, v, true);
              for (let b = 0; b < 8; b++) datos.push(buf.getUint8(b));
            }
          }
        }
      } else {
        throw new ErrorMIPS(`directiva desconocida ${dir}`, numLinea);
      }
    }

    function valoresRepetidos(resto, numLinea) {
      const salida = [];
      for (const parte of separarOperandos(resto)) {
        const r = /^(.+?)\s*:\s*(\d+)$/.exec(parte);
        if (r && !/^'/.test(parte)) salida.push([r[1], parseInt(r[2], 10)]);
        else if (parte !== '') salida.push([parte, 1]);
        else throw new ErrorMIPS('valor vacio', numLinea);
      }
      return salida;
    }

    const programa = { instrucciones, etiquetas, datos: Uint8Array.from(datos), lineas: lineas.length };
    for (const p of parches) {
      const v = valorEtiqueta(programa, p.expr, p.linea);
      for (let b = 0; b < 4; b++) programa.datos[p.offset + b] = (v >>> (8 * b)) & 0xff;
    }
    return programa;
  }

  // `etiqueta`, `etiqueta+4`, `etiqueta-8`
  function valorEtiqueta(programa, expr, linea) {
    const m = /^([A-Za-z_.$][\w.$]*)\s*(?:([+-])\s*(.+))?$/.exec(expr.trim());
    if (!m || !programa.etiquetas.has(m[1])) throw new ErrorMIPS(`etiqueta desconocida: ${expr}`, linea);
    let v = programa.etiquetas.get(m[1]);
    if (m[2]) {
      const k = numero(m[3]);
      if (k === null) throw new ErrorMIPS(`desplazamiento invalido: ${m[3]}`, linea);
      v += m[2] === '+' ? k : -k;
    }
    return v | 0;
  }

  // ------------------------------------------------------------------
  // CPU
  // ------------------------------------------------------------------

  class CPU {
    constructor(programa, opciones = {}) {
      this.programa = programa;
      this.R = new Int32Array(33);
      this.fbuf = new ArrayBuffer(128);
      this.FV = new DataView(this.fbuf);
      this.cond = new Uint8Array(8);
      this.hi = 0;
      this.lo = 0;
      const tamDatos = BASE_DATOS - BASE_SEGMENTO + programa.datos.length;
      this.seg = new Uint8Array(Math.max(1 << 20, potencia2(tamDatos + (1 << 16))));
      this.seg.set(programa.datos, BASE_DATOS - BASE_SEGMENTO);
      this.segV = new DataView(this.seg.buffer);
      this.pila = new Uint8Array(TAMANIO_PILA);
      this.pilaV = new DataView(this.pila.buffer);
      this.finEstatico = BASE_DATOS + programa.datos.length;
      this.sbrk = (this.finEstatico + 7) & ~7;
      this.R[29] = SP_INICIAL;
      this.R[28] = GP_INICIAL;
      this.pc = 0;
      if (opciones.iniciarEnMain && programa.etiquetas.has('main')) {
        const d = programa.etiquetas.get('main');
        if (d >= BASE_TEXTO && d < BASE_TEXTO + 4 * programa.instrucciones.length) this.pc = (d - BASE_TEXTO) / 4;
      }
      this.pasos = 0;
      this.terminado = false;
      this.cayoAlFinal = false;
      this.codigoSalida = 0;
      this.esperando = null; // 'int' | 'float' | 'double' | 'string' | 'char'
      this.entrada = null;
      this.durmiendo = 0;
      this.despertar = false;
      this.semilla = (opciones.semilla ?? Date.now()) >>> 0;
      this.puntosDeRuptura = new Set();
      this.salida = opciones.salida || (() => {});
      this.aviso = opciones.aviso || (() => {});
      this.midi = opciones.midi || (() => {});
      this.codigo = programa.instrucciones.map((ins, i) => {
        try {
          return this.compilar(ins, i);
        } catch (e) {
          if (e instanceof ErrorMIPS) {
            e.linea = ins.linea;
            e.message = `${e.message}  ->  ${ins.texto}`;
          }
          throw e;
        }
      });
    }

    get lineaActual() {
      const ins = this.programa.instrucciones[this.pc];
      return ins ? ins.linea : null;
    }

    // --- memoria ------------------------------------------------------

    ubicar(dir, n) {
      dir >>>= 0;
      if (dir % n) throw new ErrorMIPS(`acceso desalineado a ${hex(dir)} (${n} bytes)`);
      if (dir >= BASE_SEGMENTO && dir + n <= BASE_SEGMENTO + this.seg.length) {
        this._v = this.segV;
        return dir - BASE_SEGMENTO;
      }
      if (dir >= BASE_PILA && dir + n <= FIN_PILA) {
        this._v = this.pilaV;
        return dir - BASE_PILA;
      }
      if (dir >= BASE_TEXTO && dir < BASE_SEGMENTO) throw new ErrorMIPS(`acceso a memoria del segmento de texto ${hex(dir)}`);
      if (dir < BASE_PILA && dir >= BASE_PILA - (1 << 20)) throw new ErrorMIPS('desbordamiento de pila');
      throw new ErrorMIPS(`direccion invalida ${hex(dir)}`);
    }
    lw(d) { const o = this.ubicar(d, 4); return this._v.getInt32(o, true); }
    lh(d) { const o = this.ubicar(d, 2); return this._v.getInt16(o, true); }
    lhu(d) { const o = this.ubicar(d, 2); return this._v.getUint16(o, true); }
    lb(d) { const o = this.ubicar(d, 1); return this._v.getInt8(o); }
    lbu(d) { const o = this.ubicar(d, 1); return this._v.getUint8(o); }
    sw(d, v) { const o = this.ubicar(d, 4); this._v.setInt32(o, v, true); }
    sh(d, v) { const o = this.ubicar(d, 2); this._v.setInt16(o, v, true); }
    sb(d, v) { const o = this.ubicar(d, 1); this._v.setInt8(o, v); }

    leerPalabraSegura(d) {
      try { return this.lw(d); } catch (e) { return null; }
    }

    crecer(hasta) {
      const necesario = hasta - BASE_SEGMENTO;
      if (necesario <= this.seg.length) return;
      if (necesario > MAX_SEGMENTO) throw new ErrorMIPS('sbrk: memoria agotada');
      const nuevo = new Uint8Array(potencia2(necesario));
      nuevo.set(this.seg);
      this.seg = nuevo;
      this.segV = new DataView(nuevo.buffer);
    }

    cadena(dir) {
      const bytes = [];
      for (let d = dir; ; d++) {
        const b = this.lbu(d);
        if (b === 0) break;
        bytes.push(b);
        if (bytes.length > 1 << 20) throw new ErrorMIPS('cadena sin terminador nulo');
      }
      return new TextDecoder('utf-8').decode(Uint8Array.from(bytes));
    }

    // --- flotantes ----------------------------------------------------

    dbl(n) { return this.FV.getFloat64(4 * n, true); }
    setDbl(n, v) { this.FV.setFloat64(4 * n, v, true); }
    flt(n) { return this.FV.getFloat32(4 * n, true); }
    setFlt(n, v) { this.FV.setFloat32(4 * n, v, true); }
    fw(n) { return this.FV.getInt32(4 * n, true); }
    setFw(n, v) { this.FV.setInt32(4 * n, v, true); }

    // --- traduccion de cada instruccion a una funcion -------------------

    compilar(ins, indice) {
      const op = ins.op;
      const a = ins.args;
      const R = this.R;
      const cpu = this;
      const prog = this.programa;
      const retorno = BASE_TEXTO + 4 * (indice + 1);

      const nargs = (...ns) => {
        if (!ns.includes(a.length)) throw new ErrorMIPS(`'${op}' espera ${ns.join(' o ')} operandos, hay ${a.length}`);
      };
      const reg = (t) => {
        const m = /^\$(\w+)$/.exec(t || '');
        if (!m || !(m[1] in REG)) throw new ErrorMIPS(`registro invalido: ${t}`);
        return REG[m[1]];
      };
      const regD = (t) => { const r = reg(t); return r === 0 ? SUMIDERO : r; };
      const esReg = (t) => /^\$\w+$/.test(t || '') && !/^\$f\d+$/.test(t);
      const freg = (t, par) => {
        const m = /^\$f(\d+)$/.exec(t || '');
        if (!m || +m[1] > 31) throw new ErrorMIPS(`registro de punto flotante invalido: ${t}`);
        const r = +m[1];
        if (par && r % 2) throw new ErrorMIPS(`los double usan registros pares: ${t}`);
        return r;
      };
      const imm = (t) => {
        const v = numero(t || '');
        if (v === null) throw new ErrorMIPS(`inmediato invalido: ${t}`);
        if (v > 0xffffffff || v < -0x80000000) throw new ErrorMIPS(`inmediato fuera de rango: ${t}`);
        return v | 0;
      };
      const destino = (t) => {
        const d = valorEtiqueta(prog, t || '', ins.linea);
        const i = (d - BASE_TEXTO) / 4;
        if (!Number.isInteger(i) || i < 0 || i > prog.instrucciones.length) throw new ErrorMIPS(`'${t}' no es una etiqueta de codigo`);
        return i;
      };
      const memoria = (t) => {
        let m = /^(.*?)\(\s*(\$\w+)\s*\)$/.exec((t || '').trim());
        if (m) {
          const r = reg(m[2]);
          const base = m[1].trim();
          let k = 0;
          if (base !== '') {
            const n = numero(base);
            k = n !== null ? n | 0 : valorEtiqueta(prog, base, ins.linea);
          }
          return () => (R[r] + k) | 0;
        }
        const n = numero(t || '');
        if (n !== null) return () => n | 0;
        const d = valorEtiqueta(prog, t || '', ins.linea);
        return () => d;
      };
      // segundo operando: registro o inmediato
      const fuente = (t) => {
        if (esReg(t)) { const r = reg(t); return { r }; }
        return { k: imm(t) };
      };
      const binaria = (f) => {
        nargs(3);
        const d = regD(a[0]); const s = reg(a[1]); const t = fuente(a[2]);
        if (t.r !== undefined) { const r2 = t.r; return () => { R[d] = f(R[s], R[r2]); }; }
        const k = t.k;
        return () => { R[d] = f(R[s], k); };
      };
      const desborda = (v) => {
        if (v > 2147483647 || v < -2147483648) throw new ErrorMIPS('desbordamiento aritmetico');
        return v;
      };
      const salto = (cmp) => { // op rs, rt|imm, etiqueta
        nargs(3);
        const s = reg(a[0]); const t = fuente(a[1]); const dst = destino(a[2]);
        if (t.r !== undefined) { const r2 = t.r; return () => (cmp(R[s], R[r2]) ? dst : undefined); }
        const k = t.k;
        return () => (cmp(R[s], k) ? dst : undefined);
      };
      const saltoCero = (cmp, enlazar) => {
        nargs(2);
        const s = reg(a[0]); const dst = destino(a[1]);
        if (enlazar) return () => { if (cmp(R[s])) { R[31] = retorno; return dst; } return undefined; };
        return () => (cmp(R[s]) ? dst : undefined);
      };
      const div0 = (b) => { if (b === 0) throw new ErrorMIPS('division entre cero'); return b; };
      const u = (x) => x >>> 0;

      switch (op) {
        // --- aritmetica y logica ---
        case 'add': return binaria((x, y) => desborda(x + y));
        case 'addu': return binaria((x, y) => (x + y) | 0);
        case 'sub': return binaria((x, y) => desborda(x - y));
        case 'subu': return binaria((x, y) => (x - y) | 0);
        case 'addi': return binaria((x, y) => desborda(x + y));
        case 'addiu': return binaria((x, y) => (x + y) | 0);
        case 'and': case 'andi': return binaria((x, y) => x & y);
        case 'or': case 'ori': return binaria((x, y) => x | y);
        case 'xor': case 'xori': return binaria((x, y) => x ^ y);
        case 'nor': return binaria((x, y) => ~(x | y));
        case 'slt': case 'slti': return binaria((x, y) => (x < y ? 1 : 0));
        case 'sltu': case 'sltiu': return binaria((x, y) => (u(x) < u(y) ? 1 : 0));
        case 'seq': return binaria((x, y) => (x === y ? 1 : 0));
        case 'sne': return binaria((x, y) => (x !== y ? 1 : 0));
        case 'sge': return binaria((x, y) => (x >= y ? 1 : 0));
        case 'sgt': return binaria((x, y) => (x > y ? 1 : 0));
        case 'sle': return binaria((x, y) => (x <= y ? 1 : 0));
        case 'sgeu': return binaria((x, y) => (u(x) >= u(y) ? 1 : 0));
        case 'sgtu': return binaria((x, y) => (u(x) > u(y) ? 1 : 0));
        case 'sleu': return binaria((x, y) => (u(x) <= u(y) ? 1 : 0));
        case 'sll': case 'sllv': return binaria((x, y) => x << (y & 31));
        case 'srl': case 'srlv': return binaria((x, y) => (x >>> (y & 31)) | 0);
        case 'sra': case 'srav': return binaria((x, y) => x >> (y & 31));
        case 'rol': return binaria((x, y) => ((x << (y & 31)) | (x >>> ((32 - (y & 31)) & 31))) | 0);
        case 'ror': return binaria((x, y) => ((x >>> (y & 31)) | (x << ((32 - (y & 31)) & 31))) | 0);
        case 'mul': return binaria((x, y) => { cpu.multiplicar(x, y, true); return cpu.lo; });
        case 'mulo': return binaria((x, y) => { const p = x * y; if (!Number.isSafeInteger(p) || p > 2147483647 || p < -2147483648) throw new ErrorMIPS('desbordamiento aritmetico'); return p; });
        case 'mult': case 'multu': {
          nargs(2);
          const s = reg(a[0]); const t = reg(a[1]); const con = op === 'mult';
          return () => { cpu.multiplicar(R[s], R[t], con); };
        }
        case 'madd': case 'maddu': case 'msub': case 'msubu': {
          nargs(2);
          const s = reg(a[0]); const t = reg(a[1]);
          const con = !op.endsWith('u'); const resta = op.startsWith('msub');
          return () => {
            const acc = (BigInt(cpu.hi) << 32n) | BigInt(cpu.lo >>> 0);
            const x = con ? BigInt(R[s]) : BigInt(R[s] >>> 0);
            const y = con ? BigInt(R[t]) : BigInt(R[t] >>> 0);
            const r = resta ? acc - x * y : acc + x * y;
            cpu.hi = Number(BigInt.asIntN(32, r >> 32n));
            cpu.lo = Number(BigInt.asIntN(32, r));
          };
        }
        case 'div': case 'divu': {
          const con = op === 'div';
          if (a.length === 2) {
            const s = reg(a[0]); const t = reg(a[1]);
            return () => {
              const x = R[s]; const y = R[t];
              if (y === 0) { cpu.aviso(`division entre cero en la linea ${ins.linea}: HI y LO no cambian (como MARS)`); return; }
              if (con) { cpu.lo = (x / y) | 0; cpu.hi = (x % y) | 0; } else { cpu.lo = (u(x) / u(y)) | 0; cpu.hi = (u(x) % u(y)) | 0; }
            };
          }
          return binaria(con ? (x, y) => (x / div0(y)) | 0 : (x, y) => (u(x) / u(div0(y))) | 0);
        }
        case 'rem': return binaria((x, y) => (x % div0(y)) | 0);
        case 'remu': return binaria((x, y) => (u(x) % u(div0(y))) | 0);
        case 'mfhi': { nargs(1); const d = regD(a[0]); return () => { R[d] = cpu.hi; }; }
        case 'mflo': { nargs(1); const d = regD(a[0]); return () => { R[d] = cpu.lo; }; }
        case 'mthi': { nargs(1); const s = reg(a[0]); return () => { cpu.hi = R[s]; }; }
        case 'mtlo': { nargs(1); const s = reg(a[0]); return () => { cpu.lo = R[s]; }; }
        case 'clz': { nargs(2); const d = regD(a[0]); const s = reg(a[1]); return () => { R[d] = Math.clz32(R[s]); }; }
        case 'clo': { nargs(2); const d = regD(a[0]); const s = reg(a[1]); return () => { R[d] = Math.clz32(~R[s]); }; }
        case 'movn': case 'movz': {
          nargs(3);
          const d = regD(a[0]); const s = reg(a[1]); const t = reg(a[2]); const n = op === 'movn';
          return () => { if ((R[t] !== 0) === n) R[d] = R[s]; };
        }

        // --- pseudoinstrucciones de un registro ---
        case 'move': { nargs(2); const d = regD(a[0]); const s = reg(a[1]); return () => { R[d] = R[s]; }; }
        case 'not': { nargs(2); const d = regD(a[0]); const s = reg(a[1]); return () => { R[d] = ~R[s]; }; }
        case 'neg': { nargs(2); const d = regD(a[0]); const s = reg(a[1]); return () => { R[d] = desborda(-R[s]); }; }
        case 'negu': { nargs(2); const d = regD(a[0]); const s = reg(a[1]); return () => { R[d] = (-R[s]) | 0; }; }
        case 'abs': { nargs(2); const d = regD(a[0]); const s = reg(a[1]); return () => { R[d] = R[s] < 0 ? (-R[s]) | 0 : R[s]; }; }
        case 'li': { nargs(2); const d = regD(a[0]); const k = imm(a[1]); return () => { R[d] = k; }; }
        case 'lui': { nargs(2); const d = regD(a[0]); const k = imm(a[1]); return () => { R[d] = k << 16; }; }
        case 'la': {
          nargs(2);
          const d = regD(a[0]);
          const f = memoria(a[1]);
          return () => { R[d] = f(); };
        }

        // --- memoria ---
        case 'lw': case 'lh': case 'lhu': case 'lb': case 'lbu': case 'll': {
          nargs(2);
          const d = regD(a[0]); const f = memoria(a[1]);
          const lee = op === 'll' ? 'lw' : op;
          return () => { R[d] = cpu[lee](f()); };
        }
        case 'sw': case 'sh': case 'sb': {
          nargs(2);
          const s = reg(a[0]); const f = memoria(a[1]);
          return () => { cpu[op](f(), R[s]); };
        }
        case 'sc': {
          nargs(2);
          const s = reg(a[0]); const f = memoria(a[1]); const d = s === 0 ? SUMIDERO : s;
          return () => { cpu.sw(f(), R[s]); R[d] = 1; };
        }

        // --- saltos ---
        case 'b': { nargs(1); const dst = destino(a[0]); return () => dst; }
        case 'j': { nargs(1); const dst = destino(a[0]); return () => dst; }
        case 'jal': case 'bal': { nargs(1); const dst = destino(a[0]); return () => { R[31] = retorno; return dst; }; }
        case 'jr': {
          nargs(1);
          const s = reg(a[0]);
          return () => cpu.indiceCodigo(R[s]);
        }
        case 'jalr': {
          nargs(1, 2);
          const d = a.length === 2 ? regD(a[0]) : 31;
          const s = reg(a[a.length - 1]);
          return () => { const dst = cpu.indiceCodigo(R[s]); R[d] = retorno; return dst; };
        }
        case 'beq': return salto((x, y) => x === y);
        case 'bne': return salto((x, y) => x !== y);
        case 'blt': return salto((x, y) => x < y);
        case 'ble': return salto((x, y) => x <= y);
        case 'bgt': return salto((x, y) => x > y);
        case 'bge': return salto((x, y) => x >= y);
        case 'bltu': return salto((x, y) => u(x) < u(y));
        case 'bleu': return salto((x, y) => u(x) <= u(y));
        case 'bgtu': return salto((x, y) => u(x) > u(y));
        case 'bgeu': return salto((x, y) => u(x) >= u(y));
        case 'beqz': return saltoCero((x) => x === 0);
        case 'bnez': return saltoCero((x) => x !== 0);
        case 'bgez': return saltoCero((x) => x >= 0);
        case 'bgtz': return saltoCero((x) => x > 0);
        case 'blez': return saltoCero((x) => x <= 0);
        case 'bltz': return saltoCero((x) => x < 0);
        case 'bgezal': return saltoCero((x) => x >= 0, true);
        case 'bltzal': return saltoCero((x) => x < 0, true);

        // --- sistema ---
        case 'syscall': nargs(0); return () => cpu.syscall(ins);
        case 'nop': nargs(0); return () => undefined;
        case 'break': return () => { throw new ErrorMIPS('se ejecuto la instruccion break'); };
        case 'teq': case 'tne': {
          nargs(2);
          const s = reg(a[0]); const t = fuente(a[1]); const igual = op === 'teq';
          return () => {
            const y = t.r !== undefined ? R[t.r] : t.k;
            if ((R[s] === y) === igual) throw new ErrorMIPS(`trap (${op})`);
          };
        }
        default: break;
      }
      const f = this.compilarFlotante(op, a, ins, nargs, reg, regD, freg, memoria, destino);
      if (f) return f;
      throw new ErrorMIPS(`instruccion desconocida '${op}'`);
    }

    compilarFlotante(op, a, ins, nargs, reg, regD, freg, memoria, destino) {
      const cpu = this;
      const R = this.R;
      const m = /^([a-z0-9]+)\.([sdw])(?:\.([sdw]))?$/.exec(op);
      const arit = { add: (x, y) => x + y, sub: (x, y) => x - y, mul: (x, y) => x * y, div: (x, y) => x / y };
      if (m && arit[m[1]] && !m[3] && m[2] !== 'w') {
        nargs(3);
        const d = m[2] === 'd';
        const r0 = freg(a[0], d); const r1 = freg(a[1], d); const r2 = freg(a[2], d);
        const f = arit[m[1]];
        if (d) return () => { cpu.setDbl(r0, f(cpu.dbl(r1), cpu.dbl(r2))); };
        return () => { cpu.setFlt(r0, f(cpu.flt(r1), cpu.flt(r2))); };
      }
      const unarias = { abs: Math.abs, neg: (x) => -x, mov: (x) => x, sqrt: Math.sqrt };
      if (m && unarias[m[1]] && !m[3] && m[2] !== 'w') {
        nargs(2);
        const d = m[2] === 'd';
        const r0 = freg(a[0], d); const r1 = freg(a[1], d); const f = unarias[m[1]];
        if (d) return () => { cpu.setDbl(r0, f(cpu.dbl(r1))); };
        return () => { cpu.setFlt(r0, f(cpu.flt(r1))); };
      }
      if (m && m[1] === 'cvt' && m[3]) {
        nargs(2);
        const a2 = m[2]; const de = m[3];
        const r0 = freg(a[0], a2 === 'd'); const r1 = freg(a[1], de === 'd');
        const leer = de === 'd' ? (r) => cpu.dbl(r) : de === 's' ? (r) => cpu.flt(r) : (r) => cpu.fw(r);
        const escribir = a2 === 'd' ? (r, v) => cpu.setDbl(r, v) : a2 === 's' ? (r, v) => cpu.setFlt(r, v) : (r, v) => cpu.setFw(r, aEntero(v, Math.trunc));
        return () => { escribir(r0, leer(r1)); };
      }
      const redondeos = { trunc: Math.trunc, round: (x) => { const r = Math.round(x); return (x % 1 === -0.5 || x % 1 === 0.5) && r % 2 ? r - 1 : r; }, floor: Math.floor, ceil: Math.ceil };
      if (m && redondeos[m[1]] && m[2] === 'w' && m[3]) {
        nargs(2);
        const d = m[3] === 'd';
        const r0 = freg(a[0]); const r1 = freg(a[1], d); const f = redondeos[m[1]];
        return () => { cpu.setFw(r0, aEntero(d ? cpu.dbl(r1) : cpu.flt(r1), f)); };
      }
      const mc = /^c\.(eq|lt|le)\.([sd])$/.exec(op);
      if (mc) {
        nargs(2, 3);
        const cc = a.length === 3 ? numero(a.shift()) : 0;
        if (cc === null || cc < 0 || cc > 7) throw new ErrorMIPS('codigo de condicion invalido');
        const d = mc[2] === 'd';
        const r1 = freg(a[0], d); const r2 = freg(a[1], d);
        const tipo = mc[1];
        const cmp = { eq: (x, y) => x === y, lt: (x, y) => x < y, le: (x, y) => x <= y }[tipo];
        if (d) return () => { cpu.cond[cc] = cmp(cpu.dbl(r1), cpu.dbl(r2)) ? 1 : 0; };
        return () => { cpu.cond[cc] = cmp(cpu.flt(r1), cpu.flt(r2)) ? 1 : 0; };
      }
      switch (op) {
        case 'bc1t': case 'bc1f': {
          nargs(1, 2);
          const cc = a.length === 2 ? numero(a[0]) : 0;
          const dst = destino(a[a.length - 1]); const v = op === 'bc1t' ? 1 : 0;
          return () => (cpu.cond[cc] === v ? dst : undefined);
        }
        case 'mtc1': { nargs(2); const s = reg(a[0]); const d = freg(a[1]); return () => { cpu.setFw(d, R[s]); }; }
        case 'mfc1': { nargs(2); const d = regD(a[0]); const s = freg(a[1]); return () => { R[d] = cpu.fw(s); }; }
        case 'mtc1.d': { nargs(2); const s = reg(a[0]); const d = freg(a[1], true); return () => { cpu.setFw(d, R[s]); cpu.setFw(d + 1, R[s + 1]); }; }
        case 'mfc1.d': { nargs(2); const d = regD(a[0]); const s = freg(a[1], true); return () => { R[d] = cpu.fw(s); R[d + 1] = cpu.fw(s + 1); }; }
        case 'lwc1': case 'l.s': { nargs(2); const d = freg(a[0]); const f = memoria(a[1]); return () => { cpu.setFw(d, cpu.lw(f())); }; }
        case 'swc1': case 's.s': { nargs(2); const s = freg(a[0]); const f = memoria(a[1]); return () => { cpu.sw(f(), cpu.fw(s)); }; }
        case 'ldc1': case 'l.d': {
          nargs(2);
          const d = freg(a[0], true); const f = memoria(a[1]);
          return () => { const dir = f(); if (dir & 7) throw new ErrorMIPS(`acceso desalineado a ${hex(dir)} (8 bytes)`); cpu.setFw(d, cpu.lw(dir)); cpu.setFw(d + 1, cpu.lw(dir + 4)); };
        }
        case 'sdc1': case 's.d': {
          nargs(2);
          const s = freg(a[0], true); const f = memoria(a[1]);
          return () => { const dir = f(); if (dir & 7) throw new ErrorMIPS(`acceso desalineado a ${hex(dir)} (8 bytes)`); cpu.sw(dir, cpu.fw(s)); cpu.sw(dir + 4, cpu.fw(s + 1)); };
        }
        case 'li.s': case 'li.d': {
          nargs(2);
          const d = freg(a[0], op === 'li.d'); const v = Number(a[1]);
          if (Number.isNaN(v)) throw new ErrorMIPS(`numero invalido: ${a[1]}`);
          if (op === 'li.d') return () => { cpu.setDbl(d, v); };
          return () => { cpu.setFlt(d, v); };
        }
        default: return null;
      }
    }

    multiplicar(x, y, conSigno) {
      if (!conSigno) { x >>>= 0; y >>>= 0; }
      const exacto = x * y;
      if (Number.isSafeInteger(exacto)) {
        this.lo = Math.imul(x, y);
        this.hi = Math.floor(exacto / 4294967296) | 0;
        return;
      }
      const p = BigInt(x) * BigInt(y);
      this.hi = Number(BigInt.asIntN(32, p >> 32n));
      this.lo = Number(BigInt.asIntN(32, p));
    }

    indiceCodigo(dir) {
      const i = ((dir >>> 0) - BASE_TEXTO) / 4;
      if (!Number.isInteger(i) || i < 0 || i > this.codigo.length) throw new ErrorMIPS(`salto a una direccion que no es codigo: ${hex(dir)}`);
      return i;
    }

    // --- llamadas al sistema -------------------------------------------

    aleatorio() { // xorshift32
      let x = this.semilla || 0x9e3779b9;
      x ^= x << 13; x ^= x >>> 17; x ^= x << 5;
      this.semilla = x >>> 0;
      return this.semilla;
    }

    pedir(tipo) {
      if (this.entrada === null) {
        this.esperando = tipo;
        return null;
      }
      const t = this.entrada;
      this.entrada = null;
      this.esperando = null;
      return t;
    }

    darEntrada(texto) { this.entrada = texto; }

    syscall(ins) {
      const R = this.R;
      const s = R[2];
      switch (s) {
        case 1: this.salida(String(R[4])); return undefined;
        case 2: this.salida(formatoJava(this.flt(12), true)); return undefined;
        case 3: this.salida(formatoJava(this.dbl(12), false)); return undefined;
        case 4: this.salida(this.cadena(R[4])); return undefined;
        case 5: {
          const t = this.pedir('int'); if (t === null) return PAUSA;
          const v = numero(t.trim());
          if (v === null || v > 2147483647 || v < -2147483648) throw new ErrorMIPS(`entrada invalida para un entero: "${t}"`);
          R[2] = v; return undefined;
        }
        case 6: case 7: {
          const t = this.pedir(s === 6 ? 'float' : 'double'); if (t === null) return PAUSA;
          const v = Number(t.trim());
          if (t.trim() === '' || Number.isNaN(v)) throw new ErrorMIPS(`entrada invalida para un numero: "${t}"`);
          if (s === 6) this.setFlt(0, v); else this.setDbl(0, v);
          return undefined;
        }
        case 8: {
          const t = this.pedir('string'); if (t === null) return PAUSA;
          const max = R[5];
          if (max < 1) return undefined;
          const bytes = Array.from(new TextEncoder().encode(t + '\n')).slice(0, max - 1);
          bytes.forEach((b, i) => this.sb(R[4] + i, b));
          this.sb(R[4] + bytes.length, 0);
          return undefined;
        }
        case 9: {
          const n = R[4];
          if (n < 0) throw new ErrorMIPS('sbrk con tamanio negativo');
          R[2] = this.sbrk;
          this.crecer(this.sbrk + n);
          this.sbrk = (this.sbrk + n + 3) & ~3;
          return undefined;
        }
        case 10: this.terminado = true; return undefined;
        case 11: this.salida(String.fromCharCode(R[4] & 0xff)); return undefined;
        case 12: {
          const t = this.pedir('char'); if (t === null) return PAUSA;
          R[2] = t.length ? t.charCodeAt(0) & 0xff : 10; return undefined;
        }
        case 17: this.codigoSalida = R[4]; this.terminado = true; return undefined;
        case 30: { const t = BigInt(Date.now()); R[4] = Number(BigInt.asIntN(32, t)); R[5] = Number(BigInt.asIntN(32, t >> 32n)); return undefined; }
        case 31: case 33: {
          const dur = Math.max(0, R[5]);
          this.midi(R[4] & 127, dur, R[6] & 127, R[7] & 127);
          if (s === 33) { this.durmiendo = dur; this.despertar = true; return PAUSA; }
          return undefined;
        }
        case 32: this.durmiendo = Math.max(0, R[4]); this.despertar = true; return PAUSA;
        case 34: this.salida(hex(R[4])); return undefined;
        case 35: this.salida((R[4] >>> 0).toString(2).padStart(32, '0')); return undefined;
        case 36: this.salida(String(R[4] >>> 0)); return undefined;
        case 40: this.semilla = R[5] >>> 0; return undefined;
        case 41: R[4] = this.aleatorio() | 0; return undefined;
        case 42: {
          const n = R[5];
          if (n <= 0) throw new ErrorMIPS('syscall 42: el limite superior debe ser positivo');
          R[4] = this.aleatorio() % n; return undefined;
        }
        default: throw new ErrorMIPS(`syscall no soportada: ${s}`);
      }
    }

    // --- ejecucion -----------------------------------------------------

    /*
     * Ejecuta hasta `maxPasos` instrucciones. Devuelve el estado:
     * 'fin', 'entrada', 'dormir', 'ruptura', 'limite'. Lanza ErrorMIPS con
     * la linea del error si la simulacion falla.
     */
    ejecutar(maxPasos, ignorarRupturaInicial = false) {
      const codigo = this.codigo;
      const total = codigo.length;
      const bp = this.puntosDeRuptura;
      const conBp = bp.size > 0;
      let pc = this.pc;
      let i = 0;
      try {
        if (this.despertar) { this.despertar = false; this.durmiendo = 0; pc++; }
        for (; i < maxPasos; i++) {
          if (this.terminado) break;
          if (pc >= total) { this.terminado = true; this.cayoAlFinal = true; break; }
          if (conBp && bp.has(pc) && !(i === 0 && ignorarRupturaInicial)) { this.pc = pc; this.pasos += i; return 'ruptura'; }
          const r = codigo[pc]();
          if (r === undefined) pc++;
          else if (r === PAUSA) {
            this.pc = pc; this.pasos += i;
            return this.esperando ? 'entrada' : 'dormir';
          } else pc = r;
        }
      } catch (e) {
        this.pc = pc;
        this.pasos += i;
        if (e instanceof ErrorMIPS) {
          const ins = this.programa.instrucciones[pc];
          if (ins) { e.linea = ins.linea; e.instruccion = ins.texto; }
          throw e;
        }
        throw e;
      }
      this.pc = pc;
      this.pasos += i;
      return this.terminado ? 'fin' : 'limite';
    }
  }

  function aEntero(v, f) {
    const r = f(v);
    if (!Number.isFinite(r) || r > 2147483647 || r < -2147483648) return 2147483647;
    return r | 0;
  }

  function potencia2(n) {
    let p = 1;
    while (p < n) p *= 2;
    return p;
  }

  // Ejecucion completa y sincrona (Node y pruebas): entradas por arreglo.
  function simular(fuente, opciones = {}) {
    const salida = [];
    const cpu = new CPU(ensamblar(fuente), { ...opciones, salida: (t) => salida.push(t), semilla: 1 });
    const entradas = [...(opciones.entradas || [])];
    const limite = opciones.maxInstrucciones || 200000000;
    for (;;) {
      const estado = cpu.ejecutar(limite - cpu.pasos);
      if (estado === 'entrada') {
        if (!entradas.length) throw new ErrorMIPS('el programa pide entrada y no hay mas');
        cpu.darEntrada(entradas.shift());
      } else if (estado === 'dormir') {
        continue;
      } else if (estado === 'limite') {
        throw new ErrorMIPS(`el programa no termino en ${limite} instrucciones`);
      } else {
        break;
      }
    }
    return { salida: salida.join(''), codigoSalida: cpu.codigoSalida, instrucciones: cpu.pasos };
  }

  const API = {
    ensamblar, CPU, simular, ErrorMIPS, formatoJava, hex, NOMBRES,
    BASE_TEXTO, BASE_DATOS, GP_INICIAL, SP_INICIAL,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  else raiz.MIPS = API;
})(typeof window !== 'undefined' ? window : globalThis);
