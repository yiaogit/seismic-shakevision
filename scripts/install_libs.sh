#!/usr/bin/env bash
# ============================================================
# Descarga local de Three.js, Globe.gl y ECharts.
# ------------------------------------------------------------
# Sin esto el Globo y el Dashboard dependen de cdn.jsdelivr.net,
# y en redes restrictivas (China continental, algunas redes
# corporativas) la carga puede fallar o ser muy lenta.
#
# Tras ejecutar este script, las páginas web del paquete intentan
# cargar las bibliotecas DESDE DISCO primero; si no existen, caen
# en el CDN (lógica en index.html con fallback).
#
# Uso:
#   bash scripts/install_libs.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

GLOBE_LIB="$ROOT_DIR/shakevision/web/globe/lib"
DASH_LIB="$ROOT_DIR/shakevision/web/dashboard/lib"

mkdir -p "$GLOBE_LIB" "$DASH_LIB"

# ----------------------------------------------------------------
# Helper: descarga si no existe ya
# ----------------------------------------------------------------
download() {
    local url="$1"
    local dest="$2"
    local name="$(basename "$dest")"
    if [ -f "$dest" ] && [ -s "$dest" ]; then
        echo "✓ ${name} ya está instalado"
        return
    fi
    echo "↓ Descargando ${name}…"
    if curl -fL --progress-bar -o "$dest" "$url"; then
        local size_kb=$(($(stat -f%z "$dest" 2>/dev/null || stat -c%s "$dest") / 1024))
        echo "✓ ${name} descargado (${size_kb} KB)"
    else
        echo "✗ Falló la descarga de ${name}"
        rm -f "$dest"
        return 1
    fi
}

echo "→ Carpetas de destino:"
echo "    $GLOBE_LIB"
echo "    $DASH_LIB"
echo

# ----------------------------------------------------------------
# ECharts core (compartido por Globo y Datos)
# ----------------------------------------------------------------
download \
    "https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js" \
    "$DASH_LIB/echarts.min.js"

# Copia adicional para el Globo (mismo binario, distinta carpeta)
cp "$DASH_LIB/echarts.min.js" "$GLOBE_LIB/echarts.min.js" 2>/dev/null || \
    download \
        "https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js" \
        "$GLOBE_LIB/echarts.min.js"

# ----------------------------------------------------------------
# ECharts-GL (extensión 3D — añade globe / scatter3D / lines3D)
# ----------------------------------------------------------------
download \
    "https://cdn.jsdelivr.net/npm/echarts-gl@2.0.9/dist/echarts-gl.min.js" \
    "$GLOBE_LIB/echarts-gl.min.js"

# ----------------------------------------------------------------
# Mapa de relieve (height map para sombreado realista del relieve)
# Pequeño (~370 KB), no cambia entre versiones — lo mantenemos aquí.
# ----------------------------------------------------------------
download \
    "https://cdn.jsdelivr.net/npm/three-globe@2.27.4/example/img/earth-topology.png" \
    "$GLOBE_LIB/earth-topology.png"

# ----------------------------------------------------------------
# Texturas + GeoJSON de bordes — delegamos al script Python que
# tiene mirrors de fallback y validación de cada archivo.
# ----------------------------------------------------------------
# v0.7.3 fix: antes este shell sólo descargaba earth-night.jpg con un
# único mirror (three-globe). Resultado:
#   * earth-day.jpg     → NUNCA se descargaba → modo día rendering
#                          fallback a la night texture
#   * earth-night.jpg   → mirror low-res sin luces de ciudad
#   * world.json        → NUNCA se descargaba → modo profesional
#                          sin fronteras de país ni etiquetas
# En el desarrollo en macOS estos archivos existían localmente porque
# el desarrollador corre `download_globe_assets.py` a mano. En CI no
# se corría → Windows .exe rendería con texturas incompletas.
#
# Solución: invocar al script Python que cubre los 3 assets con
# mirrors NASA / Natural Earth y validación. Si Python no está
# disponible, dejamos los antiguos downloads simples como fallback.
echo
if command -v python3 >/dev/null 2>&1; then
    echo "→ Descargando texturas día/noche + fronteras GeoJSON…"
    python3 "$ROOT_DIR/scripts/download_globe_assets.py" || \
        echo "⚠ download_globe_assets.py reportó errores parciales — continuamos"
elif command -v python >/dev/null 2>&1; then
    echo "→ Descargando texturas día/noche + fronteras GeoJSON…"
    python "$ROOT_DIR/scripts/download_globe_assets.py" || \
        echo "⚠ download_globe_assets.py reportó errores parciales — continuamos"
else
    echo "⚠ python3 no disponible — usando fallback básico (solo night.jpg)"
    download \
        "https://cdn.jsdelivr.net/npm/three-globe@2.27.4/example/img/earth-night.jpg" \
        "$GLOBE_LIB/earth-night.jpg"
fi

echo
echo "Bibliotecas instaladas:"
echo "  $GLOBE_LIB:"
ls -lh "$GLOBE_LIB" 2>/dev/null | tail -n +2 | awk '{print "    "$5"\t"$NF}'
echo "  $DASH_LIB:"
ls -lh "$DASH_LIB" 2>/dev/null | tail -n +2 | awk '{print "    "$5"\t"$NF}'
echo
echo "Listo. Reinicia la aplicación con:"
echo "    python -m shakevision"
echo "El Globo cargará las bibliotecas desde disco, sin depender de CDN."
