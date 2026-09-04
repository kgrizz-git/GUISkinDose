"""Modern/Material design CSS for the GUISkinDose GUI.

Single source of truth for the app's design tokens. After editing, regenerate
dev-docs/UI_values.md:
    python scripts/generate_ui_values.py
"""

MODERN_CSS = r"""
:root {
    --bg-primary: #0e0e0e;
    --bg-secondary: #1d1d1d;
    --aurora-purple: #4338CA;
    --aurora-teal: #0D9488;
    --aurora-pink: #831843;
    --text-main: #F8FAFC;
    --text-muted: #94A3B8;
    --glass-bg: rgba(33, 33, 33, 0.70);
    --glass-bg-hover: rgba(33, 33, 33, 0.85);
    --glass-border: rgba(255, 255, 255, 0.15);
    --shadow-soft: 0 4px 24px rgba(0, 0, 0, 0.4);
    --shadow-hover: 0 8px 32px rgba(0, 0, 0, 0.5);
    --glow-blue: rgba(59, 130, 246, 0.3);
    --glow-purple: rgba(99, 102, 241, 0.3);
}

.text-aurora-purple { color: var(--aurora-purple) !important; }
.text-aurora-teal { color: var(--aurora-teal) !important; }
.text-aurora-pink { color: var(--aurora-pink) !important; }

body {
    background-color: var(--bg-primary) !important;
    color: var(--text-main) !important;
    font-family: 'Inter', -apple-system, sans-serif;
    background-image:
        radial-gradient(at 100% 0%, rgba(165, 141, 149, 0.17) 0%, transparent 55%),
        radial-gradient(at 0% 0%, rgba(126, 145, 194, 0.16) 0%, transparent 55%),
        radial-gradient(at 100% 100%, rgba(107, 125, 138, 0.15) 0%, transparent 60%) !important;
    background-attachment: fixed;
}

.nicegui-content { background: transparent !important; }

.q-table th {
    font-weight: 800 !important;
    color: var(--text-main) !important;
    text-transform: uppercase;
    font-size: 0.75rem;
    background: rgba(255, 255, 255, 0.05) !important;
    border-bottom: 2px solid #3d3d4d !important;
}

.q-table td {
    color: var(--text-main) !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
}

.modern-header {
    background-color: rgba(10, 10, 10, 0.95) !important;
    backdrop-filter: blur(24px) saturate(180%);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
    box-shadow: 0 4px 30px rgba(0,0,0,0.7) !important;
}

.q-drawer {
    background: linear-gradient(180deg, #0D0D0D 0%, #050505 100%) !important;
    background-image: radial-gradient(at 0% 100%, rgba(126, 145, 194, 0.12) 0%, transparent 65%) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
}

.modern-card {
    border-top: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-left: 1px solid rgba(255, 255, 255, 0.05) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
    background: var(--glass-bg) !important;
    backdrop-filter: blur(20px) saturate(150%);
    border-radius: 12px !important;
    box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.1),
        var(--shadow-soft),
        0 0 15px rgba(255, 255, 255, 0.05) !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.modern-card:hover {
    transform: translateY(-1px) !important;
    background: var(--glass-bg-hover) !important;
    box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.15),
        var(--shadow-hover),
        0 0 20px rgba(255, 255, 255, 0.08) !important;
}

.modern-toggle {
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    background: rgba(0, 0, 0, 0.4) !important;
    border-radius: 8px;
    overflow: hidden;
    backdrop-filter: blur(12px);
}

.modern-toggle .q-btn {
    border: 1px solid rgba(255, 255, 255, 0.05) !important;
    color: var(--text-muted) !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    font-size: 0.75rem;
    padding: 0 16px !important;
    border-radius: 0 !important;
}

.modern-toggle .q-btn--active {
    background: var(--q-primary) !important;
    color: white !important;
    border-color: var(--q-primary) !important;
}

.modern-btn {
    border-radius: 8px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    backdrop-filter: blur(12px) !important;
    background: rgba(30, 30, 30, 0.5) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
}

.modern-btn:hover {
    transform: scale(1.02) !important;
    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.4), 0 0 15px var(--glow-blue) !important;
    background: rgba(30, 30, 30, 0.6) !important;
}

.modern-btn-primary {
    background: linear-gradient(180deg, rgba(15, 118, 110, 0.4) 0%, rgba(13, 100, 92, 0.3) 100%) !important;
    border: 1px solid rgba(20, 184, 166, 0.4) !important;
    border-radius: 8px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    backdrop-filter: blur(12px) !important;
}

.modern-btn-primary:hover {
    transform: scale(1.02) !important;
    background: linear-gradient(180deg, rgba(20, 184, 166, 0.5) 0%, rgba(13, 100, 92, 0.4) 100%) !important;
    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.4), 0 0 20px var(--glow-blue) !important;
}

.modern-btn-secondary {
    background: linear-gradient(180deg, rgba(67, 56, 202, 0.4) 0%, rgba(55, 48, 163, 0.3) 100%) !important;
    border: 1px solid rgba(99, 102, 241, 0.4) !important;
    border-radius: 8px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    backdrop-filter: blur(12px) !important;
}

.modern-btn-secondary:hover {
    transform: scale(1.02) !important;
    background: linear-gradient(180deg, rgba(99, 102, 241, 0.5) 0%, rgba(55, 48, 163, 0.4) 100%) !important;
    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.4), 0 0 20px var(--glow-purple) !important;
}

/* Override Quasar button colors with glassmorphism */
.q-btn, .q-btn--flat, .q-btn--outline,
.q-btn.bg-deep-purple, .q-btn.text-deep-purple,
.q-btn.bg-primary, .q-btn.text-primary,
.q-btn.bg-positive, .q-btn.text-positive,
.q-btn.bg-teal, .q-btn.text-teal,
.q-btn--standard {
    background: rgba(30, 30, 30, 0.5) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
}

.q-btn:hover, .q-btn--flat:hover, .q-btn--outline:hover,
.q-btn.bg-deep-purple:hover, .q-btn.text-deep-purple:hover,
.q-btn.bg-primary:hover, .q-btn.text-primary:hover,
.q-btn.bg-positive:hover, .q-btn.text-positive:hover,
.q-btn.bg-teal:hover, .q-btn.text-teal:hover,
.q-btn--standard:hover {
    background: rgba(30, 30, 30, 0.6) !important;
    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.4), 0 0 15px var(--glow-blue) !important;
}

/* Glassmorphism for separators and dividers */
.q-separator, .q-divider {
    background: rgba(255, 255, 255, 0.1) !important;
    box-shadow: 0 0 10px rgba(255, 255, 255, 0.05) !important;
}

/* Upload component styling */
.q-uploader, .q-uploader__header {
    background: rgba(30, 30, 30, 0.4) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-radius: 12px !important;
    box-shadow: 0 0 15px rgba(255, 255, 255, 0.05) !important;
}

.q-uploader:hover, .q-uploader__header:hover {
    background: rgba(30, 30, 30, 0.5) !important;
    box-shadow: 0 0 20px rgba(255, 255, 255, 0.08) !important;
}

.nav-item {
    position: relative;
    padding-left: 16px;
    transition: all 0.2s ease;
    border-radius: 8px;
}

.nav-item:hover {
    background: rgba(255, 255, 255, 0.01) !important;
}

.nav-item.active {
    color: #60A5FA !important;
    background: rgba(37, 99, 235, 0.1) !important;
}

.nav-item.active::before {
    content: '';
    position: absolute;
    left: 0;
    top: 12px;
    bottom: 12px;
    width: 2px;
    background: linear-gradient(180deg, #60A5FA 0%, #3B82F6 100%);
    border-radius: 1px;
}

.q-notification--positive {
    background: #064E3B !important;
    color: #d1fae5 !important;
    border: 1px solid #059669 !important;
    border-radius: 8px !important;
    backdrop-filter: blur(12px);
}

/* Uploader: hide quasar's internal file list. The loaded file is shown by our
   own card below the drop zone, so quasar's per-file cards/checkmarks are
   redundant — and were confusing (they accumulated across consecutive uploads
   and flashed on each load). The drop-zone header (prompt) stays visible. */
.uploader-no-list .q-uploader__list {
    display: none;
}

/* Sticky/frozen column headers for the Data-tab event table (raw + normalized).
   The virtual-scroll container (.q-table__middle) scrolls; the header row sticks
   to its top. The background must be OPAQUE (the base .q-table th uses a
   translucent fill) so scrolled rows do not bleed through the pinned header. The
   higher-specificity selector below wins over ".q-table th" despite both using
   !important. */
.sticky-header thead tr th {
    position: sticky;
    top: 0;
    z-index: 2;
    background-color: #191919 !important;
}
"""
