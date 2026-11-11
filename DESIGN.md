# Shishya design system: Ink & Marigold

One product, four surfaces: the home page, the control panel, the clone's
desktop, and the apps on it. They used to speak three visual languages
(frosted glass over a photo, navy and cream, a dark monospace console).
This is the one they share now. The values live in code as named tokens:
`clone/kit.py` for the Qt side, `:root` in `web/home.html` and
`web/css/style.css` for the pages. Use the names, never raw values.

The direction was chosen from the project itself (the शि mark, the butter
orb, "the counter and the desk behind it"), not from a survey of other
products.

## The idea

**A dark desk, bright paper, one warm colour.** The ground of every surface
is deep ink with a slow aurora in it. Everything you read or type into is a
crisp light sheet on top. Marigold is the only colour that means "act":
the button that does the thing, the orb, the selected row. The five soft
tints mark *kinds* of app and never mean anything else.

## Colour

| Token | Value | Role |
|---|---|---|
| `ink-950` | `#0B0C1D` | Wallpaper, lowest |
| `ink-900` | `#14162B` | Text on light; the desk; chosen tab; ticked box |
| `ink-800` | `#1C1F3A` | Dark surfaces: dock, start panel, cards on the desk |
| `ink-700` | `#2A2E52` | Edges on dark; focused field border |
| `ink-500` | `#62678A` | Secondary text on light (5.4:1 on canvas) |
| `ink-300` | `#A4A8C3` | Placeholder, disabled text, quiet icons |
| `ink-200` | `#D5D7E6` | Borders of controls |
| `ink-100` | `#E8E9F2` | Rules, tracks, hover fills |
| `ink-50`  | `#F4F5FA` | App canvas |
| `white`   | `#FFFFFF` | Sheets: cards, fields, tables, title bars |
| `on-dark` | `#F3F2FA` | Text on ink |
| `on-dark-muted` | `#A7A9C4` | Secondary text on ink |
| `marigold-500` | `#F5B63A` | Primary action fill; the orb; progress |
| `marigold-600` | `#E9A21B` | Primary hover |
| `marigold-700` | `#A86A12` | Marigold as text or line on light (4.6:1) |
| `marigold-100` | `#FDF0CC` | Selected row, your chat bubble, hover wash |
| `good` / `warn` / `bad` | `#1E8E5F` / `#B7791F` / `#CC3D2E` | State only |

Text on marigold is always `ink-900`. Never white on marigold, never
marigold text on white below `marigold-700`.

**Tints** (fill, and the dark drawn on it) name kinds of app:

| Tint | Fill | Dark | Kind |
|---|---|---|---|
| butter | `#F6E3A1` | `#5F3B06` | Money, and Shishya itself |
| mint | `#CFEBDD` | `#0A5140` | Stock and incoming things |
| peach | `#F8D0BB` | `#73301A` | Things that need a look |
| lav | `#DAD7F7` | `#3A3391` | Learning |
| paper | `#E1E5F2` | `#363B5C` | Tools and the machine |

## Type

Segoe UI Variable, which every Windows 11 has: `Display` for anything 18 px
and up, `Text` below. Cascadia Mono for programs and their output. Nirmala
UI carries the शि. Sizes are pixels, never points.

| Role | Size / weight |
|---|---|
| Greeting (home) | 44 / 600, Display |
| Clock (desk) | 44 / 600, Display |
| Page title | 20 / 600, Display |
| Body, controls | 13 / 400 (500 on buttons) |
| Label, table header | 11 / 600, +0.6 px tracking, `ink-500` |
| Code | 12, Cascadia Mono |

## Space and shape

Spacing is a 4 px scale: 4, 8, 12, 16, 24, 32. Radius: 8 small controls,
10 fields and buttons, 14 cards, 12 windows, 22 dock and panels. Shadows
exist only on the pages (`0 8px 24px rgba(11,12,29,.14)`); on the clone's
screen depth is the dark ground against light sheets.

## Components

- **Primary button**: marigold fill, ink text, 600. Hover `marigold-600`.
  One per view.
- **Button**: white, `ink-200` border; hover `ink-100`.
- **Field**: white, `ink-200` border, radius 10; focus border `ink-700`.
- **Table**: white card, no vertical lines, small-caps style header in
  `ink-500`, selected row `marigold-100`. Sheets keeps its grid.
- **Tabs**: pills; the chosen one is `ink-900` with white text.
- **Window**: white title bar with the app's tinted icon, quiet controls
  (close turns red on hover), radius 12, one-pixel `ink-200` frame.
- **Dock and start panel**: `ink-800` at 78% over the wallpaper, a
  hairline of white at 12%, radius 22.
- **Chat**: yours right on `marigold-100`; Shishya's left on white;
  programs in a `ink-50` monospace block.

## Imagery

No photographs. The wallpaper is drawn: ink with three slow glows (indigo,
teal, marigold) and a grain of noise so the gradient never bands. Icons are
the 24 px line set in `clone/kit.py`, always on a tint tile.
