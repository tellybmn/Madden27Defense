"""Loads the offline HTML fixtures (synthetic huddle.gg / madden.tools DOM) for the test suite."""
from pathlib import Path

_DIR = Path(__file__).parent

BASE = "https://huddle.gg/playbooks/minnesota-vikings"
INDEX_HTML = (_DIR / "mock_index.html").read_text(encoding="utf-8")
FORMATION_HTML = (_DIR / "mock_formation.html").read_text(encoding="utf-8")

# Expected classification of the formation page: name -> (family, rush, sim, blitz, plug)
EXPECTED = {
    "Mid Blitz 0": ("Cover 0", 6, False, True, False),
    "Nickel Dog 3 Buzz": ("Cover 3 Sky/Buzz/Cloud", 4, True, False, False),
    "Cover 4 Palms": ("Cover 4 Match/Palms", 4, False, False, False),
    "Cover 3 Match": ("Cover 3 Sky/Buzz/Cloud", 4, False, False, False),
    "Tampa 2": ("Tampa 2", 4, False, False, False),
    "Pinch Dog 2": ("Tampa 2", 4, False, False, True),
    "Edge Sting": ("Unknown", 4, False, False, True),
    "Cover 1 Robber": ("Cover 1", 4, False, False, False),
    "Split-Field Cover 6": ("Cover 6/9", 4, False, False, False),
}

PAGES = {BASE: INDEX_HTML, f"{BASE}/nickel-2-4-dbl-mug": FORMATION_HTML}
