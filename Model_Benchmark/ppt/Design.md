# Design System for Brandlogy PPT (16:9) — Inspired by MiniMax

> Revision note: This version incorporates verified refinements from production runs — Pattern G (Stacked Insight Cards) with calibrated typography for tight containers, the Breathing Room Rule, Featured Tag Pill correction, KPI card internal Y-coordinate spec, and a data consistency check. Look for **[v2 refinement]** tags inline.

## 0. Production Constraints (Read First)

Output
- 16:9 slides only (PowerPoint standard 13.333" × 7.5", reference resolution 1920 × 1080 px). No other aspect ratios are valid output. Reject 4:3, 1:1, 9:16, A4, letter, or any other format requests.
- All deliverables go through the Brandlogy template (_Claude_Brandlogy_Template_2026.pptx or equivalent uploaded to project knowledge).

Brand Assets (mandatory, no substitution)
- Logo: Brandlogy logo only. Do NOT substitute MiniMax or any third-party logo. Place at top-right of every slide unless explicitly told otherwise. Use the logo file exactly as provided — see Logo Integrity Rule below. The Brandlogy logo asset is uploaded to project knowledge; reference that file directly.
- Typography: **Paperlogy only — no exceptions.** Do NOT use Pretendard, DM Sans, Outfit, Poppins, Roboto, Noto, Apple SD Gothic, Malgun Gothic, system fallbacks, or any other family under any circumstance. Every weight reference below maps to Paperlogy's scale (Thin 100 → Black 900). The available Paperlogy files are:
  - `Paperlogy-1Thin.ttf` (100)
  - `Paperlogy-2ExtraLight.ttf` (200)
  - `Paperlogy-3Light.ttf` (300)
  - `Paperlogy-4Regular.ttf` (400)
  - `Paperlogy-5Medium.ttf` (500)
  - `Paperlogy-6SemiBold.ttf` (600)
  - `Paperlogy-7Bold.ttf` (700)
  - `Paperlogy-8ExtraBold.ttf` (800)
  - `Paperlogy-9Black.ttf` (900)

  Assume Paperlogy is available on the rendering machine; if a fallback string is needed for export-safety, use `Paperlogy, -apple-system, system-ui, sans-serif`, but the only family that should actually render is Paperlogy. Paperlogy must be embedded in the .pptx on export so the layout survives on machines without it installed.

Slide Skeleton — locked positions across the deck
Every slide in the deck must place these five zones at identical coordinates. The reader's eye should never have to relearn the layout when flipping pages — only the body contents change, never the frame.

| Zone | Position (slide 13.333" × 7.5") | Contents | Style |
|---|---|---|---|
| Header strip | 0.4"–0.7" from top, full width within 0.5" side margins | Chapter name (left), Brandlogy logo (right) | Chapter: Paperlogy 600, 12pt, #8e8e93. Logo: original transparent PNG provided by user, sized ≈ 1.22" × 0.24" (aspect-locked), top-right anchored ≈0.5" from right edge |
| Headline zone | 1.0"–1.75" from top, 0.5" left margin | Slide headline (one-sentence copy, 대제목) | Paperlogy 700, 32–40pt, #222222, line-height 1.20 |
| Subtitle zone | 1.63"–2.03" from top, 0.5" left margin | Subtitle (부제목) | Paperlogy 500, 16pt, #45515e, line-height 1.45 |
| Body box | 2.39"–6.85" from top, 0.5" side margins | All body components — see §5 | Mixed |
| Footer strip | 7.05"–7.3" from top, full width within 0.5" side margins | Page number (left), source/footnote (right) | Page: Paperlogy 500, 10pt, #8e8e93. Source: Paperlogy 400, 9–10pt, #8e8e93 |

Vertical rhythm: The gaps in the upper half of the slide are intentional and not uniform — Header strip → Headline = 0.3" (deliberate breathing space below chapter line). Headline zone → Subtitle zone = 0.1" zone-to-zone, but because the headline text typically renders shorter than its zone, the visual gap between the headline text bottom and the subtitle text is closer to 0.13" — title and subtitle read as one tightly-coupled unit. Subtitle bottom → Body top ≈ 0.36" — a clear visual break that lets the body box read as its own region while still feeling anchored to the title block above. This pattern (loose top, tight middle, medium bottom) is what makes the title block feel like the slide's "anchor" rather than a floating header.

Lock rule: These five zones do not move between slides. Chapter name stays at the same baseline, headline starts at the same Y, subtitle starts at the same Y, body box starts and ends at the same Y, footer strip is identical. Override is permitted only when structurally unavoidable — i.e., a section divider that intentionally breaks the frame, a full-bleed cover, or a closing slide. Routine "this body is taller than usual" is NOT an unavoidable case; restructure the content instead.

Hard boundary: Body content lives strictly inside 2.39"–6.85" (the Body box). It does NOT bleed upward into the Subtitle zone (above 2.39") and does NOT bleed downward into the Footer strip (below 6.85"). A 0.2" clearance buffer (6.85"–7.05") sits between the body box and the footer strip — keep it empty so the page number and source line never get crowded. Anything taller than 4.46" of body height must be split, scaled down, or moved to a second slide — not allowed to invade adjacent zones.

Logo Integrity Rule: The Brandlogy logo must be placed exactly as provided — original file, original proportions, original colors, original transparency (alpha channel preserved). The user supplies a transparent PNG (누끼); insert that file as-is. Do NOT add an underline, strikethrough, drop shadow, glow, border, frame, recolor, gradient, opacity change, background fill, opaque box behind the logo, or any other visual treatment. Do NOT crop, stretch, skew, rotate, or duplicate the logo. The only permitted operations are uniform scaling (preserving aspect ratio) to fit the ≈0.24" target height (resulting width typically ≈1.22" depending on source proportions), and uniform color inversion to a white variant when placed on dark backgrounds (section dividers, closing slides). A black or white rectangle behind the logo is a defect, not the design — if a generated output shows any line, mark, decoration, or solid box on/behind the logo that is not in the original file, treat it as a defect and fix it before exporting.

Body Density Rule
The lower body box must NOT be left half-empty. Plan body content to fill the available area at a comfortable reading density — charts, diagrams, KPI tiles, comparison tables, dual-column layouts, supporting captions. Empty bottom space breaks the McKinsey/BCG sharpness target. Whitespace is a tool for breathing rhythm between elements, not a default for the bottom 30% of every slide.

Density never overrides the hard boundary. "Filling the bottom" means filling inside the body box (2.39"–6.85") — it does NOT mean spilling content into the 0.2" footer clearance, the footer strip, or the subtitle/headline zones above. If pursuing density tempts you to push a card down to 7.0" or up to 2.35", you have too much content on the slide; split it.

