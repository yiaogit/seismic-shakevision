# Events i18n + Timezone — design & build guide

> Source of truth for the "事件页面革新(多语言搜索)+ 时区一致性" work
> started after v0.8.0.0. Read this before touching event search
> (`processing/event_filter.py`, `ui/event_center_panel.py`,
> `ui/event_list_panel.py`) or timestamp display
> (`services/timezone_service.py` and any surface that prints event time).

---

## 1. Two decisions (locked)

### 1.1 Multilingual location search — **structured localized layer**

Rejected alternatives:

* **Translate every USGS `place` string** (via a translation API): the
  field is freeform compositional text (`"<dist> <dir> of <city>, <region>"`)
  over an unbounded vocabulary. Needs network, breaks the offline/privacy
  stance, unstable quality, and substring-matching translated freeform text
  is still fragile. **No.**
* **Better English engine only** (fuzzy/tokenized but English data): lower
  effort but delivers **no** multilingual search — 日本 still won't match
  "Japan". **No.**

Chosen: keep the canonical English `place` for precision/scientific
cross-reference, but add a **language-independent structured layer** and
localize only **closed vocabularies**:

| Dimension | Source (offline) | Localization | Coverage |
|---|---|---|---|
| **Flinn–Engdahl region** | ObsPy `FlinnEngdahl` (lat/lon → region №1–757 + EN name) | **EN only for now** (no authoritative multilingual source; 757-name hand-translation is error-prone — deferred) | whole globe incl. **oceans** |
| **Country** | `reverse_geocoder` (lat/lon → ISO, offline) | **`babel` / CLDR** — `Locale.parse("zh").territories["JP"] → "日本"`, authoritative, no hand-translation | land only |

> **Finding (corrected):** `QLocale.countryToString` returns English
> regardless of locale — it does **not** localize. The authoritative source
> for localized country names is **`babel`** (bundles CLDR), already present.
> So country localization is free & accurate via babel; FE region has **no**
> such multilingual source, so its 757 names stay English (searchable as a
> scientific label) until/unless we source a vetted translation set. The core
> "中文 user searches 日本" need is fully met by the localized **country**.
| **Magnitude / depth / time / distance-from-me** | already in `Earthquake` | numeric — language-independent | all |
| **English `place`** | USGS feed | — (kept verbatim) | all |

Search = localized keyword across **{region name, country name, English
place}** + structured numeric filters. A 中文 user types 日本 → matches the
localized region/country, not a translated string. Offline, deterministic,
no translation API.

ObsPy is already a hard dependency (replay/seedlink/response), so the FE
lookup is free at runtime. It is **not importable in the assistant sandbox**
(`no obspy`) → region code paths must be validated on a real machine / CI,
and isolated behind a thin wrapper with a graceful fallback when obspy is
absent (return `None` region, search still works on place/country).

### 1.2 Timezone — **canonical UTC + labeled display modes**

