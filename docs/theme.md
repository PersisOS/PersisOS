# PersisOS Theme Guide

This document describes the visual identity of PersisOS and where each part
of it lives, so future changes stay coherent.

## Design language: "violet night"

One quiet idea: **a dark screen with a single purple glow.** Every themed
surface (boot splash, login, session accents) uses the same palette, the same
typography rules, and restrained motion. Nothing bounces, nothing blinks
fast, nothing competes with the logo.

The logo itself (`persisos.svg`) is never restyled or recolored; all themes
render it as-is.

## Palette

| Token | Hex | Used for |
|---|---|---|
| `bg` | `#141317` | Splash and greeter background |
| `surface` | `#1b171f` | Frosted card / panels |
| `field` | `#241e2b` | Input fields |
| `field-border` | `#3a3142` | Unfocused field border |
| `brand` | `#9738ba` | Logo color, selection highlight, titlebar blend |
| `glow` | `#b25ae8` | Focus ring, progress line, hover accents |
| `ink` | `#f4eff8` | Primary text |
| dim text | `ink` at 45–55% opacity | Labels, hints, footer branding |

Rules of thumb: purple is the only saturated color on themed screens; white
appears only as low-opacity structure (dividers, track lines); never use a
second hue.

## Typography

Noto Sans everywhere. Wordmarks use large letter-spacing (4–6) and no bold
weight. Labels are small (9 pt) with letter-spacing 1 and reduced opacity
instead of grey colors.

## Motion

- Durations: 200–900 ms, `OutCubic` for movement, `InOutSine` for opacity loops.
- One animated element at a time; loops must be slow (≥ 1.4 s per cycle).
- The splash progress line is tied to real ksplash stages — never fake
  progress.

## Components and file locations

All paths are relative to `assets/persisos-plasma-theme/`.

| Screen | File |
|---|---|
| Boot splash | `usr/share/plasma/look-and-feel/org.persisos.desktop/contents/splash/Splash.qml` |
| Login (SDDM greeter) | `usr/share/sddm/themes/persisos-greeter/Main.qml` |
| SDDM theme registration | `usr/share/sddm/themes/persisos-greeter/metadata.desktop` |
| SDDM wallpaper | `usr/share/sddm/themes/persisos-greeter/theme.conf` |
| SDDM selection | `etc/sddm.conf.d/persisos.conf` (`Current=persisos-greeter`) |
| Session color scheme | `etc/xdg/kdeglobals` |

The SDDM greeter is installed by `hooks/desktop/plasma-assets.sh`; the
`etc/` defaults by `hooks/desktop/desktop-defaults.sh`. If you add files
under a new `usr/share/` subdirectory, make sure a hook copies it.

## Logout / shutdown

Plasma 6 does not allow the logout confirmation dialog to be themed through
the look-and-feel package. The stock dialog is kept on purpose; continuity
comes from the shared dark palette, not a custom dialog. Do not ship a
custom `contents/logout/Logout.qml` — it risks breaking logout on Plasma
updates.

## Changing the theme

- Keep new colors out; extend the table above only if a token is genuinely
  missing.
- Test any QML change by booting the live ISO in a VM: splash, login
  (wrong password included), and a normal session login.
- Update the mockup `docs/theme-mockup.svg` when a screen's layout changes.
