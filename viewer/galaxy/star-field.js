/* Every star of the galaxy map in three draws: the stars themselves as
 * points, one vertex each, their disc and glow drawn by the shader; the stems down to the galactic
 * plane as one set of lines; the discs where they meet it as points too.
 * Before, each star was six meshes — at 10,000 stars, 60,000 draws.
 *
 * The look is the old one's: a disc in the spectral colour; for the stars
 * with a glow, three layers to 1.3, 1.8 and 2.5 radii pulsing and twinkling,
 * else one to 1.5 radii; a hovered star 1.3 times as large. Never smaller
 * on screen than MIN_PIXELS.
 *
 *   const field = createStarField(records)   // { position, colour, radius, glow, stem, occludes }
 *
 * `stem: false` leaves a star without its stem and disc on the plane: the
 * real sky's stars, small and many round Sol. `occludes: false`:
 * a star that hides nothing behind it — a black hole, whose point would
 * hide its own glow.
 *   scene.add(field.object); each frame field.update(time, camera, height, renderer)
 *   field.setStems(false)    the stems and their discs on the plane hidden
 *   field.nearest(pointer, camera, width, height) → index or -1
 */
import * as THREE from 'three'

const MIN_PIXELS = 1.5          // a star's disc is never smaller than this, in radius
const GLOW_REACH = 3.0          // a bright star's corona fades out at this many radii
const PLAIN_REACH = 2.0         // a dimmer one's
const CORE = 2.2                // the disc's brightness: its centre brighter than white
const PULSE = 0.12              // the corona's slow flicker, as a share
const TWINKLE = 0.07            // and its quick one
const PICK_PIXELS = 10          // a click this near a star's centre takes it
// Far stars dimmer and without their corona: at a fixed visible
// brightness, thousands of overlapping coronas added up to a white wash. A
// star's light falls off as the square root of FADE_FROM / distance beyond
// FADE_FROM (ly), to FADE_FLOOR at most (linearly, to 0.16, the galaxy
// looks dull); its corona fades out as its true disc shrinks
// from CORONA_PIXELS[1] to CORONA_PIXELS[0] (radius, CSS pixels) — the
// hovered star keeps both.
const FADE_FROM = 8000
const FADE_FLOOR = 0.3
const CORONA_PIXELS = [0.6, 2.2]
// A star hides what lies behind it once its true disc is this large (radius,
// CSS pixels): the far ones add up instead (coreFragment).
const OCCLUDE_PIXELS = 2.2
const PICK_CELL = 32            // px: the screen grid nearest() looks stars up in
const STEM_OPACITY = 0.4
const BASE_RADIUS = 15          // the disc on the galactic plane under each star
const BASE_OPACITY = 0.5

const vertexShader = `
  #include <common>
  #include <logdepthbuf_pars_vertex>
  attribute vec3 starColour;
  attribute float starRadius;
  attribute float starGlow;
  attribute float starOccludes;
  uniform float time;
  uniform float hovered;
  uniform float pixelWorld;         // world units per CSS pixel at distance 1
  uniform float pixelRatio;
  uniform float largest;            // the largest point the GPU draws, in its pixels
  varying vec3 vColour;
  varying float vGlow;
  varying float vReach;
  varying float vPulse;
  varying float vTwinkle;
  varying float vFade;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    float phase = float(gl_VertexID);
    bool isHovered = abs(phase - hovered) < 0.5;
    float grow = isHovered ? 1.3 : 1.0;
    float distance = -mv.z;
    float radius = max(starRadius, ${MIN_PIXELS.toFixed(1)} * pixelWorld * distance) * grow;
    // Its true disc on screen, before MIN_PIXELS: the corona only for a
    // star seen as more than a point; dimmer the farther (FADE_FROM).
    float truePixels = starRadius / (pixelWorld * distance);
    float corona = isHovered ? 1.0 : smoothstep(${CORONA_PIXELS[0].toFixed(1)}, ${CORONA_PIXELS[1].toFixed(1)}, truePixels);
    float reach = starGlow > 0.5 ? ${GLOW_REACH.toFixed(1)} : ${PLAIN_REACH.toFixed(1)};
    vReach = mix(1.05, reach, corona);
    vFade = isHovered ? 1.0 : clamp(sqrt(${FADE_FROM.toFixed(1)} / distance), ${FADE_FLOOR.toFixed(2)}, 1.0);
    gl_PointSize = min(2.0 * radius * vReach / (pixelWorld * distance) * pixelRatio, largest);
    vColour = starColour;
    vGlow = starGlow;
    // A gentle flicker of the corona, each star in its own time: a stronger
    // pulse and twinkle read as restless.
    vPulse = sin(time * 1.2 + phase) * ${PULSE.toFixed(2)} + 1.0;
    vTwinkle = sin(time * 2.6 + phase * 2.5) * ${TWINKLE.toFixed(2)} + 1.0;
    gl_Position = projectionMatrix * mv;
    #include <logdepthbuf_vertex>
    #ifdef CORES
    // Only a star seen as a disc hides what lies behind it: the far ones,
    // drawn at MIN_PIXELS, stand for light the eye does not resolve, and add
    // up to the bulge's glow. Outside the view: not drawn.
    if (starOccludes < 0.5 || truePixels < ${OCCLUDE_PIXELS.toFixed(1)}) gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    #endif
  }`