If a slide genuinely has thin content, use one of these density tactics — never decorative padding, never zone invasion:
- Pull supporting evidence (quote, data point, mini-chart, source) into a side panel, still inside the body box
- Add a "So What" callout box at the bottom of the body box (above 6.85") summarizing the takeaway
- Insert a diagram that visually reinforces the headline
- Split the body into a 2-column claim / evidence layout
- Use Pattern F (Stacked Insight Layers, see §5) — three horizontal bands within the body box
- Use Pattern G (Stacked Insight Cards, see §5) — three vertical cards on the right side of a 2-column layout **[v2]**

Do NOT pad with decorative shapes or stock illustrations to fake density.

**[v2 refinement] Breathing Room Rule (paired with Density Rule)**
Density does NOT mean "fill the container edge-to-edge with text." Every card, panel, and visualization must keep at least 0.06"–0.10" of internal padding between the last text baseline and the bottom edge. If text fills a container right up to the wall, the font is too large for the container — drop one step on the type scale (14→13, 13→12, 12→11, 11→10) before considering layout changes. Symptoms of a breathing-room failure: text looks "꽉 차있다" (packed), supporting body lines abut card borders, eye finds no rest between elements within a card. Tight ≠ dense; tight is a defect, dense is structured.

Visualization-First Rule (Style 1 — strong)
Style 1 is data-first. Whenever a slide carries data, comparison, process, structure, or relationship — visualize it, do not narrate it in prose. This is a strong default, not a suggestion.

Trigger conditions (if any of these apply, the slide MUST include a visualization):
- Two or more numbers being compared (chart or KPI tile row, never inline prose)
- A trend over time (line chart or timeline, even with only 2–3 points)
- Composition / share / distribution (bar, donut, or 100% stacked bar)
- A process or sequence (horizontal arrow flow, numbered stages)
- A comparison across categories (grouped/stacked bar or table — chart preferred over table)
- A structural relationship between concepts (diagram, matrix, 2×2)
- A geographic or hierarchical breakdown (map, tree, or org chart)

Visualization options to reach for, in priority order:
1. Charts — bar (horizontal/vertical/grouped/stacked), line, area, scatter, donut. Default. Use Style 1 chart palette (§4).
2. KPI tiles with sparklines — when a single number deserves emphasis but context still matters
3. Diagrams — flow, sequence, 2×2 matrix, layered architecture, Venn (rare), funnel, hierarchy
4. Annotated images / screenshots — only when the visual artifact itself is the evidence
5. Tables — last resort, only when individual cell values matter and ranking/comparison is secondary

Constraints (visualization never breaks the layout):
- Visualizations live strictly inside the body box (2.39"–6.85"). Never bleed into headline/subtitle/footer zones.
- A single slide should carry 1–2 visualizations max, not 4+. Cramming charts breaks the pacing more than missing them.
- Every chart and diagram must have: a title (Paperlogy 600 14pt), axis labels (Paperlogy 400 10pt #45515e), and a source line (Paperlogy 400 9pt #8e8e93) directly below.
- If a visualization would force font sizes below 9pt or compress data labels into illegibility, the slide has too much data — split it, don't shrink the chart.
- Pure-prose body slides are reserved for: section openers, hero takeaways, single-quote callouts, definitions. Everything else gets a visualization.

When in doubt, ask: "Could this be a chart instead of bullets?" If yes, make it a chart.

**[v2 refinement] Data Consistency Rule**
Every number that appears in the headline, subtitle, body callout, chart label, or footer source must be internally consistent on the same slide. If the headline says "양강이 75% 차지" but the donut chart sums to 82.4% and a callout below shows 87.6%, the slide is broken — pick the correct figure (recompute from raw data if necessary), use it everywhere on the slide, and never let three different versions of the same metric coexist. Run a "number reconciliation" pass before declaring a slide done: list every number on the slide, verify each traces to the source, and confirm derived numbers (totals, share%, growth%) recompute correctly.

---

## 1. Visual Theme & Atmosphere

The aesthetic bridges Apple-grade product-marketing clarity with a playful, rounded, gallery-like feel. Pure white (#ffffff) is the structural background; color enters via charts, KPI cards, gradients, and accent elements. Paperlogy at moderate weights (500–700) carries a confident-but-approachable tone — not aggressive, not airy.

Key Characteristics
- White-dominant canvas with colorful accent elements (charts, KPI cards, gradients) carrying visual interest
- Paperlogy across the entire system, with weight (not family) doing all hierarchy work
- Pill buttons (9999px / fully rounded) for nav, tabs, toggles
- Generous rounded cards (16–24px radius) for content blocks
- Brand blue spectrum: #1456f0 → #3b82f6 → #60a5fa
- Brand pink (#ea5ec1) reserved for decorative accents
- Near-black text (#222222, #18181b) on white
- Purple-tinted shadows (rgba(44, 30, 116, 0.16)) for featured cards — subtle brand glow
- Dark sections (#181e25) for divider/closing slides if needed

---

## 2. Color Palette & Roles

### Brand Primary
- Brand Blue (#1456f0): primary brand identity color
- Sky Blue (#3daeff): lighter brand variant for accents
- Brand Pink (#ea5ec1): secondary accent — decorative only, never on body text

### Blue Scale
- #bfdbfe — light blue background
- #60a5fa — primary-light, active states, chart fills
- #3b82f6 — primary-500, standard blue actions, primary chart series
- #2563eb — primary-600, emphasis
- #1d4ed8 — primary-700, deep emphasis
- #17437d — brand-deep

### Text
- #222222 — primary text (body, headline)
- #18181b — heading-dark, dark button text
- #181e25 — dark surface text, footer-bg
- #45515e — secondary text (subtitle, captions)
- #8e8e93 — tertiary/muted text (chapter name, page number, source)
- #5f5f5f — helper text

### Surface
- #ffffff — primary background (every slide)
- #f0f0f0 — secondary container background
- hsla(0, 0%, 100%, 0.4) — frosted glass overlay
- #f2f3f5 — subtle dividers
- #e5e7eb — component borders

### Semantic
- #e8ffea — success background (pair with #16a34a for success text)

### Color Format Rule (PptxGenJS-specific)
- All hex values are **6 characters, no `#` prefix** (e.g., `"1456f0"` not `"#1456f0"`). Adding `#` corrupts the .pptx file.
- Do NOT encode opacity into 8-character hex (e.g., `"00000020"`). Use the separate `transparency` or `opacity` property instead.

### Shadow Library
| Token | Value | Use |
|---|---|---|
| Standard | rgba(0, 0, 0, 0.08) 0px 4px 6px | Default cards |
| Soft Glow | rgba(0, 0, 0, 0.08) 0px 0px 22.576px | Ambient shadow |
| Brand Glow | rgba(44, 30, 116, 0.16) 0px 0px 15px | Featured cards |
| Brand Glow Offset | rgba(44, 30, 116, 0.11) 6.5px 2px 17.5px | Hero product cards |
| Elevated | rgba(36, 36, 36, 0.08) 0px 12px 16px -4px | Lifted/hover-equivalent emphasis |

Shadow Object Rule (PptxGenJS-specific): When applying the same shadow to multiple shapes in PptxGenJS, do NOT pass a shared shadow object reference — the second invocation can mutate or break. Use a factory function that returns a fresh object per call:

```js
const stdShadow = () => ({ type: "outer", color: "000000", opacity: 0.08, blur: 6, offset: 2, angle: 90 });
const brandGlow = () => ({ type: "outer", color: "2c1e74", opacity: 0.16, blur: 15, offset: 0, angle: 90 });

slide.addShape(..., { shadow: stdShadow() }); // ✓
slide.addShape(..., { shadow: stdShadow() }); // ✓ — fresh object
```

### Hero Gradient (Premium Accent — use sparingly)
A single elegant blue gradient is permitted to elevate hero moments. The gradient is built from the existing blue scale — no new colors are introduced.

Token Hero Gradient: linear-gradient(135deg, #1456f0 0%, #3b82f6 50%, #60a5fa 100%)

Fixed parameters — do NOT vary these:
- Angle: 135° (top-left dark → bottom-right light). Consistent across the deck.
- Stops: 0% / 50% / 100% with the three brand blues in order. No additional color stops.
- Colors: Only #1456f0, #3b82f6, #60a5fa from the existing scale. No purple, cyan, teal, or pink mixed in.

PptxGenJS Implementation Note: Native CSS-style gradients are NOT supported by PptxGenJS in shape fills. To approximate Hero Gradient on a featured card, use **solid #1456f0 with Brand Glow shadow** — this carries enough premium weight that the absence of the gradient is not noticed. If a true gradient is required (e.g., section divider full-bleed), generate a 1920×1080 PNG of the gradient externally and use it as a slide background image. Do not attempt to fake gradients with stacked semi-transparent shapes.

Permitted locations (max 3 across the entire deck)
1. Cover slide hero card — the single featured card on the cover slide (Pattern E in §5)
2. Section divider background — the dark divider slide may use Hero Gradient instead of solid #181e25 for a more premium feel
3. One Featured KPI card per slide — at most one KPI tile per slide may use the gradient (or its solid #1456f0 substitute) as background, with white text on it. Pair with Brand Glow shadow.

Forbidden locations
- Chart bars / lines / data points — gradients on data create false visual hierarchy (longer bars look "more saturated"). Use flat brand blue (#1456f0 or #3b82f6) for all chart series.
- Headline or body text — text-on-gradient or gradient-text is AI-slop visual. Text stays solid #222222.
- Header strip and footer strip — these zones are flat, always.
- Standard content cards (non-featured) — gradients on every card destroy the white-canvas brand identity.
- Body card backgrounds in bulk — only one gradient element per slide. Multiple gradients break the design.

Premium-look rules
- Always pair Hero Gradient (or its solid substitute) with the Brand Glow shadow (rgba(44, 30, 116, 0.16) 0px 0px 15px) for the soft halo effect that prevents flat-poster look.
- Inside text on gradient must be white (#ffffff) at Paperlogy 500–700, never #222222 or any blue.
- Gradient cards use 20–24px radius (the larger end of the radius scale) — sharp corners on gradient look cheap.
- Never overlay another gradient, image, or pattern on top of Hero Gradient. The gradient itself IS the visual interest.

If the gradient would compete with charts on the same slide, the chart wins — move the gradient element to a different slide. Charts and gradients on the same slide create visual chaos.

---

## 3. Typography Rules (Paperlogy-only)

### Family
**Paperlogy only** (Korean + Latin support, weights 100–900). No other family is permitted under any circumstance — not for headlines, not for data, not for fallback. If a fallback string is required for export-safety, use: `Paperlogy, -apple-system, system-ui, sans-serif`, but the only family that should actually render is Paperlogy. Paperlogy must be embedded in the .pptx on export so the layout survives on machines without it installed.

### Weight Map (functional roles)
- 700 Bold (Paperlogy-7Bold) — Slide headlines, section titles, KPI numbers, strong body emphasis
- 600 SemiBold (Paperlogy-6SemiBold) — Card titles, button text, chapter name, body H2/H3
- 500 Medium (Paperlogy-5Medium) — Sub-headings, subtitles, feature labels, emphasized body
- 400 Regular (Paperlogy-4Regular) — Body text, captions, sources, footnotes
- 300 Light (Paperlogy-3Light) and 800 ExtraBold (Paperlogy-8ExtraBold) are available for special cases — use sparingly
- 100 Thin / 200 ExtraLight / 900 Black are reserved for rare display moments only (oversized cover statements, single-character headers) — never for body, headlines, or data labels

### Hierarchy (16:9 slide, 1920 × 1080 reference)

| Role | Weight | Size (pt) | Size (px @144dpi) | Line Height | Color |
|---|---|---|---|---|---|
| Slide Headline (대제목) | 700 | 32–40pt | 64–80px | 1.20 | #222222 |
| Subtitle (부제목) | 500 | 16pt | 32px | 1.45 | #45515e |
| Body H2 (본문 중제목) | 600 | 18–20pt | 36–40px | 1.40 | #222222 |
| Body H3 (본문 소제목) | 600 | 14–16pt | 28–32px | 1.45 | #222222 |
| Body | 400 | 12–14pt | 24–28px | 1.50 | #222222 |
| Body Emphasized | 500 | 12–14pt | 24–28px | 1.50 | #222222 |
| Body Bold | 700 | 12–14pt | 24–28px | 1.50 | #222222 |
| KPI Primary Number (KR / featured) | 700 | 24pt | 48px | 1.10 | #1456f0 (or #ffffff on featured) |
| KPI Secondary Number (JP / comparison) | 700 | 19pt | 38px | 1.10 | #8e8e93 (or rgba white on featured) |
| KPI Label | 500–600 | 11pt | 22px | 1.30 | #45515e |
| Chapter Name | 600 | 11–12pt | 22–24px | 1.30 | #8e8e93 |
| Page Number | 500 | 9–10pt | 18–20px | 1.30 | #8e8e93 |
| Caption / Source | 400 | 9–10pt | 18–20px | 1.40 | #8e8e93 |
| Tag / Badge | 600 | 10–11pt | 20–22px | 1.20 | varies |
| **[v2] Tight Card Title (1.3"-tall stacked card)** | **700** | **13pt** | **26px** | **1.30** | **#222222** |
| **[v2] Tight Card Body (1.3"-tall stacked card)** | **400** | **10pt** | **20px** | **1.45** | **#45515e** |
| **[v2] Tight Card Tag (small pill)** | **600** | **9pt** | **18px** | **1.20** | **white on tag color** |

KPI Number Sizing Note: 24pt for the primary value and 19pt for the secondary value are tested-and-balanced sizes for a 3-up KPI strip with 1.5" card height and an 11pt label above. Going larger (28pt/22pt) overpowers the label and gap badge; smaller numbers lose hierarchy. If KPI cards are taller (>1.7") or wider, you may scale up to 28pt/22pt — keep the ~1.25× ratio between primary and secondary.

**[v2 refinement] Container-Aware Type Scale**
The standard hierarchy above assumes "regular" containers — KPI cards ~1.5" tall, panels with ample interior space, chart titles in spacious chart containers. When a container is tighter than standard (stacked insight cards ~1.3" tall, small comparison tiles, dense info pills), drop one step on the type scale to preserve breathing room:

| Standard container → Tight container | Title | Body | Tag |
|---|---|---|---|
| Card height ≥ 1.5" | 14–16pt | 11–12pt | 10–11pt |
| Card height 1.3"–1.5" (Pattern G) | **13pt** | **10pt** | **9pt** |
| Card height < 1.3" | content too dense — restructure |

Verified empirically: at card height ≈ 1.36" (Pattern G geometry below), a 14pt title + 11pt body fills the card edge-to-edge with zero bottom padding ("꽉 차있어" effect). Dropping to 13pt + 10pt produces the correct 0.06–0.10" of internal bottom padding. Do not skip this step on the assumption that "the body is dense, more text is better."

### Principles
- Weight does the hierarchy work, not family. Paperlogy 700 vs 500 vs 400 carries the entire vertical rhythm.
- Default line-height 1.50 for body, 1.45 for subtitles, 1.20–1.30 for headlines and labels. Tight (1.10) for big numbers.
- No italic unless quoting a source — use weight contrast instead.
- Korean–Latin mixing: Paperlogy handles both natively. No font swap mid-sentence.
- Tracking (자간): 0 for body, -0.02em ~ -0.03em for large headlines (32pt+) to compensate for optical loosening at large sizes. In PptxGenJS, this maps to `charSpacing: -0.6` for a 36pt headline.
- Paperlogy has slightly different x-height and stroke characteristics than other Korean sans-serif families — do NOT manually re-tune sizes to mimic another font's rendering. Use Paperlogy's natural proportions at the sizes specified above.
- Always set `margin: 0` on PptxGenJS text boxes to remove the default internal padding; otherwise text shifts unpredictably from the specified Y coordinate.

---

## 4. Component Stylings

### Buttons / Pills

Pill Primary Dark
- BG #181e25, text #ffffff, padding 11px 20px, radius 8px, Paperlogy 600 13–14pt
- Use: primary CTA on cover/closing slides

Pill Nav / Tab
- BG rgba(0, 0, 0, 0.05), text #18181b, radius 9999px, Paperlogy 500 11–12pt
- Use: section tabs, filter indicators

Pill White
- BG #ffffff, text rgba(24, 30, 37, 0.8), radius 9999px, Paperlogy 500
- Use: secondary nav, inactive tabs

Secondary Light
- BG #f0f0f0, text #333333, padding 11px 20px, radius 8px, Paperlogy 500
- Use: secondary actions, divider tags

**[v2] Featured-Card Tag Pill (CRITICAL correction)**
When a tag pill sits inside a Featured (blue background) card, do NOT use a transparent or low-opacity white fill — the pill renders nearly invisible against the blue background and the text-on-pill loses contrast. Instead use:
- Fill: solid #ffffff (no transparency)
- Text: brand blue (#1456f0) at Paperlogy 600
- Radius: 0.14" (matching standard tag pills)

This produces a high-contrast white badge on blue that reads cleanly. The same rule applies inverse for any tag pill on a Hero-Gradient surface. The general principle: tag pills must always have ≥3:1 contrast against their immediate background, regardless of whether the parent card is featured or standard.

### Content Cards (body zone)

Standard Content Card
- BG #ffffff, radius 13–16px, shadow Standard (rgba(0,0,0,0.08) 0px 4px 6px)
- Internal padding 16–24px
- Use: KPI tiles, point-by-point breakdowns, capability cards

Featured Card
- BG vibrant gradient (blue/purple/pink/orange family) or white, radius 20–24px
- Shadow Brand Glow (rgba(44,30,116,0.16) 0px 0px 15px)
- Use: hero takeaway, section opener, headline product card
- **[v2]** Tag pills inside Featured cards: solid white pill + brand blue text (see Featured-Card Tag Pill rule above)

Data Card (chart container)
- BG #ffffff, radius 13px, border 1px solid #f2f3f5, no shadow OR Standard shadow
- Title row at top (Paperlogy 600, 14pt), source line at bottom (Paperlogy 400, 9pt, #8e8e93)

**[v2] Tight Stacked Insight Card (Pattern G member — see §5)**
- Card height ≈ 1.36" (calculated from body box geometry)
- Card width: ~5.0–5.5" (right-side column)
- BG #ffffff, radius 0.13", border 1px solid #f2f3f5, shadow Standard
- Internal layout (verified empirically):

  ```
  y_offset 0.20" → Tag pill (h 0.28", w ~1.0", Paperlogy 600 9pt)
  y_offset 0.58" → Card title (h 0.30", Paperlogy 700 13pt)
  y_offset 0.93" → Body text (h ~0.32", Paperlogy 400 10pt)
  y_offset ~1.30" → bottom padding (~0.06")
  ```
- Inter-card vertical gap: 0.18"
- Body text constraint: 2 lines maximum at 10pt (≈ 60–80 Korean chars). If body needs 3+ lines, the slide is too dense — move content to a separate slide or use Pattern B (two-column).

### Charts
- Primary series: #1456f0 or #3b82f6
- Secondary series: #60a5fa, #bfdbfe, #17437d
- Negative/comparison series: #ea5ec1 or neutral #8e8e93
- Gridlines: #e5e7eb, 1px
- Axis labels: Paperlogy 400, 10pt, #45515e
- Data labels on bars/points: Paperlogy 600, 8–11pt, #222222 (use 8pt for cluster bar charts where labels sit close together)
- Always cite source under chart in 9–10pt #8e8e93

Grouped Bar Chart Settings (PptxGenJS): Grouped/clustered bar charts have a specific failure mode where the data label of one series visually collides with the adjacent bar of the next series. Do NOT solve this by drawing manual labels with computed coordinates — the plot-area geometry cannot be predicted reliably across renderers. Use these chart options instead:

```js
{
  barDir: "bar", barGrouping: "clustered",
  showValue: true,
  dataLabelFontSize: 8,
  dataLabelPosition: "outEnd",
  dataLabelFormatCode: '0.0"%"',
  valAxisMinVal: 0,
  valAxisMaxVal: <data_max * 1.3>,  // headroom for outEnd labels (e.g., 88 for data peaking at ~65)
  barGapWidthPct: 100,              // gap between category clusters
  barOverlapPct: -30,               // intra-cluster gap; negative = bars push apart
}
```

`barOverlapPct` is undocumented in the PptxGenJS API surface but is implemented in the chart XML writer and accepted by both PowerPoint and LibreOffice. Negative values create separation between bars in the same cluster, which is the correct fix for label/bar collision in clustered bar charts.

### Tables
- Header row: BG #f2f3f5, Paperlogy 600 12pt, #222222
- Body rows: Paperlogy 400 12pt, #222222, alternating BG #ffffff / #fafafa optional
- Row dividers: 1px #e5e7eb
- Cell padding: 8px 12px
- No vertical dividers — rely on column spacing

### Links / Inline Emphasis
- Primary inline: #1456f0, no underline, Paperlogy 500
- Source attribution: #8e8e93, Paperlogy 400, 9–10pt

---

## 5. Layout Principles

### Slide Grid (16:9, 13.333" × 7.5")
- Outer margins: 0.5" left/right, 0.4" top, 0.3" bottom
- Content width: 12.333"
- Content height: 6.8"
- Internal column system: 12-column grid, 0.2" gutter (column width ≈ 0.95")

### Vertical Zones (locked — identical coordinates on every slide)
| Zone | Y-range (from top) | Contents |
|---|---|---|
| Header strip | 0.4" – 0.7" | Chapter name (left), Brandlogy logo (right) |
| Headline | 1.0" – 1.75" | Slide headline (대제목) |
| Subtitle | 1.63" – 2.03" | Subtitle (부제목, one-sentence lead, 16pt) |
| Body box | 2.39" – 6.85" | All body components, charts, diagrams |
| Clearance buffer | 6.85" – 7.05" | Empty — no content, no padding |
| Footer strip | 7.05" – 7.3" | Page number (left), source line (right) |

Lock rule: These zones do not shift between slides. The header → headline → subtitle → body → footer rhythm is fixed across the entire deck. Body zone (2.39"–6.85", a 4.46" tall box) is where 95% of design work happens, and it must be filled densely — but only inside the box (see §0 Body Density Rule and Hard boundary).

Vertical rhythm (gaps between zones): Header → Headline = 0.3" (loose, breathing space below chapter line). Headline zone → Subtitle zone = 0.1" zone-to-zone, but visual gap between rendered headline text and subtitle text is closer to 0.13" because the headline text doesn't fill its full zone — title and subtitle read as a single tightly-coupled unit. Subtitle → Body = 0.36" (medium, lets the body box read as its own region while staying anchored to the title block). The non-uniform rhythm — loose top, tight middle, medium bottom — is what makes the title block feel like an anchor rather than a floating header.

Clearance buffer: The 0.2" gap between body box bottom (6.85") and footer strip top (7.05") is intentional. It must remain empty so the page number and source line never visually collide with body cards. Treat 6.85" as a wall.

Override exception: Section dividers, full-bleed covers, and closing slides may break the frame intentionally — but only if the break is the design point. "I had too much content" is not a valid override.

### Spacing Scale (within body zone)
- Base unit: 4px (0.028" / 0.07cm)
- Steps: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80px
- Card-to-card gap: 16–24px (≈ 0.16"–0.24" in PptxGenJS)
- Section-internal padding: 16–24px
- Headline-to-subtitle gap: 16px
- Subtitle-to-body gap: 32px

### Border Radius Scale
- 4px — small tags, micro badges
- 8px — buttons, small cards, input-like elements
- 11–13px — medium cards, data tiles
- 16–20px — large content cards
- 22–24px — hero product cards, major containers
- 30–32px — badge pills
- 9999px — full pill (buttons, tabs)

### Body Composition Patterns (use these to maintain density)

**Pattern A — KPI Strip + Detail (most common)**
- Top half of body: 3–4 KPI cards in a row (each ~3" wide × **1.5" tall** at 3-up; height tested for balance with 24pt KPI numbers and gap badge below)
- Bottom half: supporting chart on the left (~6.9" wide) and a "So What" insights panel on the right (~5.25" wide × 2.8" tall) — the wider/taller right panel accommodates 2-line insight bodies without crowding
- Inter-section gap (KPI strip → lower half): ~0.16"

**[v2] Verified KPI Card Internal Y-Coordinates (1.5"-tall, 3-up strip)**
The 1.5" KPI card has 4 stacked text elements. Use these exact Y offsets to prevent overlap between secondary value and gap badge (a recurring defect):

```
y_offset 0.16" → Label             (h 0.22", Paperlogy 600 11pt)
y_offset 0.40" → Primary value     (h 0.46", Paperlogy 700 24–26pt + 13pt unit)
y_offset 0.88" → Secondary value   (h 0.26", Paperlogy 700 17–19pt comparison)
y_offset 1.20" → Gap badge         (h 0.22", Paperlogy 600 10pt color-coded delta)
y_offset ~1.42" → bottom padding (~0.08")
```

Symptoms of incorrect Y coordinates: secondary value and gap badge visually touch or overlap (typical when secondary y_offset = 0.92 and gap badge y_offset = 1.18, leaving only 0.04" gap). Verify by computing y_secondary + h_secondary vs y_gap_badge — there must be ≥ 0.06" between them.

**Pattern B — Two-Column Compare**
- Left column (5.5" wide): claim + supporting bullets
- Right column (5.5" wide): chart, diagram, or visual evidence
- Optional bottom-spanning "So What" callout box

**Pattern C — Diagram-Centered**
- Centered diagram occupies ~70% of body
- 3–4 caption boxes around the diagram explain components
- Bottom strip: source + summary takeaway

**Pattern D — Process Flow**
- Horizontal arrow flow with 4–6 stages across body
- Each stage: numbered circle, stage label, 1–2 line description
- Below the flow: outcomes summary or pull-quote

**Pattern E — Quote + Evidence**
- Large pull-quote (Paperlogy 500, 24–28pt) on left half
- Stack of 2–3 supporting data cards on right half

**Pattern F — Stacked Insight Layers (use when content is thin to keep density)**
- Top band: KPI summary (1 row)
- Middle band: one chart or diagram
- Bottom band: 3-up evidence cards (claim + 1-line proof + source)
- Eliminates empty bottom space without padding

**[v2] Pattern G — Stacked Vertical Insight Cards (right-column accent)**
Use when the body is split 2-column with a chart/diagram on the left and 3 short insight cards stacked vertically on the right. Common pairing: "main visualization + supporting takeaways."

Geometry (verified):
- Right column width: 5.0–5.5" (works with chart width 7.4–7.9" on the left + 0.24" gutter)
- Per-card height: (4.46 − 2 × 0.18) / 3 ≈ **1.36"**
- Inter-card gap: 0.18"
- Total stack height: 3 × 1.36 + 2 × 0.18 = 4.44" (≤ body box 4.46")

Per-card internal layout (use the Container-Aware Type Scale):
- Top padding: 0.20"
- Tag pill: y +0.20, h 0.28 (Paperlogy 600 9pt, w ~1.0")
- Card title: y +0.58, h 0.30 (Paperlogy 700 13pt — NOT 14pt)
- Body: y +0.93, h ~0.32 (Paperlogy 400 10pt — NOT 11pt)
- Bottom padding: ~0.06"

Body length constraint: max ~80 Korean characters / 2 lines at 10pt. If the body needs 3 lines, either tighten the copy or restructure to Pattern B (full-width two-column) where each insight gets more vertical space.

When to use Pattern G:
- A primary chart deserves the focal weight (left 7.4")
- The slide carries 3 distinct supporting insights (TOP/MID/RISK, BEFORE/NOW/AFTER, etc.)
- Each insight has a 2–4-word tag identifier and a short headline-plus-evidence
- Symptom of wrong pattern choice: any insight needs more than 2 body lines → use Pattern B instead

When NOT to use Pattern G:
- Only 1–2 insights — use a single "So What" panel (Pattern A's right panel)
- 4+ insights — use Pattern F (3 horizontal bands) or restructure
- Insights are KPI numbers, not narrative — use Pattern A's KPI strip instead

---

## 6. Depth & Elevation

| Level | Treatment | Use |
|---|---|---|
| 0 — Flat | No shadow | Background, in-flow text |
| 1 — Subtle | rgba(0,0,0,0.08) 0px 4px 6px | Standard content cards |
| 2 — Ambient | rgba(0,0,0,0.08) 0px 0px 22.576px | Soft surrounding glow |
| 3 — Brand Glow | rgba(44,30,116,0.16) 0px 0px 15px | Featured/takeaway cards |
| 4 — Elevated | rgba(36,36,36,0.08) 0px 12px 16px -4px | Hero, hover-equivalent emphasis |

Use Brand Glow sparingly — at most one element per slide. Standard shadow handles most cards. Flat is the default for blocks of text directly on the white slide background.

---

## 7. Do's and Don'ts

### Do
- Anchor chapter name, headline, and subtitle at the same coordinates on every single slide
- Fill the lower body box with structured, dense content (charts, KPI cards, 2-column layouts, evidence stacks)
- Use Paperlogy weights — not different families — to build hierarchy
- Apply pill radius (9999px) for tabs/toggles, 8px for action buttons, 16–24px for content cards
- Reserve the brand purple-tinted shadow for the single featured element on a slide
- Keep body copy at Paperlogy 400–500; use 700 only for emphasis and KPI numbers
- Cite every data source in 9–10pt #8e8e93 at the bottom of the relevant element
- Use 12-column internal grid logic for body layouts
- For grouped bar charts, set `barOverlapPct: -30` and `valAxisMaxVal` ≈ 1.3× the data peak so labels don't collide with adjacent bars
- Use a fresh shadow object per shape (factory function) — do not reuse a single shadow object across multiple PptxGenJS calls
- Always set `margin: 0` on text boxes for accurate Y-positioning
- **[v2] Drop one step on the type scale (14→13, 11→10) when a card is shorter than 1.5"** — the standard hierarchy assumes "regular" containers, and tighter ones need smaller type to preserve the 0.06–0.10" of bottom padding that makes a card breathe
- **[v2] Use solid white pill + brand blue text for tag pills inside Featured (blue) cards** — never transparency on white, which renders the pill invisible
- **[v2] Reconcile every number on a slide against its source before finalizing** — headline % must match chart sum, callouts must trace to displayed data; three different versions of the same metric on one slide is a defect, not a stylistic choice
- **[v2] For 1.5"-tall KPI cards, use the verified Y-offsets** (label 0.16, primary 0.40, secondary 0.88, gap badge 1.20) so secondary value and gap badge don't overlap

### Don't
- Don't leave the bottom 20–30% of the body zone visually empty — restructure or add evidence/callout
- Don't use any font other than Paperlogy — no Pretendard, DM Sans, Outfit, Poppins, Roboto, Noto, Apple SD Gothic, Malgun Gothic, system defaults
- Don't use the MiniMax logo or any logo other than Brandlogy
- Don't deviate from the locked zone coordinates (header strip, headline, subtitle, body box, footer strip) across slides — same Y for chapter, headline, subtitle, body top, body bottom, logo, and source line on every page. Override only when structurally unavoidable (section divider, full-bleed cover, closing slide).
- Don't let body content invade the headline/subtitle zones above 2.39" or the clearance buffer / footer strip below 6.85" — if it doesn't fit, split the slide
- Don't apply brand pink (#ea5ec1) to body text or buttons — decorative accents only
- Don't use sharp corners on content cards — minimum radius is 8px, body cards 13–24px
- Don't darken shadows past 0.16 opacity — light-and-airy is the brand register
- Don't apply Hero Gradient to chart bars, lines, or any data series — gradients create false visual hierarchy on data. Charts use flat brand blue.
- Don't apply Hero Gradient to text or use gradient-text effects — solid #222222 for ink, white for text on gradient surfaces.
- Don't use more than one Hero Gradient element per slide, and don't exceed 3 gradient elements across the entire deck.
- Don't vary the gradient angle, stops, or colors — Hero Gradient is fixed at linear-gradient(135deg, #1456f0 0%, #3b82f6 50%, #60a5fa 100%).
- Don't pad slides with decorative shapes or stock illustrations to fake density — use real evidence
- Don't introduce a second display family alongside Paperlogy
- Don't use weight 800–900 for body headings (reserve for closing slide / section divider only)
- Don't use emojis anywhere on slides
- Don't compute manual data-label coordinates over a chart — plot-area geometry is not predictable across renderers. Use chart options (`barOverlapPct`, `valAxisMaxVal`, `dataLabelPosition`) instead.
- Don't prefix hex colors with `#` in PptxGenJS — use 6-character hex without prefix. `#` corrupts the file.
- Don't encode opacity in 8-character hex (e.g., `00000020`). Use the separate `opacity` / `transparency` property.
- **[v2] Don't fill a card edge-to-edge with text** — if the body abuts the bottom border with no padding, drop one font size step before declaring it "dense." Tight ≠ dense; tight is a defect.
- **[v2] Don't put a transparent (or 80%-opacity) white tag pill on a Featured blue card** — the pill renders invisible and the text loses contrast. Use solid white + brand blue text instead.
- **[v2] Don't let a slide carry conflicting versions of the same number** — if the headline says 75%, a chart sums to 82%, and a callout shows 87.6%, fix the source-of-truth and propagate. Do not paper over with vague language.
- **[v2] Don't size Pattern G insight-card text the same as standard body text** (14pt title + 11pt body). The 1.36" container is too tight; use 13pt title + 10pt body per the Container-Aware Type Scale.

---

## 8. Aspect Ratio & Export Notes

- 16:9 only. Reject 4:3, 1:1, 9:16, A4, letter, or any other format requests.
- Export resolution target: 1920 × 1080 px minimum for image preview; native PowerPoint vector preserved in the .pptx.
- Embedded font: Paperlogy must be embedded in the .pptx (Save options → "Embed fonts in the file") so the layout survives on machines without Paperlogy installed. Embed all weights actually used in the deck (typically 400/500/600/700 at minimum).
- All chart text and data labels must be live text (not rasterized images) to keep edit-ability.

### Visual QA Pass (run before declaring done)
After generating a .pptx, render it to an image and visually inspect before delivery:

```bash
# Convert .pptx → PDF using LibreOffice
python /mnt/skills/public/pptx/scripts/office/soffice.py --headless --convert-to pdf <file>.pptx

# Rasterize PDF → JPG at 150 DPI
rm -f slide-*.jpg
pdftoppm -jpeg -r 150 <file>.pdf slide

# View the result
view slide-1.jpg
```

Then run the iteration checklist below against the rendered image, not just the source code. Code can compile cleanly but still produce overlapping labels, off-by-half-inch zones, colors that read wrong at slide scale, or text that fills cards edge-to-edge ("꽉 차있어" defect — see Breathing Room Rule).

---

## 9. Agent Prompt Guide

### Quick Reference Strip
- Aspect: 16:9 only
- Bg: #ffffff (every slide), #181e25 (closing/divider only)
- Headline: #222222, Paperlogy 700, 32–40pt, charSpacing -0.6 for 36pt+
- Subtitle: #45515e, Paperlogy 500, 16pt
- Body: #222222, Paperlogy 400, 12–14pt
- **[v2] Tight card (Pattern G, ~1.36" tall): title 13pt / body 10pt / tag 9pt** — drop one step from regular body
- Source/caption: #8e8e93, Paperlogy 400, 9–10pt
- Brand blue: #1456f0 / #3b82f6 / #60a5fa
- Hero Gradient (premium accent, max 3 elements per deck): linear-gradient(135deg, #1456f0 0%, #3b82f6 50%, #60a5fa 100%) — for cover hero card / section divider bg / 1 featured KPI per slide. Pair with Brand Glow shadow. Never on charts, text, headers, or footers. **In PptxGenJS, substitute solid #1456f0 + Brand Glow shadow** since native gradients aren't supported in shape fills.
- Brand pink (accents only): #ea5ec1
- Borders: #e5e7eb, #f2f3f5
- Logo: Brandlogy, top-right (≈0.5" from right edge, y≈0.44"), insert provided PNG as-is, ≈1.22"×0.24" aspect-locked, alpha preserved (no background fill / underline / shadow / recolor / crop)
- Page number: bottom-left, Paperlogy 500 10pt #8e8e93
- Font: **Paperlogy only** (weights 100–900, files Paperlogy-1Thin through Paperlogy-9Black)
- Chart safe defaults (clustered bars): `barOverlapPct: -30`, `barGapWidthPct: 100`, `valAxisMaxVal` ≈ 1.3× data peak, `dataLabelFontSize: 8`, `dataLabelPosition: "outEnd"`
- PptxGenJS hex format: 6 characters, no `#` prefix; never 8-character hex with embedded alpha
- **[v2] KPI card Y-offsets (1.5"-tall, 3-up strip): label 0.16 / primary 0.40 / secondary 0.88 / gap badge 1.20**
- **[v2] Featured-card tag pill: solid #ffffff fill + #1456f0 text** (NOT transparent white)

### Example Component Prompts

Cover Slide (Hero Gradient option)
"Build a 16:9 cover slide on #ffffff. Slide headline at 1.0"–1.75" from top, Paperlogy 700, 40pt, #222222, line-height 1.20. Subtitle at 1.63"–2.03", Paperlogy 500, 16pt, #45515e, line-height 1.45. Body zone (2.39"–6.85"): single hero featured card with solid #1456f0 background (PptxGenJS gradient substitute), 24px radius, Brand Glow shadow rgba(44,30,116,0.16) 0px 0px 15px (use a factory function for the shadow object), containing the deck's central KPI in Paperlogy 700 24pt #ffffff (white text on blue — never blue-on-blue) with a 11pt Paperlogy 500 rgba(255,255,255,0.85) label below. Brandlogy logo at top-right (insert provided PNG file as-is, ≈1.22"×0.24" aspect-locked, alpha preserved — no background fill, no decorations, no recolor), page number at bottom-left. Body content stays strictly above 6.85" — clearance buffer 6.85"–7.05" remains empty. Keep at least 0.06–0.10" of bottom padding inside the hero card so source line and KPI numbers don't overlap."

Content Slide — KPI Strip + Chart + So What (Pattern A, tested)
"Build a 16:9 content slide. Chapter name top-left at y=0.4" baseline, Paperlogy 600 12pt #8e8e93. Brandlogy logo top-right at y≈0.44", insert provided PNG file as-is (≈1.22"×0.24" aspect-locked, transparent alpha preserved, no background fill / underline / box / recolor). Headline at 1.0"–1.75", Paperlogy 700 36pt #222222, charSpacing -0.6. Subtitle at 1.72"–2.03", Paperlogy 500 16pt #45515e.

Body zone split:
- Top band (y 2.39"–3.89", h=1.5"): row of 3 KPI cards. Card 1 is featured (solid #1456f0 bg, 0.18 radius, Brand Glow shadow); cards 2–3 are standard (white bg, 0.13 radius, 1px #f2f3f5 border, Standard shadow). Each card width ≈3.98", gap 0.18". Inside each card, use these verified Y-offsets to prevent label/value overlap: label at y_offset 0.16 (h 0.22, Paperlogy 600 11pt); primary value at y_offset 0.40 (h 0.46, Paperlogy 700 24–26pt + 13pt unit); secondary comparison value at y_offset 0.88 (h 0.26, Paperlogy 700 17–19pt, #8e8e93 or rgba white on featured); gap badge at y_offset 1.20 (h 0.22, Paperlogy 600 10pt color-coded).
- Inter-band gap: 0.16".
- Lower band (y 4.05"–6.85", h=2.8"): two columns. Left column = chart container, width 6.9", white bg, 1px #f2f3f5 border, 0.13 radius. Inside: title Paperlogy 600 14pt #222222; horizontal grouped bar chart (barDir 'bar', clustered, primary #1456f0, comparison #ea5ec1, dataLabelFontSize 8, dataLabelPosition 'outEnd', valAxisMaxVal ≈ 1.3× data peak, barGapWidthPct 100, barOverlapPct -30); source line Paperlogy 400 9pt #8e8e93 below chart. Right column = "So What" panel, width 5.25", white bg, 1px #f2f3f5 border, 0.13 radius, Standard shadow. Header 'So What — 핵심 시사점' Paperlogy 600 12pt #1456f0. Three insight items, each with a 0.06"×0.62" left accent bar (color rotates: #1456f0, #ea5ec1, #60a5fa), title Paperlogy 600 13pt #222222, body Paperlogy 400 11pt #45515e (up to 2 lines).

Page number at bottom-left (y=7.05"), source/footnote at bottom-right (y=7.05"). All hex colors as 6 characters without #. All margins set to 0 on text boxes."

**[v2] Content Slide — Chart + Stacked Insight Cards (Pattern G, tested)**
"Build a 16:9 content slide with the standard locked zones (header / headline / subtitle / footer at fixed Y). Body zone splits into two columns:
- Left (x 0.5", w 7.4"): chart container, white bg, 0.13 radius, 1px #f2f3f5 border, Standard shadow. Inside: chart title Paperlogy 600 13pt #222222 at top, primary horizontal bar chart with #1456f0 series, source line Paperlogy 400 9pt #8e8e93 at bottom.
- Right (x 8.14", w ~5.0"): three vertically stacked insight cards. Each card: w 5.0", h 1.36", gap 0.18". White bg, 0.13 radius, 1px #f2f3f5 border, Standard shadow.

Inside each insight card use the Tight Container type scale (one step smaller than standard body):
- Tag pill at y_offset 0.20, w ~1.0", h 0.28, fill = tag color (e.g., #1456f0 / #ea5ec1 / #8e8e93), Paperlogy 600 9pt #ffffff centered.
- Card title at y_offset 0.58, h 0.30, Paperlogy 700 13pt #222222.
- Body at y_offset 0.93, h ~0.32, Paperlogy 400 10pt #45515e, max 2 lines (~80 Korean chars).
- Bottom padding ~0.06" — body must NOT touch the card border.

If any body needs 3+ lines or feels packed, drop content or switch to Pattern B (full two-column, more vertical room). Do NOT use 14pt title + 11pt body in this geometry — it fills edge-to-edge and breaks the breathing rhythm."

Two-Column Compare
"Build a 16:9 slide with anchors as standard. Body zone: two columns, 5.5" wide each, 0.4" gutter. Left column header Paperlogy 600 18pt #222222, body bullets Paperlogy 400 13pt #222222 line-height 1.50. Right column same structure but with a vertical bar chart (primary #1456f0, comparison #ea5ec1, barOverlapPct -30 if clustered). Add a 'So What' callout box spanning full width at the bottom of the body zone, BG #f2f3f5, 13px radius, padding 16px, Paperlogy 600 14pt #222222."

Section Divider
"Build a 16:9 section divider on #181e25 (dark) BG OR a pre-rendered PNG of the Hero Gradient linear-gradient(135deg, #1456f0 0%, #3b82f6 50%, #60a5fa 100%) inserted as a full-bleed background image (since PptxGenJS shape fills don't support native gradients). Section number top-left in Paperlogy 600 14pt rgba(255,255,255,0.6). Brandlogy logo top-right in white variant (original asset uniformly inverted to white — no other modification). Section title centered vertically, Paperlogy 700 56pt #ffffff. One-line lead under title, Paperlogy 500 22pt rgba(255,255,255,0.7), line-height 1.45. Page number bottom-left in rgba(255,255,255,0.6)."

### Iteration Checklist (run before exporting any slide)
1. Aspect ratio 16:9? ✓
2. **Paperlogy everywhere — no other fonts (no Pretendard, no system fallbacks)?** ✓
3. Brandlogy logo at top-right, original asset with transparency preserved (no black/white box behind), no underline / shadow / recolor / crop / rotation? ✓
4. All five zone anchors (header / headline / subtitle / body box / footer) match previous slide coordinates? ✓
5. Body content stays strictly inside 2.39"–6.85" — no invasion of headline/subtitle zones above or clearance buffer/footer below? ✓
6. Lower body box filled with dense, structured content (no empty bottom 30% within the box)? ✓
7. If the slide carries data / comparison / process / structure — is it visualized as a chart or diagram (not narrated as prose)? ✓
8. For grouped bar charts: is `barOverlapPct: -30` set so labels don't collide with adjacent bars? Is `valAxisMaxVal` ≈ 1.3× data peak so `outEnd` labels have room? ✓
9. KPI numbers sized correctly (24pt primary / 19pt secondary for 1.5"-tall cards)? ✓
10. **[v2] KPI card internal Y-offsets match the verified values** (label 0.16, primary 0.40, secondary 0.88, gap badge 1.20) so secondary value and gap badge don't overlap? ✓
11. Every data point has a source line? ✓
12. At most one Brand Glow element on the slide? ✓
13. Hero Gradient (if used) only on permitted locations (cover hero card / section divider bg / 1 featured KPI), max 1 per slide and max 3 across the deck, never on chart bars or text? Solid #1456f0 substitute used where PptxGenJS shape fill is involved? ✓
14. Headline weight 700 (charSpacing -0.6 for 36pt+), subtitle weight 500, body 400 — hierarchy holds? ✓
15. **[v2] For tight containers (Pattern G stacked cards ~1.36" tall): title is 13pt (NOT 14), body is 10pt (NOT 11), tag is 9pt (NOT 10)** — Container-Aware Type Scale applied? ✓
16. **[v2] Breathing Room Rule: every card has at least 0.06–0.10" of bottom padding** — text does NOT abut the card border ("꽉 차있어" check)? ✓
17. **[v2] Featured (blue) card tag pills use solid white fill + brand blue text**, not transparent white? ✓
18. **[v2] Data Consistency: every number on the slide reconciles to source** — headline %, chart sum, and callouts agree (no 75% / 82% / 87.6% conflict)? ✓
19. No emojis anywhere? ✓
20. All chart/data text is live (not rasterized)? ✓
21. Paperlogy embedded in the .pptx export so layout survives on machines without it installed? ✓
22. All hex colors are 6-character without `#` prefix; no 8-character hex with embedded alpha? ✓
23. All text boxes have `margin: 0` set? ✓
24. Shadow objects created via factory function (not shared references)? ✓
25. **Visual QA done**: rendered to PDF + JPG and inspected — no overlapping labels, no off-position elements, colors read correctly at slide scale, no edge-to-edge text in tight cards? ✓

---

## Appendix — v2 Refinement Summary

What changed from v1 (consolidated for quick scan):

1. **Pattern G — Stacked Insight Cards** (new). Right-column accent of 3 cards stacked vertically in a 2-column body, each ≈1.36" tall. Pairs with a primary chart on the left (~7.4" wide).

2. **Container-Aware Type Scale** (new). Standard hierarchy assumes ≥1.5" containers. For tighter ones (Pattern G's ~1.36" cards), drop one step: title 14→13pt, body 11→10pt, tag 10→9pt. Empirically verified — using regular sizes fills the card edge-to-edge.

3. **Breathing Room Rule** (new). Density ≠ edge-to-edge text. Every card needs ≥0.06–0.10" of bottom padding. If text abuts the border, drop a type-scale step before considering layout changes.

4. **Featured-Card Tag Pill** (correction). Inside Featured (blue) cards, tag pills must use solid white fill + brand blue text. Transparent white pills (e.g., 80% opacity) render invisible against blue and break legibility.

5. **KPI Card Y-Offsets** (verified). Internal layout for 1.5"-tall, 3-up KPI cards: label 0.16 / primary 0.40 / secondary 0.88 / gap badge 1.20. Prevents the recurring secondary-vs-gap overlap defect.

6. **Data Consistency Rule** (new). Every number on a slide must reconcile against its source. Headline, chart sum, and callouts must agree. Three different versions of the same metric on one slide is a defect.

End of system. Apply consistently across every slide in the deck.
