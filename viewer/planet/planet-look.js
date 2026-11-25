/* One look for a planet in every view (a consistent
 * visual): the galaxy map's planets around a star (galaxy-map.js), the
 * star-system map (system-map.js), and the globe view (globe-view.js).
 * Lit by its star, its axial tilt and rings, as the
 * star-system map drew it; its texture — the planet's map where it has one,
 * else one generated for its class — and its atmosphere glow and clouds, as
 * the galaxy map drew them. Each map keeps its own orbits.
 *
 * The builders take THREE as an argument; the generated textures are
 * planet-texture.js's.
 */

import { hashString, PALETTES, ProceduralPlanetTexture } from './planet-texture.js';

// The atmosphere by planet class: glow colour and outer radius in planet
// radii — a thin haze at the limb, not a shell around it (// Saturn's 1.3 read as an aura). A gas giant's bands are its clouds: no
// cloud layer over them. Classes not listed have none (nor clouds).
export const ATMOSPHERE = {
    'terrestrial-habitable': { colour: '#88CCFF', thickness: 1.05 },
    'terrestrial-desert': { colour: '#FFAA88', thickness: 1.03 },
    'gas-giant-cold': { colour: '#AACCFF', thickness: 1.03, clouds: false },
    'gas-giant-warm': { colour: '#FFCC88', thickness: 1.03, clouds: false },
    'volcanic': { colour: '#FF6633', thickness: 1.04 },
};
export const GLOW_OPACITY = 0.7;             // at the limb, fading to nothing at the outer radius
export const CLOUD_OPACITY = 0.6;
export const CLOUD_HEIGHT = 1.02;            // the cloud shell, in planet radii
export const RING_COLOUR = 0xd8ccb0;
export const RING_OPACITY = 0.8;
// Rings as scattered rocks, as the belts are drawn (a
// solid band looked odd): this many per square planet radius of the densest
// ring; a band's `density` (0.01–1) takes its share.
export const RING_DENSITY = 1500;

// A colour per class, for what a texture cannot carry: orbit lines, dots.
export const CLASS_COLOURS = {
    'terrestrial-habitable': 0x4a8fd8, 'terrestrial-desert': 0xd8a75a, 'terrestrial-barren': 0x9a9a9a,
    volcanic: 0xd0552d, 'ice-world': 0xcfe8ff, 'gas-giant-cold': 0x9fc3e8, 'gas-giant-warm': 0xe0b07a,
};

// A planet's class: its own; else, with a map, habitable; else unknown.
export function resolveClass(planet, hasMap = false) {
    if (planet.class) return planet.class;
    return hasMap ? 'terrestrial-habitable' : 'unknown';
}

/* The cloud layer's texture: white, its opacity from value noise sampled
 * on the sphere (ProceduralPlanetTexture._noise3), squeezed north–south so
 * the clouds run in bands. Ellipses painted on the flat texture would end
 * in wedges round the poles, which grow as one zooms in, and in hard lines
 * where they meet the texture's edges. */
function cloudCanvas(width, height) {
    const P = ProceduralPlanetTexture;
    const rand = P._seededRandom(42);              // the same clouds on every planet, as before
    const seeds = [0, 1, 2, 3].map(() => Math.floor(rand() * 4294967296) | 0);
    const at = P._spherePoints(width, height);
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    const image = ctx.createImageData(width, height);
    const d = image.data;
    for (let i = 0; i < width * height; i++) {
        const x = at[i * 3], y = at[i * 3 + 1], z = at[i * 3 + 2];
        let sum = 0, amp = 1, total = 0, f = 2.2;
        for (let o = 0; o < seeds.length; o++) {
            sum += P._noise3(x * f, y * f * 2.5, z * f, seeds[o]) * amp;
            total += amp;
            amp *= 0.5;
            f *= 2;
        }
        const t = Math.min(1, Math.max(0, (sum / total - 0.52) / 0.2));
        d[i * 4] = d[i * 4 + 1] = d[i * 4 + 2] = 255;
        d[i * 4 + 3] = Math.round(t * t * (3 - 2 * t) * 0.55 * 255);
    }
    ctx.putImageData(image, 0, 0);
    return canvas;
}

// ── Three.js ─────────────────────────────────────────────────────────────────

const classTextures = new Map();
// A class texture's widths, and the globe's radius on screen (pixels) from
// which the next is drawn: more detail as a planet comes close.
const TEXTURE_SIZES = [128, 512, 1024, 2048];
const TEXTURE_FROM = [0, 10, 120, 320];

/* Sharper textures, made one at a time — the largest on screen first — so
 * that frames keep coming while planets come close; made at once, a flight
 * past a planet and its moons stalled for seconds. A run may return a
 * promise (made in the worker): the next waits for it. */
const upgrades = new Map();             // globe → { pixels, run }
let upgrading = false;
function nextFrame(work) {
    requestAnimationFrame(() => setTimeout(work, 0));
}
function requestUpgrade(globe, pixels, run) {
    upgrades.set(globe, { pixels, run });
    if (!upgrading) {
        upgrading = true;
        nextFrame(nextUpgrade);
    }
}
function nextUpgrade() {
    let best = null;
    for (const entry of upgrades) if (!best || entry[1].pixels > best[1].pixels) best = entry;
    if (!best) {
        upgrading = false;
        return;
    }
    upgrades.delete(best[0]);
    Promise.resolve(best[1].run()).then(() => {
        redraw();
        if (upgrades.size) nextFrame(nextUpgrade);
        else upgrading = false;
    });
}
let cloudTexture = null;

