---

# Design Specification: Aurora-Brutalist

## 1. Visual Philosophy
This design marries the rigid, structural honesty of **Brutalism** with the fluid, high-energy aesthetics of **Aurora** gradients. 

* **Structure:** Defined by heavy borders, hard shadows, and a strict grid.
* **Atmosphere:** Softened by "light leaks," mesh gradients, and glowing accents that break the rigidity of the layout.

## 2. Core Color Palette
The background must be a true "Deep Black" to allow the vibrant accents to achieve maximum luminance.

| Role | Variable | Hex | Description |
| :--- | :--- | :--- | :--- |
| **Surface** | `--bg-primary` | `#050505` | Absolute dark base. |
| **Elevation** | `--bg-secondary` | `#0D0D0D` | For cards and sidebars. |
| **Accent 1** | `--aurora-purple` | `#A855F7` | Primary glow and brand color. |
| **Accent 2** | `--aurora-teal` | `#2DD4BF` | Secondary glow for contrast. |
| **Accent 3** | `--aurora-pink` | `#EC4899` | Tertiary highlight. |
| **Text** | `--text-main` | `#F8FAFC` | High-contrast, crisp white. |
| **Border** | `--border-brutal` | `#262626` | Sharp, defined structural lines. |

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

### Global CSS Implementation (Refined)
```css
:root {
  --bg: #050505;
  --accent: #A855F7;
  --border: #262626;
}

body {
  background-color: var(--bg);
  color: #ffffff;
  /* Aurora Mesh Background */
  background-image: 
    radial-gradient(at 0% 0%, rgba(168, 85, 247, 0.15) 0px, transparent 50%),
    radial-gradient(at 100% 100%, rgba(45, 212, 191, 0.1) 0px, transparent 50%);
}

.card {
  border: 1px solid var(--border);
  background: rgba(13, 13, 13, 0.7);
  backdrop-filter: blur(10px);
  box-shadow: 5px 5px 0px var(--accent); /* Brutalist shadow */
}
```
