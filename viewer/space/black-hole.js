/* The galactic centre as a black hole: an event horizon, black; a photon ring hugging it, brighter
 * than white for the light effects' bloom; an accretion disc in the
 * galactic plane, white-hot within, orange, then dark red without, streaked
 * in a turning spiral — its approaching side brighter, as a real disc's —
 * and a faint halo, so that it glows without the effects too.
 *
 *   const hole = createBlackHole()   // a Group at the origin
 *   each frame: hole.userData.update(seconds)
 *
 * Shared (space/): the galactic centre on the galaxy map, and, scaled down,
 * a stellar black hole on the galaxy and system maps — its
 * horizon HORIZON in radius before scaling.
 */
import * as THREE from 'three'

export const HORIZON = 80       // ly: the event horizon's radius, as drawn
const DISC = [110, 650]         // ly: the accretion disc's inner and outer edge
const HALO = 900                // ly: the halo's reach

const discVertex = `
  #include <common>
  #include <logdepthbuf_pars_vertex>
  varying vec2 vAt;               // in the disc's plane, ly from the centre
  varying float vToward;          // its motion toward the camera, −1 to 1
  void main() {
    vAt = position.xy;
    vec4 world = modelMatrix * vec4(position, 1.0);
    // Turning anticlockwise: the direction it moves here, in the world.
    vec3 motion = normalize((modelMatrix * vec4(-position.y, position.x, 0.0, 0.0)).xyz);
    vToward = dot(motion, normalize(cameraPosition - world.xyz));
    gl_Position = projectionMatrix * viewMatrix * world;
    #include <logdepthbuf_vertex>
  }`

const discFragment = `
  #include <common>
  #include <logdepthbuf_pars_fragment>
  uniform float time;
  varying vec2 vAt;
  varying float vToward;
  void main() {
    #include <logdepthbuf_fragment>
    float r = length(vAt);
    float t = clamp((r - ${DISC[0].toFixed(1)}) / ${(DISC[1] - DISC[0]).toFixed(1)}, 0.0, 1.0);
    // Hotter within: white, then orange, then a dull red at the rim.
    vec3 hot = mix(vec3(1.0, 0.82, 0.55), vec3(1.0, 0.42, 0.08), smoothstep(0.0, 0.3, t));
    vec3 colour = mix(hot, vec3(0.45, 0.06, 0.02), smoothstep(0.3, 1.0, t));
    // Streaks wound into a spiral, turning as one. Turned as Kepler has it
    // (ω ∝ r^−1.5), the shear wound them tighter every second, into the
    // grooves of a record within a minute.
    float a = atan(vAt.y, vAt.x);
    float spin = time * 0.35;
    // Three arms, sharpened, and fine threads wound along them.
    float arms = pow(0.5 + 0.5 * sin(a * 3.0 + log(r) * 6.0 - spin), 2.0);
    float streaks = 0.45 + 0.4 * arms + 0.15 * sin(a * 11.0 + log(r) * 13.0 - spin * 1.5);
    float bright = pow(1.0 - t, 2.4) * streaks
                 * smoothstep(0.0, 0.06, t) * (1.0 - smoothstep(0.85, 1.0, t))
                 * (1.0 + 0.45 * vToward);                       // beamed toward the camera
    gl_FragColor = vec4(colour * bright * 1.4, 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }`

/* A round glow: `profile(x)` its brightness from the centre (0) to the
 * edge (1), drawn into a texture. */