/* A map that draws only when something changes (the system map) is told
 * that a globe changed on its own: a sharper texture, its relief loaded. */
function redraw() {
    globalThis.dispatchEvent?.(new Event('space-redraw'));
}

/* The generated texture for a planet of a class and look (PALETTES; seeded,
 * so the same planet looks the same in every view), `size` wide; kept per
 * all three. */
export function classTexture(THREE, planetClass, look, size = TEXTURE_SIZES[0]) {
    const key = `${planetClass}|${look}|${size}`;
    if (!classTextures.has(key)) {
        const texture = new THREE.CanvasTexture(ProceduralPlanetTexture.canvas(planetClass, look, size));
        texture.anisotropy = 4;
        texture.colorSpace = THREE.SRGBColorSpace;
        classTextures.set(key, texture);
    }
    return classTextures.get(key);
}

/* Free the sharper class textures and the relief maps, which are otherwise
 * kept for the whole visit (a 2048-wide texture is 8 MB, more with its
 * mipmaps): a map calls this when it is destroyed. The smallest class
 * textures stay, as cheap as they are common. A globe still showing a freed
 * texture keeps it, and three uploads it again when that globe is drawn. */
export function releaseTextures() {
    for (const [key, texture] of classTextures) {
        if (key.endsWith(`|${TEXTURE_SIZES[0]}`)) continue;
        texture.dispose();
        classTextures.delete(key);
    }
    for (const relief of reliefs.values()) relief.then(texture => texture?.dispose());
    reliefs.clear();
}

/* The same, made in a worker (texture-worker.js): a 2048-wide texture took tens of
 * milliseconds, one frame's hitch as a planet came close. Where a worker
 * cannot draw (no OffscreenCanvas), or fails, made here as before. */
let worker = null;
let workerBroken = typeof Worker === 'undefined' || typeof OffscreenCanvas === 'undefined';
const jobs = new Map();                 // id → done(bitmap | null)
let jobId = 0;
function textureWorker() {
    if (worker || workerBroken) return worker;
    try {
        worker = new Worker(new URL('./texture-worker.js', import.meta.url), { type: 'module' });
    } catch {
        workerBroken = true;
        return null;
    }
    worker.onmessage = ({ data }) => {
        const done = jobs.get(data.id);
        jobs.delete(data.id);
        if (done) done(data.bitmap);
    };
    worker.onerror = () => {
        workerBroken = true;
        worker = null;
        for (const done of jobs.values()) done(null);
        jobs.clear();
    };
    return worker;
}
const making = new Map();               // key → Promise<Texture>, while in the worker
function classTextureLater(THREE, planetClass, look, size) {
    const key = `${planetClass}|${look}|${size}`;
    if (classTextures.has(key)) return Promise.resolve(classTextures.get(key));
    const w = textureWorker();
    if (!w) return Promise.resolve(classTexture(THREE, planetClass, look, size));
    if (!making.has(key)) {
        making.set(key, new Promise(resolve => {
            const id = ++jobId;
            jobs.set(id, bitmap => {
                making.delete(key);
                if (!bitmap) {
                    resolve(classTexture(THREE, planetClass, look, size));
                    return;
                }
                const texture = new THREE.Texture(bitmap);
                texture.flipY = false;                  // flipped in the worker
                texture.anisotropy = 4;
                texture.colorSpace = THREE.SRGBColorSpace;
                texture.needsUpdate = true;
                classTextures.set(key, texture);
                resolve(texture);
            });
            w.postMessage({ id, planetClass, look, size });
        }));
    }
    return making.get(key);
}

/* The axial tilt as a turn of the planet's pole: `tilt` from the orbit's
 * normal toward `tilt_bearing` — in the scene's axes (galaxy x, height,
 * -y), as both maps place things. */
/* A planet's rings as bands, innermost first: one band as a bare object, an
 * older form, reads as one band (galaxy.bodies.ring_bands). */
export function ringBands(planet) {
    const rings = planet.rings;
    if (!rings) return [];
    return Array.isArray(rings) ? rings : [rings];
}

export function tiltQuaternion(THREE, planet) {
    const rad = Math.PI / 180, t = (planet.tilt || 0) * rad, b = (planet.tilt_bearing || 0) * rad;
    const pole = new THREE.Vector3(Math.sin(t) * Math.cos(b), Math.cos(t), -Math.sin(t) * Math.sin(b)).normalize();
    return new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), pole);
}

/* A planet's rings as rocks in its equator, evenly over each band's area,
 * a pixel or two each whatever the distance, as an asteroid belt's; each a
 * little lighter or darker. Seeded by the planet's name: the same each time. */

// ── shadows ─────────────────
// Worked out in the shaders, exactly at any scale — shadow maps cannot span
// a moon's surface and a system's 1,000 AU. Per light: each star of a
// binary casts its own. What a globe's surface checks toward each light:
// the spheres that may stand in the way (setShadows), each by the share of
// the star's disc it hides, and its own rings, each band by its density.
export const OCCLUDERS = 8              // spheres a globe checks, the nearest to its light
const RING_BANDS = 4                    // bands a ring shadow knows
const RING_SHADOW = 0.8                 // the densest band takes this much of the light
const ringShadow = { value: RING_SHADOW }
const SUNS = 2                          // stars the rings check the planet's shadow toward

