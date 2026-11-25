# The viewer

Three maps on [three.js](https://threejs.org), as ES modules under
[`viewer/`](../viewer/): the galaxy map, a star system's map, a planet's
globe. The [README](../README.md#viewer) shows a minimal page; this is the
reference. The files they read are described in
[data-formats.md](data-formats.md#the-builds-output).

- [Supplying three.js](#supplying-threejs)
- [Styles](#styles)
- [The manifest](#the-manifest)
- [Galaxy map](#galaxy-map)
- [System map](#system-map)
- [Globe view](#globe-view)
- [Shared modules](#shared-modules)
- [Browser state and events](#browser-state-and-events)

## Supplying three.js

The modules import `three` and `three/addons/…` by name; the host supplies
them (`three` is a peer dependency, `^0.182.0`).

With an import map, as [`demo/index.html`](../demo/index.html) does:

```html
<script type="importmap">
{"imports": {"three": "/node_modules/three/build/three.module.js",
             "three/addons/": "/node_modules/three/examples/jsm/"}}
</script>
```

With a bundler, install `three` in the host and import the modules by path
(`galaxy/viewer/…` when the package is a dependency). If the package is
linked rather than copied (`npm link`, a `file:` dependency), the bundler
resolves `three` from the package's real location and may load a second
copy; with Vite set `resolve.preserveSymlinks: true` (or
`resolve.dedupe: ['three']`) so that there is one.

The planet textures are generated in a worker,
`new Worker(new URL('./texture-worker.js', import.meta.url), { type: 'module' })`;
a bundler that understands this pattern (Vite, webpack 5) bundles it. Where
workers are unavailable, textures are made on the page.

## Styles

| Map | Stylesheets |
|---|---|
| Galaxy | `viewer/space/space.css`, `viewer/galaxy/galaxy-map.css` |
| System | `viewer/space/space.css`, `viewer/system/system-map.css` |

Each map fills its container, which needs a size. The galaxy map's markup
uses fixed element ids, so a page holds one galaxy map at a time.

## The manifest

`viewer/space/manifest.js` reads a build's `manifest.json` and resolves its
file names against the manifest's URL:

```js
import { loadManifest } from './viewer/space/manifest.js'
const { galaxy, system, calendar } = await loadManifest('/data/manifest.json')
```

`galaxy` is ready as the galaxy map's `config`; `system` holds the URLs a
host passes to the system map (`systems`, `nebulae`, `glow`,
`travelSettings`); `calendar` is the project's calendar definition.

## Galaxy map

```js
import { createGalaxyMap } from './viewer/galaxy/galaxy-map.js'
const map = createGalaxyMap(root, { title, config, links, focus, uncharted })
```

| Option | Meaning |
|---|---|
| `config` | The data's URLs and a few settings (below). |
| `title` | HTML for the info box. |
| `links.system` | `(name, { procedural: id }?) => URL or null`: where a star's system map is. The second argument is given for a procedural system. Without it, stars do not link. |
| `focus` | A star's name, selected and flown to once loaded. |
| `uncharted` | A procedural system's id: the procedural layer is shown and the system selected. |

`config`, every key optional; a file not given is not drawn:

| Key | Meaning |
|---|---|
| `layers` | The catalogue's layers, `[{ id, url, label?, icon?, real?, shown?, toggle?, key? }]`, merged in order by system name as the library merges them. Each gets a show/hide button when there is more than one (`toggle: false` for none). `real` draws its stars as the real sky's: small, no glow, no stem to the plane, named on hover. `shown: false` hides it at first. `icon` is an icon name (default `star`). `key` overrides the localStorage key. |
| `galaxy` | One catalogue file instead of `layers`. A star with a Hipparcos number is drawn as real. |
| `textures`, `heights` | URLs of JSON maps of planet name → texture URL and → height-map URL. |
| `textureBase` | Prefix for the URLs in those maps. Default `''`. |
| `territories` | Folder URL with a trailing slash, holding `index.json` and the snapshot files. Adds the territory button, a branch selector and a time slider. |
| `trips` | `trips.json`: stored trips, listed and drawn read-only. |
| `travelSettings` | `travel-settings.json`. Without it no route, gate overlay or trip is drawn. |
| `procedural`, `proceduralGates` | The procedural galaxy's files. Adds a button; the files are fetched when first shown, and its gate network replaces the stored one while shown. |
| `departPlaceholder` | Placeholder of the planner's date field. Default `'a date — optional'`. |
| `travel` | URL of a planner endpoint (below). Adds the travel panel. |
| `tripSave` | URL to keep and remove trips (below). |
| `onChange` | Called after a trip was kept or removed. |

The map also draws the galactic centre as a black hole, a sector grid
(cylindrical: 15 rings of 3 554 ly and 24 beams, as the
[SVG map](svg-map.md#grid)) switchable to a Cartesian one, stems from each
star to the galactic plane, nebulae, and planets around a selected star.

It returns:

| Member | Meaning |
|---|---|
| `reload()` | Fetch the data again; the selection, camera and territories stay. |
| `locate(name)` | Select a star by name and fly to it; `false` if there is none. |
| `destroy()` | Stop drawing, release the WebGL context and listeners, empty `root`. |

### Planner endpoints

The library has no server; a host that wants planning in the browser
answers these with `galaxy.travel` and `galaxy.trips`:

| Endpoint | Request | Response |
|---|---|---|
| `config.travel` | `GET ?start=&end=&depart=[&efficiency=]` | `{start, end, options: [travel.as_json(option, travel.systems(doc))]}`, or `{error}` with a non-2xx status. |
| `config.tripSave` | `POST` form: `name, start, end, depart, way, by[, efficiency]` | The stored trip (`{name, …}`) or `{error}`. |
| | `DELETE {tripSave}/{name}` | 2xx on success. |

## System map

```js
import { createSystemMap } from './viewer/system/system-map.js'
const systems = await (await fetch(system.systems)).json()
const map = createSystemMap(container, systems['Sol'], {
  sky: Object.values(systems), nebulae, glow: system.glow, travelSettings: system.travelSettings,
  links: { galaxy: name => `/galaxy?focus=${encodeURIComponent(name)}` },
})
```

The second argument is one record of `systems.json` (or of a procedural
block, see `space/procedural.js`); its `constellations`, if any, are drawn
in the sky. Options, all optional:

| Option | Meaning |
|---|---|
| `links.galaxy` | `name => URL`: a back link to the galaxy map. |
| `links.planet` | `(body, planet) => URL or null`: a link to a body's globe; `planet` is the moon's planet, or null for a planet. |
| `focus` | A body's name, flown to on opening. |
| `absolute` | The date to open at, in years on the calendar's axis. Default: the epoch. |
| `sky` | Stars of the sky: records with `name`, `spectral_class` (or `star.spectral_class`), `at` and `abs_mag` — the values of `systems.json` serve. |
| `nebulae` | The contents of `nebulae.json`. |
| `glow` | URL of `glow.json`: the galactic band as seen from this system. |
| `procedural` | URL of the procedural galaxy's `procedural.json`: adds a button for its stars in the sky. |
| `uncharted` | Truthy for a procedural system: its procedural sky is shown. |
| `textures`, `heights` | Objects of body name → texture URL and → height-map URL. |
| `travelSettings` | `travel-settings.json`. Without it no trip and no jumpgate overlay is drawn. |
| `trips` | `trips.json`: the stored trips within this system, listed and played. |
| `trip` | URL of an in-system planner endpoint (below). Adds the trip panel. |
| `tripSave` | URL to keep and remove trips. |
| `onChange` | Called after a trip was kept or removed. |

Orbits are true to each other in AU; planets and their moons' orbits are
enlarged by one common factor so that each stays clear of its neighbours,
and a body is never drawn smaller than 3 pixels.

It returns:

| Member | Meaning |
|---|---|
| `destroy()` | Stop drawing and release everything. |
| `setDate(absolute)` | Move to a date (years on the axis). |
| `snapshot()` | The view's state: date, speed, camera, selection, overlays, trip panel. |
| `restore(saved)` | Restore a `snapshot()` when the same system is opened again. |

### In-system endpoints

| Endpoint | Request | Response |
|---|---|---|
| `trip` | `GET ?start=&end=&date=[&efficiency=][&thrust=]`; `start`, `end` are body or point references, `date` an era and decimal year | `{options: [insystem.as_json(option, insystem.Places(system))]}` or `{error}`. |
| `tripSave` | `POST` form: `name, by, system, way, start, end, depart[, efficiency][, thrust]` | The stored trip or `{error}`. |
| | `DELETE {tripSave}/{name}` | 2xx on success. |

## Globe view

```js
import { createGlobeView } from './viewer/planet/globe-view.js'
const view = await createGlobeView(canvas, { map, relief, planet, system, stars, constellations, glow, onDraw })
```

| Option | Meaning |
|---|---|
| `map` | Texture URL. Required: the promise resolves to `null` if it does not load. |
| `relief` | Height-map URL, or null. |
| `planet` | The body's record (`name`, `class`, `radius`). |
| `system`, `stars`, `constellations`, `glow` | As for the system map: the sky seen from that system. |
| `onDraw` | Called after each draw with the km per pixel at the view's centre (null without a radius). |

Drag turns, the wheel or a pinch zooms, a double click resets. Drawn on
demand only. The view has `setClouds(on)`, `setRelief(on)`, `request()`,
`dispose()`, `hasClouds`, `reliefReady`, and the `globe`, `camera`,
`controls` and `scene`.

For a planet without a texture file, `planet/planet-look.js`
`createGlobe(THREE, planet, { map, relief })` draws one from its `class`
and `look`; the galaxy and system maps use it for every planet.

## Shared modules

`viewer/space/` holds what the maps share; each module documents its use
at the top.

| Module | Exports | Purpose |
|---|---|---|
| `manifest.js` | `loadManifest` | A build's manifest as URLs. |
| `calendar.js` | `createCalendar`, `GREGORIAN` | Read and write dates with a project's calendar: `read(text)` → `{absolute}` or `{error}`, `text(absolute)`, `param(absolute)`. |
| `camera.js` | `createNavigator` | Drag to turn, right-drag to pan, wheel to zoom (Shift faster), eased flights, following a moving body. |
| `pointer.js` | `attachPointer`, `foldable`, `steeringHint`, `TOUCH` | Clicks and taps that pick, Esc to let go. |
| `search.js` | `createSearch` | The search box at the top of every map. |
| `sky.js` | `createSky`, `skyToggles` | The sky behind every map: background stars, the galactic band, the galaxy's stars and nebulae as seen from a system, constellation lines. |
| `galaxy-glow.js` | `loadGlow`, `bandLight` | The galactic band's light from `glow.json`. |
| `effects.js` | `createEffects`, `qualityButton`, `effectsOn` | Bloom, toggled per browser. |
| `star-colours.js` | `starColour`, `starColourMode`, `starColourButton`, `PHYSICAL`, `SATURATED` | Star colours by spectral class, physical or saturated. |
| `black-hole.js` | `createBlackHole`, `horizonMaterial`, `HORIZON` | The galactic centre and stellar black holes. |
| `pulsar.js` | `createPulsarBeams` | A pulsar's beams. |
| `procedural.js` | `proceduralSystem`, `proceduralBlock` | Fetch one procedural system's record by id, for the system map. |
| `icons.js` | `icon`, `toggleIcon`, `iconAdd`, `ICONS` | Remix Icon SVGs, generated by `make icons`; do not edit. |

`viewer/planet/` holds the planet's look (`planet-look.js`), its generated
textures (`planet-texture.js`, `texture-worker.js`) and the globe view;
`viewer/galaxy/` the galaxy map with its star field and nebula sprites.

## Browser state and events

Choices are kept in `localStorage` (missing storage is tolerated) and
announced on `window`, so that several maps on one page follow each other:

| Key | Values | Set by | Event on `window` |
|---|---|---|---|
| `galaxy-layer-<id>` | `shown`, `hidden` | A layer's button | Same name, `detail`: boolean |
| `galaxy-real-stars` | `shown`, `hidden` | The button of a `real` layer (instead of the key above) | Same name |
| `galaxy-nebulae` | `shown`, `hidden` | Galaxy map | Same name |
| `galaxy-procedural` | `shown`, `hidden` | Galaxy map; read by the system map for its sky | — |
| `galaxy-stems` | `shown`, `hidden` | Galaxy map | — |
| `space-effects` | `on`, `off` | Every map's quality button | `space-effects`, `detail`: boolean |
| `space-star-colours-galaxy`, `space-star-colours-system` | `physical`, `saturated` | Each map's colour button | — |
| `space-sky-names`, `space-sky-lines` | `shown`, `hidden` | The sky's buttons | — |

A host can dispatch the same events to switch the maps from its own
controls. `space-redraw` (no detail) is dispatched when a generated planet
texture is ready; the system map redraws on it.
