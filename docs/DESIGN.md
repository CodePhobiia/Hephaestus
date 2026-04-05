# DESIGN.md — Hephaestus CLI Visual & UX Language

This document defines the visual identity, color system, typography, layout patterns,
and UX principles for every surface of the `heph` CLI and interactive REPL. It is the
single source of truth — implementation in `cli/display.py` and all rendering code
must conform to what is specified here.

---

## 1. Design Philosophy

Hephaestus is a forge. Not a chatbot, not an AI assistant, not a SaaS dashboard.
The CLI should feel like operating heavy, precise machinery — warm light spilling
from molten metal, the controlled violence of a hammer strike, the quiet satisfaction
of a finished blade cooling on the anvil.

**Three ground rules:**

1. **Warmth over coolness.** No blue. No purple. No cyan. These are the colors of
   corporate AI slop, chatbot UIs, and generic developer tooling. Hephaestus runs
   hot — golds, ambers, embers, and the red-white of metal under pressure.

2. **Density over decoration.** Every pixel of terminal real estate earns its keep.
   No gratuitous box-drawing, no emoji-as-branding, no animated flourishes. Information
   density is the aesthetic. If something can be a single line, it is a single line.

3. **Machinery over magic.** The interface communicates mechanism, not mystery. Users
   see what stage is running, what the score breakdown is, what the cost was. The forge
   is glass-walled — you watch the metal move.

---

## 2. Color System

### 2.1 The Palette

The palette is derived from forge metallurgy: the visible spectrum of heated steel,
from dull red through orange to white-hot, plus the natural darks and lights of
a workshop environment.

```
ROLE              RICH STYLE            HEX (reference)   USAGE
─────────────────────────────────────────────────────────────────────────
Molten Gold       bold yellow           #FFD700            Primary brand. Banner, section headers,
                                                           rules, emphasis. The "Hephaestus color."

Forge Amber       yellow                #FFBF00            Secondary headers, labels, active menu
                                                           indices, stage names, score labels.

Ember             dark_orange           #FF8C00            Interactive elements: commands in help
                                                           text, clickable/actionable items,
                                                           prompt accents, navigation hints.
                                                           This replaces all prior cyan usage.

White Hot         bold white            #FFFFFF            Primary body text, important values,
                                                           invention names, key data.

Iron              white                 #C0C0C0            Standard body text, table cell content,
                                                           descriptions.

Slag              dim                   #808080            Metadata, timestamps, secondary info,
                                                           tertiary labels, parentheticals.

Spark Green       bold green            #00FF00            Success: checkmarks, passing scores,
                                                           positive verdicts, cost totals.

Furnace Red       bold red              #FF0000            Errors: failed stages, fatal flaws,
                                                           error panels, negative verdicts.

Caution           yellow                #FFD700            Warnings: structural weaknesses,
                                                           deprecation notices, non-fatal issues.
                                                           Uses same yellow as Forge Amber but
                                                           paired with warning symbol.

Steel             grey70                #B0B0B0            Neutral data in tables: IDs, hashes,
                                                           revision numbers, file paths.
                                                           A warm-neutral gray, never blue-gray.
```

### 2.2 Color Rules

**Hard bans:**
- `blue`, `bright_blue`, `dodger_blue`, `steel_blue` — banned. Blue is the color
  of every AI tool on earth. Hephaestus is not that.
- `magenta`, `purple`, `violet`, `orchid` — banned. Purple is blue's accomplice.
- `cyan`, `bright_cyan`, `dark_cyan`, `turquoise` — banned. Cyan is blue wearing
  a hat. No.

**Semantic binding:**
Colors are bound to meaning, never used decoratively. If green appears, something
succeeded. If red appears, something failed. Gold means "Hephaestus brand / attention."
Ember means "you can act on this." Breaking these bindings is a design defect.

| Meaning                  | Color         | Symbol pairing |
|--------------------------|---------------|----------------|
| Success / passed / done  | Spark Green   | `\u2713`             |
| Failure / error / fatal  | Furnace Red   | `\u2717`             |
| Warning / caution        | Caution       | `\u26a0`             |
| Brand / section header   | Molten Gold   | (none)         |
| Actionable / interactive | Ember         | `\u25b8` or `\u2192`        |
| Data / neutral           | Iron / Steel  | (none)         |
| Secondary / metadata     | Slag          | (none)         |