const shadowFunction = `
uniform vec4 shadowOccluders[${OCCLUDERS}];   // view-space centre, radius
uniform int shadowOccluderCount;
uniform vec3 shadowSunAt[${SUNS}];            // view space, where each star is drawn
uniform vec4 shadowSun[${SUNS}];              // view-space centre, radius: where it truly is, seen from here
uniform int shadowSunCount;
uniform vec3 shadowRingCentre;                // view space
uniform vec3 shadowRingNormal;                // view space
uniform float shadowRingScale;                // world units per planet radius
uniform vec3 shadowBands[${RING_BANDS}];      // inner, outer (planet radii), density
uniform int shadowBandCount;
uniform float shadowRingStrength;
// The share of a star's disc (angular radius a) that a disc of angular
// radius b, its centre th away, hides: the lens where the two overlap.
float covered(float a, float b, float th) {
    if (th >= a + b) return 0.0;
    if (a < 1e-9) return 1.0;                 // a point of light: hidden or not
    if (th <= abs(a - b)) return b >= a ? 1.0 : b * b / (a * a);
    float a2 = a * a, b2 = b * b, t2 = th * th;
    float lens = a2 * acos(clamp((t2 + a2 - b2) / (2.0 * th * a), -1.0, 1.0))
               + b2 * acos(clamp((t2 + b2 - a2) / (2.0 * th * b), -1.0, 1.0))
               - 0.5 * sqrt(max(0.0, (a + b - th) * (th + a - b) * (th - a + b) * (th + a + b)));
    return clamp(lens / (PI * a2), 0.0, 1.0);
}
// How much of the light at view-space L reaches view-space P. The spheres
// are checked against the star where it truly stands and as large as it
// is (shadowSun, the one drawn nearest L), not where it is drawn: umbra,
// penumbra and a transit's slight dimming as they are.
float shadowAt(vec3 L, vec3 P) {
    vec3 toL = L - P;
    float dist = length(toL);
    vec3 d = toL / dist;
    vec3 S = L;
    float Rs = 0.0, nearest = 1e30;
    for (int k = 0; k < ${SUNS}; k++) {
        if (k >= shadowSunCount) break;
        float e = length(shadowSunAt[k] - L);
        if (e < nearest) { nearest = e; S = shadowSun[k].xyz; Rs = shadowSun[k].w; }
    }
    vec3 toS = S - P;
    float sDist = length(toS);
    vec3 s = toS / sDist;
    float sunAngle = asin(min(Rs / sDist, 1.0));
    float shade = 1.0;
    for (int k = 0; k < ${OCCLUDERS}; k++) {
        if (k >= shadowOccluderCount) break;
        vec3 oc = shadowOccluders[k].xyz - P;
        float t = dot(oc, s);
        if (t <= 0.0 || t >= sDist) continue;
        float angle = asin(min(shadowOccluders[k].w / length(oc), 1.0));
        shade *= 1.0 - covered(sunAngle, angle, atan(length(cross(oc, s)), t));
    }
    if (shadowBandCount > 0) {
        vec3 n = shadowRingNormal;
        vec3 o = shadowRingCentre;
        float dn = dot(d, n);
        if (abs(dn) > 1e-6) {
            float t = dot(o - P, n) / dn;
            if (t > 0.0 && t < dist) {
                float r = length(P + t * d - o) / shadowRingScale;
                for (int k = 0; k < ${RING_BANDS}; k++) {
                    if (k >= shadowBandCount) break;
                    vec3 b = shadowBands[k];
                    if (r >= b.x && r <= b.y) shade *= 1.0 - shadowRingStrength * b.z;
                }
            }
        }
    }
    return shade;
}
`;

/* The uniforms a globe's shadows read, set by setShadows and each frame
 * from where the globe is. */
function shadowUniforms(THREE, bands) {
    const list = bands.slice(0, RING_BANDS).map(b => new THREE.Vector3(b.inner, b.outer,
        typeof b.density === 'number' ? b.density : 1));
    while (list.length < RING_BANDS) list.push(new THREE.Vector3());
    return {
        shadowOccluders: { value: Array.from({ length: OCCLUDERS }, () => new THREE.Vector4()) },
        shadowOccluderCount: { value: 0 },
        shadowSunAt: { value: Array.from({ length: SUNS }, () => new THREE.Vector3()) },
        shadowSun: { value: Array.from({ length: SUNS }, () => new THREE.Vector4()) },
        shadowSunCount: { value: 0 },
        shadowRingCentre: { value: new THREE.Vector3() },
        shadowRingNormal: { value: new THREE.Vector3(0, 1, 0) },
        shadowRingScale: { value: 1 },
        shadowBands: { value: list },
        shadowBandCount: { value: Math.min(bands.length, RING_BANDS) },
        shadowRingStrength: ringShadow,
    };
}

/* Where on the texture each pixel of a unit sphere lies, worked out per
 * pixel from its direction (the latitude–longitude of three's
 * SphereGeometry: x = −cos φ sin θ, z = sin φ sin θ), with the texture's
 * gradients from whichever longitude does not jump there: no seam where it
 * wraps from 1 to 0, and no pinch at the poles. */
