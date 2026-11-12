"""Project builder: the Customize step's choices beyond style, colour and motion.

The wizard sends ``look.custom`` as ``{key: value}`` for typography, buttons and
surfaces. ``normalize_custom`` keeps only known keys and values (unknown input is
dropped, never guessed), and ``custom_lines`` turns them into concrete guidance
and CSS tokens for the new project's docs/UI_UX.md.
"""

from __future__ import annotations

# key -> (label, {value: (name, what it means for the build)})
CHOICES: dict[str, tuple[str, dict[str, tuple[str, str]]]] = {
    "font": ("Typeface", {
        "sans": ("Modern sans", "a neutral sans-serif for headings and body"),
        "serif": ("Classic serif", "serif headings with a sans-serif body"),
        "geometric": ("Geometric", "a geometric sans with round letterforms"),
        "mono": ("Mono accents", "monospace headings and labels with a sans-serif body"),
        "humanist": ("Humanist", "a humanist sans with calligraphic, open letterforms"),
        "slab": ("Slab serif", "slab-serif headings with a sans-serif body"),
        "rounded": ("Rounded", "a rounded sans with soft stroke ends"),
        "condensed": ("Condensed", "condensed headings with a regular sans-serif body"),
    }),
    "scale": ("Text size", {
        "compact": ("Compact", "15px body text, a tight type scale"),
        "comfortable": ("Comfortable", "16px body text, a balanced type scale"),
        "large": ("Large", "18px body text, large headings"),
    }),
    "btnShape": ("Button shape", {
        "square": ("Square", "0px corners"),
        "soft": ("Soft", "6px corners"),
        "rounded": ("Rounded", "12px corners"),
        "pill": ("Pill", "fully round ends (999px)"),
    }),
    "btnFill": ("Button fill", {
        "solid": ("Solid", "filled with the primary colour"),
        "tint": ("Soft tint", "a see-through tint of the primary colour with primary text"),
        "outline": ("Outline", "a 1px primary border on a transparent background"),
        "ghost": ("Ghost", "primary text only, filling with a tint on hover"),
    }),
    "btnHover": ("Button hover", {
        "lift": ("Lift", "rises 1px with a soft shadow"),
        "darken": ("Deepen", "the colour deepens"),
        "glow": ("Glow", "a soft halo in the primary colour"),
        "none": ("Still", "no change beyond the cursor"),
    }),
    "corners": ("Corners", {
        "sharp": ("Sharp", "0px radius on cards and fields"),
        "soft": ("Soft", "8px radius on cards and fields"),
        "round": ("Round", "16px radius on cards and fields"),
    }),
    "depth": ("Depth", {
        "flat": ("Flat", "surfaces separated by colour only"),
        "border": ("Bordered", "1px borders around surfaces"),
        "shadow": ("Raised", "soft, offset shadows under surfaces"),
        "glass": ("Glass", "translucent surfaces with a background blur"),
    }),
    "density": ("Spacing", {
        "compact": ("Compact", "a 4px spacing unit, tight gaps"),
        "comfortable": ("Comfortable", "an 8px spacing unit"),
        "airy": ("Airy", "a 12px spacing unit, generous gaps"),
    }),
}

_RADIUS = {"square": "0px", "soft": "6px", "rounded": "12px", "pill": "999px"}
_CORNERS = {"sharp": "0px", "soft": "8px", "round": "16px"}
_SPACE = {"compact": "4px", "comfortable": "8px", "airy": "12px"}
_BODY = {"compact": "15px", "comfortable": "16px", "large": "18px"}
_FONTS = {
    "sans": ('system-ui, -apple-system, "Segoe UI", Roboto, sans-serif', 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'),
    "serif": ('Georgia, "Times New Roman", serif', 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'),
    "geometric": ('"Avenir Next", "Century Gothic", Futura, sans-serif', '"Avenir Next", "Century Gothic", Futura, sans-serif'),
    "mono": ('ui-monospace, "SF Mono", Menlo, Consolas, monospace', 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'),
    "humanist": ('"Gill Sans", "Gill Sans MT", Optima, Candara, "Segoe UI", sans-serif', '"Gill Sans", "Gill Sans MT", Optima, Candara, "Segoe UI", sans-serif'),
    "slab": ('Rockwell, "Roboto Slab", "Courier New", serif', 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'),
    "rounded": ('ui-rounded, "SF Pro Rounded", "Arial Rounded MT Bold", Nunito, sans-serif', 'ui-rounded, "SF Pro Rounded", Nunito, system-ui, sans-serif'),
    "condensed": ('"Avenir Next Condensed", "Roboto Condensed", Bahnschrift, "Arial Narrow", sans-serif', 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'),
}


def normalize_custom(raw) -> dict | None:
    """Known keys with known values only; None when nothing valid is left."""
    if not isinstance(raw, dict):
        return None
    out = {}
    for key, (_label, values) in CHOICES.items():
        value = str(raw.get(key) or "").strip()
        if value in values:
            out[key] = value
    return out or None


def custom_lines(custom: dict) -> list[str]:
    """Markdown for the project's UI doc: each choice, what it means, and CSS tokens."""
    lines = []
    for key, (label, values) in CHOICES.items():
        if key in custom:
            name, meaning = values[custom[key]]
            lines.append(f"- {label}: **{name}** ({meaning})")
    tokens = []
    if "font" in custom:
        head, body = _FONTS[custom["font"]]
        tokens += [f"  --font-heading: {head};", f"  --font-body: {body};"]
    if "scale" in custom:
        tokens.append(f"  --text-body: {_BODY[custom['scale']]};")
    if "btnShape" in custom:
        tokens.append(f"  --radius-button: {_RADIUS[custom['btnShape']]};")
    if "corners" in custom:
        tokens.append(f"  --radius-surface: {_CORNERS[custom['corners']]};")
    if "density" in custom:
        tokens.append(f"  --space-unit: {_SPACE[custom['density']]};")
    if tokens:
        lines += ["", "Shape and type tokens:", "", "```css", ":root {", *tokens, "}", "```"]
    return lines
