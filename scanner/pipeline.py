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

_CANON = {sin_acentos(m): m for m in cfg.MUNICIPIOS}
_CANON.update({sin_acentos(k): v for k, v in cfg.ALIAS_MUNICIPIOS.items()})


def normaliza_municipio(nombre):
    """Devuelve el nombre canónico del municipio, o None si cae fuera de zona."""
    if not nombre:
        return None
    limpio = sin_acentos(nombre).strip()
    limpio = re.sub(r"\s*\(.*?\)\s*", "", limpio).strip()
    if limpio in _CANON:
        return _CANON[limpio]
    # "l'estartit - torroella", "palamos centre", etc.
    for trozo in re.split(r"[-–/,]", limpio):
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

def clave_dedupe(a):
    """Misma vivienda publicada en varios portales -> misma clave."""
    mun = sin_acentos(a.get("municipio_norm") or "")
    precio = a.get("precio") or 0
    m2 = a.get("m2")
    hab = a.get("habitaciones")
    if m2:
        return f"{mun}|{precio}|{m2}"
    if hab is not None:
        return f"{mun}|{precio}|h{hab}"
    return f"{mun}|{precio}|{sin_acentos(a.get('titulo'))[:40]}"


def uid_de(clave):
    return hashlib.sha1(clave.encode("utf-8")).hexdigest()[:12]


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

    grupos = {}
    for a in validos:
        grupos.setdefault(clave_dedupe(a), []).append(a)

    fichas = []
    for clave, grupo in grupos.items():
        f = fusiona(grupo)
        f["id"] = uid_de(clave)
        f["clave"] = clave
        f["precio_m2"] = precio_m2(f)
        f["portales"] = sorted({e["portal"] for e in f["enlaces"]})
        fichas.append(f)

    stats["fichas"] = len(fichas)
    stats["duplicados_fundidos"] = len(validos) - len(fichas)
    return fichas, stats


def aplica_historico(fichas, hoy):
    """Asigna first_seen, marca novedades y conserva las fichas ya desaparecidas."""
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
                    break
        f["first_seen"] = (anterior or {}).get("first_seen", hoy)
        f["nuevo"] = f["first_seen"] == hoy
        f["last_seen"] = hoy
        f["activo"] = True
        # conserva la posición histórica de precio para detectar bajadas
        precio_ant = (anterior or {}).get("precio")
        f["precio_anterior"] = precio_ant if precio_ant and precio_ant != f["precio"] else None
        anuncios[uid] = f
        vistos_hoy.add(uid)

    # las que ya no aparecen se conservan, marcadas como no activas
    resultado = list(fichas)
    for uid, viejo in anuncios.items():
        if uid in vistos_hoy:
            continue
        viejo["activo"] = False
        viejo["nuevo"] = False
        resultado.append(viejo)

    estado["anuncios"] = anuncios
    estado["ultima_actualizacion"] = datetime.now().isoformat(timespec="seconds")
    guarda_json(cfg.FICHERO_ESTADO, estado)
    return resultado
