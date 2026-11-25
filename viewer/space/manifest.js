/* What a build wrote for the maps (python -m galaxy.cli.build): its
 * manifest.json names each file relative to itself; this gives them back as
 * URLs, ready for the maps' options.
 *
 *   const { galaxy, system, calendar } = await loadManifest('data/manifest.json')
 *   createGalaxyMap(root, { config: galaxy })
 */
export async function loadManifest(url) {
  const base = new URL(url, location.href)
  const manifest = await (await fetch(base)).json()
  const resolve = value => (typeof value === 'string' ? new URL(value, base).href : value)
  const urls = config => Object.fromEntries(Object.entries(config || {}).map(([key, value]) => [key,
    key === 'layers' ? value.map(layer => ({ ...layer, url: resolve(layer.url) })) : resolve(value)]))
  return { galaxy: urls(manifest.galaxy), system: urls(manifest.system), calendar: manifest.calendar }
}
