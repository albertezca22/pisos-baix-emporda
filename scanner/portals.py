"""Escrapers de los cinco portales.

Cada función devuelve una lista de anuncios en bruto con una forma común y
NUNCA lanza una excepción hacia arriba: si un portal falla o corta el acceso,
devuelve lo que haya conseguido y deja constancia en el informe. Así un mal
día de Habitaclia no tumba el escaneo entero.
"""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass, field

from bs4 import BeautifulSoup
from curl_cffi import requests as cr

from . import config as cfg

# Perfiles TLS que sí superan los filtros anti-bot de Idealista.
# Chrome está deliberadamente fuera: devuelve 403.
PERFILES = ["safari17_0", "firefox", "safari15_5"]

# curl_cffi ya envía las cabeceras exactamente como las manda el navegador que
# imitamos. Añadir las nuestras delata la petición: Milanuncios sirve el muro
# anti-bot en cuanto detecta un Accept o un Accept-Language que no encaja con
# el perfil TLS, así que a ese portal no le mandamos ninguna.
CABECERAS = {"Accept-Language": "es-ES,es;q=0.9,ca;q=0.8,en;q=0.7"}
CABECERAS_POR_PORTAL = {"milanuncios": {}}

MUROS = ("pardon our interruption", "access denied", "are you a human",
         "request unsuccessful", "captcha")


@dataclass
class Informe:
    """Qué ha pasado en cada portal, para poder enseñarlo en la web."""
    por_portal: dict = field(default_factory=dict)

    def anota(self, portal, anuncios=0, paginas=0, error=None, bloqueado=False):
        d = self.por_portal.setdefault(
            portal, {"anuncios": 0, "paginas": 0, "errores": [], "bloqueado": False})
        d["anuncios"] += anuncios
        d["paginas"] += paginas
        d["bloqueado"] = d["bloqueado"] or bloqueado
        if error:
            d["errores"].append(str(error)[:200])


def _pausa(rango):
    time.sleep(random.uniform(*rango))


class Reloj:
    """Presupuesto de tiempo de un portal. Al agotarse, se recoge y se publica."""

    def __init__(self, portal):
        self.portal = portal
        self.inicio = time.monotonic()
        self.tope = cfg.PRESUPUESTO_SEGUNDOS.get(portal, 300)

    def agotado(self, informe):
        if time.monotonic() - self.inicio < self.tope:
            return False
        informe.anota(self.portal,
                      error=f"tiempo agotado tras {self.tope}s; se publica lo obtenido")
        return True


def pedir(url, portal, informe, intentos=3):
    """GET con reintentos, rotación de perfil TLS y detección de muro anti-bot.

    Devuelve el HTML o None. Nunca lanza.
    """
    cabeceras = CABECERAS_POR_PORTAL.get(portal, CABECERAS)
    for intento in range(intentos):
        perfil = PERFILES[intento % len(PERFILES)]
        try:
            r = cr.get(url, impersonate=perfil, timeout=cfg.TIMEOUT, headers=cabeceras)
        except Exception as e:  # red, TLS, timeout...
            if intento == intentos - 1:
                informe.anota(portal, error=f"{type(e).__name__}: {e}")
                return None
            time.sleep(2 * (intento + 1))
            continue

        if r.status_code == 200:
            bajo = r.text[:4000].lower()
            if any(m in bajo for m in MUROS):
                informe.anota(portal, bloqueado=True)
                time.sleep(5 * (intento + 1))
                continue
            return r.text
        if r.status_code in (403, 429):
            informe.anota(portal, bloqueado=True)
            time.sleep(4 * (intento + 1))
            continue
        if r.status_code == 404:
            return None
        time.sleep(2 * (intento + 1))

    return None


# --- utilidades de parseo --------------------------------------------------

RE_PRECIO = re.compile(r"([\d][\d.\s]{2,12})\s*€(?!\s*/)")
RE_M2 = re.compile(r"(\d[\d.]*)\s*m\s*²|(\d[\d.]*)\s*m\s*2\b")
RE_HAB = re.compile(r"(\d+)\s*(?:hab\b|hab\.|habitacion|habitación|habitacione|habitaciones|habs|dorm)", re.I)
RE_BANO = re.compile(r"(\d+)\s*(?:baño|banos|baños|bany|banys|bao)", re.I)
RE_PLANTA = re.compile(r"(bajo|entresuelo|principal|ático|atico|\d+\s*ª?\s*planta)", re.I)


