"""Ejecuta el JavaScript de docs/index.html sobre un DOM simulado en QuickJS.

No sustituye a abrir la página, pero demuestra con los datos reales del último
escaneo que la web arranca, pinta fichas, filtra, ordena y que las estrellas y
los favoritos se guardan y se pueden publicar y retirar.

    ./.venv/bin/pip install -r requirements-dev.txt
    ./.venv/bin/python tests/test_ui.py
"""

import json
import pathlib
import re
import sys

import quickjs

RAIZ = pathlib.Path(__file__).resolve().parent.parent

SHIM = r"""
var __log = [];
var console = { log:function(){}, warn:function(){}, error:function(m){ __log.push("ERR:"+m); } };

function Elem(tag){
  this.tagName = tag || "div";
  this.children = [];
  this._attrs = {};
  this._text = "";
  this._html = "";
  this._listeners = {};
  this.style = {};
  this.value = "";
  var self = this;
  this.classList = {
    _s: {},
    add:function(c){ self.classList._s[c]=true; },
    remove:function(c){ delete self.classList._s[c]; },
    toggle:function(c,on){ if(on){self.classList._s[c]=true;} else {delete self.classList._s[c];} },
    contains:function(c){ return !!self.classList._s[c]; }
  };
}
Object.defineProperty(Elem.prototype, "className", {
  get:function(){ return Object.keys(this.classList._s).join(" "); },
  set:function(v){ this.classList._s={};
    (""+v).split(/\s+/).forEach(function(c){ if(c) this.classList._s[c]=true; }, this); }
});
Object.defineProperty(Elem.prototype, "innerHTML", {
  get:function(){ return this._html; },
  set:function(v){ this._html = ""+v; if(v==="") this.children=[]; }
});
Object.defineProperty(Elem.prototype, "textContent", {
  get:function(){ return this._text; },
  set:function(v){ this._text = ""+v; }
});
Elem.prototype.appendChild = function(c){
  if (c && c.__frag) this.children = this.children.concat(c.children);
  else this.children.push(c);
  return c;
};
Elem.prototype.setAttribute = function(k,v){ this._attrs[k]=""+v; };
Elem.prototype.getAttribute = function(k){ return this._attrs[k]===undefined?null:this._attrs[k]; };
Elem.prototype.addEventListener = function(t,f){ (this._listeners[t]=this._listeners[t]||[]).push(f); };
Elem.prototype.click = function(){ (this._listeners["click"]||[]).forEach(function(f){ f({}); }); };
Elem.prototype.querySelector = function(sel){
  if (!this.__q) this.__q = {};
  if (!this.__q[sel]) this.__q[sel] = new Elem("button");
  return this.__q[sel];
};
Elem.prototype.showModal = function(){ this.__abierto = true; };
Elem.prototype.close = function(){ this.__abierto = false; };
Elem.prototype.select = function(){};

var __reg = {};
var document = {
  querySelector: function(sel){
    if (!__reg[sel]) __reg[sel] = new Elem("div");
    return __reg[sel];
  },
  createElement: function(t){ return new Elem(t); },
  createDocumentFragment: function(){ var f = new Elem("frag"); f.__frag = true; return f; },
  execCommand: function(){}
};
var __store = {};
var localStorage = {
  getItem:function(k){ return __store[k]===undefined?null:__store[k]; },
  setItem:function(k,v){ __store[k]=""+v; },
  removeItem:function(k){ delete __store[k]; }
};
var navigator = { clipboard: { writeText: function(){ return Promise.resolve(); } } };
function setTimeout(f,ms){ return 0; }
function clearTimeout(){}
function confirm(){ return true; }
var location = { reload:function(){}, href:"" };
var window = {};
"""


