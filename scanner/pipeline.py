"""Normalizado, exclusiones, deduplicado entre portales y memoria histórica.

La memoria histórica es lo que permite dos cosas que pediste: marcar cada día
las viviendas nuevas (las que nunca se habían visto) y que las anteriores
sigan ahí, con sus estrellas y favoritos intactos.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime

from . import config as cfg


# --- texto -----------------------------------------------------------------

def sin_acentos(t):
    if not t:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", str(t))
                   if unicodedata.category(c) != "Mn").lower()


def texto_completo(a):
    return sin_acentos(" ".join(str(a.get(k) or "") for k in
                                ("titulo", "descripcion", "texto_bruto", "zona")))


# --- municipio -------------------------------------------------------------

def clave_municipio(t):
    """Reduce un nombre de municipio a una forma comparable.

    Cada portal lo escribe a su manera: "La Bisbal d'Empordà",
    "la_bisbal_d_emporda" (slug de Habitaclia), "Bisbal d´Empordà (La)".
    Todo acaba en "la bisbal d emporda".
    """
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", sin_acentos(t))).strip()


_CANON = {clave_municipio(m): m for m in cfg.MUNICIPIOS}
_CANON.update({clave_municipio(k): v for k, v in cfg.ALIAS_MUNICIPIOS.items()})


def normaliza_municipio(nombre):
    """Devuelve el nombre canónico del municipio, o None si cae fuera de zona."""
    if not nombre:
        return None
    limpio = clave_municipio(re.sub(r"\s*\(.*?\)\s*", " ", str(nombre)))
    if limpio in _CANON:
        return _CANON[limpio]
    # "Bisbal d'Empordà (La)" -> el artículo va al final
    m = re.match(r"^(.*?)\s+(la|el|les|els|l)$", limpio)
    if m and clave_municipio(f"{m.group(2)} {m.group(1)}") in _CANON:
        return _CANON[clave_municipio(f"{m.group(2)} {m.group(1)}")]
    # "l'estartit - torroella", "palamos centre", etc.
    for trozo in re.split(r"[-–/,]", clave_municipio(str(nombre))):
        t = trozo.strip()
        if t in _CANON:
            return _CANON[t]
    # búsqueda por contención (el portal añade barrio o provincia)
    for clave, canon in _CANON.items():
        if len(clave) > 4 and clave in limpio:
            return canon
    return None


# --- filtros ---------------------------------------------------------------

def es_vivienda_en_edificio(a):
    """True si es un piso (o ático/dúplex/estudio/apartamento/bajo)."""
    tipo = (a.get("tipo") or "").lower()
    if tipo in cfg.TIPOS_INCLUIDOS:
        return True
    if tipo in ("casa", "terreno", "garaje", "trastero", "oficina"):
        return False
    # sin tipo fiable: decidimos por el título
    titulo = sin_acentos(a.get("titulo"))
    for kw in cfg.TIPOS_EXCLUIDOS_KW:
        if sin_acentos(kw).strip() in titulo:
            return False
    return any(sin_acentos(t) in titulo for t in cfg.TIPOS_INCLUIDOS)


def motivo_descarte(a):
    """Devuelve el motivo por el que un anuncio es 'raro', o None si está limpio."""
    flags = a.get("flags") or {}
    etiquetas = {"subasta": "subasta", "ocupado": "ocupado",
                 "nuda_propiedad": "nuda propiedad", "con_inquilinos": "alquilado con inquilinos"}
    for k, etiqueta in etiquetas.items():
        if flags.get(k):
            return etiqueta

    texto = texto_completo(a)
    for kw in cfg.EXCLUIR_KW:
        if sin_acentos(kw) in texto:
            return kw
    return None


def detecta_extras(a):
    """Extras por palabra clave, más los que el propio portal ya declara."""
    texto = texto_completo(a)
    declarados = a.get("extras_portal") or {}
    extras = {}
    for clave, variantes in cfg.EXTRAS.items():
        extras[clave] = bool(declarados.get(clave)) or any(
            sin_acentos(v) in texto for v in variantes)
    return extras


# --- deduplicado -----------------------------------------------------------

def uid_de(clave):
    return hashlib.sha1(clave.encode("utf-8")).hexdigest()[:12]


# --- ¿son el mismo piso? ---------------------------------------------------
# Un mismo piso puede estar anunciado por tres agencias con precio distinto
# (149.000 / 150.000), superficie distinta (construida o útil) y títulos que
# no se parecen en nada. Comparamos varias señales a la vez en lugar de
# exigir que precio y metros coincidan exactamente.

VIAS = ("calle", "carrer", "avenida", "avinguda", "av", "passeig", "paseo",
        "plaza", "placa", "rambla", "cami", "camino", "travessia", "travesia",
        "ronda", "carretera", "ctra", "urbanitzacio", "urbanizacion", "pasaje",
        "passatge", "baixada", "bajada", "pujada", "riera", "muralla")

ARTICULOS = {"de", "del", "dels", "la", "les", "el", "els", "l", "d", "en"}

# Palabras que ya no forman parte del nombre de la calle: en cuanto aparece
# una, el nombre se ha terminado. Sin esto, de "Carrer del bruc. Piso en venta"
# se sacaba "bruc piso en", que no casaba con el "bruc" del otro portal y
# dejaba el mismo piso duplicado.
PARADAS = {"piso", "pisos", "duplex", "atico", "estudio", "apartamento", "loft",
           "casa", "planta", "bajo", "venta", "vender", "alquiler", "vivienda",
           "zona", "barrio", "ref", "referencia", "oportunidad", "exclusiva",
           "inmobiliaria", "reformado", "reformada", "nuevo", "nueva", "gran",
           "amplio", "amplia", "bonito", "bonita", "con", "sin", "para", "por"}

RE_NUMERO_VIA = re.compile(r"^(\d{1,4})[a-z]?$")


def via_de(a):
    """Saca (nombre de calle, número) del título. (None, None) si no se ve.

    Se trabaja frase a frase: el nombre de una calle nunca cruza un punto.
    """
    bruto = f"{a.get('titulo') or ''}. {a.get('zona') or ''}"
    for frase in re.split(r"[.;:|–—]", bruto):
        palabras = clave_municipio(frase).split()
        for i, p in enumerate(palabras):
            if p not in VIAS:
                continue
            nombre, numero = [], None
            for w in palabras[i + 1:i + 8]:
                m = RE_NUMERO_VIA.match(w)
                if m:
                    if nombre:
                        numero = m.group(1)
                        break
                    continue
                if w in ARTICULOS:
                    continue                       # "de la", "dels"... se ignoran
                if w in VIAS or w in PARADAS or len(nombre) >= 3:
                    break
                nombre.append(w)
            if nombre:
                return " ".join(nombre), numero
    return None, None


def planta_de_ficha(a):
    """Normaliza la planta a algo comparable: '1', 'bajo'... o None."""
    t = sin_acentos(a.get("planta") or "")
    if not t:
        return None
    if "bajo" in t or "baja" in t:
        return "bajo"
    if "atico" in t:
        return "atico"
    m = re.search(r"(\d+)", t)
    return m.group(1) if m else None


def _metros_cerca(a, b):
    """Distancia aproximada en metros entre dos anuncios geolocalizados."""
    if not (a.get("lat") and a.get("lon") and b.get("lat") and b.get("lon")):
        return None
    dlat = (float(a["lat"]) - float(b["lat"])) * 111_320
    dlon = (float(a["lon"]) - float(b["lon"])) * 111_320 * 0.74  # cos(42º)
    return (dlat ** 2 + dlon ** 2) ** 0.5


def mismo_piso(a, b):
    """True si dos anuncios son, con bastante seguridad, la misma vivienda."""
    # Plantas distintas conocidas: son pisos distintos del mismo edificio.
    pa, pb = planta_de_ficha(a), planta_de_ficha(b)
    if pa and pb and pa != pb:
        return False

    via_a, num_a = a["_via"]
    via_b, num_b = b["_via"]
    if via_a and via_b and via_a != via_b:
        return False                      # calles distintas
    if num_a and num_b and num_a != num_b:
        return False                      # misma calle, portal distinto
    misma_via = bool(via_a and via_b and via_a == via_b)

    m2a, m2b = a.get("m2"), b.get("m2")
    pra, prb = a.get("precio"), b.get("precio")

    # Vetos: por muy bien que encaje todo lo demás, esto delata dos pisos
    # distintos del mismo edificio. Sin ellos se fundía un piso de 2
    # habitaciones con uno de 4, y uno de 71 m² con uno de 96.
    ha, hb = a.get("habitaciones"), b.get("habitaciones")
    if ha is not None and hb is not None and ha != hb:
        return False
    if m2a and m2b and abs(m2a - m2b) > max(6, 0.12 * max(m2a, m2b)):
        return False

    # La superficie baila entre construida y útil; el precio, entre agencias.
    mismos_m2 = bool(m2a and m2b and abs(m2a - m2b) <= max(2, 0.04 * max(m2a, m2b)))
    mismo_precio = bool(pra and prb and abs(pra - prb) <= max(1_000, 0.02 * max(pra, prb)))
    mismas_hab = a.get("habitaciones") is not None and a.get("habitaciones") == b.get("habitaciones")
    mismos_banos = a.get("banos") is not None and a.get("banos") == b.get("banos")

    metros = _metros_cerca(a, b)
    mismo_edificio = metros is not None and metros <= 40

    if mismos_m2 and mismo_precio:
        return True
    if misma_via and (mismos_m2 or mismo_precio):
        return True
    if mismo_edificio and mismos_m2 and mismas_hab:
        return True
    if misma_via and num_a and num_a == num_b and mismas_hab and mismos_banos:
        return True
    return False


def agrupa(validos):
    """Agrupa los anuncios que son el mismo piso. Compara solo dentro del
    mismo municipio, que es lo que hace el coste irrelevante."""
    for a in validos:
        a["_via"] = via_de(a)

    por_municipio = {}
    for a in validos:
        por_municipio.setdefault(a["municipio_norm"], []).append(a)

    grupos = []
    for lista in por_municipio.values():
        padre = list(range(len(lista)))

        def raiz(i):
            while padre[i] != i:
                padre[i] = padre[padre[i]]
                i = padre[i]
            return i

        for i in range(len(lista)):
            for j in range(i + 1, len(lista)):
                ri, rj = raiz(i), raiz(j)
                if ri != rj and mismo_piso(lista[i], lista[j]):
                    padre[ri] = rj

        cubos = {}
        for i, a in enumerate(lista):
            cubos.setdefault(raiz(i), []).append(a)
        grupos.extend(cubos.values())

    return grupos


ORDEN_PORTALES = ["idealista", "fotocasa", "habitaclia", "pisos", "milanuncios"]


def fusiona(grupo):
    """Funde varios anuncios del mismo piso en una ficha con todos los enlaces."""
    grupo = sorted(grupo, key=lambda a: ORDEN_PORTALES.index(a["portal"])
                   if a["portal"] in ORDEN_PORTALES else 99)
    principal = grupo[0]

    def primero(campo):
        for a in grupo:
            if a.get(campo) not in (None, "", 0):
                return a[campo]
        return None

    extras = {}
    for a in grupo:
        for k, v in (a.get("extras") or {}).items():
            extras[k] = extras.get(k, False) or v

    descripcion = max((a.get("descripcion") or "" for a in grupo), key=len)

    # Un enlace por portal: si el mismo piso está anunciado dos veces en el
    # mismo sitio, en la ficha basta con el primero.
    enlaces, ya = [], set()
    for a in grupo:
        if a.get("url") and a["portal"] not in ya:
            ya.add(a["portal"])
            enlaces.append({"portal": a["portal"], "url": a["url"]})

    return {
        "titulo": principal.get("titulo"),
        "precio": primero("precio"),
        "m2": primero("m2"),
        "habitaciones": primero("habitaciones"),
        "banos": primero("banos"),
        "planta": primero("planta"),
        "municipio": principal.get("municipio_norm"),
        "minutos": cfg.MUNICIPIOS.get(principal.get("municipio_norm")),
        "preferente": principal.get("municipio_norm") in cfg.PREFERENTES,
        "zona": primero("zona"),
        "tipo": primero("tipo") or "piso",
        "descripcion": descripcion[:900],
        "foto": primero("foto"),
        "lat": primero("lat"),
        "lon": primero("lon"),
        "extras": extras,
        "enlaces": enlaces,
        "portal_ids": sorted({f"{a['portal']}:{a['id_portal']}" for a in grupo}),
    }


def precio_m2(f):
    if f.get("precio") and f.get("m2"):
        return round(f["precio"] / f["m2"])
    return None


def es_ideal(f):
    """1 habitación y hasta 130.000 €: el perfil que busca Albert.

    El número de baños no cuenta. El tope de precio es inclusivo.
    """
    precio = f.get("precio")
    return (f.get("habitaciones") == cfg.IDEAL_HABITACIONES
            and precio is not None
            and precio <= cfg.IDEAL_PRECIO_MAX)


# --- memoria histórica -----------------------------------------------------

def carga_json(ruta, por_defecto):
    try:
        with open(ruta, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return por_defecto


def guarda_json(ruta, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=1, sort_keys=True)


# --- favoritos fijados a mano ----------------------------------------------

PORTAL_POR_DOMINIO = {
    "idealista.com": "idealista", "fotocasa.es": "fotocasa",
    "habitaclia.com": "habitaclia", "pisos.com": "pisos",
    "milanuncios.com": "milanuncios",
}


def huella_url(url):
    """(portal, id del anuncio) de un enlace, para reconocerlo aunque el portal
    le cambie los parámetros o reescriba la ruta.

    Nos quedamos solo con la ristra de dígitos más larga, que es el
    identificador del anuncio. Comparar cualquier número de cinco cifras daba
    falsos positivos: "17200" es el código postal de Palafrugell y aparece en
    media pisos.com.
    """
    u = str(url or "").lower()
    portal = next((p for dom, p in PORTAL_POR_DOMINIO.items() if dom in u), None)
    numeros = re.findall(r"\d{6,}", u.split("?")[0])
    ident = max(numeros, key=len) if numeros else None
    return portal, ident


def aplica_fijados(fichas, marcas, hoy):
    """Marca como favorito lo que Albert ha fijado a mano.

    Si el escaneo lo ha encontrado, se le pone la marca verde. Si no (porque
    se ha retirado, porque el portal lo esconde o porque se sale del
    presupuesto), se añade la ficha con los datos del fichero para que no
    desaparezca del enlace público.
    """
    fijados = carga_json(cfg.FICHERO_FIJADOS, [])
    if not isinstance(fijados, list) or not fijados:
        return fichas, {"encontrados": 0, "anadidos": 0}

    favoritos = set(marcas.get("favoritos") or ())
    indice = {}
    for f in fichas:
        for e in f.get("enlaces", []):
            portal, ident = huella_url(e["url"])
            if ident:
                indice.setdefault((portal, ident), f)

    encontrados = anadidos = 0
    for fij in fijados:
        portal, ident = huella_url(fij.get("url"))
        hallada = indice.get((portal, ident)) if ident else None

        if hallada is not None:
            favoritos.add(hallada["id"])
            hallada["fijado"] = True
            # Un piso fijado a mano se ve siempre: para eso se fija. Aunque un
            # escaneo lo diera por retirado (o no llegara a comprobar su
            # portal), sigue en la lista para quien abra el enlace público.
            hallada["activo"] = True
            encontrados += 1
            continue

        municipio = normaliza_municipio(fij.get("municipio"))
        uid = uid_de(f"fijado:{portal}:{ident or fij.get('url')}")
        extras = {k: (k in (fij.get("extras") or [])) for k in cfg.EXTRAS}
        ficha = {
            "id": uid,
            "titulo": fij.get("titulo") or "Piso fijado por Albert",
            "precio": fij.get("precio"),
            "m2": fij.get("m2"),
            "habitaciones": fij.get("habitaciones"),
            "banos": fij.get("banos"),
            "planta": None,
            "municipio": municipio,
            "minutos": cfg.MUNICIPIOS.get(municipio),
            "preferente": municipio in cfg.PREFERENTES,
            "zona": None,
            "tipo": "piso",
            "descripcion": fij.get("descripcion") or "",
            "foto": fij.get("foto"),
            "lat": None, "lon": None,
            "extras": extras,
            "enlaces": [{"portal": portal or "enlace", "url": fij["url"]}],
            "portales": [portal or "enlace"],
            "portal_ids": [f"{portal}:{ident or uid}"],
            "precio_m2": None,
            "first_seen": fij.get("desde") or hoy,
            "last_seen": hoy,
            "nuevo": False,
            "activo": True,
            "fijado": True,
            "fuera_de_criterios": bool(fij.get("precio") and fij["precio"] > cfg.PRECIO_MAX),
        }
        ficha["precio_m2"] = precio_m2(ficha)
        ficha["ideal"] = es_ideal(ficha)
        fichas.append(ficha)
        favoritos.add(uid)
        anadidos += 1

    marcas["favoritos"] = sorted(favoritos)
    return fichas, {"encontrados": encontrados, "anadidos": anadidos}


def procesa(brutos):
    """De anuncios en bruto a fichas limpias y deduplicadas.

    Devuelve (fichas, estadisticas_de_filtrado).
    """
    stats = {"total_bruto": len(brutos), "fuera_zona": 0, "no_piso": 0,
             "precio": 0, "raros": 0, "motivos_raros": {}}

    validos = []
    for a in brutos:
        a["municipio_norm"] = normaliza_municipio(a.get("municipio"))
        if not a["municipio_norm"] or cfg.MUNICIPIOS.get(a["municipio_norm"], 999) > cfg.MINUTOS_MAX:
            stats["fuera_zona"] += 1
            continue

        precio = a.get("precio")
        if not precio or precio > cfg.PRECIO_MAX or precio < cfg.PRECIO_MIN:
            stats["precio"] += 1
            continue

        if not es_vivienda_en_edificio(a):
            stats["no_piso"] += 1
            continue

        motivo = motivo_descarte(a)
        if motivo:
            stats["raros"] += 1
            stats["motivos_raros"][motivo] = stats["motivos_raros"].get(motivo, 0) + 1
            continue

        a["extras"] = detecta_extras(a)
        validos.append(a)

    fichas = []
    for grupo in agrupa(validos):
        f = fusiona(grupo)
        # El identificador cuelga de un anuncio concreto del grupo, no del
        # precio ni de los metros: así una estrella no se pierde porque una
        # agencia retoque el precio y cambie la forma de agrupar.
        f["id"] = uid_de(f["portal_ids"][0])
        f["precio_m2"] = precio_m2(f)
        f["ideal"] = es_ideal(f)
        f["portales"] = sorted({e["portal"] for e in f["enlaces"]})
        fichas.append(f)

    stats["fichas"] = len(fichas)
    stats["duplicados_fundidos"] = len(validos) - len(fichas)
    return fichas, stats


def carga_alias():
    """Identificadores absorbidos por el deduplicado -> el que los sustituye."""
    return dict((carga_json(cfg.FICHERO_ESTADO, {}) or {}).get("alias") or {})


def resuelve_marcas(marcas, alias):
    """Traduce las marcas cuyo piso se fundió con otro.

    Albert publica estrellas y favoritos por identificador. Si después el
    deduplicado funde ese anuncio con otro, la marca apuntaría a una ficha que
    ya no existe y desaparecería de la web sin avisar. Aquí se reencaminan.
    """
    cambiadas = 0
    for clave in ("destacados", "favoritos"):
        salida, vistos = [], set()
        for ident in marcas.get(clave) or []:
            destino, saltos = ident, 0
            while destino in alias and saltos < 10:   # cadenas de absorciones
                destino, saltos = alias[destino], saltos + 1
            if destino != ident:
                cambiadas += 1
            if destino not in vistos:
                vistos.add(destino)
                salida.append(destino)
        marcas[clave] = sorted(salida)
    return cambiadas


def consolida(fichas, marcas, hoy, alias=None):
    """Segunda pasada de deduplicado, ya sobre el conjunto completo.

    agrupa() solo compara los anuncios del escaneo en curso. Como el Mac y
    GitHub llegan a portales distintos, el mismo piso acaba como dos fichas:
    una traída hoy por Idealista y otra guardada ayer por Habitaclia. Aquí se
    juntan, y las estrellas y favoritos de la ficha absorbida se trasladan a la
    que sobrevive para que no se pierda ninguna marca.
    """
    alias = {} if alias is None else alias
    activos = [f for f in fichas if f.get("activo")]
    for f in activos:
        f["municipio_norm"] = f.get("municipio")

    destacados = set(marcas.get("destacados") or ())
    favoritos = set(marcas.get("favoritos") or ())
    absorbidas, fundidas = set(), 0

    for grupo in agrupa(activos):
        if len(grupo) < 2:
            continue
        # Sobrevive la que lleve marcas; si no, la más antigua.
        marcada = [f for f in grupo if f["id"] in destacados or f["id"] in favoritos]
        grupo.sort(key=lambda f: (f["id"] not in {m["id"] for m in marcada},
                                  f.get("first_seen") or "9999"))
        principal, resto = grupo[0], grupo[1:]

        for otra in resto:
            ya = {e["portal"] for e in principal["enlaces"]}
            principal["enlaces"] += [e for e in otra.get("enlaces", [])
                                     if e["portal"] not in ya]
            principal["portal_ids"] = sorted(set(principal.get("portal_ids", []))
                                             | set(otra.get("portal_ids", [])))
            for campo in ("m2", "habitaciones", "banos", "planta", "zona",
                          "lat", "lon", "foto", "descripcion"):
                if principal.get(campo) in (None, "", 0) and otra.get(campo):
                    principal[campo] = otra[campo]
            for k, v in (otra.get("extras") or {}).items():
                principal["extras"][k] = principal["extras"].get(k, False) or v
            if otra.get("fijado"):
                principal["fijado"] = True
            if otra.get("first_seen") and otra["first_seen"] < (principal.get("first_seen") or "9999"):
                principal["first_seen"] = otra["first_seen"]
            # La marca viaja con el piso, no con el anuncio que la llevaba.
            if otra["id"] in destacados:
                destacados.discard(otra["id"]); destacados.add(principal["id"])
            if otra["id"] in favoritos:
                favoritos.discard(otra["id"]); favoritos.add(principal["id"])
            absorbidas.add(otra["id"])
            # Se anota para siempre: una marca publicada mañana contra el
            # identificador viejo seguirá encontrando su piso.
            alias[otra["id"]] = principal["id"]
            fundidas += 1

        principal["portales"] = sorted({e["portal"] for e in principal["enlaces"]})
        principal["precio_m2"] = precio_m2(principal)
        principal["ideal"] = es_ideal(principal)
        principal["nuevo"] = principal.get("first_seen") == hoy

    if absorbidas:
        marcas["destacados"] = sorted(destacados)
        marcas["favoritos"] = sorted(favoritos)

    return [f for f in fichas if f["id"] not in absorbidas], fundidas


def aplica_historico(fichas, hoy, portales_cubiertos):
    """Asigna first_seen, marca novedades y conserva las fichas desaparecidas.

    `portales_cubiertos` son los portales que esta ejecución ha conseguido
    consultar de verdad. Es la pieza que permite combinar escaneos parciales:
    si hoy solo hemos podido mirar Habitaclia, un piso que solo estaba en
    Idealista NO se marca como retirado, porque no tenemos ninguna prueba
    sobre él. Sin esto, el escaneo del Mac y el de GitHub se borrarían los
    hallazgos mutuamente.
    """
    portales_cubiertos = set(portales_cubiertos or ())
    estado = carga_json(cfg.FICHERO_ESTADO, {"anuncios": {}})
    anuncios = estado.get("anuncios", {})

    # índice portal_id -> uid histórico, para no perder la fecha si cambia la clave
    indice = {}
    for uid, viejo in anuncios.items():
        for pid in viejo.get("portal_ids", []):
            indice[pid] = uid

    vistos_hoy = set()
    for f in fichas:
        uid = f["id"]
        anterior = anuncios.get(uid)
        if anterior is None:
            for pid in f["portal_ids"]:
                if pid in indice:
                    anterior = anuncios.get(indice[pid])
                    # Adoptamos el identificador que ya tenía en el histórico:
                    # las estrellas y los favoritos se guardan por ese
                    # identificador y no deben perderse si cambia la agrupación.
                    if anterior:
                        anuncios.pop(uid, None)
                        uid = indice[pid]
                        f["id"] = uid
                    break
        # Los enlaces de portales que hoy no hemos mirado se conservan: si
        # ayer Habitaclia encontró este piso y hoy solo hemos podido ver
        # Idealista, la ficha debe seguir enseñando los dos.
        if anterior:
            ya = {e["portal"] for e in f["enlaces"]}
            f["enlaces"] = f["enlaces"] + [
                e for e in anterior.get("enlaces", [])
                if e["portal"] not in ya and e["portal"] not in portales_cubiertos]
            f["portales"] = sorted({e["portal"] for e in f["enlaces"]})
            f["portal_ids"] = sorted(set(f["portal_ids"]) | set(anterior.get("portal_ids", [])))

        f["first_seen"] = (anterior or {}).get("first_seen", hoy)
        f["nuevo"] = f["first_seen"] == hoy
        f["last_seen"] = hoy
        f["activo"] = True
        # conserva la posición histórica de precio para detectar bajadas
        precio_ant = (anterior or {}).get("precio")
        f["precio_anterior"] = precio_ant if precio_ant and precio_ant != f["precio"] else None
        anuncios[uid] = f
        vistos_hoy.add(uid)

    # Las que ya no aparecen se conservan. Solo se dan por retiradas si hoy
    # hemos consultado TODOS los portales donde estaban: si alguna de sus
    # fuentes se quedó sin mirar, se deja tal cual estaba.
    resultado = list(fichas)
    for uid, viejo in anuncios.items():
        if uid in vistos_hoy:
            continue
        fuentes = set(viejo.get("portales") or ())
        if not fuentes or not fuentes <= portales_cubiertos:
            viejo["nuevo"] = False
            resultado.append(viejo)
            continue
        viejo["activo"] = False
        viejo["nuevo"] = False
        resultado.append(viejo)

    estado["anuncios"] = anuncios
    estado["ultima_actualizacion"] = datetime.now().isoformat(timespec="seconds")
    guarda_json(cfg.FICHERO_ESTADO, estado)
    return resultado


def guarda_estado(fichas, alias=None):
    """Reescribe el histórico. Se llama después de consolidar, para que las
    fichas absorbidas no vuelvan a aparecer mañana."""
    for f in fichas:
        f.pop("_via", None)
        f.pop("municipio_norm", None)
    guarda_json(cfg.FICHERO_ESTADO, {
        "anuncios": {f["id"]: f for f in fichas},
        "alias": alias or {},
        "ultima_actualizacion": datetime.now().isoformat(timespec="seconds"),
    })
