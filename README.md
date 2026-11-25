# galaxy

A fictional galaxy to tell stories in: three linked 3D maps (the galaxy, a
star system with its orbits over time, a planet's globe) and the Python
library that builds and checks what they draw. The real sky is there from the
start: Sol and its planets, the bright stars, the constellations and the real
nebulae. A procedural galaxy fills the Milky Way's arms with systems nobody
has named yet. A story adds its own systems, gate networks, a
faster-than-light medium, nations holding systems through time, trips with
dates, and its own calendar.

Early days: the data formats will still change (see *Status*).

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
catalogue = "galaxy.json"           # the story's own systems, labels, gate links, trips, nebulae
layers = ["@real-sky", "galaxy.json"]   # optional, the default: the catalogue's layers in order
nations = "nations.json"            # who held which system, when, in which timeline branch
travel = "travel.json"              # the travel planner's numbers
medium = "medium.json"              # the faster-than-light medium's density field
constellations = "constellations.json"
procedural = "procedural.json"      # the procedural galaxy's measured numbers
density = "@milky-way"              # the image its density is read from: the engine's, or your own
calendar = "calendar.json"          # eras on one axis of years (galaxy.calendar)
namer = "package.module:function"   # optional: names for the procedural galaxy
drafts = "…"                        # optional: an editor's working state
public = "…"                        # optional: where the maps' data is written
```

The catalogue is a list of layers (`galaxy.catalogue`), merged in order by
name: the engine ships `@real-sky` (Sol and its bodies, the bright stars, the
real nebulae), and a story adds its own file, which may also extend a real
star (planets for Vega, say). An editor works on the merged catalogue and
writes only the story's layer back. A map is extended by adding a layer,
never by rewriting one.

Travel between stars always has the faster-than-light own drive (through the
medium) and, where gate links exist, the gates; within a system, sublight and
jumpgates. A story adds its own ways in `travel.json`:

```json
"modes": {
  "Slingshot": {"kind": "straight", "ly_per_day": 1400, "from_point": "slingshot"},
  "Warp": {"kind": "jump", "minutes": 10, "label": "Warp jump"}
}
```

A `straight` mode flies straight at its speed, blocked by a void in between,
and with `from_point` starts only where a point of interest of that kind is.
A `jump` mode takes its minutes anywhere outside a void: a shortcut, not a
flight.

One command writes everything the maps read into one folder, with a
`manifest.json` naming each file:

```sh
python -m galaxy.cli.build --project my/project.toml --out public/galaxy [--procedural]
```

The CLIs for single files take `--project` too, or read `GALAXY_PROJECT`:

```sh
python -m galaxy.cli.catalogue   --project my/project.toml --out public/galaxy.json --layers public/layers
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

## Example and demo

`examples/minimal/` is a small story: three systems near Sol, a planet for
Vega, gate links, one nation over two dates, a trip, and two ways of travel
of its own. `make demo` builds it and serves the maps at
http://localhost:8040/demo/.

## Viewer

The modules import `three` by name: a bundler or an import map supplies it.
A build's manifest gives the maps their files:

```js
import { loadManifest } from 'galaxy/viewer/space/manifest.js'
const { galaxy, system } = await loadManifest('/data/manifest.json')
createGalaxyMap(root, { config: galaxy })
```

Or name the files yourself:

```js
import 'galaxy/viewer/space/space.css'
import 'galaxy/viewer/galaxy/galaxy-map.css'
import { createGalaxyMap } from 'galaxy/viewer/galaxy/galaxy-map.js'

const map = createGalaxyMap(document.getElementById('map'), {
  title: '<strong>My galaxy</strong>',
  config: {                          // each file the build wrote; a layer without one is not drawn
    layers: [                        // the catalogue's layers, a switch each on the map
      { id: 'real-sky', label: "the real sky's stars", url: '/data/layers/real-sky.json', real: true, icon: 'star' },
      { id: 'story', label: "the story's systems", url: '/data/layers/galaxy.json', icon: 'planet' },
    ],
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

## Documentation

- [docs/data-formats.md](docs/data-formats.md): every file a project
  supplies and every file the build writes, field by field.
- [docs/viewer.md](docs/viewer.md): the three maps' options, supplying
  three.js, the shared modules, browser state.
- [docs/svg-map.md](docs/svg-map.md): the 2D SVG map and its coordinate
  conversion.

## Status

Planned next:

- custom 3D objects beside the built-in nebulae, black holes and pulsars.

## Data and credits

- Bright stars: the HYG database (astronexus.com), CC BY-SA, in
  `python/galaxy/data/bright-stars.csv`, and placed from it in the real-sky
  layer, `python/galaxy/data/real-sky.json` (CC BY-SA as well).
- Constellation names and boundaries: `python/galaxy/data/` (a project may add
  figures in its `constellations.json`).
- Real nebulae: positions and sizes from OpenNGC (CC BY-SA 4.0) where it has
  them, else SIMBAD (CDS, Strasbourg) or the literature; distances from the
  literature, checked against SIMBAD: `python/galaxy/data/real-nebulae.csv`.
- The Milky Way's arms, which the procedural galaxy's density follows:
  NASA/JPL-Caltech/R. Hurt (SSC-Caltech), `python/galaxy/data/milky-way.jpg`.

The code is under the MIT licence (`LICENSE`); the data keeps the licences
named above.
