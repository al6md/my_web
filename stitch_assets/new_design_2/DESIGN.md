# Design System Strategy: The Inspired Curator

## 1. Overview & Creative North Star
This design system is built upon the Creative North Star of **"The Inspired Curator."** We are moving away from the "digital shelf" aesthetic of traditional bookstores and toward a high-end editorial experience that feels like a conversation with a well-read friend. 

The system rejects the rigid, boxy constraints of standard web grids in favor of **Intentional Asymmetry**. By utilizing the `xl` (3rem) rounding and staggered spacing, we create a layout that feels organic and fluid. We break the "template" look by overlapping book covers across container boundaries and using high-contrast typography scales that command attention. This isn't just a database; it’s a living invitation to discover.

---

## 2. Colors: Tonal Depth & The "No-Line" Rule
The palette is a sophisticated blend of energetic `primary` purples and optimistic `secondary` oranges, anchored by a `surface` that feels like premium cream paper.

*   **The "No-Line" Rule:** To maintain a high-end feel, **do not use 1px solid borders for sectioning.** Boundaries must be defined solely through background color shifts. For example, a "Featured" section should be a full-bleed `surface_container_low` block sitting directly against a `surface` background. 
*   **Surface Hierarchy & Nesting:** Treat the UI as physical layers of paper. Use `surface_container_lowest` for the most prominent foreground elements (like a featured book card) to create a "lifted" effect against a `surface_container` backdrop.
*   **The "Glass & Gradient" Rule:** To avoid a flat "Material" look, use Glassmorphism for floating navigation bars or mobile overlays. Apply `surface` at 80% opacity with a `backdrop-blur` of 20px. 
*   **Signature Textures:** For Hero CTAs, use a linear gradient transitioning from `primary` (#6f26f6) to `primary_container` (#cab6ff) at a 135-degree angle. This adds a "soul" to the interface that flat fills lack.

---

## 3. Typography: The Editorial Voice
We utilize a dual-font strategy to balance character with extreme readability, especially for Arabic script.

*   **Display & Headlines (Be Vietnam Pro):** These are our "shout" moments. Use `display-lg` (3.5rem) for book titles in hero sections. The tight letter-spacing and bold weight create an authoritative, editorial feel.
*   **Body & Labels (Plus Jakarta Sans):** Chosen for its high x-height and exceptional clarity in both Latin and Arabic. 
*   **Arabic Support:** Ensure line-height (leading) for Arabic text is increased by 20% compared to Latin to accommodate deep descenders and diacritics, preventing the "crowded" look of standard templates.
*   **Visual Hierarchy:** Use `tertiary` (#7b5913) for category labels (e.g., "Historical Fiction") to provide a warm, distinct contrast against the `primary` purple headers.

---

## 4. Elevation & Depth: Tonal Layering
Traditional shadows are often a crutch for poor layout. In this system, depth is earned through color and blur.

*   **The Layering Principle:** Achieve 90% of your hierarchy by "stacking" tiers. A `surface_container_highest` element naturally feels deeper than a `surface_container_low` element.
*   **Ambient Shadows:** When a float is required (e.g., a "Buy Now" FAB), use a shadow with a 40px blur and 6% opacity. The shadow color must be a tinted version of `on_surface` (#353229), never pure black.
*   **The "Ghost Border" Fallback:** If a container requires a boundary for accessibility on high-brightness screens, use the `outline_variant` (#b7b1a4) at **15% opacity**. It should be felt, not seen.
*   **Layered Glass:** Use semi-transparent `surface_container_lowest` for cards over vibrant background gradients to create a "frosted" look that integrates the content into the environment.

---

## 5. Components: Fluidity Over Rigidity

### Buttons
*   **Primary:** Uses the `xl` (3rem) rounding. Background: `primary`. Text: `on_primary`. Apply a subtle 4px vertical offset on hover to simulate a "soft press."
*   **Tertiary:** No background or border. Use `title-sm` typography in `primary` color with a 2px `primary_container` underline that expands on hover.

### Cards & Lists
*   **Forbid Dividers:** Do not use lines to separate list items. Use `3` (1rem) spacing and alternating `surface_container_low` backgrounds for every second item, or simply rely on vertical white space.
*   **Book Cards:** Should use `lg` (2rem) rounding. The image should bleed to the top and side edges, with text content padded by `4` (1.4rem) at the bottom.

### Input Fields
*   **Style:** Use `surface_container_high` as the background fill. No border. On focus, transition the background to `surface_container_lowest` and add a 2px "Ghost Border" of `primary`.
*   **Rounding:** `md` (1.5rem) to maintain the "soft but functional" aesthetic.

### Additional Contextual Components
*   **The "Quote Block":** A specialized component for book excerpts. Use `headline-sm` in `secondary` (#a14200), set in an asymmetrical container with `xl` rounding on the top-left and bottom-right corners only.
*   **Reading Progress:** A thick (8px) bar using a gradient from `tertiary_fixed` to `secondary`.

---

## 6. Do's and Don'ts

### Do
*   **Do** use asymmetrical margins (e.g., `8` on the left, `12` on the right) for hero images to create energy.
*   **Do** overlap elements. Let a book cover "break" the container of a surface to create 3D depth.
*   **Do** use `secondary` (#a14200) for interactive elements like "Heart" icons or "Save" buttons to make them pop against the purple primary.

### Don't
*   **Don't** use sharp corners. The minimum rounding for any visible container is `sm` (0.5rem).
*   **Don't** use pure grey. All neutrals (`surface`, `outline`) are warmed with cream and ochre undertones to keep the "Inspiring" vibe.
*   **Don't** center-align long blocks of text. Keep editorial content flush-start (right-aligned for Arabic, left-aligned for English) to maintain a clean vertical axis.