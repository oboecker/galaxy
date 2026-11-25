# The 2D SVG map

A flat map of the galaxy as one SVG file (`galaxy/renderer.py`): the
galactic plane seen from above, with a sector grid, the systems coloured by
spectral class, nebulae, labels and, optionally, nation territories. The
file opens in a browser (hover effects, a coordinate readout) and in
Inkscape (each part is an Inkscape layer with a label and an id). Output is
deterministic: the same input gives the same bytes.

- [Running it](#running-it)
- [Coordinates](#coordinates)
- [Layers](#layers)
- [Grid](#grid)
- [Sectors](#sectors)
- [Systems](#systems)
- [Nebulae](#nebulae)
- [Labels](#labels)
- [Territories](#territories)
- [In the browser](#in-the-browser)

## Running it

The renderer reads one JSON file, not a project. For a project, merge its
layers first:

```sh
python -m galaxy.cli.catalogue --project my/project.toml --out build/galaxy.json
python -m galaxy.cli.galaxy_generate -i build/galaxy.json -o build/galaxy.svg [--interactive]
```

| Option | Default | Meaning |
|---|---|---|
| `-i`, `--input` | required | The catalogue (`star_systems`, `nebulae`, `labels`, `sector_names`). |
| `-o`, `--output` | required | The SVG file, written atomically. |
| `-w`, `--width`, `--height` | 5600 | Canvas size in pixels. |
| `--interactive` | off | Embed zoom and pan (see [In the browser](#in-the-browser)). |

With territories at one moment:

```sh
python -m galaxy.cli.territories --project my/project.toml --svg build/galaxy.svg --at "AD 2450" [--world +] [--interactive]
```

`--world` picks a timeline branch; without it only holdings valid in every
branch count. This command always renders at 5600 × 5600.

From Python: `GalaxyMapGenerator(width=6000, height=6000,
interactive=False).generate(data, output_path, territories=None)`. Note the
class's default size differs from the CLI's.

The input format is the catalogue's ([data-formats.md](data-formats.md#the-catalogue));
the renderer also accepts the older keys `galaxy_labels` (for `labels`) and
`celestial_objects` (for `star_systems`).

## Coordinates

Each system's `coordinate_system` says how its `x` and `y` are read:

- `"galactic"`: light years in the catalogue's frame (galactic centre at 0,
  0; Sol at −513, 24 995). Converted with `galaxy/coords.py`. `z` is
  ignored.
- `"graphic"` **or absent**: SVG pixels, used as they are.

Write `"coordinate_system": "galactic"` on every catalogue system; the real
sky's systems and those promoted from the procedural galaxy carry it.

`CoordinateConverter(center_x, center_y)` maps galactic to graphic
linearly, anchored on two points: the galactic centre at the canvas centre,
and Sol at (2778, 1745) on a 5600-pixel canvas, scaled with the canvas:

```
graphic_x = cx + x · 0.042885 · cx / 2800
graphic_y = cy − y · 0.042208 · cy / 2800
```

(`cx`, `cy` the canvas centre.) Galactic +y points up the image. The two
scales differ by about 1.6 % because both come from Sol's position; at
5600 pixels one pixel is about 23.3 ly across and 23.7 ly down.
`graphic_to_galactic` is the inverse. Nebula outlines and territory
footprints are always galactic and converted the same way.

## Layers

Top-level groups, in document order (later ones on top):

| Id | Content |
|---|---|
| (`<style>`, `<script>`) | Hover styles and the browser script. |
| `background` | A rectangle over the canvas, `#262626`. |
| `labels` | [Labels](#labels). |
| `grid` | Centre circle, rings, beams and their labels. |
| `legend` | Top right: a dot, the letter and the temperature range for each class O–M, and *Unclassified*. |
| `mouse_coordinates` | The coordinate readout, hidden until the pointer moves. |
| `territories` | Only when territories are given. |
| `nebulae` | Only when the input has nebulae. |
| `sectors` | 361 sector layers, each holding its shape, its labels and its systems. |
| `star_hover_areas` | Invisible hit circles over the systems. |

Text uses the font family `Lithos Pro Regular`, which the viewer must have
installed; otherwise the browser's fallback is used.

## Grid

All grid measures are in pixels and do not scale with the canvas:

- Centre circle: radius 150.
- 15 rings, each 150 wide, numbered 1 (innermost) to 15 just right of the
  vertical line above the centre.
- 24 beams 15° apart, from the centre circle's edge to 150 beyond the
  outermost ring (radius 2 550), lettered A–X counter-clockwise from the
  top; each letter sits inside the centre circle, halfway between its beam
  and the next.

Strokes are black, 2 wide. 24 × 15 sectors plus the centre make 361
sectors, `0` and `A1` … `X15`.

Because the grid is fixed in pixels while the galactic scale follows the
canvas, sectors match the 3D galaxy map's grid (rings 3 554 ly wide) only
at 5600 × 5600. `galaxy/sectors.py` (`SectorAssigner`) gives the sector of
a graphic point; a point beyond ring 15 has none.

## Sectors

Each sector is an Inkscape layer labelled with its id, `id="sector_<id>"`,
holding:

- its shape (`sector_shape_<id>`): a wedge, or the centre circle for `0`,
  transparent, below the systems;
- a hover label with its id (`sector_hover_label_<id>`), 18 px, red,
  shown on hover;
- with a name in `sector_names`, the name (`sector_name_<id>`), 8 px, red,
  always visible (hidden while hovered), and a red outline on the wedge.
  The centre sector shows its name but gets no outline.

`sector_names` maps sector ids to names; validation refuses an id that does
not exist:

```json
"sector_names": {"0": "The Core", "A7": "The Near Reach"}
```

## Systems

Each system is drawn in its sector's layer as a group `object_<id>` (id:
the name in lower case, spaces and hyphens as underscores) with classes
`celestial-object <object_type>` and `data-object-type`,
`data-spectral-class` attributes. A system outside ring 15 is skipped
with a warning on stderr.

Stars (`object_type` absent or `star`) are drawn by the first letter of
`spectral_class` (`galaxy/config.py`):

| Class | Colour | Radius | Glow | Temperature |
|---|---|---|---|---|
| O | `#9bb0ff` | 1.25 | yes | 30,000+ K |
| B | `#aabfff` | 1.0 | yes | 10,000–30,000 K |
| A | `#cad7ff` | 0.9 | yes | 7,500–10,000 K |
| F | `#f8f7ff` | 0.75 | no | 6,000–7,500 K |
| G | `#fff4ea` | 0.6 | no | 5,200–6,000 K |
| K | `#ffd2a1` | 0.5 | no | 3,700–5,200 K |
| M | `#ffcc6f` | 0.4 | no | < 3,700 K |
| other letter | `#ffffff` | 0.5 | no | (Unclassified) |

A star without `spectral_class` gets a letter derived from an MD5 hash of
its name, so it is stable between runs.

Other object types:

| `object_type` | Colour | Radius | Glow | Type label |
|---|---|---|---|---|
| `black_hole` | black core, `#ff4500` disc | 2.0 | — | [Black Hole] |
| `neutron_star` | `#00ffff` | 1.5 | yes | [Neutron Star] |
| `pulsar` | `#00ff00` | 1.5 | yes | [Pulsar] |
| `white_dwarf` | `#e0e0ff` | 1.0 | no | [White Dwarf] |
| `wormhole` | `#9400d3` | 4.0 | no | [Wormhole] |
| `anomaly` | `#ff00ff` | 2.5 | no | [Spatial Anomaly] |
| `quasar` | `#ffff00` | 3.5 | yes | [Quasar] |
| any other | `#808080` | 2.0 | no | [Unknown Object] |

A dot is a circle of that radius in pixels; a glow adds a circle of twice
the radius at 30 % opacity, blurred. A black hole is drawn as three blurred
rings of its disc colour (2.5×, 1.5× and 1.2× the radius) around a black
core.

A real star (one of its `stars` has a Hipparcos number `hip`) is drawn at
0.35 × the size, without glow, with class `real-star`; its name shows only
on hover.

Each system's name is drawn to the right of its dot in its colour (a black
hole's in its disc colour). Its size follows the distance to the nearest
other system: 8 px at 60 px or more, 2.5 px at 15 px or less, linear in
between; opacity falls from 1 at 30 px to 0.6 at 10 px. Non-star types get
a smaller type label, `[Pulsar]` and so on, below the name (1.8–5 px).

## Nebulae

Each nebula is an ellipse in the plane: centre and the first two semi-axes
of `size` converted to pixels (at least 4 px each), rotated by the third
`tilt` angle, filled in its `colour` or its kind's, blurred, at 45 %
opacity (a dark nebula 75 %). Its name is written below in 3.5 px. Group id
`nebula_<nebula id>`.

## Labels

`labels` puts free text on the map:

```json
"labels": [{"label": "The Outer Arm", "x": 3200, "y": 900, "rotation": -30}]
```

`x`, `y` are SVG pixels (no coordinate conversion), the text's start.
`rotation` (degrees, optional) is applied as `transform="rotate(r)"`,
which turns about the SVG origin (0, 0), not about the label, so a
rotated label moves. 56 px, `#4d4d4d`; id `label_<text in lower case,
spaces as underscores>`.

## Territories

Given territories (the Python argument, or `galaxy.cli.territories --svg`),
each nation's footprint on the plane is drawn as one path: a 10 % fill in
its colour, a hatch at its own angle (`hatch_<nation>` pattern, 55 %
opacity lines), and an outline. Nations stacked in height overlap here, so
each keeps its full outline. Its name, in capitals, sits at its label
point. Group id `territory_<nation>`.

## In the browser

Always included:

- A readout next to the pointer: graphic coordinates, galactic
  coordinates and the sector.
- Hovering a sector fills it light blue and shows its id.
- Hovering a system brightens and outlines its dot, shows its name bold at
  20 px (a real star's at 8 px) and enlarges the type label. The hit area
  is a circle of at least 4 px, 3 × the dot's radius.

With `--interactive`:

| Input | Action |
|---|---|
| Wheel | Zoom 0.5×–5× in steps of 0.1, toward the pointer. |
| Left or middle drag | Pan. |
| `+` / `=`, `-` / `_` | Zoom in, out. |
| Arrow keys | Pan by a tenth of the view. |
| `0`, right click | Reset. |

Panning is limited to the canvas.
