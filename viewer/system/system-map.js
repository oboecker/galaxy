/* The star-system map.
 *
 * One system in 3D: its stars, each on its level of the star tree around
 * the centres of gravity they share, the planets and their moons on their
 * orbits at a date, the habitable zone and the frost line of each host,
 * asteroid belts, rings, points of interest, and the Lagrange points of
 * whatever is selected.
 *
 * Scale: orbits are true to each other, in AU. Planets
 * and their moons' orbits are true to each other but enlarged against the
 * planets' orbits, by one factor — as large as it can be without a planet
 * or its moons reaching into a neighbouring orbit — and never smaller than
 * a few pixels. The star is capped at 15% of
 * the innermost orbit, or it would fill a system of few, far planets.
 *
 * The physics that needs more than Kepler is worked out in Python
 * (galaxy.systemmap): this file only moves bodies along their orbits.
 * Shared by every page that shows it, a site's or an editor's; each gives a container and one system's data, and may
 * give links ({ galaxy: name => URL, planet: (body, its planet) => URL or
 * null } — out to the galaxy map, on to a globe) and focus (a
 * body's name, flown to on arrival).
 */
import * as THREE from 'three'
// The camera, clicks and search every 3D map shares.
import { createNavigator } from '../space/camera.js'
import { attachPointer, foldable, steeringHint } from '../space/pointer.js'
import { createSearch } from '../space/search.js'
import { createEffects, qualityButton } from '../space/effects.js'
import { starColour, starColourButton, starColourMode } from '../space/star-colours.js'
import { createSky, skyToggles } from '../space/sky.js'
import { loadGlow } from '../space/galaxy-glow.js'
import { createBlackHole, horizonMaterial, HORIZON } from '../space/black-hole.js'
import { createPulsarBeams } from '../space/pulsar.js'
import { icon, toggleIcon } from '../space/icons.js'
import { createCalendar } from '../space/calendar.js'
import { CSS2DObject, CSS2DRenderer } from 'three/addons/renderers/CSS2DRenderer.js'
// One look for a planet in every view: lit, tilted, ringed, textured (its map
// or its class's), with its atmosphere — shared with the galaxy map.
import { CLASS_COLOURS, createGlobe, releaseTextures, ringBands, tiltQuaternion } from '../planet/planet-look.js'

const AU_KM = 1.496e8
const EXTENT = 500              // scene units the system's outermost reach is drawn at
const MIN_PIXELS = 3            // a body is never drawn smaller than this, in radius
const CORONA_REACH = 3          // a star's corona fades out at this many of its radii
// How a stellar remnant looks as a system's primary.
const REMNANT_LOOKS = {
  white_dwarf: { kind: 'white_dwarf', colour: 0xdfe8ff, corona: 2.2, light: 0xdfe8ff, intensity: 1.2 },
  neutron_star: { kind: 'neutron_star', colour: 0xb4f6ff, corona: 1.8, light: 0xb4f6ff, intensity: 0.6 },
  pulsar: { kind: 'pulsar', colour: 0xa8ffea, corona: 1.8, light: 0xa8ffea, intensity: 0.6 },
  black_hole: { kind: 'black_hole', colour: 0x000000, corona: 0, light: 0xff9a4a, intensity: 0.8 },
}
const MOON_FADE = [4, 16]       // a moon fades in as its orbit grows from this many pixels to that, on screen
// A planet's orbit fades out as the camera comes close against the orbit's
// size (its distance to what it looks at, over the orbit's semi-major
// axis): whole at the first, gone at the second — an orbit about 2.5
// screens across, then 25 — so that near a planet the other planets'
// orbits do not cross the view. The selected planet's stays.
const ORBIT_FADE = [0.5, 0.05]
// Zoomed out at most this many times the system's outer reach: the whole
// system still about 40 % of the view's height (the view opens at 2.4).
const ZOOM_OUT = 6
const LABEL_PIXELS = 40         // a zone's or centre's label shows once what it names is this large, on screen
const GAP_SHARE = 0.3           // a planet's radius may take this share of the gap to its neighbour
const RAD = Math.PI / 180
const UP = new THREE.Vector3(0, 1, 0)

// A point of interest's shape and colour, by its kind (galaxy.schema.POI_KINDS).
const POI_SHAPES = {
  point: [() => new THREE.OctahedronGeometry(1), 0xffd24a],
  station: [() => new THREE.OctahedronGeometry(1), 0xffd24a],
  jumpgate: [() => new THREE.TorusGeometry(1, 0.3, 8, 24), 0x7fe0ff],
  outpost: [() => new THREE.BoxGeometry(1.3, 1.3, 1.3), 0xb8e07a],
  shipyard: [() => new THREE.BoxGeometry(2, 0.8, 0.8), 0xffa04a],
  wreck: [() => new THREE.TetrahedronGeometry(1.1), 0x9a8f86],
  beacon: [() => new THREE.SphereGeometry(0.8, 12, 8), 0xff5a5a],
  catapult: [() => new THREE.ConeGeometry(0.9, 2, 12), 0xd07aff],
}
const SPEEDS = [
  ['10 minutes/s', 1 / 365.25 / 24 / 6], ['1 hour/s', 1 / 365.25 / 24], ['6 hours/s', 1 / 365.25 / 4], ['1 day/s', 1 / 365.25], ['1 week/s', 7 / 365.25], ['1 month/s', 1 / 12], ['1 year/s', 1], ['10 years/s', 10],
]
const DEFAULT_SPEED = 3         // 1 day/s
// The drives of a trip within a system, slowest first: galaxy.insystem's way names and their labels.
// A project's own modes (travel.json `modes`) go between the stars only.
const DRIVES = [['sublight', 'Sublight'], ['jumpgates', 'Jump gate'], ['own drive', 'Own drive']]
// The sublight thrust's stops, in g: 0 coasts (a Hohmann transfer); from
// 0.1 g (galaxy.travel_config MIN_THRUST_G) up to travel.json's sublight.g.
const THRUSTS = [0, 0.1, 0.2, 0.3, 0.5, 1, 1.5, 2, 3]
const LIGHT_KM_S = 299792.458

/* A speed as a reader takes it in: km/s, with its share of
 * light once that is worth saying; past half of light, as multiples of it —
 * the own drive's. The planner is Newtonian: relativity is not modelled. */
function speedText(kmS) {
  // Three figures: the model is no more precise than that.
  const three = n => Number(n.toPrecision(3)).toLocaleString('en')
  const c = kmS / LIGHT_KM_S
  if (c >= 0.5) return `${three(c)} c`
  return c >= 0.001 ? `${three(kmS)} km/s (${three(c * 100)} % c)` : `${three(kmS)} km/s`
}
const AU_DAY_KM_S = 1.496e8 / 86400       // AU a day in km/s

// ── orbits ────────────────────────────────────────────────────────────────────

/* Position on the orbit `years` after the epoch, in the orbit's unit (AU or
 * km), as galaxy.orbits.position: x and y in the reference plane, z out of it. */
function position(orbit, years, period) {
  const a = orbit.au || orbit.km || 0, e = orbit.e || 0
  const m = (orbit.anomaly || 0) * RAD + (period ? 2 * Math.PI * years / period : 0)
  let E = e < 0.8 ? m : Math.PI
  for (let k = 0; k < 30; k++) {
    const step = (E - e * Math.sin(E) - m) / (1 - e * Math.cos(E))
    E -= step
    if (Math.abs(step) < 1e-12) break
  }
  const x = a * (Math.cos(E) - e), y = a * Math.sqrt(1 - e * e) * Math.sin(E)
  const w = (orbit.periapsis || 0) * RAD, node = (orbit.node || 0) * RAD, inc = (orbit.i || 0) * RAD
  const xw = x * Math.cos(w) - y * Math.sin(w), yw = x * Math.sin(w) + y * Math.cos(w)
  return [xw * Math.cos(node) - yw * Math.cos(inc) * Math.sin(node),
    xw * Math.sin(node) + yw * Math.cos(inc) * Math.cos(node),
    yw * Math.sin(inc)]
}

/* Reference plane x, y and its normal z, to the scene's x, z and up y. */
/* Where the system stands in Earth's sky (galaxy.systemmap.sky):
 * a muted line under its name; none for Sol. */
function skyLine(sky) {
  if (!sky) return ''
  const ly = Math.round(sky.ly).toLocaleString('en-GB')
  return `<div class="sm-muted sm-sky">From Earth: ${escape(sky.text)} · ${ly} ly</div>`
}

function toScene(p, scale) {
  return new THREE.Vector3(p[0] * scale, p[2] * scale, -p[1] * scale)
}

function orbitLine(orbit, scale, colour, opacity) {
  const points = []
  for (let k = 0; k <= 256; k++) {
    points.push(toScene(position({ ...orbit, anomaly: k / 256 * 360 }, 0, 0), scale))
  }
  const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),
    new THREE.LineBasicMaterial({ color: colour, transparent: true, opacity }))
  return line
}

/* What the last commit had, where the draft changed it (an editor's
 * `saved` on a body): its orbit dashed and faint. */
function ghostOrbit(orbit, scale) {
  const line = orbitLine(orbit, scale, 0xffffff, 0.35)
  line.computeLineDistances()
  const along = line.geometry.attributes.lineDistance
  const dash = along.getX(along.count - 1) / 160
  line.material = new THREE.LineDashedMaterial({ color: 0xffffff, transparent: true, opacity: 0.35,
    dashSize: dash, gapSize: dash })
  line.raycast = () => {}
  return line
}

/* ... and its size: a circle around the body at the saved radius, `ratio`
 * of the drawn one, facing the camera and over the body, so a smaller one
 * shows too. A child of the body's globe: it moves and scales with it. */
function ghostSize(ratio) {
  const points = []
  for (let k = 0; k < 128; k++) {
    const a = k / 128 * 2 * Math.PI
    points.push(new THREE.Vector3(Math.cos(a) * ratio, Math.sin(a) * ratio, 0))
  }
  const ring = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(points),
    new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.6, depthTest: false }))
  ring.renderOrder = 10
  ring.raycast = () => {}
  const at = new THREE.Vector3(), turn = new THREE.Quaternion(), size = new THREE.Vector3()
  ring.onBeforeRender = (renderer, scene, camera) => {
    ring.matrixWorld.decompose(at, turn, size)
    ring.matrixWorld.compose(at, camera.quaternion, size)
  }
  return ring
}

function ghosts(body, mesh) {
  const saved = body.saved || {}
  if (saved.radius && body.radius) mesh.add(ghostSize(saved.radius / body.radius))
}

function circle(radius, colour, opacity) {
  return orbitLine({ au: radius }, 1, colour, opacity)
}

function name(body, kind) {
  return body.name && body.name !== '?' ? body.name : `${kind} ${body.index || ''}`.trim()
}

// ── the map ───────────────────────────────────────────────────────────────────