const sphereLookup = `
varying vec3 vSphere;
vec2 sphereUv;
vec2 sphereDx;
vec2 sphereDy;
void sphereAt(vec3 p) {
    vec3 n = normalize(p);
    float u1 = fract(atan(n.z, -n.x) / (2.0 * PI));
    float u2 = fract(u1 + 0.5) - 0.5;
    float v = 1.0 - acos(clamp(n.y, -1.0, 1.0)) / PI;
    vec2 g1 = vec2(dFdx(u1), dFdy(u1)), g2 = vec2(dFdx(u2), dFdy(u2));
    vec2 g = dot(g1, g1) <= dot(g2, g2) ? g1 : g2;
    // At a pole every longitude meets in a pixel: the gradient blows up and
    // a coarse level of the texture — blurred across latitude as well, down
    // into Greenland — showed there as a grey spot. Capped at a few texels,
    // the pole samples its own rows, which are one colour on a map and all
    // but one on a generated texture.
    g *= min(1.0, 0.004 / max(length(g), 1e-6));
    sphereUv = vec2(u1, v);
    sphereDx = vec2(g.x, dFdx(v));
    sphereDy = vec2(g.y, dFdy(v));
}
`;

/* Real terrain up close: the height map raised along the
 * normal, sea level flat — on the outline, mountains; the bump map still
 * shades them. `reliefAmount` is the highest point's height in planet
 * radii, 0 while the globe is small on screen (and for the clouds). */
const reliefVertex = () => `
uniform sampler2D reliefMap;
uniform float reliefAmount;
float reliefAt(vec3 p) {
    if (reliefAmount <= 0.0) return 0.0;
    vec3 n = normalize(p);
    vec2 uv = vec2(fract(atan(n.z, -n.x) / (2.0 * PI)), 1.0 - acos(clamp(n.y, -1.0, 1.0)) / PI);
    float h = texture2D(reliefMap, uv).r;
    return reliefAmount * max(0.0, (h - ${SEA_LEVEL.toFixed(3)}) / ${(1 - SEA_LEVEL).toFixed(3)});
}
`;
// The highest point raised to this share of the radius: about ten times
// true for Earth (Everest is 0.0014), or no mountain would show at all.
const RELIEF_HEIGHT = 0.015;
// The globe's radius on screen (pixels) between which the terrain rises.
const RELIEF_FROM = [250, 600];

/* A globe's lit material (the surface, the clouds): its texture looked up
 * by sphereLookup, and each point light dimmed by shadowAt. */
function globeMaterial(THREE, material, uniforms) {
    material.onBeforeCompile = shader => {
        Object.assign(shader.uniforms, uniforms);
        shader.vertexShader = shader.vertexShader
            .replace('#include <common>', '#include <common>\nvarying vec3 vSphere;')
            .replace('#include <common>', '#include <common>\n' + reliefVertex())
            .replace('#include <begin_vertex>', '#include <begin_vertex>\nvSphere = position;\ntransformed += normal * reliefAt(position);');
        shader.fragmentShader = shader.fragmentShader
            .replace('#include <common>', '#include <common>\n' + sphereLookup)
            .replace('#include <bumpmap_pars_fragment>', THREE.ShaderChunk.bumpmap_pars_fragment
                .replace(/dFdx\( vBumpMapUv \)/g, 'sphereDx').replace(/dFdy\( vBumpMapUv \)/g, 'sphereDy')
                .replace(/vBumpMapUv/g, 'sphereUv')
                .replace(/texture2D\( bumpMap, ([^)]*?) \)/g, 'textureGrad( bumpMap, $1, sphereDx, sphereDy )'))
            .replace('#include <map_fragment>', THREE.ShaderChunk.map_fragment
                .replace('texture2D( map, vMapUv )', 'textureGrad( map, sphereUv, sphereDx, sphereDy )'))
            .replace('void main() {', shadowFunction + '\nvoid main() {\n\tsphereAt(vSphere);')
            .replace('#include <lights_fragment_begin>', THREE.ShaderChunk.lights_fragment_begin.replace(
                'getPointLightInfo( pointLight, geometryPosition, directLight );',
                'getPointLightInfo( pointLight, geometryPosition, directLight );\n' +
                '\t\tdirectLight.color *= shadowAt( pointLight.position, geometryPosition );'));
    };
    // One program for every globe: the uniforms differ, the code does not.
    material.customProgramCacheKey = () => 'globe-shadows';
    return material;
}

/* The rings as rocks that the planet's shadow darkens: toward each star,
 * a rock behind the planet gets none of its light. */
const rockVertex = `
    #include <common>
    #include <logdepthbuf_pars_vertex>
    uniform float size;
    uniform vec3 suns[${SUNS}];
    uniform int sunCount;
    varying vec3 vColour;
    varying float vLit;
    void main() {
        vec4 world = modelMatrix * vec4(position, 1.0);
        vec3 centre = (modelMatrix * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
        float R = length(modelMatrix[0].xyz);
        float lit = sunCount > 0 ? 0.0 : 1.0;
        for (int k = 0; k < ${SUNS}; k++) {
            if (k >= sunCount) break;
            vec3 d = normalize(suns[k] - world.xyz);
            float t = dot(centre - world.xyz, d);
            float miss = length(centre - world.xyz - t * d);
            lit += (t > 0.0 && miss < R) ? 0.0 : 1.0 / float(sunCount);
        }
        vLit = lit;
        vColour = color;
        gl_PointSize = size;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        #include <logdepthbuf_vertex>
    }`;
const rockFragment = `
    #include <common>
    #include <logdepthbuf_pars_fragment>
    uniform float opacity;
    varying vec3 vColour;
    varying float vLit;
    void main() {
        #include <logdepthbuf_fragment>
        gl_FragColor = vec4(vColour * (0.12 + 0.88 * vLit), opacity);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
    }`;