**Never color alone.** Every colored element must also carry a text or symbol
indicator that communicates the same meaning without color. This is not optional
accessibility — it is a hard design requirement. Score bars, verdict strings, and
status labels must all be readable on a monochrome terminal.

### 2.3 Rich Style Constants (Implementation)

These constants replace the current set in `cli/display.py`:

```python
# ── Hephaestus Forge Palette ──────────────────────────────────────────
GOLD        = "bold yellow"          # Primary brand
AMBER       = "yellow"              # Secondary headers, labels
EMBER       = "dark_orange"         # Interactive / actionable elements
WHITE_HOT   = "bold white"          # Emphasized body text
IRON        = "white"               # Standard body text
SLAG        = "dim"                 # Metadata, secondary
GREEN       = "bold green"          # Success
RED         = "bold red"            # Error
CAUTION     = "yellow"              # Warning (with symbol)
STEEL       = "grey70"             # Neutral data
```

**Removed constants:** `CYAN`, `CYAN_BOLD`, `BLUE`, `MAGENTA`. Every reference to
these must be migrated to the appropriate palette color above. The migration table:

| Old constant  | New constant | Rationale                                   |
|---------------|-------------|---------------------------------------------|
| `CYAN`        | `EMBER`     | Interactive elements, commands, UI accents   |
| `CYAN_BOLD`   | `WHITE_HOT` | Emphasized names, bold interactive elements  |
| `BLUE`        | `STEEL`     | Neutral data display                         |
| `MAGENTA`     | `AMBER`     | Secondary emphasis                           |

---

## 3. Typography & Symbols

### 3.1 Symbol Vocabulary

A fixed, small symbol set. No emoji except the hammer (`\u2692\ufe0f`) in the banner.
Every symbol has a Unicode version and an ASCII fallback.

```
PURPOSE              UNICODE    ASCII     CONTEXT
───────────────────────────────────────────────────────────
Success              \u2713          v         Stage complete, tests passed
Failure              \u2717          x         Stage failed, errors
Warning              \u26a0          !         Cautions, structural weaknesses
Arrow / next         \u2192          ->        Suggestions, navigation, mapping
Bullet / list        \u2022          *         List items
Action pointer       \u25b8          >         Menu items, recommended actions
Progress filled      \u2588          #         Score bar filled
Progress empty       \u2591          .         Score bar empty
Spinner              dots       -         Stage in-progress (Rich spinner)
Section rule         \u2500          -         Horizontal separator
```

**No symbols beyond this set.** No `\ud83d\udca1`, no `\ud83d\ude80`, no `\u2728`, no `\ud83d\udee1\ufe0f`. The one permitted
emoji is `\u2692\ufe0f` (hammer and pick) in the banner, because it is the literal tool
of Hephaestus.

### 3.2 Text Hierarchy

Three levels of emphasis, expressed through Rich styles:

```
Level 1 (Primary):    [bold yellow]SECTION HEADER[/]
Level 2 (Secondary):  [yellow]Label:[/] [white]value[/]
Level 3 (Tertiary):   [dim]metadata, timestamps, hints[/]
```

Section headers are always UPPERCASE. Labels use Title Case followed by a colon.
Values are unstyled or Iron. Metadata is always Slag (dim).

---

## 4. Layout Patterns

### 4.1 Vertical Rhythm

Every discrete block of content is separated by exactly one blank line. No double
blanks. No zero blanks between unrelated content. The rhythm is:

```
[blank]
SECTION HEADER
  content line
  content line
[blank]
SECTION HEADER
  content line
[blank]
```

Indentation is always **2 spaces** for content nested under a header. Table content
handles its own internal spacing via Rich padding.

### 4.2 Horizontal Rules

Rich rules (`console.rule()`) use `style="yellow"` for major section breaks and
`style="dim yellow"` for minor separators within a report. Rules never carry text
except the report title rule.

### 4.3 Panels

Panels are used sparingly — only for:
- The startup banner
- Error messages (red border)
- Key Insight blocks in invention reports (dim yellow border)
- Lens Engine and Pantheon summary blocks (dim yellow border)
- Help text (yellow border)

