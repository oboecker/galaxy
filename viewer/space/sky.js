/* The sky behind every 3D map: distant stars at infinity —
 * turning with the view's direction, never coming closer — drawn first,
 * under everything, never picked nor named. Faint, so that no point of it
 * reads as a star of the map, and below the light effects' bloom threshold.
 * A band of them, where `band` is given: the galaxy's own disc as seen from
 * within it — where `galaxy` says how it lies (galaxy.celestial.galaxy_from:
 * its pole and the way to its centre in the system's own axes),
 * there and densest toward the centre; else tilted somewhere at random.
 *
 *   scene.add(createSky({ seed: 'Sol', band: true, galaxy: system.galaxy }))
 *
 * With `system` (galaxy.systemmap: its `at`, `axes`) and `stars` (every
 * system's name, class, `at` and `abs_mag`: galaxy.systemmap.sky_stars),
 * the galaxy's own stars too, each in its true direction from the system
 * and as bright as it shows from there: from Sol the real
 * constellations; one too faint to see still a faint point, to show where
 * it stands. Each named beside its point, small and pale;
 * a star with `procedural` (galaxy.procedural) only where the eye sees it.
 * With `galaxy`, the galactic centre is named too, where the band is densest.
 *
 *   scene.add(createSky({ seed: system.name, band: true, galaxy: system.galaxy, system, stars }))
 *
 * With `glow` (galaxy.procedural.glow, fetched by galaxy-glow.js loadGlow)
 * and the system's `at`, the band is the galaxy as seen from there: its light along every line of sight, a faint glow under the
 * band's points, which fall where it is brightest — not the same ring in
 * every sky. Without it, a band of the same make everywhere, only turned.
 *
 * `constellations` (galaxy.constellations: figures of lines through stars by
 * name) draws their lines among them. Names and lines are shown or hidden
 * by the viewer's choice, kept in the browser; skyToggles adds the buttons.
 */
import * as THREE from 'three'
import { starColour } from './star-colours.js'
import { bandLight, LATITUDES, LONGITUDES, latitude } from './galaxy-glow.js'
import { toggleIcon } from './icons.js'

// A star's colour by its temperature, roughly: blue-white to orange.
const TINTS = [[0.75, 0.82, 1.0], [0.9, 0.93, 1.0], [1.0, 1.0, 1.0], [1.0, 0.95, 0.85], [1.0, 0.85, 0.65], [1.0, 0.72, 0.5]]

const vertexShader = `
  attribute vec3 tint;
  attribute float size;
  uniform float pixelRatio;
  varying vec3 vTint;
  void main() {
    vTint = tint;
    // The direction only, as the view turns it: at infinity, at the far
    // end of the depth range whatever the camera's near and far planes.
    vec4 at = projectionMatrix * vec4(mat3(viewMatrix) * position, 1.0);
    gl_Position = at.xyww;
    gl_Position.z = at.w * 0.999999;
    gl_PointSize = size * pixelRatio;
  }`

const fragmentShader = `
  varying vec3 vTint;
  void main() {
    float r = length(gl_PointCoord * 2.0 - 1.0);
    if (r > 1.0) discard;
    gl_FragColor = vec4(vTint * (1.0 - r * r), 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }`

