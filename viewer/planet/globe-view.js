/* A planet's globe on its own:
 * the maps' globe (./planet-look.js) on a canvas, with the sky behind it,
 * lit from the upper left, turned by dragging and zoomed by the wheel or a
 * pinch, a double-click back to the first view. Shared by an editor's
 * planet view and the public maps site.
 *
 *   const view = await createGlobeView(canvas, { map, relief, planet, onDraw })
 *   view.setClouds(on), view.setRelief(on), view.request(), view.dispose()
 *
 * `map` a texture's URL (the planet's map), `relief` its height map's URL
 * or null, `planet` its record (name, class, radius in km). With `system`
 * (its system as galaxy.systemmap gives it) and `stars` (every system), the
 * sky is that system's: the galaxy's band and stars where they stand from
 * there. `onDraw` is
 * called after each draw with the km a pixel takes at the view's centre
 * (null without a radius). Drawn on demand — when something changed and
 * while the view still eases — not every frame. Null if the texture does
 * not load.
 */
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { createGlobe, releaseTextures } from './planet-look.js'
import { createSky } from '../space/sky.js'
import { loadGlow } from '../space/galaxy-glow.js'

const ZOOM = [0.5, 6]                   // of the first view's size, as a 2D globe allows
const FILL = 0.45                       // the globe's radius, of the canvas's smaller side, at first
const FOV = 30
const TILT = 0.35                       // the first view's height above the equator, radians

export async function createGlobeView(canvas, { map, relief = null, planet = {}, system = null, stars = null, constellations = null,
  glow = null, onDraw = () => {} } = {}) {
  const texture = await new Promise(resolve => new THREE.TextureLoader().load(map, resolve, undefined, () => resolve(null)))
  if (!texture) return null
  texture.colorSpace = THREE.SRGBColorSpace

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(FOV, 1, 0.01, 100)
  scene.add(camera, new THREE.AmbientLight(0xffffff, 0.25))
  // The sky behind it, as on the maps (../space/sky.js); seeded by the planet.
  scene.add(createSky({ seed: planet.name || 'planet', count: 2500, brightness: 0.55,
    band: Boolean(system && system.galaxy), galaxy: system && system.galaxy, system, stars,
    constellations: constellations || (system && system.constellations),
    glow: glow ? await loadGlow(glow) : null }))
  // Light from the upper left, a little in front, turning with the view.
  const light = new THREE.PointLight(0xffffff, 2.5, 0, 0)
  light.position.set(-45, 50, 75)
  camera.add(light)
  const globe = createGlobe(THREE, planet, { map: texture, relief })
  scene.add(globe)

  const controls = new OrbitControls(camera, canvas)
  controls.enablePan = false
  controls.enableDamping = true
  let first = 1                         // the first view's distance, set by fit
  function fit() {
    const w = canvas.clientWidth || 1, h = canvas.clientHeight || 1
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    const was = first
    first = (h / 2) / (FILL * Math.min(w, h) * Math.tan(FOV * Math.PI / 360))
    // As far as the 2D globe allowed: the surface at the view's centre at
    // most as large as that globe drawn 6×. Closer, a map's texels show —
    // round a pole, its rows are wedges.
    controls.minDistance = 1 + first / ZOOM[1]
    controls.maxDistance = first / ZOOM[0]
    if (was === 1) {
      camera.position.set(0, Math.sin(TILT), Math.cos(TILT)).multiplyScalar(first)
      controls.update()
      controls.saveState()
    }
  }
  fit()

  let frame = 0
  const request = () => { if (!frame && !canvas.hidden && canvas.isConnected) frame = requestAnimationFrame(draw) }
  const resize = new ResizeObserver(() => { fit(); request() })
  resize.observe(canvas)
  controls.addEventListener('change', request)
  controls.addEventListener('start', request)
  const reset = () => { controls.reset(); request() }
  canvas.addEventListener('dblclick', reset)
  globe.userData.reliefReady.then(request)

  const lightAt = new THREE.Vector3()
  function draw() {
    frame = 0
    if (!canvas.isConnected || canvas.hidden) return
    const moving = controls.update()
    light.getWorldPosition(lightAt)
    if (globe.userData.setLight) globe.userData.setLight(lightAt)
    renderer.render(scene, camera)
    // The pixels a radius takes on the surface at the view's centre, which
    // is distance − 1 away, not distance.
    const pixels = (canvas.clientHeight / 2) / ((camera.position.length() - 1) * Math.tan(FOV * Math.PI / 360))
    onDraw(planet.radius ? planet.radius / pixels : null)
    if (moving) request()
  }

  return {
    globe, camera, controls, request, scene,
    hasClouds: !!globe.userData.clouds,
    reliefReady: globe.userData.reliefReady,
    setClouds(on) { if (globe.userData.clouds) globe.userData.clouds.visible = on; request() },
    setRelief(on) { globe.userData.setRelief(on); request() },
    dispose() {
      cancelAnimationFrame(frame)
      resize.disconnect()
      canvas.removeEventListener('dblclick', reset)
      controls.dispose()
      releaseTextures()
      renderer.dispose()
      renderer.forceContextLoss()   // or the context outlives the view: browsers cap them at about 16
    },
  }
}
