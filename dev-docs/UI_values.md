# UI Values — MyPySkinDose

This document maps the primary design tokens (colors, gradients, effects) used in the MyPySkinDose GUI. All values are defined in [src/mypyskindose/gui/app.py](../src/mypyskindose/gui/app.py) within the `MODERN_CSS` constant.

> **IMPORTANT:** If you modify any CSS values in `app.py`, please update this file to keep it in sync.

## 🎨 Color Palette (CSS Variables)

| Variable | Value | Purpose |
| :--- | :--- | :--- |
| `--bg-primary` | `#0e0e0e` | Main black background |
| `--bg-secondary` | `#1d1d1d` | Secondary background (panels, drawer) |
| `--aurora-purple` | `#4338CA` | Navigation, Primary actions, & Sidebar glow (Darker Indigo) |
| `--aurora-teal` | `#0D9488` | Input & Load accents (True Teal) |
| `--aurora-pink` | `#831843` | Status & Highlights (Deep Pink) |
| `--text-main` | `#F8FAFC` | Primary text (White/Off-white) |
| `--text-muted` | `#94A3B8` | Secondary text (Grey) |
| `--glass-bg` | `rgba(33, 33, 33, 0.70)` | Card background (Sleek Modern) |
| `--glass-bg-hover` | `rgba(33, 33, 33, 0.85)` | Card hover background |
| `--glass-border` | `rgba(255, 255, 255, 0.15)` | Glass border color |
| `--glow-blue` | `rgba(59, 130, 246, 0.3)` | Blue glow for hover effects |
| `--glow-purple` | `rgba(99, 102, 241, 0.3)` | Purple glow for secondary buttons |

## ✨ Aurora Effects (Gradients)

Defined in the `body` and `.q-drawer` styles.

### Main Window Gradients
*   **Pink (Top-Right):** `rgba(165, 141, 149, 0.17)` (55% radius)
*   **Indigo (Top-Left):** `rgba(126, 145, 194, 0.16)` (55% radius)
*   **Blue-Cyan (Bottom-Right):** `rgba(107, 125, 138, 0.15)` (60% radius)

### Navigation Drawer
*   **Indigo Glow (Bottom-Left):** `rgba(126, 145, 194, 0.12)` (65% radius)

## 🔘 Component Styling

### Buttons (`.modern-btn`)
*   **Border:** `1px solid rgba(255, 255, 255, 0.15)`
*   **Background:** `rgba(30, 30, 30, 0.5)` with `backdrop-filter: blur(12px)`
*   **Hover:** Scale `1.02x`, background `rgba(30, 30, 30, 0.6)`, blue glow `0 0 15px`
*   **Primary:** Teal gradient `rgba(15, 118, 110, 0.4)` → `rgba(13, 100, 92, 0.3)`
*   **Secondary:** Purple gradient `rgba(67, 56, 202, 0.4)` → `rgba(55, 48, 163, 0.3)`

### Navigation (`.nav-item`)
*   **Hover:** `rgba(255, 255, 255, 0.01)` (very subtle)
*   **Active:** Blue `#60A5FA` text, `rgba(37, 99, 235, 0.1)` background
*   **Active Indicator:** Vertical line `2px` gradient `#60A5FA` → `#3B82F6`

### Cards (`.modern-card`)
*   **Border:** Top `rgba(255, 255, 255, 0.15)`, sides/bottom `rgba(255, 255, 255, 0.05)`
*   **Background:** `rgba(33, 33, 33, 0.8)` with `backdrop-filter: blur(20px) saturate(150%)`
*   **Border Radius:** `12px`
*   **Effects:** Inner glow `inset 0 1px 0 rgba(255, 255, 255, 0.1)`, soft shadow, white glow `0 0 15px rgba(255, 255, 255, 0.05)`
*   **Hover:** `translateY(-1px)`, background `rgba(33, 33, 33, 0.85)`, enhanced glow

### Toggle (`.modern-toggle`)
*   **Background:** `rgba(0, 0, 0, 0.4)` with `backdrop-filter: blur(12px)`
*   **Border:** `1px solid rgba(255, 255, 255, 0.08)`
*   **Border Radius:** `8px`

### Header (`.modern-header`)
*   **Background:** `rgba(10, 10, 10, 0.95)` with `backdrop-filter: blur(24px) saturate(180%)`
*   **Border:** Bottom `rgba(255, 255, 255, 0.08)`
*   **Shadow:** `0 4px 30px rgba(0,0,0,0.7)`

### Upload Component (`.q-uploader`)
*   **Background:** `rgba(30, 30, 30, 0.4)` with `backdrop-filter: blur(12px)`
*   **Border:** `1px solid rgba(255, 255, 255, 0.15)`
*   **Border Radius:** `12px`
*   **Glow:** `0 0 15px rgba(255, 255, 255, 0.05)`

### Notifications (`.q-notification--positive`)
*   **Background:** `#064E3B` (Dark emerald)
*   **Text:** `#d1fae5` (Light mint)
*   **Border:** `#059669`
*   **Border Radius:** `8px`
*   **Backdrop:** `blur(12px)`

## 📊 Summary Card (Tab 5)
*   **Labels:** `font-normal`, `text-[11px]`, `opacity-70`.
*   **Values:** `font-bold`, `text-[13px]`, `100% opacity`.