function seeded(text) {
  let s = 0
  for (const c of String(text)) s = (Math.imul(s, 31) + c.charCodeAt(0)) >>> 0
  return () => {
    s = (s + 0x6D2B79F5) >>> 0
    let t = Math.imul(s ^ (s >>> 15), 1 | s)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// Apparent magnitude to light: the brightest (about −1.5, Sirius from Earth)
// just under the bloom threshold; the naked eye's limit, 6.5, faint; past
// it a floor, so that every star shows where it stands.
const BRIGHTEST = -1.5, FAINTEST = 6.5, FLOOR = 0.1, CEILING = 0.95
const LY_PER_10_PC = 32.6156

/* The galaxy's stars as `system` sees them: direction in the map's axes,
 * light, size and colour — itself and Sol's own sun left out. */
function starsSeen(system, stars) {
  const axes = system.axes                          // system → frame; frame → system is its transpose
  const out = []
  for (const star of stars) {
    if (star.name === system.name || star.abs_mag == null || !star.at) continue
    const d = [star.at[0] - system.at[0], star.at[1] - system.at[1], star.at[2] - system.at[2]]
    const ly = Math.hypot(d[0], d[1], d[2])
    if (!(ly > 0)) continue
    const own = axes ? [0, 1, 2].map(i => (axes[0][i] * d[0] + axes[1][i] * d[1] + axes[2][i] * d[2]) / ly)
      : d.map(v => v / ly)
    const mag = star.abs_mag + 5 * Math.log10(ly / LY_PER_10_PC)
    const share = Math.min(1, Math.max(0, (FAINTEST - mag) / (FAINTEST - BRIGHTEST)))
    out.push({
      name: star.name,
      // A procedural system's star (galaxy.procedural, thousands of them)
      // named only where the eye would see it: a name is a sprite of its own.
      named: !star.procedural || mag <= FAINTEST,
      direction: scene(own).normalize(),
      light: mag > FAINTEST ? FLOOR : FLOOR + (CEILING - FLOOR) * share,
      size: 1.4 + 3 * share,
      colour: new THREE.Color(starColour(star.spectral_class ?? (star.star && star.star.spectral_class), 'physical')),
    })
  }
  return out
}

/* `count` stars, `brightness` the brightest's (kept under 1: no bloom),
 * `seed` for the same sky each time, `band` a share of them along a tilted
 * great circle, a soft scatter about it. */
// A system's x, y, z (its plane x–y) as the maps place them: x, height, −y.
const scene = p => new THREE.Vector3(p[0], p[2], -p[1])

export function createSky({ count = 4000, brightness = 0.7, seed = 'sky', band = false, galaxy = null,
  system = null, stars = null, constellations = null, glow = null, nebulae = null } = {}) {
  const rand = seeded(seed)
  const known = system && system.at && stars ? starsSeen(system, stars) : []
  // Under the galaxy's own stars the made-up ones step back: dimmer, so the
  // constellations read.
  if (known.length) brightness *= 0.45
  const total = count + known.length
  const at = new Float32Array(total * 3), tint = new Float32Array(total * 3), size = new Float32Array(total)
  // A system without a plane of its own: its axes are the frame's, the
  // galaxy's pole straight up, its centre back the way from the origin.
  if (!galaxy && band && system && system.at && Math.hypot(system.at[0], system.at[1]) > 0) {
    const r = Math.hypot(system.at[0], system.at[1], system.at[2])
    galaxy = { pole: [0, 0, 1], centre: system.at.map(v => -v / r) }
  }
  // The band's plane: the galaxy's, or its pole somewhere tilted from the map's up.
  const random = new THREE.Vector3(rand() - 0.5, 0.6 + rand(), rand() - 0.5).normalize()
  const pole = galaxy ? scene(galaxy.pole).normalize() : random
  // `across` points to the centre, laid into the band.
  const across = galaxy ? scene(galaxy.centre).addScaledVector(pole, -pole.dot(scene(galaxy.centre))).normalize()
    : new THREE.Vector3(1, 0, 0).cross(pole).normalize()
  const along = pole.clone().cross(across)
  const v = new THREE.Vector3()
  // The galaxy's light from where the system stands, when known: the band's
  // points drawn by it, cell by cell of its grid.
  const seen = band && glow && galaxy && system && system.at ? bandSeen(glow, system.at) : null
  for (let k = 0; k < count; k++) {
    if (seen && rand() < 0.45) {
      seen.direction(rand(), rand(), rand(), v)
      v.copy(across).multiplyScalar(v.x).addScaledVector(along, v.y).addScaledVector(pole, v.z).normalize()
    } else if (band && rand() < 0.45) {
      // Within the band: round its circle, a little off it, thicker near its
      // middle; a third of it crowding toward the galaxy's centre, wider there.
      const bulge = galaxy && rand() < 0.35
      const a = bulge ? (rand() + rand() + rand() - 1.5) * 0.9 : rand() * 2 * Math.PI
      const off = (rand() + rand() + rand() - 1.5) * (bulge ? 0.3 : 0.18)
      v.copy(across).multiplyScalar(Math.cos(a)).addScaledVector(along, Math.sin(a)).addScaledVector(pole, off).normalize()
    } else {
      const z = rand() * 2 - 1, a = rand() * 2 * Math.PI, r = Math.sqrt(1 - z * z)
      v.set(r * Math.cos(a), z, r * Math.sin(a))
    }
    at.set([v.x, v.y, v.z], k * 3)
    // Most faint, a few bright: brightness falls off steeply.
    const light = brightness * (0.15 + 0.85 * rand() ** 4)
    const c = TINTS[Math.floor(rand() * TINTS.length)]
    tint.set([c[0] * light, c[1] * light, c[2] * light], k * 3)
    size[k] = 1.2 + 1.6 * rand() ** 3
  }
  known.forEach((star, j) => {
    const k = count + j
    at.set([star.direction.x, star.direction.y, star.direction.z], k * 3)
    tint.set([star.colour.r * star.light, star.colour.g * star.light, star.colour.b * star.light], k * 3)
    size[k] = star.size
  })
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(at, 3))
  geometry.setAttribute('tint', new THREE.BufferAttribute(tint, 3))
  geometry.setAttribute('size', new THREE.BufferAttribute(size, 1))
  const material = new THREE.ShaderMaterial({
    vertexShader, fragmentShader, uniforms: { pixelRatio: { value: 1 } },
    // Among the opaque, drawn first by its order: as transparent it would be
    // drawn after every planet, and over them, since it tests no depth.
    depthTest: false, depthWrite: false, transparent: false, blending: THREE.AdditiveBlending,
  })
  const sky = new THREE.Points(geometry, material)
  sky.frustumCulled = false
  sky.renderOrder = -100                // first, under everything
  sky.raycast = () => {}                // never picked
  sky.onBeforeRender = renderer => { material.uniforms.pixelRatio.value = renderer.getPixelRatio() }
  sky.name = 'sky'
  if (seen) sky.add(glowMesh(seen, across, along, pole, known.length ? 0.45 : 1))
  if (system && system.at && nebulae && nebulae.length) {
    for (const cloud of nebulaSprites(nebulaeSeen(system, nebulae), seeded(seed + ':nebulae'))) sky.add(cloud)
  }
  const names = new THREE.Group()
  names.name = 'sky-names'
  known.forEach(star => { if (star.named) names.add(nameAt(star.name, star.direction)) })
  // The galactic centre where the band is densest, named as the galaxy map
  // names it: only where the sky knows the way there.
  if (galaxy && galaxy.centre) names.add(nameAt('Galactic Center', scene(galaxy.centre).normalize()))
  sky.add(names)
  const lines = figures(known, constellations)
  if (lines) sky.add(lines)
  showChoices(sky)
  return sky
}

// ── nebulae in the sky ─────────
// Each seen from the system at its angular size: soft sprites round its
// direction, as on the galaxy map; from inside one, a haze of its colour
// over the whole sky. Too small to see (under a tenth of a degree): none.

const NEBULA_LEAST = 0.0018            // radians: a tenth of a degree across
// A kind's colour where a nebula has none of its own (galaxy.nebulae.KINDS).
const NEBULA_COLOURS = { emission: '#ff5a85', reflection: '#7fa7ff', dark: '#3a2f27', planetary: '#4fd6c4',
  remnant: '#ffa65c' }

function nebulaeSeen(system, nebulae) {
  const axes = system.axes
  const out = []
  for (const n of nebulae) {
    const d = [n.at[0] - system.at[0], n.at[1] - system.at[1], n.at[2] - system.at[2]]
    const ly = Math.hypot(d[0], d[1], d[2])
    const largest = Math.max(...n.size), mean = (n.size[0] + n.size[1] + n.size[2]) / 3
    const inside = ly < mean
    const angle = inside ? Math.PI : Math.atan2(largest, ly)
    if (!inside && angle < NEBULA_LEAST) continue
    const own = ly > 0 ? (axes ? [0, 1, 2].map(i => (axes[0][i] * d[0] + axes[1][i] * d[1] + axes[2][i] * d[2]) / ly)
      : d.map(v => v / ly)) : [1, 0, 0]
    out.push({ name: n.name, kind: n.kind, colour: new THREE.Color(n.colour || NEBULA_COLOURS[n.kind] || NEBULA_COLOURS.emission),
      direction: scene(own).normalize(), angle, inside })
  }
  return out
}

const nebulaVertex = `
  attribute vec3 tint; attribute float angle; attribute float seed; attribute float weight;
  uniform float pxPerRadian;
  varying vec3 vTint; varying float vSeed; varying float vWeight;
  void main() {
    vTint = tint; vSeed = seed; vWeight = weight;
    vec4 at = projectionMatrix * vec4(mat3(viewMatrix) * position, 1.0);
    gl_Position = at.xyww;
    gl_Position.z = at.w * 0.999999;
    gl_PointSize = clamp(angle * pxPerRadian, 2.0, 2048.0);
  }`

const nebulaFragment = dark => `
  varying vec3 vTint; varying float vSeed; varying float vWeight;
  float hash3(vec3 p){ p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
  float noise3(vec3 x){ vec3 i = floor(x), f = fract(x); f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(hash3(i), hash3(i + vec3(1,0,0)), f.x), mix(hash3(i + vec3(0,1,0)), hash3(i + vec3(1,1,0)), f.x), f.y),
               mix(mix(hash3(i + vec3(0,0,1)), hash3(i + vec3(1,0,1)), f.x), mix(hash3(i + vec3(0,1,1)), hash3(i + vec3(1,1,1)), f.x), f.y), f.z); }
  float fbm3(vec3 p){ float v = 0.0, a = 0.5; for (int i = 0; i < 4; i++) { v += a * noise3(p); p = p * 2.02 + 3.1; a *= 0.5; } return v; }
  void main() {
    vec2 c = gl_PointCoord * 2.0 - 1.0; float r = length(c); if (r > 1.0) discard;
    float a = pow(1.0 - r, 2.0) * smoothstep(0.38, 0.78, fbm3(vec3(c * 2.6, vSeed))) * vWeight;
    gl_FragColor = vec4(vTint, a * ${dark ? '0.7' : '0.35'});
  }`

/* Two clouds of sprites on the sky's sphere: the glowing nebulae added to it,
 * the dark ones over it. */
function nebulaSprites(seen, rand) {
  const out = []
  for (const dark of [false, true]) {
    const at = [], tint = [], angle = [], seed = [], weight = []
    for (const n of seen.filter(s => (s.kind === 'dark') === dark)) {
      // A basis round its direction, to scatter the sprites across its disc.
      const u = new THREE.Vector3(0, 1, 0).cross(n.direction)
      if (u.lengthSq() < 1e-6) u.set(1, 0, 0)
      u.normalize()
      const w = n.direction.clone().cross(u)
      const count = n.inside ? 160 : 50
      for (let k = 0; k < count; k++) {
        const v = new THREE.Vector3()
        if (n.inside) {
          const z = rand() * 2 - 1, a = rand() * 2 * Math.PI, r = Math.sqrt(1 - z * z)
          v.set(r * Math.cos(a), z, r * Math.sin(a))
        } else {
          const g = () => (rand() + rand() + rand() - 1.5) * 0.8
          v.copy(n.direction).addScaledVector(u, g() * n.angle).addScaledVector(w, g() * n.angle).normalize()
        }
        at.push(v.x, v.y, v.z)
        tint.push(n.colour.r, n.colour.g, n.colour.b)
        angle.push(n.inside ? 0.5 + rand() * 0.4 : n.angle * (0.7 + rand() * 0.7))
        seed.push(rand() * 100)
        weight.push(n.inside ? 0.25 : 0.6 + rand() * 0.6)
      }
    }
    if (!at.length) continue
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(at, 3))
    geometry.setAttribute('tint', new THREE.Float32BufferAttribute(tint, 3))
    geometry.setAttribute('angle', new THREE.Float32BufferAttribute(angle, 1))
    geometry.setAttribute('seed', new THREE.Float32BufferAttribute(seed, 1))
    geometry.setAttribute('weight', new THREE.Float32BufferAttribute(weight, 1))
    const material = new THREE.ShaderMaterial({
      vertexShader: nebulaVertex, fragmentShader: nebulaFragment(dark), uniforms: { pxPerRadian: { value: 500 } },
      depthTest: false, depthWrite: false, transparent: true,
      blending: dark ? THREE.NormalBlending : THREE.AdditiveBlending,
    })
    const cloud = new THREE.Points(geometry, material)
    cloud.name = dark ? 'sky-nebulae-dark' : 'sky-nebulae'
    cloud.frustumCulled = false
    cloud.raycast = () => {}
    // Over the sky's stars, under everything near (the sky draws first).
    cloud.renderOrder = -99
    const size = new THREE.Vector2()
    cloud.onBeforeRender = (renderer, _scene, camera) => {
      renderer.getDrawingBufferSize(size)
      material.uniforms.pxPerRadian.value = size.y / 2 * camera.projectionMatrix.elements[5]
    }
    out.push(cloud)
  }
  return out
}

