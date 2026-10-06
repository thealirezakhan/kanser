"""Convert stitch screen1 (dark) to the light palette used by screens 2 & 3."""

import json
import re
from pathlib import Path

SRC = Path("stitch/screen1.html")
DST = Path("frontend/public/swarm.html")

LIGHT = {
    "on-surface-variant": "#3f4850",
    "on-tertiary-fixed-variant": "#005137",
    "on-primary-fixed-variant": "#004b73",
    "tertiary-fixed": "#85f8c4",
    "surface-variant": "#d3e4fe",
    "surface-bright": "#f8f9ff",
    "surface-dim": "#cbdbf5",
    "surface-container-high": "#dce9ff",
    "on-background": "#0b1c30",
    "on-primary-container": "#fdfcff",
    "error-container": "#ffdad6",
    "on-primary": "#ffffff",
    "background": "#f8f9ff",
    "secondary-container": "#316bf3",
    "tertiary-container": "#00855d",
    "on-secondary-container": "#fefcff",
    "on-surface": "#0b1c30",
    "on-secondary-fixed": "#00174b",
    "surface-tint": "#006398",
    "on-tertiary-container": "#f5fff7",
    "on-primary-fixed": "#001d31",
    "secondary": "#0051d5",
    "surface": "#f8f9ff",
    "primary-container": "#007bb9",
    "tertiary": "#006948",
    "surface-container-lowest": "#ffffff",
    "on-tertiary-fixed": "#002114",
    "on-error-container": "#93000a",
    "primary-fixed-dim": "#93ccff",
    "surface-container-highest": "#d3e4fe",
    "primary-fixed": "#cce5ff",
    "surface-container-low": "#eff4ff",
    "inverse-primary": "#93ccff",
    "surface-container": "#e5eeff",
    "secondary-fixed": "#dbe1ff",
    "inverse-surface": "#213145",
    "on-error": "#ffffff",
    "secondary-fixed-dim": "#b4c5ff",
    "outline": "#707881",
    "error": "#ba1a1a",
    "outline-variant": "#bfc7d2",
    "inverse-on-surface": "#eaf1ff",
    "on-secondary": "#ffffff",
    "on-tertiary": "#ffffff",
    "primary": "#006194",
    "on-secondary-fixed-variant": "#003ea8",
    "tertiary-fixed-dim": "#68dba9",
}


def replace_colors_block(s: str) -> str:
    m = re.search(r'"colors":\s*\{', s)
    assert m, "colors block not found"
    start = m.end() - 1
    depth = 0
    end = None
    for i, ch in enumerate(s[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    dark = json.loads(s[start : end + 1])
    missing = sorted(set(dark) - set(LIGHT))
    if missing:
        raise SystemExit(f"missing light values for: {missing}")
    new = ", ".join(f'"{k}": "{LIGHT[k]}"' for k in dark)
    return s[:start] + "{" + new + "}" + s[end + 1 :]


def fix_body(body: str) -> str:
    pairs = [
        ("#5dd6e8", "#007bb9"),  # gradient stops / inline accents
        ("#5DD6E8", "#007bb9"),
        ("#5ed7e9", "#007bb9"),
        ("#3d494b", "#bfc7d2"),  # muted svg line -> light outline-variant
        ("#c7beff", "#006948"),  # tertiary svg line -> light tertiary
        ("rgba(93,214,232", "rgba(0,123,185"),  # cyan glow -> blue glow
        ("rgba(0,0,0,0.5)", "rgba(0,0,0,0.12)"),
        ("rgba(0,0,0,0.4)", "rgba(0,0,0,0.10)"),
        # bypass chips collided with wrapped toolbar in light layout;
        # stacked vertically to fit the center gap between agent cards
        (
            "absolute top-4 left-1/2 -translate-x-1/2 z-20 flex gap-space-sm",
            "absolute top-16 left-1/2 -translate-x-1/2 z-20 flex flex-col gap-space-sm",
        ),
    ]
    for a, b in pairs:
        body = body.replace(a, b)
    return body


def main() -> None:
    s = SRC.read_text(encoding="utf-8")
    s = s.replace('<html class="dark"', '<html class="light"')
    s = replace_colors_block(s)
    cfg_end = s.index("</script>", s.index("tailwind.config")) + len("</script>")
    s = s[:cfg_end] + fix_body(s[cfg_end:])
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(s, encoding="utf-8")
    print(f"wrote {DST} ({len(s)} bytes)")


if __name__ == "__main__":
    main()