Panel borders are **never** any color outside the palette. No `border_style="cyan"`,
no `border_style="blue"`.

### 4.4 Tables

Tables use `box.SIMPLE_HEAD` for data tables (cost breakdown, structural mapping,
comparisons) and `box.SIMPLE` for key-value tables (status, vault info). Table
`border_style` is always `"yellow"` or `"dim yellow"`. Column styles follow the
palette — headers in Amber, data in Iron, accents in Ember.

### 4.5 Score Bars

Score bars render as `\u2588\u2588\u2588\u2588\u2588\u2588\u2591\u2591\u2591\u2591 0.63`. The filled portion uses the semantic color
for what is being measured:
- Domain distance, structural fidelity: Spark Green
- Novelty score: Molten Gold
- Debt score (ForgeBase lint): tiered — Green (<10), Caution (10-50), Red (>50)

The numeric value always appears after the bar. The bar is 10 characters wide.

---

## 5. Component Specifications

### 5.1 Banner

```
\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
  \u2692\ufe0f  HEPHAESTUS \u2014 The Invention Engine
\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
```

- "HEPHAESTUS" in `GOLD`
- "The Invention Engine" in `AMBER`
- Dash in `SLAG`
- Panel border: `yellow`, `padding=(0, 2)`, `expand=False`
- One blank line above and below

### 5.2 Pipeline Progress (StageProgress)

Each stage renders as a single updating line managed by `Rich.Progress`:

```
\u25cf Stage 1/5 Decompose  Extracting abstract structural form    3.2s
\u2713 Stage 1/5 Decompose  2.1s
\u25cf Stage 2/5 Search     Scanning knowledge domains              0:05
\u2717 Stage 3/5 Score      Embedding service timeout
```

| Element           | Style             |
|-------------------|-------------------|
| Spinner (active)  | `EMBER` dots      |
| `\u2713` (complete)    | `GREEN`           |
| `\u2717` (failed)      | `RED`             |
| "Stage N/5"       | `SLAG`            |
| Stage name        | `AMBER`           |
| Description       | `SLAG`            |
| Elapsed time      | `SLAG`            |
| Error message     | `RED`             |

The spinner style is `dots` in Ember. Not `line`, not `arc`, not `moon`. `dots`.

### 5.3 Invention Result Summary (Post-Pipeline)

The compact result shown immediately after a pipeline run, before the menu:

```
  \u2692\ufe0f  Thermoelastic Resonance Bridge
  Source: Piezoelectric Crystal Lattice Theory
  Novelty: 0.87  Feasibility: HIGH  Cost: $0.1423  Time: 34s
  Lens engine: 3 bundles, 12 lenses, cohesion=0.91
  Saved snapshot: resonance-bridge-2026-04-05.json
```

| Element           | Style                |
|-------------------|----------------------|
| Invention name    | `GOLD`               |
| "Source:" label   | `SLAG`               |
| Source domain val  | `EMBER`             |
| "Novelty:" label  | `SLAG`               |
| Novelty value     | `GOLD`               |
| "Feasibility:"    | `SLAG`               |
| Feasibility val   | `EMBER`              |
| "Cost:" label     | `SLAG`               |
| Cost value        | `GREEN`              |
| "Time:" label     | `SLAG`               |
| Time value        | `EMBER`              |
| Lens/Pantheon     | `SLAG` label, `EMBER` values |
| Snapshot path     | `SLAG` label, `EMBER` filename |

### 5.4 Post-Invention Menu

```
  What next?
  [1] View full report          [4] Try different problem
  [2] Explore alternatives      [5] Export (markdown/json/text/pdf)
  [3] Refine this invention     [6] Re-run from this source domain
  [7] Agent chat about this invention
  Or type a new problem to invent something else.
```

| Element           | Style               |
|-------------------|----------------------|
| "What next?"      | `SLAG`               |
| `[1]` indices     | `AMBER`              |
| Menu text         | `IRON`               |
| Hint line         | `SLAG`               |

Menu indices are `[N]` not `(N)` and not `N.` — bracket style is the standard.

### 5.5 Invention Report (Full)

The full report (`/1` or `--trace`) follows this skeleton:

```
\u2500\u2500 \u2692\ufe0f  HEPHAESTUS \u2014 Invention Report \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
  Generated: 2026-04-05 14:30:00 UTC  Session: a1b2c3

  PROBLEM:
  <problem text>

  STRUCTURAL FORM:
  <mathematical shape>
  Native domain: <domain>

\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

  INVENTION: Thermoelastic Resonance Bridge
  SOURCE DOMAIN: Piezoelectric Crystal Theory

  DOMAIN DISTANCE:    \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2591\u2591 0.82
  STRUCTURAL FIDELITY:\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2591\u2591\u2591 0.71
  NOVELTY SCORE:      \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2591 0.87
  FEASIBILITY:        HIGH
  VERDICT:            NOVEL

\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

  KEY INSIGHT:
  \u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510
  \u2502 The key insight text appears here in a       \u2502
  \u2502 dim-yellow-bordered panel.                    \u2502
  \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518

  STRUCTURAL MAPPING:
   Source Element       \u2192   Target Element        Mechanism
   crystal oscillator   \u2192   request rate sensor   frequency detection
   piezo feedback       \u2192   load signal           strain measurement

  ADVERSARIAL VERIFICATION:
  \u2713 No fatal flaws found

  \u26a0 Structural weaknesses:
    \u26a0 Thermal coupling assumes linear response
    \u26a0 Scale factor untested above 10k RPS

  RECOMMENDED NEXT STEPS:
    \u25b8 Prototype the frequency detection layer
    \u25b8 Validate thermal model at scale

\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

  COST BREAKDOWN:
   Stage          Cost (USD)
   Decompose        $0.0312
   Search           $0.0089
   Translate        $0.0821
   Verify           $0.0201
   TOTAL            $0.1423

  Models: claude-opus-4 + gpt-5  Time: 34.2s

\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

  RECOMMENDED USAGE:
    heph --refine       Iterate on this invention
    heph --depth N      Explore deeper (novelty 0.87)
    heph --domain X     Try a different source domain

\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
```

Styling rules within the report:

| Element                    | Style            |
|----------------------------|------------------|
| Report title rule          | `GOLD` text, `yellow` rule |
| "Generated:" / "Session:"  | `SLAG` label, `EMBER` value |
| Section headers (PROBLEM, etc.) | `GOLD`    |
| Section body text          | `IRON`           |
| "Native domain:" label     | `SLAG`           |
| Domain value               | `EMBER`          |
| Invention name             | `bold` + `AMBER` |
| Source domain               | `EMBER`         |
| Score labels               | `SLAG`           |
| Score bars (distance/fidelity) | `GREEN`     |
| Score bar (novelty)        | `GOLD`           |
| Feasibility value          | `EMBER`          |
| Verdict: NOVEL             | `GREEN`          |
| Verdict: QUESTIONABLE      | `AMBER`          |
| Verdict: DERIVATIVE        | `CAUTION`        |
| Verdict: INVALID           | `RED`            |
| Key insight panel          | `dim yellow` border |
| Mapping table headers      | `AMBER`          |
| Mapping source column      | `EMBER`          |
| Mapping target column      | `AMBER`          |
| Mapping mechanism          | `SLAG`           |
| Mapping arrow              | `SLAG`           |
| Fatal flaws                | `RED` + `\u2717`       |
| "No fatal flaws"           | `GREEN` + `\u2713`     |
| Structural weaknesses      | `AMBER` + `\u26a0`     |
| Next steps                 | `EMBER` + `\u25b8`     |
| Cost table stage names     | `AMBER`          |
| Cost table values          | `GREEN`          |
| Cost total                 | `bold green`     |
| Models/time footer         | `SLAG` label, `EMBER` value |
| Recommended commands       | `EMBER` command, `SLAG` description |

### 5.6 REPL Prompt

```
heph> _
heph[resonance-bridge]> _
```

| Element               | Style            |
|-----------------------|------------------|
| `heph`                | `bold yellow`    |
| `[slug]`              | `dim`            |
| `>`                   | (unstyled)       |

The prompt is minimal. No timestamp, no backend indicator, no decoration.
Backend status belongs in `/status`, not the prompt.

### 5.7 Help Panel