export function createSystemMap(container, system, options = {}) {
  // Dates as the system's calendar reads and writes them (../space/calendar.js).
  const calendar = createCalendar(system.calendar)
  const readDate = calendar.read, dateText = calendar.text, DATE_FORMS = calendar.forms
  const ERA_NAMES = Object.keys((system.calendar || {}).eras || { AD: 0, BC: 0 }).join(', ')
  container.classList.add('system-map')
  container.innerHTML = `
    <div class="sm-canvas"></div>
    <div class="sm-info"><strong>${escape(system.name)}</strong>${skyLine(system.sky)}<div class="sm-detail"></div></div>
    <div class="space-bar">
      ${options.links && options.links.galaxy ? `<a class="space-back" href="${escape(options.links.galaxy(system.name))}"
        title="Out to the galaxy map, ${escape(system.name)} selected">${icon('arrow-left-s')} Galaxy</a>` : ''}
      <button type="button" class="space-tool sm-whole" title="The whole system">${icon('focus-3')}</button>
    </div>
    <div class="sm-time">
      <button type="button" class="sm-play" title="Play or pause">${icon('play')}</button>
      <label class="sm-speed-label"><span class="sm-speed-word">Time runs at</span> <select class="sm-speed" title="How fast the map's clock runs — not a drive's speed">${SPEEDS.map(([label], k) =>
        `<option value="${k}"${k === DEFAULT_SPEED ? ' selected' : ''}>${label}</option>`).join('')}</select></label>
      <input class="sm-date" type="text" aria-label="Date shown" title="A date: ${ERA_NAMES} and a year, e.g. ${DATE_FORMS}" spellcheck="false">
    </div>
    <div class="sm-time-why" role="alert" hidden></div>
    <div class="sm-tools">
      <button type="button" class="sm-tool sm-gates-toggle" aria-pressed="false" title="Toggle the jumpgate pairs" data-toggle-icon="arrow-left-right" hidden></button>
      ${options.trip ? '<button type="button" class="sm-tool sm-trip-toggle" aria-pressed="false" title="Travel: a trip within the system, from the date shown" data-toggle-icon="route"></button>' : ''}
      ${!options.trip && options.trips ? '<button type="button" class="sm-tool sm-trip-toggle sm-stored-toggle" aria-pressed="false" title="Trips: the journeys of the story in this system" data-toggle-icon="flag" hidden></button>' : ''}
    </div>
    ${!options.trip && options.trips ? `<div class="sm-trip sm-stored" hidden>
      <h4>Trips</h4>
      <div class="sm-stored-list"></div>
      <div class="sm-note sm-trip-slow" hidden>Too fast to watch the flight: choose a slower speed below.</div>
    </div>` : ''}
    ${options.trip ? `<div class="sm-trip" hidden>
      <h4>Travel</h4>
      <div class="sm-grid">
        <label>From <select class="sm-trip-from"></select></label>
        <label>To <select class="sm-trip-to"></select></label>
        <label class="sm-wide" title="The drive this trip flies: its way is drawn; every way is compared below">Drive
          <input type="range" class="sm-trip-drive" min="0" max="${DRIVES.length - 1}" step="1" value="0">
          <span class="sm-field-note sm-drive-text">${DRIVES[0][1]}</span></label>
        <label class="sm-wide sm-setting"><span class="sm-setting-name">Thrust</span>
          <input type="range" class="sm-trip-setting" min="0" step="1">
          <span class="sm-field-note sm-setting-text"></span></label>
        <label>Leaving <input class="sm-trip-leaving" type="text" spellcheck="false"
          title="When the trip leaves: the date shown until a trip is planned; then the planned departure. ${DATE_FORMS}"></label>
        <span class="sm-action"><button type="button" class="sm-primary sm-trip-go">Plan</button></span>
        <span class="sm-field-why sm-wide sm-leaving-why" role="alert" hidden></span>
      </div>
      <div class="sm-note sm-trip-hint">Click a body for the start, another for the destination.</div>
      <div class="sm-note sm-trip-slow" hidden>Too fast to watch the flight: choose a slower speed below.</div>
      <div class="sm-note sm-trip-none" role="status" hidden></div>
      <div class="sm-way-head" aria-hidden="true" hidden><span>Way</span><span>Takes</span><span>Arrives</span></div>
      <div class="sm-trip-results"></div>
      ${options.tripSave ? `<div class="sm-keep" hidden>
        <h4>Keep this trip</h4>
        <div class="sm-note sm-keep-what"></div>
        <div class="sm-grid">
          <label>Name <input class="sm-keep-name" type="text" spellcheck="false"></label>
          <label>Arrive by <input class="sm-keep-by" type="text" placeholder="optional" spellcheck="false" title="${DATE_FORMS}"></label>
          <span class="sm-action sm-col2"><button type="button" class="sm-secondary sm-keep-go">Keep</button></span>
        </div>
        <div class="sm-note sm-keep-hint" role="status"></div>
      </div>` : ''}
      ${options.trips ? '<h4>Stored trips</h4><div class="sm-stored-list"></div><div class="sm-note sm-stored-hint" role="status"></div>' : ''}
    </div>` : ''}
    <div class="sm-hint">${steeringHint('body')}</div>`
  // The toggles written above draw their icon, filled while pressed.
  container.querySelectorAll('[data-toggle-icon]').forEach(button => toggleIcon(button, button.dataset.toggleIcon))
  const holder = container.querySelector('.sm-canvas')
  const detail = container.querySelector('.sm-detail')
  // On a phone the details fold to their first lines, a tap unfolds them.
  const removeFold = foldable(container.querySelector('.sm-info'))
  const dateInput = container.querySelector('.sm-date')
  const playButton = container.querySelector('.sm-play')
  const speedSelect = container.querySelector('.sm-speed')

  // A logarithmic depth buffer: one view spans a moon's surface and Sedna's
  // orbit, a ratio no linear one holds (Titan clipped).
  // A stencil: a black hole's horizon keeps the light effects' glow off it (space/effects.js).
  const renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: true, stencil: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  holder.appendChild(renderer.domElement)
  const labels = new CSS2DRenderer()
  labels.domElement.className = 'sm-labels'
  holder.appendChild(labels.domElement)

  const camera = new THREE.PerspectiveCamera(45, 1, 0.0005, 100000)
  let skyButtons = null                 // the sky's names and lines, toggled (set with the bar's buttons below)
  // The procedural galaxy's stars in the sky (galaxy.procedural):
  // where the host gives them (options.procedural: its procedural.json — an
  // editor and the maps site), while ⁂ is on — the galaxy map's choice, kept
  // in the browser — and always in an uncharted system's own sky
  // (options.uncharted).
  let skyProcedural = Boolean(options.procedural) && (options.uncharted || proceduralChosen())
  let proceduralStars = null            // fetched once, as sky stars
  let proceduralNebulae = []            // and the layer's nebulae, with them
  // The galaxy's light (options.glow: its glow.json, galaxy.procedural.glow):
  // the band as it lies from here; till it has come, or without it, the
  // band of the same make everywhere.
  let glow = null
  if (options.glow) loadGlow(options.glow).then(found => { if (found) { glow = found; redrawSky() } })

  function skyOf() {
    const stars = skyProcedural && proceduralStars ? [...(options.sky || []), ...proceduralStars] : options.sky
    const nebulae = skyProcedural ? [...(options.nebulae || []), ...proceduralNebulae] : (options.nebulae || [])
    return createSky({ seed: system.name, band: true, galaxy: system.galaxy, system, stars,
      constellations: system.constellations, glow, nebulae })
  }

  /* The sky made again, its procedural stars shown or not. */
  function redrawSky() {
    if (!scene) return
    const old = scene.getObjectByName('sky')
    if (old) {
      scene.remove(old)
      old.traverse(o => {
        if (o.geometry) o.geometry.dispose()
        if (o.material) { if (o.material.map) o.material.map.dispose(); o.material.dispose() }
      })
    }
    scene.add(skyOf())
    if (skyButtons) skyButtons.update()
    wake()
  }

  async function showProceduralSky(shown) {
    skyProcedural = shown
    if (shown && !proceduralStars) {
      const sky = await proceduralSky(options.procedural)
      proceduralStars = sky.stars
      proceduralNebulae = sky.nebulae
      if (!skyProcedural) return
    }
    redrawSky()
  }
  const nav = createNavigator(camera, labels.domElement, { holder, reach: () => (state.view ? state.view.frame : EXTENT) })
  const controls = nav.controls
  // The light effects' bloom, shared (../space/effects.js); the scene is set
  // by newScene. For the glow alone, stars brighter than white: they bloom,
  // the planets lit by them do not.
  const fx = createEffects(renderer, null, camera, { onGlow: glowing => { starBright.value = glowing ? 3 : 1 } })

  const state = {
    years: (options.absolute ?? system.epoch_year) - system.epoch_year,
    playing: false, speed: SPEEDS[DEFAULT_SPEED][1], view: null, selected: null, last: performance.now(), frame: 0,
    awake: 0, moving: false,
  }

  /* Drawn only while something changes: time runs, the view moves, a flight's route pulses,
   * or something woke the map — input, a resize, a texture or an answer
   * arriving — and for a moment after, for what follows from it (a hover,
   * a load it started). A still, paused map draws nothing. */
  const WAKE_MS = 1000
  function wake(ms = WAKE_MS) {
    state.awake = Math.max(state.awake, performance.now() + ms)
  }
  dateInput.value = dateText(system.epoch_year + state.years)

  let scene = null, bodies = [], extras = [], route = null
  let colourMode = starColourMode('system', 'physical')     // the stars' colours (../space/star-colours.js)

  // ── the system view ─────────────────────────────────────────────────────

  /* Each host's centre at a date:
   * the star tree walked from the whole system's centre of gravity, at the
   * origin. Each group's satellites circle its core; both sides move about
   * their shared centre, by the other's share of the mass. By key ("A",
   * "A+B"). */
  function hostPositions(tree, years, scale) {
    const out = {}
    const walk = (node, at) => {
      out[node.key] = at
      if (node.star) return
      const sats = node.satellites.map(s => ({ s, rel: toScene(position(s.orbit, years, s.period), scale) }))
      const shift = new THREE.Vector3()
      sats.forEach(({ s, rel }) => shift.addScaledVector(rel, s.node.mass / node.mass))
      walk(node.core, at.clone().sub(shift))
      sats.forEach(({ s, rel }) => walk(s.node, at.clone().add(rel).sub(shift)))
    }
    walk(tree, new THREE.Vector3())
    return out
  }

  function findNode(node, key) {
    if (!node) return null
    if (node.key === key) return node
    if (node.star) return null
    return findNode(node.core, key) || node.satellites.reduce((found, x) => found || findNode(x.node, key), null)
  }

  /* How far each host's centre can stray from the system's, in AU. */
  function hostStray(tree) {
    const out = {}
    const walk = (node, d) => {
      out[node.key] = d
      if (node.star) return
      const far = s => s.orbit.au * (1 + (s.orbit.e || 0))
      walk(node.core, d + Math.max(0, ...node.satellites.map(s => far(s) * s.node.mass / node.mass)))
      node.satellites.forEach(s => walk(s.node, d + far(s) * (1 - s.node.mass / node.mass)))
    }
    walk(tree, 0)
    return out
  }

  function systemView() {
    const tree = system.tree
    const hosts = system.hosts || {}
    const starOf = Object.fromEntries((system.stars || []).map(s => [s.name, s]))
    const planets = system.planets.filter(p => p.orbit && p.orbit.au && p.host)
    const stray = tree ? hostStray(tree) : {}
    const satellites = []          // every star orbit: { s, group }
    const collect = node => { if (node && !node.star) { node.satellites.forEach(s => satellites.push({ s, group: node })); collect(node.core); node.satellites.forEach(s => collect(s.node)) } }
    collect(tree)
    const around = (key, au) => au + (stray[key] || 0)
    const reach = Math.max(
      ...planets.map(p => around(p.host, p.orbit.au * (1 + (p.orbit.e || 0)))),
      ...Object.values(stray),
      ...(system.belts || []).filter(b => b.host).map(b => around(b.host, b.outer)),
      ...(system.points_of_interest || []).filter(p => p.anchor && p.anchor.au && p.anchor.host)
        .map(p => around(p.anchor.host, p.anchor.au)),
      ...Object.entries(hosts).filter(([, h]) => h.zones).map(([k, h]) => around(k, h.habitable_zone[1] * 1.2)),
      0.05)
    const scale = EXTENT / reach              // scene units per AU

    // One enlargement for planets and their moons' orbits alike, so that
    // both stay true to each other: as large as the tightest pair of
    // neighbouring orbits allows (GAP_SHARE of the gap each), and small
    // enough that each planet's moons stay well inside its gaps.
    let factor = Infinity
    const byHost = {}
    for (const p of planets) (byHost[p.host] = byHost[p.host] || []).push(p)
    for (const group of Object.values(byHost)) {
      const sorted = group.slice().sort((a, b) => a.orbit.au - b.orbit.au)
      for (let k = 0; k < sorted.length; k++) {
        const p = sorted[k], inner = sorted[k - 1], outer = sorted[k + 1]
        const gaps = []
        if (inner) gaps.push(p.orbit.au * (1 - (p.orbit.e || 0)) - inner.orbit.au * (1 + (inner.orbit.e || 0)))
        if (outer) gaps.push(outer.orbit.au * (1 - (outer.orbit.e || 0)) - p.orbit.au * (1 + (p.orbit.e || 0)))
        if (inner) {
          const sizes = ((inner.radius || 0) + (p.radius || 0)) / AU_KM
          if (gaps[0] > 0 && sizes > 0) factor = Math.min(factor, GAP_SHARE * gaps[0] / sizes)
        }
        const moonReach = Math.max(0, ...(p.moons || []).filter(m => m.orbit && m.orbit.km)
          .map(m => m.orbit.km * (1 + (m.orbit.e || 0))))
        const gap = Math.min(...gaps.filter(g => g > 0), p.orbit.au * (1 - (p.orbit.e || 0)))
        if (moonReach > 0 && gap > 0) factor = Math.min(factor, GAP_SHARE * gap * AU_KM / moonReach)
      }
    }
    const first = planets.slice().sort((a, b) => a.orbit.au - b.orbit.au)[0]
    if (!isFinite(factor)) factor = first && first.radius ? 0.15 * first.orbit.au / (first.radius / AU_KM) : 1000
    factor = Math.max(1, factor)
    const kmScale = scale / AU_KM * factor     // scene units per km, for planet and moon sizes and moon orbits
    const innermost = Math.min(...planets.map(p => p.orbit.au * (1 - (p.orbit.e || 0))), reach / 10)

    const view = newScene(scale)
    view.kmScale = kmScale
    let cachedYears = null, cached = null
    view.hostAt = (key, years) => {
      if (years !== cachedYears) { cached = tree ? hostPositions(tree, years, scale) : {}; cachedYears = years }
      return (cached[key] || new THREE.Vector3()).clone()
    }
    // A group per host, moved to its centre each frame: its zones, belts and
    // the orbit lines of what circles it travel with it.
    view.carriers = {}
    const carrier = key => {
      if (!view.carriers[key]) {
        const group = new THREE.Group()
        view.scene.add(group)
        view.carriers[key] = group
        view.movers.push({ object: group, place: years => view.hostAt(key, years) })
      }
      return view.carriers[key]
    }
    view.carrier = carrier

    // The stars, each on its own level of the tree.
    const closest = Math.min(...satellites.map(({ s }) => s.orbit.au * (1 - (s.orbit.e || 0))), Infinity)
    const cap = Math.min(0.15 * innermost, 0.3 * closest)
    const placed = (system.stars || []).filter(s => s.placed && s.mass)
    for (const st of placed) {
      const radius = Math.min(st.radius / AU_KM * factor, cap) * scale
      addStar(view, st, radius, st.name, years => view.hostAt(st.name, years), st.name !== system.primary_name)
    }
    if (!placed.length) {
      const st = system.star || { mass: 1, radius: 696000, spectral_class: 'G2V' }
      let radius = Math.min(st.radius / AU_KM * factor, cap) * scale
      // A black hole's horizon is 24 km: drawn so, it stayed a speck however
      // near the camera came. Drawn at the enlarged scale its disc reaches
      // about as far as a star may be drawn (cap), clear of the planets.
      if (st.object_type === 'black_hole') radius = Math.max(radius, 0.12 * cap * scale)
      addStar(view, st, radius, system.primary_name || system.name, () => new THREE.Vector3(), false)
    }
    for (const { s, group } of satellites) {
      // Each side's path about the group's centre: exactly so for a single
      // satellite (the core's the opposite, smaller ellipse).
      const cls = node => (starOf[node.star || ''] || {}).spectral_class || 'G'
      // In the star's colour, recoloured with the toggle.
      const tinted = (line, node) => {
        view.tints.push(mode => line.material.color.set(starColour(cls(node), mode, 0xaaaaaa)))
        return line
      }
      const home = carrier(group.key)
      home.add(tinted(orbitLine(s.orbit, scale * (1 - s.node.mass / group.mass), starColour(cls(s.node), colourMode, 0xaaaaaa), 0.3), s.node))
      if (group.satellites.length === 1) {
        home.add(tinted(orbitLine({ ...s.orbit, periapsis: (s.orbit.periapsis || 0) + 180 }, scale * s.node.mass / group.mass,
          starColour(cls(group.core), colourMode, 0xaaaaaa), 0.3), group.core))
      }
    }
    // The centre of gravity of each group something circles — or the
    // system's, when it has more than one star.
    const used = new Set([...planets.map(p => p.host), ...(system.belts || []).map(b => b.host),
      ...(system.points_of_interest || []).map(p => p.anchor && p.anchor.host)])
    for (const key of Object.keys(hosts)) {
      if (!key.includes('+') || !(used.has(key) || (tree && key === tree.key))) continue
      const arm = 0.012 * EXTENT
      const cross = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(-arm, 0, 0), new THREE.Vector3(arm, 0, 0),
        new THREE.Vector3(0, 0, -arm), new THREE.Vector3(0, 0, arm)]),
        new THREE.LineBasicMaterial({ color: 0xaaaaaa, transparent: true, opacity: 0.6 }))
      carrier(key).add(cross)
      const node = findNode(tree, key)
      const spread = node && !node.star ? Math.max(...node.satellites.map(x => x.orbit.au * (1 + (x.orbit.e || 0)))) : reach
      view.scaled.push({ label: tag(view, cross, `centre of ${key}`, null, 'sm-zone-label'), size: spread * scale, anchor: carrier(key) })
    }

    for (const [key, h] of Object.entries(hosts)) {
      if (!h.zones) continue
      const [hzIn, hzOut] = h.habitable_zone
      const zone = new THREE.Mesh(new THREE.RingGeometry(hzIn * scale, hzOut * scale, 128),
        new THREE.MeshBasicMaterial({ color: 0x3fbf6f, transparent: true, opacity: 0.08, side: THREE.DoubleSide,
          depthWrite: false }))
      // A tint under everything, never hiding an orbit behind it.
      zone.renderOrder = -1
      zone.rotation.x = -Math.PI / 2
      carrier(key).add(zone)
      const frost = circle(h.frost_line * scale, 0x88ccff, 0.25)
      carrier(key).add(frost)
      const whose = Object.values(hosts).filter(x => x.zones).length > 1 ? ` of ${key}` : ''
      view.scaled.push(
        { label: tag(view, frost, `frost line${whose}`, new THREE.Vector3(h.frost_line * scale, 0, 0), 'sm-zone-label', carrier(key)),
          size: h.frost_line * scale, anchor: carrier(key) },
        { label: tag(view, zone, `habitable zone${whose}`, new THREE.Vector3(0, 0, -(hzIn + hzOut) / 2 * scale), 'sm-zone-label', carrier(key)),
          size: hzOut * scale, anchor: carrier(key) })
    }
    for (const belt of system.belts || []) if (belt.host) carrier(belt.host).add(beltCloud(belt, scale))

    for (const planet of planets) {
      const colour = CLASS_COLOURS[planet.class] || 0xbbbbbb
      const orbits = [orbitLine(planet.orbit, scale, colour, 0.35)]
      if (planet.saved && planet.saved.orbit && planet.saved.orbit.au) orbits.push(ghostOrbit(planet.saved.orbit, scale))
      orbits.forEach(line => { line.userData.opacity = line.material.opacity; carrier(planet.host).add(line) })
      const mesh = createGlobe(THREE, planet, { map: textureOf(planet), relief: (options.heights || {})[planet.name] })
      ghosts(planet, mesh)
      view.scene.add(mesh)
      const centre = years => view.hostAt(planet.host, years)
      const body = {
        kind: 'planet', data: planet, mesh, label: tag(view, mesh, name(planet, 'Planet')),
        radius: (planet.radius || 0) * kmScale, centre, sun: centre,       // its host, which lights its haze
        place: years => centre(years).add(toScene(position(planet.orbit, years, planet.period), scale)),
        orbits, orbitSize: (planet.orbit.au || 0) * scale,
      }
      bodies.push(body)
      addMoons(view, planet, body, kmScale)
    }
    for (const poi of system.points_of_interest || []) {
      const added = poiBody(view, poi, scale)
      if (added) bodies.push(added)
    }
    view.enlargement = factor
    view.frame = reach * scale
    return view
  }

  /* A planet's moons, on their orbits in its equator, at the scale its own
   * size is drawn (moons in the system view). */
  function addMoons(view, planet, planetBody, kmScale) {
    const moons = (planet.moons || []).filter(m => m.orbit && m.orbit.km)
    if (!moons.length) return
    const equator = tiltQuaternion(THREE, planet)
    const lines = new THREE.Group()
    view.scene.add(lines)
    const outer = Math.max(...moons.map(m => m.orbit.km * (1 + (m.orbit.e || 0)))) * kmScale
    view.movers.push({ object: lines, place: years => planetBody.place(years), size: outer })
    for (const moon of moons) {
      const colour = CLASS_COLOURS[moon.class] || 0xaaaaaa
      const line = orbitLine(moon.orbit, kmScale, colour, 0.4)
      line.quaternion.copy(equator)
      lines.add(line)
      if (moon.saved && moon.saved.orbit && moon.saved.orbit.km) {
        const was = ghostOrbit(moon.saved.orbit, kmScale)
        was.quaternion.copy(equator)
        lines.add(was)
      }
      const mesh = createGlobe(THREE, moon, { map: textureOf(moon), relief: (options.heights || {})[moon.name] })
      ghosts(moon, mesh)
      mesh.material.transparent = true          // it fades in with zoom
      view.scene.add(mesh)
      const centre = years => planetBody.place(years)
      bodies.push({ kind: 'moon', data: moon, planet, mesh, label: tag(view, mesh, name(moon, 'Moon'), null, 'sm-label sm-moon-label'),
        radius: (moon.radius || 0) * kmScale, centre, size: moon.orbit.km * kmScale, sun: planetBody.centre,
        place: years => centre(years).add(toScene(position(moon.orbit, years, moon.period), kmScale).applyQuaternion(equator)) })
    }
  }

  // ── pieces ──────────────────────────────────────────────────────────────

  function newScene(scale) {
    bodies.forEach(b => b.label && b.label.removeFromParent())
    bodies = []
    clearExtras()
    if (scene) dispose(scene)
    const view = { scene: new THREE.Scene(), scale, movers: [], scaled: [], tints: [], spinners: [], holes: [] }
    view.scene.add(new THREE.AmbientLight(0xffffff, 0.25))
    // The sky behind it (../space/sky.js): this system's own, the galaxy's
    // band across it as it lies to the system's plane and as it shines from
    // where the system stands (options.glow).
    // And the galaxy's stars where they stand from here (options.sky).
    // Its constellations where the sidecar has them (galaxy.constellations).
    view.scene.add(skyOf())
    scene = view.scene
    if (skyButtons) skyButtons.update()
    fx.setScene(scene)
    return view
  }

  /* A star, its glow and its light, at `place(years)`; `companion` when it
   * is not the primary. */
  function addStar(view, star, radius, label, place, companion = false) {
    const remnant = REMNANT_LOOKS[star.object_type]
    if (remnant) return addRemnant(view, star, remnant, radius, label, place)
    const colour = starColour(star.spectral_class || 'G', colourMode)
    // A disc darker toward its rim, as a star's is, and a corona fading
    // outward from it — not a shell around it, which read as the planets'
    // old aura.
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 32), starSurface(colour))
    mesh.scale.setScalar(radius)
    mesh.userData.glow = true                         // drawn in the light effects' glow
    view.scene.add(mesh)
    const corona = new THREE.Sprite(new THREE.SpriteMaterial({ map: coronaTexture(), color: colour, transparent: true,
      blending: THREE.AdditiveBlending, depthWrite: false }))
    corona.scale.setScalar(2 * CORONA_REACH)          // across, in star radii
    mesh.add(corona)
    const light = new THREE.PointLight(colour, companion ? 1.2 : 2.5, 0, 0)
    mesh.add(light)
    view.tints.push(mode => {
      const c = starColour(star.spectral_class || 'G', mode)
      mesh.material.uniforms.colour.value.set(c)
      corona.material.color.set(c)
      light.color.set(c)
    })
    bodies.push({ kind: 'star', data: star, companion, mesh,
      label: tag(view, mesh, label), radius, place, fixedSize: true })
  }

  /* A stellar remnant as the primary (galaxy.stars.REMNANTS): a
   * white dwarf a small blue-white star, its light dim; a neutron star or
   * pulsar a tiny cyan-white one, a pulsar with two beams turning with the
   * map's clock (a turn a day: still when paused, at a glance at 1 day/s); a
   * black hole the galactic centre's, scaled to the sphere — horizon, disc,
   * photon ring, halo — its faint orange light the disc's. The disc and beams are the sphere's
   * children: they keep their size to it when it is drawn larger than true. */
  function addRemnant(view, star, look, radius, label, place) {
    // A black hole's sphere plain black, as its horizon is: a star's surface
    // whitens toward its centre, and the two, one size, showed a grey grid.
    const surface = look.kind === 'black_hole' ? horizonMaterial() : starSurface(look.colour)
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 32), surface)
    mesh.scale.setScalar(radius)
    mesh.userData.glow = look.kind !== 'black_hole'
    view.scene.add(mesh)
    if (look.kind === 'black_hole') {
      // The galactic centre's black hole (../space/black-hole.js), its
      // horizon the sphere: disc, photon ring and halo round it, the disc in
      // its equator, tipped toward the eye a little.
      const hole = createBlackHole()
      hole.scale.setScalar(1 / HORIZON)
      hole.rotation.x = 0.35
      mesh.add(hole)
      view.holes.push(hole)
    } else {
      const corona = new THREE.Sprite(new THREE.SpriteMaterial({ map: coronaTexture(), color: look.colour, transparent: true,
        blending: THREE.AdditiveBlending, depthWrite: false }))
      corona.scale.setScalar(2 * look.corona)
      mesh.add(corona)
    }
    if (look.kind === 'pulsar') {
      // Its beams (../space/pulsar.js), 14 of its radii long.
      const spinner = createPulsarBeams(14, look.colour)
      mesh.add(spinner)
      view.spinners.push(spinner)
    }
    const light = new THREE.PointLight(look.light, look.intensity, 0, 0)
    mesh.add(light)
    bodies.push({ kind: 'star', data: star, companion: false, mesh,
      label: tag(view, mesh, label), radius, place, fixedSize: true })
  }

  /* A star's surface: its colour, darker toward the rim (limb darkening,
   * I ∝ 0.4 + 0.6·cos θ), lit by nothing but itself. The depth chunks keep it
   * right under the logarithmic depth buffer. */
  function starSurface(colour) {
    return new THREE.ShaderMaterial({
      // `bright`: 1, or brighter than white in the light effects' glow render.
      uniforms: { colour: { value: new THREE.Color(colour) }, bright: starBright },
      vertexShader: `
        #include <common>
        #include <logdepthbuf_pars_vertex>
        varying vec3 vNormal;
        varying vec3 vView;
        void main() {
          vec4 at = modelViewMatrix * vec4(position, 1.0);
          vNormal = normalize(normalMatrix * normal);
          vView = normalize(-at.xyz);
          gl_Position = projectionMatrix * at;
          #include <logdepthbuf_vertex>
        }`,
      fragmentShader: `
        #include <common>
        #include <logdepthbuf_pars_fragment>
        uniform vec3 colour;
        uniform float bright;
        varying vec3 vNormal;
        varying vec3 vView;
        void main() {
          #include <logdepthbuf_fragment>
          float mu = clamp(dot(normalize(vNormal), normalize(vView)), 0.0, 1.0);
          gl_FragColor = vec4(mix(colour, vec3(1.0), 0.35 * mu) * (0.4 + 0.6 * mu) * bright, 1.0);
        }`,
    })
  }

  // Shared by every star's surface: set by the effects for their glow render.
  const starBright = { value: 1 }

  /* The corona: white at the star's rim, fading to nothing CORONA_REACH
   * radii out, steeply at first. One texture for every star, tinted by its
   * colour. */
  let corona = null
  function coronaTexture() {
    if (corona) return corona
    const size = 256, c = document.createElement('canvas')
    c.width = c.height = size
    const g = c.getContext('2d')
    const rim = size / 2 / CORONA_REACH
    const fade = g.createRadialGradient(size / 2, size / 2, rim * 0.9, size / 2, size / 2, size / 2)
    for (let k = 0; k <= 10; k++) {
      const x = k / 10
      fade.addColorStop(x, `rgba(255,255,255,${(0.55 * (1 - x) ** 3).toFixed(3)})`)
    }
    g.fillStyle = fade
    g.fillRect(0, 0, size, size)
    corona = new THREE.CanvasTexture(c)
    corona.colorSpace = THREE.SRGBColorSpace
    return corona
  }

  /* A globe's own texture, where the planet has a map
   * (options.textures, by name); else its class's colour. */
  const loader = new THREE.TextureLoader(new THREE.LoadingManager(() => wake(), () => wake()))
  function textureOf(body) {
    const url = (options.textures || {})[body.name]
    if (!url) return null
    const texture = loader.load(url)
    texture.colorSpace = THREE.SRGBColorSpace
    return texture
  }

  function beltCloud(belt, scale) {
    const count = 2500, positions = new Float32Array(count * 3)
    let seed = 0
    for (const c of String(belt.name || belt.id)) seed = (seed * 31 + c.charCodeAt(0)) >>> 0
    const rand = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296 }
    for (let k = 0; k < count; k++) {
      const r = (belt.inner + (belt.outer - belt.inner) * rand()) * scale, angle = rand() * 2 * Math.PI
      positions[k * 3] = r * Math.cos(angle)
      positions[k * 3 + 1] = (rand() - 0.5) * (belt.outer - belt.inner) * scale * 0.08
      positions[k * 3 + 2] = r * Math.sin(angle)
    }
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    return new THREE.Points(geometry, new THREE.PointsMaterial({ color: 0xb0a080, size: 1.5, sizeAttenuation: false,
      transparent: true, opacity: 0.6 }))
  }

  /* A point of interest: around a star or a group of them on a circular
   * orbit at its distance (starting at 0° at the epoch); at a Lagrange point
   * of a planet or moon; or in orbit above one. None around a host that is
   * not drawn. */
  function poiBody(view, poi, scale) {
    const at = poi.anchor || {}
    let place
    if (at.body === 'star' && at.au) {
      const host = (system.hosts || {})[at.host]
      if (!host) return null
      const period = Math.sqrt(at.au ** 3 / host.mass)
      view.carrier(at.host).add(orbitLine({ au: at.au }, scale, 0xffd24a, 0.2))
      place = years => view.hostAt(at.host, years).add(toScene(position({ au: at.au }, years, period), scale))
    } else {
      const [planetId, moonId] = String(at.body).split('/')
      const planet = system.planets.find(p => p.id === planetId)
      const moon = moonId && planet ? (planet.moons || []).find(m => m.id === moonId) : null
      // `km` above it, in its equator, at the scale its size is drawn: the
      // orbit and period worked out in Python (systemmap._above), as a moon's.
      const equator = (moon || planet) ? tiltQuaternion(THREE, moon || planet) : null
      place = years => {
        const host = bodies.find(b => b.data === (moon || planet))
        if (!host) return new THREE.Vector3()
        if (at.point) return lagrange(host, years, at.point, view)
        if (!poi.orbit) return host.place(years)
        return host.place(years).add(toScene(position(poi.orbit, years, poi.period), view.kmScale).applyQuaternion(equator))
      }
    }
    const [geometry, colour] = POI_SHAPES[poi.kind] || POI_SHAPES.point
    const mesh = new THREE.Mesh(geometry(), new THREE.MeshBasicMaterial({ color: colour }))
    view.scene.add(mesh)
    return { kind: 'poi', data: poi, mesh, label: tag(view, mesh, poi.name, null, 'sm-poi-label'), radius: 0, place }
  }

  /* Lagrange point `point` of `body` at `years`: L4 and L5 on its orbit, 60°
   * ahead and behind; L3 opposite; L1 and L2 at its Hill radius inside and
   * outside — which an enlarged planet would swallow, so drawn at least
   * just outside it. */
  function lagrange(body, years, point, view) {
    // Relative to what the body orbits — a moving primary, in a binary.
    const centre = body.centre ? body.centre(years) : new THREE.Vector3()
    return lagrangeAround(body, years, point, view).add(centre)
  }

  function lagrangeAround(body, years, point, view) {
    const at = t => body.place(t).sub(body.centre ? body.centre(t) : new THREE.Vector3())
    const here = at(years)
    const ahead = at(years + (body.data.period || 1) / 1000)
    const d = here.length()
    if (point === 'L3') return here.clone().multiplyScalar(-1)
    if (point === 'L4' || point === 'L5') {
      // 60° ahead and behind in the plane of its orbit, about the orbit's own
      // axis — the way it goes round. About the system's vertical, a moon of
      // a tilted planet (Charon, in Pluto's equator) had them off its orbit
      //.
      const axis = here.clone().cross(ahead)
      if (axis.lengthSq() === 0) axis.set(0, 1, 0)           // not moving: no plane to go by
      axis.normalize()
      return here.clone().applyAxisAngle(axis, (point === 'L4' ? 1 : -1) * Math.PI / 3)
    }
    const hill = (body.data.hill || 0) * (body.kind === 'moon' ? view.kmScale : view.scale / AU_KM)
    // Moons are drawn enlarged with their planet: L1 and L2 just outside them.
    const moons = bodies.filter(b => b.kind === 'moon' && b.planet === body.data).map(b => b.size * 1.2)
    const reach = Math.max(hill, body.radius * 1.4, ...moons)
    return here.clone().multiplyScalar((d + (point === 'L2' ? reach : -reach)) / d)
  }

  function tag(view, object, text, at = null, className = 'sm-label', parent = null) {
    const el = document.createElement('div')
    el.className = className
    el.textContent = text
    const label = new CSS2DObject(el)
    // Above its body rather than over it: the renderer sets the element's
    // transform itself, so the offset goes through its anchor.
    label.center.set(0.5, 1.5)
    if (at) {
      label.position.copy(at)
      ;(parent || view.scene).add(label)          // a zone's label travels with its host
    } else {
      object.add(label)
    }
    return label
  }

  function clearExtras() {
    extras.forEach(o => { o.removeFromParent(); if (o.element) o.element.remove() })
    extras = []
  }

  /* The selected planet's or moon's Lagrange points, as small rings with
   * their names. */
  function showLagrange(body) {
    clearExtras()
    if (!body || (body.kind !== 'planet' && body.kind !== 'moon')) return
    for (const point of ['L1', 'L2', 'L3', 'L4', 'L5']) {
      const marker = new THREE.Mesh(new THREE.TorusGeometry(1, 0.18, 6, 24),
        new THREE.MeshBasicMaterial({ color: 0x8fe3ff }))
      marker.userData.point = point
      scene.add(marker)
      const el = document.createElement('div')
      el.className = 'sm-lagrange-label'
      el.textContent = point
      const label = new CSS2DObject(el)
      label.center.set(0.5, 1.5)
      marker.add(label)
      extras.push(marker, label)
    }
  }

  // ── selection ───────────────────────────────────────────────────────────

  const ray = new THREE.Raycaster(), pointer = new THREE.Vector2()

  function pick(event) {
    const box = renderer.domElement.getBoundingClientRect()
    pointer.set((event.clientX - box.left) / box.width * 2 - 1, -(event.clientY - box.top) / box.height * 2 + 1)
    ray.setFromCamera(pointer, camera)
    const hit = ray.intersectObjects(bodies.filter(b => b.mesh.visible).map(b => b.mesh), false)[0]
    if (hit) return bodies.find(b => b.mesh === hit.object)
    // Small bodies: the nearest within a few pixels on screen.
    let best = null, bestPx = 12
    for (const b of bodies.filter(x => x.mesh.visible)) {
      const p = b.mesh.position.clone().project(camera)
      const px = Math.hypot((p.x - pointer.x) * box.width / 2, (p.y - pointer.y) * box.height / 2)
      if (p.z < 1 && px < bestPx) { best = b; bestPx = px }
    }
    return best
  }

  function select(body) {
    state.selected = body
    bodies.forEach(b => b.label && b.label.element.classList.toggle('is-selected', b === body))
    showLagrange(body)
    detail.innerHTML = body ? describe(body) : ''
  }

  /* Where a star sits in the tree: the group whose centre it circles, the
   * other side of that pair, its orbit and period if it is a satellite. */
  function standing(starName) {
    let found = null
    const walk = node => {
      if (!node || node.star) return
      const coreStar = n => (n.star ? n.star : coreStar(n.core))
      for (const s of node.satellites) {
        if (coreStar(s.node) === starName) found = { group: node, other: node.core.key, orbit: s.orbit, period: s.period }
      }
      if (!found && coreStar(node.core) === starName && node.satellites.length) {
        found = { group: node, other: node.satellites.map(s => s.node.key).join(', ') }
      }
      walk(node.core)
      node.satellites.forEach(s => walk(s.node))
    }
    walk(system.tree)
    return found
  }

  function zonesLine(key, h) {
    return `habitable zone ${h.habitable_zone[0].toFixed(2)}–${h.habitable_zone[1].toFixed(2)} AU · frost line ${h.frost_line.toFixed(2)} AU${key.includes('+') ? ` <span class="sm-muted">(${escape(key)}, their light together)</span>` : ''}`
  }

  function describe(body) {
    const d = body.data
    if (body.kind === 'star') {
      const lines = [`<strong>${escape(d.name || system.primary_name || system.name)}</strong>`]
      // A black hole has no temperature of its own to give.
      lines.push(d.mass ? `${escape(d.spectral_class || '')} · ${d.mass.toFixed(2)} solar masses`
        + (d.temperature ? ` · ${fmt(d.temperature)} K` : '') : 'No spectral class')
      const hosts = system.hosts || {}
      if (hosts[d.name]) lines.push(zonesLine(d.name, hosts[d.name]))
      const at = standing(d.name)
      if (at && at.orbit) {
        lines.push(`${at.orbit.au} AU from ${escape(at.other)} on average · e ${at.orbit.e ?? 0} · ${at.period.toFixed(2)} years`)
      }
      if (at) lines.push(`<span class="sm-muted">circles the centre of gravity of ${escape(at.group.key)} with ${escape(at.other)}</span>`)
      if (!body.companion) {
        const lost = (system.stars || []).filter(s => !s.placed).map(s => escape(s.name))
        if (lost.length) lines.push(`<span class="sm-muted">${lost.join(', ')}: no spectral class or orbit — not drawn</span>`)
        for (const [key, h] of Object.entries(hosts)) if (key.includes('+') && h.zones) lines.push(zonesLine(key, h))
      }
      return lines.join('<br>')
    }
    if (body.kind === 'poi') {
      const at = d.anchor || {}
      return `<strong>${escape(d.name)}</strong>${d.kind ? ` <span class="sm-muted">${escape(d.kind)}</span>` : ''}<br>${at.au ? `${at.au} AU from ${escape(at.host || 'the star')}` : at.point
        ? `at ${at.point} of ${escape(anchorName(at.body))}` : `${fmt(at.km)} km above ${escape(anchorName(at.body))}${d.period
        ? ` · once round in ${d.period * 365.25 < 1 ? `${(d.period * 365.25 * 24).toFixed(1)} hours` : `${(d.period * 365.25).toFixed(1)} days`}` : ''}`}`
    }
    const lines = [`<strong>${escape(name(d, body.kind === 'moon' ? 'Moon' : 'Planet'))}</strong>${d.dwarf ? ' <span class="sm-muted">dwarf planet</span>' : ''}`]
    if (d.radius) lines.push(`radius ${fmt(d.radius)} km${d.gravity ? ` · ${d.gravity.toFixed(2)} g` : ''}`)
    if (d.orbit) {
      const unit = d.orbit.au ? `${d.orbit.au} AU` : `${fmt(d.orbit.km)} km`
      const period = d.period ? (d.period < 0.3 ? `${(d.period * 365.25).toFixed(1)} days` : `${d.period.toFixed(2)} years`) : ''
      lines.push(`orbit ${unit} · e ${d.orbit.e ?? 0} · i ${d.orbit.i ?? 0}°${period ? ` · ${period}` : ''}`)
      if (d.orbit.au && body.kind === 'planet') {
        const centre = body.centre(state.years)
        const around = d.host && d.host.includes('+') ? `the centre of ${escape(d.host)}` : escape(d.host || 'its star')
        lines.push(`now ${(body.mesh.position.distanceTo(centre) / scaleOf()).toFixed(3)} AU from ${around}`)
      } else if (body.kind === 'moon') {
        lines.push(`moon of ${escape(name(body.planet, 'Planet'))}`)
      }
    }
    if (typeof d.tilt === 'number') lines.push(`axial tilt ${d.tilt}°${typeof d.tilt_bearing === 'number' ? `, leaning toward ${d.tilt_bearing}°` : ''}`)
    // Bands, the gaps between them divisions (Saturn's Cassini Division).
    if (d.rings) lines.push(`rings ${ringBands(d).map(band => `${band.inner}–${band.outer}`).join(', ')} planet radii`)
    if (body.kind === 'planet' && (d.moons || []).length) lines.push(`${d.moons.length} moon${d.moons.length > 1 ? 's' : ''}`)
    // On to its globe, where it has a map and the page has a place for it.
    const globe = options.links && options.links.planet ? options.links.planet(d, body.kind === 'moon' ? body.planet : null) : null
    if (globe) lines.push(`<a class="space-link" href="${escape(globe)}">Globe ${icon('arrow-right-s')}</a>`)
    lines.push('<span class="sm-muted">L1–L5 shown; L1 and L2 at least just outside the enlarged body and its moons</span>')
    return lines.join('<br>')
  }

  function anchorName(id) {
    if (id === 'star') return 'the star'
    const [pid, mid] = String(id).split('/')
    const planet = system.planets.find(p => p.id === pid)
    if (!planet) return id
    if (!mid) return name(planet, 'Planet')
    const moon = (planet.moons || []).find(m => m.id === mid)
    return moon ? `${name(moon, 'Moon')} (of ${name(planet, 'Planet')})` : id
  }

  function scaleOf() { return state.view ? state.view.scale : 1 }

  // A body's name is as good a target as its dot.
  // By where the click is, not its target: the orbit controls capture the
  // pointer, so the click lands on the layer, not on the name.
  const labelled = event => {
    const el = document.elementsFromPoint(event.clientX, event.clientY)
      .find(e => e.matches && e.matches('.sm-label, .sm-poi-label'))
    return el ? bodies.find(b => b.label && b.label.element === el && b.label.visible) || null : null
  }
  // As the galaxy map: a click goes to a body — selects it, flies there and
  // keeps it in view as it moves; a click on nothing, or Esc, lets go.
  // With the Travel panel open a click picks the trip's ends
  // instead, and the camera stays: both ends should stay in view.
  const detachPointer = attachPointer(labels.domElement, {
    pick: event => labelled(event) || pick(event),
    onPick: body => {
      if (trip && trip.picking()) {
        select(body)
        trip.pick(body)
      } else {
        goTo(body)
      }
    },
    onNothing: letGo,
    onEscape: () => { if (state.selected || nav.busy) letGo() },
    live: () => container.isConnected,
  })

  /* How far from a body the camera comes to see it: a planet's moons all in
   * view, else the body a fair size on screen; never farther away than it is. */
  function nearOf(body) {
    if (body.kind === 'poi') {
      const at = body.data.anchor || {}
      const host = at.body && at.body !== 'star' ? bodies.find(b => refOf(b) === String(at.body)) : null
      return host ? nearOf(host) : 0.05 * state.view.frame
    }
    // A far-out moon (Saturn's Phoebe) would leave the rest specks: one more
    // than three times as far as the next is left outside the frame.
    const moons = bodies.filter(b => b.kind === 'moon' && b.planet === body.data).map(b => b.size).sort((a, b) => a - b)
    while (moons.length > 1 && moons[moons.length - 1] > 3 * moons[moons.length - 2]) moons.pop()
    // A star at least a fiftieth of the system's frame away: a remnant's true
    // size (a black hole's 24 km) put the camera a millionth of it from the
    // centre, where the wheel, which zooms by factors, could not get back out.
    const least = body.kind === 'star' ? 0.02 * state.view.frame : 1e-4
    return Math.max(body.radius * (body.kind === 'star' ? 20 : 12), ...moons.map(size => size * 2.5), least)
  }

  /* Fly to a body (or, with none, back to the whole system), following it
   * once there; never into it — by its true radius: its drawn size is
   * enlarged to a few pixels when far, and a flight ending in one long
   * frame would take that from the far end and stop there. */
  function goTo(body) {
    if (body) {
      // Framed by its own size: the nearer of the distance the
      // camera was at and the body's, close on a moon, flew to a gas giant
      // or the star at the moon's distance. Again to the one selected, the
      // zoom the viewer chose stays.
      const distance = body === state.selected ? nav.distance() : nearOf(body)
      nav.goTo(() => body.mesh.position, { item: body, distance, near: () => body.radius * 1.5 })
    } else {
      nav.goTo(new THREE.Vector3(), { distance: state.view.frame * 2.4, follow: false })
    }
    select(body)
  }

  function letGo() {
    nav.letGo()
    select(null)
  }

  // ── search (as the galaxy map's) ────────────────────────────────────────

  const KIND = { star: 'Star', planet: 'Planet', moon: 'Moon', poi: 'Point of interest' }
  function titleOf(b) {
    if (b.kind === 'star') return b.data.name || system.primary_name || system.name
    if (b.kind === 'poi') return b.data.name || '?'
    return name(b.data, KIND[b.kind])
  }
  function detailOf(b) {
    const d = b.data
    if (b.kind === 'star') return [KIND.star, d.spectral_class].filter(Boolean).join(' · ')
    if (b.kind === 'poi') return [d.kind || KIND.poi, anchorName((d.anchor || {}).body || 'star')].join(' · ')
    const where = b.kind === 'moon' ? `moon of ${name(b.planet, 'Planet')}` : d.orbit && d.orbit.au ? `${d.orbit.au} AU` : 'planet'
    return [d.dwarf ? 'dwarf planet' : '', where, d.class].filter(Boolean).join(' · ')
  }
  const search = createSearch(container.querySelector('.space-bar'), {
    placeholder: 'Search for a body...', items: () => bodies, title: titleOf, detail: detailOf, choose: goTo,
  })
  container.querySelector('.sm-whole').addEventListener('click', () => goTo(null))
  const removeQuality = qualityButton(container.querySelector('.space-bar'))
  // Physical star colours here, saturated at a button (../space/star-colours.js).
  const removeColours = starColourButton(container.querySelector('.space-bar'), 'system', 'physical', mode => {
    colourMode = mode
    if (state.view) state.view.tints.forEach(tint => tint(mode))
  })
  // The sky's star names and constellation lines (../space/sky.js).
  skyButtons = skyToggles(container.querySelector('.space-bar'), () => scene)
  // The procedural galaxy's stars in the sky: ⁂, the galaxy map's choice.
  let removeProcedural = () => {}
  if (options.procedural) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'space-tool sky-procedural'
    toggleIcon(button, 'sparkling')
    const show = () => {
      button.setAttribute('aria-pressed', String(skyProcedural))
      button.title = skyProcedural ? 'Hide the uncharted systems in the sky' : 'Show the uncharted systems in the sky (the procedural galaxy)'
    }
    show()
    button.addEventListener('click', () => {
      try { localStorage.setItem(PROCEDURAL_KEY, skyProcedural ? 'hidden' : 'shown') } catch { /* this page only */ }
      showProceduralSky(!skyProcedural)
      show()
    })
    container.querySelector('.space-bar').appendChild(button)
    removeProcedural = () => button.remove()
    if (skyProcedural) showProceduralSky(true)
  }

  // ── time controls ───────────────────────────────────────────────────────

  playButton.addEventListener('click', () => {
    state.playing = !state.playing
    playButton.innerHTML = icon(state.playing ? 'pause' : 'play')
  })
  speedSelect.addEventListener('change', () => { state.speed = SPEEDS[+speedSelect.value][1] })
  const timeWhy = container.querySelector('.sm-time-why')
  /* A date field's refusal said under it, in words (as an editor says one
   * at its field); cleared by the next date it takes. */
  function refuse(input, why, read) {
    input.classList.toggle('is-invalid', !!read.error)
    input.setAttribute('aria-invalid', String(!!read.error))
    why.hidden = !read.error
    why.textContent = read.error || ''
  }
  dateInput.addEventListener('change', () => {
    const read = readDate(dateInput.value)
    refuse(dateInput, timeWhy, read)
    if (read.error) return
    state.years = read.absolute - system.epoch_year
    if (trip) trip.dateSet()
  })

  // ── a trip within the system ──
  // The host plans it (galaxy.insystem, options.trip): from a body or
  // point of interest to another, leaving at the date shown. Two lines
  //: the flight path, fixed once planned — each leg from
  // where its start was left to where its end is reached — with the ship
  // moving along it as time runs, leaving and arriving with the bodies;
  // and the straight line between start and destination as they are now.

  /* A route as the galaxy map draws one (galaxy-map.js streamLine, after its
   * distance line): each leg a faint line in its colour
   * with a glow streaming along it, start to end; a stop a small white point. */
  // How travel looks — route colours, the streaming glow, the drive slider,
  // the jumpgate overlay — from travel.json's `maps` (options.travelSettings),
  // the one place both maps read it from. Without it, no travel is drawn.
  let look = null, topThrust = 3
  const lookReady = (options.travelSettings ? fetch(options.travelSettings)
    .then(response => (response.ok ? response.json() : null)).catch(() => null) : Promise.resolve(null))
    .then(settings => {
      look = settings && settings.maps
      if (settings && settings.sublight) topThrust = settings.sublight.g
      return look
    })

  function streamLine(points, colour) {
    const group = new THREE.Group()
    group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color: colour, transparent: true, opacity: look.stream.line_opacity })))
    const positions = new Float32Array(look.stream.samples * 3)
    for (let i = 0; i < look.stream.samples; i++) {
      const at = pointAt(points, i / (look.stream.samples - 1))
      positions.set([at.x, at.y, at.z], i * 3)
    }
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geometry.setAttribute('color', new THREE.BufferAttribute(new Float32Array(look.stream.samples * 3), 3))
    const flow = new THREE.Line(geometry, new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, blending: THREE.AdditiveBlending }))
    flow.userData.stream = new THREE.Color(colour)
    group.add(flow)
    return group
  }

  /* Each frame: the glow a step further along every leg, a pulse of a third
   * of its length. */
  function flowRoute() {
    const stream = look.stream
    flight.flow = (flight.flow + stream.step_per_frame) % 1
    route.traverse(line => {
      const colour = line.userData && line.userData.stream
      if (!colour) return
      const colors = line.geometry.attributes.color.array
      for (let i = 0; i < look.stream.samples; i++) {
        let d = Math.abs(i / (look.stream.samples - 1) - flight.flow)
        d = Math.min(d, 1 - d)
        const a = d < stream.pulse_share ? Math.cos(d / stream.pulse_share * Math.PI / 2) ** 2 : 0
        colors[i * 3] = colour.r * a; colors[i * 3 + 1] = colour.g * a; colors[i * 3 + 2] = colour.b * a
      }
      line.geometry.attributes.color.needsUpdate = true
    })
  }

  // The own drive orange and gates cyan, as on the galaxy map; sublight pale.
  const routeColour = kind => (look.route_colours[kind] || (kind === 'ballistic' && look.route_colours.sublight) || '#ffffff')

  function refOf(body) {
    if (body.kind === 'star') return `star:${body.data.name}`
    if (body.kind === 'moon') return `${body.planet.id}/${body.data.id}`
    return body.kind === 'planet' || body.kind === 'poi' ? String(body.data.id) : null
  }

  // What is drawn: the group, and what moves in it each frame.
  let flight = null

  function clearRoute() {
    if (route) { scene.remove(route); dispose(route); route = null }
    flight = null
  }

  /* A marker on screen, not in the scene: the same few pixels at any zoom,
   * never fighting the bodies or zones for depth. */
  function marker(className, colour, text) {
    const el = document.createElement('div')
    el.className = className
    el.style.setProperty('--colour', colour)
    el.innerHTML = `<span class="sm-meeting-ring"></span>${text ? `<span class="sm-meeting-label">${escape(text)}</span>` : ''}`
    const object = new CSS2DObject(el)
    object.center.set(0.5, 0.5)
    return object
  }

  /* How far along a leg the ship is, as a share of its length, a share
   * `f` of its time in: sublight speeds up to halfway and brakes; the own
   * drive and a gate hop go evenly. */
  function along(kind, f) {
    if (kind !== 'sublight') return f
    return f < 0.5 ? 2 * f * f : 1 - 2 * (1 - f) * (1 - f)
  }

  /* A coast's points are even in time (galaxy.insystem._ballistic): the
   * ship moves from point to point at an even pace, not by length. */
  function pointByIndex(points, f) {
    const at = Math.min(points.length - 1, Math.max(0, f * (points.length - 1)))
    const k = Math.min(points.length - 2, Math.floor(at))
    return points[k].clone().lerp(points[k + 1], at - k)
  }

  function pointAt(points, share) {
    const lengths = points.slice(1).map((p, k) => p.distanceTo(points[k]))
    let left = share * lengths.reduce((a, b) => a + b, 0)
    for (let k = 0; k < lengths.length; k++) {
      if (left <= lengths[k] || k === lengths.length - 1) {
        return points[k].clone().lerp(points[k + 1], lengths[k] ? Math.min(1, left / lengths[k]) : 0)
      }
      left -= lengths[k]
    }
    return points[0].clone()
  }

  /* A leg's points with its ends on its bodies as the map draws them —
   * moons' orbits and L1/L2 enlarged — when it leaves and arrives; the
   * shift spread along the way, so the line runs from body to body. */
  function onBodies(points, b0, b1, t0, t1) {
    const d0 = b0 ? b0.place(t0).sub(points[0]) : new THREE.Vector3()
    const d1 = b1 ? b1.place(t1).sub(points[points.length - 1]) : new THREE.Vector3()
    const lengths = points.slice(1).map((p, k) => p.distanceTo(points[k]))
    const total = lengths.reduce((a, b) => a + b, 0) || 1
    let run = 0
    return points.map((p, k) => {
      if (k) run += lengths[k - 1]
      const s = run / total
      return p.clone().addScaledVector(d0, 1 - s).addScaledVector(d1, s)
    })
  }

  function drawRoute(option, departure, ends, frame = true, stored = false) {
    clearRoute()
    route = new THREE.Group()
    const scale = scaleOf()
    const legs = []
    let at = 0
    const stops = []
    for (const leg of option.legs) {
      const from = at, to = at + leg.days / 365.25
      const [b0, b1] = (leg.refs || []).map(ref => ref && bodies.find(x => refOf(x) === ref))
      const points = onBodies(leg.points.map(p => toScene(p, scale)), b0, b1, departure + from, departure + to)
      // Waiting for a launch window: no line, the ship rides with its body.
      if (leg.kind === 'wait') {
        legs.push({ kind: leg.kind, points, body: b0, from, to })
        at = to
        continue
      }
      route.add(streamLine(points, routeColour(leg.kind)))
      if (legs.length && legs[legs.length - 1].kind !== 'wait') stops.push(points[0])
      // Where the leg's end is reached: a ring, and its way there dotted
      // along its orbit — as drawn.
      if (leg.track && leg.track.length > 1) {
        const track = b1 ? leg.track.map((_, k, all) => b1.place(departure + from + (to - from) * k / (all.length - 1)))
          : leg.track.map(p => toScene(p, scale))
        const way = new THREE.Line(new THREE.BufferGeometry().setFromPoints(track),
          new THREE.LineDashedMaterial({ color: routeColour(leg.kind), dashSize: scale * 0.004, gapSize: scale * 0.004,
            transparent: true, opacity: 0.7 }))
        way.computeLineDistances()
        route.add(way)
        const meet = marker('sm-meeting', routeColour(leg.kind), `${leg.end} on arrival`)
        meet.position.copy(points[points.length - 1])
        route.add(meet)
      }
      legs.push({ kind: leg.kind, points, from, to })
      at = to
    }
    if (stops.length) {
      route.add(new THREE.Points(new THREE.BufferGeometry().setFromPoints(stops), new THREE.PointsMaterial({
        color: 0xffffff, size: look.stop_pixels, sizeAttenuation: false, transparent: true, opacity: 0.9 })))
    }
    // The straight line between start and destination now, faint; and the ship.
    const now = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]),
      new THREE.LineDashedMaterial({ color: 0xffffff, dashSize: scale * 0.01, gapSize: scale * 0.01, transparent: true, opacity: 0.35 }))
    route.add(now)
    const ship = marker('sm-ship', '#ffffff', '')
    route.add(ship)
    flight = { departure, legs, now, ship, ends, total: at, stored, flow: 0 }
    scene.add(route)
    moveFlight()
    if (!frame) return
    // Framed: the camera keeps its direction and closes in on the route.
    const sphere = new THREE.Box3().setFromObject(route).getBoundingSphere(new THREE.Sphere())
    const radius = Math.max(sphere.radius, scale * 0.05)
    const direction = camera.position.clone().sub(controls.target).normalize()
    nav.letGo()
    controls.target.copy(sphere.center)
    camera.position.copy(sphere.center).addScaledVector(direction, radius * 3)
  }

  /* Each frame: the straight line to where the bodies are, the ship where
   * it is on its way — shown between leaving and arriving only. */
  function moveFlight() {
    if (!flight) return
    flowRoute()
    const [a, b] = flight.ends.map(ref => bodies.find(x => refOf(x) === ref))
    if (a && b) {
      flight.now.geometry.setFromPoints([a.mesh.position, b.mesh.position])
      flight.now.computeLineDistances()
    }
    const t = state.years - flight.departure
    // Arrived, or the date set outside the flight: planned again from the
    // date shown, the way chosen kept — the ship flies again.
    // A flight shorter than half a second at the speed time runs cannot be
    // watched: no ship, the route planned again at most twice a second,
    // and a hint to slow down.
    const blur = state.playing && flight.total / state.speed < 0.5
    // Even at the slowest speed too short to see (the own drive): nothing
    // to slow down for.
    const instant = flight.total / SPEEDS[0][1] < 0.5
    container.querySelectorAll('.sm-trip-slow').forEach(el => {
      if (el.hidden === blur) el.hidden = !blur
      const text = instant ? 'Near-instant: no flight to watch.' : 'Too fast to watch the flight: choose a slower speed below.'
      if (el.textContent !== text) el.textContent = text
    })
    // A stored trip keeps its date: the ship flies it again only when its
    // departure comes round, as time is set back.
    if (trip && !flight.stored && (t > flight.total || t < 0)) trip.again(blur ? 500 : 0)
    const leg = flight.legs.find(l => t >= l.from && t <= l.to)
    flight.ship.visible = !!leg && !blur
    if (leg) {
      const f = leg.to > leg.from ? (t - leg.from) / (leg.to - leg.from) : 1
      flight.ship.position.copy(leg.kind === 'wait' && leg.body ? leg.body.place(state.years)
        : leg.kind === 'wait' || leg.kind === 'ballistic' ? pointByIndex(leg.points, f) : pointAt(leg.points, along(leg.kind, f)))
    }
  }

  /* Time set to run so that a flight takes a few seconds on screen: the
   * fastest speed at which it still does. */
  function paceFor(days) {
    let k = 0
    SPEEDS.forEach(([, speed], n) => { if (days / 365.25 / speed >= 3) k = n })
    state.speed = SPEEDS[k][1]
    speedSelect.value = String(k)
  }

  function duration(days) {
    if (days < 1 / 86400) return '< 1 s'
    if (days < 1 / 24 / 60) return `${(days * 86400).toFixed(0)} s`
    if (days < 1 / 24) return `${(days * 24 * 60).toFixed(0)} min`
    if (days < 2) return `${(days * 24).toFixed(1)} h`
    return `${days.toFixed(1)} days`
  }

  /* A way, as both maps show it (galaxy-map.js wayLine): its name, how long,
   * when it arrives; under it the stops and how far. */
  function wayLine(option) {
    const label = (DRIVES.find(([way]) => way === option.name) || [option.name, option.name])[1]
    if (option.reachable === false) {
      return `<span class="sm-way-name">${escape(label)}</span><span class="sm-way-days">—</span><span class="sm-way-arrival"></span>`
        + `<span class="sm-way-how">${escape(option.why)}</span>`
    }
    const far = option.legs.reduce((sum, leg) => sum + leg.au, 0)
    const stops = option.legs.slice(0, -1).filter(leg => leg.kind !== 'wait').map(leg => leg.end)
    const wait = option.legs.find(leg => leg.kind === 'wait')
    // How fast: a coast leaving and arriving; sublight its
    // average and its peak at turnover; else its average, while moving.
    const coast = option.legs.find(leg => leg.speeds)
    const speed = coast ? `coasts ${speedText(coast.speeds[0])} → ${speedText(coast.speeds[1])}`
      : option.peak ? `${speedText(option.average * AU_DAY_KM_S)} average, ${speedText(option.peak * AU_DAY_KM_S)} at turnover`
        : option.average ? speedText(option.average * AU_DAY_KM_S) : ''
    const how = [wait ? `waits ${duration(wait.days)} for the launch window` : '', stops.length ? `via ${stops.map(escape).join(', ')}` : '',
      `${far.toFixed(3)} AU`, speed].filter(Boolean).join(' · ')
    // Three columns — the way, how long, when it arrives — the same in every
    // row; under them the stops and how far.
    return `<span class="sm-way-name">${escape(label)}</span><span class="sm-way-days">${duration(option.days)}</span>`
      + `<span class="sm-way-arrival">${escape(option.arrival)}</span><span class="sm-way-how">${how}</span>`
  }

  /* The own drive's share of its speed between the stars, from the slider:
   * a millionth (0) to all of it (60), a tenth of a decade a step. */
  function shareSteps() { return Math.round(-Math.log10(look.drive_share_min.system) * 10) }
  function efficiencyOf(value) { const top = shareSteps(); return value >= top ? 1 : 10 ** ((value - top) / 10) }

  function efficiencyText(share) {
    return share >= 1 ? 'at full speed, as between the stars'
      : `at 1/${fmt(Math.round(1 / share))} of its speed between the stars`
  }

  /* The sublight thrust's stops up to travel.json's sublight.g. */
  function thrusts() { return THRUSTS.filter(g => g <= topThrust) }
  const thrustShort = g => (g === 0 ? 'coasting (ballistic)' : `at ${g} g`)
  function thrustText(g) {
    return g === 0 ? 'none: coasting — a Hohmann transfer, at the next launch window' : `${g} g`
  }

  /* The date shown as the planner reads it: an era and a decimal year. */
  const dateParam = calendar.param

  const trip = options.trip ? (() => {
    const panel = container.querySelector('.sm-trip')
    const toggle = container.querySelector('.sm-trip-toggle')
    const from = container.querySelector('.sm-trip-from'), to = container.querySelector('.sm-trip-to')
    const results = container.querySelector('.sm-trip-results')
    let next = 'from'
    // An unnamed body by its orbit, as galaxy.insystem.label_of names it.
    const label = (data, planet = null) => {
      const named = (data.name || '').trim()
      if (named && named !== '?') return named
      const orbit = data.orbit || {}
      return planet ? `Moon at ${fmt(orbit.km || 0)} km of ${label(planet)}` : `Planet at ${+(orbit.au || 0).toPrecision(6)} AU`
    }
    const stops = () => bodies.map(b => [refOf(b), b]).filter(([ref]) => ref)
      .map(([ref, b]) => `<option value="${escape(ref)}">${escape(b.kind === 'moon' ? label(b.data, b.planet)
        : b.kind === 'planet' ? label(b.data) : b.data.name || ref)}</option>`).join('')
    const fill = () => {
      if (from.options.length) return
      from.innerHTML = to.innerHTML = stops()
      if (to.options.length > 1) to.selectedIndex = 1
    }
    function show(open) {
      panel.hidden = !open
      toggle.setAttribute('aria-pressed', String(open))
      if (open) fill()
      else clearRoute()
    }
    toggle.addEventListener('click', () => show(panel.hidden))
    // The trip as planned — its places, departure, the drive's share, every
    // way — which the rows show and Keep stores. Once the ship has arrived
    // it flies again from the date shown, the way chosen
    // kept: only the route drawn changes, never the plan.
    // The drive chosen: its way is
    // drawn and kept; every way is compared in the rows, each at its setting.
    let chosen = DRIVES[0][0], pending = false, planned = 0, last = null
    const rows = new Map()          // option name → { row, option }: kept, so a click is never lost to a new plan
    const driveSlider = container.querySelector('.sm-trip-drive'), driveText = container.querySelector('.sm-drive-text')
    const slider = container.querySelector('.sm-trip-setting'), sliderText = container.querySelector('.sm-setting-text')
    const settingName = container.querySelector('.sm-setting-name')
    const wayHead = container.querySelector('.sm-way-head')
    // Each drive's setting, remembered: the thrust (sublight, and to and from
    // the gates — the same drive) as a stop of thrusts(); the own drive's share.
    const setting = { thrust: 0, share: 0 }
    const thrustNow = () => thrusts()[setting.thrust]
    const shareNow = () => efficiencyOf(setting.share)
    function showSetting() {
      const way = DRIVES[+driveSlider.value][0]
      driveText.textContent = DRIVES[+driveSlider.value][1]
      const field = slider.closest('label')
      if (way === 'own drive') {
        settingName.textContent = 'Speed'
        field.title = "The own drive's share of its speed between the stars: a drive that does worse near a star, chosen per trip"
        slider.max = String(shareSteps())
        slider.value = String(setting.share)
        // Its speed here, once planned: the web's density where the system
        // lies is the planner's to know; scaled with the slider as it moves.
        const own = last && last.options.find(o => o.name === 'own drive' && o.rate)
        sliderText.textContent = efficiencyText(shareNow())
          + (own ? ` — ${speedText(own.rate / last.share * shareNow() * AU_DAY_KM_S)} here` : '')
      } else {
        settingName.textContent = way === 'jumpgates' ? 'Thrust to and from the gates' : 'Thrust'
        field.title = 'The sublight drive\'s thrust: turning over halfway; none coasts, leaving when the orbits line up'
        slider.max = String(thrusts().length - 1)
        slider.value = String(setting.thrust)
        sliderText.textContent = thrustText(thrustNow())
      }
    }
    // The sliders' ranges from travel.json; without its settings, no trips.
    toggle.hidden = true
    lookReady.then(look => {
      if (!look) return
      setting.thrust = thrusts().length - 1
      setting.share = shareSteps()
      showSetting()
      toggle.hidden = false
    })
    // Leaving: the date shown until a trip is planned, then its departure;
    // a date set by hand — here or in the time bar — is the next one to plan.
    const leaving = container.querySelector('.sm-trip-leaving'), tripHint = container.querySelector('.sm-trip-hint')
    const leavingWhy = container.querySelector('.sm-leaving-why')
    let leavingSet = false
    leaving.addEventListener('change', () => {
      const read = readDate(leaving.value)
      refuse(leaving, leavingWhy, read)
      if (read.error) return
      leavingSet = true
      state.years = read.absolute - system.epoch_year
      dateInput.value = dateText(read.absolute)
      refuse(dateInput, timeWhy, {})
    })
    leaving.addEventListener('keydown', event => { if (event.key === 'Enter') { leaving.dispatchEvent(new Event('change')); plan() } })
    slider.addEventListener('input', () => {
      if (DRIVES[+driveSlider.value][0] === 'own drive') setting.share = +slider.value
      else setting.thrust = +slider.value
      showSetting()
    })
    // A new setting: the same trip planned again, the drive chosen kept.
    slider.addEventListener('change', () => { if (last) plan({ keepChoice: true }) })
    driveSlider.addEventListener('input', showSetting)
    // Another drive: its way drawn from the plan there is, if it has one.
    driveSlider.addEventListener('change', () => {
      choose(DRIVES[+driveSlider.value][0])
      if (last) drawChosen()
    })

    const keepWhat = container.querySelector('.sm-keep-what')
    // What a kept trip records of its drive: the setting of the way chosen.
    const settingOf = way => way === 'own drive' ? (last.share < 1 ? `, ${efficiencyText(last.share)}` : '')
      : last.thrust !== topThrust ? `, ${thrustShort(last.thrust)}` : ''
    function sayKept() {
      const option = last && last.options.find(o => o.name === chosen && o.reachable !== false)
      const keepForm = container.querySelector('.sm-keep')
      if (keepForm) keepForm.hidden = !option
      if (!keepWhat || !option) return
      keepWhat.innerHTML = `Keeps <strong>${escape(DRIVES.find(([way]) => way === option.name)[1])}</strong>, leaving `
        + `${escape(dateText(system.epoch_year + last.departure))} — as planned${escape(settingOf(option.name))}.`
    }
    function choose(name) {
      chosen = name
      driveSlider.value = String(Math.max(0, DRIVES.findIndex(([way]) => way === name)))
      showSetting()
      rows.forEach(e => e.row.classList.toggle('is-chosen', e.option.name === name))
      sayKept()
    }
    // The chosen drive's way drawn — or, where it has none, why not.
    const driveNone = container.querySelector('.sm-trip-none')
    function drawChosen(frame = false) {
      const option = last.options.find(o => o.name === chosen)
      const flown = option && option.reachable !== false
      driveNone.hidden = flown
      if (!flown) {
        clearRoute()
        const name = DRIVES.find(([way]) => way === chosen)[1]
        driveNone.textContent = option ? `${name}: ${option.why}.` : `${name}: no way on this trip${chosen === 'jumpgates' ? ' — no gate pair, or none faster than sublight' : ''}.`
        return null
      }
      drawRoute(option, last.departure, last.ends, frame)
      return option
    }

    /* Planned from Leaving (or, with keepChoice, from the plan's own
     * departure), the rows and Keep then this plan. */
    async function plan({ keepChoice = false, quiet = false } = {}) {
      if (from.value === to.value) { clearRoute(); results.textContent = 'Pick two different places.'; return }
      let departure
      if (keepChoice && last) departure = last.departure
      else {
        const read = leaving.value.trim() ? readDate(leaving.value) : { absolute: system.epoch_year + state.years }
        refuse(leaving, leavingWhy, read)
        if (read.error) return
        departure = read.absolute - system.epoch_year
      }
      rows.clear()
      results.textContent = 'Planning…'
      const ends = [from.value, to.value], share = shareNow(), thrust = thrustNow()
      try {
        const data = await fetchPlan(ends, departure, share, thrust)
        if (panel.hidden) return
        results.innerHTML = ''
        for (const option of data.options) {
          const row = document.createElement('button')
          row.type = 'button'
          row.className = 'sm-trip-option'
          row.innerHTML = wayLine(option)
          const entry = { row, option }
          // A row chooses its drive (the comparison stays,
          // under the sliders).
          row.addEventListener('click', () => {
            choose(option.name)
            if (option.reachable !== false) paceFor(option.days)
            drawChosen()
          })
          rows.set(option.name, entry)
          results.appendChild(row)
        }
        wayHead.hidden = !data.options.length
        last = { ends, departure, options: data.options, share, thrust }
        showSetting()
        leavingSet = false
        leaving.value = dateText(system.epoch_year + departure)
        const first = data.options.find(o => o.legs.length)
        if (first) tripHint.textContent = `${first.legs[0].start} → ${first.legs[first.legs.length - 1].end}`
        choose(chosen)
        const keep = last.options.find(o => o.name === chosen && o.reachable !== false)
        if (keep && !quiet) paceFor(keep.days)
        // A new plan: the map at its departure, so that the ship is seen to leave.
        if (keep && !keepChoice) {
          state.years = departure
          dateInput.value = dateText(system.epoch_year + departure)
        }
        drawChosen(!quiet)
      } catch (error) {
        clearRoute()
        rows.clear()
        last = null
        wayHead.hidden = true
        results.textContent = `No trip: ${error.message || error}`
      }
    }

    async function fetchPlan(ends, departure, share, thrust) {
      const query = new URLSearchParams({ start: ends[0], end: ends[1], date: dateParam(system.epoch_year + departure) })
      if (share < 1) query.set('efficiency', String(share))
      if (thrust !== topThrust) query.set('thrust', String(thrust))
      planned = performance.now()
      pending = true
      try {
        const response = await fetch(`${options.trip}?${query}`)
        const data = await response.json()
        if (!response.ok) throw new Error(data.error || response.statusText)
        return data
      } finally {
        pending = false
      }
    }

    /* The ship flies again from the date shown: the chosen way planned
     * anew for the route drawn; the rows and Keep stay with the plan. */
    async function fly() {
      if (!last) return
      const departure = state.years, ends = last.ends
      try {
        const data = await fetchPlan(ends, departure, last.share, last.thrust)
        const option = data.options.find(o => o.name === chosen && o.reachable !== false)
        if (option && !panel.hidden && last && last.ends === ends) drawRoute(option, departure, ends, false)
      } catch (error) { /* the plan stays as it was drawn */ }
    }

    container.querySelector('.sm-trip-go').addEventListener('click', () => plan())

    // Kept (options.tripSave, an editor): the way chosen, as
    // planned; goes with the next save. A name already stored asks first.
    const keepButton = container.querySelector('.sm-keep-go')
    const keepName = container.querySelector('.sm-keep-name'), keepBy = container.querySelector('.sm-keep-by')
    let replacing = null
    const unask = () => { replacing = null; if (keepButton) keepButton.textContent = 'Keep' }
    if (keepName) keepName.addEventListener('input', unask)
    if (keepButton) keepButton.addEventListener('click', async () => {
      const hint = container.querySelector('.sm-keep-hint')
      const option = last && last.options.find(o => o.name === chosen && o.reachable !== false)
      if (!option) return
      const name = keepName.value.trim(), by = keepBy.value.trim()
      if (!name) { hint.textContent = 'Name the trip to keep it.'; keepName.focus(); return }
      if (by) {
        const read = readDate(by)
        keepBy.classList.toggle('is-invalid', !!read.error)
        if (read.error) { hint.textContent = `Arrive by: ${read.error}.`; return }
      }
      keepBy.classList.remove('is-invalid')
      const taken = stored && stored.names().includes(name)
      if (taken && replacing !== name) {
        replacing = name
        keepButton.textContent = `Replace ${name}`
        hint.textContent = `A trip named ${name} is stored already: Replace it, or give this one another name.`
        return
      }
      const body = new URLSearchParams({
        name, by, system: system.name, way: option.name,
        start: option.legs[0].start, end: option.legs[option.legs.length - 1].end,
        depart: dateParam(system.epoch_year + last.departure),
      })
      if (option.name === 'own drive' && last.share < 1) body.set('efficiency', String(last.share))
      if (option.name !== 'own drive' && last.thrust !== topThrust) body.set('thrust', String(last.thrust))
      const response = await fetch(options.tripSave, { method: 'POST', body })
      const data = await response.json()
      unask()
      if (!response.ok) { hint.textContent = data.error || response.statusText; return }
      hint.textContent = `${taken ? 'Replaced' : 'Kept'} the trip ${data.name} — it goes with the next save.`
      if (stored) stored.load()
      if (options.onChange) options.onChange()
    })

    return {
      follow() {
        // Leaving follows the date shown until a trip is planned, or a date is set for the next.
        if (!last && !leavingSet && document.activeElement !== leaving && leaving.value !== dateInput.value) leaving.value = dateInput.value
        moveFlight()
      },
      // The time bar's date set by hand: the next trip leaves then.
      dateSet() {
        if (document.activeElement === leaving) return
        leaving.value = dateInput.value
        leavingSet = true
        refuse(leaving, leavingWhy, {})
      },
      again(wait) {
        if (pending || panel.hidden || !last || performance.now() - planned < wait) return
        fly()
      },
      // A stored trip shown instead: the plan is of another trip.
      forget() {
        last = null
        rows.clear()
        results.innerHTML = ''
        wayHead.hidden = true
        const keep = container.querySelector('.sm-keep')
        if (keep) keep.hidden = true
        driveNone.hidden = true
      },

      // With the panel open, a click on a body sets the start, the next
      // the destination, and plans.
      picking() { return !panel.hidden },
      pick(body) {
        const ref = refOf(body)
        if (panel.hidden || !ref) return
        fill()
        if (next === 'from') { from.value = ref; next = 'to' }
        else if (ref !== from.value) { to.value = ref; next = 'from'; plan() }      // a second click on the start is no destination
      },

      // What the host keeps across closing and opening the map again.
      snapshot() {
        return { open: !panel.hidden, from: from.value, to: to.value, setting: { ...setting }, chosen,
          planned: last && { ends: last.ends, departure: last.departure },
          name: keepName ? keepName.value : '', by: keepBy ? keepBy.value : '' }
      },
      restore(saved) {
        if (saved && saved.open) restoreNow(saved)        // called once travel.json is read
      },
    }
    function restoreNow(saved) {
        show(true)
        if (saved.from) from.value = saved.from
        if (saved.to) to.value = saved.to
        if (saved.setting) Object.assign(setting, saved.setting)
        if (saved.chosen && DRIVES.some(([way]) => way === saved.chosen)) chosen = saved.chosen
        choose(chosen)
        if (keepName) keepName.value = saved.name
        if (keepBy) keepBy.value = saved.by
        if (saved.planned) {
          from.value = saved.planned.ends[0]
          to.value = saved.planned.ends[1]
          last = { ends: saved.planned.ends, departure: saved.planned.departure, options: [], share: shareNow(), thrust: thrustNow() }
          plan({ keepChoice: true, quiet: true })
        }
    }
  })() : null

  // ── stored trips (galaxy.json `trips`, galaxy.trips) ─────────────────
  // The stored journeys in this system, from options.trips (the export
  // the build writes; an editor's draft): listed, and one
  // chosen is drawn from its date — play to watch the ship fly it.

  const stored = options.trips ? (() => {
    const lists = () => container.querySelectorAll('.sm-stored-list')
    const toggle = container.querySelector('.sm-stored-toggle')
    const panel = container.querySelector('.sm-stored')
    let found = [], taken = []
    if (toggle) toggle.addEventListener('click', () => {
      panel.hidden = !panel.hidden
      toggle.setAttribute('aria-pressed', String(!panel.hidden))
      if (panel.hidden) clearRoute()
    })
    function line(found) {
      const option = found.option
      if (!option) return `<strong>${escape(found.name)}</strong> <span class="sm-muted">— ${escape(found.error || 'no route')}</span>`
      const check = found.check ? (found.check.in_time
        ? ` <span class="sm-in-time">${icon('check')} ${found.check.spare_days.toFixed(1)} days to spare</span>`
        : ` <span class="sm-late">${icon('close')} late by ${(-found.check.spare_days).toFixed(1)} days</span>`) : ''
      const share = found.efficiency && found.efficiency < 1 && option.name === 'own drive' ? ` ${efficiencyText(found.efficiency)}`
        : found.thrust !== undefined && option.name !== 'own drive' ? `, ${thrustShort(found.thrust)}` : ''
      return `<strong>${escape(found.name)}</strong><br><span class="sm-muted">${escape(found.start)} → ${escape(found.end)},
        ${escape(option.name)}${escape(share)}, ${duration(option.days)}, arrives ${escape(option.arrival)}</span>${check}`
        + (found.note ? `<br><span class="sm-muted"><em>${escape(found.note)}</em></span>` : '')
    }
    function render() {
      lists().forEach(holder => {
        holder.innerHTML = found.length ? '' : '<span class="sm-muted">None yet.</span>'
        for (const item of found) {
          const row = document.createElement('div')
          row.className = 'sm-stored-row'
          const show = document.createElement('button')
          show.type = 'button'
          show.className = 'sm-trip-option'
          show.innerHTML = line(item)
          if (item.option) show.addEventListener('click', () => {
            container.querySelectorAll('.sm-stored-row .sm-trip-option').forEach(r => r.classList.toggle('is-chosen', r === show))
            const departure = item.depart_at - system.epoch_year
            // The planner's last results are of another trip: gone.
            if (trip) trip.forget()
            state.playing = false
            playButton.innerHTML = icon('play')
            state.years = departure
            dateInput.value = dateText(item.depart_at)
            paceFor(item.option.days)
            drawRoute(item.option, departure, item.refs || [], true, true)
          })
          row.appendChild(show)
          if (options.tripSave) {
            const remove = document.createElement('button')
            remove.type = 'button'
            remove.className = 'sm-trip-delete'
            remove.title = `Remove the trip ${item.name}`
            remove.setAttribute('aria-label', remove.title)
            remove.innerHTML = icon('close')
            // Asked first, in the row: a kept trip
            // carries its name, way, share and arrive-by date.
            remove.addEventListener('click', () => {
              const ask = document.createElement('div')
              ask.className = 'sm-confirm'
              ask.setAttribute('role', 'alertdialog')
              ask.innerHTML = `<span>Remove the trip <strong>${escape(item.name)}</strong>? It goes with the next save.</span>`
              const yes = document.createElement('button'), no = document.createElement('button')
              yes.type = no.type = 'button'
              yes.className = 'sm-danger'
              yes.textContent = 'Remove'
              no.className = 'sm-secondary'
              no.textContent = 'Cancel'
              const buttons = document.createElement('span')
              buttons.className = 'sm-confirm-buttons'
              buttons.append(no, yes)
              ask.appendChild(buttons)
              row.replaceWith(ask)
              no.addEventListener('click', () => { ask.replaceWith(row); remove.focus() })
              yes.addEventListener('click', async () => {
                const response = await fetch(`${options.tripSave}/${encodeURIComponent(item.name)}`, { method: 'DELETE' })
                const hint = container.querySelector('.sm-stored-hint')
                if (hint) hint.textContent = response.ok ? `Removed the trip ${item.name} from the draft.` : `${item.name} could not be removed.`
                await load()
                if (response.ok && options.onChange) options.onChange()
              })
              no.focus()
            })
            row.appendChild(remove)
          }
          holder.appendChild(row)
        }
      })
      if (toggle) toggle.hidden = !found.length
    }
    async function load() {
      if (!(await lookReady)) return               // without the travel settings, no trips drawn
      try {
        const response = await fetch(options.trips, { cache: 'no-store' })
        const data = response.ok ? await response.json() : {}
        found = ((data.systems || {})[system.name]) || []
        // Every name, between the stars and in every system: Keep under one
        // of them replaces that trip, wherever it is.
        taken = [...(data.galaxy || []), ...Object.values(data.systems || {}).flat()].map(t => t.name)
      } catch (error) {
        found = []
      }
      render()
    }
    load()
    return { load, names: () => taken }
  })() : null

  // ── the jumpgate pairs, an overlay ─────────────────────────────────────
  // Toggled by ⌗, once the system has a paired jumpgate: a faint cyan line
  // between the two gates of each pair, moving with them; an early pair
  // fainter.

  const gatePairs = (() => {
    const points = (system.points_of_interest || []).filter(p => p.kind === 'jumpgate' && p.pair)
    const pairs = []
    for (const gate of points) {
      const other = points.find(p => p.id === gate.pair)
      if (other && gate.id < other.id) pairs.push([gate, other, gate.grade || other.grade || 'mature'])
    }
    if (!pairs.length) return null
    const toggle = container.querySelector('.sm-gates-toggle')
    toggle.hidden = false
    const group = new THREE.Group()
    group.visible = false
    const lines = pairs.map(([a, b, grade]) => {
      const material = new THREE.LineBasicMaterial({ transparent: true, opacity: 0 })
      lookReady.then(look => {
        if (!look) return
        material.color.set(look.gate_overlay.colour)
        material.opacity = look.gate_overlay.opacity[grade]
      })
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]), material)
      group.add(line)
      return { line, ends: [a, b] }
    })
    const show = on => {
      group.visible = on
      toggle.setAttribute('aria-pressed', String(on))
    }
    toggle.addEventListener('click', () => show(!group.visible))
    return {
      group, show,
      // Each frame, while shown: the lines to where the gates are.
      move() {
        if (!group.visible) return
        if (!group.parent && scene) scene.add(group)
        for (const { line, ends } of lines) {
          const [a, b] = ends.map(gate => bodies.find(x => x.kind === 'poi' && x.data.id === gate.id))
          if (a && b) line.geometry.setFromPoints([a.mesh.position, b.mesh.position])
        }
      },
    }
  })()

  // ── the loop ────────────────────────────────────────────────────────────

  function open(view) {
    state.view = view
    controls.maxDistance = view.frame * ZOOM_OUT
    camera.position.set(0, view.frame * 1.1, view.frame * 2.1)
    nav.place(camera.position.clone(), new THREE.Vector3())
    select(null)
  }

  function resize() {
    const w = holder.clientWidth || 1, h = holder.clientHeight || 1
    renderer.setSize(w, h)
    fx.setSize(w, h)
    labels.setSize(w, h)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }
  const observer = new ResizeObserver(() => { resize(); wake() })
  observer.observe(holder)
  // What wakes the map: input on it, a key (Esc lets go), the effects
  // toggled, a globe's texture made sharper or its relief loaded
  // (planet-look.js), and any change to the map's panels — an answer
  // arriving, a trip planned — but not the labels', which the drawing
  // itself moves.
  const WAKING = ['pointerdown', 'pointermove', 'pointerup', 'wheel', 'keydown', 'input', 'change', 'click', 'focusin']
  const onWake = () => wake()
  WAKING.forEach(type => container.addEventListener(type, onWake, { capture: true, passive: true }))
  const WAKING_WINDOW = ['keydown', 'space-effects', 'space-redraw']
  WAKING_WINDOW.forEach(type => window.addEventListener(type, onWake))
  const panels = new MutationObserver(records => {
    if (records.some(r => !labels.domElement.contains(r.target))) wake()
  })
  panels.observe(container, { subtree: true, childList: true, attributes: true, characterData: true })

  function tick(now) {
    state.frame = requestAnimationFrame(tick)
    const dt = Math.min(0.1, (now - state.last) / 1000)
    state.last = now
    if (!state.playing && !state.moving && !flight && now > state.awake) return
    if (state.playing) {
      state.years += dt * state.speed
      if (document.activeElement !== dateInput) dateInput.value = dateText(system.epoch_year + state.years)
    }
    const perPixel = (2 * Math.tan(camera.fov * RAD / 2)) / (holder.clientHeight || 1)
    // A moon fades in as its orbit grows on screen, or it would sit on its
    // planet; so do the orbits.
    const fade = (size, at) => {
      const px = size / (perPixel * camera.position.distanceTo(at))
      return Math.min(1, Math.max(0, (px - MOON_FADE[0]) / (MOON_FADE[1] - MOON_FADE[0])))
    }
    if (state.view) {
      // A zone's or a centre's label shows once what it names is large
      // enough on screen not to sit on the others.
      state.view.scaled.forEach(z => { z.label.visible = z.size / (perPixel * camera.position.distanceTo(z.anchor.position)) > LABEL_PIXELS })
      // A pulsar's beams, a turn a day of the map's clock.
      state.view.spinners.forEach(spinner => spinner.userData.spin(((state.years * 365.25) % 1) * 2 * Math.PI))
      // A black hole's disc turns with the map's clock too, a turn a day.
      state.view.holes.forEach(hole => hole.userData.update(((state.years * 365.25) % 1) * 20))
      state.view.movers.forEach(m => {
        m.object.position.copy(m.place(state.years))
        if (m.size) {
          const f = fade(m.size, m.object.position)
          m.object.visible = f > 0
          m.object.children.forEach(line => { line.material.opacity = 0.4 * f })
        }
      })
    }
    const closeness = nav.distance()
    for (const b of bodies) {
      if (b.orbits) {
        const ratio = b.orbitSize > 0 ? closeness / b.orbitSize : Infinity
        const f = b === state.selected ? 1
          : Math.min(1, Math.max(0, Math.log(ratio / ORBIT_FADE[1]) / Math.log(ORBIT_FADE[0] / ORBIT_FADE[1])))
        b.orbits.forEach(line => { line.visible = f > 0; line.material.opacity = line.userData.opacity * f })
      }
      b.mesh.position.copy(b.place(state.years))
      // Its atmosphere lit from its star's side (planet-look.js).
      if (b.sun && b.mesh.userData.setLight) b.mesh.userData.setLight(b.sun(state.years))
      // The name sits above the body's top — a star's above its glow —
      // whichever way a tilted planet is turned, not at its centre, which a
      // large disc would cover.
      if (b.label && b.label.parent === b.mesh) {
        b.label.position.copy(UP).multiplyScalar(b.kind === 'star' ? 1.35 : 1)
          .applyQuaternion(b.mesh.quaternion.clone().invert())
      }
      if (b.size) {
        const f = b === state.selected ? 1 : fade(b.size, b.mesh.position)
        b.mesh.visible = b.label.visible = f > 0
        b.mesh.material.opacity = f
        b.label.element.style.opacity = f
      }
      const floor = MIN_PIXELS * perPixel * camera.position.distanceTo(b.mesh.position)
      b.mesh.scale.setScalar(b.fixedSize ? Math.max(b.radius, floor) : Math.max(b.radius, b.kind === 'poi' ? floor * 1.2 : floor))
    }
    castShadows()
    declutter()
    if (state.selected) {
      for (const marker of extras.filter(o => o.userData && o.userData.point)) {
        marker.position.copy(lagrange(state.selected, state.years, marker.userData.point, state.view))
        marker.scale.setScalar(4 * perPixel * camera.position.distanceTo(marker.position))
        marker.lookAt(camera.position)
      }
      if (state.playing && (state.selected.kind === 'planet' || state.selected.kind === 'moon')) detail.innerHTML = describe(state.selected)
    }
    if (trip) trip.follow()
    else moveFlight()
    if (gatePairs) gatePairs.move()                       // a site: stored trips only
    state.moving = nav.update(now)
    fx.render()
    labels.render(scene, camera)
  }

  /* Who shades whom (planet-look.js setShadows), worked out true to scale
   *: every planet and moon may shade every other, a moon its
   * planet as an inner planet in transit dims an outer one. Planets, moons
   * and moon orbits are drawn enlarged against the planets' orbits by one
   * factor (kmScale), so around each body a frame true to scale is its
   * drawn place plus the true offsets in kmScale units: a moon's offset
   * from its planet as drawn, a planet's (and a star's) from another
   * planet's the drawn one times the enlargement; true radii, the stars'
   * too. Those whose discs come nearest the brightest star's first.
   *
   * Worked out again only when the date changed or another view opened:
   * the shadows stand in the world, the globes put them in view space as
   * they are drawn.
   * The lists are built once per view and the vectors reused: no garbage
   * per frame. */
  const shade = { view: null, years: NaN }
  const toSun = new THREE.Vector3(), offset = new THREE.Vector3(), shift = new THREE.Vector3(), across = new THREE.Vector3()
  const byScore = (x, y) => x.score - y.score
  function shadeList(view) {
    const stars = bodies.filter(b => b.kind === 'star')
    const planetOf = new Map(bodies.filter(b => b.kind === 'planet').map(b => [b.data, b]))
    const placed = bodies.filter(b => b.kind === 'star' || b.kind === 'planet' || b.kind === 'moon')
      .map(b => ({ b, host: b.kind === 'moon' ? planetOf.get(b.planet) : b, at: new THREE.Vector3() }))
    const casters = bodies.filter(b => (b.kind === 'planet' || b.kind === 'moon') && b.radius > 0)
    return {
      view, years: NaN, stars, placed, enlarged: new Map(placed.map(p => [p.b, p.at])),
      casters, receivers: casters.filter(b => b.mesh.userData.setShadows),
      suns: stars.map(b => b.mesh.position),
      trueSuns: stars.map(s => ({ centre: new THREE.Vector3(), radius: (s.data.radius || 0) * view.kmScale })),
      pool: casters.map(() => ({ score: 0, centre: new THREE.Vector3(), radius: 0 })),
      ranked: [],
      given: null,                       // what setShadows is handed, the same object each time
    }
  }
  function castShadows() {
    const view = state.view
    if (!view) return
    if (shade.view !== view) {
      Object.assign(shade, shadeList(view))
      shade.given = { suns: shade.suns, occluders: shade.ranked, trueSuns: shade.trueSuns }
    }
    if (!shade.stars.length || shade.years === state.years) return
    shade.years = state.years
    const factor = view.enlargement
    // Where each body stands in a frame the enlargement applies to all of it.
    for (const p of shade.placed) p.at.copy(p.host.mesh.position).multiplyScalar(factor).add(p.b.mesh.position).sub(p.host.mesh.position)
    const enlarged = shade.enlarged
    for (const b of shade.receivers) {
      shift.copy(b.mesh.position).sub(enlarged.get(b))
      for (let k = 0; k < shade.stars.length; k++) shade.trueSuns[k].centre.copy(enlarged.get(shade.stars[k])).add(shift)
      offset.copy(shade.trueSuns[0].centre).sub(b.mesh.position)
      const sunDistance = offset.length()
      toSun.copy(offset).normalize()
      const sunAngle = shade.trueSuns[0].radius / sunDistance
      const ranked = shade.ranked
      ranked.length = 0
      for (const c of shade.casters) {
        if (c === b) continue
        const entry = shade.pool[ranked.length]
        entry.centre.copy(enlarged.get(c)).add(shift)
        offset.copy(entry.centre).sub(b.mesh.position)
        const t = offset.dot(toSun)
        if (t <= 0 || t >= sunDistance) continue          // behind it, or beyond the star
        const apart = Math.atan2(across.copy(offset).cross(toSun).length(), t)
        entry.score = apart - Math.asin(Math.min(1, c.radius / offset.length())) - sunAngle
        entry.radius = c.radius
        ranked.push(entry)
      }
      ranked.sort(byScore)
      b.mesh.userData.setShadows(shade.given)
    }
  }

  /* Names that would print over one another: the more important kept — the
   * selected body, then stars, planets, points of interest, moons — the
   * others hidden until zooming in parts them.
   * Boxes estimated from the text's length, not measured: no layout read
   * every frame. */
  const RANK = { star: 0, planet: 1, poi: 2, moon: 3 }
  function declutter() {
    const w = holder.clientWidth || 1, h = holder.clientHeight || 1
    const placed = []
    // A moon's name is shown or not by its fade, set this frame; the rest start shown.
    bodies.forEach(b => { if (b.label && !b.size) b.label.visible = b.mesh.visible })
    const order = bodies.filter(b => b.label && b.label.visible)
      .sort((a, b) => (b === state.selected) - (a === state.selected) || RANK[a.kind] - RANK[b.kind])
    for (const b of order) {
      const p = b.mesh.position.clone().project(camera)
      if (p.z > 1) continue
      const x = (p.x + 1) / 2 * w, y = (1 - p.y) / 2 * h
      const half = (b.label.element.textContent.length * 6 + 8) / 2
      const box = [x - half, y - 22, x + half, y - 6]
      const clash = placed.some(o => box[0] < o[2] && box[2] > o[0] && box[1] < o[3] && box[3] > o[1])
      b.label.visible = !clash
      if (!clash) placed.push(box)
    }
  }

  resize()
  open(systemView())
  wake()
  state.frame = requestAnimationFrame(tick)
  // Arrived for a body (options.focus, its name): flown to, as a search finds it.
  const arrival = options.focus ? bodies.find(b => titleOf(b) === options.focus) : null
  if (arrival) goTo(arrival)

  return {
    destroy() {
      cancelAnimationFrame(state.frame)
      observer.disconnect()
      panels.disconnect()
      WAKING.forEach(type => container.removeEventListener(type, onWake, { capture: true }))
      WAKING_WINDOW.forEach(type => window.removeEventListener(type, onWake))
      detachPointer()
      search.dispose()
      nav.dispose()
      removeQuality()
      removeColours()
      removeFold()
      skyButtons.remove()
      removeProcedural()
      fx.dispose()
      if (scene) dispose(scene)
      releaseTextures()
      renderer.dispose()
      renderer.forceContextLoss()   // or the context outlives the page: browsers cap them at about 16
      container.innerHTML = ''
      container.classList.remove('system-map')
    },
    setDate(absolute) {
      state.years = absolute - system.epoch_year
      dateInput.value = dateText(absolute)
      wake()
    },
    // How the map is looked at — date, speed, camera, selection, overlay,
    // the trip panel — for the host to give back when it opens the same
    // system again.
    snapshot() {
      return {
        years: state.years, speed: speedSelect.value, playing: state.playing,
        camera: camera.position.toArray(), target: controls.target.toArray(),
        selected: state.selected && refOf(state.selected), follow: nav.following && refOf(nav.following),
        gates: !!(gatePairs && gatePairs.group.visible), trip: trip && trip.snapshot(),
      }
    },
    restore(saved) {
      if (!saved) return
      wake()
      state.years = saved.years
      dateInput.value = dateText(system.epoch_year + saved.years)
      speedSelect.value = saved.speed
      state.speed = SPEEDS[+saved.speed][1]
      state.playing = saved.playing
      playButton.innerHTML = icon(state.playing ? 'pause' : 'play')
      camera.position.fromArray(saved.camera)
      controls.target.fromArray(saved.target)
      controls.update()
      const find = ref => (ref ? bodies.find(b => refOf(b) === ref) || null : null)
      const followed = find(saved.follow)
      if (followed) nav.follow(() => followed.mesh.position, followed, () => followed.radius * 1.5)
      // Once the bodies stand where the date puts them: its details say how far it is now.
      requestAnimationFrame(() => select(find(saved.selected)))
      if (gatePairs) gatePairs.show(saved.gates)
      if (trip) lookReady.then(look => { if (look) trip.restore(saved.trip) })
    },
  }
}

