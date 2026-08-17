"""Comprueba que dos escaneos parciales se combinan en vez de pisarse.

Es el caso real del proyecto: GitHub solo consigue leer pisos.com y Habitaclia,
mientras que el Mac de Albert sí puede con Idealista, Fotocasa y Milanuncios.
Ninguno de los dos debe retirar los hallazgos del otro.

    ./.venv/bin/python tests/test_fusion.py
"""

import json
import pathlib
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scanner import config as cfg          # noqa: E402
from scanner import pipeline as pl         # noqa: E402

PRUEBAS = []


def comprueba(nombre, condicion, detalle=""):
    PRUEBAS.append((nombre, bool(condicion), str(detalle)[:70]))


def ficha(uid, portal, precio, m2=70):
    """Una ficha mínima tal y como la deja procesa()."""
    return {
        "id": uid, "clave": f"c-{uid}", "precio": precio, "m2": m2,
        "titulo": f"Piso {uid}", "municipio": "Palafrugell", "minutos": 5,
        "habitaciones": 2, "banos": 1, "extras": {}, "tipo": "piso",
        "enlaces": [{"portal": portal, "url": f"https://{portal}.example/{uid}"}],
        "portales": [portal],
        "portal_ids": [f"{portal}:{uid}"],
    }


def con_estado_temporal(fn):
    with tempfile.TemporaryDirectory() as tmp:
        original = cfg.FICHERO_ESTADO
        cfg.FICHERO_ESTADO = pathlib.Path(tmp) / "listings.json"
        try:
            return fn()
        finally:
            cfg.FICHERO_ESTADO = original


def escenario():
    # --- Día 1: escaneo completo, cada piso lo ve un portal distinto -------
    dia1 = [ficha("aaa", "idealista", 100_000),
            ficha("bbb", "habitaclia", 110_000),
            ficha("ccc", "pisos", 120_000)]
    pl.aplica_historico(dia1, "2026-08-17", ["idealista", "habitaclia", "pisos"])

    # --- Día 2: GitHub, bloqueado en Idealista -----------------------------
    # Solo reaparecen los de habitaclia y pisos. El de Idealista no se ha
    # podido comprobar: no debe darse por retirado.
    dia2 = [ficha("bbb", "habitaclia", 110_000),
            ficha("ccc", "pisos", 120_000)]
    r2 = {f["id"]: f for f in pl.aplica_historico(dia2, "2026-08-18",
                                                  ["habitaclia", "pisos"])}

    comprueba("El piso solo visto en Idealista sobrevive al escaneo de GitHub",
              r2["aaa"]["activo"] is True,
              f"activo={r2['aaa']['activo']}")
    comprueba("Y conserva su enlace de Idealista",
              [e["portal"] for e in r2["aaa"]["enlaces"]] == ["idealista"],
              r2["aaa"]["enlaces"])
    comprueba("Y deja de contar como novedad", r2["aaa"]["nuevo"] is False)

    # --- Día 3: GitHub otra vez, y ahora Habitaclia ya no lo publica -------
    dia3 = [ficha("ccc", "pisos", 120_000)]
    r3 = {f["id"]: f for f in pl.aplica_historico(dia3, "2026-08-19",
                                                  ["habitaclia", "pisos"])}

    comprueba("El de Habitaclia sí se retira, porque sí lo hemos mirado",
              r3["bbb"]["activo"] is False,
              f"activo={r3['bbb']['activo']}")
    comprueba("El de Idealista sigue intacto",
              r3["aaa"]["activo"] is True)

    # --- Día 4: el Mac, que sí llega a Idealista, encuentra el mismo piso
    #            que Habitaclia ya conocía. Deben fundirse, no duplicarse. ---
    mismo = ficha("bbb", "idealista", 110_000)
    r4 = {f["id"]: f for f in pl.aplica_historico([mismo], "2026-08-20",
                                                  ["idealista", "fotocasa"])}

    portales = sorted(r4["bbb"]["portales"])
    comprueba("Un piso hallado por dos portales distintos acumula ambos enlaces",
              portales == ["habitaclia", "idealista"], portales)
    comprueba("Vuelve a estar activo al reaparecer",
              r4["bbb"]["activo"] is True)
    comprueba("No se cuenta como nuevo: ya se conocía del día 1",
              r4["bbb"]["nuevo"] is False and r4["bbb"]["first_seen"] == "2026-08-17",
              r4["bbb"]["first_seen"])
    comprueba("El de pisos.com no se retira: hoy no se ha mirado pisos.com",
              r4["ccc"]["activo"] is True)

    # --- Bajada de precio ---------------------------------------------------
    barato = ficha("ccc", "pisos", 99_000)
    r5 = {f["id"]: f for f in pl.aplica_historico([barato], "2026-08-21", ["pisos"])}
    comprueba("Se detecta la bajada de precio",
              r5["ccc"]["precio_anterior"] == 120_000,
              f"antes {r5['ccc']['precio_anterior']} ahora {r5['ccc']['precio']}")