// ── the band as the system sees it (galaxy-glow.js) ─────────────────────────
// Its light to the glow's brightness: (1 − e^(−light / GLOW_REFERENCE))²,
// up to GLOW_BRIGHTEST — about the band's brightest from Sol; kept faint,
// under the points and far under the light effects' threshold. Squared:
// encoded for the screen, the faint light off the band, a thirtieth of it,
// came out a quarter as bright — a grey haze over the whole sky.
const GLOW_REFERENCE = 6e-5
const GLOW_BRIGHTEST = 0.05
const GLOW_TINT = [1.0, 0.92, 0.8]

/* The light from `at`, and a direction drawn by it: the cell by `u`, a place
 * in it by `a`, `b` — into `out` as (across, along, pole) components. */
function bandSeen(glow, at) {
  const { light } = bandLight(glow, at)
  const cells = LATITUDES * LONGITUDES
  const total = new Float64Array(cells)
  let sum = 0
  for (let i = 0; i < LATITUDES; i++) {
    const b0 = latitude(i), b1 = latitude(i + 1)
    const area = Math.sin(b1) - Math.sin(b0)         // a cell's solid angle, but for 2π / LONGITUDES
    for (let j = 0; j < LONGITUDES; j++) {
      const j1 = (j + 1) % LONGITUDES
      const mean = (light[i * LONGITUDES + j] + light[i * LONGITUDES + j1]
        + light[(i + 1) * LONGITUDES + j] + light[(i + 1) * LONGITUDES + j1]) / 4
      sum += mean * area
      total[i * LONGITUDES + j] = sum
    }
  }
  return {
    light,
    direction(u, a, b, out) {
      const goal = u * sum
      let lo = 0, hi = cells - 1
      while (lo < hi) { const mid = (lo + hi) >> 1; if (total[mid] < goal) lo = mid + 1; else hi = mid }
      const i = Math.floor(lo / LONGITUDES), j = lo % LONGITUDES
      const lat = Math.asin(Math.sin(latitude(i)) + a * (Math.sin(latitude(i + 1)) - Math.sin(latitude(i))))
      const lon = 2 * Math.PI * (j + b) / LONGITUDES
      return out.set(Math.cos(lat) * Math.cos(lon), Math.cos(lat) * Math.sin(lon), Math.sin(lat))
    },
  }
}

