"""SVG icon generator for RealTypeCoach."""

SVG_ICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect x="0" y="0" width="64" height="64" fill="none"/>
  <rect x="4" y="16" width="56" height="36" rx="4" fill="#3daee9" stroke="#2c7a91" stroke-width="2"/>
  <rect x="8" y="20" width="8" height="8" rx="2" fill="#ffffff"/>
  <rect x="20" y="20" width="8" height="8" rx="2" fill="#ffffff"/>
  <rect x="32" y="20" width="8" height="8" rx="2" fill="#ffffff"/>
  <rect x="44" y="20" width="8" height="8" rx="2" fill="#ffffff"/>
  <rect x="12" y="32" width="8" height="8" rx="2" fill="#ffffff"/>
  <rect x="24" y="32" width="8" height="8" rx="2" fill="#ffffff"/>
  <rect x="36" y="32" width="8" height="8" rx="2" fill="#ffffff"/>
  <circle cx="52" cy="10" r="5" fill="#ff6b6b" stroke="#c0392b" stroke-width="1"/>
  <text x="52" y="12" font-family="Arial" font-size="6" text-anchor="middle" fill="white">⚡</text>
</svg>"""

SVG_ICON_PAUSED = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect x="0" y="0" width="64" height="64" fill="none"/>
  <rect x="4" y="16" width="56" height="36" rx="4" fill="#e9c46a" stroke="#b36a40" stroke-width="2"/>
  <rect x="8" y="20" width="8" height="8" rx="2" fill="#ffffff"/>
  <rect x="20" y="20" width="8" height="8" rx="2" fill="#ffffff"/>
  <rect x="32" y="20" width="8" height="8" rx="2" fill="#ffffff"/>
  <rect x="44" y="20" width="8" height="8" rx="2" fill="#ffffff"/>
  <rect x="12" y="32" width="8" height="8" rx="2" fill="#ffffff"/>
  <rect x="24" y="32" width="8" height="8" rx="2" fill="#ffffff"/>
  <rect x="36" y="32" width="8" height="8" rx="2" fill="#ffffff"/>
  <rect x="48" y="8" width="8" height="12" rx="2" fill="#ffd700" stroke="#b8860b" stroke-width="1"/>
  <text x="52" y="17" font-family="Arial" font-size="5" text-anchor="middle" fill="black">II</text>
</svg>"""

SVG_ICON_STOPPING = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect x="0" y="0" width="64" height="64" fill="none"/>
  <rect x="4" y="16" width="56" height="36" rx="4" fill="#808080" stroke="#606060" stroke-width="2"/>
  <rect x="8" y="20" width="8" height="8" rx="2" fill="#cccccc"/>
  <rect x="20" y="20" width="8" height="8" rx="2" fill="#cccccc"/>
  <rect x="32" y="20" width="8" height="8" rx="2" fill="#cccccc"/>
  <rect x="44" y="20" width="8" height="8" rx="2" fill="#cccccc"/>
  <rect x="12" y="32" width="8" height="8" rx="2" fill="#cccccc"/>
  <rect x="24" y="32" width="8" height="8" rx="2" fill="#cccccc"/>
  <rect x="36" y="32" width="8" height="8" rx="2" fill="#cccccc"/>
  <circle cx="52" cy="10" r="5" fill="#606060" stroke="#404040" stroke-width="1"/>
  <text x="52" y="12" font-family="Arial" font-size="6" text-anchor="middle" fill="white">■</text>
</svg>"""


def save_icon(path: str, active: bool = True, stopping: bool = False) -> None:
    """Save SVG icon to file."""
    if stopping:
        icon_svg = SVG_ICON_STOPPING
    else:
        icon_svg = SVG_ICON if active else SVG_ICON_PAUSED
    with open(path, "w") as f:
        f.write(icon_svg)


def get_icon_data(active: bool = True, stopping: bool = False) -> bytes:
    """Get SVG icon as bytes."""
    if stopping:
        icon_svg = SVG_ICON_STOPPING
    else:
        icon_svg = SVG_ICON if active else SVG_ICON_PAUSED
    return icon_svg.encode("utf-8")