def anuncio(portal, titulo, precio, m2=None, hab=None, banos=None,
            planta=None, lat=None, lon=None, municipio="Palafrugell"):
    return {"portal": portal, "id_portal": f"{portal}-{precio}-{m2}", "titulo": titulo,
            "precio": precio, "m2": m2, "habitaciones": hab, "banos": banos,
            "planta": planta, "lat": lat, "lon": lon, "zona": None,
            "municipio_norm": municipio}


def son_el_mismo(a, b):
    a["_via"], b["_via"] = pl.via_de(a), pl.via_de(b)
    return pl.mismo_piso(a, b)


def dedupe():
    # --- lo que SÍ debe fundirse ------------------------------------------
    comprueba("Dos agencias, mismo piso, 1.000 € de diferencia",
              son_el_mismo(
                  anuncio("idealista", "Piso en Carrer dels Plans, 19", 149_000, 84, 3, 2),
                  anuncio("habitaclia", "Piso en Carrer dels plans 19", 150_000, 84, 3, 2)))

    comprueba("Misma calle y precio, 1 m² de diferencia (construida vs útil)",
              son_el_mismo(
                  anuncio("habitaclia", "Piso en Carrer dels plans 19", 150_000, 84, 3, 2),
                  anuncio("pisos", "Piso en calle Plans 19 ¡oportunidad!", 150_000, 85, 3, 2)))

    comprueba("Mismos metros y mismo precio, aunque no se lea la calle",
              son_el_mismo(
                  anuncio("habitaclia", "Apartamento en Torroella. Estudio loft", 115_900, 49, 1, 1),
                  anuncio("pisos", "Apartamento en Torroella. Estudio loft", 115_900, 49, 1, 1)))

    comprueba("Mismo edificio por coordenadas, mismos metros y habitaciones",
              son_el_mismo(
                  anuncio("fotocasa", "Piso en Centre", 130_000, 65, 2, 1,
                          lat=41.917400, lon=3.163200),
                  anuncio("pisos", "Piso reformado con parking", 133_000, 66, 2, 1,
                          lat=41.917600, lon=3.163300)))

    # --- lo que NO debe fundirse ------------------------------------------
    comprueba("NO funde 2 habitaciones con 4 en la misma calle",
              not son_el_mismo(
                  anuncio("habitaclia", "Piso en calle Marçal de la Trinxeria", 134_000, 78, 2, 2),
                  anuncio("habitaclia", "Piso en calle Marçal de la Trinxeria", 140_000, 80, 4, 2)))

    comprueba("NO funde 71 m² con 96 m² aunque coincidan calle, número y precio",
              not son_el_mismo(
                  anuncio("habitaclia", "Piso en Camí dels plans 29a", 150_000, 96, 3, 2),
                  anuncio("habitaclia", "Piso en Camí dels plans 29a", 150_000, 71, 3, 2)))

    comprueba("NO funde calles distintas con el mismo precio y metros",
              not son_el_mismo(
                  anuncio("habitaclia", "Piso en Carrer de Barcelona", 125_000, 78, 3, 1),
                  anuncio("habitaclia", "Piso en Carrer de Lleida", 125_000, 78, 3, 1)))

    comprueba("NO funde dos portales distintos de la misma calle",
              not son_el_mismo(
                  anuncio("habitaclia", "Piso en Carrer dels plans 19", 150_000, 84, 3, 2),
                  anuncio("habitaclia", "Piso en Carrer dels plans 29", 150_000, 84, 3, 2)))

    comprueba("NO funde plantas distintas del mismo edificio",
              not son_el_mismo(
                  anuncio("idealista", "Piso en Carrer dels plans 19", 150_000, 84, 3, 2,
                          planta="1ª planta"),
                  anuncio("idealista", "Piso en Carrer dels plans 19", 150_000, 84, 3, 2,
                          planta="Bajo")))

    comprueba("NO funde pisos de municipios distintos",
              len(pl.agrupa([
                  anuncio("habitaclia", "Piso en Carrer Major 4", 120_000, 70, 2, 1,
                          municipio="Palafrugell"),
                  anuncio("pisos", "Piso en Carrer Major 4", 120_000, 70, 2, 1,
                          municipio="Palamós"),
              ])) == 2)

    # --- la calle se extrae bien -----------------------------------------
    for titulo, esperado in [
        ("Piso en Carrer dels Plans, 19, Palafrugell", ("plans", "19")),
        ("Dúplex en Carrer del Bruc", ("bruc", None)),
        ("Piso en Avinguda de garcía lorca 2", ("garcia lorca", "2")),
        ("Planta baja en Camí dels plans 29a", ("plans", "29")),
        ("Piso en La Bisbal d'Empordà", (None, None)),
    ]:
        obtenido = pl.via_de({"titulo": titulo})
        comprueba(f"Vía de {titulo[:34]!r}", obtenido == esperado, f"{obtenido}")


