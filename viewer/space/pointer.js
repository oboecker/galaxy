/* Clicks on a 3D map, as every map takes them: a click that stayed put picks what is under it — a drag to turn
 * or pan ends in a click too, and picks nothing; a click on nothing lets go;
 * Esc lets go, not while typing.
 *
 *   const detach = attachPointer(dom, { pick, onPick, onNothing, onEscape, live })
 */

const STILL_PIXELS = 4          // a press and release closer than this is a click

/* A touch screen (a phone, a tablet): taps, a finger to turn, two to pinch and pan. */
export const TOUCH = Boolean(globalThis.matchMedia && globalThis.matchMedia('(pointer: coarse)').matches)

/* How to steer a map, one line: `thing` is what a tap or click goes to. */
/* On a narrow screen an info box folds to its first lines (space.css,
 * .space-fold): a tap on it unfolds or folds it again — not one on a link
 * or a button in it. */
export function foldable(box) {
  const narrow = globalThis.matchMedia && globalThis.matchMedia('(max-width: 600px)')
  box.classList.add('space-fold')
  const tap = e => {
    if (!narrow || !narrow.matches || e.target.closest('a, button, select, input')) return
    box.classList.toggle('is-open')
  }
  box.addEventListener('click', tap)
  return () => box.removeEventListener('click', tap)
}

export function steeringHint(thing) {
  return TOUCH
    ? `Tap a ${thing} to go to it · drag to turn, pinch to zoom, two fingers to pan`
    : `Click a ${thing} to go to it · drag to turn, right-drag to pan, wheel to zoom (Shift: faster) · Esc lets go`
}

export function attachPointer(dom, { pick, onPick, onNothing = () => {}, onEscape = () => {}, live = () => true }) {
  let pressed = null
  const onDown = event => { pressed = [event.clientX, event.clientY] }
  const dragged = event => pressed && Math.hypot(event.clientX - pressed[0], event.clientY - pressed[1]) > STILL_PIXELS
  const onClick = event => {
    if (dragged(event)) return
    const item = pick(event)
    if (item) onPick(item, event)
    else onNothing(event)
  }
  const onKey = event => {
    if (event.key !== 'Escape' || !live()) return
    if (event.target.closest && event.target.closest('input, select, textarea')) return
    onEscape(event)
  }
  dom.addEventListener('pointerdown', onDown)
  dom.addEventListener('click', onClick)
  globalThis.addEventListener('keydown', onKey)
  return () => {
    dom.removeEventListener('pointerdown', onDown)
    dom.removeEventListener('click', onClick)
    globalThis.removeEventListener('keydown', onKey)
  }
}