/* The rings up close: a sheet under the rocks, fading in as
 * the rings grow on screen, so that they stay rings rather than falling
 * apart into sparse dots — opaque by each band's density, with fine
 * ringlets across it, and dark where the planet hides a star. Its bands,
 * suns and fade shared with the rocks' uniforms. */
const SHEET_FROM = [90, 260]            // the rings' outer radius on screen, pixels: the sheet fades in between
const sheetVertex = `
    #include <common>
    #include <logdepthbuf_pars_vertex>
    varying vec2 vAt;                   // in the rings' plane, planet radii
    varying vec3 vWorld;
    varying vec3 vCentre;               // the planet's centre and radius, world
    varying float vRadius;
    void main() {
        vAt = position.xy;
        vWorld = (modelMatrix * vec4(position, 1.0)).xyz;
        vCentre = (modelMatrix * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
        vRadius = length(modelMatrix[0].xyz);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        #include <logdepthbuf_vertex>
    }`;
const sheetFragment = `
    #include <common>
    #include <logdepthbuf_pars_fragment>
    uniform vec3 bands[${RING_BANDS}];
    uniform int bandCount;
    uniform vec3 suns[${SUNS}];
    uniform int sunCount;
    uniform float fade;
    uniform vec3 colour;
    uniform float seed;
    varying vec2 vAt;
    varying vec3 vWorld;
    varying vec3 vCentre;
    varying float vRadius;
    float ripple(float x) {             // 1D value noise
        float i = floor(x), f = fract(x);
        float a = fract(sin(i * 127.1 + seed) * 43758.5453), b = fract(sin((i + 1.0) * 127.1 + seed) * 43758.5453);
        return mix(a, b, f * f * (3.0 - 2.0 * f));
    }
    void main() {
        #include <logdepthbuf_fragment>
        float r = length(vAt), density = 0.0;
        for (int k = 0; k < ${RING_BANDS}; k++) {
            if (k >= bandCount) break;
            vec3 b = bands[k];
            float edge = 0.008;
            density += b.z * smoothstep(b.x, b.x + edge, r) * (1.0 - smoothstep(b.y - edge, b.y, r));
        }
        float ringlets = 0.55 + 0.3 * ripple(r * 140.0) + 0.15 * ripple(r * 900.0);
        float alpha = 0.8 * density * ringlets * fade;
        if (alpha < 0.003) discard;
        // Dark where the planet stands between it and a star.
        vec3 centre = vCentre;
        float R = vRadius;
        float lit = sunCount > 0 ? 0.0 : 1.0;
        for (int k = 0; k < ${SUNS}; k++) {
            if (k >= sunCount) break;
            vec3 d = normalize(suns[k] - vWorld);
            float t = dot(centre - vWorld, d);
            float miss = length(centre - vWorld - t * d);
            lit += (t > 0.0 && miss < R) ? 0.0 : 1.0 / float(sunCount);
        }
        vec3 tone = colour * (0.8 + 0.4 * ripple(r * 60.0 + 7.0));
        gl_FragColor = vec4(tone * (0.12 + 0.88 * lit), alpha);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
    }`;

function ringSheet(THREE, planet, bands, rockUniforms) {
    const list = bands.slice(0, RING_BANDS).map(b => new THREE.Vector3(b.inner, b.outer,
        typeof b.density === 'number' ? b.density : 1));
    while (list.length < RING_BANDS) list.push(new THREE.Vector3());
    let seed = 0;
    for (const c of String(planet.name || planet.id || 'ring')) seed = (seed * 31 + c.charCodeAt(0)) % 1000;
    const material = new THREE.ShaderMaterial({
        vertexShader: sheetVertex, fragmentShader: sheetFragment,
        uniforms: { bands: { value: list }, bandCount: { value: Math.min(bands.length, RING_BANDS) },
            suns: rockUniforms.suns, sunCount: rockUniforms.sunCount, fade: { value: 0 },
            colour: { value: new THREE.Color(RING_COLOUR) }, seed: { value: seed } },
        transparent: true, depthWrite: false, side: THREE.DoubleSide,
    });
    const inner = Math.min(...bands.map(b => b.inner)), outer = Math.max(...bands.map(b => b.outer));
    const sheet = new THREE.Mesh(new THREE.RingGeometry(inner, outer, 256, 1), material);
    sheet.rotation.x = -Math.PI / 2;
    sheet.userData.outer = outer;
    return sheet;
}

function ringRocks(THREE, planet, bands) {
    let seed = 0;
    for (const c of String(planet.name || planet.id || 'ring')) seed = (seed * 31 + c.charCodeAt(0)) >>> 0;
    const rand = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
    const base = new THREE.Color(RING_COLOUR), positions = [], colours = [];
    for (const band of bands) {
        const span = band.outer ** 2 - band.inner ** 2;
        // Its density (galaxy.schema: 0.01–1, absent the densest) thins the rocks.
        const count = Math.max(1, Math.round(RING_DENSITY * span * (typeof band.density === 'number' ? band.density : 1)));
        for (let k = 0; k < count; k++) {
            const r = Math.sqrt(band.inner ** 2 + rand() * span), angle = rand() * 2 * Math.PI;
            positions.push(r * Math.cos(angle), (rand() - 0.5) * 0.004, r * Math.sin(angle));
            const shade = 0.75 + 0.5 * rand();
            colours.push(base.r * shade, base.g * shade, base.b * shade);
        }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(colours, 3));
    const material = new THREE.ShaderMaterial({
        vertexShader: rockVertex, fragmentShader: rockFragment, vertexColors: true,
        uniforms: { size: { value: 1.5 }, opacity: { value: RING_OPACITY },
            suns: { value: Array.from({ length: SUNS }, () => new THREE.Vector3()) }, sunCount: { value: 0 } },
        transparent: true, depthWrite: false,
    });
    const rocks = new THREE.Points(geometry, material);
    // A rock a pixel and a half across, on any screen.
    rocks.onBeforeRender = renderer => { material.uniforms.size.value = 1.5 * renderer.getPixelRatio(); };
    return rocks;
}