// The galaxy map's choice for the procedural layer (galaxy-map.js, ⁂).
const PROCEDURAL_KEY = 'galaxy-procedural'

function proceduralChosen() {
  try { return localStorage.getItem(PROCEDURAL_KEY) === 'shown' } catch { return false }
}

// procedural.json as sky stars, fetched once a page.
const proceduralSkies = new Map()
function proceduralSky(url) {
  if (!proceduralSkies.has(url)) {
    proceduralSkies.set(url, fetch(url).then(r => (r.ok ? r.json() : null)).catch(() => null)
      .then(data => ({
        stars: ((data && data.systems) || []).map(d => ({
          name: d.name, spectral_class: d.spectral_class, at: [d.x, d.y, d.z], abs_mag: d.abs_mag, procedural: true,
        })),
        // The layer's nebulae (galaxy.procedural.nebulae), as the sky takes them.
        nebulae: ((data && data.nebulae) || []).map(n => ({
          name: n.name, kind: n.kind, colour: n.colour, at: [n.x, n.y, n.z], size: n.size,
        })),
      })))
  }
  return proceduralSkies.get(url)
}

function dispose(scene) {
  scene.traverse(o => {
    if (o.geometry) o.geometry.dispose()
    if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => m.dispose())
    if (o.element) o.element.remove()
  })
}

function fmt(n) {
  return Number(n).toLocaleString('en', { maximumFractionDigits: 0 })
}

function escape(text) {
  return String(text ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
}