def _num(txt):
    if txt is None:
        return None
    t = re.sub(r"[^\d]", "", str(txt))
    return int(t) if t else None


def precio_de(texto):
    """Primer importe plausible de la tarjeta: es el precio de venta.

    El patrón ya descarta los €/m², y el rango deja fuera cifras absurdas.
    """
    for m in RE_PRECIO.finditer(texto):
        v = _num(m.group(1))
        if v and 10_000 <= v <= 5_000_000:
            return v
    return None


def m2_de(texto):
    m = RE_M2.search(texto)
    if not m:
        return None
    v = _num(m.group(1) or m.group(2))
    return v if v and 10 <= v <= 1000 else None


def hab_de(texto):
    m = RE_HAB.search(texto)
    v = _num(m.group(1)) if m else None
    return v if v is not None and 0 <= v <= 12 else None


def banos_de(texto):
    m = RE_BANO.search(texto)
    v = _num(m.group(1)) if m else None
    return v if v is not None and 0 <= v <= 8 else None


def planta_de(texto):
    m = RE_PLANTA.search(texto)
    return m.group(1).strip() if m else None


def tipo_de(texto):
    t = texto.lower()
    for clave, etiqueta in [
        ("ático", "ático"), ("atico", "ático"), ("àtic", "ático"),
        ("dúplex", "dúplex"), ("duplex", "dúplex"),
        ("estudio", "estudio"), ("estudi ", "estudio"),
        ("apartamento", "apartamento"), ("apartament", "apartamento"),
        ("loft", "loft"),
        ("planta baja", "planta baja"), ("bajo con", "planta baja"),
        ("piso", "piso"), ("pis ", "piso"),
    ]:
        if clave in t:
            return etiqueta
    return None


def _abs(base, href):
    if not href:
        return None
    if href.startswith("http"):
        return href
    return base.rstrip("/") + "/" + href.lstrip("/")


# --- Idealista -------------------------------------------------------------

def idealista(informe):
    """Barre la comarca entera. Fuente principal: ~218 anuncios bajo 160k."""
    out = []
    base = ("https://www.idealista.com/venta-viviendas/girona/baix-emporda/"
            f"con-precio-hasta_{cfg.PRECIO_MAX}/")
    vistos = set()
    reloj = Reloj("idealista")

    for pagina in range(1, cfg.MAX_PAGINAS + 1):
        if reloj.agotado(informe):
            break
        url = base if pagina == 1 else f"{base}pagina-{pagina}.htm"
        html = pedir(url, "idealista", informe)
        if not html:
            break
        sopa = BeautifulSoup(html, "lxml")
        tarjetas = sopa.select("article.item")
        if not tarjetas:
            break

        nuevos = 0
        for art in tarjetas:
            idp = art.get("data-element-id")
            if not idp or idp in vistos:
                continue
            vistos.add(idp)

            enlace = art.select_one("a.item-link")
            if not enlace:
                continue
            titulo = enlace.get("title") or enlace.get_text(" ", strip=True)
            texto = art.get_text(" ", strip=True)

            desc_el = art.select_one(".item-description")
            desc = desc_el.get_text(" ", strip=True) if desc_el else ""

            precio_el = art.select_one(".item-price")
            precio = _num(precio_el.get_text()) if precio_el else precio_de(texto)

            # Municipio: último tramo del título ("Piso en calle X, Zona, Palafrugell")
            partes = [p.strip() for p in titulo.split(",") if p.strip()]
            municipio = partes[-1] if len(partes) > 1 else None

            foto = None
            img = art.select_one("picture img, img")
            if img:
                foto = (img.get("data-ondemand-img") or img.get("data-src")
                        or img.get("src"))

            out.append({
                "portal": "idealista",
                "id_portal": idp,
                "url": _abs("https://www.idealista.com", enlace.get("href")),
                "titulo": titulo,
                "precio": precio,
                "m2": m2_de(texto),
                "habitaciones": hab_de(texto),
                "banos": banos_de(texto),
                "planta": planta_de(texto),
                "municipio": municipio,
                "descripcion": desc,
                "foto": foto,
                "tipo": tipo_de(titulo),
                "texto_bruto": texto,
            })
            nuevos += 1

        informe.anota("idealista", anuncios=nuevos, paginas=1)
        if nuevos == 0:
            break
        _pausa(cfg.PORTALES["idealista"]["pausa"])

    return out


