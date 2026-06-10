# GUI Aesthetic Redesign Plan
## Transitioning from "Aurora-Brutalist" to "Sleek Modern/Material"

> **Status:** In Progress  
> **Target File:** `src/mypyskindose/gui/app.py`  
> **Current Version:** 1.1.0  
> **Aesthetic:** Aurora-Brutalist → Sleek Modern/Material

---

## Overview

The current GUI uses an "Aurora-Brutalist" aesthetic characterized by sharp edges, hard borders, and high contrast. This plan transitions the UI to a "Sleek Modern/Material" design with softer geometry, glassmorphism effects, and refined interactive elements.

**Key Design Goals:**
- Softer, more approachable visual language
- Enhanced depth through glassmorphism
- More intuitive navigation with subtle active states
- Modern, polished interactive feedback

---

## Implementation Checklist

> Update this checklist as changes are completed. Mark items with `[x]` when done.

### Phase 1: CSS Foundation
- [x] Create new CSS class names (duplicate AURORA_CSS as MODERN_CSS)
- [x] Rename classes: `.brutal-*` → `.modern-*`
- [x] Apply geometry changes (border-radius: 0px → 12px)
- [x] Replace hard borders with inner glow shadows
- [x] Update color variables (add glass-bg, glass-border, shadow-soft, shadow-hover)
- [ ] Test CSS in isolation (pending GUI launch - missing dependencies)

### Phase 2: Component Updates
- [x] Update all card references (`.brutal-card` → `.modern-card`)
- [x] Update button classes (`.brutal-btn` → `.modern-btn`)
- [x] Update primary button classes (`.brutal-btn-teal` → `.modern-btn-primary`)
- [x] Add gradient button variants (secondary, ghost)
- [x] Apply `.modern-header` to header
- [x] Update drawer CSS with new glassmorphism

### Phase 3: Navigation Redesign
- [x] Redesign navigation buttons (update `nav_btn()` function)
- [x] Implement active state indicator (vertical line)
- [x] Add hover transitions to navigation
- [x] Add Google Fonts stylesheet for Material Symbols Outlined
- [x] Update all icons to use outlined variants
- [x] Test icon rendering

**Note:** NiceGUI/Quasar uses its own icon system (Material Icons by default). The Google Fonts stylesheet for Material Symbols Outlined was added, but icons still render as filled Material Icons. To actually use Material Symbols Outlined would require either using raw HTML spans or configuring Quasar's icon system, which is more complex. The stylesheet is in place for future use if needed.

### Phase 4: Interactive Polish
- [x] Add hover effects to all interactive cards (in CSS)
- [ ] Test transitions and performance
- [x] Update toggle buttons (`.brutal-toggle` → `.modern-toggle`)
- [x] Improve toggle active state styling (in CSS)
- [ ] Verify responsive behavior
- [ ] Check mobile navigation (if applicable)

### Phase 5: Final Review
- [ ] Cross-browser testing (Chrome, Firefox, Safari, Edge)
- [ ] Verify backdrop-filter support (add fallback if needed)
- [ ] Accessibility check (contrast ratios, keyboard nav, screen reader)
- [x] Update `dev-docs/GUI_PLAN.md` §0 with new aesthetic (supersedes retired `UI_ANALYSIS.md`)
- [ ] Add screenshots to documentation
- [x] Update GUI_VERSION to 1.1.0
- [ ] Final QA testing

---

## Current State Analysis

### Existing CSS Classes (AURORA_CSS in `app.py`)

| Class | Current Style | Purpose |
|-------|--------------|---------|
| `.brutal-card` | `border-radius: 0px`, `border: 1px solid rgba(255,255,255,0.1)`, `background: rgba(13,13,13,0.8)` | Main card containers |
| `.brutal-header` | `border-bottom: 1px solid rgba(139,148,158,0.2)`, `backdrop-filter: blur(16px)` | Top navigation header |
| `.brutal-toggle` | `border-radius: 4px`, hard borders | Toggle buttons |
| `.brutal-btn` | Flat colors, no gradients | Action buttons |
| `.q-drawer` | `border-right: 2px solid var(--border-brutal)` | Left navigation pane |

### Current Color Variables

```css
--bg-primary: #090909;
--bg-secondary: #101010;
--aurora-purple: #4338CA;
--aurora-teal: #0D9488;
--aurora-pink: #831843;
--text-main: #F8FAFC;
--text-muted: #94A3B8;
--border-brutal: rgba(139, 148, 158, 0.2);
```

