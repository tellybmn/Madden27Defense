"""Synthetic offline HTML mimicking huddle.gg / madden.tools playbook DOM structure."""

BASE = "https://huddle.gg/playbooks/minnesota-vikings"

INDEX_HTML = """<!doctype html><html><head><title>Minnesota Vikings Defensive Playbook</title></head>
<body><main><h1 class="playbook-title">Minnesota Vikings</h1>
<nav class="formation-grid" data-role="formation-nav">
  <a class="formation-card" href="/playbooks/minnesota-vikings/nickel-2-4-dbl-mug" data-formation="Nickel 2-4 Dbl Mug"><h3 class="formation-name">Nickel 2-4 Dbl Mug</h3></a>
  <a class="formation-card" href="/playbooks/minnesota-vikings/dollar-3-2"><h3 class="formation-name">Dollar 3-2</h3></a>
  <a class="formation-card" href="/playbooks/minnesota-vikings/3-4-bear"><h3 class="formation-name">3-4&nbsp;Bear</h3></a>
  <a class="formation-card" href="https://huddle.gg/playbooks/minnesota-vikings/nickel-3-3-swap-mug"><span class="formation-name">Nickel 3-3  Swap Mug</span></a>
  <a class="formation-card" href="/playbooks/minnesota-vikings/dollar-3-2"><h3 class="formation-name">Dollar 3-2</h3></a>
  <a class="formation-card" href="javascript:void(0)"><h3 class="formation-name">Broken Card</h3></a>
  <a class="formation-card"><h3 class="formation-name">No Href</h3></a>
  <a class="nav-link" href="/about">About</a>
</nav></main></body></html>"""

FORMATION_HTML = """<!doctype html><html><body><h1 class="formation-title">Nickel 2-4 Dbl Mug</h1>
<table class="play-table"><tbody>
  <tr class="play-row"><td class="play-name">Mid Blitz 0</td><td class="play-meta">DEF</td></tr>
  <tr class="play-row"><td class="play-name">Nickel Dog 3 Buzz</td></tr>
  <tr class="play-row"><td class="play-name">Cover 4 Palms</td></tr>
  <tr class="play-row"><td class="play-name">Cover 3 Match</td></tr>
  <tr class="play-row"><td class="play-name">Tampa 2</td></tr>
  <tr class="play-row"><td class="play-name">Pinch Dog 2</td></tr>
  <tr class="play-row"><td class="play-name">Edge Sting</td></tr>
  <tr class="play-row"><td class="play-name">Cover 1 Robber</td></tr>
  <tr class="play-row"><td class="play-name">Split-Field Cover 6</td></tr>
  <tr class="play-row"><td class="play-name">  Tampa   2 </td></tr>
  <tr class="play-row"><td class="play-name"></td></tr>
</tbody></table></body></html>"""

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