# --- Fotocasa --------------------------------------------------------------

def _fotocasa_buscar_lista(obj):
    """Localiza la lista de anuncios dentro del JSON embebido."""
    if isinstance(obj, dict):
        r = obj.get("realEstates")
        if isinstance(r, list) and r and isinstance(r[0], dict) and "price" in r[0]:
            return r
        res = obj.get("result")
        if isinstance(res, list) and res and isinstance(res[0], dict) and "price" in res[0]:
            return res
        for v in obj.values():
            hallado = _fotocasa_buscar_lista(v)
            if hallado:
                return hallado
    elif isinstance(obj, list):
        for v in obj[:10]:
            hallado = _fotocasa_buscar_lista(v)
            if hallado:
                return hallado
    return None


# En Fotocasa "rooms", "bathrooms", "surface" y "floor" llevan el valor real;
# el resto de claves son booleanas: si aparecen, la vivienda tiene ese extra.
EXTRAS_FOTOCASA = {
    "parking": "parking", "garage": "parking",
    "terrace": "terraza",
    "balcony": "balcon",
    "elevator": "ascensor",
    "swimming_pool": "piscina", "community_pool": "piscina",
    "private_garden": "jardin", "yard": "jardin", "community_garden": "jardin",
    "storage_room": "trastero",
    "air_conditioner": "aire",
    "heating": "calefaccion",
    "furnished": "amueblado",
    "DYN:HAS_VIEW_TO_BEACH": "vistas_mar", "DYN:IS_ON_SEAFRONT": "vistas_mar",
}

def _fotocasa_features(reg):
    """Devuelve (hab, baños, m², extras) leyendo el bloque de features.

    Ojo: "floor", "orientation" y "conservationStatus" guardan identificadores
    internos, no valores legibles, así que no se usan. La planta la aporta
    Idealista, que sí la publica como texto.
    """
    hab = banos = m2 = None
    extras = {}

    def procesa(clave, valor, prefijo=""):
        nonlocal hab, banos, m2
        k = f"{prefijo}{clave}"
        if clave == "rooms":
            hab = _num(valor)
        elif clave == "bathrooms":
            banos = _num(valor)
        elif clave == "surface":
            m2 = _num(valor)
        elif k in EXTRAS_FOTOCASA:
            extras[EXTRAS_FOTOCASA[k]] = True

    for f in reg.get("features") or []:
        if isinstance(f, dict):
            procesa(str(f.get("key") or ""), f.get("value"))
    for f in reg.get("dynamicFeatures") or []:
        clave = f.get("key") if isinstance(f, dict) else f
        procesa(str(clave or ""), True, prefijo="DYN:")

    return hab, banos, m2, extras


MAPA_TIPOS_FOTOCASA = {
    "Flat": "piso", "Penthouse": "ático", "Attic": "ático", "Duplex": "dúplex",
    "Studio": "estudio", "Study": "estudio", "Apartment": "apartamento",
    "Loft": "loft", "GroundFloor": "planta baja",
    "GroundFloorWithGarden": "planta baja",
    "House": "casa", "Chalet": "casa", "Villa": "casa", "TerracedHouse": "casa",
    "SemidetachedHouse": "casa", "DetachedHouse": "casa", "CountryHouse": "casa",
    "Rustic": "casa", "Land": "terreno", "Garage": "garaje",
    "Storage": "trastero", "Office": "oficina", "Premises": "local",
}


