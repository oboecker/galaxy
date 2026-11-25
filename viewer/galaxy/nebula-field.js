/* The nebulae on the 3D galaxy map:
 * soft sprites — billboards, each a fuzzy blob broken by noise — scattered
 * through each nebula's ellipsoid, as the side-by-side test chose (orbiting,
 * their depths read as volume). Two clouds of them: the glowing kinds
 * (emission, reflection, planetary, remnant) added to what lies behind, the
 * dark ones laid over it, drawn after.
 *
 *   const field = createNebulaField(json.nebulae)   // galaxy.json's list
 *   scene.add(field.object); field.update(camera, height, pixelRatio) each frame
 *
 * Scene units are light years, as the stars' (galaxy x, y, z → x, z, −y).
 */
import * as THREE from 'three'

// A kind's look: its colour (the nebula's own wins), a second it fades to,
// and whether its sprites fill it or lie on a shell (a planetary nebula, a
// supernova remnant).
const LOOK = {
  emission: { colour: '#ff5a85', second: '#6fa8ff', shell: false },
  reflection: { colour: '#7fa7ff', second: '#c8d8ff', shell: false },
  // Dim brown-grey, not black: a dark cloud reads as smoke over the stars
  // behind it, and as a shape where nothing is.
  dark: { colour: '#3a2f27', second: '#3a2f27', shell: false },
  planetary: { colour: '#4fd6c4', second: '#ff7a9a', shell: true },
  remnant: { colour: '#ffa65c', second: '#7fd4ff', shell: true },
}

// Sprites per nebula: more for a larger one, within a budget the map keeps
// its frame rate at (some 21 real nebulae and the catalogue's own).
const MIN_SPRITES = 24
const MAX_SPRITES = 220
// Below this size on screen a sprite stops shrinking and fades instead, so a
// far nebula stays a coloured smudge, as a star stays a point, rather than
// vanishing (a nebula of 20 ly is under a pixel across the galaxy).
const MIN_PIXELS = 6

const NOISE = `
  float hash3(vec3 p){ p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
  float noise3(vec3 x){ vec3 i = floor(x), f = fract(x); f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(hash3(i), hash3(i + vec3(1,0,0)), f.x), mix(hash3(i + vec3(0,1,0)), hash3(i + vec3(1,1,0)), f.x), f.y),
               mix(mix(hash3(i + vec3(0,0,1)), hash3(i + vec3(1,0,1)), f.x), mix(hash3(i + vec3(0,1,1)), hash3(i + vec3(1,1,1)), f.x), f.y), f.z); }
  float fbm3(vec3 p){ float v = 0.0, a = 0.5; for (int i = 0; i < 4; i++) { v += a * noise3(p); p = p * 2.02 + 3.1; a *= 0.5; } return v; }`

function material(dark) {
  return new THREE.ShaderMaterial({
    uniforms: { scale: { value: 1 }, minPixels: { value: MIN_PIXELS } },
    vertexShader: `
      #include <common>
      #include <logdepthbuf_pars_vertex>
      attribute float size; attribute float seed; attribute vec3 tint; attribute float weight;
      uniform float scale; uniform float minPixels;
      varying vec3 vTint; varying float vSeed; varying float vAlpha;
      void main(){
        vec4 mv = modelViewMatrix * vec4(position, 1.0); float d = -mv.z;
        float px = size * scale / max(d, 0.001);
        gl_PointSize = clamp(px, minPixels, 2048.0);
        // Below the least size, fainter as much as it would have shrunk;
        // close by, gone as the camera passes through it.
        vAlpha = weight * min(1.0, px / minPixels) * smoothstep(size * 0.15, size * 0.9, d);
        vTint = tint; vSeed = seed;
        gl_Position = projectionMatrix * mv;
        #include <logdepthbuf_vertex>
      }`,
    fragmentShader: `
      #include <common>
      #include <logdepthbuf_pars_fragment>
      ${NOISE}
      varying vec3 vTint; varying float vSeed; varying float vAlpha;
      void main(){
        #include <logdepthbuf_fragment>
        vec2 c = gl_PointCoord * 2.0 - 1.0; float r = length(c); if (r > 1.0) discard;
        float n = fbm3(vec3(c * 2.6, vSeed));
        float a = pow(1.0 - r, 2.0) * smoothstep(0.38, 0.78, n) * vAlpha;
        gl_FragColor = vec4(vTint, a * ${dark ? '0.85' : '0.6'});
      }`,
    transparent: true, depthWrite: false, depthTest: true,
    blending: dark ? THREE.NormalBlending : THREE.AdditiveBlending,
  })
}