def carga_app():
    html = (RAIZ / "docs" / "index.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    if not scripts:
        sys.exit("No se encontró el script embebido en docs/index.html")
    return max(scripts, key=len)


def corre(inyeccion=""):
    """Arranca la web en QuickJS. `inyeccion` se ejecuta antes que la app."""
    datajs = (RAIZ / "docs" / "data.js").read_text(encoding="utf-8")
    ctx = quickjs.Context()
    ctx.eval(SHIM + "\n" + datajs + "\n" + inyeccion + "\n" + carga_app())
    return ctx


def leer(ctx, expr, por_defecto=""):
    try:
        return ctx.eval(expr)
    except Exception:
        return por_defecto


PRUEBAS = []


def comprueba(nombre, condicion, detalle=""):
    PRUEBAS.append((nombre, bool(condicion), str(detalle)[:78]))


# ---------------------------------------------------------------- escenario 1
try:
    ctx = corre()
except Exception as e:
    sys.exit(f"✗ El JavaScript ha fallado al arrancar:\n  {str(e)[:900]}")

n = leer(ctx, "__reg['#rejilla'].children.length", -1)
comprueba("Se pintan fichas en la rejilla", n > 0, f"{n} fichas")
comprueba("Sin errores en consola", not leer(ctx, "__log.join(' | ')"),
          leer(ctx, "__log.join(' | ')"))

conteo = leer(ctx, "__reg['#conteo'].textContent")
comprueba("El contador se rellena", "vivienda" in str(conteo), conteo)

activos = str(leer(ctx, "String(__reg['#c-activos'].textContent)"))
comprueba("La cifra de activos es un número", activos.isdigit() and int(activos) > 0, activos)

comprueba("El subtítulo muestra la fecha",
          "Actualizado" in str(leer(ctx, "__reg['#subtitulo'].textContent")),
          leer(ctx, "__reg['#subtitulo'].textContent"))

# QuickJS no lleva ICU: toLocaleString no separa millares. Miramos el texto.
pie = str(leer(ctx, "__reg['#pie-criterios'].textContent"))
comprueba("El pie explica los criterios", "Criterios" in pie and "20 minutos" in pie, pie)

ficha0 = str(leer(ctx, "__reg['#rejilla'].children[0].innerHTML"))
comprueba("La ficha lleva precio y enlaces", "€" in ficha0 and "enlace" in ficha0,
          ficha0.replace("\n", " ")[:60])

# --- destacar con la estrella ---
antes = str(leer(ctx, "String(__reg['#c-destacados'].textContent)"))
leer(ctx, "__reg['#rejilla'].children[0].__q['[data-marca=\"estrella\"]'].click()")
despues = str(leer(ctx, "String(__reg['#c-destacados'].textContent)"))
comprueba("La estrella incrementa el contador", antes == "0" and despues == "1",
          f"{antes} -> {despues}")

guardado = str(leer(ctx, "__store['pisos-baix-emporda:marcas-v1'] || ''"))
comprueba("La marca se guarda en el navegador",
          len(json.loads(guardado or "{}").get("destacados", [])) == 1, guardado)

comprueba("Avisa de marcas sin publicar",
          "sin publicar" in str(leer(ctx, "__reg['#texto-pendientes'].textContent")),
          leer(ctx, "__reg['#texto-pendientes'].textContent"))

# Contamos la diferencia, no el total, y pulsamos sobre una ficha que aún no
# sea favorita: ya hay favoritos publicados (los que Albert fija a mano en
# data/fijados.json) y sobre esos el botón lo que hace es quitar la marca.
fav_antes = int(str(leer(ctx, "String(__reg['#c-favoritos'].textContent)")) or 0)
indice_libre = leer(ctx, """(function(){
  var f = __reg['#rejilla'].children;
  for (var i=0;i<f.length;i++) if (f[i].innerHTML.indexOf('on-favorito') < 0) return i;
  return -1;
})()""", -1)
leer(ctx, f"__reg['#rejilla'].children[{indice_libre}].__q['[data-marca=\"favorito\"]'].click()")
fav_despues = int(str(leer(ctx, "String(__reg['#c-favoritos'].textContent)")) or 0)
comprueba("El favorito verde se registra",
          indice_libre >= 0 and fav_despues == fav_antes + 1,
          f"ficha #{indice_libre}: {fav_antes} -> {fav_despues}")

# --- filtro de habitaciones ---
todas = leer(ctx, "__reg['#rejilla'].children.length", -1)
leer(ctx, "__reg['#f-hab'].children[2].click()")           # chip "3"
tres = leer(ctx, "__reg['#rejilla'].children.length", -1)
comprueba("El filtro de habitaciones filtra", 0 < tres < todas,
          f"{todas} -> {tres} con 3 hab.")
leer(ctx, "__reg['#f-hab'].children[2].click()")

# --- filtro de extras ---
leer(ctx, "__reg['#f-extras'].children[0].click()")        # chip "Parking"
con_parking = leer(ctx, "__reg['#rejilla'].children.length", -1)
comprueba("El filtro de extras filtra", 0 <= con_parking < todas,
          f"{todas} -> {con_parking} con parking")
leer(ctx, "__reg['#f-extras'].children[0].click()")

# --- ordenación por precio ---
leer(ctx, """(function(){
  (__reg['#f-orden']._listeners['change']||[]).forEach(function(f){
    f({target:{value:'precio-asc'}});
  });
})()""")
precios = str(leer(ctx, """(function(){
  return __reg['#rejilla'].children.slice(0,6).map(function(f){
    var m = f.innerHTML.match(/class="precio">([^<]*)/);
    return m ? m[1].replace(/[^0-9]/g,'') : '';
  }).join(',');
})()"""))
nums = [int(x) for x in precios.split(",") if x]
comprueba("Ordenar por precio funciona", len(nums) > 2 and nums == sorted(nums), precios)

# ---------------------------------------------------------------- escenario 2
# Una marca que YA venía publicada en el repositorio: al quitarla tiene que
# guardarse la baja y poder publicarse, no revertirse al recargar.
# Ha de ser una ficha activa: las retiradas no se pintan salvo que se pidan.
primero = leer(ctx, "window.DATOS.anuncios.filter(function(a){return a.activo;})[0].id")
ctx2 = corre(f'window.DATOS.marcas = {{destacados:["{primero}"], favoritos:[], notas:{{}}}};')

comprueba("Una marca publicada se ve al abrir",
          str(leer(ctx2, "String(__reg['#c-destacados'].textContent)")) == "1")

# El estado "destacado" se pinta dentro de innerHTML, así que localizamos la
# ficha marcada por su HTML y pulsamos su estrella.
pulsado = leer(ctx2, """(function(){
  var fichas = __reg['#rejilla'].children;
  for (var i=0;i<fichas.length;i++){
    if (fichas[i].innerHTML.indexOf('on-estrella') >= 0) {
      fichas[i].__q['[data-marca="estrella"]'].click();
      return i;
    }
  }
  return -1;
})()""", -1)
comprueba("Se localiza la ficha ya destacada", pulsado >= 0, f"ficha #{pulsado}")

comprueba("Quitar una marca publicada baja el contador",
          str(leer(ctx2, "String(__reg['#c-destacados'].textContent)")) == "0",
          leer(ctx2, "String(__reg['#c-destacados'].textContent)"))

g2 = json.loads(str(leer(ctx2, "__store['pisos-baix-emporda:marcas-v1'] || '{}'")))
comprueba("La baja queda registrada para publicar",
          primero in g2.get("quitados", {}).get("destacados", []),
          json.dumps(g2.get("quitados", {})))

comprueba("La barra ofrece publicar la baja",
          str(leer(ctx2, "__reg['#texto-pendientes'].textContent")).startswith("1 "),
          leer(ctx2, "__reg['#texto-pendientes'].textContent"))

leer(ctx2, "__reg['#b-publicar'].click()")
publicable = str(leer(ctx2, "__reg['#txt-marcas'].value", "")) or "{}"
comprueba("El JSON a publicar ya no incluye la marca retirada",
          primero not in json.loads(publicable).get("destacados", []),
          publicable.replace("\n", " ")[:60])

# ---------------------------------------------------------------- resultado
print()
todo_ok = True
for nombre, paso, detalle in PRUEBAS:
    print(f"  {'✓' if paso else '✗'} {nombre:44} {detalle}")
    todo_ok = todo_ok and paso
print(f"\n  {sum(1 for _, p, _ in PRUEBAS if p)}/{len(PRUEBAS)} pruebas correctas\n")
sys.exit(0 if todo_ok else 1)