/* The glow itself: a sphere at infinity through the grid's nodes, each as
 * bright as the light there. */
function glowMesh(seen, across, along, pole, dim) {
  const nodes = (LATITUDES + 1) * LONGITUDES
  const at = new Float32Array(nodes * 3), tint = new Float32Array(nodes * 3)
  const v = new THREE.Vector3()
  for (let i = 0; i <= LATITUDES; i++) {
    const b = latitude(i)
    for (let j = 0; j < LONGITUDES; j++) {
      const l = 2 * Math.PI * j / LONGITUDES, n = i * LONGITUDES + j
      v.copy(across).multiplyScalar(Math.cos(b) * Math.cos(l)).addScaledVector(along, Math.cos(b) * Math.sin(l))
        .addScaledVector(pole, Math.sin(b)).normalize()
      at.set([v.x, v.y, v.z], n * 3)
      const shine = dim * GLOW_BRIGHTEST * (1 - Math.exp(-seen.light[n] / GLOW_REFERENCE)) ** 2
      tint.set(GLOW_TINT.map(c => c * shine), n * 3)
    }
  }
  const index = []
  for (let i = 0; i < LATITUDES; i++) {
    for (let j = 0; j < LONGITUDES; j++) {
      const a = i * LONGITUDES + j, b = i * LONGITUDES + (j + 1) % LONGITUDES
      index.push(a, b, a + LONGITUDES, b, b + LONGITUDES, a + LONGITUDES)
    }
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(at, 3))
  geometry.setAttribute('tint', new THREE.BufferAttribute(tint, 3))
  geometry.setIndex(index)
  const material = new THREE.ShaderMaterial({
    vertexShader: glowVertexShader, fragmentShader: glowFragmentShader,
    depthTest: false, depthWrite: false, transparent: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
  })
  const mesh = new THREE.Mesh(geometry, material)
  mesh.frustumCulled = false
  mesh.renderOrder = -101               // under the sky's points
  mesh.raycast = () => {}
  mesh.name = 'sky-glow'
  return mesh
}