Current bug: there is only one "local" (`TimezoneService.format_local` →
the *user's* tz). Users may read an event time as the *epicenter's* local
time. Two different clocks are being conflated.

Model: store UTC (already do — `Earthquake.timestamp_unix` is UTC epoch),
convert at display time, and **always print the tz label**. Policy per
surface:

* **Professional surfaces** (Workbench, Replay, waveform/spectrogram axes,
  MiniSEED, report's technical section) → **UTC**, labeled. (Replay axis
  already UTC — keep.)
* **Standard / lay surfaces** (event table, globe & event dialogs, dashboard
  timeline, helicorder, report header) → **user local time**, labeled with
  the tz abbreviation/name.
* **Epicenter local time** → **NOT in scope** for this round (would need the
  `timezonefinder` offline dep). Decision: skip; revisit later if requested.

Implementation is mostly *policy + labeling*, not heavy code: add
`format_utc()` / `to_iso_utc()` beside the existing `format_local()`, then
audit each surface to use the right clock and never print an unlabeled time.

---

## 2. Affected surfaces (timestamp audit)

| Surface | File | Clock | Notes |
|---|---|---|---|
| Event table | `ui/event_list_panel.py` | user local + label | main view |
| Globe quake dialog | `ui/main_window.py` | user local + label | |
| Event Center detail | `ui/event_center_panel.py` | user local + label | |
| Dashboard timeline | `web/dashboard/` + `dashboard_view.py` | user local + label | JS side gets tz-formatted strings or offset |
| Helicorder | `ui/helicorder_widget.py` | user local + label | "newest at bottom" |
| Report | `services/report.py` + `web/report/` | header=local, technical=UTC | both labeled |
| Replay axis | `ui/replay_panel.py` | **UTC** (already) | keep |
| Waveform/spectrogram | `ui/waveform_widget.py` / `spectrogram_widget.py` | UTC | keep |

---

## 3. Build stages

1. **Search engine core** (`processing/event_filter.py`) — multi-field,
   tokenized, accent-insensitive match + depth filter. Pure, pytest in
   sandbox. *(no new dep)*
2. **Timezone service core** (`services/timezone_service.py`) — add
   `format_utc()` / `to_iso_utc()`; document the policy. Pure, pytest.
   *(no new dep)*
3. **Region/country data layer** — region service (ObsPy FE + offline
   country reverse-geocode), extend `Earthquake` with optional
   `region_code` / `country_iso`, 757-name translation tables (batched).
   *(dependency decision — §4; needs machine/CI validation)*
4. **Event Center UI revamp** — filter bar gains region/country/depth/
   distance + unified keyword box; localized region column; wire stages 1–3.
   i18n keys to all 4 locales.
5. **Timezone labeling rollout** — apply §2 across surfaces.
6. **Verify** — compileall + ruff + i18n alignment + pytest; CHANGELOG.

Stages 1–2 are unblocked and land first (no new dependency, fully testable
in the sandbox). Stage 3's data source is the only open question.

---

## 4. Resolved — dependencies for the data layer

Decision (user): do **FE region + country**. Implemented in
`services/geo_region.py`, all three heavy/optional deps isolated behind
`None`-fallback functions:

* **`reverse_geocoder`** (new dep) — lat/lon → ISO country, offline cities DB.
* **`babel`** (new dep, was already importable) — ISO → localized country
  name via CLDR. Authoritative; replaces the abandoned QLocale idea.
* **`obspy`** (already a dep) — lat/lon → FE region number + EN name.

Packaging: both new deps are in `pyproject.toml`; `packaging/shakevision.spec`
gains `collect_data_files("babel")` + `collect_data_files("reverse_geocoder")`
and hidden imports (incl. `scipy.spatial` for rg's cKDTree). **Must be
validated in a real PyInstaller build** — sandbox can't run it.

Deferred: localizing the 757 FE region names (no authoritative multilingual
source; revisit only if ocean/region search in non-EN proves necessary).

---

## 4b. Historical retrieval (full ANSS catalog)

The live globe/dashboard use USGS **summary feeds** (`services/usgs.py`), which
cap at a 1-month window. To reach the **full catalog** (back to ~1900) the app
queries USGS **`fdsnws-event`** (`services/fdsn_event.py`) on demand.

Decisions (user): historical search lives as a **live/historical two-mode
toggle inside the Event Center** (mirrors the Workbench split). Region scoping
= **country/region presets + Global** (no manual box / no radius), since
fdsnws has no place-name parameter — region must be a bounding box.

Pieces (built, tested where pure):

* `services/fdsn_event.py` — `build_query_params/url` (pure, tested) +
  `FDSNEventClient.query(...)`. Reuses `parse_usgs_geojson`. Models the **20 000
  cap** → `FDSNTooManyError` (`error.fdsn.too_many`). Caches by query URL.
* `services/region_presets.py` — curated ISO→bbox + `GLOBAL`; names via Babel.
* `processing/magnitude_color.py` — magnitude→hex ramp + legend keys
  (`mag.scale.*`). Applied to the event table's magnitude cell.
* `processing/event_filter.structured_tokens()` — makes ID / magnitude / year /
  depth searchable so the text box can *confirm* an event (`"japan 6"`,
  `"us7000abcd"`, `"2011"`). Wired into the Event Center search index.

Remaining (Qt, validate on machine): the two-mode Event Center UI — historical
query form (time range incl. past years, min/max magnitude, region preset,
orderby, limit) + a `QThread` worker around `FDSNEventClient` (large queries
are slow), populating the same colored event table; `FDSNTooManyError` →
error overlay asking to narrow. A magnitude legend strip.

Query-pattern reminder: fdsnws is **on-demand with required filters**, NOT a
bulk "load everything" — always send a time range + region/min-magnitude to
stay under the cap.

## 5. Constraints / gotchas

* ObsPy & Qt are **not** importable in the assistant sandbox — region-code
  and any GUI paths must be validated on the user's machine / CI. Keep the
  ObsPy call behind a thin, individually-importable wrapper with a `None`
  fallback so pure search/i18n tests still run headless.
* i18n: any new user-visible string → all 4 locales (`en/es/fr/zh`), keys
  aligned, placeholders identical. Region-name tables live separately
  (`i18n/regions/{loc}.json`) to avoid bloating the main locale files; they
  are a *closed* vocabulary, not part of the 578-key UI contract.
* Every printed event time MUST carry a tz label — no bare `HH:MM:SS`.
