# Custom fonts for ShakeVision

This directory is **automatically scanned** at startup. Any `.ttf` or
`.otf` file dropped in here will be registered with Qt and will become
available to the QSS theme.

The visual design assumes two specific families:

| Family            | Used for                          | Where to download                                                |
|-------------------|-----------------------------------|------------------------------------------------------------------|
| **Inter**         | All UI text (sans-serif body)     | <https://rsms.me/inter/>                                         |
| **JetBrains Mono**| Numeric values (latency, dB, Hz…) | <https://www.jetbrains.com/lp/mono/>                             |

Both fonts are released under the SIL Open Font License (OFL), which
allows free redistribution. They are **not** included in this repo to
keep the install slim — drop them in once and you're done.

## Quick install

```bash
# Inter — the variable file covers all weights in one ~700 KB TTF
curl -L https://github.com/rsms/inter/releases/latest/download/Inter.zip -o /tmp/inter.zip
unzip -j /tmp/inter.zip "*.ttf" -d shakevision/assets/fonts/

# JetBrains Mono — the regular weight is enough for monospace
curl -L https://download.jetbrains.com/fonts/JetBrainsMono-2.304.zip -o /tmp/jbmono.zip
unzip -j /tmp/jbmono.zip "fonts/ttf/JetBrainsMono-Regular.ttf" -d shakevision/assets/fonts/
```

After that, restart the app. The first log line will read:

```
Fuentes empaquetadas cargadas: Inter, JetBrains Mono
```

## Without these fonts

The QSS theme falls back to the best modern font that ships with each
operating system:

- **macOS**: SF Pro Text / SF Mono
- **Windows 11**: Segoe UI Variable / Cascadia Code
- **Linux**: whatever the distro provides

It still looks good — Inter just makes it look *great*.