def fotocasa(informe):
    out = []
    base = ("https://www.fotocasa.es/es/comprar/viviendas/baix-emporda/"
            "todas-las-zonas/l")
    vistos = set()
    reloj = Reloj("fotocasa")

    for pagina in range(1, cfg.MAX_PAGINAS + 1):
        if reloj.agotado(informe):
            break
        url = (f"{base}?maxPrice={cfg.PRECIO_MAX}" if pagina == 1
               else f"{base}/{pagina}?maxPrice={cfg.PRECIO_MAX}")
        html = pedir(url, "fotocasa", informe)
        if not html:
            break
        sopa = BeautifulSoup(html, "lxml")
        script = sopa.find(id="__initial_props__")
        if not script or not script.string:
            informe.anota("fotocasa", error="sin __initial_props__")
            break
        try:
            datos = json.loads(script.string)
        except Exception as e:
            informe.anota("fotocasa", error=f"JSON ilegible: {e}")
            break

        lista = _fotocasa_buscar_lista(datos) or []
        nuevos = 0
        for reg in lista:
            idp = str(reg.get("id") or reg.get("realEstateAdId") or "")
            if not idp or idp in vistos:
                continue
            vistos.add(idp)

            dire = reg.get("address") or {}
            detalle = reg.get("detail")
            if isinstance(detalle, dict):
                detalle = detalle.get("es-ES") or next(iter(detalle.values()), None)

            multi = reg.get("multimedia") or []
            foto = None
            if isinstance(multi, list) and multi:
                primero = multi[0]
                foto = primero.get("src") if isinstance(primero, dict) else primero

            hab, banos, m2, extras_portal = _fotocasa_features(reg)
            subtipo = reg.get("buildingSubtype") or reg.get("buildingType")
            tipo_es = MAPA_TIPOS_FOTOCASA.get(subtipo, tipo_de(str(subtipo)))

            zona = dire.get("district") or dire.get("neighborhood")
            titulo = reg.get("promotionTitle") or " ".join(filter(None, [
                (tipo_es or "vivienda").capitalize(), "en",
                zona or dire.get("municipality") or "",
                f"· {dire.get('municipality')}" if zona and dire.get("municipality") else "",
            ])).strip()

            out.append({
                "portal": "fotocasa",
                "id_portal": idp,
                "url": _abs("https://www.fotocasa.es", detalle),
                "titulo": titulo,
                "precio": _num(reg.get("rawPrice") or reg.get("price")),
                "m2": m2,
                "habitaciones": hab,
                "banos": banos,
                "planta": None,
                "municipio": dire.get("municipality") or dire.get("city"),
                "zona": zona,
                "descripcion": reg.get("description") or "",
                "foto": foto,
                "lat": (reg.get("coordinates") or {}).get("latitude"),
                "lon": (reg.get("coordinates") or {}).get("longitude"),
                "tipo": tipo_es,
                "texto_bruto": "",
                "extras_portal": extras_portal,
                # El portal ya nos dice qué anuncios son "raros"
                "flags": {
                    "subasta": bool(reg.get("isAuctioned")),
                    "ocupado": bool(reg.get("isOccupied")),
                    "nuda_propiedad": bool(reg.get("isBareOwnership")),
                    "con_inquilinos": bool(reg.get("isRentedWithTenants")),
                },
            })
            nuevos += 1

        informe.anota("fotocasa", anuncios=nuevos, paginas=1)
        if nuevos == 0:
            break
        _pausa(cfg.PORTALES["fotocasa"]["pausa"])

    return out


# --- pisos.com -------------------------------------------------------------

