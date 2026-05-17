#!/usr/bin/env bash
# ============================================================
# Instalador de fuentes para ShakeVision
# ------------------------------------------------------------
# Descarga Inter y JetBrains Mono (ambas con licencia OFL libre)
# y las coloca en shakevision/assets/fonts/. Idempotente: si ya
# existen las omite. Robusto frente a cambios de estructura
# interna de los zips (descomprime todo y busca con `find`).
#
# Uso:
#   bash scripts/install_fonts.sh
# ============================================================

set -euo pipefail

# Carpeta donde viven los recursos del paquete
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FONTS_DIR="$ROOT_DIR/shakevision/assets/fonts"

mkdir -p "$FONTS_DIR"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "→ Carpeta de destino: $FONTS_DIR"
echo

# ----------------------------------------------------------------
# Helper: comprueba si ya hay algún archivo Inter*/JetBrainsMono*
# instalado, devuelve 0 (true) si sí.
# ----------------------------------------------------------------
already_installed() {
    local prefix="$1"
    find "$FONTS_DIR" -maxdepth 1 -type f \
        \( -iname "${prefix}*.ttf" -o -iname "${prefix}*.otf" -o -iname "${prefix}*.ttc" \) \
        | head -1 | grep -q .
}

# ----------------------------------------------------------------
# Inter (variable preferido; estático como fallback)
# ----------------------------------------------------------------
if already_installed "Inter"; then
    echo "✓ Inter ya instalado, omitiendo."
else
    echo "↓ Descargando Inter v4.0…"
    curl -fL --progress-bar \
        -o "$TMP_DIR/inter.zip" \
        "https://github.com/rsms/inter/releases/download/v4.0/Inter-4.0.zip"

    echo "  Descomprimiendo el archivo completo…"
    mkdir -p "$TMP_DIR/inter"
    unzip -q -o "$TMP_DIR/inter.zip" -d "$TMP_DIR/inter"

    echo "  Buscando archivos de fuente…"
    # 1. Preferir un único archivo "variable" (cubre todos los pesos
    #    en ~700 KB, mucho más eficiente que copiar 8 estáticos).
    VAR_FILE=$(
        find "$TMP_DIR/inter" -type f \
            \( -iname "Inter*Variable*.ttf" \
               -o -iname "InterVariable*.ttf" \
               -o -iname "Inter.ttc" \) \
            2>/dev/null | head -1 || true
    )

    if [ -n "${VAR_FILE:-}" ]; then
        cp "$VAR_FILE" "$FONTS_DIR/"
        echo "✓ Inter (variable) instalado: $(basename "$VAR_FILE")"
    else
        # 2. Fallback: copiar los cuatro pesos estáticos esenciales
        echo "  No se encontró el variable, usando estáticos…"
        ANY_FOUND=false
        for weight in Regular Medium SemiBold Bold; do
            FILE=$(
                find "$TMP_DIR/inter" -type f \
                    \( -iname "Inter-${weight}.ttf" -o -iname "Inter-${weight}.otf" \) \
                    2>/dev/null | head -1 || true
            )
            if [ -n "${FILE:-}" ]; then
                cp "$FILE" "$FONTS_DIR/"
                echo "  ✓ $(basename "$FILE")"
                ANY_FOUND=true
            fi
        done
        if [ "$ANY_FOUND" = false ]; then
            echo "  ✗ ¡No se encontró ningún archivo Inter en el zip!"
            echo "    Estructura del zip:"
            find "$TMP_DIR/inter" -name '*.ttf' -o -name '*.otf' | head -10
            exit 1
        fi
    fi
fi
echo

# ----------------------------------------------------------------
# JetBrains Mono (Regular y Medium para los dígitos)
# ----------------------------------------------------------------
if already_installed "JetBrainsMono"; then
    echo "✓ JetBrains Mono ya instalado, omitiendo."
else
    echo "↓ Descargando JetBrains Mono v2.304…"
    curl -fL --progress-bar \
        -o "$TMP_DIR/jbmono.zip" \
        "https://download.jetbrains.com/fonts/JetBrainsMono-2.304.zip"

    echo "  Descomprimiendo…"
    mkdir -p "$TMP_DIR/jbmono"
    unzip -q -o "$TMP_DIR/jbmono.zip" -d "$TMP_DIR/jbmono"

    echo "  Buscando archivos de fuente…"
    ANY_FOUND=false
    for weight in Regular Medium; do
        FILE=$(
            find "$TMP_DIR/jbmono" -type f \
                -iname "JetBrainsMono-${weight}.ttf" \
                2>/dev/null | head -1 || true
        )
        if [ -n "${FILE:-}" ]; then
            cp "$FILE" "$FONTS_DIR/"
            echo "  ✓ $(basename "$FILE")"
            ANY_FOUND=true
        fi
    done
    if [ "$ANY_FOUND" = false ]; then
        echo "  ✗ ¡No se encontró JetBrains Mono en el zip!"
        echo "    Estructura del zip:"
        find "$TMP_DIR/jbmono" -name '*.ttf' | head -10
        exit 1
    fi
fi
echo

# ----------------------------------------------------------------
# Resumen
# ----------------------------------------------------------------
echo "Fuentes instaladas en $FONTS_DIR:"
ls -1 "$FONTS_DIR" | grep -E '\.(ttf|otf|ttc)$' || echo "(ninguna — algo falló)"
echo
echo "Listo. Reinicia la aplicación con:"
echo "    python -m shakevision"
echo "y deberías ver en el log:"
echo "    Fuentes empaquetadas cargadas: Inter, JetBrains Mono"
