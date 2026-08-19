"""Orquestador del escaneo diario.

    python -m scanner.run                    # escaneo completo
    python -m scanner.run --portales idealista,fotocasa
    python -m scanner.run --paginas 2        # prueba rápida

Escribe docs/data.json (lo que lee la web) y actualiza data/listings.json
(la memoria histórica que sabe qué es nuevo y qué no).
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config as cfg
from . import pipeline as pl
from . import portals


def ahora():
    return datetime.now(ZoneInfo(cfg.ZONA_HORARIA))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--portales", default="", help="lista separada por comas")
    ap.add_argument("--paginas", type=int, default=0, help="tope de páginas (pruebas)")
    ap.add_argument("--sin-escaneo", action="store_true",
                    help="no consulta los portales: solo rehace la web con lo "
                         "que ya hay guardado. Útil al cambiar criterios.")
    args = ap.parse_args()

    if args.paginas:
        cfg.MAX_PAGINAS = args.paginas

    seleccion = ([] if args.sin_escaneo
                 else [p.strip() for p in args.portales.split(",") if p.strip()]
                 or [p for p, c in cfg.PORTALES.items() if c["activo"]])
    seleccion.sort(key=lambda p: cfg.PORTALES.get(p, {}).get("prioridad", 99))

    t0 = ahora()
    hoy = t0.date().isoformat()
    informe = portals.Informe()
    brutos = []
    previo = pl.carga_json(cfg.FICHERO_SALIDA, {})

    if args.sin_escaneo:
        print("Sin escaneo: se rehace la web con lo que ya hay guardado.\n")

    # Registramos todos los portales de antemano. Si uno falla sin llegar a
    # anotar nada, se quedaba fuera del informe y desaparecía del pie de la
    # web: parecía que no se había consultado, en vez de salir en rojo.
    for nombre in seleccion:
        informe.anota(nombre)

    for nombre in seleccion:
        fn = portals.ESCRAPERS.get(nombre)
        if not fn:
            print(f"  ! portal desconocido: {nombre}", file=sys.stderr)
            continue
        print(f"→ {nombre} ...", flush=True)
        try:
            encontrados = fn(informe)
        except Exception as e:  # un portal jamás debe tumbar el escaneo
            informe.anota(nombre, error=f"excepción: {e}")
            traceback.print_exc()
            encontrados = []
        print(f"  {nombre}: {len(encontrados)} anuncios en bruto", flush=True)
        brutos.extend(encontrados)

    # Un portal solo "cuenta" si ha devuelto algo: si lo bloquearon, no
    # tenemos ninguna prueba de qué sigue publicado en él.
    cubiertos = sorted(p for p, d in informe.por_portal.items() if d["anuncios"] > 0)

    fichas, stats = pl.procesa(brutos)
    fichas = pl.aplica_historico(fichas, hoy, cubiertos)

    marcas = pl.carga_json(cfg.FICHERO_MARCAS,
                           {"destacados": [], "favoritos": [], "notas": {}})

    # Las marcas publicadas apuntan a un identificador. Si el piso se fundió
    # con otro desde entonces, se reencaminan en vez de perderse.
    alias = pl.carga_alias()
    reencaminadas = pl.resuelve_marcas(marcas, alias)

    # Segunda pasada de deduplicado, ahora contra el histórico: el mismo piso
    # puede venir hoy de Idealista y estar guardado de ayer por Habitaclia.
    fichas, refundidas = pl.consolida(fichas, marcas, hoy, alias)

    # Lo que Albert ha publicado, antes de sumarle los fijados: es lo único que
    # debe volver a data/marks.json.
    marcas_publicadas = {"destacados": list(marcas["destacados"]),
                         "favoritos": list(marcas["favoritos"]),
                         "notas": marcas.get("notas", {})}

    # Saneamos las fotos de todo, también de lo que venía del histórico: así se
    # limpian los logos de agencia que se colaron antes de filtrarlos.
    logos = 0
    for f in fichas:
        buena = portals.foto_valida(f.get("foto"))
        logos += bool(f.get("foto")) and not buena
        f["foto"] = buena
        # Recalculado sobre todo el histórico, no solo sobre lo de hoy: así un
        # cambio de criterio se aplica también a las fichas ya guardadas.
        f["ideal"] = pl.es_ideal(f)
        # Una ficha retirada no es una novedad, por muy de hoy que sea su fecha.
        f["nuevo"] = bool(f.get("activo")) and f.get("first_seen") == hoy

    # El mismo criterio, aplicado también al histórico: lo que se coló antes de
    # existir el filtro se va ahora. Los fijados a mano se respetan siempre.
    antes = len(fichas)
    fichas = [f for f in fichas
              if f.get("fijado") or f.get("m2") or f.get("habitaciones") is not None]
    stats["sin_datos"] = stats.get("sin_datos", 0) + (antes - len(fichas))

    # Los pisos que Albert ha fijado a mano salen siempre en verde, los haya
    # encontrado el escaneo o no.
    fichas, fij = pl.aplica_fijados(fichas, marcas, hoy)

    pl.guarda_estado(fichas, alias)

    # Si alguna marca ha cambiado de sitio, se deja arreglada en el fichero
    # para que la próxima vez ya apunte bien.
    if reencaminadas:
        pl.guarda_json(cfg.FICHERO_MARCAS, marcas_publicadas)

    activos = [f for f in fichas if f.get("activo")]
    nuevos = [f for f in activos if f.get("nuevo")]

    salida = {
        "generado": t0.isoformat(timespec="seconds"),
        "generado_texto": t0.strftime("%d/%m/%Y a las %H:%M"),
        "fecha": hoy,
        "duracion_s": round((ahora() - t0).total_seconds()),
        "criterios": {
            "precio_max": cfg.PRECIO_MAX,
            "minutos_max": cfg.MINUTOS_MAX,
            "preferentes": sorted(cfg.PREFERENTES),
            "municipios": cfg.MUNICIPIOS,
        },
        "resumen": {
            "activos": len(activos),
            "nuevos_hoy": len(nuevos),
            "historico": len(fichas),
            "con_foto": sum(1 for f in activos if f.get("foto")),
            "ideales": sum(1 for f in activos if f.get("ideal")),
            "refundidas_historico": refundidas,
            "fijados_encontrados": fij["encontrados"],
            "fijados_anadidos": fij["anadidos"],
            **stats,
        },
        # Sin escaneo no hay portales que informar: se conserva el estado del
        # último, para que el pie de la web no se quede en blanco.
        "portales": informe.por_portal or previo.get("portales", {}),
        "portales_cubiertos": cubiertos,
        "marcas": marcas,
        "anuncios": sorted(fichas, key=lambda f: (not f.get("nuevo"),
                                                  f.get("precio") or 10**9)),
    }

    cfg.DIR_WEB.mkdir(parents=True, exist_ok=True)
    crudo = json.dumps(salida, ensure_ascii=False, separators=(",", ":"))

    # data.json: por si quieres reutilizar los datos desde otro sitio.
    with open(cfg.FICHERO_SALIDA, "w", encoding="utf-8") as fh:
        fh.write(crudo)

    # data.js: lo que carga la web. Al ser un <script> normal, la página
    # funciona igual publicada en GitHub Pages que abierta como fichero local.
    with open(cfg.DIR_WEB / "data.js", "w", encoding="utf-8") as fh:
        fh.write("window.DATOS=" + crudo + ";\n")

    print("\n" + "=" * 58)
    print(f"  Fichas activas ....... {len(activos)}")
    print(f"  Nuevas hoy ........... {len(nuevos)}")
    print(f"  Histórico total ...... {len(fichas)}")
    print(f"  Duplicados fundidos .. {stats['duplicados_fundidos']}"
          + (f" (+{refundidas} contra el histórico)" if refundidas else ""))
    print(f"  Fijados por Albert ... {fij['encontrados']} encontrados, "
          f"{fij['anadidos']} añadidos a mano")
    con_foto = sum(1 for f in activos if f.get("foto"))
    print(f"  Con foto ............. {con_foto}/{len(activos)}"
          + (f"  ({logos} logos de agencia descartados)" if logos else ""))
    ideales = sum(1 for f in activos if f.get("ideal"))
    rozando = sum(1 for f in activos
                  if f.get("habitaciones") == cfg.IDEAL_HABITACIONES
                  and (f.get("precio") or 0) > cfg.IDEAL_PRECIO_MAX)
    print(f"  Ideales (1 hab, ≤{cfg.IDEAL_PRECIO_MAX // 1000}k) {ideales}"
          + (f"  ({rozando} de 1 hab se pasan de precio)" if rozando else ""))
    print(f"  Descartados: fuera de zona {stats['fuera_zona']} | "
          f"no piso {stats['no_piso']} | precio {stats['precio']} | "
          f"raros {stats['raros']} | sin datos {stats.get('sin_datos', 0)}")
    if stats["motivos_raros"]:
        print(f"  Motivos de descarte .. {stats['motivos_raros']}")
    print("-" * 58)
    for portal, d in informe.por_portal.items():
        estado = "BLOQUEADO" if d["bloqueado"] and not d["anuncios"] else "ok"
        print(f"  {portal:12} {d['anuncios']:4} anuncios  {estado}"
              + (f"  {d['errores'][0][:60]}" if d["errores"] else ""))
    print("=" * 58)
    print(f"→ {cfg.FICHERO_SALIDA}")


if __name__ == "__main__":
    main()