function glowTexture(profile) {
  const size = 256, canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const g = canvas.getContext('2d')
  const fade = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  for (let k = 0; k <= 32; k++) {
    fade.addColorStop(k / 32, `rgba(255,255,255,${Math.max(0, Math.min(1, profile(k / 32))).toFixed(3)})`)
  }
  g.fillStyle = fade
  g.fillRect(0, 0, size, size)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

/* A horizon's black: where it is the nearest thing drawn, it marks the
 * stencil, and the light effects add no glow there (space/effects.js) —
 * blurred over the screen after drawing, the glow smoked it like dark glass
 *. A star in front of it is drawn over it all the same:
 * it eclipses the black hole. Needs a renderer made with a stencil. */
export function horizonMaterial() {
  return new THREE.MeshBasicMaterial({ color: 0x000000, stencilWrite: true, stencilRef: HORIZON_STENCIL,
    stencilFunc: THREE.AlwaysStencilFunc, stencilZPass: THREE.ReplaceStencilOp })
}
export const HORIZON_STENCIL = 1

/* `ring`: the photon ring's brightness, 1 as at the galactic centre; lower
 * where a map's light effects bloom more readily (the system map's). */
export function createBlackHole({ ring: ringBrightness = 1 } = {}) {
  const group = new THREE.Group()

  // The horizon: black, and hiding what lies behind it.
  const horizon = new THREE.Mesh(new THREE.SphereGeometry(HORIZON, 48, 32), horizonMaterial())
  group.add(horizon)

  // The disc, flat in the galactic plane, seen from both sides.
  const discMaterial = new THREE.ShaderMaterial({
    vertexShader: discVertex, fragmentShader: discFragment, uniforms: { time: { value: 0 } },
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
  })
  const disc = new THREE.Mesh(new THREE.RingGeometry(DISC[0], DISC[1], 128, 8), discMaterial)
  disc.rotation.x = -Math.PI / 2
  // After the galaxy map's stars (star-field.js), as the ring and the halo.
  disc.renderOrder = 3
  group.add(disc)

  // The photon ring: a thin bright ring just outside the horizon, facing
  // the camera, brighter than white.
  const ringReach = HORIZON * 1.7
  const ring = new THREE.Sprite(new THREE.SpriteMaterial({
    map: glowTexture(x => {
      const edge = HORIZON / ringReach * 1.08                  // where the ring is, of the sprite's radius
      return Math.exp(-(((x - edge) / 0.07) ** 2))
    }),
    color: new THREE.Color(2.2, 1.9, 1.5).multiplyScalar(ringBrightness), transparent: true, depthWrite: false,
    // Tested against depth, so a star in front of the black hole hides it
    // (untested, it shone through them); onBeforeRender
    // sets it before the horizon, where the sphere hid it seen edge-on.
    // Not over any horizon either — a black hole's in front of it — which
    // marks the stencil.
    blending: THREE.AdditiveBlending,
    stencilWrite: true, stencilRef: HORIZON_STENCIL, stencilFunc: THREE.NotEqualStencilFunc,
  }))
  ring.scale.setScalar(2 * ringReach)
  ring.renderOrder = 3
  // Kept at the horizon's edge as the camera sees it: the ring is flat
  // through the centre, the horizon a sphere bulging toward the camera —
  // near it (the galactic centre, close up) the sphere's edge lies wider
  // than the ring, which vanished behind it. And set before the horizon,
  // toward the camera, so the sphere does not hide it in the depth test.
  // Set before each draw, its matrix again, so the frame drawn has it.
  const centre = new THREE.Vector3(), toward = new THREE.Vector3()
  ring.onBeforeRender = (renderer, scene, camera) => {
    group.getWorldPosition(centre)
    const d = camera.position.distanceTo(centre) / group.getWorldScale(centre.clone()).x
    const edge = d > HORIZON * 1.001 ? d * Math.tan(Math.asin(HORIZON / d)) / HORIZON : 1
    const ahead = Math.min(HORIZON * 1.02, d / 2)
    // Nearer the camera by `ahead`, smaller by as much: the same size seen.
    ring.scale.setScalar(2 * ringReach * edge * (d - ahead) / d)
    toward.copy(camera.position)
    group.worldToLocal(toward)
    ring.position.copy(toward.normalize()).multiplyScalar(ahead)
    ring.updateMatrixWorld()
  }
  group.add(ring)

  // The halo: faint, wide, warm.
  const halo = new THREE.Sprite(new THREE.SpriteMaterial({
    map: glowTexture(x => 0.2 * (1 - x) ** 4), color: 0xff8a40,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  }))
  halo.scale.setScalar(2 * HALO)
  halo.renderOrder = 3
  group.add(halo)

  // None of it in the light effects' glow: blurred over the screen after
  // drawing, it spread over the horizon, a smoked glass where black belongs
  //. The ring and the disc's inner edge are white enough.
  for (const part of [disc, ring, halo]) part.userData.glow = false

  group.userData = {
    name: 'Galactic Center',
    spectralType: 'Black Hole',
    position: { x: 0, y: 0, z: 0 },
    update(seconds) { discMaterial.uniforms.time.value = seconds },
  }
  return group
}