---

## Detailed Changes

### 1. Soften the Geometry

#### 1.1 Rounded Corners for Cards and Buttons

**Target:** All cards and buttons

**Current:**
```css
.brutal-card {
    border-radius: 0px !important;
}
```

**New:**
```css
.modern-card {
    border-radius: 12px !important;
}
```

**Implementation:**
- Rename `.brutal-card` → `.modern-card` throughout `app.py`
- Update all button classes to use `border-radius: 8px` for smaller buttons, `12px` for primary buttons
- Apply to: upload cards, settings expansions, geometry preview cards, data table cards

**Files to modify:**
- `src/mypyskindose/gui/app.py` — replace all `.brutal-card` class references (approx. 15 occurrences)

---

#### 1.2 Replace Hard Borders with Inner Glow

**Target:** Card containers

**Current:**
```css
.brutal-card {
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
}
```

**New:**
```css
.modern-card {
    border: none !important;
    box-shadow: 
        inset 0 1px 0 rgba(255, 255, 255, 0.1),
        0 4px 24px rgba(0, 0, 0, 0.4) !important;
}
```

**Rationale:** Inner glow (`inset` shadow) creates a floating effect without harsh borders, making elements feel integrated with the aurora background.

**Implementation:**
- Remove all `border` properties from card classes
- Add `box-shadow` with inset top highlight
- Add outer shadow for depth

---

### 2. Embrace Glassmorphism

#### 2.1 Heavier Blur Effect

**Target:** Header, drawer, and cards

**Current:**
```css
.brutal-header {
    backdrop-filter: blur(16px);
}
.brutal-card {
    backdrop-filter: blur(12px);
}
```

**New:**
```css
.modern-header {
    backdrop-filter: blur(24px) saturate(180%);
}
.modern-card {
    backdrop-filter: blur(20px) saturate(150%);
}
```

**Rationale:** Increased blur + saturation creates a more pronounced glass effect, allowing aurora colors to bleed through while maintaining readability.

---

#### 2.2 Variable Opacity for Background Bleed-Through

**Target:** Card backgrounds

**Current:**
```css
.brutal-card {
    background: rgba(13, 13, 13, 0.8) !important;
}
```

**New:**
```css
.modern-card {
    background: rgba(13, 13, 13, 0.6) !important;
}
.modern-card:hover {
    background: rgba(13, 13, 13, 0.7) !important;
}
```

**Rationale:** Lower opacity allows background aurora gradients to be more visible, creating a more immersive experience.

---

#### 2.3 Edge Highlights (Top Border Light)

**Target:** All cards

**New CSS:**
```css
.modern-card {
    border-top: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-left: 1px solid rgba(255, 255, 255, 0.05) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
}
```

**Rationale:** Simulates light hitting the top edge of a glass pane, enhancing the 3D material feel.

---

### 3. Sleek Interactive Elements

#### 3.1 Enhanced Hover States

**Target:** Buttons and interactive cards

**Current:** Simple color change (implicit in Quasar)

**New:**
```css
.modern-btn {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.modern-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.4) !important;
}

.modern-card:hover {
    transform: translateY(-1px) !important;
    box-shadow: 
        inset 0 1px 0 rgba(255, 255, 255, 0.15),
        0 8px 32px rgba(0, 0, 0, 0.5) !important;
}
```

**Implementation:**
- Add `.modern-btn` class to all buttons
- Apply hover effects via CSS
- Ensure smooth transitions with cubic-bezier easing

---

#### 3.2 Gradient Buttons

**Target:** Primary action buttons (Run Calculation, Load, Export)

**Current:** Flat colors
```css
.brutal-btn-teal {
    background: rgba(15, 118, 110, 0.45) !important;
}
```

**New:**
```css
.modern-btn-primary {
    background: linear-gradient(180deg, rgba(15, 118, 110, 0.6) 0%, rgba(13, 100, 92, 0.5) 100%) !important;
    border: 1px solid rgba(20, 184, 166, 0.3) !important;
}

.modern-btn-primary:hover {
    background: linear-gradient(180deg, rgba(20, 184, 166, 0.7) 0%, rgba(13, 100, 92, 0.6) 100%) !important;
    box-shadow: 0 10px 20px rgba(20, 184, 166, 0.2) !important;
}
```

**Button Variants:**
- `.modern-btn-primary` — teal gradient (Run, Load)
- `.modern-btn-secondary` — purple gradient (Export actions)
- `.modern-btn-ghost` — transparent with border (secondary actions)