// A seeded random source, so a nebula looks the same on every visit.
function random(seed) {
  let s = seed >>> 0
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296 }
}
function seedOf(text) {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619)
  return h >>> 0
}
function gauss(rand) {
  let u = 0, v = 0
  while (!u) u = rand()
  while (!v) v = rand()
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)
}

/* The sprites of one nebula, appended to `into` (arrays per attribute). */
function sprites(n, into) {
  const look = LOOK[n.kind] || LOOK.emission
  const rand = random(seedOf(n.id || n.name))
  const [a, b, c] = n.size
  const largest = Math.max(a, b, c)
  // A shell needs more sprites to close round, however small it is.
  const least = look.shell ? 60 : MIN_SPRITES
  const count = Math.round(Math.min(MAX_SPRITES, Math.max(least, 24 + Math.sqrt(largest) * 12)))
  const tilt = new THREE.Euler(...(n.tilt || [0, 0, 0]).map(THREE.MathUtils.degToRad))
  const colour = new THREE.Color(n.colour || look.colour), second = new THREE.Color(look.second)
  const p = new THREE.Vector3()
  for (let i = 0; i < count; i++) {
    let x, y, z, q
    if (look.shell) {
      // A shell: on the ellipsoid's surface, thickened a little inward.
      do { x = gauss(rand); y = gauss(rand); z = gauss(rand); q = Math.hypot(x, y, z) } while (q === 0)
      const r = 0.75 + rand() * 0.25
      x = x / q * r; y = y / q * r; z = z / q * r; q = r * r
    } else {
      do { x = gauss(rand) * 0.45; y = gauss(rand) * 0.45; z = gauss(rand) * 0.45; q = x * x + y * y + z * z } while (q > 1)
    }
    // The ellipsoid in galaxy axes, turned by its tilt, then into the scene's.
    p.set(x * a, y * b, z * c).applyEuler(tilt)
    into.position.push(n.x + p.x, (n.z || 0) + p.z, -(n.y + p.y))
    const core = 1 - Math.sqrt(q)
    into.size.push(look.shell ? (0.35 + rand() * 0.35) * largest : (0.3 + rand() * 0.5) * largest * (0.6 + core * 0.8))
    into.seed.push(rand() * 100)
    const tint = colour.clone().lerp(second, n.kind === 'dark' ? 0 : Math.pow(rand(), 2) * (look.shell ? 0.5 : 1 - core))
    into.tint.push(tint.r, tint.g, tint.b)
    into.weight.push((n.kind === 'dark' ? 0.9 : look.shell ? 1.1 : 0.3 + core * 0.6) * Math.min(2.0, 150 / count))
  }
}

function points(list, dark) {
  const into = { position: [], size: [], seed: [], tint: [], weight: [] }
  for (const n of list) sprites(n, into)
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(into.position, 3))
  geometry.setAttribute('size', new THREE.Float32BufferAttribute(into.size, 1))
  geometry.setAttribute('seed', new THREE.Float32BufferAttribute(into.seed, 1))
  geometry.setAttribute('tint', new THREE.Float32BufferAttribute(into.tint, 3))
  geometry.setAttribute('weight', new THREE.Float32BufferAttribute(into.weight, 1))
  const cloud = new THREE.Points(geometry, material(dark))
  cloud.frustumCulled = false
  // After the stars; the dark ones last, over what lies behind them.
  cloud.renderOrder = dark ? 6 : 5
  return cloud
}

export function createNebulaField(list) {
  const nebulae = (list || []).filter(n => Array.isArray(n.size) && n.size.length === 3)
  const object = new THREE.Group()
  object.name = 'nebulae'
  const glowing = points(nebulae.filter(n => n.kind !== 'dark'), false)
  const dark = points(nebulae.filter(n => n.kind === 'dark'), true)
  object.add(glowing, dark)
  return {
    object,
    nebulae,
    /* Sprite sizes follow the view: pixels per light year at distance 1. */
    update(camera, height, pixelRatio) {
      const scale = height * pixelRatio * 0.5 / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))
      glowing.material.uniforms.scale.value = scale
      dark.material.uniforms.scale.value = scale
    },
    dispose() {
      for (const cloud of [glowing, dark]) { cloud.geometry.dispose(); cloud.material.dispose() }
    },
  }
}
