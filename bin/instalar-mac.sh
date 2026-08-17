#!/bin/bash
# Instala (o quita) el escaneo diario en este Mac usando launchd.
#
#   ./bin/instalar-mac.sh            instala a las 21:00
#   ./bin/instalar-mac.sh 07 45      instala a las 07:45
#   ./bin/instalar-mac.sh --quitar   lo desinstala
#
# launchd es el sistema propio de macOS: si a la hora prevista el Mac está
# apagado o dormido, la tarea se ejecuta en cuanto vuelve a estar disponible.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ETIQUETA="com.albertezca22.pisos-baix-emporda"
PLIST="$HOME/Library/LaunchAgents/$ETIQUETA.plist"

if [ "${1:-}" = "--quitar" ]; then
  launchctl unload "$PLIST" 2>/dev/null
  rm -f "$PLIST"
  echo "Escaneo local desinstalado."
  exit 0
fi

HORA="${1:-21}"
MINUTO="${2:-0}"

chmod +x "$REPO/bin/escaneo-local.sh"
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLISTFIN
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$ETIQUETA</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$REPO/bin/escaneo-local.sh</string>
  </array>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>$HORA</integer>
    <key>Minute</key><integer>$MINUTO</integer>
  </dict>

  <key>WorkingDirectory</key>
  <string>$REPO</string>

  <key>StandardOutPath</key>
  <string>$REPO/data/escaneo-local.salida.log</string>
  <key>StandardErrorPath</key>
  <string>$REPO/data/escaneo-local.salida.log</string>

  <key>ProcessType</key>
  <string>Background</string>
  <key>LowPriorityIO</key>
  <true/>
</dict>
</plist>
PLISTFIN

launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST" || { echo "No se ha podido cargar la tarea."; exit 1; }

printf 'Escaneo local instalado. Se ejecutará cada día a las %02d:%02d.\n' "$HORA" "$MINUTO"
echo
echo "Comprobarlo:      launchctl list | grep pisos"
echo "Lanzarlo ahora:   launchctl start $ETIQUETA"
echo "Ver el registro:  tail -f \"$REPO/data/escaneo-local.log\""
echo "Desinstalarlo:    ./bin/instalar-mac.sh --quitar"
