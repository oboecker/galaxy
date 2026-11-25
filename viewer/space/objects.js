/* The objects a system map draws inside a system besides its bodies: points
 * of interest by kind (galaxy.objects). A kind's look is a shape in a colour
 * (`size` times its usual size); the engine's own kinds are POINTS, a
 * project's come with each system record (`objects`), and a host may draw a
 * kind its own way with `create`:
 *
 *   createSystemMap(holder, system, { objects: {
 *     relay: { create: THREE => new THREE.Mesh(new THREE.IcosahedronGeometry(1), new THREE.MeshBasicMaterial()) },
 *   } })
 *
 * An object is drawn at unit size; the map scales it with the view.
 */
import * as THREE from 'three'

export const SHAPES = {
  octahedron: () => new THREE.OctahedronGeometry(1),
  torus: () => new THREE.TorusGeometry(1, 0.3, 8, 24),
  box: () => new THREE.BoxGeometry(1.3, 1.3, 1.3),
  bar: () => new THREE.BoxGeometry(2, 0.8, 0.8),
  tetrahedron: () => new THREE.TetrahedronGeometry(1.1),
  sphere: () => new THREE.SphereGeometry(0.8, 12, 8),
  cone: () => new THREE.ConeGeometry(0.9, 2, 12),
}

// The engine's own kinds (galaxy.objects.POINTS), and a point of no kind.
export const POINTS = {
  point: { shape: 'octahedron', colour: '#ffd24a' },
  station: { label: 'Station', shape: 'octahedron', colour: '#ffd24a' },
  jumpgate: { label: 'Jumpgate', shape: 'torus', colour: '#7fe0ff' },
  outpost: { label: 'Outpost', shape: 'box', colour: '#b8e07a' },
  shipyard: { label: 'Shipyard', shape: 'bar', colour: '#ffa04a' },
  wreck: { label: 'Wreck', shape: 'tetrahedron', colour: '#9a8f86' },
  beacon: { label: 'Beacon', shape: 'sphere', colour: '#ff5a5a' },
}

/* The object for a point of `kind`: the host's (`hosted`, the map's
 * `objects` option), the project's (`declared`, the system record's), the
 * engine's, or a plain point. */
export function pointObject(kind, declared = {}, hosted = {}) {
  const own = hosted[kind]
  if (own && typeof own.create === 'function') return own.create(THREE)
  const look = own || declared[kind] || POINTS[kind] || POINTS.point
  const geometry = (SHAPES[look.shape] || SHAPES.octahedron)()
  if (look.size && look.size !== 1) geometry.scale(look.size, look.size, look.size)
  return new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: new THREE.Color(look.colour || POINTS.point.colour) }))
}