---

### 4. Refined Navigation (Left Pane)

#### 4.1 Active Indicator Redesign

**Current:** Full button highlight (Quasar default)

**New Options:**

**Option A: Pill Shape Behind Text**
```css
.nav-item {
    position: relative;
    border-radius: 8px;
    padding: 8px 12px;
    transition: all 0.2s ease;
}

.nav-item.active {
    background: rgba(37, 99, 235, 0.15) !important;
    color: #60A5FA !important;
}

.nav-item.active::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 3px;
    height: 20px;
    background: #60A5FA;
    border-radius: 0 2px 2px 0;
}
```

**Option B: Thin Vertical Line (Preferred)**
```css
.nav-item {
    position: relative;
    padding-left: 16px;
    transition: all 0.2s ease;
}

.nav-item.active {
    color: #60A5FA !important;
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
```

**Implementation:**
- Replace `nav_btn()` function to use new class structure
- Add active state tracking in JavaScript/Python
- Update drawer navigation section

---

#### 4.2 Thin-Stroke Iconography

**Target:** All icons in navigation and UI

**Current:** Default Material Icons (filled)

**New:** Material Symbols Outlined with weight 300

**Implementation:**
```python
# Change icon props from:
ui.icon("menu")

# To:
ui.icon("menu").props("outline style={font-weight: 300}")
```

**Icon Updates:**
- Navigation: `menu`, `upload`, `table_view`, `settings`, `3d_rotation`, `play_arrow`, `assessment`, `download`
- Status: `warning`, `check_circle`, `info`
- Actions: `play_arrow`, `refresh`, `description`

**Note:** NiceGUI/Quasar uses Material Icons by default. To use Material Symbols Outlined, may need to load the Google Fonts stylesheet:
```html
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,300,0,0" />
```

---

## Implementation Steps

### Phase 1: CSS Foundation (High Priority)

1. **Create new CSS class names**
   - Duplicate `AURORA_CSS` as `MODERN_CSS`
   - Rename classes: `.brutal-*` → `.modern-*`
   - Apply all geometry and glassmorphism changes

2. **Update color variables**
   - Keep aurora colors (they work well)
   - Add new variables for gradients and shadows
   - Example:
     ```css
     :root {
         --glass-bg: rgba(13, 13, 13, 0.6);
         --glass-border: rgba(255, 255, 255, 0.1);
         --shadow-soft: 0 4px 24px rgba(0, 0, 0, 0.4);
         --shadow-hover: 0 10px 32px rgba(0, 0, 0, 0.5);
     }
     ```

3. **Test CSS in isolation**
   - Create a test page with one card and one button
   - Verify rounded corners, blur, and hover effects

---

### Phase 2: Component Updates (High Priority)

4. **Update all card references**
   - Search and replace `.brutal-card` → `.modern-card` in `app.py`
   - Count: ~15 occurrences across tabs

5. **Update button classes**
   - Replace `.brutal-btn` → `.modern-btn`
   - Replace `.brutal-btn-teal` → `.modern-btn-primary`
   - Add gradient variants for secondary actions

6. **Update header and drawer**
   - Apply `.modern-header` to header
   - Update drawer CSS with new glassmorphism

---

### Phase 3: Navigation Redesign (Medium Priority)

7. **Redesign navigation buttons**
   - Update `nav_btn()` function to use new CSS classes
   - Implement active state indicator (vertical line)
   - Add hover transitions

8. **Update iconography**
   - Add Google Fonts stylesheet for Material Symbols Outlined
   - Update all icon calls to use outlined variants
   - Test icon rendering

---

### Phase 4: Interactive Polish (Medium Priority)

9. **Add hover effects to cards**
   - Ensure all interactive cards have hover states
   - Test transitions and performance

10. **Refine toggle buttons**
    - Update `.brutal-toggle` → `.modern-toggle`
    - Add rounded corners and glassmorphism
    - Improve active state styling

11. **Test responsive behavior**
    - Verify glassmorphism works on different screen sizes
    - Check mobile navigation (if applicable)

---

### Phase 5: Final Review (Low Priority)

12. **Cross-browser testing**
    - Test in Chrome, Firefox, Safari, Edge
    - Verify backdrop-filter support (add fallback if needed)

13. **Accessibility check**
    - Ensure contrast ratios meet WCAG AA
    - Test keyboard navigation
    - Verify screen reader compatibility

14. **Documentation update**
    - Update `dev-docs/GUI_PLAN.md` §0 with new aesthetic
    - Add screenshots to documentation
    - Update GUI_VERSION to 1.1.0