```
\u250c\u2500 Help \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510
\u2502                                              \u2502
\u2502 Quick Start                                  \u2502
\u2502   Type a problem in plain English...         \u2502
\u2502                                              \u2502
\u2502 Session                                      \u2502
\u2502   /help             Show this help            \u2502
\u2502   /status           Session info...           \u2502
\u2502   ...                                        \u2502
\u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518
```

| Element               | Style            |
|-----------------------|------------------|
| Panel title           | `bold yellow`    |
| Panel border          | `yellow`         |
| Category headers      | `bold yellow`    |
| Command names         | `EMBER`          |
| Command descriptions  | `IRON`           |

Previously command names were cyan. They must be Ember — they are actionable
things the user types.

### 5.8 Error Display

```
\u250c\u2500 Error \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510
\u2502 \u2717 Connection timeout after 30s               \u2502
\u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518

  Hint: Check network connectivity or retry with --timeout 60
```

| Element               | Style            |
|-----------------------|------------------|
| Panel title           | `bold red`       |
| Panel border          | `red`            |
| Error text            | `RED`            |
| "Hint:" label         | `SLAG`           |
| Hint text             | `IRON`           |

Error messages must follow the three-part pattern:
1. **What went wrong** (in the panel)
2. **What's valid** (if applicable, as hint)
3. **How to fix it** (as hint with a concrete command)

### 5.9 Warning Display

```
  \u26a0 API rate limit approaching (82/100 requests this minute)
```

Single line. `\u26a0` in `AMBER`, message text in `SLAG`. No panel, no box.
Warnings are informational, not blocking.

### 5.10 Success Display

```
  \u2713 Invention saved to ~/.hephaestus/inventions/resonance-bridge.json
```

Single line. `\u2713` in `GREEN`, message text in `IRON`. No panel, no box.

### 5.11 ForgeBase Surfaces

ForgeBase display follows the same palette. Specific mappings:

| ForgeBase element     | Style            |
|-----------------------|------------------|
| Vault ID              | `EMBER`          |
| Vault name            | `WHITE_HOT`      |
| Entity counts         | `EMBER`          |
| Lint debt score       | Tiered (Green/Amber/Red) |
| Category names        | `AMBER`          |
| Severity labels       | `RED` (critical/error), `AMBER` (warning), `SLAG` (info) |
| Bridge concepts       | `WHITE_HOT`      |
| Confidence values     | `AMBER`          |
| Vault table borders   | `yellow`         |
| Panel titles          | `bold yellow`    |

### 5.12 Batch Mode

Batch results render as a summary table after all problems complete:

```
  Batch complete: 8/10 succeeded, 2 failed (4m 12s)

   #   Problem                        Status    Invention              Time
   1   Load balancer for spiky...     \u2713 done    Thermoelastic Bridge   34s
   2   Self-healing mesh network      \u2713 done    Mycorrhizal Routing    28s
   3   Quantum key distribution       \u2717 fail    (timeout)              60s
   ...
```

| Element               | Style            |
|-----------------------|------------------|
| Summary line          | `IRON`           |
| Success count         | `GREEN`          |
| Failure count         | `RED`            |
| Duration              | `SLAG`           |
| Row index             | `SLAG`           |
| Problem (truncated)   | `IRON`           |
| `\u2713 done`              | `GREEN`          |
| `\u2717 fail`              | `RED`            |
| Invention name        | `AMBER`          |
| Time per problem      | `SLAG`           |

### 5.13 Onboarding Wizard

The first-run wizard uses conversational prompts with minimal decoration:

```
  \u2692\ufe0f  Welcome to Hephaestus.

  Let's set up your backend. How do you want to connect?

    [1] API keys (Anthropic + OpenAI)
    [2] Claude Max (uses your browser login)
    [3] Claude CLI (uses the claude command)
    [4] OpenRouter

  Choice (1-4): _
```

| Element               | Style            |
|-----------------------|------------------|
| Welcome line          | `GOLD` for name, `IRON` for text |
| Prompt question       | `IRON`           |
| Option indices        | `AMBER`          |
| Option text           | `IRON`           |
| Input prompt          | `IRON`           |

No panels during onboarding. Clean, conversational flow. The user is already
overwhelmed by a new tool — don't add visual noise.

---

## 6. UX Principles (Applied to Hephaestus)

These principles are adapted from the CLI Design Architect framework and
applied specifically to Hephaestus's surfaces.

