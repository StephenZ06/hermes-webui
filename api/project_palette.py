"""Project builder colour palette (the wizard's Look & feel step).

A palette is ``{"name", "source", "light", "dark", "why"}``, where ``light``
and ``dark`` each map the five roles in ``ROLES`` to ``#rrggbb``. It comes from
the planner (recommended from the brief), the user's logo, a preset or the
user's own picks. ``normalize_palette`` keeps only valid hex colours, and
derives a readable dark set when the dark one is missing or broken.
``palette_lines`` is what ``api.project_toolkit`` writes into the new project.
"""

from __future__ import annotations

import colorsys
import re

ROLES = ("bg", "surface", "text", "primary", "accent")
SOURCES = ("recommended", "logo", "preset", "custom")
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_SOURCE_LABEL = {"recommended": "recommended from the brief", "logo": "from the logo",
                 "preset": "a preset", "custom": "picked by hand"}
_ROLE_LABEL = {"bg": "page background", "surface": "cards and panels", "text": "body text",
               "primary": "buttons, links and focus", "accent": "highlights and secondary actions"}


def normalize_hex(value) -> str | None:
    text = str(value or "").strip()
    if not _HEX_RE.fullmatch(text):
        return None
    text = text.lower()
    if len(text) == 4:
        text = "#" + "".join(c * 2 for c in text[1:])
    return text


def _set(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    out = {}
    for role in ROLES:
        value = normalize_hex(raw.get(role))
        if value is None:
            return None
        out[role] = value
    return out


def _rgb(hex_: str) -> tuple[float, float, float]:
    return tuple(int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in rgb)


def luminance(hex_: str) -> float:
    """WCAG relative luminance."""
    def channel(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in _rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _hls(hex_: str) -> tuple[float, float, float]:
    return colorsys.rgb_to_hls(*_rgb(hex_))


def _from_hls(h: float, l: float, s: float) -> str:
    return _hex(colorsys.hls_to_rgb(h, l, s))


def _readable_on(hex_: str, bg: str, target: float = 4.5) -> str:
    """The same hue, lightened until it reads on ``bg``."""
    h, l, s = _hls(hex_)
    l = max(l, 0.6)
    out = _from_hls(h, l, s)
    while contrast(out, bg) < target and l < 0.95:
        l = min(0.95, l + 0.02)
        out = _from_hls(h, l, s)
    return out


def derive_dark(light: dict) -> dict:
    """A dark set in the light set's hues: near-black tinted background, light text,
    and the primary and accent lightened until they read on it."""
    h, _l, s = _hls(light["primary"])
    bg = _from_hls(h, 0.08, min(s, 0.22))
    return {"bg": bg, "surface": _from_hls(h, 0.13, min(s, 0.2)), "text": _from_hls(h, 0.93, min(s, 0.12)),
            "primary": _readable_on(light["primary"], bg), "accent": _readable_on(light["accent"], bg)}


def normalize_palette(raw, *, default_source: str = "custom") -> dict | None:
    """A valid palette, or None. The light set is required; dark is derived when missing or broken."""
    if not isinstance(raw, dict):
        return None
    light = _set(raw.get("light"))
    if light is None:
        return None
    dark = _set(raw.get("dark")) or derive_dark(light)
    source = str(raw.get("source") or "").strip().lower()
    if source not in SOURCES:
        source = default_source if default_source in SOURCES else "custom"
    name = re.sub(r"\s+", " ", str(raw.get("name") or "").strip())[:40]
    return {"name": name, "source": source, "light": light, "dark": dark,
            "why": str(raw.get("why") or "").strip()[:300]}


def _tokens(colours: dict, indent: str) -> list[str]:
    return [f"{indent}--color-{role}: {colours[role]};" for role in ROLES]


def palette_lines(palette: dict) -> list[str]:
    """Markdown for the project's UI doc: the palette, what each role is for, and CSS tokens."""
    name = palette.get("name") or "Custom"
    lines = [f"- Colour palette: **{name}** ({_SOURCE_LABEL.get(palette.get('source'), 'picked by hand')})"]
    if palette.get("why"):
        lines.append(f"- Why these colours: {palette['why']}")
    lines += ["", "| Role | Light | Dark | Used for |", "| --- | --- | --- | --- |"]
    lines += [f"| `{role}` | `{palette['light'][role]}` | `{palette['dark'][role]}` | {_ROLE_LABEL[role]} |"
              for role in ROLES]
    lines += ["", "Use these tokens for every colour; support both themes (the system setting, and a",
              "`data-theme` attribute when the app has a theme switch):", "", "```css", ":root {",
              *_tokens(palette["light"], "  "), "}", "@media (prefers-color-scheme: dark) {",
              "  :root:not([data-theme=\"light\"]) {", *_tokens(palette["dark"], "    "), "  }", "}",
              ":root[data-theme=\"dark\"] {", *_tokens(palette["dark"], "  "), "}", "```"]
    return lines