/* The atmosphere's glow: the far side of a shell just above the surface,
 * brightest where the line of sight grazes the planet's rim and fading to
 * nothing at the shell's edge. Seen from outside, the planet hides the rest.
 * The depth chunks keep it right under a logarithmic depth buffer (the
 * star-system map's). */
function haze(THREE, air) {
    const rim = Math.sqrt(1 - 1 / (air.thickness * air.thickness));   // |cos| between view and shell normal at the planet's rim
    return new THREE.ShaderMaterial({
        // `sun`: where its star is, in the world; `lit` 1 once it is set
        // (setLight), else the haze glows all round, as before.
        uniforms: { colour: { value: new THREE.Color(air.colour) }, rim: { value: rim }, strength: { value: GLOW_OPACITY },
            sun: { value: new THREE.Vector3() }, lit: { value: 0 } },
        vertexShader: `
            #include <common>
            #include <logdepthbuf_pars_vertex>
            uniform vec3 sun;
            varying vec3 vNormal;
            varying vec3 vView;
            varying float vDay;
            void main() {
                vec4 at = modelViewMatrix * vec4(position, 1.0);
                vNormal = normalize(normalMatrix * normal);
                vView = normalize(-at.xyz);
                // How much this part of the rim faces its star: 1 at noon, −1 at midnight.
                vec3 world = (modelMatrix * vec4(position, 1.0)).xyz;
                vec3 centre = (modelMatrix * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
                vDay = dot(normalize(world - centre), normalize(sun - centre));
                gl_Position = projectionMatrix * at;
                #include <logdepthbuf_vertex>
            }`,
        fragmentShader: `
            #include <common>
            #include <logdepthbuf_pars_fragment>
            uniform vec3 colour;
            uniform float rim;
            uniform float strength;
            uniform float lit;
            varying vec3 vNormal;
            varying vec3 vView;
            varying float vDay;
            void main() {
                #include <logdepthbuf_fragment>
                float graze = clamp(abs(dot(normalize(vNormal), normalize(vView))) / rim, 0.0, 1.0);
                // Lit by its star: bright over the day side, a faint trace over
                // the night side, and reddened toward the line between, where
                // its light crosses the most air (as a sunset's).
                float day = smoothstep(-0.35, 0.45, vDay);
                float dusk = (1.0 - smoothstep(0.0, 0.5, abs(vDay - 0.05))) * 0.6;
                vec3 tint = mix(colour, vec3(1.0, 0.45, 0.2), dusk);
                float light = mix(1.0, 0.08 + 0.92 * day, lit);
                gl_FragColor = vec4(mix(colour, tint, lit), strength * graze * graze * light);
            }`,
        transparent: true, blending: THREE.AdditiveBlending, side: THREE.BackSide, depthWrite: false,
    });
}

/* A planet (or moon) as every map draws it: a unit sphere, lit, its map or
 * its class's texture; its atmosphere's glow and clouds; its rings in planet
 * radii; turned by its tilt. Scale it to its size. `userData.clouds` is the
 * cloud shell, to turn a little faster than the planet. */
// ── relief ────────────────
// A mapped planet's height map (grey, sea level at the middle) as the
// globe's bump map, as the globe view shades it: the sea flat at its level, the bands blurred so slopes show
// across them rather than only at their edges.
export const SEA_LEVEL = 0.5;
export const RELIEF_WIDTH = 1024;           // texels across: enough at map scale
export const RELIEF_BLUR = 2;               // px at that width
export const BUMP_SCALE = 20;            // three.js bumps in screen space: tried 4 (faint), 20, 60 (dark at the limb)

const reliefs = new Map();                  // url → Promise<CanvasTexture | null>

export function reliefTexture(THREE, url) {
    if (!reliefs.has(url)) {
        reliefs.set(url, new Promise(resolve => {
            const img = new Image();
            img.crossOrigin = 'anonymous';
            img.onload = () => {
                const w = RELIEF_WIDTH, h = Math.max(2, Math.round(img.height * w / img.width));
                const flat = document.createElement('canvas');
                flat.width = w; flat.height = h;
                const fc = flat.getContext('2d', { willReadFrequently: true });
                fc.drawImage(img, 0, 0, w, h);
                const data = fc.getImageData(0, 0, w, h);
                const sea = Math.round(SEA_LEVEL * 255);
                for (let i = 0; i < data.data.length; i += 4) {
                    const v = Math.max(data.data[i], sea);
                    data.data[i] = data.data[i + 1] = data.data[i + 2] = v;
                }
                fc.putImageData(data, 0, 0);
                const out = document.createElement('canvas');
                out.width = w; out.height = h;
                const oc = out.getContext('2d');
                oc.filter = `blur(${RELIEF_BLUR}px)`;   // where unsupported, terraced but there
                oc.drawImage(flat, 0, 0);
                resolve(new THREE.CanvasTexture(out));
            };
            img.onerror = () => resolve(null);       // no height map: no relief
            img.src = url;
        }));
    }
    return reliefs.get(url);
}