---

## Files to Modify

| File | Changes | Lines Affected (Est.) |
|------|---------|----------------------|
| `src/mypyskindose/gui/app.py` | CSS class replacements, navigation updates | ~100 |
| `src/mypyskindose/gui/app.py` | New CSS variables and styles | ~150 (new) |
| `dev-docs/GUI_PLAN.md` | Update §0 current-state aesthetic description | ~20 |
| `dev-docs/GUI_PLAN.md` | Note aesthetic change | ~10 |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Backdrop-filter not supported in older browsers | Medium | Low | Add fallback background color |
| Performance degradation with heavy blur | Low | Medium | Test on lower-end devices, reduce blur if needed |
| Icon font loading delay | Low | Low | Use system fonts as fallback |
| Breaking existing functionality | Very Low | High | Only CSS changes, no logic modifications |

---

## Success Criteria

- [ ] All cards have 12px border radius
- [ ] Hard borders replaced with inner glow shadows
- [ ] Backdrop blur increased to 20-24px
- [ ] Card backgrounds at 60% opacity
- [ ] Top edge highlights visible on all cards
- [ ] Buttons have translateY hover effect
- [ ] Primary buttons use gradient backgrounds
- [ ] Navigation uses vertical line active indicator
- [ ] Icons use thin-stroke Material Symbols
- [ ] No functionality broken
- [ ] Cross-browser compatible
- [ ] Accessibility standards met

---

## Before/After Comparison

### Card Styling

**Before (Aurora-Brutalist):**
```css
.brutal-card {
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    background: rgba(13, 13, 13, 0.8) !important;
    backdrop-filter: blur(12px);
    border-radius: 0px !important;
}
```

**After (Sleek Modern):**
```css
.modern-card {
    border-top: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-left: 1px solid rgba(255, 255, 255, 0.05) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
    background: rgba(13, 13, 13, 0.6) !important;
    backdrop-filter: blur(20px) saturate(150%);
    border-radius: 12px !important;
    box-shadow: 
        inset 0 1px 0 rgba(255, 255, 255, 0.1),
        0 4px 24px rgba(0, 0, 0, 0.4) !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.modern-card:hover {
    transform: translateY(-1px) !important;
    box-shadow: 
        inset 0 1px 0 rgba(255, 255, 255, 0.15),
        0 8px 32px rgba(0, 0, 0, 0.5) !important;
}
```

### Button Styling

**Before:**
```css
.brutal-btn-teal {
    border-color: rgba(15, 118, 110, 0.8) !important;
    background: rgba(15, 118, 110, 0.45) !important;
}
```

**After:**
```css
.modern-btn-primary {
    background: linear-gradient(180deg, rgba(15, 118, 110, 0.6) 0%, rgba(13, 100, 92, 0.5) 100%) !important;
    border: 1px solid rgba(20, 184, 166, 0.3) !important;
    border-radius: 8px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.modern-btn-primary:hover {
    transform: translateY(-2px) !important;
    background: linear-gradient(180deg, rgba(20, 184, 166, 0.7) 0%, rgba(13, 100, 92, 0.6) 100%) !important;
    box-shadow: 0 10px 20px rgba(20, 184, 166, 0.2) !important;
}
```

### Navigation Active State

**Before:**
- Full button background color change (Quasar default)

**After:**
```css
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
```

---

## Timeline Estimate

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: CSS Foundation | 2-3 hours | None |
| Phase 2: Component Updates | 2-3 hours | Phase 1 |
| Phase 3: Navigation Redesign | 1-2 hours | Phase 2 |
| Phase 4: Interactive Polish | 1-2 hours | Phase 3 |
| Phase 5: Final Review | 1-2 hours | Phase 4 |
| **Total** | **7-12 hours** | |

---

## Notes

- This is a pure CSS/styling change — no backend logic modifications required
- The aurora background gradients will remain unchanged as they work well with both aesthetics
- Consider creating a CSS variable system for easier theme switching in the future
- Test with both light and dark content (tables, plots) to ensure readability
- The glassmorphism effect may need adjustment based on user feedback regarding readability

---

## References

- Material Design 3 Guidelines: https://m3.material.io/
- Glassmorphism CSS patterns: https://ui.glass/generator/
- CSS backdrop-filter browser support: https://caniuse.com/backdrop-filter
- Material Symbols Outlined: https://fonts.google.com/icons?icon.set=Material+Symbols+Outlined
