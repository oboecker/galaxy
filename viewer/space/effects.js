/* Light effects every 3D map shares: light brighter than white blooms past its edges — a star's
 * core, a sun — added over the map as it is otherwise drawn. On for every
 * reader, with a toggle on the map that turns it off for a weak device;
 * remembered per browser, for every map at once.
 *
 * Added over, not drawn through: the map is drawn to the screen exactly as
 * without the effects; a second, half-size render of the same scene feeds
 * the bloom, and only its glow is added on top. Drawn through a high
 * dynamic range pipeline instead, everything translucent — halos, stems,
 * orbit lines — blended in linear light and came out brighter: the galaxy
 * filled with haze.
 *
 *   const fx = createEffects(renderer, scene, camera, { onGlow })
 *   fx.render() instead of renderer.render(scene, camera); fx.setSize(w, h)
 *   qualityButton(bar) — the toggle, a round button in the map's bar
 *
 * `onGlow(true)` before the glow's render, `onGlow(false)` after: a map may
 * make its suns brighter than white for it alone.
 *
 * The glow's render draws only what can glow: what is added on (additive
 * blending — stars, coronas, the black hole's disc) and what a map marks
 * with `object.userData.glow` (a sun's surface, the galaxy's stems) — and
 * not what is marked `userData.glow = false` (a black hole's disc); every
 * other solid mesh is drawn black, so it still hides the glow behind it,
 * and the rest (lines, translucent halos) not at all. The two renders need each material's
 * shader in two versions (the screen's colour and tone mapping, and linear
 * light for the glow), and three.js looks the right one up again on every
 * switch, for every material: drawing the few that glow, not all, saves that
 * work twice a frame.
 */
import * as THREE from 'three'
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js'
import { toggleIcon } from './icons.js'

const KEY = 'space-effects'            // localStorage: 'off' turns them off
const EVENT = 'space-effects'          // on window, when the toggle changes
const GLOW_SCALE = 0.5                 // the glow's render, of the screen's size
const GLOWS = 30                       // layers: what is drawn in the glow's render
const HIDES = 31                       //   what is drawn black in it
const black = new THREE.MeshBasicMaterial({ color: 0x000000 })

/* Sorts every object for the glow's render, as it is now: a map adds and
 * removes objects at any time. Lights take part in every render, or three.js
 * would see the lights change, and look up every lit material's shader again. */
function sort(object) {
  const layers = object.layers
  layers.disable(GLOWS)
  layers.disable(HIDES)
  const material = object.material
  if (object.isLight) {
    layers.enable(GLOWS)
    layers.enable(HIDES)
  } else if (material && !Array.isArray(material)) {
    // userData.glow false: never in the glow, though added on — a black
    // hole's disc and rings, whose glow spread over its horizon.
    if (object.userData.glow === false) { if (object.isMesh && !material.transparent) layers.enable(HIDES) }
    else if (object.userData.glow || material.blending === THREE.AdditiveBlending) layers.enable(GLOWS)
    else if (object.isMesh && !material.transparent) layers.enable(HIDES)
  } else if (material && object.isMesh) {
    layers.enable(HIDES)
  }
}

/* Unless chosen with ✦: off on a small touch screen (a phone), on elsewhere. */
function smallTouch() {
  const coarse = globalThis.matchMedia && globalThis.matchMedia('(pointer: coarse)').matches
  return Boolean(coarse && globalThis.screen && Math.min(screen.width, screen.height) < 600)
}

export function effectsOn() {
  let chosen = null
  try { chosen = localStorage.getItem(KEY) } catch { /* private window: the default */ }
  return chosen ? chosen !== 'off' : !smallTouch()
}

function setEffects(on) {
  try { localStorage.setItem(KEY, on ? 'on' : 'off') } catch { /* private window: this page only */ }
  globalThis.dispatchEvent(new CustomEvent(EVENT, { detail: on }))
}

/* The glow, added over the screen: tone mapped (1 − e^−x), so much burns
 * toward white, and added as it is — not encoded for the screen, which
 * lifts faint values (0.01 to 0.12): the bloom's wide, faint tail covered
 * the whole map in haze. */
function overlayMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: { glow: { value: null } },
    vertexShader: 'varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }',
    fragmentShader: `
      uniform sampler2D glow;
      varying vec2 vUv;
      void main() {
        gl_FragColor = vec4(1.0 - exp(-texture2D(glow, vUv).rgb), 1.0);
      }`,
    blending: THREE.AdditiveBlending, depthTest: false, depthWrite: false, transparent: true,
    // Not over a black hole's horizon, which marks the stencil (black-hole.js horizonMaterial).
    stencilWrite: true, stencilRef: 1, stencilFunc: THREE.NotEqualStencilFunc,
  })
}

/* `strength`, `radius`, `threshold`: the bloom's (UnrealBloomPass): how
 * bright the glow, how far it spreads, from what brightness on (1 is white:
 * only what is brighter blooms). */
export function createEffects(renderer, scene, camera, { strength = 0.8, radius = 0.3, threshold = 1.2,
  onGlow = () => {} } = {}) {
  let current = scene
  const size = renderer.getSize(new THREE.Vector2())
  const target = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType })
  const bloom = new UnrealBloomPass(size.clone().multiplyScalar(GLOW_SCALE), strength, radius, threshold)
  const overlay = overlayMaterial()
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), overlay)
  quad.frustumCulled = false
  const quadScene = new THREE.Scene()
  quadScene.add(quad)
  const quadCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1)

  let on = effectsOn()
  const onToggle = event => { on = event.detail }
  globalThis.addEventListener(EVENT, onToggle)

  function setSize(width, height) {
    const ratio = renderer.getPixelRatio() * GLOW_SCALE
    target.setSize(Math.max(1, Math.round(width * ratio)), Math.max(1, Math.round(height * ratio)))
    bloom.setSize(target.width, target.height)
  }
  setSize(size.x, size.y)

  return {
    render() {
      if (!current) return
      renderer.render(current, camera)
      if (!on) return
      // The glow: what glows, small and in linear light, through the bloom.
      onGlow(true)
      current.traverse(sort)
      const mask = camera.layers.mask
      const autoClear = renderer.autoClear
      renderer.setRenderTarget(target)
      renderer.clear()
      renderer.autoClear = false
      current.overrideMaterial = black
      camera.layers.set(HIDES)
      renderer.render(current, camera)
      current.overrideMaterial = null
      camera.layers.set(GLOWS)
      renderer.render(current, camera)
      camera.layers.mask = mask
      renderer.autoClear = autoClear
      onGlow(false)
      bloom.render(renderer, null, target, 0, false)
      // UnrealBloomPass leaves the mips' composite in its first horizontal
      // target, before blending it over its input — that blend is not wanted.
      overlay.uniforms.glow.value = bloom.renderTargetsHorizontal[0].texture
      renderer.setRenderTarget(null)
      renderer.autoClear = false
      renderer.render(quadScene, quadCamera)
      renderer.autoClear = autoClear
    },
    setSize,
    // A map that builds a new scene (the system map, another view).
    setScene(next) { current = next },
    get on() { return on },
    bloom,                              // its strength, radius and threshold, to tune
    dispose() {
      globalThis.removeEventListener(EVENT, onToggle)
      target.dispose()
      bloom.dispose()
      quad.geometry.dispose()
      overlay.dispose()
    },
  }
}

/* The toggle, a round button appended to `bar`: pressed while the effects
 * are on; every map's button follows any one of them. */
export function qualityButton(bar) {
  const button = document.createElement('button')
  button.type = 'button'
  button.className = 'space-tool space-effects-toggle'
  toggleIcon(button, 'sun')
  const show = on => {
    button.setAttribute('aria-pressed', String(on))
    button.title = on ? 'Light effects on — turn them off on a slow device' : 'Light effects off — turn them on'
  }
  show(effectsOn())
  button.addEventListener('click', () => setEffects(!effectsOn()))
  const onToggle = event => show(event.detail)
  globalThis.addEventListener(EVENT, onToggle)
  bar.appendChild(button)
  return () => { globalThis.removeEventListener(EVENT, onToggle); button.remove() }
}