const glowVertexShader = `
  attribute vec3 tint;
  varying vec3 vTint;
  void main() {
    vTint = tint;
    vec4 at = projectionMatrix * vec4(mat3(viewMatrix) * position, 1.0);
    gl_Position = at.xyww;
    gl_Position.z = at.w * 0.999999;
  }`

const glowFragmentShader = `
  varying vec3 vTint;
  void main() {
    gl_FragColor = vec4(vTint, 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }`

// ── what the viewer shows of it: the stars' names, the figures' lines ──────
const CHOICES = { names: 'space-sky-names', lines: 'space-sky-lines' }

function chosen(what) {
  try { return localStorage.getItem(CHOICES[what]) !== 'hidden' } catch { return true }
}

function showChoices(sky) {
  const names = sky.getObjectByName('sky-names'), lines = sky.getObjectByName('sky-lines')
  if (names) names.visible = chosen('names')
  if (lines) lines.visible = chosen('lines')
}

/* Two buttons in `holder`: the stars' names, the constellations' lines —
 * the latter only where `root()` (the scene) has a sky with figures. Each
 * choice kept for every map. `changed()` after a toggle, to redraw;
 * `kind` the buttons' classes, the maps' by default. */
export function skyToggles(holder, root, changed = () => {}, kind = 'space-tool') {
  const make = (what, name, on, off) => {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = `${kind} sky-toggle`
    toggleIcon(button, name)
    const show = () => {
      button.setAttribute('aria-pressed', String(chosen(what)))
      button.title = chosen(what) ? off : on
    }
    show()
    button.addEventListener('click', () => {
      try { localStorage.setItem(CHOICES[what], chosen(what) ? 'hidden' : 'shown') } catch { /* this page only */ }
      show()
      const sky = root() && root().getObjectByName('sky')
      if (sky) showChoices(sky)
      changed()
    })
    holder.appendChild(button)
    return button
  }
  const names = make('names', 'font-size', "Name the sky's stars", "Hide the sky's star names")
  const lines = make('lines', 'share', "Draw the constellations", "Hide the constellations")
  const update = () => { const sky = root() && root().getObjectByName('sky'); lines.hidden = !(sky && sky.getObjectByName('sky-lines')) }
  update()
  return { update, remove() { names.remove(); lines.remove() } }
}