/* A planet's look (galaxy.json `look`, drawn with its class): its palette
 * and its texture's seed. A planet without one is seeded by its name. */
export function lookOf(planet, name = planet.name) {
    if (Number.isInteger(planet.look)) return planet.look;
    return hashString(!name || name === '?' ? `planet-${planet.index || planet.id || 0}` : name);
}

/* A unit sphere from a cube, each face `n` × `n`, its points spread evenly
 * (the "spherified cube"): no pinch at the poles, as a sphere of latitude
 * rings has. Its texture is looked up per pixel (globeMaterial), so it has
 * no seam either. */
const cubeSpheres = new Map();
// Segments per cube face by the globe's radius on screen (pixels): smooth
// up close, cheap far off — the geometries shared, swapped per frame.
const GLOBE_SEGMENTS = [[0, 12], [100, 24], [250, 48], [500, 96]];
function cubeSphere(THREE, n) {
    if (cubeSpheres.has(n)) return cubeSpheres.get(n);
    const geometry = new THREE.BoxGeometry(2, 2, 2, n, n, n);
    geometry.clearGroups();
    const at = geometry.getAttribute('position'), normal = geometry.getAttribute('normal');
    for (let k = 0; k < at.count; k++) {
        const x = at.getX(k), y = at.getY(k), z = at.getZ(k);
        const sx = x * Math.sqrt(1 - y * y / 2 - z * z / 2 + y * y * z * z / 3);
        const sy = y * Math.sqrt(1 - z * z / 2 - x * x / 2 + z * z * x * x / 3);
        const sz = z * Math.sqrt(1 - x * x / 2 - y * y / 2 + x * x * y * y / 3);
        at.setXYZ(k, sx, sy, sz);
        normal.setXYZ(k, sx, sy, sz);
    }
    geometry.computeBoundingSphere();
    cubeSpheres.set(n, geometry);
    return geometry;
}