def pisos(informe):
    # El tramo "hasta-N" sí filtra por precio aunque el título de la página no
    # cambie. Sin él, las primeras páginas vienen ordenadas por precio alto y
    # los pisos baratos quedan más allá del tope de páginas: los perderíamos.
    out = []
    base = f"https://www.pisos.com/venta/pisos-baix_emporda/hasta-{cfg.PRECIO_MAX}/"
    vistos = set()
    reloj = Reloj("pisos")

    for pagina in range(1, cfg.MAX_PAGINAS + 1):
        if reloj.agotado(informe):
            break
        url = base if pagina == 1 else f"{base}{pagina}/"
        html = pedir(url, "pisos", informe)
        if not html:
            break
        sopa = BeautifulSoup(html, "lxml")
        tarjetas = sopa.select("div.ad-preview__info")
        if not tarjetas:
            break

        nuevos = 0
        for info in tarjetas:
            # el enlace envuelve la tarjeta o está justo al lado
            enlace, nodo = None, info
            for _ in range(4):
                nodo = nodo.parent
                if nodo is None:
                    break
                enlace = nodo.find("a", href=True)
                if enlace:
                    break
            if not enlace:
                continue
            href = enlace["href"]
            if href in vistos:
                continue
            vistos.add(href)

            texto = info.get_text(" ", strip=True)
            titulo_el = info.select_one(".ad-preview__title")
            titulo = titulo_el.get_text(" ", strip=True) if titulo_el else texto[:90]

            loc_el = info.select_one(".ad-preview__subtitle, .p-sronly")
            loc = loc_el.get_text(" ", strip=True) if loc_el else ""
            # "Sant Antoni de Calonge (Calonge i Sant Antoni)" -> nos quedamos el paréntesis
            m = re.search(r"\(([^)]+)\)", loc)
            municipio = (m.group(1) if m else loc).strip() or None

            foto = None
            cont = info.parent
            if cont:
                img = cont.find("img")
                if img:
                    foto = img.get("data-src") or img.get("src")

            out.append({
                "portal": "pisos",
                "id_portal": re.sub(r"\D", "", href)[-14:] or href,
                "url": _abs("https://www.pisos.com", href),
                "titulo": titulo,
                "precio": precio_de(texto),
                "m2": m2_de(texto),
                "habitaciones": hab_de(texto),
                "banos": banos_de(texto),
                "planta": planta_de(texto),
                "municipio": municipio,
                "descripcion": texto,
                "foto": foto,
                "tipo": tipo_de(titulo),
                "texto_bruto": texto,
            })
            nuevos += 1

        informe.anota("pisos", anuncios=nuevos, paginas=1)
        if nuevos == 0:
            break
        _pausa(cfg.PORTALES["pisos"]["pausa"])

    return out


# --- Habitaclia (mejor esfuerzo, municipio a municipio) --------------------

def habitaclia(informe):
    out = []
    vistos = set()
    fallos = 0
    reloj = Reloj("habitaclia")
    for municipio in cfg.MUNICIPIOS_LENTOS:
        if reloj.agotado(informe):
            break
        slug = cfg.SLUGS_HABITACLIA.get(municipio)
        if not slug:
            continue
        url = f"https://www.habitaclia.com/viviendas-{slug}.htm?pmax={cfg.PRECIO_MAX}"
        html = pedir(url, "habitaclia", informe, intentos=2)
        if not html:
            fallos += 1
            if fallos >= cfg.FALLOS_SEGUIDOS_MAX:
                informe.anota("habitaclia",
                              error=f"abandonado tras {fallos} municipios seguidos sin respuesta")
                break
            _pausa(cfg.PORTALES["habitaclia"]["pausa"])
            continue
        fallos = 0

        sopa = BeautifulSoup(html, "lxml")
        tarjetas = sopa.select("article")
        nuevos = 0
        for art in tarjetas:
            enlace = art.find("a", href=True)
            if not enlace:
                continue
            href = enlace["href"]
            if "habitaclia.com" not in href and not href.startswith("/"):
                continue
            if href in vistos:
                continue
            vistos.add(href)

            texto = art.get_text(" ", strip=True)
            if "€" not in texto:
                continue

            titulo = (enlace.get("title") or "").strip()
            if not titulo:
                h = art.find(["h2", "h3"])
                titulo = h.get_text(" ", strip=True) if h else texto[:90]

            img = art.find("img")
            foto = (img.get("data-src") or img.get("src")) if img else None

            out.append({
                "portal": "habitaclia",
                "id_portal": re.sub(r"\D", "", href)[-14:] or href,
                "url": _abs("https://www.habitaclia.com", href),
                "titulo": titulo,
                "precio": precio_de(texto),
                "m2": m2_de(texto),
                "habitaciones": hab_de(texto),
                "banos": banos_de(texto),
                "planta": planta_de(texto),
                "municipio": municipio,
                "descripcion": texto,
                "foto": foto,
                "tipo": tipo_de(titulo + " " + texto[:120]),
                "texto_bruto": texto,
            })
            nuevos += 1

        informe.anota("habitaclia", anuncios=nuevos, paginas=1)
        _pausa(cfg.PORTALES["habitaclia"]["pausa"])

    return out