def fijados():
    """Los favoritos que Albert fija a mano por URL."""
    casos = [
        ("https://www.idealista.com/inmueble/109987514/", "idealista", "109987514"),
        ("https://www.fotocasa.es/es/comprar/vivienda/palafrugell/no-amueblado/186695079/d",
         "fotocasa", "186695079"),
        ("https://www.habitaclia.com/comprar-apartamento-piso_reformado_con_parking"
         "_piverd_vila_seca_bruguerol-palafrugell-i53343000000196.htm",
         "habitaclia", "53343000000196"),
        ("https://www.pisos.com/comprar/piso-palafrugell_poble17200-66749195905_500582/",
         "pisos", "66749195905"),
    ]
    for url, portal_esperado, id_esperado in casos:
        portal, ident = pl.huella_url(url)
        comprueba(f"Identifica el anuncio de {portal_esperado}",
                  portal == portal_esperado and ident == id_esperado,
                  f"{portal}/{ident}")

    # El fallo que había: 17200 es el código postal de Palafrugell y aparece
    # en muchísimas URLs de pisos.com, así que emparejaba anuncios distintos.
    _, a = pl.huella_url("https://www.pisos.com/comprar/piso-palafrugell_poble17200-66749195905_500582/")
    _, b = pl.huella_url("https://www.pisos.com/comprar/piso-palafrugell_poble17200-11111111111_500582/")
    comprueba("Dos anuncios de pisos.com del mismo código postal no se confunden", a != b,
              f"{a} vs {b}")

    # Un piso fijado se ve siempre, aunque el escaneo lo diera por retirado.
    fichas = [{
        "id": "zzz", "activo": False, "precio": 130_000, "m2": 65,
        "enlaces": [{"portal": "idealista", "url": "https://www.idealista.com/inmueble/109987514/"}],
        "portales": ["idealista"], "portal_ids": ["idealista:109987514"],
    }]
    marcas = {"favoritos": [], "destacados": [], "notas": {}}
    original = cfg.FICHERO_FIJADOS
    import tempfile, pathlib as _p
    with tempfile.TemporaryDirectory() as tmp:
        ruta = _p.Path(tmp) / "fijados.json"
        ruta.write_text(json.dumps([
            {"url": "https://www.idealista.com/inmueble/109987514/", "precio": 130_000,
             "m2": 65, "municipio": "Palafrugell", "titulo": "Fijado"},
            {"url": "https://www.fotocasa.es/es/comprar/vivienda/palafrugell/x/999888777/d",
             "precio": 175_000, "m2": 61, "municipio": "Palafrugell", "titulo": "No hallado"},
        ]), encoding="utf-8")
        cfg.FICHERO_FIJADOS = ruta
        try:
            resultado, res = pl.aplica_fijados(fichas, marcas, "2026-08-17")
        finally:
            cfg.FICHERO_FIJADOS = original

    comprueba("Reconoce el fijado que sí estaba en el escaneo", res["encontrados"] == 1, res)
    comprueba("Añade el fijado que no aparecía", res["anadidos"] == 1, res)
    comprueba("Un fijado dado por retirado vuelve a estar visible",
              resultado[0]["activo"] is True and resultado[0]["fijado"] is True)
    comprueba("Los dos quedan como favoritos de Albert", len(marcas["favoritos"]) == 2,
              marcas["favoritos"])
    anadido = resultado[-1]
    comprueba("El que se sale del presupuesto queda avisado",
              anadido["fuera_de_criterios"] is True and anadido["precio"] == 175_000)
    comprueba("Y con su municipio y minutos resueltos",
              anadido["municipio"] == "Palafrugell" and anadido["minutos"] == 5,
              f"{anadido['municipio']} / {anadido['minutos']} min")


con_estado_temporal(escenario)
dedupe()
fijados()

print()
ok = True
for nombre, paso, detalle in PRUEBAS:
    print(f"  {'✓' if paso else '✗'} {nombre:62} {detalle}")
    ok = ok and paso
print(f"\n  {sum(1 for _, p, _ in PRUEBAS if p)}/{len(PRUEBAS)} pruebas correctas\n")
sys.exit(0 if ok else 1)
