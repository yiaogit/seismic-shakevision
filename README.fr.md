<div align="center">

# 🌐 SeismicGuard

[简体中文](README.md) · [English](README.en.md) · [Español](README.es.md) · **Français**

> Anciennement **ShakeVision OpenData Monitor**. La v0.7.0 apporte le
> rebranding en SeismicGuard, une refonte visuelle façon macOS Sonoma,
> l'i18n complète en 4 langues, un assistant de configuration initiale,
> une page profil avec timeline d'activité, la géolocalisation par IP
> et de nombreuses améliorations d'usage. Les anciens binaires (v0.1.x)
> restent disponibles sur la page Releases sous le nom `ShakeVision-*`.

**Station de monitoring sismique de bureau, open-source**
*Cross-platform desktop seismic monitoring workbench*

Récupère en temps réel les données du réseau mondial de sismologie
citoyenne (Raspberry Shake) et des réseaux professionnels (USGS / IRIS),
et combine globe 3D · tableau de bord · analyse formes d'onde /
spectrogramme / déclenchement dans une seule application desktop.

[![CI](https://github.com/yiaogit/seismic-shakevision/actions/workflows/ci.yml/badge.svg)](https://github.com/yiaogit/seismic-shakevision/actions/workflows/ci.yml)
[![Release](https://github.com/yiaogit/seismic-shakevision/actions/workflows/release.yml/badge.svg)](https://github.com/yiaogit/seismic-shakevision/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platforms](https://img.shields.io/badge/platform-windows%20%7C%20macos%20arm64%20%7C%20linux-lightgrey)](https://github.com/yiaogit/seismic-shakevision/releases/latest)
[![i18n](https://img.shields.io/badge/i18n-EN%20%7C%20ES%20%7C%20%E4%B8%AD%E6%96%87%20%7C%20FR-brightgreen)](shakevision/i18n/locales/)

[**Télécharger**](#-télécharger) · [**Lancer depuis les sources**](#-lancer-depuis-les-sources) · [**Fonctionnalités**](#-fonctionnalités) · [**Architecture**](#-architecture) · [**Publication**](#-publication)

</div>

---

## ✨ Fonctionnalités

| Module                     | Description                                                                                                                       |
|----------------------------|-----------------------------------------------------------------------------------------------------------------------------------|
| 🌍 **Globe 3D**            | Rendu temps réel ECharts-GL, 600+ stations citoyennes Raspberry Shake + 400+ stations dorsales USGS / IRIS, séismes colorés par magnitude, click-zoom + ajout au banc Pro |
| 📊 **Tableau de bord**     | 7 graphiques ECharts liés : top pays, histogrammes magnitude / profondeur, timeline 24 h (bulles de densité), radar PAGER (filtre régional), buckets adaptatifs, dispersion profondeur × magnitude |
| 🔬 **Banc Pro**            | Fenêtre flottante : formes d'onde 3 canaux + spectrogramme + héliographe 24 h + mouvement de particule N-E + enregistrement STA/LTA + carte d'intensité MMI |
| 🔊 **Sonification**        | Joue les 60 dernières secondes du mouvement du sol en audio audible à vitesse 1× – 60×                                            |
| 🌐 **i18n**                | Stack complète en 4 langues (EN / ES / 简中 / FR) avec changement instantané, y compris vues web, intérieurs de graphiques, tooltips et rapports HTML |
| 🕒 **Fuseau horaire**      | Auto-détection du fuseau système + override manuel ; tous les timestamps affichés dans le fuseau de l'utilisateur                 |
| 📄 **Rapports**            | Export en un clic vers un fichier HTML autonome (avec timeline SVG) + export PDF via `QWebEngine.printToPdf`                      |
| ⚡ **SeedLink en direct**  | Connexion directe à IRIS `rtserve.iris.washington.edu:18000`, routage automatique IU/US/II/IC, statut de connexion par étapes, annulable à tout moment |
| 👤 **Profil**              | OAuth GitHub (Device Flow), statistiques d'usage, **timeline d'activité récente** (50 derniers événements avec timestamps relatifs, stockés localement) |
| 📍 **Localisation**        | Géolocalisation par IP (un clic, jamais en arrière-plan) suggère les stations proches et met à jour le fuseau horaire             |

---

## 📦 Télécharger

> **Recommandé pour les utilisateurs finaux.** Les binaires sont
> compilés par GitHub Actions à chaque tag ; les sommes SHA-256 sont
> également publiées automatiquement.

Dernière version → **[Latest Release](https://github.com/yiaogit/seismic-shakevision/releases/latest)**

| Plateforme                            | Fichier                                        | Installation                                                  |
|---------------------------------------|------------------------------------------------|---------------------------------------------------------------|
| 🪟 **Windows 10 / 11 x64**            | `ShakeVision-X.Y.Z-windows-x64.zip`            | Dézipper → double-clic `ShakeVision.exe` (SmartScreen au premier lancement, voir plus bas) |
| 🍎 **macOS Apple Silicon (M1–M5)**    | `ShakeVision-X.Y.Z-macos-arm64.dmg`            | Ouvrir le DMG → glisser vers `/Applications` → première fois clic droit → Ouvrir           |
| 🐧 **Linux x64**                      | `ShakeVision-X.Y.Z-linux-x64.AppImage`         | `chmod +x ShakeVision-*.AppImage` → double-clic                                            |

#### 🛡 Notes du premier lancement (Windows SmartScreen / macOS Gatekeeper)

SeismicGuard n'est **pas encore signé** (certificat EV ≈ 300 $/an —
prévu pour la v1.0). Le système avertira au premier lancement :

<details>
<summary><b>🪟 Windows — "Windows protected your PC"</b></summary>

Après dézippage et double-clic sur `ShakeVision.exe`, un dialogue
bleu apparaît :

```
Windows protected your PC
Microsoft Defender SmartScreen prevented an unrecognized app from starting.
```

Que faire :

1. Cliquer sur **"More info"** (petit lien, en bas à gauche)
2. Un bouton **"Run anyway"** apparaît — cliquer dessus
3. Les lancements suivants ne demandent plus rien

> Une seule fois. SmartScreen mémorise la confiance locale.

</details>

<details>
<summary><b>🍎 macOS — "ShakeVision can't be opened because Apple cannot check it for malicious software"</b></summary>

Après avoir glissé `.app` dans `/Applications`, le premier lancement
est bloqué par Gatekeeper :

1. **Ne pas** double-cliquer ; faire **clic droit (ou Ctrl-clic)** sur
   `ShakeVision.app`
2. Choisir **"Open"** dans le menu
3. Reconfirmer **"Open"** dans le dialogue
4. À partir de là, le double-clic fonctionne normalement

</details>

> 🍎 **Utilisateurs Mac Intel** : les binaires Intel ne sont plus
> publiés (Apple Silicon est mainstream depuis 4+ ans). Compilez
> localement — voir [Lancer depuis les sources](#-lancer-depuis-les-sources).

Vérification optionnelle des checksums :

```bash
# Après téléchargement de SHA256SUMS.txt depuis la page release
sha256sum -c SHA256SUMS.txt        # Linux
shasum -a 256 -c SHA256SUMS.txt    # macOS
certutil -hashfile <file> SHA256   # Windows PowerShell
```

---

## 💻 Lancer depuis les sources

Pour développeurs, utilisateurs Mac Intel et contributeurs.

### Prérequis

| OS         | Requis                                                                                                   |
|------------|----------------------------------------------------------------------------------------------------------|
| Tous       | Python ≥ 3.10 (3.11 / 3.12 recommandé) + Git                                                             |
| **Linux**  | `libegl1 libxkbcommon0 libxcb-cursor0 libxcb-icccm4 libgl1 libdbus-1-3` (Ubuntu/Debian `apt install`)    |
| **macOS**  | Xcode Command Line Tools (`xcode-select --install`)                                                      |
| **Windows**| Visual C++ Redistributable (généralement fourni par le PySide6 installé via pip)                         |

### Démarrage en une commande

```bash
# 1) Cloner + entrer
git clone https://github.com/yiaogit/seismic-shakevision.git
cd seismic-shakevision

# 2) Env virtuel + installation (avec extras dev)
python3 -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .\.venv\Scripts\activate
pip install --upgrade pip
pip install -e ".[dev]"

# 3) Téléchargement unique des assets (~10 Mo : ECharts + polices + textures globe)
bash scripts/install_libs.sh
bash scripts/install_fonts.sh

# 4) Lancer
python -m shakevision
```

> 🪟 Sous Windows, l'étape 3 s'exécute via Git Bash / WSL, ou téléchargez
> manuellement les URL listées dans le script.
> 🍎 macOS : `pip install -e ".[macos]"` ajoute pyobjc pour la barre
> de titre translucide.

---

## 🚀 Démarrage rapide

```
Lancer → entre par défaut dans la vue 🌍 Globe
  ├── Clic sur un point USGS → dialogue "Ajouter à Pro ?" → ✅ → apparaît dans le panneau Pro
  ├── Basculer vers 📊 Data → 7 graphiques liés + filtres période / région
  └── En haut à droite 🔬 Pro → ouvre la fenêtre pro indépendante
                                ├── Sélectionner la station USGS juste ajoutée
                                ├── Cliquer sur Connect → stream SeedLink en direct
                                └── Voir formes d'onde / spectrogramme / héliographe / particule en temps réel

En haut à droite ⚙ Settings → changer langue + fuseau, appliqué instantanément
En haut à droite 👤 Profile → carte identité + statistiques + timeline d'activité
```

---

## 🏗 Architecture

### Flux de données

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ USGS GeoJSON │ ──► │   Worker     │ ──► │  data_models │ ──► │   Globe      │
│ IRIS FDSN    │     │ (async,      │     │ (Earthquake, │     │ Dashboard    │
│ ShakeNet     │     │  mono-thread)│     │  Station…)   │     │ (HTML + JS)  │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  SeedLink    │ ──► │  RingBuffer  │ ──► │  Processor   │ ──► │ Fenêtre Pro  │
│ rtserve.iris │     │ (thread-safe)│     │ Butterworth, │     │  Waveform +  │
│  → ObsPy     │     │              │     │ STA/LTA, FFT │     │  Spec + Hel  │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

### Stack technique

| Couche           | Choix                                               | Justification                                      |
|------------------|-----------------------------------------------------|----------------------------------------------------|
| **Framework UI** | PySide6 ≥ 6.6                                       | LGPL, look natif multi-plateforme, QtWebEngine livre Chromium |
| **Rendu web**    | QWebEngineView                                      | Embarquer ECharts sans tirer un moteur navigateur tiers      |
| **Globe 3D**     | [ECharts-GL](https://github.com/ecomfe/echarts-gl)  | Une seule lib couvre 2D + 3D, bundle plus léger que Three.js |
| **Charts 2D**    | [Apache ECharts](https://echarts.apache.org/) 5.4   | Les 7 charts partagent le même moteur                        |
| **DSP**          | NumPy + SciPy                                       | Standard industrie — Butterworth + FFT                       |
| **Sismologie**   | [ObsPy](https://www.obspy.org/) ≥ 1.4               | Client SeedLink + lecture/écriture MiniSEED                  |
| **Waveform**     | [pyqtgraph](https://www.pyqtgraph.org/) 0.13        | 60 FPS accéléré GPU                                          |
| **Audio**        | QtMultimedia QAudioSink                             | Multi-plateforme, zéro dépendance supplémentaire             |
| **Fuseau**       | `zoneinfo` (+ `tzdata` pip sur Windows)             | Stdlib ; auto-détection `/etc/localtime` POSIX               |
| **i18n**         | Dict JSON maison + helper `t()`                     | Python et JS partagent un dictionnaire, sans build           |
| **Packaging**    | PyInstaller (onedir) + `create-dmg` + `appimagetool` | Cohérent inter-plateformes ; onedir démarre vite             |
| **CI / Release** | GitHub Actions                                      | Matrice 3 plateformes + publication automatique sur tag      |

### Structure du projet

```
seismic-shakevision/
├── shakevision/              # ── package principal ──
│   ├── __main__.py           # entrée (python -m shakevision)
│   ├── config.py             # registre serveurs SeedLink + stations par défaut
│   ├── sources/              # DataSource abstrait + Mock / SeedLink
│   ├── processing/           # RingBuffer / Filters / Detector / Spectrum / Recorder / Intensity / Sonifier
│   ├── services/             # clients USGS / IRIS / ShakeNet + Worker + Report + Timezone + ActivityLog + Location + ClearCache
│   ├── ui/                   # fenêtre principale PySide6 + flottants + widgets + Settings + Profile + Onboarding
│   ├── i18n/                 # LocaleService + 4 dictionnaires alignés (435 clés chacun)
│   ├── web/{globe,dashboard,report}/   # HTML/JS/CSS embarqué
│   └── assets/{fonts,icons}/ # polices (téléchargées par script, hors du repo)
│
├── tests/                    # pytest unitaires + intégration (40+ modules)
├── packaging/                # ⭐ spec PyInstaller + build.py multi-plateforme
├── scripts/                  # install_libs.sh / install_fonts.sh / download_globe_assets.py
├── .github/workflows/        # ci.yml (chaque push) + release.yml (déclenché par tag)
├── CHANGELOG.md
├── pyproject.toml
└── README.md                 # ce fichier (plus README.en.md / README.es.md / README.fr.md)
```

---

## 🛠 Développement & tests

```bash
# Lancer la suite de tests
pytest -v

# Lint
ruff check shakevision tests

# Sanity check de compilation
python -m compileall -q shakevision tests
```

CI tourne à chaque push / PR : Ubuntu / macOS / Windows × Python 3.10 /
3.11 / 3.12 × (ruff + pytest). Linux utilise `xvfb-run` ; macOS /
Windows utilisent `QT_QPA_PLATFORM=offscreen`.

---

## 🌐 Traductions i18n

Les dictionnaires vivent dans `shakevision/i18n/locales/*.json`
(≈ 435 clés chacun, 4 langues alignées à 100 %).

**Ajouter une langue** :

1. Copier `en.json` vers un nouveau fichier, p. ex. `ja.json` / `de.json`
2. Traduire chaque value (ne pas changer les keys)
3. Enregistrer dans `shakevision/i18n/service.py` sous
   `SUPPORTED_LANGUAGES` + `LANGUAGE_LABELS`
4. Ouvrir une PR

---

## 🚢 Publication

> Mainteneurs uniquement. Suivre ce flux à chaque release.

### Préparation unique (déjà en place — passer)

- ✅ `packaging/shakevision.spec` — spec PyInstaller
- ✅ `packaging/build.py` — driver multi-plateforme
- ✅ `.github/workflows/release.yml` — build + publication auto

### Étapes de release (avec v0.1.1 comme exemple)

```bash
# 1) Bumper les 3 numéros de version de manière cohérente
#    a. shakevision/__init__.py    →  __version__ = "0.1.1"
#    b. pyproject.toml              →  version = "0.1.1"
#    c. packaging/shakevision.spec  →  version = "0.1.1"  (BUNDLE)

# 2) Mettre à jour CHANGELOG.md : préfixer un bloc ## [0.1.1] — YYYY-MM-DD
#    Le workflow l'extrait automatiquement comme release notes.

# 3) Commit + push
git add -A
git commit -m "release: v0.1.1"
git push origin main

# 4) Tag + push tag → déclenche le release workflow
git tag -a v0.1.1 -m "ShakeVision v0.1.1 — binary installers"
git push origin v0.1.1
```

Après le push du tag, GitHub Actions exécute :

```
release.yml (tag v0.1.1)
  ├── build-windows  (windows-latest, Py 3.11)      → ShakeVision-0.1.1-windows-x64.zip
  ├── build-macos    (macos-14 / Apple Silicon)     → ShakeVision-0.1.1-macos-arm64.dmg
  ├── build-linux    (ubuntu-22.04)                 → ShakeVision-0.1.1-linux-x64.AppImage
  └── publish        (récupère les 3 artifacts)
       ├── extrait le bloc [0.1.1] de CHANGELOG.md comme release notes
       ├── assemble SHA256SUMS.txt
       └── crée la Release GitHub avec les 3 binaires + checksums
```

Environ 15–25 minutes plus tard, **v0.1.1** apparaît sur
https://github.com/yiaogit/seismic-shakevision/releases.

### Pré-releases (rc / beta)

Les suffixes `-rc1` / `-beta` / `-alpha` / `-dev` / `-pre` marquent
automatiquement `prerelease: true` :

```bash
git tag -a v0.2.0-rc1 -m "v0.2.0 release candidate 1"
git push origin v0.2.0-rc1
```

### Récupérer une release ratée

```bash
# Supprimer le tag distant (supprimer aussi la Release dans l'UI GitHub)
git push --delete origin v0.1.1
git tag -d v0.1.1
# Corriger, re-tagger, push
git tag -a v0.1.1 -m "..."
git push origin v0.1.1
```

Détails complets sur le packaging (builds locaux, particularités du
macOS dual-arch, tailles, etc.) dans
[`packaging/README.md`](packaging/README.md).

---

## 🗺 Feuille de route

- [x] **v0.1.0** — release complète depuis les sources (i18n + fuseau + Pro + Settings)
- [x] **v0.1.1** — installeurs binaires (Windows `.zip` + macOS arm64 `.dmg` + Linux `.AppImage`)
- [x] **v0.2.0** — replay historique : téléchargement MiniSEED depuis IRIS FDSN dataselect, vitesse ajustable
- [x] **v0.3.0** — UI Raspberry Shake LAN personnalisé ("➕ Add LAN Shake…" + onglet "My Shakes")
- [x] **v0.7.0** — rebranding SeismicGuard, theming macOS-Sonoma, assistant, profil + activité, géolocalisation IP, correctif overflow PDF
- [ ] **v0.8.0** — UX séisme favori sur le globe (bouton, remplace le right-click reporté)
- [ ] **v1.0.0** — signature de code (Windows EV cert + macOS Developer ID + notarisation) ; suppression complète des avertissements SmartScreen / Gatekeeper

---

## 📜 Sources de données

- 🍓 [Raspberry Shake](https://raspberryshake.org/) — réseau de sismologie citoyenne, données ouvertes CC-BY
- 🇺🇸 [USGS Earthquake Hazards Program](https://earthquake.usgs.gov/) — flux GeoJSON sismes
- 🌍 [IRIS DMC](https://ds.iris.edu/) — métadonnées réseaux pro + stream SeedLink direct (`rtserve.iris.washington.edu`)

> ⚠ **Aucun serveur SeedLink Raspberry Shake public n'existe.** Vous ne
> pouvez vous connecter qu'à votre propre appareil LAN
> (`rs.local:18000`) ou à un abonnement RTDC payant. Voir le registre
> `SEEDLINK_SERVERS` dans `shakevision/config.py`.

---

## 🤝 Contribuer

Issues et PRs bienvenus. Les commentaires de code sont en espagnol
(convention historique du projet) ; les chaînes utilisateur sont
externalisées via i18n. Avant soumission, merci de lancer :

```bash
ruff check shakevision tests
pytest -v
```

CI doit passer avant merge.

---

## 📄 Licence

[MIT License](LICENSE) © 2025 Yiao

---

## 🙏 Remerciements

Merci à la communauté [Raspberry Shake](https://raspberryshake.org/)
et au projet [ObsPy](https://www.obspy.org/) pour la chaîne d'outils
sismologique open-source ; et hommage aux scientifiques citoyens du
monde entier pour leur contribution continue au monitoring sismique.
