#!/bin/bash
# Escaneo desde el Mac de Albert.
#
# Existe porque Idealista, Fotocasa y Milanuncios bloquean las IPs de centros
# de datos: desde GitHub devuelven cero, y desde una conexión doméstica
# funcionan. Este complemento rellena ese hueco los días que el Mac esté
# encendido, y sube lo que encuentre al mismo repositorio.
#
# No pisa el trabajo de GitHub: el escaneo solo retira anuncios de los
# portales que ha conseguido consultar de verdad (ver aplica_historico).
#
# Se instala con bin/instalar-mac.sh y se puede lanzar a mano cuando quieras.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REGISTRO="$REPO/data/escaneo-local.log"
PYTHON="$REPO/.venv/bin/python"

cd "$REPO" || exit 1

# Nos aseguramos de tener git y python en el PATH: launchd arranca con un
# entorno mínimo y no hereda el de la sesión de Terminal.
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

anota() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$REGISTRO"; }

# El registro no crece sin control: nos quedamos con las últimas 2.000 líneas.
if [ -f "$REGISTRO" ] && [ "$(wc -l < "$REGISTRO")" -gt 2000 ]; then
  tail -1000 "$REGISTRO" > "$REGISTRO.tmp" && mv "$REGISTRO.tmp" "$REGISTRO"
fi

anota "──────── inicio del escaneo local ────────"

if [ ! -x "$PYTHON" ]; then
  anota "ERROR: falta el entorno virtual. Ejecuta:"
  anota "  python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt"
  exit 1
fi

# Sin red no hay nada que hacer; volveremos mañana.
if ! curl -s --max-time 10 -o /dev/null https://www.idealista.com/; then
  anota "Sin conexión utilizable. Se deja para la próxima."
  exit 0
fi

# 1. Traer lo que haya subido GitHub esta mañana.
if ! git pull --rebase --autostash -q origin main 2>>"$REGISTRO"; then
  anota "ERROR: no se ha podido sincronizar con GitHub. Se aborta para no liarla."
  exit 1
fi

# 2. Escanear. Los cinco portales: desde aquí funcionan todos.
anota "Escaneando…"
if ! "$PYTHON" -m scanner.run >> "$REGISTRO" 2>&1; then
  anota "ERROR: el escaneo ha fallado. Mira el detalle justo arriba."
  exit 1
fi

# 3. Comprobar que la web sigue viva. No es motivo para no publicar.
if [ -x "$REPO/.venv/bin/python" ]; then
  "$PYTHON" tests/test_ui.py >> "$REGISTRO" 2>&1 \
    || anota "AVISO: las pruebas de la web han fallado; se publica igualmente."
fi

# 4. Publicar.
git add data/listings.json data/marks.json docs/data.json docs/data.js 2>/dev/null
if git diff --staged --quiet; then
  anota "Sin cambios respecto a lo que ya había publicado."
  anota "──────── fin ────────"
  exit 0
fi

ACTIVOS=$("$PYTHON" -c "import json;print(json.load(open('docs/data.json'))['resumen']['activos'])" 2>/dev/null || echo "?")
NUEVOS=$("$PYTHON" -c "import json;print(json.load(open('docs/data.json'))['resumen']['nuevos_hoy'])" 2>/dev/null || echo "?")

git -c user.name="Escaneo local" -c user.email="albertezca@gmail.com" \
    commit -q -m "Escaneo local $(date '+%d/%m/%Y %H:%M'): ${NUEVOS} nuevos, ${ACTIVOS} en venta"

# GitHub puede haber publicado mientras escaneábamos: reintentamos una vez.
if ! git push -q origin main 2>>"$REGISTRO"; then
  anota "Push rechazado; reintento tras sincronizar."
  git pull --rebase --autostash -q origin main 2>>"$REGISTRO"
  if ! git push -q origin main 2>>"$REGISTRO"; then
    anota "ERROR: no se ha podido subir. El commit queda en local para el próximo intento."
    exit 1
  fi
fi

anota "Publicado: ${NUEVOS} nuevos, ${ACTIVOS} en venta."
anota "──────── fin ────────"
