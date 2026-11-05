"""
IDE de Compiscript (CustomTkinter + Tk) con estilo oscuro tipo Visual Studio Code.

Escribir/abrir un .cps, compilarlo y ver el codigo intermedio (TAC), el
ensamblador (MIPS32 o AArch64), la asignacion de registros, los problemas, la
tabla de simbolos extendida (direcciones, registros de activacion), la salida
del programa, el arbol sintactico y la bateria de pruebas. Los paneles se
alimentan de `driver.Resultado`; la compilacion NO se reimplementa aqui.

Atajos: F5 compilar, F6 ejecutar el TAC, F7 correr la bateria, F8 ejecutar el
ensamblador, Ctrl+S guardar, Ctrl+O abrir, Ctrl+/ comentar, Ctrl+rueda o
Ctrl +/- para el zoom.
"""

from __future__ import annotations

import bisect
import io
import pathlib
import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
from PIL import Image, ImageTk

from arbol.ast_graphviz import dot_disponible, render_png, render_texto
from backend import BackendError, Ensamblado, generar_ensamblador
from codegen.interpreter import ejecutar
from codegen.report import render_codegen_report
from driver import Resultado, analizar
from pruebas.runner import ERRORES_DE_EJECUCION, ejecutar_bateria
from simulador.ejecucion import ejecutar_codigo, medios_disponibles

ctk.set_appearance_mode("dark")

MAX_NODOS_ARBOL = 400
ZOOM_PASO = 1.25
RAIZ_PRUEBAS = pathlib.Path(__file__).resolve().parent.parent / "pruebas"

# --- Paleta (Dark+) -----------------------------------------------------
BG = "#1e1e1e"
BG_LATERAL = "#252526"
BG_BARRA = "#333333"
BG_TAB = "#2d2d2d"
BORDE = "#3c3c3c"
TEXTO = "#d4d4d4"
TEXTO_TENUE = "#858585"
SELECCION = "#264f78"
LINEA_ACTUAL = "#2a2d2e"
LINEA_ERROR = "#4b1818"
AZUL = "#007acc"
ROJO = "#c5392b"
VERDE = "#2ea043"

COLORES_SINTAXIS = {
    "kw_ctrl": "#c586c0",
    "kw": "#569cd6",
    "tipo": "#4ec9b0",
    "const": "#569cd6",
    "clase": "#4ec9b0",
    "funcion": "#dcdcaa",
    "numero": "#b5cea8",
    "cadena": "#ce9178",
    "comentario": "#6a9955",
    "etiqueta": "#d7ba7d",
    "temp": "#9cdcfe",
    "global": "#4fc1ff",
    "up": "#4fc1ff",
}

CTRL = {"if", "else", "while", "do", "for", "foreach", "switch", "case", "default", "break",
        "continue", "return", "try", "catch"}
KW = {"let", "var", "const", "function", "class", "new", "this", "print", "in"}
TIPOS = {"boolean", "integer", "float", "string"}
CONSTANTES = {"true", "false", "null"}

TAC_CTRL = {"goto", "if", "ifFalse", "return"}
TAC_KW = {"func", "endfunc", "param", "call", "callv", "callc", "new", "newlist", "len", "closure",
          "itof", "try", "endtry", "catch"}

# Opciones del selector de procesador: texto -> nombre en backend/.
PROCESADORES = {"MIPS32": "mips", "ARM64 (Raspberry Pi 4)": "arm64"}

RE_FUENTE = re.compile(
    r'(?P<comentario>//[^\n]*|/\*.*?\*/)'
    r'|(?P<cadena>"(?:[^"\\\n]|\\.)*"?)'
    r'|(?P<numero>\b\d+(?:\.\d+)?\b)'
    r'|(?P<palabra>[A-Za-z_]\w*)',
    re.S,
)
RE_TAC = re.compile(
    r'(?P<etiqueta>^[ \t]*L\d+:)'
    r'|(?P<cadena>"(?:[^"\\\n]|\\.)*"?)'
    r'|(?P<up>\bup\d+\.\w+)'
    r'|(?P<global>@\w+)'
    r'|(?P<temp>\bt\d+\b)'
    r'|(?P<numero>-?\b\d+(?:\.\d+)?\b)'
    r'|(?P<defunc>(?<=func )[\w.]+)'
    r'|(?P<palabra>[A-Za-z_]\w*)',
    re.M,
)

RE_ASM = re.compile(
    r'(?P<comentario>(?:#|//)[^\n]*)'
    r'|(?P<cadena>"(?:[^"\\\n]|\\.)*")'
    r'|(?P<etiqueta>^[\w.]+:)'
    r'|(?P<directiva>^\s*\.\w+|(?<=: )\.\w+)'
    r'|(?P<registro>\$\w+|\b[xwd]\d+\b|\b(?:sp|xzr|wzr)\b)'
    r'|(?P<numero>#?-?\b\d+(?:\.\d+)?\b)'
    r'|(?P<instruccion>^\s+[a-z][a-z0-9.]*)',
    re.M,
)

EJEMPLO = '''// Compiscript: F5 compila, F6 ejecuta el TAC y F8 ejecuta el ensamblador
class Animal {
  let nombre: string;
  function constructor(nombre: string) { this.nombre = nombre; }
  function hablar(): string { return this.nombre + " hace ruido"; }
}

class Perro : Animal {
  function hablar(): string { return this.nombre + " ladra"; }
}

function fib(n: integer): integer {
  if (n <= 1) { return n; }
  return fib(n - 1) + fib(n - 2);
}

let mascota: Animal = new Perro("Rex");
print(mascota.hablar());

for (let i: integer = 0; i < 8; i = i + 1) {
  print(fib(i));
}
'''