### 6.1 Familiarity

**Convention compliance:**
- `--help` / `-h` on every command and subcommand
- `--version` prints `hephaestus-ai vX.Y.Z` and exits
- `--verbose` / `--quiet` for output control
- `--no-color` disables all ANSI color (must respect `NO_COLOR` env var)
- Exit code 0 = success, 1 = error, 130 = interrupted (SIGINT)

**Slash commands follow `/verb` pattern:**
`/help`, `/status`, `/refine`, `/export`, `/save`, `/load`, `/quit`
Not `/show-help`, not `/getStatus`, not `/HELP`.

**Flags follow GNU conventions:**
- Short flags: single dash, single letter (`-d 5`)
- Long flags: double dash, words (`--depth 5`)
- Boolean flags: no value needed (`--trace`, `--cost`)

### 6.2 Discoverability

**Progressive disclosure:**
1. No-argument invocation opens the REPL with a banner and prompt
2. `/help` shows all commands grouped by category
3. Each command shows its own usage on error
4. Tab completion covers all slash commands

**The post-invention menu** is the primary discovery mechanism. After every
pipeline run, the numbered menu shows the 7 most common next actions. Users
never need to memorize commands to be productive.

**Implicit help:** When a user types an invalid slash command, suggest the
closest match:

```
  \u2717 Unknown command: /rfine
  Did you mean /refine?
```

### 6.3 Feedback

**Pipeline stages** provide real-time feedback via Rich Progress spinners.
Each stage transition is visible. Each completion shows elapsed time.

**Feedback timing thresholds:**

| Duration     | Required feedback                        |
|--------------|------------------------------------------|
| < 0.5s       | Completion confirmation only             |
| 0.5 - 2s     | "Working..." or spinner                  |
| 2 - 10s      | Spinner with stage name and description  |
| > 10s         | Spinner + elapsed time + what's happening |

**Post-action confirmation:**
Every mutation gets a confirmation line:
- `/save` -> `\u2713 Saved to ~/.hephaestus/inventions/name.json`
- `/context add` -> `\u2713 Context added (3 items total)`
- `/clear` -> `\u2713 Context cleared`
- `/backend api` -> `\u2713 Backend switched to api`

Silent mutations are a defect.

### 6.4 Clarity

**Information hierarchy in the invention result:**
1. Invention name + source domain (what you got)
2. Scores: novelty, feasibility, cost, time (how good is it)
3. Post-invention menu (what to do next)

This is the "inverted pyramid" — most important information first. The full
report (`[1]`) adds detail; the summary gives you enough to decide.

**Table alignment:** All tables use consistent column widths within a given
surface. Score labels are right-padded to align their values. Cost values
are right-aligned.

**Truncation:** Long text (problem descriptions, key insights, domain names)
truncates at 120 characters with `\u2026` in dim. Full text is available in the
detailed report view.

### 6.5 Flow

**Minimal-friction paths:**
- Entering a problem string directly runs the pipeline (no subcommand needed)
- Pressing `1` after a result shows the full report (no `/` prefix needed)
- `/refine` with no argument re-runs with the same problem
- `/deeper` with no argument increments depth by 1

**Scriptable usage:**
```bash
# Single problem, exit with result
heph "my problem" --format json --quiet

# Batch mode
heph --batch problems.txt --output ./results/

# Pipe-friendly (JSON to stdout, no color)
heph "my problem" --format json --no-color | jq .top_invention
```

**Keyboard interrupt handling:**
`Ctrl+C` during a pipeline run cancels the current stage cleanly, prints
`\u2717 Cancelled`, and returns to the prompt. It does not kill the process.
`Ctrl+C` at the prompt shows "Type /quit to exit." `Ctrl+D` at an empty
prompt exits cleanly.

### 6.6 Forgiveness

**Error recovery:**
- API key missing: Error panel + concrete fix command
  (`Set ANTHROPIC_API_KEY or run /backend claude-max`)
- Model timeout: Error + retry suggestion (`Retry with /deeper or /refine`)
- Invalid depth: Error + valid range (`Depth must be 1-10. Current: 3`)

**Destructive action protection:**
- `/clear` clears context but not invention history
- No command deletes saved inventions from disk
- `/quit` during an active pipeline warns before exiting

