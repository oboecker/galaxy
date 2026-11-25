/* A pulsar's beams: two cones from its poles along a magnetic
 * axis tilted from the spin axis, brightest at the star and fading outward,
 * added on. Shared by the galaxy and system maps.
 *
 *   const beams = createPulsarBeams(length, colour)   // a Group, the spin axis its y
 *   each frame: beams.userData.spin(angle)            // turns about the spin axis
 */
import * as THREE from 'three'

const vertexShader = `
  #include <common>
  #include <logdepthbuf_pars_vertex>
  varying float vAlong;             // 1 at the star, 0 at the beam's far end
  void main() {
    vAlong = uv.y;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    #include <logdepthbuf_vertex>
  }`

const fragmentShader = `
  #include <common>
  #include <logdepthbuf_pars_fragment>
  uniform vec3 colour;
  varying float vAlong;
  void main() {
    #include <logdepthbuf_fragment>
    gl_FragColor = vec4(colour * 0.9 * vAlong * vAlong, 1.0);
  }`

/* `length` in the map's units; the cones open to WIDTH of it. `tilt` turns
 * the magnetic axis off the spin axis (radians). */
const WIDTH = 0.14

export function createPulsarBeams(length, colour, tilt = 0.6) {
  const material = new THREE.ShaderMaterial({
    vertexShader, fragmentShader, uniforms: { colour: { value: new THREE.Color(colour) } },
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
  })
  const beams = new THREE.Group()
  for (const side of [1, -1]) {
    // A cone's tip is its top (uv.y 1): the upper one turned over, so both
    // have their tips at the star and widen outward.
    const cone = new THREE.Mesh(new THREE.ConeGeometry(length * WIDTH, length, 24, 1, true), material)
    cone.position.y = side * length / 2
    cone.rotation.x = side > 0 ? Math.PI : 0
    beams.add(cone)
  }
  beams.rotation.z = tilt
  const spinner = new THREE.Group()           // turns about the spin axis, its y
  spinner.add(beams)
  spinner.userData.spin = angle => { spinner.rotation.y = angle }
  return spinner
}
