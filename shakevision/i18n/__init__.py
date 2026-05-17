"""
Internacionalización (i18n) — paquete público.

API expuesta:

    from shakevision.i18n import t, LocaleService

    t("settings.title")                 → "Settings"  (idioma actual)
    t("status.connecting", host="iris") → "Connecting to iris…"
    LocaleService.set_language("zh")    → cambia idioma + emite signal

Las traducciones viven en ``locales/<lang>.json`` como diccionarios
planos con claves en notación punteada (``settings.title``,
``controls.connect``). El idioma por defecto es inglés; cualquier clave
ausente en otro idioma cae a inglés, y si falta también en inglés se
devuelve la clave misma (útil para depurar).
"""

from shakevision.i18n.service import LocaleService, t

__all__ = ["LocaleService", "t"]
