"""
SeismicGuard — desktop seismic monitoring workbench.

Antes conocido como "SeismicGuard". El paquete Python conserva el
nombre ``shakevision`` por compatibilidad (cambiar el namespace
rompería las claves QSettings persistidas de los usuarios actuales,
los imports en plugins externos y las rutas relativas en cientos
de archivos). Para el USUARIO final la app se llama SeismicGuard:
ventana, splash, logo, README y notas de versión usan el nombre
nuevo.
"""

# Versión del paquete (mantener sincronizada con pyproject.toml y
# con packaging/shakevision.spec).
__version__ = "0.7.1"

# Nombre comercial que el usuario ve (ventana, splash, About).
APP_NAME = "SeismicGuard"

# Nombre legacy. Solo se usa para resolver claves QSettings antiguas
# (organización en QSettings.setUserScope etc.) y mantener la
# retrocompatibilidad de datos persistidos durante el rebrand.
LEGACY_APP_NAME = "SeismicGuard"