// ── the constellations' lines ──────────────────────────────────────────────
const LINE_COLOUR = 0x8fa6c8, LINE_OPACITY = 0.35

/* The figures' lines among the stars seen (by system name), at infinity as
 * the names are; null without any. */
function figures(known, constellations) {
  if (!constellations || !constellations.length) return null
  const where = new Map(known.map(star => [star.name, star.direction]))
  const points = []
  for (const figure of constellations) {
    for (const chain of figure.lines || []) {
      for (let k = 1; k < chain.length; k++) {
        const a = where.get(chain[k - 1]), b = where.get(chain[k])
        if (a && b) points.push(a.x, a.y, a.z, b.x, b.y, b.z)
      }
    }
  }
  if (!points.length) return null
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3))
  const lines = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({
    color: LINE_COLOUR, transparent: true, opacity: LINE_OPACITY, depthTest: true, depthWrite: false, toneMapped: false,
  }))
  lines.name = 'sky-lines'
  lines.renderOrder = -98
  lines.frustumCulled = false
  lines.raycast = () => {}
  lines.onBeforeRender = (_renderer, _scene, camera) => {
    eye.setFromMatrixPosition(camera.matrixWorld)
    lines.matrixWorld.compose(eye, unit, span.setScalar(camera.far * 0.9))
  }
  return lines
}

