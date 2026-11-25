# galaxy

A fictional galaxy to tell stories in: three linked 3D maps (the galaxy, a
star system with its orbits over time, a planet's globe) and the Python
library that builds and checks what they draw. The real sky is there from the
start: Sol and its planets, the bright stars, the constellations and the real
nebulae. A procedural galaxy fills the Milky Way's arms with systems nobody
has named yet. A story adds its own systems, gate networks, a
faster-than-light medium, nations holding systems through time, trips with
dates, and its own calendar.

Early days: the engine was extracted from one story project, its only host so
far. The data formats will still change (see *Status*).

## Parts

| | | |
|---|---|---|
| `viewer/` | JS, ES modules on [three.js](https://threejs.org) | `galaxy/galaxy-map.js`, `system/system-map.js`, `planet/globe-view.js`; shared camera, selection, search, sky, bloom and shadows in `space/` |
| `python/` | Python package `galaxy` (uv) | catalogue editing and validation, the procedural galaxy, orbits and positions at a date, travel between and within systems, gate networks, territories, the SVG map, the data the viewer reads |

## Python

```sh
cd python
uv sync
uv run pytest
```

A project describes itself in a `project.toml`. Paths in it are read against
the file's folder (`galaxy.project`):

```toml
catalogue = "galaxy.json"           # the systems, labels, gate links, trips, nebulae
nations = "nations.json"            # who held which system, when, in which timeline branch
travel = "travel.json"              # the travel planner's numbers
medium = "medium.json"              # the faster-than-light medium's density field
constellations = "constellations.json"
procedural = "procedural.json"      # the procedural galaxy's measured numbers
density = "density.svg"             # the image its density is read from
calendar = "calendar.json"          # eras on one axis of years (galaxy.calendar)
namer = "package.module:function"   # optional: names for the procedural galaxy
drafts = "…"                        # optional: an editor's working state
public = "…"                        # optional: where the maps' data is written
```

The CLIs take `--project`, or read `GALAXY_PROJECT`:

```sh
python -m galaxy.cli.system_maps --project my/project.toml --out public/systems.json
python -m galaxy.cli.trips       --project my/project.toml --out public/trips.json
python -m galaxy.cli.territories --project my/project.toml --out public/territories
python -m galaxy.cli.procedural  --project my/project.toml --glow public/glow.json
python -m galaxy.cli.travel Vega Sol --depart "AD 2523" --project my/project.toml
```

A calendar (`calendar.json`):

```json
{"eras": {"BC": {"zero": 0, "direction": -1}, "AD": {"zero": 0, "direction": 1}},
 "written": [{"era": "AD", "from": 1}, {"era": "BC"}],
 "epoch": "AD 2000"}
```

The axis is the Gregorian year, so the real sky's positions and the story's
dates share it. `written` says which era a year is written in. `epoch` is
the date the orbits' phases are given for.

## Viewer

The modules import `three` by name: a bundler or an import map supplies it.

```js
import 'galaxy/viewer/space/space.css'
import 'galaxy/viewer/galaxy/galaxy-map.css'
import { createGalaxyMap } from 'galaxy/viewer/galaxy/galaxy-map.js'

const map = createGalaxyMap(document.getElementById('map'), {
  title: '<strong>My galaxy</strong>',
  config: {                          // each file the build wrote; a layer without one is not drawn
    galaxy: '/data/galaxy.json',
    trips: '/data/trips.json',
    travelSettings: '/data/travel-settings.json',
    territories: '/data/territories/',
  },
  links: { system: name => `/systems/${encodeURIComponent(name)}` },
})
```

`createSystemMap(container, system, options)` draws one record of
`systems.json`. The record carries the calendar its dates are read and
written in. `createGlobeView(canvas, { map, relief, planet })` draws one
planet.

Icons are [Remix Icon](https://remixicon.com) (Apache 2.0, see
`viewer/space/icons.LICENSE`), generated into `viewer/space/icons.js` by
`npm run icons`.

## Status

What the engine still takes from the project it came from, to be made
general:

- the catalogue holds the real stars too; they become a base layer the
  engine ships, with the project's catalogue only an overlay;
- the travel modes beyond gates and the own drive, which carry that
  project's names;
- one build command writing everything the viewer reads, with a manifest;
- an example project and a demo page.

## Data and credits

- Bright stars: the HYG database (astronexus.com), CC BY-SA, in
  `python/galaxy/data/bright-stars.csv`.
- Constellation figures and boundaries: `python/galaxy/data/`.
- Real nebulae: positions and distances checked against SIMBAD (CDS,
  Strasbourg), `python/galaxy/data/real-nebulae.csv`.

No licence has been chosen for the code yet.