/* The discs of the stars seen as discs (OCCLUDE_PIXELS), in the depth
 * buffer only, drawn before anything transparent: added on and writing no
 * depth, a star let what lies behind it shine through it — the bulge, the
 * galactic centre's disc, halo and photon ring. A hair behind the star
 * itself, which is drawn at the same depth. Where a disc lies in front of a
 * black hole's horizon it clears the horizon's mark in the stencil, so the
 * light effects' bloom (space/effects.js) lies over the whole star, not only
 * the half beside the horizon.
 *
 * In the bloom's own render (FAR_BEHIND) a disc hides only what lies twice
 * as far or farther: there light is not clamped at white, and the stars of
 * the bulge, overlapping, add up to the glow that blooms — hidden by each
 * other, the glow was gone. A star well in front still
 * keeps the bulge's and the centre's glow off it. */
const coreFragment = `
  #include <common>
  #include <logdepthbuf_pars_fragment>
  varying float vReach;
  void main() {
    #include <logdepthbuf_fragment>
    if (length(gl_PointCoord * 2.0 - 1.0) * vReach > 0.97) discard;   // the disc, to its soft rim
    #if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
    #ifdef FAR_BEHIND
    gl_FragDepth = min(gl_FragDepth + logDepthBufFC * 0.5, 1.0);   // twice as far: log2(2 w)
    #else
    gl_FragDepth = min(gl_FragDepth + 1e-6, 1.0);
    #endif
    #endif
    gl_FragColor = vec4(0.0);
  }`

const fragmentShader = `
  #include <common>
  #include <logdepthbuf_pars_fragment>
  varying vec3 vColour;
  varying float vGlow;
  varying float vReach;
  varying float vPulse;
  varying float vTwinkle;
  varying float vFade;
  void main() {
    #include <logdepthbuf_fragment>
    float r = length(gl_PointCoord * 2.0 - 1.0) * vReach;     // in star radii
    // A ball of light, as the star-system map's stars:
    // its disc darker toward the rim and whiter at the centre — brighter
    // than white there, so the light effects' bloom takes it up — and a
    // corona fading out from the rim, not the old map's layered shells.
    float mu = sqrt(max(0.0, 1.0 - r * r));
    float disc = 1.0 - smoothstep(0.94, 1.0, r);
    vec3 surface = mix(vColour, vec3(1.0), 0.35 * mu) * (0.4 + 0.6 * mu) * ${CORE.toFixed(1)};
    float x = clamp((r - 0.9) / (vReach - 0.9), 0.0, 1.0);
    float corona = (vGlow > 0.5 ? 0.6 : 0.35) * pow(1.0 - x, 3.0) * vPulse * vTwinkle;
    vec3 light = (surface * disc + vColour * corona * (1.0 - disc)) * vFade;
    if (max(light.r, max(light.g, light.b)) <= 0.0) discard;
    gl_FragColor = vec4(light, 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }`

// The largest point the GPU draws (ALIASED_POINT_SIZE_RANGE): a star nearer
// than that allows is drawn at it, not larger.
let largestKnown = 0
function largestPoint(renderer) {
  if (!largestKnown) {
    const gl = renderer.getContext()
    largestKnown = gl.getParameter(gl.ALIASED_POINT_SIZE_RANGE)[1] || 64
  }
  return largestKnown
}

const baseVertex = `
  #include <common>
  #include <logdepthbuf_pars_vertex>
  attribute vec3 starColour;
  uniform float pixelWorld;
  uniform float pixelRatio;
  uniform float largest;
  varying vec3 vColour;
  varying float vSquash;
  void main() {
    vec4 world = modelMatrix * vec4(position, 1.0);
    vec4 mv = viewMatrix * world;
    // How steeply the plane is seen here: 1 from straight above, 0 edge-on.
    vSquash = max(abs(normalize(cameraPosition - world.xyz).y), 0.05);
    gl_PointSize = min(2.0 * ${BASE_RADIUS.toFixed(1)} / (pixelWorld * -mv.z) * pixelRatio, largest);
    vColour = starColour;
    gl_Position = projectionMatrix * mv;
    #include <logdepthbuf_vertex>
  }`