**Typo tolerance:**
The command registry should support fuzzy matching for slash commands.
Levenshtein distance <= 2 triggers a "Did you mean?" suggestion rather
than a bare "Unknown command" error.

---

## 7. Accessibility

### 7.1 Color Independence

Every piece of information conveyed by color is also conveyed by:
- A symbol (`\u2713`, `\u2717`, `\u26a0`, `\u25b8`)
- A text label (`NOVEL`, `FAILED`, `HIGH`)
- A numeric value (`0.87`)

A user running `--no-color` or piping to a file loses nothing meaningful.

### 7.2 NO_COLOR Support

The `NO_COLOR` environment variable (https://no-color.org/) is respected.
When set, all ANSI color codes are suppressed. Rich's `Console(no_color=True)`
handles this, but the detection logic must also check:

```python
import os, sys

def _should_use_color() -> bool:
    if os.getenv("NO_COLOR") is not None:
        return False
    if "--no-color" in sys.argv:
        return False
    if not sys.stdout.isatty():
        return False
    return True
```

### 7.3 Terminal Width

All output respects `shutil.get_terminal_size()`. Tables wrap or truncate
rather than overflowing. The minimum supported width is 60 columns. Below
that, Rich's built-in wrapping handles graceful degradation.

### 7.4 Unicode Fallback

On terminals that cannot render Unicode (detected by encoding check),
fall back to ASCII equivalents. The symbol table in section 3.1 defines
every fallback.

---

## 8. Anti-Patterns (Banned)

These are things that must never appear in the Hephaestus CLI:

| Anti-Pattern                           | Why                                         |
|----------------------------------------|---------------------------------------------|
| Blue, purple, or cyan text             | AI-slop aesthetics. We run hot.             |
| Emoji beyond `\u2692\ufe0f`                         | Childish. This is heavy machinery.          |
| Animated spinners (bouncing, pulsing)  | Distracting. `dots` only.                   |
| Double-bordered panels (`box.DOUBLE`)  | Noisy. `SIMPLE_HEAD` or `SIMPLE` only.      |
| Color without symbol/text backup       | Accessibility failure.                      |
| Silent mutations                       | Users must see confirmation.                |
| Vague errors ("Something went wrong")  | Always: what + valid + how-to-fix.          |
| Trailing summaries after tool actions  | The output IS the summary. Don't narrate.   |
| Decorative horizontal rules            | Rules separate content. No aesthetic rules. |
| Gradient or rainbow text               | This is a forge, not a pride parade float.  |
| "Loading..." without context           | Always say WHAT is loading.                 |
| Nested panels (panel inside panel)     | Visual noise. Flatten the hierarchy.        |

---

## 9. Migration Checklist

To bring the current codebase into compliance with this design:

- [ ] `display.py`: Replace color constants (remove CYAN, CYAN_BOLD, BLUE, MAGENTA;
      add EMBER, WHITE_HOT, STEEL)
- [ ] `display.py`: Update all `style=CYAN` references to use EMBER or appropriate
      palette color per the migration table in section 2.3
- [ ] `display.py`: Change spinner style from `style=CYAN` to `style=EMBER`
- [ ] `repl.py`: Update HELP_TEXT to use `[dark_orange]` instead of `[cyan]`
      for all slash command names
- [ ] `repl.py`: Update prompt text colors
- [ ] `repl.py`: Update `_display_invention_result` colors
- [ ] `repl.py`: Update post-invention menu colors
- [ ] `repl.py`: Update all `[cyan]` references in status, usage, compare displays
- [ ] `forgebase_display.py`: Update all CYAN imports and references to EMBER
- [ ] `forgebase_commands.py`: Update any inline color references
- [ ] `config.py`: Update onboarding wizard colors
- [ ] `agent_chat.py`: Update any display colors
- [ ] `batch.py`: Update any display colors
- [ ] `main.py`: Verify banner and top-level output compliance
- [ ] All files: Verify no remaining `cyan`, `blue`, `magenta`, or `purple`
      string literals in Rich markup
- [ ] Test: Run `grep -rn "cyan\|blue\|magenta\|purple" src/hephaestus/cli/`
      and confirm zero matches (excluding this design doc reference)