// ── the names of the galaxy's stars ────────────────────────────────────────
const NAME_PIXELS = 11                  // the text's height on screen
const NAME_COLOUR = 'rgba(190, 205, 230, 0.5)'
const spot = new THREE.Vector3(), eye = new THREE.Vector3(), unit = new THREE.Quaternion(), span = new THREE.Vector3(), seen = new THREE.Vector2()

/* A star's name at infinity in `direction`, as the sky's points are: placed
 * each frame far out the way it looks — beyond everything of the map, so
 * that a planet hides it (transparent, it is drawn after the planets, whatever
 * its order) — at a fixed size on screen, left-aligned beside the point. */
function nameAt(name, direction) {
  const ratio = 2
  const canvas = document.createElement('canvas'), pen = canvas.getContext('2d')
  const font = `${NAME_PIXELS * ratio}px system-ui, sans-serif`
  pen.font = font
  canvas.width = Math.ceil(pen.measureText(name).width) + 4
  canvas.height = Math.ceil(NAME_PIXELS * ratio * 1.3)
  pen.font = font
  pen.fillStyle = NAME_COLOUR
  pen.textBaseline = 'middle'
  pen.fillText(name, 2, canvas.height / 2)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  const label = new THREE.Sprite(new THREE.SpriteMaterial({
    map: texture, sizeAttenuation: false, depthTest: true, depthWrite: false, transparent: true, toneMapped: false,
  }))
  label.material.addEventListener('dispose', () => texture.dispose())     // a material lets its map be
  label.center.set(-0.08, 0.5)           // to the right of the point, a little apart
  label.renderOrder = -99
  label.frustumCulled = false
  label.raycast = () => {}
  const aspect = canvas.width / canvas.height
  label.onBeforeRender = (renderer, _scene, camera) => {
    renderer.getSize(seen)
    // Without size attenuation a sprite's height on screen is its scale
    // times the projection's vertical factor, in units of half the view.
    const height = (2 * NAME_PIXELS * 1.3 / (seen.y || 1)) / camera.projectionMatrix.elements[5]
    eye.setFromMatrixPosition(camera.matrixWorld)
    spot.copy(direction).multiplyScalar(camera.far * 0.9).add(eye)
    label.matrixWorld.compose(spot, unit, span.set(height * aspect, height, 1))
  }
  return label
}