export function createGlobe(THREE, planet, { map = null, relief = null, name = planet.name } = {}) {
    const cls = resolveClass(planet, !!map);
    // Filtered along its rows as well as down them, as the class textures:
    // near the poles the rows are squeezed, and isotropic filtering blurs
    // across latitude as far as across longitude.
    if (map) map.anisotropy = Math.max(map.anisotropy || 1, 4);
    const texture = map || classTexture(THREE, cls, lookOf(planet, name));
    const bands = ringBands(planet);
    const shadows = shadowUniforms(THREE, bands);
    const terrain = { reliefMap: { value: null }, reliefAmount: { value: 0 } };
    const globe = new THREE.Mesh(cubeSphere(THREE, GLOBE_SEGMENTS[0][1]),
        globeMaterial(THREE, new THREE.MeshStandardMaterial({ map: texture, roughness: 0.9, metalness: 0 }),
            Object.assign({}, shadows, terrain)));
    // Relief only on a map's own texture: the class textures have no heights.
    // `userData.reliefReady` says whether it has any; `setRelief` turns it
    // off and on (a page's Relief button).
    let reliefOn = true;
    globe.userData.reliefReady = (relief && map ? reliefTexture(THREE, relief) : Promise.resolve(null)).then(bump => {
        if (!bump) return false;
        globe.material.bumpMap = bump;
        globe.material.bumpScale = reliefOn ? BUMP_SCALE : 0;
        terrain.reliefMap.value = bump;
        globe.material.needsUpdate = true;
        redraw();
        return true;
    });
    globe.userData.setRelief = on => {
        reliefOn = on;
        if (globe.material.bumpMap) globe.material.bumpScale = on ? BUMP_SCALE : 0;
    };
    const air = ATMOSPHERE[cls];
    if (air) {
        const shell = new THREE.Mesh(new THREE.SphereGeometry(air.thickness, 48, 32), haze(THREE, air));
        globe.add(shell);
        // Where its star is, in the world: the haze lights the day side.
        globe.userData.setLight = at => {
            shell.material.uniforms.sun.value.copy(at);
            shell.material.uniforms.lit.value = 1;
        };
    }
    if (air && air.clouds !== false) {
        if (!cloudTexture) {
            cloudTexture = new THREE.CanvasTexture(cloudCanvas(512, 256));
            cloudTexture.colorSpace = THREE.SRGBColorSpace;
        }
        const clouds = new THREE.Mesh(cubeSphere(THREE, 16),
            globeMaterial(THREE, new THREE.MeshStandardMaterial({ map: cloudTexture, transparent: true, opacity: CLOUD_OPACITY,
                depthWrite: false, roughness: 1, metalness: 0 }),
                // The same program as the surface's: its relief set to none, not left as the surface's.
                Object.assign({}, shadows, { reliefMap: { value: null }, reliefAmount: { value: 0 } })));
        clouds.scale.setScalar(CLOUD_HEIGHT);
        globe.add(clouds);
        globe.userData.clouds = clouds;
    }
    // Each band its own ring, the divisions between left open (Saturn's
    // Cassini Division).
    const rocks = bands.length ? ringRocks(THREE, planet, bands) : null;
    const sheet = rocks ? ringSheet(THREE, planet, bands, rocks.material.uniforms) : null;
    if (rocks) {
        rocks.renderOrder = 1;                     // over the sheet
        globe.add(sheet, rocks);
    }
    // Before each draw, in view space — worked out here, in double
    // precision, not on the GPU from world positions far from the origin:
    // its rings' plane and what stands between it and its stars. And a
    // sharper class texture once it is large on screen.
    // Copied into these slots, not kept: the caller reuses its vectors.
    const occludersWorld = Array.from({ length: OCCLUDERS }, () => ({ centre: new THREE.Vector3(), radius: 0 }));
    const sunsWorld = Array.from({ length: SUNS }, () => ({ at: new THREE.Vector3(), centre: new THREE.Vector3(), radius: 0 }));
    let textureStep = 0, pending = false;
    const centre = new THREE.Vector3(), axis = new THREE.Vector3(), viewNormal = new THREE.Matrix3();
    globe.onBeforeRender = (renderer, scene, camera) => {
        const view = camera.matrixWorldInverse;
        centre.setFromMatrixPosition(globe.matrixWorld);
        shadows.shadowRingCentre.value.copy(centre).applyMatrix4(view);
        axis.setFromMatrixColumn(globe.matrixWorld, 1);
        const scale = axis.length();
        shadows.shadowRingNormal.value.copy(axis).normalize().applyMatrix3(viewNormal.setFromMatrix4(view)).normalize();
        shadows.shadowRingScale.value = scale;
        occludersWorld.forEach((o, k) => {
            if (k >= shadows.shadowOccluderCount.value) return;
            const v = shadows.shadowOccluders.value[k];
            axis.copy(o.centre).applyMatrix4(view);
            v.set(axis.x, axis.y, axis.z, o.radius);
        });
        sunsWorld.forEach((o, k) => {
            if (k >= shadows.shadowSunCount.value) return;
            shadows.shadowSunAt.value[k].copy(o.at).applyMatrix4(view);
            axis.copy(o.centre).applyMatrix4(view);
            shadows.shadowSun.value[k].set(axis.x, axis.y, axis.z, o.radius);
        });
        if (!camera.isPerspectiveCamera) return;
        const distance = Math.max(camera.position.distanceTo(centre), 1e-9);
        const pixels = scale / (distance * Math.tan(camera.fov * Math.PI / 360)) * renderer.domElement.height / 2;
        if (terrain.reliefMap.value) {
            const rise = Math.min(1, Math.max(0, (pixels - RELIEF_FROM[0]) / (RELIEF_FROM[1] - RELIEF_FROM[0])));
            terrain.reliefAmount.value = reliefOn ? RELIEF_HEIGHT * rise : 0;
        }
        let n = GLOBE_SEGMENTS[0][1];
        for (const [from, segs] of GLOBE_SEGMENTS) if (pixels >= from) n = segs;
        if (globe.geometry !== cubeSphere(THREE, n)) globe.geometry = cubeSphere(THREE, n);
        if (sheet) {
            const ring = pixels * sheet.userData.outer;
            sheet.material.uniforms.fade.value = Math.min(1, Math.max(0, (ring - SHEET_FROM[0]) / (SHEET_FROM[1] - SHEET_FROM[0])));
        }
        if (map || pending || textureStep >= TEXTURE_SIZES.length - 1) return;
        if (pixels < TEXTURE_FROM[textureStep + 1]) return;
        // A step at a time, queued (requestUpgrade): the next once this is shown.
        pending = true;
        requestUpgrade(globe, pixels, () => {
            textureStep++;
            return classTextureLater(THREE, cls, lookOf(planet, name), TEXTURE_SIZES[textureStep]).then(texture => {
                globe.material.map = texture;
                pending = false;
            });
        });
    };
    /* What casts shadows on it: `suns`, the stars (world positions, as
     * drawn), for the planet's shadow on its rings; `occluders`, the spheres
     * that may stand between it and a star ({ centre, radius }, world), at
     * most OCCLUDERS — the caller picks the nearest; `trueSuns`, each star
     * of `suns` as it truly stands seen from this globe ({ centre, radius },
     * world). A map that draws sizes and distances on different scales
     * gives occluders and trueSuns in one frame true to scale around the
     * globe, so the eclipses come out as they are; without trueSuns a star
     * is a point where it is drawn. */
    globe.userData.setShadows = ({ suns = [], occluders = [], trueSuns = [] } = {}) => {
        const sunCount = Math.min(suns.length, SUNS);
        if (rocks) {
            const u = rocks.material.uniforms;
            for (let k = 0; k < sunCount; k++) u.suns.value[k].copy(suns[k]);
            u.sunCount.value = sunCount;
        }
        const occluderCount = Math.min(occluders.length, OCCLUDERS);
        for (let k = 0; k < occluderCount; k++) {
            occludersWorld[k].centre.copy(occluders[k].centre);
            occludersWorld[k].radius = occluders[k].radius;
        }
        shadows.shadowOccluderCount.value = occluderCount;
        const trueCount = Math.min(trueSuns.length, sunCount);
        for (let k = 0; k < trueCount; k++) {
            sunsWorld[k].at.copy(suns[k]);
            sunsWorld[k].centre.copy(trueSuns[k].centre);
            sunsWorld[k].radius = trueSuns[k].radius;
        }
        shadows.shadowSunCount.value = trueCount;
    };
    globe.quaternion.copy(tiltQuaternion(THREE, planet));
    globe.userData.planetClass = cls;
    return globe;
}