const baseFragment = `
  #include <common>
  #include <logdepthbuf_pars_fragment>
  varying vec3 vColour;
  varying float vSquash;
  void main() {
    #include <logdepthbuf_fragment>
    vec2 p = gl_PointCoord * 2.0 - 1.0;
    if (p.x * p.x + (p.y / vSquash) * (p.y / vSquash) > 1.0) discard;
    gl_FragColor = vec4(vColour, ${BASE_OPACITY.toFixed(2)});
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }`

export function createStarField(records) {
  const count = records.length
  const object = new THREE.Group()

  // ── the stars: one point each, its disc and glow drawn by the shader
  // (a point is one vertex, a quad four: four times less work per star) ──
  const geometry = new THREE.BufferGeometry()
  const at = new Float32Array(count * 3), colour = new Float32Array(count * 3)
  const radius = new Float32Array(count), glow = new Float32Array(count), occludes = new Float32Array(count)
  records.forEach((r, k) => {
    at.set([r.position.x, r.position.y, r.position.z], k * 3)
    const c = new THREE.Color(r.colour)
    colour.set([c.r, c.g, c.b], k * 3)
    radius[k] = r.radius
    glow[k] = r.glow ? 1 : 0
    occludes[k] = r.occludes === false ? 0 : 1
  })
  geometry.setAttribute('position', new THREE.BufferAttribute(at, 3))
  geometry.setAttribute('starColour', new THREE.BufferAttribute(colour, 3))
  geometry.setAttribute('starRadius', new THREE.BufferAttribute(radius, 1))
  geometry.setAttribute('starGlow', new THREE.BufferAttribute(glow, 1))
  geometry.setAttribute('starOccludes', new THREE.BufferAttribute(occludes, 1))
  const material = new THREE.ShaderMaterial({
    vertexShader, fragmentShader,
    uniforms: { time: { value: 0 }, hovered: { value: -1 }, pixelWorld: { value: 0.001 }, pixelRatio: { value: 1 },
      largest: { value: 256 } },
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  })
  const stars = new THREE.Points(geometry, material)
  stars.frustumCulled = false
  stars.renderOrder = 1
  object.add(stars)
  // Their discs, in depth only (coreFragment): opaque, so drawn before the
  // transparent rest, and after a black hole's horizon (render order 1);
  // the same uniforms, so the same size. One set for the scene, one for the
  // bloom's render only (its layer alone, see space/effects.js).
  const coresFor = glow => {
    const cores = new THREE.Points(geometry, new THREE.ShaderMaterial({
      vertexShader, fragmentShader: coreFragment, uniforms: material.uniforms,
      defines: glow ? { CORES: '', FAR_BEHIND: '' } : { CORES: '' },
      colorWrite: false,
      stencilWrite: true, stencilRef: 0, stencilFunc: THREE.AlwaysStencilFunc, stencilZPass: THREE.ReplaceStencilOp,
    }))
    cores.frustumCulled = false
    cores.renderOrder = 1
    cores.userData.glow = glow
    if (glow) cores.layers.disable(0)      // not in the scene's render: the bloom's sorting adds its layer
    return cores
  }
  const cores = coresFor(false)
  object.add(coresFor(true))
  object.add(cores)

  // ── stems and the discs on the plane ───────────────────────────────────
  const rooted = records.filter(r => r.stem !== false)
  const stem = new Float32Array(rooted.length * 6), stemColour = new Float32Array(rooted.length * 6)
  rooted.forEach((r, k) => {
    stem.set([r.position.x, 0, r.position.z, r.position.x, r.position.y, r.position.z], k * 6)
    const c = new THREE.Color(r.colour)
    stemColour.set([c.r, c.g, c.b, c.r, c.g, c.b], k * 6)
  })
  const stemGeometry = new THREE.BufferGeometry()
  stemGeometry.setAttribute('position', new THREE.BufferAttribute(stem, 3))
  stemGeometry.setAttribute('color', new THREE.BufferAttribute(stemColour, 3))
  const stems = new THREE.LineSegments(stemGeometry,
    new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: STEM_OPACITY }))
  stems.userData.glow = true      // under a star, they add to its glow (space/effects.js)
  object.add(stems)

  // The discs, flat on the plane: points drawn as the ellipse a disc seen
  // at that angle makes — squashed by how steeply the plane is seen. As
  // meshes, 10,000 of them cost more than everything else.
  const baseAt = new Float32Array(rooted.length * 3), baseColour = new Float32Array(rooted.length * 3)
  rooted.forEach((r, k) => {
    baseAt.set([r.position.x, 0, r.position.z], k * 3)
    const c = new THREE.Color(r.colour)
    baseColour.set([c.r, c.g, c.b], k * 3)
  })
  const baseGeometry = new THREE.BufferGeometry()
  baseGeometry.setAttribute('position', new THREE.BufferAttribute(baseAt, 3))
  baseGeometry.setAttribute('starColour', new THREE.BufferAttribute(baseColour, 3))
  const baseMaterial = new THREE.ShaderMaterial({
    vertexShader: baseVertex, fragmentShader: baseFragment, uniforms: material.uniforms,
    transparent: true, depthWrite: false,
  })
  const bases = new THREE.Points(baseGeometry, baseMaterial)
  bases.frustumCulled = false
  bases.userData.glow = true
  object.add(bases)

  const projected = new THREE.Vector3()
  // nearest()'s screen grid, made again when the camera, its lens or the
  // view's size changed.
  let grid = null, gridKey = ''
  function screenGrid(camera, width, height) {
    const key = camera.matrixWorld.elements.join(',') + camera.projectionMatrix.elements.join(',') + width + 'x' + height
    if (grid && key === gridKey) return grid
    const perPixel = material.uniforms.pixelWorld.value
    const x = new Float32Array(count), y = new Float32Array(count), pick = new Float32Array(count)
    const cells = new Map()
    let farthest = PICK_PIXELS
    for (let k = 0; k < count; k++) {
      const p = records[k].position
      projected.copy(p).project(camera)
      if (projected.z > 1 || projected.z < -1) continue
      x[k] = projected.x * width / 2
      y[k] = projected.y * height / 2
      const discPx = records[k].radius / (perPixel * camera.position.distanceTo(p))
      pick[k] = Math.max(PICK_PIXELS, discPx * 1.3)
      if (pick[k] > farthest) farthest = Math.min(pick[k], Math.max(width, height))
      const cell = Math.floor(x[k] / PICK_CELL) * 65536 + Math.floor(y[k] / PICK_CELL)
      const list = cells.get(cell)
      if (list) list.push(k); else cells.set(cell, [k])
    }
    grid = { x, y, pick, cells, farthest }
    gridKey = key
    return grid
  }
  return {
    object,
    /* Each frame: the clock, and how large a pixel is at distance 1. */
    update(time, camera, height, renderer) {
      material.uniforms.time.value = time
      material.uniforms.pixelRatio.value = renderer.getPixelRatio()
      material.uniforms.largest.value = largestPoint(renderer)
      material.uniforms.pixelWorld.value = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) / (height || 1)
    },
    setHovered(index) { material.uniforms.hovered.value = index },
    /* The stems down to the galactic plane and their discs there, shown or
     * not (the map's ⊥): with thousands of stars and the gate network, they
     * clutter the view. */
    setStems(shown) { stems.visible = shown; bases.visible = shown },
    /* The star nearest `pointer` (normalised device coordinates) within its
     * disc on screen or PICK_PIXELS, nearer stars first among equals; -1 if
     * none. On screen, not by ray: no mesh per star to hit. */
    nearest(pointer, camera, width, height) {
      // The stars on screen, in a grid of PICK_CELL-pixel cells, kept while
      // the camera and the view stay as they are: a pointer
      // move looks at the cells round it, not at every star — 30,000 of
      // them with the procedural galaxy, several milliseconds each move.
      const grid = screenGrid(camera, width, height)
      const px0 = pointer.x * width / 2, py0 = pointer.y * height / 2
      const reach = Math.ceil(grid.farthest / PICK_CELL)
      const cx = Math.floor(px0 / PICK_CELL), cy = Math.floor(py0 / PICK_CELL)
      // As before: of the stars whose pick radius takes the pointer, the
      // nearest; on a tie the later one.
      let best = -1, bestPx = Infinity
      for (let gx = cx - reach; gx <= cx + reach; gx++) {
        for (let gy = cy - reach; gy <= cy + reach; gy++) {
          const cellStars = grid.cells.get(gx * 65536 + gy)
          if (!cellStars) continue
          for (const k of cellStars) {
            const px = Math.hypot(grid.x[k] - px0, grid.y[k] - py0)
            if (px > grid.pick[k] || px > bestPx || (px === bestPx && k < best)) continue
            best = k; bestPx = px
          }
        }
      }
      return best
    },
    dispose() {
      object.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose() })
    },
  }
}
