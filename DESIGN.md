---

# Design Specification: Aurora-Brutalist

## 1. Visual Philosophy
This design marries the rigid, structural honesty of **Brutalism** with the fluid, high-energy aesthetics of **Aurora** gradients. 

* **Structure:** Defined by heavy borders, hard shadows, and a strict grid.
* **Atmosphere:** Softened by "light leaks," mesh gradients, and glowing accents that break the rigidity of the layout.

## 2. Core Color Palette
The background must be a near-black base so the accents carry the luminance.

The values below are the ones `MODERN_CSS` in
[src/guiskindose/gui/styles.py](src/guiskindose/gui/styles.py) actually ships;
`styles.py` is the single source of truth and
[dev-docs/UI_values.md](dev-docs/UI_values.md) is generated from it by
`python scripts/generate_ui_values.py`. Change a colour there, regenerate, and
update this table in the same commit.

| Role | Variable | Hex | Description |
| :--- | :--- | :--- | :--- |
| **Surface** | `--bg-primary` | `#0e0e0e` | Near-black base. |
| **Elevation** | `--bg-secondary` | `#1d1d1d` | For cards and sidebars. |
| **Accent 1** | `--aurora-purple` | `#4338CA` | Navigation, primary actions, sidebar glow. |
| **Accent 2** | `--aurora-teal` | `#0D9488` | Input and load accents. |
| **Accent 3** | `--aurora-pink` | `#831843` | Status and highlights. |
| **Text** | `--text-main` | `#F8FAFC` | High-contrast, crisp white. |
| **Muted text** | `--text-muted` | `#94A3B8` | Secondary text and captions. |
| **Border** | `--glass-border` | `rgba(255, 255, 255, 0.15)` | Sharp, defined structural lines. |
| **Dose severity** | `--dose-pending` | `#94A3B8` | Not calculated yet. |
| | `--dose-low` | `#22C55E` | Low band. |
| | `--dose-elevated` | `#FACC15` | Elevated band. |
| | `--dose-high` | `#EF4444` | High band. |

The three accents are deliberately darker than a "vibrant glow" reading of §1
would suggest, because they are used behind white text; `--aurora-purple` at
`#4338CA` is the one known contrast problem (2.44:1 on `--bg-primary`), which is
why it no longer carries any dose value — see the severity note below.

### Severity colours are semantic, not brand

The four `--dose-*` tokens are the **first semantic colours** in the palette — every other
colour above is brand or accent. They are deliberately exempt from the §5 "never use
middle-greys, keep the accent vibe" rule: their job is clinical signalling, not aesthetics,
so they are chosen for contrast against `--bg-primary` and for band legibility rather than
for the accent vibe. They carry no brand meaning and must not be reused as decoration.

**Colour is never the only carrier.** Green / yellow / red is not reliably distinguishable
for the most common colour-vision deficiencies, so every value in these colours also carries
a Material symbol keyed to the band and a tooltip naming the band and its range. The three
carriers move together in one helper; a band change that recolours the number but leaves a
stale tooltip is a bug, not a cosmetic issue. The band names, their numeric edges, and the
in-app wording live in `src/guiskindose/gui/dose_severity.py` and
`dev-docs/ui_copy.json` — never inline them at a call site, and state the edges in prose in
exactly one place: the Results help page.

## 3. Typography
The goal is "technical elegance." 

* **Headings:** Use a **Bold Sans-Serif** (e.g., *Inter*, *Geist*, or *Public Sans*). Set headings with slightly tighter letter spacing (`-0.02em`) to feel dense and impactful.
* **Body:** Keep it clean and crisp. Use a `1.6` line height to ensure readability against the dark background.
* **Data/Monospace:** Use a modern mono font (e.g., *JetBrains Mono*) for any system-level information or technical labels to reinforce the "built" look.

## 4. UI Components

### The "Glow-Border" Card
Brutalist cards usually have thick black borders. In this style, we use a **1px subtle border** that feels sharp, but we add a **Hard Accent Shadow**.
* **Shadow Style:** Instead of a blurry shadow, use a solid offset.
* **Example:** `box-shadow: 4px 4px 0px var(--aurora-purple);`

### Aurora Backgrounds
To mimic the feel of sites like Cursor but with more color, use "Radial Glares" placed behind the content:
* Place a large, blurred circle in the top-left (Teal) and bottom-right (Purple).
* Set the opacity to roughly `15%` so it feels like a soft light source rather than a distracting shape.

### High-Vibrancy Buttons
Buttons should be "Active Brutalist."
1.  **State 1 (Default):** Transparent background, 1px solid accent border.
2.  **State 2 (Hover):** Background fills with the accent color; add an outer glow (`drop-shadow`) to make it look like the button is emitting light onto the UI.

## 5. Layout Rules
* **Grid-First:** Everything must align to a strict 8px or 12px grid.
* **High Contrast:** Never use middle-greys for text. If it's not the primary text, use a muted version of your accent colors (e.g., a dark purple-grey) to keep the "vibe" consistent.
* **Micro-Motion:** Use snappy transitions. `100ms ease-out` for hover states. If an element expands, it should snap into place, reflecting the brutalist foundation.

---

### Global CSS sketch (illustrative, not the shipped stylesheet)

This shows the shape of the implementation only. The stylesheet that actually
runs is `MODERN_CSS` in [src/guiskindose/gui/styles.py](src/guiskindose/gui/styles.py);
read the §2 table or [dev-docs/UI_values.md](dev-docs/UI_values.md) for the live
values, and do not copy hexes out of this block.

```css
:root {
  --bg-primary: #0e0e0e;
  --aurora-purple: #4338CA;
  --glass-border: rgba(255, 255, 255, 0.15);
}

body {
  background-color: var(--bg-primary);
  color: var(--text-main);
  /* Aurora Mesh Background */
  background-image:
    radial-gradient(at 0% 0%, rgba(126, 145, 194, 0.16) 0px, transparent 55%),
    radial-gradient(at 100% 100%, rgba(107, 125, 138, 0.15) 0px, transparent 60%);
}

.card {
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  backdrop-filter: blur(10px);
  box-shadow: 5px 5px 0px var(--aurora-purple); /* Brutalist shadow */
}
```
