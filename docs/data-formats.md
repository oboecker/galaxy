# Data formats

Every file a project supplies, and every file the build writes. The
[README](../README.md) shows the short version; this is the reference. The
examples come from [`examples/minimal/`](../examples/minimal/), a complete
small project.

The library knows no repository layout: everything is found through a
project's `project.toml`. All JSON files are UTF-8; the library writes them
as `json.dumps(indent=2, ensure_ascii=False)` plus a newline, so a rewrite
without changes leaves the file byte for byte as it was.

- [Coordinates and units](#coordinates-and-units)
- [project.toml](#projecttoml)
- [The catalogue](#the-catalogue)
- [calendar.json](#calendarjson)
- [The medium](#the-medium)
- [travel.json](#traveljson)
- [nations.json](#nationsjson)
- [constellations.json](#constellationsjson)
- [procedural.json](#proceduraljson)
- [The build's output](#the-builds-output)

## Coordinates and units

| Quantity | Unit | Notes |
|---|---|---|
| A system's or nebula's `x`, `y`, `z` | light years | Galactic centre at 0, 0, 0; Sol at (−513, 24 995, 50). +z is the north galactic pole, so x–y is the galactic plane. Limits: \|x\|, \|y\| ≤ 50 000, \|z\| ≤ 5 000. |
| A planet's orbit `au` | AU | Semi-major axis. |
| A moon's orbit `km` | km | Semi-major axis. |
| Angles (`i`, `node`, `periapsis`, `anomaly`, `tilt`, …) | degrees | |
| `radius` of a planet or moon | km | Whole number, 1–200 000. |
| Dates | `ERA YEAR[-MM[-DD]]` | Read by the project's calendar, e.g. `AD 2400`, `AD 2400-03-01`. |

The frame is anchored on Sol: real stars keep their true distance from Sol
(galaxy.celestial converts RA, Dec and distance into it).

## project.toml

Paths are read against the folder of `project.toml`. A value starting with
`@` names a file the engine ships.

```toml
catalogue = "galaxy.json"
layers = ["@real-sky", "galaxy.json"]
nations = "nations.json"
travel = "travel.json"
medium = "medium.json"
constellations = "constellations.json"
procedural = "procedural.json"
density = "@milky-way"
calendar = "calendar.json"
```

| Key | Required | Meaning |
|---|---|---|
| `catalogue` | yes | The project's own catalogue layer, the one an editor writes. |
| `layers` | no | The catalogue's layers in merge order. Default `["@real-sky", <catalogue>]`. The last entry must be the catalogue. `@real-sky` is the only built-in layer. |
| `nations` | yes | [nations.json](#nationsjson). May be absent on disk: no nations. |
| `travel` | yes | [travel.json](#traveljson). Needed by the travel planner, and by the build when the catalogue has trips. |
| `medium` | yes | [The medium](#the-medium). Needed by the travel planner. |
| `constellations` | yes | [constellations.json](#constellationsjson). May be absent on disk. |
| `procedural` | yes | [procedural.json](#proceduraljson). May be absent on disk: the build then writes no `glow.json` and no procedural galaxy. |
| `density` | yes | The image the procedural galaxy's density follows: `@milky-way` (the engine's, the Milky Way's arms), a project's own image, or an `.svg` with the image embedded as a base64 `<image>`. |
| `calendar` | yes | [calendar.json](#calendarjson). Must exist. |
| `root` | no | Paths in messages are written relative to it. Default `.`. |
| `namer` | no | `package.module:function`: names for the procedural galaxy. The function takes a `random.Random` and returns a name. Default: `galaxy.names.generate`. |
| `drafts` | no | Where an editor keeps its working state. |
| `planet_maps` | no | One folder per planet map, for an editor. |
| `public` | no | Default output folder of `galaxy.cli.system_maps` and `galaxy.cli.trips`. |
| `public_planets` | no | Planet textures and height maps for `galaxy.cli.public_maps` (see [Planet textures](#planet-textures)). |
| `svg` | no | Where an editor writes the 2D map. |
| `objects` | no | [objects.json](#objectsjson): kinds of point of interest of the project's own. |

Any other key is an error. Without `--project`, the CLIs and
`galaxy.project.current()` read the file named by the `GALAXY_PROJECT`
environment variable.

## The catalogue

### Layers

The catalogue is a list of JSON files merged in order (`galaxy.catalogue`).
The engine ships `@real-sky`: Sol with its planets and moons, the systems
of the bright stars (HYG; 287 systems in all) and the real nebulae. A project adds its own layer last.

Merging, layer by layer:

- `star_systems` and `nebulae` merge **by name**. A later layer's entry with
  a name already present overrides it field by field; its `_removed` list
  names fields it takes away. A new name is added. Systems from earlier
  layers are inserted in name order, `Unnamed …` placeholders last.
- A system is in **every layer that names it**. `{"name": "Sol"}` alone puts
  the real Sol into a story's layer, with the real sky's position, stars and
  planets; the galaxy map shows it while either layer is switched on, and
  draws it as a story's star, since not only real layers name it.
- Other lists (`labels`, `gate_links`, `trips`) are concatenated.
- Objects (`sector_names`) are merged, the later layer's keys winning.
- Anything else: the later layer wins.

`galaxy.catalogue.write(doc)` saves an edited merged document by writing
back only what the earlier layers do not already say, and the entries the
project's layer already names, if only by name. A project's layer cannot
remove a system or nebula an earlier layer holds.

The example gives Vega, a real star, a planet. It names only the system and
the planet; position, spectral class and Hipparcos number come from
`@real-sky`:

```json
{"name": "Vega", "planets": [{"name": "Vega Prime", "index": 1, "id": "p1",
  "class": "gas-giant-cold", "radius": 70000,
  "orbit": {"au": 9.5, "e": 0.02, "i": 1.0, "node": 10.0, "periapsis": 30.0, "anomaly": 45.0}}]}
```

### Top-level keys

| Key | Type | Meaning |
|---|---|---|
| `star_systems` | list | [Star systems](#star-systems). |
| `nebulae` | list | [Nebulae](#nebulae). |
| `gate_links` | list | [Gate links](#gate-links) between systems. |
| `gate_blocked` | list | `{from, to}` pairs the gate network generator never links again. |
| `trips` | list | [Trips](#trips). |
| `labels` | list | Text on the [2D SVG map](svg-map.md#labels). Not drawn by the 3D maps. |
| `sector_names` | object | Sector id → name, for the [2D SVG map](svg-map.md#sectors). |

### Star systems

```json
{"name": "Aster", "x": -93, "y": 25305, "z": 40, "coordinate_system": "galactic",
 "spectral_class": "G8V", "planets": [ … ]}
```

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Unique among systems. |
| `x`, `y`, `z` | yes | Position in light years (after merging: a project's layer may leave them to an earlier layer). |
| `coordinate_system` | no | `"galactic"` (the default) for the frame above. Only the [SVG renderer](svg-map.md#coordinates) reads it, which also takes `"graphic"` (SVG pixels). The 3D maps always read galactic coordinates. |
| `spectral_class` | no | MK class: letter `O B A F G K M`, optional subtype, luminosity class, peculiarity marks (`K3V`, `M4.5Ve`, `K3IIIb`, `G2`). Validation checks the first letter. With `stars`, derived from the primary. |
| `object_type` | no | `star` (default), `white_dwarf`, `neutron_star`, `pulsar`, `black_hole`, `wormhole`, `anomaly`, `quasar`. The four from `white_dwarf` to `black_hole` are stellar remnants with physical properties (mass, light) used by the maps; `wormhole`, `anomaly` and `quasar` only change how the SVG map draws the system. |
| `stars` | no | [Stars](#stars), for a multiple system or a named star. |
| `planets` | no | [Planets and moons](#planets-and-moons). |
| `planet_count` | derived | Number of planets, dwarf planets not counted. |
| `belts` | no | [Belts](#belts). |
| `points_of_interest` | no | [Points of interest](#points-of-interest). |
| `plane` | no | The system's reference plane in the galaxy: `{"i", "node", "zero"}` in degrees (`i` 0–180, `node` and `zero` 0–360) — its tilt to the galactic plane, the frame longitude of its ascending node, and the angle from the node to the system's longitude 0°. Real systems carry one; it orients the sky and the galactic band on the system map. |
| `procedural` | no | The id (`c123456-0`) of the procedural system this one was promoted from. That procedural system is then skipped. |

Real-sky systems have a star with a Hipparcos number (`hip`); such a system
is treated as real (small dot, named on hover, not moved by an editor).

### Stars

`stars` lists the system's stars, primary first. A single unnamed star is
dropped on normalising, since `spectral_class` says the same.

| Field | Meaning |
|---|---|
| `name` | Required for every star of a multiple system, unique within it, without `+`. |
| `spectral_class` | As for a system. |
| `hip` | Hipparcos number (real stars). |
| `orbit` | A companion's orbit around its host: the planet orbit fields, `au` required. The primary has none. |
| `host` | What the companion orbits: a star's name, or a group written as names joined with `+` (`"A+B"`, their common centre of gravity). Default: the primary. |

### Planets and moons

| Field | Planet | Moon | Meaning |
|---|---|---|---|
| `name` | ✓ | ✓ | Unique across all stars, planets, moons and nebulae of the galaxy (compared as slugs). `"?"` means unnamed. |
| `index` | required | required | Position by orbit, from 1. Derived on normalising; dwarf planets are counted apart from planets. |
| `id` | ✓ | ✓ | Stable id, `p1`, `p2`, … for planets, `m1`, … for moons; given once, never renumbered. Assigned on normalising when missing. |
| `class` | ✓ | ✓ | `terrestrial-barren`, `terrestrial-habitable`, `terrestrial-desert`, `gas-giant-cold`, `gas-giant-warm`, `ice-world`, `volcanic`, `unknown`. Sets the generated texture, atmosphere and the radius range. |
| `radius` | ✓ | ✓ | km, whole number 1–200 000. Gravity and mass are derived from radius and class. |
| `look` | ✓ | ✓ | Whole number 0–999 999: palette and seed of the generated texture. |
| `orbit` | ✓ | ✓ | See below. |
| `tilt` | ✓ | ✓ | Axial tilt against the orbit, 0–180°. |
| `tilt_bearing` | ✓ | ✓ | Which way the pole leans, 0–360° in the system's plane. |
| `rings` | ✓ | ✓ | List of bands `{"inner", "outer", "density"?}`, edges in planet radii (1–20), innermost first, each band beyond the previous one; `density` 0.01–1 (default 1). A single band object is accepted and turned into a list. |
| `dwarf` | ✓ | — | `true` for a dwarf planet; otherwise absent. |
| `host` | ✓ | — | Star or group the planet orbits (as for stars). Default: the primary. |
| `moons` | ✓ | — | List of moons. |

`orbit`: `au` (planet, 0.001–100 000) or `km` (moon, 100–10⁸) is required;
optional `e` (eccentricity 0–0.99), `i` (inclination 0–180°: a planet's
against the system's plane, a moon's against its planet's equator), `node`
(longitude of the ascending node), `periapsis` (argument of periapsis),
`anomaly` (mean anomaly at the calendar's epoch), each 0–360°. Periods are
derived, never stored.

### Belts

```json
{"name": "Main belt", "id": "b1", "inner": 2.1, "outer": 3.3}
```

`inner` < `outer`, in AU (0.001–100 000). Optional `host` as for planets;
`name` and `id` are kept as given.

### Points of interest

```json
{"name": "Gate One", "id": "g1", "kind": "jumpgate", "pair": "g2", "grade": "mature",
 "anchor": {"body": "p2", "point": "L1"}}
```

| Field | Meaning |
|---|---|
| `name` | Required. |
| `anchor` | Required. `body` is `"star"`, a planet's id, or a moon's as `"<planet id>/<moon id>"`. Around the star: `{"body": "star", "au": …}` with an optional `host`. Around a planet or moon: an orbit `km` above its surface, or a Lagrange point `"point": "L1"`…`"L5"`. |
| `kind` | The engine's `station`, `jumpgate`, `outpost`, `shipyard`, `wreck`, `beacon`, or one the project declares in [objects.json](#objectsjson); absent is a plain point. A travel mode's `from_point` refers to a kind. |
| `id` | Needed by jumpgates (their `pair` refers to it). |
| `pair` | Jumpgates only: the id of the partner jumpgate in the same system, which must point back. |
| `grade` | Jumpgates only: `early` (hop time by distance) or `mature` (flat hop time, the default). See [`jumpgates`](#traveljson). |

### Nebulae

```json
{"id": "n1", "name": "Orion Nebula", "kind": "emission",
 "x": -1150.2, "y": 26080.4, "z": -470.0, "size": [12, 12, 8], "real": "M42"}
```

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Unique, and not the name of a system, star, planet or moon. |
| `kind` | yes | `emission`, `reflection`, `dark`, `planetary`, `remnant`. |
| `x`, `y`, `z` | yes | Centre, light years. |
| `size` | yes | Three semi-axes of the ellipsoid, 0.01–5 000 ly each. |
| `tilt` | no | Three angles in degrees (x, y, z rotation), each within ±360. |
| `density` | no | Particles per cm³, 0.001–10⁷. Default by kind: emission 600, reflection 300, dark 10 000, planetary 1 000, remnant 1. |
| `colour` | no | `#rrggbb`. Default by kind. |
| `real` | no | The sky's designation (`M42`). The real nebulae of `@real-sky` are matched by it. |
| `heart` | no | Name of the system at its centre. |
| `id` | no | `n1`, `n2`, …; assigned on normalising. |

Density has effects: the faster-than-light medium is thicker inside a
nebula (factor 1 + 0.25·log₁₀(1 + density/100)); sublight speed is capped
at 1 % of light speed × √(100/density) and barred above 50 000 particles
per cm³; gates cannot stand above 5 000.

### Gate links

```json
{"from": "Sol", "to": "Aster", "grade": "provisional"}
```

`from` and `to` are two different systems; each pair at most once. `grade`
is `permanent` (default) or `provisional`. A link longer than its grade's
`range_ly` in [travel.json](#traveljson), or across a void, is not used by
the planner. `galaxy.gatenet` can generate the network from its rules:
every pair within a permanent gate's range, unless the line passes close
to a third system (within `gates.network.pass_by_share` of its length) or
through a void; pairs in `gate_blocked` are skipped.

### Trips

A trip stores what defines a journey; its route is worked out again from
the galaxy as it is.

```json
{"name": "First flight", "start": "Sol", "end": "Brannock", "depart": "AD 2400", "by": "AD 2401"}
```

| Field | Meaning |
|---|---|
| `name` | Required, unique. |
| `start`, `end` | Required. Systems; with `system`, bodies or points of interest in it (by name or reference). |
| `system` | A trip within this system. Needs `depart`. |
| `depart` | Departure date. Without it there is no arrival date. |
| `by` | Date to arrive by: the build reports in time or late, and the days to spare. |
| `way` | The way to show: between stars `own drive`, `gates` or a mode's name; within a system `sublight`, `own drive` or `jumpgates`. Default: the fastest way that is not a jump. |
| `efficiency` | The own drive's share of its speed, above 0 and at most 1. |
| `thrust` | Within a system: sublight thrust in g, 0 (coast, a Hohmann transfer at the next launch window) or 0.1 up to `sublight.g`. |
| `note` | Free text. |

### Derived fields and validation

`galaxy.schema.normalise(doc)` recomputes, in place: `spectral_class` from
`stars[0]`, `planet_count`, each body's `index` and missing `id`, nebula
ids; it drops empty `planets`, `moons`, `nebulae` and a `stars` list of one
unnamed star, and turns a single ring object into a list. An editor runs it
before saving; the build does not, so a hand-written layer carries `index`
itself (as the example does).

`galaxy.schema.validate(doc)` refuses a merged document that would break a
reader: missing or out-of-range fields as listed above, duplicate names,
unknown classes, kinds or sector ids, gate links or trips naming unknown
systems.

## objects.json

The project's own kinds of point of interest (`galaxy.objects`), beside the
engine's. Each has a label and a look: one of the shapes `octahedron`,
`torus`, `box`, `bar`, `tetrahedron`, `sphere`, `cone`, a colour `#rrggbb`,
and optionally `size`, times its usual size.

```json
{"points": {"relay": {"label": "Relay", "shape": "cone", "colour": "#5fd0a0", "size": 1.2}}}
```

A kind may not take an engine kind's name. Each record of `systems.json`
carries the looks of the project's kinds its points use (`objects`), so any
map draws them; a host can draw a kind with code of its own instead (the
system map's [`objects`](viewer.md#system-map) option). Stars, black holes,
pulsars and nebulae are the engine's own.

## calendar.json

```json
{"eras": {"BC": {"zero": 0, "direction": -1}, "AD": {"zero": 0, "direction": 1}},
 "written": [{"era": "AD", "from": 1}, {"era": "BC"}],
 "epoch": "AD 2400"}
```

All dates share one axis: the Gregorian year (year 0 is 1 BC, as
astronomers count), so the real sky's J2000 positions and a story's dates
agree.

| Field | Meaning |
|---|---|
| `eras` | Era name → `zero` (the era's year 0 on the axis, an integer) and `direction` (1 counts forward, −1 back). Months and days run forward in every era. |
| `written` | Which era a year on the axis is written in: the first entry whose `from` (a year on the axis) is reached. The last entry has no `from` and takes the rest. |
| `epoch` | The date the orbits' `anomaly` values refer to. |

Dates are written `ERA YEAR[-MM[-DD]]`. Planner inputs also accept a
fractional year (`AD 2400.5`) and a day of the year (`AD 2400, day 120`);
the maps show dates in the last form.

## The medium

The faster-than-light medium's density across the galaxy (`galaxy.medium`).
1 is average; the own drive's speed is `ly_per_day` × the local density.

```json
{"name": "subspace",
 "base": {"inner_radius_ly": 28000, "falloff_ly": 2000, "rim_floor": 0.12,
          "core_boost": 1.0, "core_radius_ly": 12000,
          "arms": {"count": 4, "pitch_deg": 12, "amplitude": 0.15, "phase_deg": 0}},
 "grid_ly": 250, "extent_ly": 46000,
 "regions": [{"kind": "void", "name": "The Hush", "circle": {"x": -1413, "y": 24195, "r": 250}}]}
```

| Field | Default | Meaning |
|---|---|---|
| `name` | `medium` | What the medium is called in messages. |
| `base.inner_radius_ly` | required | Beyond this radius the density thins … |
| `base.falloff_ly` | required | … as e^(−(r − inner)/falloff) … |
| `base.rim_floor` | 0 | … down to this floor. |
| `base.core_boost`, `base.core_radius_ly` | 0, 1 | Density × (1 + boost·e^(−(r/core_radius)²)) toward the centre. |
| `base.arms` | none | Spiral ripple: `count`, `pitch_deg`, `amplitude`, `phase_deg` (0). |
| `grid_ly`, `extent_ly` | 250, 46 000 | The route search's grid: cell size and half-width. |
| `regions` | `[]` | Regions multiplying the density inside them, applied in order. |
| `void_kinds` | `[]` | Further region kinds that act as voids. |

A region has a `kind`, an optional `name`, a shape, and optionally `factor`
and `years`:

| Kind | Effect |
|---|---|
| `void` (and any kind in `void_kinds`) | Density 0: no faster-than-light travel, no gates, no jumps into or out of it. |
| `corridor` | × `factor` (use > 1). |
| `thin` | × `factor` (use < 1). |

`factor` defaults to 1. Shapes, one per region:

| Shape | Fields |
|---|---|
| Circle | `"circle": {"x", "y", "r"}` |
| Ellipse | `"ellipse": {"x", "y", "rx", "ry", "angle"?}` (degrees) |
| Corridor | `"path": [[x, y], …]`, `"width"` |
| Around a system | `"system": "<name>"`, `"r"` |
| Around a planet | `"around": "<planet>"`, `"seals": ["<planet>", …]`, `"reach"` (default 0.2): radius = reach × distance to the nearest seal. Follows the planets' systems. |

`years: [from, to]` (numbers on the calendar's axis) makes a region hold
only for trips dated within it. Coordinates are galactic x, y in light
years; height is ignored. Each nebula adds a region of kind `nebula` in
memory (its footprint, factor from its density); it is not written to the
file.

## travel.json

How fast each way of travel is (`galaxy.travel`, `galaxy.insystem`) and how
the maps draw it. A planner call can override any value (`--set
key.path=value` on `galaxy.cli.travel`).

```json
{"own_drive": {"ly_per_day": 308, "min_density": 0.1, "in_system_efficiency": 1},
 "gates": {"permanent": {"ly_per_day": 925, "range_ly": 1200},
           "provisional": {"ly_per_day": 462, "range_ly": 600},
           "stop_hours": 6, "network": {"pass_by_share": 0.25}},
 "modes": {"Slingshot": {"kind": "straight", "ly_per_day": 1400, "from_point": "beacon"},
           "Warp": {"kind": "jump", "minutes": 10, "label": "Warp jump"}},
 "jumpgates": {"early": {"au_per_hour": 0.5}, "mature": {"minutes": 10}},
 "sublight": {"g": 3, "star_clearance_au": 0.1, "planet_clearance_hill": 1},
 "maps": { … }}
```

Between stars every trip compares the own drive, the gates (where links
exist), and the project's modes:

| Key | Meaning |
|---|---|
| `own_drive.ly_per_day` | Speed at density 1, through the medium, steering around thin regions and voids. |
| `own_drive.min_density` | Below this density the own drive cannot fly. |
| `own_drive.in_system_efficiency` | Within a system: share of the between-stars speed (× the density where the system lies). |
| `gates.<grade>.ly_per_day`, `.range_ly` | Per grade (`permanent`, `provisional`): hop speed and the longest usable link. |
| `gates.stop_hours` | Stop at each system passed through. Gate routes fly the own drive to the first gate and from the last. |
| `gates.network.pass_by_share` | Rule of the gate network generator (see [Gate links](#gate-links)). |
| `modes.<name>` | A project's own way of travel, offered under its name. |

A mode has a `kind`:

- `straight`: flies straight at `ly_per_day`, blocked by a void in between.
  With `from_point`, offered only from a system that has a point of
  interest of that kind.
- `jump`: takes `minutes` anywhere outside a void at either end; a
  shortcut, not a flight.

Optional on both: `label` (shown on the maps, default the name) and `leg`
(the leg kind the maps colour by, default the name in lower case).

Within a system a trip compares sublight, the own drive and jumpgates:

| Key | Meaning |
|---|---|
| `sublight.g` | Constant thrust, turning over halfway; 0 coasts. Also the upper limit of a trip's `thrust`. |
| `sublight.star_clearance_au` | Closest approach to a star; a leg that comes closer bends around it. |
| `sublight.planet_clearance_hill` | Closest approach to a planet, in its Hill radii. |
| `jumpgates.early.au_per_hour` | Hop time of an `early` jumpgate, by distance. |
| `jumpgates.mature.minutes` | Hop time of a `mature` jumpgate, flat. |

`maps` is for the viewer only and reaches it through
`travel-settings.json`. Give every key; the maps read them without
defaults:

| Key | Meaning |
|---|---|
| `route_colours` | Leg kind → colour: `own drive`, `gate`, `jumpgate`, `sublight`, and each mode's leg kind. Unknown kinds draw white. |
| `route_opacity` | Leg kind → opacity of its route line on the galaxy map; a kind not listed is opaque. The object must be present, even if empty. |
| `stream` | The glow streaming along a route: `samples`, `pulse_share`, `step_per_frame`, `line_opacity`. |
| `stop_pixels` | Size of a stop's point. |
| `drive_share_min` | Lowest value of the own-drive slider: `galaxy`, `system`. |
| `gate_overlay` | `colour` and `opacity` by grade (`permanent`, `provisional` on the galaxy map; `early`, `mature` for jumpgates on the system map). |

Only numbers and colours of `maps` are passed on; any other text is
dropped.

## nations.json

Who held which system, when, and in which timeline branch
(`galaxy.nations`, `galaxy.territories`).

```json
{"nations": {
  "league": {"name": "The League",
             "holdings": ["Sol",
                          {"system": "Aster", "from": "AD 2350"},
                          {"system": "Brannock", "from": "AD 2420", "to": "AD 2500"}]}}}
```

| Field | Meaning |
|---|---|
| `nations.<id>.name` | Display name. |
| `nations.<id>.claim_radius` | Light years each held system claims around it. Default 1000. |
| `nations.<id>.color` | `#rrggbb`. Default: a hue from the nation's position in the file, so keep the order append-only. |
| `nations.<id>.holdings` | A system name (held throughout), or `{system, from?, to?, world?}`. `from` absent: since before any record. `to` absent: still held; `to` is exclusive. `world`: the timeline branch the holding belongs to, any short string (`+`, say); absent holds in every branch. |

A territory is a volume: every held system claims a sphere of the claim
radius, and where claims meet a point belongs to the nearest held system.
History is split at every date a holding starts or ends; each interval of
each branch is one snapshot. A holding naming an unknown system is skipped
with a warning.

## constellations.json

Constellation figures in the skies of the system maps, by the system they
are seen from. Keys starting with `_` are notes.

```json
{"Sol": [{"name": "Orion", "lines": [["Betelgeuse", "Bellatrix"], ["Rigel", "Saiph"]]}]}
```

Each line is a chain of stars, named by system, star or Bayer designation
(`Alpha Orionis`). A star the galaxy does not have is skipped and its
neighbours are joined. The engine ships no figures: without the file, the
skies have no lines.

## procedural.json

The numbers the procedural galaxy follows (`galaxy.procedural`), measured
off the catalogue's own systems by `python -m galaxy.cli.procedural
--measure` and kept, so that procedural systems stay where they are when the
catalogue changes. Measuring again moves every procedural system.

| Field | Meaning |
|---|---|
| `seed` | Seed of every draw. |
| `sol` | Sol's `[x, y]`: the density is scaled to match the catalogue's around it. |
| `density` | The catalogue's systems per ly² of the plane within 2 000 ly of Sol. |
| `heights` | The `z` of those systems: procedural heights are drawn from them. |
| `classes` | Spectral classes drawn from. |
| `companion_share` | Share of systems with a companion star. |
| `planet_counts` | Planet counts drawn from. |

Positions follow the `density` image (the arms), thicker toward the bulge,
fraying at the rim beyond 40 000 ly. Each density cell draws its systems
from its own seed and each system its details from its id
(`c<cell>-<n>`), so the layer is deterministic. An authored system removes
the procedural one nearest to it; a promoted system (field `procedural`)
replaces its own. Names come from the project's `namer`.

## The build's output

```sh
python -m galaxy.cli.build --project my/project.toml --out public/galaxy [--procedural [--within LY]]
```

`galaxy.build.write` writes into one folder, `manifest.json` last:

| File | Content |
|---|---|
| `galaxy.json` | The merged catalogue. |
| `layers/<name>.json` | Each layer as its file holds it (`real-sky`, then the project's layers by file stem). |
| `systems.json` | Every system as the system map draws it, by name (`galaxy.systemmap`). |
| `nebulae.json` | The nebulae as the skies draw them: `[{name, kind, colour, at: [x, y, z], size}]`. |
| `glow.json` | The galaxy's light for the band in the skies (only with `procedural.json`). |
| `trips.json` | The stored trips with their routes: `{"galaxy": [...], "systems": {"<system>": [...]}}`. |
| `travel-settings.json` | `{"maps": {...}, "modes": {"<name>": {kind, label, leg, from_point?}}, "sublight": {"g": …}}`: travel.json's `maps`, the modes without their numbers, and the sublight drive's top thrust (the system map's thrust slider ends there). |
| `territories/` | Only with nations: `index.json` and snapshot files `s0.json`, … |
| `procedural.json`, `procedural-gates.json`, `procedural/` | Only with `--procedural` (takes minutes; `--within` limits it to a radius around Sol). |

### manifest.json

File names are relative to the manifest. `null` means the file was not
written. [`viewer/space/manifest.js`](viewer.md#the-manifest) turns them into
URLs.

```json
{"galaxy": {"layers": [{"id": "real-sky", "label": "the real sky's stars", "url": "layers/real-sky.json", "real": true, "icon": "star"},
                       {"id": "galaxy", "label": "galaxy", "url": "layers/galaxy.json", "icon": "planet"}],
            "trips": "trips.json", "travelSettings": "travel-settings.json",
            "territories": "territories/", "procedural": "procedural.json",
            "proceduralGates": "procedural-gates.json"},
 "system": {"systems": "systems.json", "nebulae": "nebulae.json", "glow": "glow.json",
            "travelSettings": "travel-settings.json", "trips": "trips.json",
            "procedural": "procedural.json"},
 "calendar": {"eras": {...}, "written": [...], "epoch": "AD 2400"}}
```

`galaxy` is the galaxy map's `config`; `system` names the files a host
passes to the system map; `calendar` is calendar.json.

### systems.json

One record per system, keyed by name. Besides the catalogue's fields it
carries what the browser should not compute:

| Field | Meaning |
|---|---|
| `epoch`, `epoch_year`, `calendar` | The calendar's epoch and definition; the map reads and writes dates with it. |
| `star` | The primary: `spectral_class`, `object_type`, `mass` and `luminosity` (suns), `temperature` (K), `radius` (km), `habitable_zone` [inner, outer] and `frost_line` (AU). |
| `stars`, `tree`, `primary_name`, `hosts` | Every star, the star hierarchy with companion orbits and periods, and each host's mass and zones. |
| `planets` | Each with `host`, `period` (years), `hill` (km), `mass_ratio`, `gravity` (g), rings as bands, and `moons` likewise. |
| `belts`, `points_of_interest` | As in the catalogue, hosts resolved; a point orbiting a body gets its `orbit` and `period`. |
| `at`, `axes`, `abs_mag`, `galaxy`, `sky` | Position, the system's axes in the frame, absolute magnitude, the galactic pole and centre in the system's axes, and where it stands in Earth's sky. |
| `constellations` | Figures seen from it, where constellations.json has them. |

### territories/

`index.json` lists every interval of every branch; snapshots with the same
holdings share a file:

```json
{"snapshots": [{"world": null, "from": null, "to": "AD 2350", "file": "s0.json"},
               {"world": null, "from": "AD 2350", "to": "AD 2420", "file": "s1.json"}]}
```

A snapshot is `{"territories": [...]}`, one entry per nation: `nation`,
`name`, `color`, `hatch` (degrees), `members` (system names), `vertices`
and `faces` (the volume's surface in galactic coordinates), `footprint`
(its projection on the plane: polygons → rings → `[x, y]`) and `label`
(`[x, y]`).

### The procedural galaxy

| File | Content |
|---|---|
| `procedural.json` | `{"systems": [{id, name, x, y, z, spectral_class or object_type, planet_count, abs_mag}], "nebulae": [...]}` |
| `procedural-gates.json` | `{"links": [{from, to, grade?}]}`: the gate network over procedural and catalogue systems. |
| `procedural/<block>.json` | Full system-map records by id, grouped in blocks of 10 × 10 density cells; the block of id `c<cell>-<n>` is `<row:02><col:02>` with row = cell ÷ 700 ÷ 10 and col = (cell mod 700) ÷ 10. `viewer/space/procedural.js` computes it. |

### Other writers

- `python -m galaxy.cli.galaxy_generate` and `galaxy.cli.territories --svg`
  write the [2D SVG map](svg-map.md).
- `python -m galaxy.cli.public_maps --out DIR` writes a public subset:
  only allowed fields of the catalogue (no trips, no territories), the
  engine's layers, `systems.json`, `nebulae.json`, `glow.json`,
  `travel-settings.json`, the procedural galaxy (unless
  `--no-procedural`), and the planet textures.

### Planet textures

Optional. A planet without a texture gets one generated from its `class`
and `look`. Textures and height maps are listed in two manifests mapping
planet or moon name to URL: `index.json` (textures) and `heights.json`
(height maps). `galaxy.cli.public_maps` reads them from the project's
`public_planets` folder (height maps under `height/`) and copies those of
planets in the catalogue. The viewer takes the same mappings (see
[viewer.md](viewer.md#galaxy-map)).
