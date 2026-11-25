/* The procedural galaxy's systems, opened one at a time (galaxy.procedural):
 * their details lie in blocks of 10 × 10 cells of its density
 * grid, procedural/<block>.json, by id — worked out from the id as
 * galaxy.procedural.group does.
 *
 *   const system = await proceduralSystem('data/procedural/', 'c123456-0')
 */
const GRID = 700
const GROUP = 10

export function proceduralBlock(id) {
  const cell = Number(id.slice(1, id.indexOf('-')))
  const pad = n => String(n).padStart(2, '0')
  return pad(Math.floor(cell / GRID / GROUP)) + pad(Math.floor((cell % GRID) / GROUP))
}

/* The system as the system map draws it, or null. */
export async function proceduralSystem(base, id) {
  if (!/^c\d{6}-\d{1,2}$/.test(id || '')) return null
  try {
    const response = await fetch(`${base}${proceduralBlock(id)}.json`)
    if (!response.ok) return null
    return (await response.json())[id] || null
  } catch {
    return null
  }
}
