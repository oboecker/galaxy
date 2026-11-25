/* The galaxy's band as a system sees it: the light of its stars along every
 * line of sight from where the system stands (the band
 * looked the same in every sky). From galaxy.procedural.glow's light map —
 * the systems' density on the plane and how they lie in height — summed out
 * along each direction, dimmed by the dust in front: from inside the bulge
 * half the sky glows, from the rim a thin band bright one way only, from
 * high above the plane the disc a wide glow below.
 *
 *   const glow = await loadGlow('data/glow.json')
 *   const band = bandLight(glow, system.at)
 *
 * The directions are the galaxy's own, round the system: longitude from the
 * way to the centre (laid into the plane), latitude from the plane, finest
 * near it, where the band is thin. No three.js: sky.js turns them into the
 * system's axes.
 */

export const LONGITUDES = 128          // grid lines round the band
export const LATITUDES = 48            // cells from pole to pole
const STEPS = 128                      // samples along a line of sight
const NEAREST = 5, FARTHEST = 110000   // ly: from, to
// Dust: the light from farther away dimmed as e^(−DUST · systems passed per
// ly²) — about e^−2 through the plane from Sol to the centre.
const DUST = 8e3

const loads = new Map()

/* The light map at `url`, fetched once a page; null if it cannot be. */
export function loadGlow(url) {
  if (!loads.has(url)) {
    loads.set(url, fetch(url).then(r => (r.ok ? r.json() : null)).catch(() => null))
  }
  return loads.get(url)
}

/* Latitude of grid line `i` (0 … LATITUDES), radians: denser near the plane. */
export function latitude(i) {
  const s = -1 + 2 * i / LATITUDES
  return Math.sign(s) * s * s * Math.PI / 2
}

/* The light of the galaxy from `at` ([x, y, z], ly), at each grid node:
 * (LATITUDES + 1) × LONGITUDES, latitude by latitude; in systems per ly²
 * (their light, summed). With the frame the directions are in: `across`
 * (to the centre, in the plane), `along`, `pole`, as galactic vectors. */
export function bandLight(glow, at) {
  const n = glow.cells, half = glow.radius, step = 2 * half / n
  const density = glow.density, scale = glow.scale
  const { mean, sigma, bulge, bulge_radius: bulgeRadius } = glow.height
  const r0 = Math.hypot(at[0], at[1])
  const across = r0 > 1 ? [-at[0] / r0, -at[1] / r0, 0] : [1, 0, 0]
  const along = [-across[1], across[0], 0]
  const pole = [0, 0, 1]
  // Along a line: the distances sampled and each one's share of the line.
  const ratio = Math.pow(FARTHEST / NEAREST, 1 / STEPS)
  const mids = new Float64Array(STEPS), widths = new Float64Array(STEPS)
  for (let k = 0; k < STEPS; k++) {
    const a = NEAREST * ratio ** k, b = a * ratio
    mids[k] = (a + b) / 2
    widths[k] = b - a
  }
  function surface(x, y) {
    const fx = (x + half) / step - 0.5, fy = (y + half) / step - 0.5
    const ix = Math.floor(fx), iy = Math.floor(fy)
    if (ix < -1 || iy < -1 || ix >= n || iy >= n) return 0
    const tx = fx - ix, ty = fy - iy
    const at = (i, j) => (i < 0 || j < 0 || i >= n || j >= n ? 0 : density[j * n + i])
    return scale * ((at(ix, iy) * (1 - tx) + at(ix + 1, iy) * tx) * (1 - ty)
      + (at(ix, iy + 1) * (1 - tx) + at(ix + 1, iy + 1) * tx) * ty)
  }
  const light = new Float32Array((LATITUDES + 1) * LONGITUDES)
  const root = Math.sqrt(2 * Math.PI)
  const ceiling = (6 * sigma + Math.abs(mean)) * (1 + bulge)
  for (let i = 0; i <= LATITUDES; i++) {
    const b = latitude(i), cb = Math.cos(b), sb = Math.sin(b)
    for (let j = 0; j < LONGITUDES; j++) {
      const l = 2 * Math.PI * j / LONGITUDES, cl = Math.cos(l), sl = Math.sin(l)
      const dx = cb * (cl * across[0] + sl * along[0])
      const dy = cb * (cl * across[1] + sl * along[1])
      const dz = sb * pole[2]
      let sum = 0, depth = 0
      for (let k = 0; k < STEPS; k++) {
        const s = mids[k]
        const x = at[0] + dx * s, y = at[1] + dy * s, z = at[2] + dz * s
        const r = Math.hypot(x, y)
        if (r > half) { if ((x * dx + y * dy) > 0) break; else continue }
        const thick = 1 + bulge * Math.exp(-((r / bulgeRadius) ** 2))
        const spread = sigma * thick, off = (z - mean * thick) / spread
        if (off > 6 || off < -6) {
          // Past the disc and leaving it, even where it is thickest: done.
          if (Math.abs(z) > ceiling && z * dz > 0) break
          continue
        }
        const rho = surface(x, y) * Math.exp(-0.5 * off * off) / (root * spread)
        const passed = rho * widths[k]
        sum += passed * Math.exp(-DUST * depth)
        depth += passed
      }
      light[i * LONGITUDES + j] = sum
    }
  }
  return { light, across, along, pole }
}
