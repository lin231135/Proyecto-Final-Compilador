/* MIPSTATION 3000 — interfaz del IDE */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const MIPS = window.MIPS;
  const hex = MIPS.hex;

  const el = {
    pantalla: $('pantalla'), contenido: $('contenido'), arranque: $('arranque'), arranqueTexto: $('arranque-texto'),
    fuente: $('fuente'), resaltado: $('resaltado'), gutter: $('gutter'), barraActual: $('barra-actual'), barraError: $('barra-error'),
    consolaCaja: $('consola'), consola: $('consola-texto'), entrada: $('entrada'), entradaCampo: $('entrada-campo'), entradaPrompt: $('entrada-prompt'),
    regs: $('regs'), pila: $('pila'), fregs: $('fregs'), mem: $('mem'), memDir: $('mem-dir'),
    stEstado: $('st-estado'), stPc: $('st-pc'), stLinea: $('st-linea'), stInstr: $('st-instr'), stVel: $('st-vel'),
    desplegable: $('desplegable'), modal: $('modal'), modalTitulo: $('modal-titulo'), modalCuerpo: $('modal-cuerpo'), modalBotones: $('modal-botones'),
    archivo: $('archivo'), disquetera: $('disquetera'), disco: $('disco'), ledDisco: $('led-disco'), soltar: $('soltar'),
    ledPower: $('led-power'), ledRun: $('led-run'), ledErr: $('led-err'), nombreArchivo: $('nombre-archivo'), modificado: $('marca-modificado'),
    reloj: $('reloj'),
  };

  // ------------------------------------------------------------------
  // preferencias (solo comodidad: si el navegador no deja guardar, no pasa nada)
  // ------------------------------------------------------------------
  const guardado = {
    leer(clave, def) { try { const v = localStorage.getItem('mipstation.' + clave); return v === null ? def : JSON.parse(v); } catch (e) { return def; } },
    escribir(clave, v) { try { localStorage.setItem('mipstation.' + clave, JSON.stringify(v)); } catch (e) { /* sin almacenamiento */ } },
  };

  const VELOCIDADES = [
    { nombre: 'MÁX', ips: Infinity },
    { nombre: '1000/s', ips: 1000 },
    { nombre: '100/s', ips: 100 },
    { nombre: '20/s', ips: 20 },
    { nombre: '5/s', ips: 5 },
    { nombre: '1/s', ips: 1 },
  ];

  const st = {
    programa: null,
    cpu: null,
    fuenteEnsamblada: null,
    estado: 'vacio', // vacio | listo | corriendo | pausa | entrada | dormido | fin | error
    corriendo: false,
    vel: guardado.leer('vel', 0),
    hexa: guardado.leer('hexa', true),
    iniciarEnMain: guardado.leer('main', false),
    efectos: guardado.leer('efectos', true),
    fosforo: guardado.leer('fosforo', 'verde'),
    brillo: guardado.leer('brillo', 2),
    glow: guardado.leer('glow', 2),
    puntos: new Set(), // números de línea
    previos: new Int32Array(35),
    previosF: new Int32Array(32),
    lineaError: null,
    encendido: true,
    memBase: MIPS.BASE_DATOS,
    nombre: guardado.leer('nombre', 'programa.asm'),
    pestana: 'cpu',
  };

  // ------------------------------------------------------------------
  // consola
  // ------------------------------------------------------------------
  const MAX_CONSOLA = 200000;
  let pendiente = '';
  let programado = false;

  function escribir(texto, clase) {
    if (clase) {
      vaciarConsola();
      const s = document.createElement('span');
      s.className = clase;
      s.textContent = texto;
      el.consola.appendChild(s);
      recortarConsola();
      bajarConsola();
      return;
    }
    pendiente += texto;
    if (!programado) {
      programado = true;
      requestAnimationFrame(vaciarConsola);
    }
  }
  function vaciarConsola() {
    programado = false;
    if (!pendiente) return;
    const ultimo = el.consola.lastChild;
    if (ultimo && ultimo.nodeType === 3) ultimo.appendData(pendiente);
    else el.consola.appendChild(document.createTextNode(pendiente));
    pendiente = '';
    recortarConsola();
    bajarConsola();
  }
  function recortarConsola() {
    let exceso = el.consola.textContent.length - MAX_CONSOLA;
    while (exceso > 0 && el.consola.firstChild) {
      const n = el.consola.firstChild;
      const largo = n.textContent.length;
      if (n.nodeType === 3 && largo > exceso) { n.deleteData(0, exceso); break; }
      el.consola.removeChild(n);
      exceso -= largo;
    }
  }
  function bajarConsola() { el.consolaCaja.scrollTop = el.consolaCaja.scrollHeight; }
  function sistema(texto) {
    const t = el.consola.textContent;
    const salto = t.length && !t.endsWith('\n') && !pendiente.endsWith('\n') ? '\n' : '';
    escribir(salto + texto + '\n', 'sis');
  }
  function sistemaClase(texto, clase) {
    const t = el.consola.textContent + pendiente;
    if (t.length && !t.endsWith('\n')) escribir('\n');
    escribir(texto, clase);
    escribir('\n');
  }

  // ------------------------------------------------------------------
  // editor: resaltado, numeración, barras
  // ------------------------------------------------------------------
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const TOKEN = /("(?:\\.|[^"\\])*"?)|('(?:\\.|[^'\\])')|(\$[\w]+)|(\.[A-Za-z]\w*)|(-?\b(?:0x[0-9a-fA-F]+|\d+(?:\.\d+)?(?:e[+-]?\d+)?)\b)|([A-Za-z_][\w.$]*)/g;

  function indiceComentario(linea) {
    let q = null;
    for (let i = 0; i < linea.length; i++) {
      const c = linea[i];
      if (q) { if (c === '\\') i++; else if (c === q) q = null; }
      else if (c === '"' || c === "'") q = c;
      else if (c === '#') return i;
    }
    return -1;
  }

  function resaltarLinea(linea) {
    const k = indiceComentario(linea);
    const codigo = k >= 0 ? linea.slice(0, k) : linea;
    const com = k >= 0 ? '<span class="t-com">' + esc(linea.slice(k)) + '</span>' : '';
    let salida = '';
    let ultimo = 0;
    let primeraPalabra = true;
    TOKEN.lastIndex = 0;
    let m;
    while ((m = TOKEN.exec(codigo))) {
      salida += esc(codigo.slice(ultimo, m.index));
      const t = esc(m[0]);
      let clase;
      if (m[1] || m[2]) clase = 't-str';
      else if (m[3]) clase = 't-reg';
      else if (m[4]) clase = 't-dir';
      else if (m[5]) clase = 't-num';
      else {
        const sigue = codigo.slice(TOKEN.lastIndex).match(/^\s*:/);
        if (sigue) clase = 't-etq';
        else if (primeraPalabra) { clase = 't-op'; primeraPalabra = false; }
        else clase = '';
      }
      if (m[4]) primeraPalabra = false;
      salida += clase ? `<span class="${clase}">${t}</span>` : t;
      ultimo = TOKEN.lastIndex;
    }
    return salida + esc(codigo.slice(ultimo)) + com;
  }

  let lineasActuales = 0;
  let resaltadoProgramado = false;

  function actualizarEditor() {
    resaltadoProgramado = false;
    const texto = el.fuente.value;
    const lineas = texto.split('\n');
    el.resaltado.innerHTML = lineas.map(resaltarLinea).join('\n') + '\n';
    if (lineas.length !== lineasActuales) {
      lineasActuales = lineas.length;
      let h = '<div class="gutter-int" id="gutter-int">';
      for (let i = 1; i <= lineas.length; i++) h += `<div class="n" data-l="${i}">${i}</div>`;
      el.gutter.innerHTML = h + '<div style="height:40px"></div></div>';
      pintarMarcasGutter();
    }
    sincronizarScroll();
  }
  function programarResaltado() {
    if (!resaltadoProgramado) { resaltadoProgramado = true; requestAnimationFrame(actualizarEditor); }
  }

  function sincronizarScroll() {
    const y = el.fuente.scrollTop;
    const x = el.fuente.scrollLeft;
    el.resaltado.style.transform = `translate(${-x}px, ${-y}px)`;
    const g = $('gutter-int');
    if (g) g.style.transform = `translateY(${-y}px)`;
    posicionarBarra(el.barraActual, st.lineaBarra, y);
    posicionarBarra(el.barraError, st.lineaError, y);
  }
  function lh() { return parseFloat(getComputedStyle(el.fuente).lineHeight) || 22; }
  function posicionarBarra(barra, linea, y) {
    if (!linea) { barra.hidden = true; return; }
    barra.hidden = false;
    barra.style.transform = `translateY(${(linea - 1) * lh() - y}px)`;
  }

  function pintarMarcasGutter() {
    const nodos = el.gutter.querySelectorAll('.n');
    nodos.forEach((n) => {
      const l = +n.dataset.l;
      n.classList.toggle('bp', st.puntos.has(l));
      n.classList.toggle('actual', l === st.lineaBarra);
      n.classList.toggle('err', l === st.lineaError);
    });
  }

  function marcarLineaActual(linea, centrar) {
    st.lineaBarra = linea;
    pintarMarcasGutter();
    if (linea && centrar) {
      const alto = lh();
      const arriba = (linea - 1) * alto;
      const vista = el.fuente.clientHeight;
      if (arriba < el.fuente.scrollTop || arriba > el.fuente.scrollTop + vista - alto * 2) {
        el.fuente.scrollTop = Math.max(0, arriba - vista / 3);
      }
    }
    sincronizarScroll();
    el.stLinea.textContent = linea || '-';
  }

  function marcarError(linea) {
    st.lineaError = linea || null;
    el.ledErr.classList.toggle('on', !!linea);
    pintarMarcasGutter();
    if (linea) {
      const alto = lh();
      const arriba = (linea - 1) * alto;
      const vista = el.fuente.clientHeight;
      if (arriba < el.fuente.scrollTop || arriba > el.fuente.scrollTop + vista - alto * 2) el.fuente.scrollTop = Math.max(0, arriba - vista / 3);
    }
    sincronizarScroll();
  }

  el.fuente.addEventListener('scroll', sincronizarScroll);
  el.fuente.addEventListener('input', () => {
    programarResaltado();
    marcarModificado();
    guardarFuente();
  });
  el.fuente.addEventListener('keydown', (e) => {
    if (e.key === 'Tab' && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      const t = el.fuente;
      const ini = t.selectionStart;
      const fin = t.selectionEnd;
      if (ini === fin) {
        if (!document.execCommand('insertText', false, '    ')) t.setRangeText('    ', ini, fin, 'end');
      } else {
        // sangrar o quitar sangría a las líneas seleccionadas
        const v = t.value;
        const a = v.lastIndexOf('\n', ini - 1) + 1;
        const bloque = v.slice(a, fin);
        const nuevo = e.shiftKey ? bloque.replace(/^ {1,4}/gm, '') : bloque.replace(/^/gm, '    ');
        t.setSelectionRange(a, fin);
        if (!document.execCommand('insertText', false, nuevo)) t.setRangeText(nuevo, a, fin, 'select');
        t.setSelectionRange(a, a + nuevo.length);
      }
      programarResaltado();
      marcarModificado();
    }
  });

  el.gutter.addEventListener('click', (e) => {
    const n = e.target.closest('.n');
    if (!n) return;
    alternarPunto(+n.dataset.l);
  });

  function alternarPunto(linea) {
    if (st.puntos.has(linea)) st.puntos.delete(linea); else st.puntos.add(linea);
    pintarMarcasGutter();
    aplicarPuntos();
  }
  function aplicarPuntos() {
    if (!st.cpu) return;
    const ins = st.programa.instrucciones;
    const set = st.cpu.puntosDeRuptura;
    set.clear();
    for (const l of st.puntos) {
      const i = ins.findIndex((x) => x.linea >= l);
      if (i >= 0) set.add(i);
    }
  }

  let temporizadorGuardar = null;
  function guardarFuente() {
    clearTimeout(temporizadorGuardar);
    temporizadorGuardar = setTimeout(() => guardado.escribir('fuente', el.fuente.value), 400);
  }
  function marcarModificado() {
    const mod = st.fuenteEnsamblada !== null && el.fuente.value !== st.fuenteEnsamblada;
    el.modificado.textContent = mod ? '[MODIFICADO]' : '';
  }

  function ponerFuente(texto, nombre) {
    el.fuente.value = texto;
    el.fuente.scrollTop = 0;
    el.fuente.scrollLeft = 0;
    st.nombre = nombre || st.nombre;
    el.nombreArchivo.textContent = st.nombre;
    guardado.escribir('nombre', st.nombre);
    guardado.escribir('fuente', texto);
    st.puntos.clear();
    detener();
    st.cpu = null;
    st.programa = null;
    st.fuenteEnsamblada = null;
    st.lineaError = null;
    el.ledErr.classList.remove('on');
    ponerEstado('vacio');
    marcarLineaActual(null);
    actualizarEditor();
    marcarModificado();
    refrescarVistas(true);
  }

  // ------------------------------------------------------------------
  // registros, memoria, estado
  // ------------------------------------------------------------------
  const NOMBRES = MIPS.NOMBRES;
  const fmt = (v) => (st.hexa ? hex(v) : String(v | 0).padStart(10, ' '));

  function construirRegistros() {
    let h = '';
    // orden por columnas: 0-15 a la izquierda, 16-31 a la derecha
    for (let fila = 0; fila < 16; fila++) {
      for (const i of [fila, fila + 16]) {
        h += `<div class="reg" id="r${i}"><span><span class="num">${String(i).padStart(2, '0')}</span><span class="nom">$${NOMBRES[i].padEnd(4, ' ')}</span></span><span class="val"></span></div>`;
      }
    }
    h += '<div class="reg especial" id="r32"><span class="nom">pc</span><span class="val"></span></div>';
    h += '<div class="reg especial" id="r33"><span class="nom">hi</span><span class="val"></span></div>';
    h += '<div class="reg especial" id="r34"><span class="nom">lo</span><span class="val"></span></div>';
    el.regs.innerHTML = h;
    let f = '<div class="fila cab"><span>reg</span><span>float (simple)</span><span>double (par)</span></div>';
    for (let i = 0; i < 32; i += 2) {
      f += `<div class="fila" id="f${i}"><span class="nom">$f${i}</span><span class="fs"></span><span class="fd"></span></div>`;
      f += `<div class="fila" id="f${i + 1}"><span class="nom">$f${i + 1}</span><span class="fs"></span><span></span></div>`;
    }
    f += '<div class="fila"><span class="nom">cc</span><span id="fcc"></span><span></span></div>';
    el.fregs.innerHTML = f;
  }

  const corto = (x) => {
    if (Number.isNaN(x)) return 'NaN';
    if (!Number.isFinite(x)) return x > 0 ? 'Inf' : '-Inf';
    const s = String(+x.toPrecision(9));
    return s.length > 15 ? x.toExponential(6) : s;
  };

  function refrescarVistas(marcarCambios) {
    const cpu = st.cpu;
    const vals = new Int32Array(35);
    if (cpu) {
      vals.set(cpu.R.subarray(0, 32));
      vals[32] = MIPS.BASE_TEXTO + 4 * cpu.pc;
      vals[33] = cpu.hi;
      vals[34] = cpu.lo;
    } else {
      vals[28] = MIPS.GP_INICIAL;
      vals[29] = MIPS.SP_INICIAL;
      vals[32] = MIPS.BASE_TEXTO;
    }
    for (let i = 0; i < 35; i++) {
      const nodo = $('r' + i);
      nodo.lastChild.textContent = fmt(vals[i]);
      nodo.classList.toggle('cambio', !!(marcarCambios && cpu && i !== 32 && vals[i] !== st.previos[i]));
    }
    st.previos = vals;
    el.stPc.textContent = hex(vals[32]);
    el.stInstr.textContent = cpu ? cpu.pasos.toLocaleString('es') : '0';

    if (st.pestana === 'fpu') refrescarFPU(marcarCambios);
    if (st.pestana === 'mem') refrescarMemoria();
    if (st.pestana === 'cpu') refrescarPila();
  }

  function refrescarFPU(marcarCambios) {
    const cpu = st.cpu;
    for (let i = 0; i < 32; i++) {
      const fila = $('f' + i);
      const w = cpu ? cpu.fw(i) : 0;
      fila.children[1].textContent = st.hexa ? hex(w) : corto(cpu ? cpu.flt(i) : 0);
      if (i % 2 === 0) fila.children[2].textContent = corto(cpu ? cpu.dbl(i) : 0);
      fila.classList.toggle('cambio', !!(marcarCambios && cpu && w !== st.previosF[i]));
      st.previosF[i] = w;
    }
    $('fcc').textContent = cpu ? Array.from(cpu.cond).join(' ') : '0 0 0 0 0 0 0 0';
  }

  function refrescarPila() {
    const cpu = st.cpu;
    const sp = cpu ? cpu.R[29] : MIPS.SP_INICIAL;
    const fp = cpu ? cpu.R[30] : 0;
    let h = '';
    for (let k = 0; k < 9; k++) {
      const d = (sp + 4 * k) | 0;
      const v = cpu ? cpu.leerPalabraSegura(d) : 0;
      const marca = k === 0 ? '$sp►' : d === fp ? '$fp►' : '    ';
      h += `<div class="fila${k === 0 ? ' tope' : ''}"><span class="${d === fp ? 'fp' : ''}">${marca}</span><span class="dir">${hex(d).slice(2)}</span><span>${v === null ? '········' : st.hexa ? hex(v).slice(2) : String(v)}</span></div>`;
    }
    el.pila.innerHTML = h;
  }

  function refrescarMemoria() {
    const cpu = st.cpu;
    let h = '';
    for (let k = 0; k < 20; k++) {
      const d = (st.memBase + 4 * k) | 0;
      const v = cpu ? cpu.leerPalabraSegura(d) : null;
      let asc = '';
      if (v !== null) {
        for (let b = 0; b < 4; b++) {
          const c = (v >>> (8 * b)) & 0xff;
          asc += c >= 32 && c < 127 ? String.fromCharCode(c) : '·';
        }
      }
      const val = v === null ? '--------' : st.hexa ? hex(v).slice(2) : String(v).padStart(11, ' ');
      h += `<div class="fila"><span class="dir">${hex(d).slice(2)}</span><span>${val}</span><span class="asc">${esc(asc)}</span></div>`;
    }
    el.mem.innerHTML = h;
    el.memDir.value = hex(st.memBase);
  }

  const ETIQUETAS_ESTADO = {
    vacio: 'SIN ENSAMBLAR', listo: 'LISTO', corriendo: 'EJECUTANDO', pausa: 'EN PAUSA', entrada: 'ESPERANDO ENTRADA',
    dormido: 'DURMIENDO', fin: 'TERMINADO', error: 'ERROR',
  };
  function ponerEstado(e) {
    st.estado = e;
    el.stEstado.textContent = ETIQUETAS_ESTADO[e];
    el.stEstado.classList.toggle('corriendo', e === 'corriendo');
    el.ledRun.classList.toggle('on', e === 'corriendo' || e === 'dormido');
  }

  function ponerVelocidad(i) {
    st.vel = i;
    el.stVel.querySelector('b').textContent = VELOCIDADES[i].nombre;
    guardado.escribir('vel', i);
  }

  // ------------------------------------------------------------------
  // ensamblado y ejecución
  // ------------------------------------------------------------------
  let audio = null;
  function tocarNota(tono, ms, instrumento, volumen) {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === 'suspended') audio.resume();
      const t = audio.currentTime;
      const o = audio.createOscillator();
      const g = audio.createGain();
      const tipos = ['square', 'triangle', 'sawtooth', 'sine'];
      o.type = tipos[Math.floor(instrumento / 32) % 4];
      o.frequency.value = 440 * Math.pow(2, (tono - 69) / 12);
      const v = Math.max(0.0001, (volumen / 127) * 0.18);
      const dur = Math.max(0.03, Math.min(ms, 5000) / 1000);
      g.gain.setValueAtTime(v, t);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g).connect(audio.destination);
      o.start(t);
      o.stop(t + dur + 0.02);
    } catch (e) { /* sin audio */ }
  }
  function pitido(frec, ms) { tocarNota(69 + 12 * Math.log2(frec / 440), ms, 0, 60); }

  function ensamblar(silencioso) {
    detener();
    const fuente = el.fuente.value;
    marcarError(null);
    try {
      const programa = MIPS.ensamblar(fuente);
      const cpu = new MIPS.CPU(programa, {
        salida: (t) => escribir(t),
        aviso: (t) => sistema('aviso: ' + t),
        midi: tocarNota,
        iniciarEnMain: st.iniciarEnMain,
      });
      st.programa = programa;
      st.cpu = cpu;
      st.fuenteEnsamblada = fuente;
      aplicarPuntos();
      ponerEstado('listo');
      if (!silencioso) {
        sistema(`✔ ensamblado: ${programa.instrucciones.length} instrucciones, ${programa.datos.length} bytes de datos, ${programa.etiquetas.size} etiquetas`);
      }
      marcarLineaActual(cpu.lineaActual, true);
      st.previos.fill(0);
      refrescarVistas(false);
      marcarModificado();
      return true;
    } catch (e) {
      if (!(e instanceof MIPS.ErrorMIPS)) throw e;
      st.cpu = null;
      st.programa = null;
      st.fuenteEnsamblada = null;
      ponerEstado('error');
      sistemaClase(` ✖ ERROR DE ENSAMBLADO${e.linea ? ' (línea ' + e.linea + ')' : ''}: ${e.message} `, 'mal');
      marcarError(e.linea);
      marcarLineaActual(null);
      pitido(220, 180);
      refrescarVistas(false);
      return false;
    }
  }

  function necesitaEnsamblar() {
    return !st.cpu || st.fuenteEnsamblada !== el.fuente.value || st.estado === 'fin' || st.estado === 'error';
  }

  let ultimoRefresco = 0;
  let siguienteTick = null;
  let primeraVuelta = false;
  let acumulado = 0;
  let ultimoTiempo = 0;
  const canal = new MessageChannel();
  canal.port1.onmessage = () => vuelta();

  function programarVuelta() {
    if (VELOCIDADES[st.vel].ips === Infinity) canal.port2.postMessage(0);
    else siguienteTick = requestAnimationFrame(vuelta);
  }

  function ejecutar() {
    if (!st.encendido) return;
    if (st.estado === 'entrada') { el.entradaCampo.focus(); return; }
    if (st.corriendo) return;
    if (necesitaEnsamblar()) {
      const reensamblar = st.cpu && st.fuenteEnsamblada !== el.fuente.value && st.estado !== 'fin';
      if (!ensamblar(st.fuenteEnsamblada === el.fuente.value)) return;
      if (reensamblar) sistema('código modificado: se volvió a ensamblar desde el inicio');
    }
    primeraVuelta = st.estado === 'pausa';
    st.corriendo = true;
    ponerEstado('corriendo');
    acumulado = 0;
    ultimoTiempo = performance.now();
    if (VELOCIDADES[st.vel].ips === Infinity) marcarLineaActual(null);
    programarVuelta();
  }

  function vuelta() {
    if (!st.corriendo) return;
    const cpu = st.cpu;
    const vel = VELOCIDADES[st.vel].ips;
    let estado;
    try {
      if (vel === Infinity) {
        const t0 = performance.now();
        do {
          estado = cpu.ejecutar(250000, primeraVuelta);
          primeraVuelta = false;
        } while (estado === 'limite' && performance.now() - t0 < 16);
      } else {
        const ahora = performance.now();
        acumulado += ((ahora - ultimoTiempo) / 1000) * vel;
        ultimoTiempo = ahora;
        const n = Math.floor(acumulado);
        if (n < 1) { programarVuelta(); return; }
        acumulado -= n;
        estado = cpu.ejecutar(Math.min(n, 5000), primeraVuelta);
        primeraVuelta = false;
      }
    } catch (e) {
      if (!(e instanceof MIPS.ErrorMIPS)) throw e;
      errorEjecucion(e);
      return;
    }
    if (estado === 'limite') {
      const ahora = performance.now();
      if (vel !== Infinity) {
        refrescarVistas(true);
        marcarLineaActual(cpu.lineaActual, true);
      } else if (ahora - ultimoRefresco > 120) {
        ultimoRefresco = ahora;
        el.stInstr.textContent = cpu.pasos.toLocaleString('es');
      }
      programarVuelta();
      return;
    }
    tratarParada(estado);
  }

  function tratarParada(estado) {
    const cpu = st.cpu;
    st.corriendo = false;
    vaciarConsola();
    if (estado === 'fin') {
      ponerEstado('fin');
      const motivo = cpu.cayoAlFinal ? 'se salió del final del código' : `código de salida ${cpu.codigoSalida}`;
      sistema(`── programa terminado (${motivo}) · ${cpu.pasos.toLocaleString('es')} instrucciones ──`);
      marcarLineaActual(null);
    } else if (estado === 'entrada') {
      ponerEstado('entrada');
      const tipos = { int: 'entero', float: 'float', double: 'double', string: 'texto', char: 'carácter' };
      el.entradaPrompt.textContent = `${tipos[cpu.esperando]}?>`;
      el.entrada.hidden = false;
      el.entradaCampo.value = '';
      el.entradaCampo.focus();
      bajarConsola();
      marcarLineaActual(cpu.lineaActual, false);
    } else if (estado === 'dormir') {
      ponerEstado('dormido');
      st.corriendo = true;
      siguienteTick = setTimeout(() => {
        if (!st.corriendo) return;
        ponerEstado('corriendo');
        programarVuelta();
      }, Math.min(cpu.durmiendo, 10000));
      refrescarVistas(true);
      return;
    } else if (estado === 'ruptura') {
      ponerEstado('pausa');
      sistema(`● punto de ruptura en la línea ${cpu.lineaActual}`);
      marcarLineaActual(cpu.lineaActual, true);
    }
    refrescarVistas(true);
  }

  function errorEjecucion(e) {
    st.corriendo = false;
    vaciarConsola();
    ponerEstado('error');
    sistemaClase(` ✖ ERROR EN TIEMPO DE EJECUCIÓN (línea ${e.linea}): ${e.message} `, 'mal');
    if (e.instruccion) sistema(`  instrucción: ${e.instruccion}`);
    marcarLineaActual(null);
    marcarError(e.linea);
    refrescarVistas(true);
    pitido(160, 260);
  }

  function detener() {
    st.corriendo = false;
    if (siguienteTick !== null) { cancelAnimationFrame(siguienteTick); clearTimeout(siguienteTick); siguienteTick = null; }
    el.entrada.hidden = true;
  }

  function pausa() {
    if (!st.corriendo) return;
    detener();
    ponerEstado('pausa');
    vaciarConsola();
    marcarLineaActual(st.cpu.lineaActual, true);
    refrescarVistas(true);
    sistema(`‖ pausa en la línea ${st.cpu.lineaActual} · ${st.cpu.pasos.toLocaleString('es')} instrucciones`);
  }

  function paso() {
    if (!st.encendido) return;
    if (st.corriendo) { pausa(); return; }
    if (st.estado === 'entrada') { el.entradaCampo.focus(); return; }
    if (necesitaEnsamblar()) {
      if (!ensamblar(false)) return;
      return; // el primer F7 deja el programa listo en la primera instrucción
    }
    let estado;
    try {
      estado = st.cpu.ejecutar(1, true);
    } catch (e) {
      if (!(e instanceof MIPS.ErrorMIPS)) throw e;
      errorEjecucion(e);
      return;
    }
    vaciarConsola();
    if (estado === 'limite') {
      ponerEstado('pausa');
      marcarLineaActual(st.cpu.lineaActual, true);
      refrescarVistas(true);
    } else if (estado === 'dormir') {
      st.cpu.despertar = true;
      ponerEstado('pausa');
      marcarLineaActual(st.cpu.lineaActual, true);
      refrescarVistas(true);
    } else {
      tratarParada(estado);
    }
  }

  function reiniciar() {
    if (!st.encendido) return;
    const habia = st.cpu !== null;
    if (ensamblar(true)) sistema(habia ? '── reinicio: programa cargado de nuevo ──' : '✔ ensamblado');
  }

  el.entradaCampo.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const texto = el.entradaCampo.value;
    el.entrada.hidden = true;
    vaciarConsola();
    escribir(texto + '\n', 'eco');
    st.cpu.darEntrada(texto);
    st.corriendo = true;
    primeraVuelta = true;
    ponerEstado('corriendo');
    ultimoTiempo = performance.now();
    programarVuelta();
    el.fuente.focus({ preventScroll: true });
  });

  // ------------------------------------------------------------------
  // archivos
  // ------------------------------------------------------------------
  function abrir() { el.archivo.value = ''; el.archivo.click(); }
  el.archivo.addEventListener('change', () => { if (el.archivo.files[0]) cargarArchivo(el.archivo.files[0]); });

  function cargarArchivo(archivo) {
    if (archivo.size > 4 * 1024 * 1024) { sistemaClase(' ✖ el archivo pesa más de 4 MB ', 'mal'); return; }
    el.disco.classList.remove('entra');
    void el.disco.offsetWidth;
    el.disco.classList.add('entra');
    el.ledDisco.classList.add('on');
    const lector = new FileReader();
    lector.onload = () => {
      setTimeout(() => {
        el.ledDisco.classList.remove('on');
        ponerFuente(String(lector.result), archivo.name);
        sistema(`A:\\> CARGADO ${archivo.name.toUpperCase()} (${archivo.size.toLocaleString('es')} bytes)`);
        el.fuente.focus();
      }, 700);
    };
    lector.onerror = () => { el.ledDisco.classList.remove('on'); sistemaClase(' ✖ no se pudo leer el archivo ', 'mal'); };
    lector.readAsText(archivo);
  }

  function guardar() {
    const blob = new Blob([el.fuente.value.replace(/\r?\n/g, '\n')], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = /\.(asm|s|mips)$/i.test(st.nombre) ? st.nombre : st.nombre + '.asm';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    el.ledDisco.classList.add('on');
    setTimeout(() => el.ledDisco.classList.remove('on'), 600);
    sistema(`A:\\> GUARDADO ${a.download.toUpperCase()}`);
  }

  async function pegar() {
    try {
      const t = await navigator.clipboard.readText();
      if (!t) { sistema('el portapapeles está vacío'); return; }
      ponerFuente(t, 'pegado.asm');
      sistema('código pegado desde el portapapeles');
    } catch (e) {
      sistema('el navegador no permite leer el portapapeles aquí: usa Ctrl+V dentro del editor');
      el.fuente.focus();
    }
  }

  let arrastres = 0;
  const conArchivo = (e) => e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files');
  window.addEventListener('dragenter', (e) => {
    if (!conArchivo(e)) return;
    arrastres++;
    el.soltar.hidden = false;
    el.disquetera.classList.add('sobre');
  });
  window.addEventListener('dragleave', () => {
    arrastres = Math.max(0, arrastres - 1);
    if (!arrastres) { el.soltar.hidden = true; el.disquetera.classList.remove('sobre'); }
  });
  window.addEventListener('dragover', (e) => { if (conArchivo(e)) e.preventDefault(); });
  window.addEventListener('drop', (e) => {
    if (!conArchivo(e)) return;
    e.preventDefault();
    arrastres = 0;
    el.soltar.hidden = true;
    el.disquetera.classList.remove('sobre');
    const f = e.dataTransfer.files[0];
    if (f) cargarArchivo(f);
  });
  el.disquetera.addEventListener('click', (e) => { if (!e.target.closest('#btn-expulsar')) abrir(); });
  $('btn-expulsar').addEventListener('click', guardar);

  // ------------------------------------------------------------------
  // menús y diálogos
  // ------------------------------------------------------------------
  function listaEjemplos() {
    return [...(window.EJEMPLOS || []), ...(window.EJEMPLOS_COMPISCRIPT || [])];
  }

  const MENUS = {
    archivo: () => [
      ['Nuevo', 'nuevo', ''],
      ['Abrir .asm…', 'abrir', 'Ctrl+O'],
      ['Guardar .asm', 'guardar', 'Ctrl+S'],
      ['Pegar del portapapeles', 'pegar', ''],
      '─',
      [st.encendido ? 'Apagar el equipo' : 'Encender el equipo', 'power', ''],
    ],
    ejemplos: () => [
      ...(window.EJEMPLOS || []).map((x, i) => [x.nombre, 'ej:' + i, '']),
      ...((window.EJEMPLOS_COMPISCRIPT || []).length ? ['── generados por el compilador ──'] : []),
      ...(window.EJEMPLOS_COMPISCRIPT || []).map((x, i) => [x.nombre, 'ej:' + ((window.EJEMPLOS || []).length + i), '']),
      '─',
      ['Ver todos con descripción…', 'catalogo', ''],
    ],
    ejecutar: () => [
      ['Ensamblar', 'ensamblar', 'F3'],
      ['Ejecutar / continuar', 'ejecutar', 'F5'],
      ['Paso a paso', 'paso', 'F7'],
      ['Pausa', 'pausa', 'F8'],
      ['Reiniciar', 'reiniciar', 'F9'],
      '─',
      ['Quitar todos los puntos de ruptura', 'sinpuntos', ''],
      ['Cambiar velocidad (' + VELOCIDADES[st.vel].nombre + ')', 'velocidad', ''],
      [(st.iniciarEnMain ? '√ ' : '  ') + 'Empezar en main (si no, al inicio de .text)', 'main', ''],
    ],
    ver: () => [
      [(st.fosforo === 'verde' ? '√ ' : '  ') + 'Fósforo verde', 'f:verde', ''],
      [(st.fosforo === 'ambar' ? '√ ' : '  ') + 'Fósforo ámbar', 'f:ambar', ''],
      [(st.fosforo === 'blanco' ? '√ ' : '  ') + 'Fósforo blanco', 'f:blanco', ''],
      '─',
      [(st.efectos ? '√ ' : '  ') + 'Efectos de tubo (líneas, barrido)', 'efectos', ''],
      [(st.hexa ? '√ ' : '  ') + 'Registros en hexadecimal', 'hexa', ''],
      ['Limpiar la consola', 'limpiar', ''],
    ],
    ayuda: () => [
      ['Cómo se usa', 'ayuda', 'F1'],
      ['Instrucciones y syscalls', 'referencia', ''],
      ['Acerca de MIPSTATION 3000', 'acerca', ''],
    ],
  };

  let menuAbierto = null;
  function abrirMenu(nombre, boton) {
    cerrarMenu();
    menuAbierto = nombre;
    boton.classList.add('abierto');
    const items = MENUS[nombre]();
    el.desplegable.innerHTML = items.map((it) => {
      if (typeof it === 'string') return `<div class="sep">${it === '─' ? '─'.repeat(30) : esc(it)}</div>`;
      return `<button data-accion="${it[1]}">${esc(it[0])}<kbd>${it[2]}</kbd></button>`;
    }).join('');
    const r = boton.getBoundingClientRect();
    const p = el.pantalla.getBoundingClientRect();
    el.desplegable.hidden = false;
    el.desplegable.style.left = Math.min(r.left - p.left, p.width - el.desplegable.offsetWidth - 20) + 'px';
    el.desplegable.style.top = (r.bottom - p.top) + 'px';
    const primero = el.desplegable.querySelector('button');
    if (primero) primero.focus();
  }
  function cerrarMenu() {
    menuAbierto = null;
    el.desplegable.hidden = true;
    document.querySelectorAll('.menu-btn.abierto').forEach((b) => b.classList.remove('abierto'));
  }
  document.querySelectorAll('.menu-btn').forEach((b) => {
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      if (menuAbierto === b.dataset.menu) cerrarMenu(); else abrirMenu(b.dataset.menu, b);
    });
    b.addEventListener('mouseenter', () => { if (menuAbierto && menuAbierto !== b.dataset.menu) abrirMenu(b.dataset.menu, b); });
  });
  el.desplegable.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    cerrarMenu();
    accion(b.dataset.accion);
  });
  el.desplegable.addEventListener('keydown', (e) => {
    const botones = [...el.desplegable.querySelectorAll('button')];
    const i = botones.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); botones[(i + 1) % botones.length].focus(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); botones[(i - 1 + botones.length) % botones.length].focus(); }
  });
  document.addEventListener('click', (e) => { if (menuAbierto && !e.target.closest('#desplegable')) cerrarMenu(); });

  let alCerrarModal = null;
  function modal(titulo, html, botones = [['CERRAR', null]]) {
    el.modalTitulo.textContent = titulo;
    el.modalCuerpo.innerHTML = html;
    el.modalBotones.innerHTML = '';
    botones.forEach(([texto, fn], i) => {
      const b = document.createElement('button');
      b.textContent = `[ ${texto} ]`;
      b.addEventListener('click', () => { cerrarModal(); if (fn) fn(); });
      el.modalBotones.appendChild(b);
      if (i === botones.length - 1) setTimeout(() => b.focus(), 0);
    });
    el.modal.hidden = false;
  }
  function cerrarModal() {
    el.modal.hidden = true;
    if (alCerrarModal) { const f = alCerrarModal; alCerrarModal = null; f(); }
  }
  el.modal.addEventListener('click', (e) => { if (e.target === el.modal) cerrarModal(); });
  el.modalCuerpo.addEventListener('click', (e) => {
    const b = e.target.closest('.ejemplo');
    if (!b) return;
    cerrarModal();
    cargarEjemplo(+b.dataset.i);
  });

  function cargarEjemplo(i) {
    const ej = listaEjemplos()[i];
    if (!ej) return;
    ponerFuente(ej.codigo, ej.archivo || 'ejemplo.asm');
    sistema(`ejemplo cargado: ${ej.nombre} · F5 para ejecutarlo`);
    el.fuente.focus({ preventScroll: true });
  }

  function textoAyuda() {
    return `<h3>1. PONER EL CÓDIGO</h3>Pega tu MIPS32 en el EDITOR (Ctrl+V), ábrelo con <kbd>Ctrl+O</kbd>, o
arrastra un .asm a la pantalla o a la disquetera. Para usar el compilador:
<span class="tenue">  python main.py programa.cps -o programa.asm</span>

<h3>2. EJECUTAR</h3><kbd>F3</kbd> ensambla y muestra los errores con su línea.
<kbd>F5</kbd> (o <kbd>Ctrl+Enter</kbd>) ejecuta o continúa.
<kbd>F7</kbd> avanza una instrucción: la barra marca la siguiente línea que se va a ejecutar
y los registros que cambiaron se ven en video inverso.
<kbd>F8</kbd> pausa y <kbd>F9</kbd> reinicia.

<h3>3. DEPURAR</h3>Clic en un número de línea pone un punto de ruptura (●).
La velocidad (abajo a la derecha, o Ejecutar ▸ velocidad) permite ver el programa
correr línea por línea, de 1 a 1000 instrucciones por segundo.
Las pestañas FPU y MEMORIA muestran los registros flotantes y la memoria.
Clic en HEX cambia entre hexadecimal y decimal.

<h3>4. ENTRADA</h3>Si el programa lee con las syscalls 5, 6, 7, 8 o 12, la consola pide el dato.
Escríbelo y presiona Enter.

<span class="tenue">Funciona como MARS 4.5 con sus opciones por defecto: sin delay slots,
el programa empieza en la primera instrucción de .text, $sp = 0x7fffeffc,
$gp = 0x10008000 y .data empieza en 0x10010000.</span>`;
  }

  function textoReferencia() {
    return `<h3>ENTEROS</h3>add addu addi addiu sub subu mul mult multu div divu rem remu mfhi mflo
mthi mtlo madd maddu msub msubu and andi or ori xor xori nor not neg negu abs
sll srl sra sllv srlv srav rol ror slt slti sltu sltiu seq sne sge sgt sle
sgeu sgtu sleu clz clo movn movz li la lui move
<h3>MEMORIA</h3>lw lh lhu lb lbu sw sh sb   operandos: k($r) ($r) etiqueta etiqueta+k etiqueta($r)
<h3>SALTOS</h3>j jal jr jalr b beq bne blt ble bgt bge bltu bleu bgtu bgeu beqz bnez
bgez bgtz blez bltz bgezal bltzal  (el 2.º operando puede ser un inmediato)
<h3>PUNTO FLOTANTE</h3>add sub mul div abs neg mov sqrt .s/.d  ·  cvt.d.w cvt.w.d cvt.s.d cvt.d.s
cvt.s.w cvt.w.s  ·  trunc/round/floor/ceil.w.s/.d  ·  c.eq c.lt c.le .s/.d
bc1t bc1f mtc1 mfc1 l.s s.s l.d s.d lwc1 swc1 ldc1 sdc1 li.s li.d
<h3>DIRECTIVAS</h3>.data .text .globl .align .space .ascii .asciiz .byte .half .word .float
.double .eqv   (valor:n repite n veces, .word acepta etiquetas)
<h3>SYSCALLS ($v0)</h3> 1 imprimir entero      2 imprimir float      3 imprimir double
 4 imprimir cadena      5 leer entero         6 leer float
 7 leer double          8 leer cadena         9 sbrk (memoria dinámica)
10 salir               11 imprimir carácter   12 leer carácter
17 salir con código    30 hora               31 nota MIDI   32 dormir (ms)
33 nota MIDI y espera  34 imprimir hex       35 imprimir binario
36 imprimir sin signo  40 semilla            41 entero aleatorio
42 aleatorio en [0, $a1)`;
  }

  function catalogo() {
    const h = listaEjemplos().map((x, i) => `<button class="ejemplo" data-i="${i}"><b>${esc(x.nombre)}</b>\n<span>  ${esc(x.descripcion || '')}</span></button>`).join('');
    modal('EJEMPLOS', h || 'No hay ejemplos cargados.');
  }

  function aplicarFosforo(f) {
    st.fosforo = f;
    el.pantalla.dataset.fosforo = f;
    guardado.escribir('fosforo', f);
  }
  function aplicarEfectos() {
    el.pantalla.classList.toggle('sin-efectos', !st.efectos);
    guardado.escribir('efectos', st.efectos);
  }
  const BRILLOS = [0.75, 0.88, 1, 1.12];
  const GLOWS = [0, 0.5, 1, 1.6];
  function aplicarPerillas() {
    el.pantalla.style.setProperty('--brillo', BRILLOS[st.brillo]);
    el.pantalla.style.setProperty('--glow', GLOWS[st.glow]);
    $('perilla-brillo').style.transform = `rotate(${-90 + st.brillo * 60}deg)`;
    $('perilla-contraste').style.transform = `rotate(${-90 + st.glow * 60}deg)`;
    guardado.escribir('brillo', st.brillo);
    guardado.escribir('glow', st.glow);
  }
  function girar(perilla, delta) {
    if (perilla === 'brillo') st.brillo = (st.brillo + delta + 4) % 4;
    else st.glow = (st.glow + delta + 4) % 4;
    aplicarPerillas();
  }
  $('perilla-brillo').addEventListener('click', () => girar('brillo', 1));
  $('perilla-contraste').addEventListener('click', () => girar('glow', 1));
  $('perilla-brillo').addEventListener('wheel', (e) => { e.preventDefault(); girar('brillo', e.deltaY < 0 ? 1 : -1); }, { passive: false });
  $('perilla-contraste').addEventListener('wheel', (e) => { e.preventDefault(); girar('glow', e.deltaY < 0 ? 1 : -1); }, { passive: false });

  function limpiarConsola() {
    pendiente = '';
    el.consola.textContent = '';
  }

  function accion(a) {
    if (a.startsWith('ej:')) { cargarEjemplo(+a.slice(3)); return; }
    if (a.startsWith('f:')) { aplicarFosforo(a.slice(2)); return; }
    switch (a) {
      case 'nuevo':
        modal('NUEVO', '¿Borrar el código del editor?\n<span class="tenue">Si no lo guardaste, se pierde.</span>', [
          ['CANCELAR', null],
          ['BORRAR', () => { ponerFuente('    .data\n\n    .text\nmain:\n    \n    li $v0, 10\n    syscall\n', 'programa.asm'); el.fuente.focus(); }],
        ]);
        break;
      case 'abrir': abrir(); break;
      case 'guardar': guardar(); break;
      case 'pegar': pegar(); break;
      case 'power': power(); break;
      case 'catalogo': catalogo(); break;
      case 'ensamblar': if (st.encendido) ensamblar(false); break;
      case 'ejecutar': ejecutar(); break;
      case 'paso': paso(); break;
      case 'pausa': pausa(); break;
      case 'reiniciar': reiniciar(); break;
      case 'sinpuntos': st.puntos.clear(); pintarMarcasGutter(); aplicarPuntos(); break;
      case 'velocidad': ponerVelocidad((st.vel + 1) % VELOCIDADES.length); break;
      case 'main':
        st.iniciarEnMain = !st.iniciarEnMain;
        guardado.escribir('main', st.iniciarEnMain);
        sistema(st.iniciarEnMain ? 'el programa empezará en la etiqueta main' : 'el programa empezará en la primera instrucción de .text (como MARS)');
        st.cpu = null;
        ponerEstado('vacio');
        break;
      case 'efectos': st.efectos = !st.efectos; aplicarEfectos(); break;
      case 'hexa': cambiarBase(); break;
      case 'limpiar': limpiarConsola(); break;
      case 'ayuda': modal('CÓMO SE USA', textoAyuda()); break;
      case 'referencia': modal('INSTRUCCIONES Y SYSCALLS', textoReferencia()); break;
      case 'acerca':
        modal('ACERCA DE', `<span class="t-etq">MIPSTATION 3000</span>  ·  simulador de MIPS32 en el navegador
Proyecto de Construcción de Compiladores · UVG 2026

Ensamblador de dos pasadas y CPU escritos en JavaScript (mips.js).
No necesita Java ni instalar nada: abre index.html en el navegador.

Verificado contra el simulador interno del compilador:
<span class="tenue">  python simulador_retro/verificar.py</span>

Para la entrega, valida también en MARS o SPIM.`);
        break;
      default: break;
    }
  }

  function cambiarBase() {
    st.hexa = !st.hexa;
    $('base-btn').textContent = st.hexa ? 'HEX' : 'DEC';
    guardado.escribir('hexa', st.hexa);
    refrescarVistas(false);
  }

  document.querySelectorAll('[data-accion]').forEach((b) => {
    if (b.closest('#desplegable')) return;
    b.addEventListener('click', () => accion(b.dataset.accion));
  });
  $('limpiar-consola').addEventListener('click', limpiarConsola);
  el.stVel.addEventListener('click', () => ponerVelocidad((st.vel + 1) % VELOCIDADES.length));
  $('base-btn').addEventListener('click', cambiarBase);

  document.querySelectorAll('.pestana[data-tab]').forEach((b) => {
    b.addEventListener('click', () => {
      st.pestana = b.dataset.tab;
      document.querySelectorAll('.pestana[data-tab]').forEach((x) => x.classList.toggle('activa', x === b));
      ['cpu', 'fpu', 'mem'].forEach((t) => { $('tab-' + t).hidden = t !== st.pestana; });
      refrescarVistas(false);
    });
  });

  document.querySelectorAll('[data-ir]').forEach((b) => {
    b.addEventListener('click', () => {
      const cpu = st.cpu;
      const destinos = {
        datos: MIPS.BASE_DATOS,
        gp: cpu ? cpu.R[28] : MIPS.GP_INICIAL,
        sp: cpu ? cpu.R[29] : MIPS.SP_INICIAL,
        heap: cpu ? cpu.finEstatico : MIPS.BASE_DATOS,
      };
      st.memBase = destinos[b.dataset.ir] & ~3;
      refrescarMemoria();
    });
  });
  document.querySelectorAll('[data-mover]').forEach((b) => {
    b.addEventListener('click', () => { st.memBase = (st.memBase + 4 * +b.dataset.mover) | 0; refrescarMemoria(); });
  });
  el.memDir.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    const v = el.memDir.value.trim();
    const n = /^0x/i.test(v) ? parseInt(v, 16) : parseInt(v, 10);
    if (!Number.isNaN(n)) { st.memBase = n & ~3; refrescarMemoria(); }
  });

  // ------------------------------------------------------------------
  // teclado
  // ------------------------------------------------------------------
  document.addEventListener('keydown', (e) => {
    if (!el.arranque.hidden) { terminarArranque(); e.preventDefault(); return; }
    if (e.key === 'Escape') {
      if (!el.modal.hidden) { cerrarModal(); return; }
      if (menuAbierto) { cerrarMenu(); el.fuente.focus(); return; }
      if (st.corriendo) { pausa(); return; }
    }
    if (!el.modal.hidden) return;
    const teclas = { F1: 'ayuda', F3: 'ensamblar', F5: 'ejecutar', F7: 'paso', F8: 'pausa', F9: 'reiniciar' };
    if (teclas[e.key]) { e.preventDefault(); accion(teclas[e.key]); return; }
    if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); accion('ejecutar'); return; }
    if (e.ctrlKey && (e.key === 's' || e.key === 'S')) { e.preventDefault(); guardar(); return; }
    if (e.ctrlKey && (e.key === 'o' || e.key === 'O')) { e.preventDefault(); abrir(); return; }
    if (e.altKey && !e.ctrlKey) {
      const atajos = { a: 'archivo', e: 'ejemplos', j: 'ejecutar', v: 'ver', u: 'ayuda' };
      const m = atajos[e.key.toLowerCase()];
      if (m) { e.preventDefault(); abrirMenu(m, document.querySelector(`.menu-btn[data-menu="${m}"]`)); }
    }
  });

  // ------------------------------------------------------------------
  // encendido y arranque
  // ------------------------------------------------------------------
  const LOGO = String.raw`
  __  __ ___ ___  ___ _____ _ _____ ___ ___  _  _   ____  ___   ___   ___
 |  \/  |_ _| _ \/ __|_   _/_\_   _|_ _/ _ \| \| | |__ / / _ \ / _ \ / _ \
 | |\/| || ||  _/\__ \ | |/ _ \| |  | | (_) | .  |  |_ \| (_) | (_) | (_) |
 |_|  |_|___|_|  |___/ |_/_/ \_\_| |___\___/|_|\_| |___/ \___/ \___/ \___/
`;
  let temporizadoresArranque = [];
  let enArranque = false;

  function arrancar() {
    enArranque = true;
    el.arranque.hidden = false;
    el.contenido.style.visibility = 'hidden';
    el.arranqueTexto.innerHTML = '';
    const reducido = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const lineas = [
      [0, `<span class="logo-ascii">${esc(LOGO)}</span>`],
      [250, 'MIPSTATION 3000  BIOS v3.2   (c) 2026 UVG · Construcción de Compiladores\n\n'],
      [500, 'CPU  ............ MIPS32 R2000 @ 33 MHz        [ OK ]\n'],
      [700, 'FPU  ............ R2010 coprocesador 1          [ OK ]\n'],
      [900, 'MEMORIA ......... <span id="cuenta-mem">0</span> KB'],
      [1700, '                   [ OK ]\n'],
      [1850, 'PILA ........... 8192 KB en 0x7FFFEFFC          [ OK ]\n'],
      [2050, 'UNIDAD A: ...... 3½" 1.44 MB                    [ OK ]\n\n'],
      [2300, 'Cargando ENSAMBLADOR.EXE '],
      [2350, '<span id="barra-carga"></span>'],
      [3100, '\n\nPresiona cualquier tecla para continuar<span class="cursor">█</span>'],
    ];
    if (reducido) { terminarArranque(); return; }
    pitido(988, 120);
    for (const [t, html] of lineas) {
      temporizadoresArranque.push(setTimeout(() => { el.arranqueTexto.insertAdjacentHTML('beforeend', html); }, t));
    }
    const cuenta = setInterval(() => {
      const c = $('cuenta-mem');
      if (!c) return;
      const v = Math.min(4096, +c.textContent + 256);
      c.textContent = v;
      if (v >= 4096) clearInterval(cuenta);
    }, 45);
    temporizadoresArranque.push(cuenta);
    const barra = setInterval(() => {
      const b = $('barra-carga');
      if (!b) return;
      if (b.textContent.length >= 20) { clearInterval(barra); return; }
      b.textContent += '█';
    }, 32);
    temporizadoresArranque.push(barra);
    temporizadoresArranque.push(setTimeout(terminarArranque, 4200));
  }

  function terminarArranque() {
    if (!enArranque) return;
    enArranque = false;
    temporizadoresArranque.forEach((t) => { clearTimeout(t); clearInterval(t); });
    temporizadoresArranque = [];
    el.arranque.hidden = true;
    el.contenido.style.visibility = '';
    el.pantalla.classList.add('encendiendo');
    setTimeout(() => el.pantalla.classList.remove('encendiendo'), 500);
    actualizarEditor();
    el.fuente.focus({ preventScroll: true });
  }
  el.arranque.addEventListener('click', terminarArranque);

  function power() {
    st.encendido = !st.encendido;
    el.ledPower.classList.toggle('on', st.encendido);
    if (!st.encendido) {
      detener();
      if (st.estado === 'corriendo' || st.estado === 'dormido') ponerEstado('pausa');
      cerrarMenu();
      el.modal.hidden = true;
      el.pantalla.classList.add('apagada');
      el.ledRun.classList.remove('on');
      return;
    }
    el.pantalla.classList.remove('apagada');
    arrancar();
  }
  $('btn-power').addEventListener('click', power);

  function reloj() {
    const d = new Date();
    el.reloj.textContent = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  }

  // ------------------------------------------------------------------
  // inicio
  // ------------------------------------------------------------------
  construirRegistros();
  aplicarFosforo(st.fosforo);
  aplicarEfectos();
  aplicarPerillas();
  ponerVelocidad(st.vel);
  $('base-btn').textContent = st.hexa ? 'HEX' : 'DEC';
  el.ledPower.classList.add('on');
  reloj();
  setInterval(reloj, 15000);
  el.nombreArchivo.textContent = st.nombre;

  const inicial = guardado.leer('fuente', null);
  if (inicial !== null && inicial.trim() !== '') {
    el.fuente.value = inicial;
  } else {
    const bienvenida = listaEjemplos()[0];
    el.fuente.value = bienvenida ? bienvenida.codigo : '';
    st.nombre = bienvenida ? bienvenida.archivo : 'programa.asm';
    el.nombreArchivo.textContent = st.nombre;
  }
  actualizarEditor();
  refrescarVistas(false);
  ponerEstado('vacio');
  sistema('MIPSTATION 3000 lista. F5 ejecuta · F7 paso a paso · F1 ayuda · menú EJEMPLOS para empezar');
  window.addEventListener('resize', sincronizarScroll);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(sincronizarScroll);
  arrancar();
})();
