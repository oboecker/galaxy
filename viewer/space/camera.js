/* The camera controls every 3D map shares: drag to turn, right-drag to pan, wheel to zoom (Shift faster);
 * go to something — an eased flight, the distance changing by equal factors
 * so that a flight from far out to something small is not over in its first
 * frame — and follow it while it moves; let go. The near and far planes
 * follow the distance (with a logarithmic depth buffer, one view can hold a
 * moon's surface and a whole system or galaxy).
 *
 *   const nav = createNavigator(camera, labels.domElement, { holder, reach })
 *   nav.goTo(() => body.mesh.position, { distance, item: body })
 *   each frame: nav.update(now) — true while the view changes
 */
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'

export const GO_SECONDS = 1             // a go-to's flight
const SHIFT_ZOOM = 4                    // the wheel with Shift: this many times faster

// Moved, for a map that skips still frames: by more than this share of the
// distance to the target — a tenth of a pixel at a 45° field on a screen 900
// high — not the damping's invisible tail, which takes seconds to end.
const STILL = 1e-4

const ease = t => (t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t)

/* `dom` takes the pointer (the label layer, where there is one); `holder`
 * the wheel, before the controls see it. `reach()` is how far the scene
 * extends from the origin, for the far plane; `minDistance`/`maxDistance`
 * bound the zoom. */
export function createNavigator(camera, dom, { holder = dom, reach = () => 1000, minDistance = 0,
  maxDistance = Infinity } = {}) {
  const controls = new OrbitControls(camera, dom)
  controls.enableDamping = true
  controls.minDistance = minDistance
  controls.maxDistance = maxDistance
  let going = null                      // { at, item, start, from, fromDistance, toDistance }
  let followed = null                   // { at, item, near }

  // The controls read the zoom speed as the wheel turns, after this.
  const onWheel = event => { controls.zoomSpeed = event.shiftKey ? SHIFT_ZOOM : 1 }
  holder.addEventListener('wheel', onWheel, { capture: true })
  // A pan moves away from what is followed: it stays selected, not followed.
  const onDown = event => { if (event.button === 2) going = followed = null }
  dom.addEventListener('pointerdown', onDown)

  const point = at => (typeof at === 'function' ? at() : at)

  /* Fly to `at` (a point, or a function giving where it is now), to
   * `distance` from it (null keeps the distance), looking along
   * `direction` (from the target to the camera; null keeps it), then follow
   * it if `follow`. `near()` keeps the camera that far at least from what
   * it follows. `item` is whatever the map calls it, given back by
   * `following`. */
  function goTo(at, { distance = null, item = null, follow = true, near = null, direction = null } = {}) {
    const now = camera.position.distanceTo(controls.target)
    const fromDirection = camera.position.clone().sub(controls.target).normalize()
    going = {
      at, item, follow, near, start: performance.now(), from: controls.target.clone(), fromDistance: now,
      toDistance: distance === null ? now : distance,
      fromDirection, toDirection: direction ? direction.clone().normalize() : fromDirection,
    }
    followed = null
  }

  function letGo() {
    going = null
    followed = null
  }

  function fly(now) {
    const g = going
    const t = Math.min(1, (now - g.start) / 1000 / GO_SECONDS)
    const eased = ease(t)
    // Turned as it flies, when told to; else as the user turns it meanwhile.
    const direction = g.toDirection.equals(g.fromDirection)
      ? camera.position.clone().sub(controls.target).normalize()
      : g.fromDirection.clone().lerp(g.toDirection, eased).normalize()
    controls.target.copy(g.from).lerp(point(g.at), eased)
    camera.position.copy(controls.target)
      .addScaledVector(direction, g.fromDistance * (g.toDistance / g.fromDistance) ** eased)
    if (t === 1) {
      going = null
      if (g.follow) followed = { at: g.at, item: g.item, near: g.near }
    }
  }

  /* The near and far planes by how close the camera is: a fixed near plane
   * cut off a moon looked at from close by, and the orbits around it. */
  function fitDepth() {
    const distance = camera.position.distanceTo(controls.target)
    const near = Math.max(distance * 1e-3, 1e-9)
    const far = camera.position.length() + reach() * 4
    if (Math.abs(camera.near / near - 1) > 0.05 || camera.far !== far) {
      camera.near = near
      camera.far = far
      camera.updateProjectionMatrix()
    }
    controls.minDistance = followed && followed.near ? followed.near() : minDistance
  }

  /* Each frame, before rendering. True while the view changes — a flight,
   * a followed target moving, the controls turning or settling — so that a
   * map may skip drawing a still view. */
  const lastPosition = camera.position.clone(), lastTarget = controls.target.clone()
  function update(now = performance.now()) {
    if (going) {
      fly(now)
    } else if (followed) {
      const shift = point(followed.at).clone().sub(controls.target)
      controls.target.add(shift)
      camera.position.add(shift)
    }
    fitDepth()
    controls.update()
    const still = STILL * camera.position.distanceTo(controls.target)
    const moved = !!going || camera.position.distanceTo(lastPosition) > still || controls.target.distanceTo(lastTarget) > still
    lastPosition.copy(camera.position)
    lastTarget.copy(controls.target)
    return moved
  }

  /* Look at `target` from `position` at once, letting go of anything. */
  function place(position, target) {
    letGo()
    camera.position.copy(position)
    controls.target.copy(target)
    controls.update()
  }

  return {
    controls, goTo, letGo, update, place,
    get busy() { return !!(going || followed) },
    // What is followed, or being flown to (the map's own item).
    get following() { return (followed && followed.item) || (going && going.item) || null },
    // Follow `item` at once, without a flight (a snapshot given back).
    follow(at, item, near = null) { going = null; followed = at ? { at, item, near } : null },
    distance() { return camera.position.distanceTo(controls.target) },
    dispose() {
      holder.removeEventListener('wheel', onWheel, { capture: true })
      dom.removeEventListener('pointerdown', onDown)
      controls.dispose()
    },
  }
}