# --- Milanuncios (mejor esfuerzo, municipio a municipio) -------------------

RE_PROPS_MILANUNCIOS = re.compile(
    r'window\.__INITIAL_PROPS__\s*=\s*JSON\.parse\((".*?")\)\s*;', re.S)


def _milanuncios_json(html):
    """Saca la lista de anuncios del JSON que Milanuncios embebe en la página.

    Las tarjetas se pintan en el navegador, así que en el HTML no hay nada que
    raspar: los datos buenos están en window.__INITIAL_PROPS__.
    """
    m = RE_PROPS_MILANUNCIOS.search(html)
    if not m:
        return None
    try:
        datos = json.loads(json.loads(m.group(1)))
    except Exception:
        return None
    lista = (((datos.get("adListPagination") or {}).get("adList") or {}).get("ads"))
    return lista if isinstance(lista, list) else None


def milanuncios(informe):
    out = []
    vistos = set()
    fallos = 0
    reloj = Reloj("milanuncios")
    for municipio in cfg.MUNICIPIOS_LENTOS:
        if reloj.agotado(informe):
            break
        slug = cfg.SLUGS_MILANUNCIOS.get(municipio)
        if not slug:
            continue
        url = (f"https://www.milanuncios.com/venta-de-pisos-en-{slug}/"
               f"?desde=0&hasta={cfg.PRECIO_MAX}")
        html = pedir(url, "milanuncios", informe, intentos=2)
        if not html:
            fallos += 1
            if fallos >= cfg.FALLOS_SEGUIDOS_MAX:
                informe.anota("milanuncios",
                              error=f"abandonado tras {fallos} municipios seguidos sin respuesta")
                break
            _pausa(cfg.PORTALES["milanuncios"]["pausa"])
            continue
        fallos = 0

        anuncios = _milanuncios_json(html)
        if anuncios is None:
            informe.anota("milanuncios", error=f"{municipio}: sin JSON embebido")
            _pausa(cfg.PORTALES["milanuncios"]["pausa"])
            continue

        nuevos = 0
        for reg in anuncios:
            href = reg.get("url") or ""
            if not href or href in vistos:
                continue
            vistos.add(href)

            etiquetas = {}
            for t in reg.get("tags") or []:
                if isinstance(t, dict):
                    etiquetas[str(t.get("type", "")).lower()] = str(t.get("text", ""))

            imagenes = reg.get("images") or []
            foto = imagenes[0] if imagenes else None
            if foto and not str(foto).startswith("http"):
                foto = "https://" + str(foto)

            desc = reg.get("description") or ""
            tipo = tipo_de(f"{reg.get('seoTitle') or ''} {desc[:200]}") or "piso"
            ciudad = (reg.get("city") or {}).get("name") or municipio

            out.append({
                "portal": "milanuncios",
                "id_portal": str(reg.get("id") or re.sub(r"\D", "", href)[-14:]),
                "url": _abs("https://www.milanuncios.com", href),
                "titulo": reg.get("seoTitle") or f"{tipo.capitalize()} en {ciudad}",
                "precio": _num(((reg.get("price") or {}).get("cashPrice") or {}).get("value")),
                "m2": m2_de(etiquetas.get("metros cuadrados", "")),
                "habitaciones": _num(etiquetas.get("dormitorios")),
                "banos": _num(etiquetas.get("baños")),
                "planta": planta_de(desc),
                "municipio": ciudad,
                "descripcion": desc,
                "foto": foto,
                "tipo": tipo,
                "texto_bruto": " ".join(etiquetas.values()),
            })
            nuevos += 1

        informe.anota("milanuncios", anuncios=nuevos, paginas=1)
        _pausa(cfg.PORTALES["milanuncios"]["pausa"])

    return out


ESCRAPERS = {
    "idealista": idealista,
    "fotocasa": fotocasa,
    "pisos": pisos,
    "habitaclia": habitaclia,
    "milanuncios": milanuncios,
}