class CompiscriptIDE(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Compiscript IDE")
        self._centrar_ventana(1440, 900)
        self.minsize(1100, 640)
        self.configure(fg_color=BG)

        self.ruta_actual: pathlib.Path | None = None
        self.modificado = False
        self.resultado: Resultado | None = None
        self.ensamblado: Ensamblado | None = None
        self.lineas_error: set[int] = set()
        self._imagen_arbol_pil: Image.Image | None = None
        self._imagen_arbol_tk: ImageTk.PhotoImage | None = None
        self._zoom_arbol: float = 1.0
        self._job_resaltado: str | None = None
        self._rutas_explorador: dict[str, pathlib.Path] = {}

        self._crear_fuentes()
        self._crear_estilos()
        self._construir_barra_herramientas()
        self._construir_barra_estado()
        self._construir_cuerpo()
        self._atar_atajos()

        self.editor.insert("1.0", EJEMPLO)
        self.editor.edit_reset()
        self.editor.edit_modified(False)
        self._despues_de_editar()
        self._actualizar_titulo()

    def _centrar_ventana(self, ancho: int, alto: int) -> None:
        """Tamano en pixeles reales (sin el escalado de CTk), limitado a la pantalla."""
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(ancho, int(sw * 0.94)), min(alto, int(sh * 0.86))
        tk.Tk.geometry(self, f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2 - 24)}")

    # ------------------------------------------------------------------
    # Fuentes y estilos
    # ------------------------------------------------------------------

    def _crear_fuentes(self) -> None:
        disponibles = set(tkfont.families())
        mono = next((f for f in ("Cascadia Code", "Consolas", "Courier New") if f in disponibles), "Courier")
        ui = "Segoe UI" if "Segoe UI" in disponibles else "Helvetica"
        self.f_editor = tkfont.Font(family=mono, size=15)
        self.f_panel = tkfont.Font(family=mono, size=13)
        self.f_ui = tkfont.Font(family=ui, size=12)
        self.f_ui_b = tkfont.Font(family=ui, size=12, weight="bold")
        self.f_tenue = tkfont.Font(family=ui, size=10)
        self.f_logo = tkfont.Font(family=ui, size=13, weight="bold")

    def _crear_estilos(self) -> None:
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure("TFrame", background=BG)
        s.configure("Treeview", background=BG, fieldbackground=BG, foreground=TEXTO, borderwidth=0,
                    font=self.f_ui, rowheight=30, bordercolor=BG, lightcolor=BG, darkcolor=BG)
        s.map("Treeview", background=[("selected", "#094771")], foreground=[("selected", "#ffffff")])
        s.configure("Treeview.Heading", background=BG_LATERAL, foreground=TEXTO_TENUE, relief="flat",
                    font=self.f_tenue, padding=(8, 6))
        s.map("Treeview.Heading", background=[("active", BG_LATERAL)])

        s.configure("Lateral.Treeview", background=BG_LATERAL, fieldbackground=BG_LATERAL, rowheight=26,
                    bordercolor=BG_LATERAL, lightcolor=BG_LATERAL, darkcolor=BG_LATERAL)
        s.map("Lateral.Treeview", background=[("selected", "#37373d")])

        s.configure("TNotebook", background=BG_LATERAL, borderwidth=0, tabmargins=(8, 4, 0, 0),
                    bordercolor=BG, lightcolor=BG, darkcolor=BG)
        s.configure("TNotebook.Tab", background=BG_LATERAL, foreground=TEXTO_TENUE, padding=(18, 10),
                    font=self.f_tenue, borderwidth=0, bordercolor=BG_LATERAL, lightcolor=BG_LATERAL,
                    darkcolor=BG_LATERAL)
        s.map("TNotebook.Tab", background=[("selected", BG), ("active", BG_TAB)],
              foreground=[("selected", "#ffffff"), ("active", TEXTO)],
              bordercolor=[("selected", BG)], lightcolor=[("selected", AZUL), ("active", BG_TAB)],
              darkcolor=[("selected", BG)])

        for orient, nombre in (("Vertical", "Vertical.TScrollbar"), ("Horizontal", "Horizontal.TScrollbar")):
            s.layout(nombre, [(f"{orient}.Scrollbar.trough", {"children": [
                (f"{orient}.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})], "sticky": "nswe"})])
            s.configure(nombre, background="#424242", troughcolor=BG, bordercolor=BG, lightcolor="#424242",
                        darkcolor="#424242", gripcount=0, width=13)
            s.map(nombre, background=[("active", "#686868"), ("pressed", "#7a7a7a")])

    # ------------------------------------------------------------------
    # Construccion de la UI
    # ------------------------------------------------------------------

    def _boton(self, padre, texto, comando, bg=BG_BARRA, fg=TEXTO, hover="#4a4a4a", negrita=False):
        etiqueta = tk.Label(padre, text=texto, bg=bg, fg=fg, padx=14, pady=7, cursor="hand2",
                            font=self.f_ui_b if negrita else self.f_ui)
        etiqueta.bind("<Button-1>", lambda _e: comando())
        etiqueta.bind("<Enter>", lambda _e: etiqueta.configure(bg=hover))
        etiqueta.bind("<Leave>", lambda _e: etiqueta.configure(bg=bg))
        return etiqueta

    def _construir_barra_herramientas(self) -> None:
        barra = tk.Frame(self, bg=BG_BARRA, height=46)
        barra.pack(side="top", fill="x")
        barra.pack_propagate(False)

        tk.Label(barra, text="  { }  Compiscript", bg=BG_BARRA, fg="#4fc1ff", font=self.f_logo).pack(
            side="left", padx=(6, 18))

        self._boton(barra, "Abrir", self.abrir_archivo).pack(side="left", pady=5)
        self._boton(barra, "Guardar", self.guardar_archivo).pack(side="left", pady=5)
        tk.Frame(barra, bg=BORDE, width=1).pack(side="left", fill="y", pady=10, padx=10)
        self._boton(barra, "▶  Compilar  F5", self.compilar, bg=VERDE, fg="#ffffff", hover="#3fb950",
                    negrita=True).pack(side="left", pady=7)
        tk.Frame(barra, bg=BG_BARRA, width=6).pack(side="left")
        self._boton(barra, "⚙  Ejecutar TAC  F6", self.ejecutar_tac, bg=AZUL, fg="#ffffff",
                    hover="#1a8ad4", negrita=True).pack(side="left", pady=7)
        tk.Frame(barra, bg=BG_BARRA, width=6).pack(side="left")
        self._boton(barra, "⚡  Ejecutar asm  F8", self.ejecutar_ensamblador, bg=AZUL, fg="#ffffff",
                    hover="#1a8ad4", negrita=True).pack(side="left", pady=7)
        tk.Frame(barra, bg=BG_BARRA, width=6).pack(side="left")
        self._boton(barra, "✔  Batería  F7", self.correr_bateria).pack(side="left", pady=5)

        self._boton(barra, "A+", lambda: self._zoom_editor(1)).pack(side="right", pady=5, padx=(0, 8))
        self._boton(barra, "A-", lambda: self._zoom_editor(-1)).pack(side="right", pady=5)

    def _construir_barra_estado(self) -> None:
        self.barra_estado = tk.Frame(self, bg=AZUL, height=28)
        self.barra_estado.pack(side="bottom", fill="x")
        self.barra_estado.pack_propagate(False)

        self.lbl_estado = tk.Label(self.barra_estado, text="  Listo", bg=AZUL, fg="#ffffff", font=self.f_ui_b,
                                   anchor="w")
        self.lbl_estado.pack(side="left", fill="y", padx=(4, 0))

        self.lbl_posicion = tk.Label(self.barra_estado, text="Ln 1, Col 1", bg=AZUL, fg="#ffffff", font=self.f_ui)
        self.lbl_zoom = tk.Label(self.barra_estado, text="", bg=AZUL, fg="#ffffff", font=self.f_ui)
        for lbl in (tk.Label(self.barra_estado, text="Compiscript   ", bg=AZUL, fg="#ffffff", font=self.f_ui),
                    tk.Label(self.barra_estado, text="UTF-8   ", bg=AZUL, fg="#ffffff", font=self.f_ui),
                    self.lbl_zoom, self.lbl_posicion):
            lbl.pack(side="right", fill="y", padx=6)
        self._actualizar_zoom_label()

    def _construir_cuerpo(self) -> None:
        horizontal = tk.PanedWindow(self, orient="horizontal", bg=BORDE, bd=0, sashwidth=4, sashrelief="flat")
        horizontal.pack(side="top", fill="both", expand=True)

        horizontal.add(self._construir_explorador(horizontal), minsize=190, width=270)

        vertical = tk.PanedWindow(horizontal, orient="vertical", bg=BORDE, bd=0, sashwidth=4, sashrelief="flat")
        horizontal.add(vertical, minsize=420)
        vertical.add(self._construir_editor(vertical), minsize=220, height=520)
        vertical.add(self._construir_panel(vertical), minsize=150)

    # --- explorador ------------------------------------------------------

    def _construir_explorador(self, padre) -> tk.Frame:
        marco = tk.Frame(padre, bg=BG_LATERAL)
        tk.Label(marco, text="EXPLORADOR", bg=BG_LATERAL, fg=TEXTO_TENUE, font=self.f_tenue, anchor="w",
                 padx=16, pady=10).pack(fill="x")
        tk.Label(marco, text="Casos de prueba (doble clic para abrir)", bg=BG_LATERAL, fg=TEXTO_TENUE,
                 font=self.f_tenue, anchor="w", padx=16).pack(fill="x", pady=(0, 6))

        contenedor = tk.Frame(marco, bg=BG_LATERAL)
        contenedor.pack(fill="both", expand=True)
        self.explorador = ttk.Treeview(contenedor, show="tree", style="Lateral.Treeview", selectmode="browse")
        barra = ttk.Scrollbar(contenedor, orient="vertical", command=self.explorador.yview)
        self.explorador.configure(yscrollcommand=barra.set)
        self.explorador.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.explorador.tag_configure("valido", foreground="#89d185")
        self.explorador.tag_configure("invalido", foreground="#f48771")
        self.explorador.tag_configure("carpeta", foreground="#cccccc")
        self.explorador.bind("<Double-1>", self._on_abrir_desde_explorador)
        self.explorador.bind("<Return>", self._on_abrir_desde_explorador)
        self._poblar_explorador()
        return marco

    def _poblar_explorador(self) -> None:
        self.explorador.delete(*self.explorador.get_children())
        self._rutas_explorador.clear()
        if not RAIZ_PRUEBAS.exists():
            return
        categorias = [d for d in sorted(RAIZ_PRUEBAS.iterdir()) if d.is_dir() and not d.name.startswith("__")]
        categorias.sort(key=lambda d: (d.name != "demo", d.name))
        for cat in categorias:
            nodo_cat = self.explorador.insert("", "end", text=f"▸ {cat.name}", tags=("carpeta",),
                                              open=(cat.name == "demo"))
            archivos = sorted(cat.glob("*.cps")) + [a for sub in sorted(cat.iterdir()) if sub.is_dir()
                                                    for a in sorted(sub.glob("*.cps"))]
            for archivo in archivos:
                es_invalido = archivo.parent.name == "invalidos"
                etiqueta = archivo.name if archivo.parent == cat else f"{archivo.parent.name[:3]}/{archivo.name}"
                iid = self.explorador.insert(nodo_cat, "end", text=f"   {etiqueta}",
                                             tags=("invalido" if es_invalido else "valido",))
                self._rutas_explorador[iid] = archivo

    def _on_abrir_desde_explorador(self, _evento=None) -> None:
        seleccion = self.explorador.selection()
        if seleccion and seleccion[0] in self._rutas_explorador:
            self.cargar_archivo(self._rutas_explorador[seleccion[0]])

    # --- editor -----------------------------------------------------------

    def _construir_editor(self, padre) -> tk.Frame:
        marco = tk.Frame(padre, bg=BG)

        tabs = tk.Frame(marco, bg=BG_LATERAL, height=40)
        tabs.pack(fill="x")
        tabs.pack_propagate(False)
        self.lbl_tab = tk.Label(tabs, text="", bg=BG, fg="#ffffff", font=self.f_ui, padx=18, anchor="w")
        self.lbl_tab.pack(side="left", fill="y")

        cuerpo = tk.Frame(marco, bg=BG)
        cuerpo.pack(fill="both", expand=True)

        self.gutter = tk.Canvas(cuerpo, bg=BG, width=64, highlightthickness=0, bd=0)
        self.gutter.pack(side="left", fill="y")

        self.scroll_y = ttk.Scrollbar(cuerpo, orient="vertical")
        self.scroll_y.pack(side="right", fill="y")
        self.scroll_x = ttk.Scrollbar(marco, orient="horizontal")
        self.scroll_x.pack(side="bottom", fill="x")

        self.editor = tk.Text(
            cuerpo, wrap="none", undo=True, maxundo=-1, bg=BG, fg=TEXTO, font=self.f_editor,
            insertbackground="#aeafad", insertwidth=2, selectbackground=SELECCION,
            inactiveselectbackground="#3a3d41", relief="flat", bd=0, padx=10, pady=8,
            spacing1=3, spacing3=3, highlightthickness=0, tabs=("1c",),
        )
        self.editor.pack(side="left", fill="both", expand=True)
        self.editor.configure(yscrollcommand=self._on_yscroll, xscrollcommand=self.scroll_x.set)
        self.scroll_y.configure(command=self.editor.yview)
        self.scroll_x.configure(command=self.editor.xview)

        self._configurar_tags(self.editor)
        self.editor.tag_configure("linea_actual", background=LINEA_ACTUAL)
        self.editor.tag_configure("linea_error", background=LINEA_ERROR)
        self.editor.tag_lower("linea_actual")
        self.editor.tag_lower("linea_error")
        self.editor.tag_raise("sel")

        self.editor.bind("<KeyRelease>", lambda _e: self._despues_de_editar())
        self.editor.bind("<ButtonRelease-1>", lambda _e: self._actualizar_cursor())
        self.editor.bind("<<Modified>>", self._on_modificado)
        self.editor.bind("<Return>", self._on_return)
        self.editor.bind("<Tab>", self._on_tab)
        self.editor.bind("<Control-slash>", self._on_comentar)
        self.editor.bind("<Control-MouseWheel>", self._on_ctrl_rueda)
        self.editor.bind("<Configure>", lambda _e: self._dibujar_gutter())
        return marco

    def _configurar_tags(self, widget: tk.Text) -> None:
        for nombre, color in COLORES_SINTAXIS.items():
            widget.tag_configure(nombre, foreground=color)
        widget.tag_configure("comentario", foreground=COLORES_SINTAXIS["comentario"], font=self._cursiva(widget))

    def _cursiva(self, widget: tk.Text):
        f = tkfont.Font(font=widget.cget("font"))
        f.configure(slant="italic")
        self._fuentes_extra = getattr(self, "_fuentes_extra", []) + [f]
        return f

    # --- panel inferior ---------------------------------------------------

    def _texto_con_scroll(self, padre, fuente=None) -> tk.Text:
        contenedor = tk.Frame(padre, bg=BG)
        contenedor.pack(fill="both", expand=True)
        texto = tk.Text(contenedor, wrap="none", bg=BG, fg=TEXTO, font=fuente or self.f_panel, relief="flat", bd=0,
                        padx=14, pady=10, spacing1=2, spacing3=2, highlightthickness=0,
                        insertbackground=TEXTO, selectbackground=SELECCION, state="disabled")
        sy = ttk.Scrollbar(contenedor, orient="vertical", command=texto.yview)
        sx = ttk.Scrollbar(contenedor, orient="horizontal", command=texto.xview)
        texto.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.pack(side="right", fill="y")
        sx.pack(side="bottom", fill="x")
        texto.pack(side="left", fill="both", expand=True)
        self._configurar_tags(texto)
        texto.tag_configure("titulo", foreground="#4fc1ff", font=self._negrita_panel())
        texto.tag_configure("env", foreground="#dcdcaa")
        texto.tag_configure("ok", foreground="#89d185")
        texto.tag_configure("fallo", foreground="#f48771")
        texto.tag_configure("tenue", foreground=TEXTO_TENUE)
        return texto

    def _negrita_panel(self):
        f = tkfont.Font(font=self.f_panel)
        f.configure(weight="bold")
        self._fuentes_extra = getattr(self, "_fuentes_extra", []) + [f]
        return f

    def _construir_panel(self, padre) -> tk.Frame:
        marco = tk.Frame(padre, bg=BG)
        self.tabs = ttk.Notebook(marco)
        self.tabs.pack(fill="both", expand=True)

        self.pestanas: dict[str, tk.Frame] = {}
        for clave, titulo in (("tac", "CÓDIGO INTERMEDIO (TAC)"), ("asm", "ENSAMBLADOR"),
                              ("registros", "REGISTROS"), ("problemas", "PROBLEMAS"),
                              ("simbolos", "TABLA DE SÍMBOLOS"), ("salida", "SALIDA"),
                              ("arbol", "ÁRBOL SINTÁCTICO"), ("bateria", "BATERÍA")):
            frame = tk.Frame(self.tabs, bg=BG)
            self.tabs.add(frame, text=titulo)
            self.pestanas[clave] = frame

        self.texto_tac = self._texto_con_scroll(self.pestanas["tac"])
        self._escribir(self.texto_tac, "Presione F5 para compilar el programa y ver el código intermedio.", "tenue")

        self._construir_barra_ensamblador()
        self.texto_asm = self._texto_con_scroll(self.pestanas["asm"])
        self._escribir(self.texto_asm, "Presione F5 para compilar y generar el ensamblador.", "tenue")
        self.texto_registros = self._texto_con_scroll(self.pestanas["registros"])

        self._construir_problemas()
        self.texto_tabla = self._texto_con_scroll(self.pestanas["simbolos"])
        self.texto_salida = self._texto_con_scroll(self.pestanas["salida"])
        self._construir_arbol()
        self.texto_bateria = self._texto_con_scroll(self.pestanas["bateria"])
        return marco

    def _construir_barra_ensamblador(self) -> None:
        """Procesador destino y donde ejecutar: arriba de la pestana ENSAMBLADOR."""
        barra = tk.Frame(self.pestanas["asm"], bg=BG_LATERAL)
        barra.pack(side="top", fill="x")
        tk.Label(barra, text="Procesador", bg=BG_LATERAL, fg=TEXTO_TENUE, font=self.f_ui).pack(side="left", padx=(10, 6))
        self.menu_procesador = ctk.CTkOptionMenu(
            barra, values=list(PROCESADORES), width=200, height=26, fg_color=BG_TAB, button_color=BORDE,
            command=lambda _v: self._cambiar_procesador(),
        )
        self.menu_procesador.pack(side="left", pady=4)
        tk.Label(barra, text="Ejecutar en", bg=BG_LATERAL, fg=TEXTO_TENUE, font=self.f_ui).pack(side="left", padx=(14, 6))
        self.menu_medio = ctk.CTkOptionMenu(
            barra, values=["interno"], width=100, height=26, fg_color=BG_TAB, button_color=BORDE,
        )
        self.menu_medio.pack(side="left", pady=4)
        self._boton(barra, "Guardar ensamblador", self.guardar_ensamblador, bg=BG_LATERAL).pack(side="right", padx=6)
        self._cambiar_procesador(recompilar=False)

    def _construir_problemas(self) -> None:
        contenedor = tk.Frame(self.pestanas["problemas"], bg=BG)
        contenedor.pack(fill="both", expand=True)
        columnas = ("linea", "columna", "categoria", "mensaje")
        self.tabla_errores = ttk.Treeview(contenedor, columns=columnas, show="headings", selectmode="browse")
        for col, texto, ancho, ancla in (("linea", "LÍNEA", 80, "center"), ("columna", "COL", 70, "center"),
                                         ("categoria", "TIPO", 140, "center"), ("mensaje", "MENSAJE", 800, "w")):
            self.tabla_errores.heading(col, text=texto)
            self.tabla_errores.column(col, width=ancho, anchor=ancla, stretch=(col == "mensaje"))
        sy = ttk.Scrollbar(contenedor, orient="vertical", command=self.tabla_errores.yview)
        self.tabla_errores.configure(yscrollcommand=sy.set)
        sy.pack(side="right", fill="y")
        self.tabla_errores.pack(side="left", fill="both", expand=True)
        self.tabla_errores.tag_configure("error", foreground="#f48771")
        self.tabla_errores.bind("<Double-1>", self._on_doble_clic_error)
        self.tabla_errores.bind("<Return>", self._on_doble_clic_error)

    def _construir_arbol(self) -> None:
        barra = tk.Frame(self.pestanas["arbol"], bg=BG_LATERAL)
        barra.pack(side="top", fill="x")
        self._boton(barra, "Acercar  +", lambda: self._zoom_arbol_paso(ZOOM_PASO), bg=BG_LATERAL).pack(side="left", pady=3)
        self._boton(barra, "Alejar  −", lambda: self._zoom_arbol_paso(1 / ZOOM_PASO), bg=BG_LATERAL).pack(
            side="left", pady=3)

        marco = tk.Frame(self.pestanas["arbol"], bg=BG)
        marco.pack(side="top", fill="both", expand=True)
        self.canvas_arbol = tk.Canvas(marco, bg="#ffffff", highlightthickness=0)
        sy = ttk.Scrollbar(marco, orient="vertical", command=self.canvas_arbol.yview)
        sx = ttk.Scrollbar(marco, orient="horizontal", command=self.canvas_arbol.xview)
        self.canvas_arbol.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.canvas_arbol.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        marco.rowconfigure(0, weight=1)
        marco.columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # Atajos
    # ------------------------------------------------------------------

    def _atar_atajos(self) -> None:
        self.bind("<F5>", lambda _e: self.compilar())
        self.bind("<F6>", lambda _e: self.ejecutar_tac())
        self.bind("<F7>", lambda _e: self.correr_bateria())
        self.bind("<F8>", lambda _e: self.ejecutar_ensamblador())
        self.bind("<Control-Return>", lambda _e: self.compilar())
        self.bind("<Control-s>", lambda _e: self.guardar_archivo())
        self.bind("<Control-o>", lambda _e: self.abrir_archivo())
        for tecla in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            self.bind(tecla, lambda _e: self._zoom_editor(1))
        for tecla in ("<Control-minus>", "<Control-KP_Subtract>"):
            self.bind(tecla, lambda _e: self._zoom_editor(-1))
        self.bind("<Control-0>", lambda _e: self._zoom_editor(0))

    # ------------------------------------------------------------------
    # Edicion: gutter, resaltado, cursor, atajos de texto
    # ------------------------------------------------------------------

    def _on_yscroll(self, primero, ultimo) -> None:
        self.scroll_y.set(primero, ultimo)
        self._dibujar_gutter()

    def _dibujar_gutter(self) -> None:
        g = self.gutter
        g.delete("all")
        total = int(self.editor.index("end-1c").split(".")[0])
        ancho = self.f_editor.measure("0") * max(3, len(str(total))) + 34
        if int(g.cget("width")) != ancho:
            g.configure(width=ancho)
        actual = int(self.editor.index("insert").split(".")[0])
        n = int(self.editor.index("@0,0").split(".")[0])
        while n <= total:
            info = self.editor.dlineinfo(f"{n}.0")
            if info is None:
                break
            y, alto = info[1], info[3]
            if y + alto > self.editor.winfo_height() - 2:
                break
            color = "#c6c6c6" if n == actual else TEXTO_TENUE
            g.create_text(ancho - 14, y + alto / 2, anchor="e", text=str(n), fill=color, font=self.f_editor)
            if n in self.lineas_error:
                g.create_oval(9, y + alto / 2 - 5, 19, y + alto / 2 + 5, fill="#f14c4c", outline="")
            n += 1

    def _despues_de_editar(self) -> None:
        self._actualizar_cursor()
        if self._job_resaltado is not None:
            self.after_cancel(self._job_resaltado)
        self._job_resaltado = self.after(90, self._resaltar_editor)

    def _actualizar_cursor(self) -> None:
        linea, col = self.editor.index("insert").split(".")
        self.lbl_posicion.configure(text=f"Ln {linea}, Col {int(col) + 1}")
        self.editor.tag_remove("linea_actual", "1.0", "end")
        self.editor.tag_add("linea_actual", "insert linestart", "insert lineend+1c")
        self._dibujar_gutter()

    def _resaltar_editor(self) -> None:
        self._job_resaltado = None
        self._resaltar(self.editor, RE_FUENTE, self._clasificar_fuente)

    @staticmethod
    def _clasificar_fuente(m: re.Match, texto: str) -> str | None:
        tipo = m.lastgroup
        if tipo != "palabra":
            return tipo
        palabra = m.group()
        if palabra in CTRL:
            return "kw_ctrl"
        if palabra in KW:
            return "kw"
        if palabra in TIPOS:
            return "tipo"
        if palabra in CONSTANTES:
            return "const"
        resto = texto[m.end():m.end() + 40].lstrip(" \t")
        if resto.startswith("("):
            return "funcion"
        if palabra[0].isupper():
            return "clase"
        return None

    @staticmethod
    def _clasificar_tac(m: re.Match, _texto: str) -> str | None:
        tipo = m.lastgroup
        if tipo == "defunc":
            return "funcion"
        if tipo != "palabra":
            return tipo
        palabra = m.group()
        if palabra in TAC_CTRL:
            return "kw_ctrl"
        if palabra in TAC_KW:
            return "kw"
        return None

    @staticmethod
    def _clasificar_asm(m: re.Match, _texto: str) -> str | None:
        return {
            "comentario": "comentario",
            "cadena": "cadena",
            "etiqueta": "etiqueta",
            "directiva": "kw",
            "registro": "temp",
            "numero": "numero",
            "instruccion": "funcion",
        }[m.lastgroup]

    def _resaltar(self, widget: tk.Text, patron: re.Pattern, clasificar) -> None:
        texto = widget.get("1.0", "end-1c")
        for nombre in COLORES_SINTAXIS:
            widget.tag_remove(nombre, "1.0", "end")
        inicios = [0]
        for m in re.finditer(r"\n", texto):
            inicios.append(m.end())

        def idx(offset: int) -> str:
            linea = bisect.bisect_right(inicios, offset) - 1
            return f"{linea + 1}.{offset - inicios[linea]}"

        rangos: dict[str, list[str]] = {}
        for m in patron.finditer(texto):
            tag = clasificar(m, texto)
            if tag:
                rangos.setdefault(tag, []).extend((idx(m.start()), idx(m.end())))
        for tag, indices in rangos.items():
            widget.tag_add(tag, *indices)

    def _on_modificado(self, _evento=None) -> None:
        if self.editor.edit_modified():
            self.modificado = True
            self._actualizar_titulo()
            self.editor.edit_modified(False)

    def _on_return(self, _evento) -> str:
        e = self.editor
        antes = e.get("insert linestart", "insert")
        despues = e.get("insert", "insert lineend")
        sangria = re.match(r"[ \t]*", antes).group()
        abre = antes.rstrip().endswith("{")
        e.insert("insert", "\n" + sangria + ("    " if abre else ""))
        if abre and despues.strip().startswith("}"):
            pos = e.index("insert")
            e.insert("insert", "\n" + sangria)
            e.mark_set("insert", pos)
        e.see("insert")
        self._despues_de_editar()
        return "break"

    def _on_tab(self, _evento) -> str:
        self.editor.insert("insert", "    ")
        return "break"

    def _on_comentar(self, _evento) -> str:
        e = self.editor
        try:
            inicio, fin = e.index("sel.first linestart"), e.index("sel.last")
        except tk.TclError:
            inicio, fin = e.index("insert linestart"), e.index("insert")
        primera = int(inicio.split(".")[0])
        ultima = int(fin.split(".")[0])
        lineas = range(primera, ultima + 1)
        todas = all(e.get(f"{n}.0", f"{n}.end").lstrip().startswith("//") for n in lineas)
        for n in lineas:
            texto = e.get(f"{n}.0", f"{n}.end")
            if todas:
                nuevo = re.sub(r"^(\s*)// ?", r"\1", texto, count=1)
            else:
                nuevo = re.sub(r"^(\s*)", r"\1// ", texto, count=1)
            e.delete(f"{n}.0", f"{n}.end")
            e.insert(f"{n}.0", nuevo)
        self._despues_de_editar()
        return "break"

    # --- zoom -----------------------------------------------------------

    def _on_ctrl_rueda(self, evento) -> str:
        self._zoom_editor(1 if evento.delta > 0 else -1)
        return "break"

    def _zoom_editor(self, paso: int) -> None:
        tam = 15 if paso == 0 else max(9, min(34, int(self.f_editor.cget("size")) + paso))
        self.f_editor.configure(size=tam)
        self.f_panel.configure(size=max(9, tam - 2))
        self._actualizar_zoom_label()
        self._dibujar_gutter()

    def _actualizar_zoom_label(self) -> None:
        self.lbl_zoom.configure(text=f"Fuente {self.f_editor.cget('size')}")

    # ------------------------------------------------------------------
    # Titulo / pestana del archivo
    # ------------------------------------------------------------------

    def _actualizar_titulo(self) -> None:
        nombre = self.ruta_actual.name if self.ruta_actual else "sin_titulo.cps"
        punto = "  ●" if self.modificado else ""
        self.lbl_tab.configure(text=f"{{ }}  {nombre}{punto}")
        self.title(f"{nombre}{' ●' if self.modificado else ''} - Compiscript IDE")

    # ------------------------------------------------------------------
    # abrir / guardar
    # ------------------------------------------------------------------

    def abrir_archivo(self) -> None:
        ruta = filedialog.askopenfilename(filetypes=[("Compiscript", "*.cps"), ("Todos", "*.*")])
        if ruta:
            self.cargar_archivo(ruta)

    def cargar_archivo(self, ruta: str | pathlib.Path) -> None:
        ruta = pathlib.Path(ruta)
        try:
            contenido = ruta.read_text(encoding="utf-8")
        except OSError as error:
            messagebox.showerror("No se pudo abrir", str(error))
            return
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", contenido)
        self.editor.edit_reset()
        self.editor.edit_modified(False)
        self.ruta_actual = ruta
        self.modificado = False
        self.lineas_error = set()
        self.editor.tag_remove("linea_error", "1.0", "end")
        self.editor.mark_set("insert", "1.0")
        self._despues_de_editar()
        self._actualizar_titulo()
        self._estado("  Archivo abierto", AZUL)

    def guardar_archivo(self) -> None:
        if self.ruta_actual is None:
            self.guardar_como()
            return
        self._escribir_a_disco(self.ruta_actual)

    def guardar_como(self) -> None:
        ruta = filedialog.asksaveasfilename(defaultextension=".cps", filetypes=[("Compiscript", "*.cps")])
        if ruta:
            self.ruta_actual = pathlib.Path(ruta)
            self._escribir_a_disco(self.ruta_actual)

    def _escribir_a_disco(self, ruta: str | pathlib.Path) -> None:
        contenido = self.editor.get("1.0", "end-1c")
        try:
            pathlib.Path(ruta).write_text(contenido, encoding="utf-8")
        except OSError as error:
            messagebox.showerror("No se pudo guardar", str(error))
            return
        self.modificado = False
        self._actualizar_titulo()
        self._estado("  Guardado", AZUL)

    # ------------------------------------------------------------------
    # compilar y ejecutar
    # ------------------------------------------------------------------

    def _estado(self, texto: str, color: str) -> None:
        self.barra_estado.configure(bg=color)
        for w in self.barra_estado.winfo_children():
            w.configure(bg=color)
        self.lbl_estado.configure(text=texto)

    def _escribir(self, widget: tk.Text, texto: str, tag: str | None = None, limpiar: bool = True) -> None:
        widget.configure(state="normal")
        if limpiar:
            widget.delete("1.0", "end")
        widget.insert("end", texto, tag) if tag else widget.insert("end", texto)
        widget.configure(state="disabled")

    def _seleccionar_pestana(self, clave: str) -> None:
        self.tabs.select(self.pestanas[clave])

    def compilar(self) -> None:
        fuente = self.editor.get("1.0", "end-1c")
        self.resultado = analizar(fuente, nombre=str(self.ruta_actual) if self.ruta_actual else "<memoria>")
        self._pintar_tac()
        self._generar_ensamblador()
        self._pintar_errores()
        self._pintar_tabla()
        self._pintar_arbol()
        self._pintar_estado()
        self._seleccionar_pestana("tac" if self.resultado.tac is not None else "problemas")

    def _pintar_tac(self) -> None:
        r = self.resultado
        if r is None:
            return
        if r.tac is not None:
            self._escribir(self.texto_tac, r.tac.render())
            self._resaltar(self.texto_tac, RE_TAC, self._clasificar_tac)
        elif r.error_interno:
            self._escribir(self.texto_tac, f"Error interno del generador:\n{r.error_interno}", "fallo")
        else:
            self._escribir(
                self.texto_tac,
                f"No se generó código intermedio: hay {len(r.errores)} error(es).\n"
                "El generador solo corre cuando el análisis no reporta errores (ver pestaña PROBLEMAS).",
                "fallo",
            )

    @property
    def procesador(self) -> str:
        return PROCESADORES[self.menu_procesador.get()]

    def _cambiar_procesador(self, recompilar: bool = True) -> None:
        medios = medios_disponibles(self.procesador)
        self.menu_medio.configure(values=medios)
        self.menu_medio.set(medios[-1] if self.procesador == "arm64" else medios[0])
        if recompilar and self.resultado is not None:
            self._generar_ensamblador()

    def _generar_ensamblador(self) -> None:
        """Traduce el TAC al procesador elegido y llena sus dos pestanas."""
        self.ensamblado = None
        r = self.resultado
        if r is None or r.tac is None:
            self._escribir(self.texto_asm, "No se generó ensamblador: corrija los problemas primero.", "fallo")
            self._escribir(self.texto_registros, "")
            return
        try:
            self.ensamblado = generar_ensamblador(r, self.procesador)
        except BackendError as error:
            self._escribir(self.texto_asm, f"Error de generación de código:\n{error}", "fallo")
            self._escribir(self.texto_registros, "")
            return
        self._escribir(self.texto_asm, self.ensamblado.codigo)
        self._resaltar(self.texto_asm, RE_ASM, self._clasificar_asm)
        reporte = self.ensamblado.reporte()
        if self.ensamblado.avisos:
            reporte = "\n".join(f"Aviso: {a}" for a in self.ensamblado.avisos) + "\n\n" + reporte
        self._escribir(self.texto_registros, reporte)

    def ejecutar_ensamblador(self) -> None:
        """Compila y ejecuta el ensamblador en el medio elegido."""
        self.compilar()
        if self.ensamblado is None:
            self._seleccionar_pestana("asm" if self.resultado and self.resultado.ok else "problemas")
            return
        medio = self.menu_medio.get()
        try:
            ejecucion = ejecutar_codigo(self.ensamblado.codigo, self.procesador, medio)
        except ERRORES_DE_EJECUCION as error:
            self._escribir(self.texto_salida, f"No se pudo ejecutar el ensamblador:\n{error}", "fallo")
            self._estado("  Error al ejecutar", ROJO)
            self._seleccionar_pestana("salida")
            return
        titulo = f"▶ Salida del programa ({self.menu_procesador.get()}, {ejecucion.medio})\n\n"
        self._escribir(self.texto_salida, titulo, "titulo")
        self._escribir(self.texto_salida, ejecucion.salida or "(el programa no imprimió nada)",
                       None if ejecucion.salida else "tenue", limpiar=False)
        if ejecucion.instrucciones is not None:
            detalle = f"\n\n{ejecucion.instrucciones} instrucciones, {ejecucion.pila_maxima} bytes de pila"
            self._escribir(self.texto_salida, detalle, "tenue", limpiar=False)
        self._estado(f"  Terminó con código {ejecucion.codigo_salida}", VERDE if ejecucion.codigo_salida == 0 else ROJO)
        self._seleccionar_pestana("salida")

    def guardar_ensamblador(self) -> None:
        self.compilar()
        if self.ensamblado is None:
            self._seleccionar_pestana("asm" if self.resultado and self.resultado.ok else "problemas")
            return
        extension = ".asm" if self.procesador == "mips" else ".s"
        ruta = filedialog.asksaveasfilename(
            defaultextension=extension, filetypes=[("Ensamblador", f"*{extension}"), ("Todos", "*.*")]
        )
        if ruta:
            pathlib.Path(ruta).write_text(self.ensamblado.codigo, encoding="utf-8", newline="\n")
            self._estado(f"  Guardado en {ruta}", VERDE)

    def ejecutar_tac(self) -> None:
        """Corre el TAC con el simulador y muestra lo que imprime el programa."""
        self.compilar()
        r = self.resultado
        if r is None or r.tac is None:
            self._escribir(self.texto_salida, "Nada que ejecutar: corrija los problemas primero.", "fallo")
            self._seleccionar_pestana("problemas")
            return
        try:
            salida = ejecutar(r)
            self._escribir(self.texto_salida, "▶ Salida del programa\n\n", "titulo")
            self._escribir(self.texto_salida, "\n".join(salida) if salida else "(el programa no imprimió nada)",
                           None if salida else "tenue", limpiar=False)
            self._estado("  Ejecución terminada", VERDE)
        except Exception as error:  # noqa: BLE001 - se muestra al usuario
            self._escribir(self.texto_salida, f"Error en tiempo de ejecución: {error!r}", "fallo")
            self._estado("  Error en tiempo de ejecución", ROJO)
        self._seleccionar_pestana("salida")

    # ------------------------------------------------------------------
    # paneles
    # ------------------------------------------------------------------

    def _pintar_errores(self) -> None:
        self.tabla_errores.delete(*self.tabla_errores.get_children())
        self.editor.tag_remove("linea_error", "1.0", "end")
        self.lineas_error = set()
        r = self.resultado
        if r is None:
            return
        for error in r.errores:
            self.tabla_errores.insert("", "end", values=(error.line, error.column, error.category, error.message),
                                      tags=("error",))
            self.lineas_error.add(error.line)
            self.editor.tag_add("linea_error", f"{error.line}.0", f"{error.line}.end+1c")
        n = len(r.errores)
        self.tabs.tab(self.pestanas["problemas"], text=f"PROBLEMAS  {n}" if n else "PROBLEMAS")
        self._dibujar_gutter()

    def _on_doble_clic_error(self, _evento=None) -> None:
        seleccion = self.tabla_errores.selection()
        if not seleccion:
            return
        linea, columna = self.tabla_errores.item(seleccion[0], "values")[:2]
        self.editor.mark_set("insert", f"{linea}.{columna}")
        self.editor.see(f"{linea}.0")
        self.editor.focus_set()
        self._despues_de_editar()

    def _pintar_tabla(self) -> None:
        r = self.resultado
        if r is None or r.table is None:
            return
        texto = "== Entornos (tabla de símbolos) ==\n" + r.table.format_environments()
        if r.generador is not None:
            texto += "\n\n" + render_codegen_report(r.generador)
        self._escribir(self.texto_tabla, texto)
        t = self.texto_tabla
        t.configure(state="normal")
        for tag in ("titulo", "env", "tipo"):
            t.tag_remove(tag, "1.0", "end")
        for n, linea in enumerate(texto.split("\n"), start=1):
            if linea.startswith("=="):
                t.tag_add("titulo", f"{n}.0", f"{n}.end")
            elif re.match(r"^\[\d+\]", linea):
                t.tag_add("env", f"{n}.0", f"{n}.end")
            elif linea.startswith(("AR ", "clase ")):
                t.tag_add("tipo", f"{n}.0", f"{n}.end")
        t.configure(state="disabled")

    def _pintar_arbol(self) -> None:
        self.canvas_arbol.delete("all")
        self._imagen_arbol_pil = None
        self._imagen_arbol_tk = None
        self._zoom_arbol = 1.0
        r = self.resultado
        if r is None or r.tree is None or r.parser is None:
            return

        if dot_disponible():
            try:
                png_bytes = render_png(r.tree, r.parser.ruleNames, MAX_NODOS_ARBOL)
                self._imagen_arbol_pil = Image.open(io.BytesIO(png_bytes))
                self._dibujar_imagen_arbol()
                return
            except Exception:  # noqa: BLE001 - cae al texto
                pass

        texto = render_texto(r.tree, r.parser)
        self.canvas_arbol.create_text(14, 14, anchor="nw", text=texto, font=self.f_panel, fill="#1e1e1e")
        self.canvas_arbol.configure(scrollregion=self.canvas_arbol.bbox("all"))

    def _dibujar_imagen_arbol(self) -> None:
        if self._imagen_arbol_pil is None:
            return
        ancho = int(self._imagen_arbol_pil.width * self._zoom_arbol)
        alto = int(self._imagen_arbol_pil.height * self._zoom_arbol)
        escalada = self._imagen_arbol_pil.resize((max(ancho, 1), max(alto, 1)))
        self._imagen_arbol_tk = ImageTk.PhotoImage(escalada)
        self.canvas_arbol.delete("all")
        self.canvas_arbol.create_image(0, 0, anchor="nw", image=self._imagen_arbol_tk)
        self.canvas_arbol.configure(scrollregion=(0, 0, ancho, alto))

    def _zoom_arbol_paso(self, factor: float) -> None:
        if self._imagen_arbol_pil is None:
            return
        self._zoom_arbol *= factor
        self._dibujar_imagen_arbol()

    def correr_bateria(self) -> None:
        self._estado("  Ejecutando batería de pruebas...", "#6c4a00")
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            resultados = ejecutar_bateria()
        finally:
            self.config(cursor="")
        pasaron = sum(1 for r in resultados if r.paso)
        total = len(resultados)

        t = self.texto_bateria
        self._escribir(t, f"✔ {pasaron}/{total} pruebas pasaron\n", "ok" if pasaron == total else "fallo")
        self._escribir(t, f"{total - pasaron} fallida(s)\n\n", "tenue", limpiar=False)
        for r in resultados:
            marca, tag = ("✔", "ok") if r.paso else ("✖", "fallo")
            ruta = r.archivo.relative_to(r.archivo.parents[2]).as_posix()
            self._escribir(t, f"{marca} {ruta}\n", tag, limpiar=False)
            if not r.paso:
                self._escribir(t, f"     {r.razon}\n", "tenue", limpiar=False)
        self._estado(f"  Batería: {pasaron}/{total} pasaron", VERDE if pasaron == total else ROJO)
        self._seleccionar_pestana("bateria")

    def _pintar_estado(self) -> None:
        r = self.resultado
        if r is None:
            return
        if r.ok:
            self._estado("  ✔ Compilación correcta", VERDE)
        else:
            n = len(r.errores)
            self._estado(f"  ✖ {n} problema{'s' if n != 1 else ''}", ROJO)


def main() -> None:
    app = CompiscriptIDE()
    app.mainloop()


if __name__ == "__main__":
    main()
