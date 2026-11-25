/* A star's colour by its spectral class, two ways: physical, as
 * the star would look — pale, white-blue to orange-white; or saturated, so
 * the classes tell apart at a glance. The star-system map shows physical
 * colours, the galaxy map saturated ones; a round button
 * in each switches its own, remembered per map.
 *
 *   const mode = starColourMode('galaxy', 'saturated')
 *   starColour('G', mode) → 0xffdd66
 *   const remove = starColourButton(bar, 'galaxy', 'saturated', mode => …)
 */
export const PHYSICAL = { O: 0x9bb0ff, B: 0xaabfff, A: 0xcad7ff, F: 0xf8f7ff, G: 0xfff4e8, K: 0xffd2a1, M: 0xffcc6f }
export const SATURATED = { O: 0x4488ff, B: 0x6699ff, A: 0xaabbff, F: 0xffee99, G: 0xffdd66, K: 0xffaa44, M: 0xffcc6f }

import { toggleIcon } from './icons.js'

const KEY = 'space-star-colours-'      // localStorage, + the map: 'physical' or 'saturated'

export function starColourMode(map, fallback) {
  try { return localStorage.getItem(KEY + map) || fallback } catch { return fallback }
}

/* `cls`: a spectral class (G2V) or its letter; `unknown` for none. */
export function starColour(cls, mode, unknown = 0xffffff) {
  return (mode === 'physical' ? PHYSICAL : SATURATED)[String(cls || '')[0]] ?? unknown
}

/* The toggle, a round button appended to `bar`: pressed while the colours
 * are physical. `onChange(mode)` recolours the map. */
export function starColourButton(bar, map, fallback, onChange) {
  const button = document.createElement('button')
  button.type = 'button'
  button.className = 'space-tool space-colours-toggle'
  toggleIcon(button, 'contrast')
  const show = mode => {
    button.setAttribute('aria-pressed', String(mode === 'physical'))
    button.title = mode === 'physical' ? 'Star colours as they look — switch to saturated, the classes apart'
      : 'Star colours saturated, the classes apart — switch to as they look'
  }
  show(starColourMode(map, fallback))
  button.addEventListener('click', () => {
    const mode = starColourMode(map, fallback) === 'physical' ? 'saturated' : 'physical'
    try { localStorage.setItem(KEY + map, mode) } catch { /* private window: this page only */ }
    show(mode)
    onChange(mode)
  })
  bar.appendChild(button)
  return () => button.remove()
}
