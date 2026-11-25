/* A planet's generated texture, by its class and look (planet-look.js
 * draws it): value noise on the sphere, then each class's features in one of
 * its palettes. Pure pixel work on 2D canvases — no Three.js, no page — so
 * that a worker can run it (texture-worker.js): on a page a canvas, in a worker an OffscreenCanvas.
 */

function newCanvas(width, height) {
    if (typeof document === 'undefined') return new OffscreenCanvas(width, height);
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    return canvas;
}

export function hashString(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) - hash) + str.codePointAt(i);
        hash = hash & hash;
    }
    return Math.abs(hash);
}

function latticeValue(h) {
    h = Math.imul(h ^ (h >>> 13), 1103515245);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

export const ProceduralPlanetTexture = {

    // Seeded pseudo-random number generator (Mulberry32).
    // Returns a function that yields numbers in [0,1).
    _seededRandom(seed) {
        let s = Math.trunc(seed);
        return function () {
            s = Math.trunc(s + 0x6D2B79F5);
            let t = Math.imul(s ^ (s >>> 15), 1 | s);
            t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
            return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        };
    },

    // Value noise on the sphere itself: sampled at each pixel's
    // point on the unit sphere, not on the flat texture — no seam where the
    // texture wraps, no rays where its columns meet at the poles, and the
    // same pattern at any texture size. One seed per octave from `rand`.
    // A lattice point's value: its coordinates hashed with the seed, 0–1.
    // Written out, without a closure per corner: called eight times a
    // pixel an octave, it was most of a texture's time.
    _noise3(x, y, z, seed) {
        const ix = Math.floor(x), iy = Math.floor(y), iz = Math.floor(z);
        const fx = x - ix, fy = y - iy, fz = z - iz;
        const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy), sz = fz * fz * (3 - 2 * fz);
        const X0 = Math.imul(ix, 374761393), X1 = Math.imul(ix + 1, 374761393);
        const Y0 = Math.imul(iy, 668265263), Y1 = Math.imul(iy + 1, 668265263);
        const Z0 = Math.imul(iz, 1274126177) ^ seed, Z1 = Math.imul(iz + 1, 1274126177) ^ seed;
        const a = latticeValue(X0 ^ Y0 ^ Z0), b = latticeValue(X1 ^ Y0 ^ Z0);
        const c = latticeValue(X0 ^ Y1 ^ Z0), d = latticeValue(X1 ^ Y1 ^ Z0);
        const e = latticeValue(X0 ^ Y0 ^ Z1), f = latticeValue(X1 ^ Y0 ^ Z1);
        const g = latticeValue(X0 ^ Y1 ^ Z1), h = latticeValue(X1 ^ Y1 ^ Z1);
        const x00 = a + (b - a) * sx, x10 = c + (d - c) * sx, x01 = e + (f - e) * sx, x11 = g + (h - g) * sx;
        const y0 = x00 + (x10 - x00) * sy, y1 = x01 + (x11 - x01) * sy;
        return y0 + (y1 - y0) * sz;
    },

    // Each pixel's point on the unit sphere, as three's SphereGeometry maps a
    // texture (x = −cos φ sin θ, y = cos θ, z = sin φ sin θ; the top row
    // north): kept per size.
    _points: new Map(),
    _spherePoints(width, height) {
        const key = `${width}x${height}`;
        if (!this._points.has(key)) {
            const at = new Float32Array(width * height * 3);
            for (let y = 0; y < height; y++) {
                const theta = (y + 0.5) / height * Math.PI, st = Math.sin(theta), ct = Math.cos(theta);
                for (let x = 0; x < width; x++) {
                    const phi = (x + 0.5) / width * 2 * Math.PI, k = (y * width + x) * 3;
                    at[k] = -Math.cos(phi) * st;
                    at[k + 1] = ct;
                    at[k + 2] = Math.sin(phi) * st;
                }
            }
            this._points.set(key, at);
        }
        return this._points.get(key);
    },

    // Multi-octave fractal noise rendered onto a canvas, grey. `baseScale`
    // the first octave's cell in pixels of the 512-wide texture, as before.
    // A larger texture adds an octave per doubling, finer detail, a smaller
    // drops its finest; the extra octaves' seeds come from the last, not
    // from `rand`, so the features drawn after (craters, storms) stay put.
    _fractalNoise(width, height, rand, octaves = 4, baseScale = 64) {
        const canvas = newCanvas(width, height);
        const ctx = canvas.getContext('2d');
        const result = ctx.createImageData(width, height);
        const rd = result.data;
        const at = this._spherePoints(width, height);
        const seeds = [], freqs = [];
        let sc = baseScale;
        for (let o = 0; o < octaves; o++) {
            seeds.push(Math.floor(rand() * 4294967296) | 0);
            freqs.push(512 / (2 * Math.PI * sc));          // a cell of `sc` pixels at the equator of 512
            sc = Math.max(2, sc * 0.5);
        }
        const extra = Math.round(Math.log2(width / 512));
        for (let o = 0; o < extra; o++) {
            seeds.push(seeds[seeds.length - 1] ^ Math.imul(o + 1, 0x9E3779B9));
            freqs.push(freqs[freqs.length - 1] * 2);
        }
        const used = Math.max(1, Math.min(seeds.length, octaves + extra));
        for (let i = 0; i < width * height; i++) {
            const x = at[i * 3], y = at[i * 3 + 1], z = at[i * 3 + 2];
            let sum = 0, amp = 1, total = 0;
            for (let o = 0; o < used; o++) {
                sum += this._noise3(x * freqs[o], y * freqs[o], z * freqs[o], seeds[o]) * amp;
                total += amp;
                amp *= 0.5;
            }
            const v = Math.floor(sum / total * 255);
            rd[i * 4] = rd[i * 4 + 1] = rd[i * 4 + 2] = v;
            rd[i * 4 + 3] = 255;
        }
        ctx.putImageData(result, 0, 0);
        return canvas;
    },

    // Public entry point: the class's texture as a canvas (classTexture
    // wraps it for Three.js). `look` picks the class's palette (look modulo
    // their number) and seeds the noise: one number, stored with the planet,
    // for the same planet in every view however it is named.
    canvas(planetClass, look, size = 512) {
        const width = size;
        const height = size / 2;
        const rand = this._seededRandom(look);
        const palettes = PALETTES[planetClass] || PALETTES.unknown;
        const p = palettes[look % palettes.length];

        const generators = {
            'terrestrial-barren': () => this._genBarren(width, height, rand, p),
            'terrestrial-habitable': () => this._genHabitable(width, height, rand, p),
            'terrestrial-desert': () => this._genDesert(width, height, rand, p),
            'gas-giant-cold': () => this._genGasGiant(width, height, rand, p),
            'gas-giant-warm': () => this._genGasGiant(width, height, rand, p),
            'ice-world': () => this._genIceWorld(width, height, rand, p),
            'volcanic': () => this._genVolcanic(width, height, rand, p),
            'unknown': () => this._genBarren(width, height, rand, p)
        };
        return (generators[planetClass] || generators.unknown)();
    },

    // --- Per-class generators, their colours a palette's (PALETTES) ---

    // A pixel's colour: the palette's base, plus `range` scaled by the noise
    // value, plus `band` scaled by the band's.
    _mix(d, i, base, range, v, band = null, b = 0) {
        for (let c = 0; c < 3; c++) {
            d[i * 4 + c] = Math.max(0, Math.min(255, Math.floor(base[c] + range[c] * v + (band ? band[c] * b : 0))));
        }
    },

    // Features are placed in units of the 512 × 256 texture and drawn
    // scaled to the texture's size: the same
    // random numbers at any size, so a planet's sharper texture is the same
    // planet. Widened toward the poles by 1 / sin θ, where the texture is
    // squeezed on the sphere: a round crater stays round there.
    _scale(w) { return w / 512; },
    _widen(h, y) { return 1 / Math.max(0.25, Math.sin((y + 0.5) / h * Math.PI)); },

    // An ellipse blended toward a colour, `weight` its weight at the centre;
    // x, y, rx, ry in base units.
    _spot(d, w, h, x, y, rx, ry, colour, weight) {
        const k = this._scale(w), cx = x * k, cy = y * k;
        const prx = rx * k * this._widen(h, cy), pry = ry * k;
        for (let py = Math.floor(cy - pry); py <= Math.ceil(cy + pry); py++) {
            if (py < 0 || py >= h) continue;
            for (let px = Math.floor(cx - prx); px <= Math.ceil(cx + prx); px++) {
                const dist = ((px - cx) / prx) ** 2 + ((py - cy) / pry) ** 2;
                if (dist > 1) continue;
                const idx = (py * w + ((px % w) + w) % w) * 4;
                const blend = (1 - dist) * weight;
                for (let c = 0; c < 3; c++) d[idx + c] = Math.floor(d[idx + c] * (1 - blend) + colour[c] * blend);
            }
        }
    },

    // A disc at x, y (base units), `r` base units across its radius, each
    // pixel in it changed by `paint(idx, dist)`, dist 0 at the centre to 1.
    _disc(d, w, h, x, y, r, paint) {
        const k = this._scale(w), cx = x * k, cy = y * k;
        const pry = Math.max(0.5, r * k), prx = pry * this._widen(h, cy);
        for (let py = Math.floor(cy - pry); py <= Math.ceil(cy + pry); py++) {
            if (py < 0 || py >= h) continue;
            for (let px = Math.floor(cx - prx); px <= Math.ceil(cx + prx); px++) {
                const dist = Math.hypot((px - cx) / prx, (py - cy) / pry);
                if (dist > 1) continue;
                paint((py * w + ((px % w) + w) % w) * 4, dist);
            }
        }
    },

    // A random walk of `steps` steps of a base unit each, from x, y; each
    // stretch drawn as discs of radius `r` along it. Consumes 2 × steps
    // random numbers, at any size.
    _walk(d, w, h, x, y, steps, rand, r, paint) {
        const k = this._scale(w), stride = Math.max(1, Math.ceil(k));
        for (let s = 0; s < steps; s++) {
            const nx = x + Math.floor(rand() * 3) - 1, ny = Math.max(0, Math.min(255, y + Math.floor(rand() * 3) - 1));
            for (let t = 0; t < stride; t++) {
                const f = t / stride;
                this._disc(d, w, h, x + (nx - x) * f, y + (ny - y) * f, r, paint);
            }
            x = (nx + 512) % 512;
            y = ny;
        }
    },

    _genBarren(w, h, rand, p) {
        const noise = this._fractalNoise(w, h, rand, 5, 64);
        const ctx = noise.getContext('2d');
        const imgData = ctx.getImageData(0, 0, w, h);
        const d = imgData.data;

        for (let i = 0; i < w * h; i++) this._mix(d, i, p.base, p.range, d[i * 4] / 255);

        const craterCount = Math.floor((8 + rand() * 12) * (p.craters ?? 1));
        for (let c = 0; c < craterCount; c++) {
            const cx = Math.floor(rand() * 512);
            const cy = Math.floor(rand() * 256);
            const cr = 3 + Math.floor(rand() * 10);
            // A dark floor and a bright rim.
            this._disc(d, w, h, cx, cy, cr, (idx, dist) => {
                const shade = dist < 0.7 ? 0.7 : 1.15;
                for (let k = 0; k < 3; k++) d[idx + k] = Math.min(255, Math.floor(d[idx + k] * shade));
            });
        }

        ctx.putImageData(imgData, 0, 0);
        return noise;
    },

    // Habitable: oceans, lowlands, highlands, snow, polar ice
    _genHabitable(w, h, rand, p) {
        const noise = this._fractalNoise(w, h, rand, 5, 80);
        const ctx = noise.getContext('2d');
        const imgData = ctx.getImageData(0, 0, w, h);
        const d = imgData.data;

        // Second noise layer for terrain variation
        const terrainNoise = this._fractalNoise(w, h, rand, 3, 32);
        const tData = terrainNoise.getContext('2d').getImageData(0, 0, w, h).data;

        const seaLevel = p.sea;
        for (let i = 0; i < w * h; i++) {
            const elevation = d[i * 4] / 255;
            const terrain = tData[i * 4] / 255;

            if (elevation < seaLevel) {
                this._mix(d, i, p.ocean, p.oceanRange, elevation / seaLevel);
            } else {
                const landHeight = (elevation - seaLevel) / (1 - seaLevel);
                if (landHeight < 0.3) this._mix(d, i, p.low, p.lowRange, terrain);
                else if (landHeight < 0.7) this._mix(d, i, p.high, p.highRange, terrain);
                else {
                    const snow = (landHeight - 0.7) / 0.3;
                    this._mix(d, i, [120, 100, 80], [135, 155, 175], snow);
                }
            }

            const lat = Math.abs(Math.floor(i / w) / h - 0.5) * 2; // 0 at equator, 1 at poles
            if (lat > p.ice) {
                const iceBlend = Math.min(1, (lat - p.ice) / 0.15);
                d[i * 4]     = Math.floor(d[i * 4] * (1 - iceBlend) + 240 * iceBlend);
                d[i * 4 + 1] = Math.floor(d[i * 4 + 1] * (1 - iceBlend) + 245 * iceBlend);
                d[i * 4 + 2] = Math.floor(d[i * 4 + 2] * (1 - iceBlend) + 255 * iceBlend);
            }
        }

        ctx.putImageData(imgData, 0, 0);
        return noise;
    },

    // Desert: banded sand and rock
    _genDesert(w, h, rand, p) {
        const noise = this._fractalNoise(w, h, rand, 4, 48);
        const ctx = noise.getContext('2d');
        const imgData = ctx.getImageData(0, 0, w, h);
        const d = imgData.data;

        for (let i = 0; i < w * h; i++) {
            const v = d[i * 4] / 255;
            const band = Math.sin(Math.floor(i / w) / h * Math.PI * 6 + v * 3) * 0.5 + 0.5;
            this._mix(d, i, p.base, p.range, v, p.band, band);
        }

        ctx.putImageData(imgData, 0, 0);
        return noise;
    },

    // Gas giant: horizontal bands, turbulence, storms or a great spot
    _genGasGiant(w, h, rand, p) {
        const noise = this._fractalNoise(w, h, rand, 4, 64);
        const ctx = noise.getContext('2d');
        const imgData = ctx.getImageData(0, 0, w, h);
        const d = imgData.data;

        for (let i = 0; i < w * h; i++) {
            const v = d[i * 4] / 255;
            const y = Math.floor(i / w);
            const x = i % w;
            const band = Math.sin(y / h * Math.PI * p.bands + v * 2.5) * 0.5 + 0.5;
            // Fading toward the poles, where the texture's columns meet.
            const turbulence = Math.sin(x / w * Math.PI * 3 + v * 4) * 0.1 * Math.sin((y + 0.5) / h * Math.PI);
            this._mix(d, i, p.base, p.range, v + turbulence, p.band, band);
        }

        // Storms: a few pale ones, or one great spot
        const storms = p.greatSpot ? 1 : 2 + Math.floor(rand() * 3);
        for (let s = 0; s < storms; s++) {
            const rx = (p.greatSpot ? 12 : 8) + Math.floor(rand() * (p.greatSpot ? 18 : 15));
            this._spot(d, w, h, Math.floor(rand() * 512), Math.floor(64 + rand() * 128),
                rx, Math.floor(rx * 0.55), p.spot, p.greatSpot ? 0.55 : 0.35);
        }

        ctx.putImageData(imgData, 0, 0);
        return noise;
    },

    // Ice world: ice with cracks
    _genIceWorld(w, h, rand, p) {
        const noise = this._fractalNoise(w, h, rand, 5, 48);
        const ctx = noise.getContext('2d');
        const imgData = ctx.getImageData(0, 0, w, h);
        const d = imgData.data;

        for (let i = 0; i < w * h; i++) this._mix(d, i, p.base, p.range, d[i * 4] / 255);

        // Cracks, a random walk each, darkened toward the palette's crack colour
        const cracks = Math.floor((5 + rand() * 8) * (p.cracks ?? 1));
        for (let c = 0; c < cracks; c++) {
            const cx = Math.floor(rand() * 512);
            const cy = Math.floor(rand() * 256);
            const steps = 20 + Math.floor(rand() * 40);
            this._walk(d, w, h, cx, cy, steps, rand, 0.5, idx => {
                for (let k = 0; k < 3; k++) d[idx + k] = Math.floor(d[idx + k] * 0.45 + p.crack[k] * 0.55);
            });
        }

        ctx.putImageData(imgData, 0, 0);
        return noise;
    },

    // Volcanic: a dark or sulphurous surface with glowing fissures
    _genVolcanic(w, h, rand, p) {
        const noise = this._fractalNoise(w, h, rand, 5, 48);
        const ctx = noise.getContext('2d');
        const imgData = ctx.getImageData(0, 0, w, h);
        const d = imgData.data;

        for (let i = 0; i < w * h; i++) this._mix(d, i, p.base, p.range, d[i * 4] / 255);

        const fissures = 6 + Math.floor(rand() * 10);
        for (let f = 0; f < fissures; f++) {
            const fx = Math.floor(rand() * 512);
            const fy = Math.floor(rand() * 256);
            const steps = 15 + Math.floor(rand() * 30);
            const intensity = 0.6 + rand() * 0.4;
            // Glowing toward its line: each stretch adds, as the old stamps did.
            const k = this._scale(w), stride = Math.max(1, Math.ceil(k));
            this._walk(d, w, h, fx, fy, steps, rand, 2, (idx, dist) => {
                const glow = (1 - dist) * intensity / stride;
                for (let c = 0; c < 3; c++) d[idx + c] = Math.min(255, d[idx + c] + Math.floor(p.lava[c] * glow));
            });
        }

        ctx.putImageData(imgData, 0, 0);
        return noise;
    }
};

// Each class's palettes: a set of looks per class, one assigned to a planet
// by its `look`. The first of each is the class's default look.
// RGB: `base` at the noise's low end, plus `range` × the noise, plus `band` ×
// the band where a class has bands.
export const PALETTES = {
    'gas-giant-warm': [
        { name: 'Jupiter tan', base: [180, 120, 60], range: [25, 30, 20], band: [50, 40, 20], bands: 14, greatSpot: true, spot: [200, 80, 40] },
        { name: 'butterscotch', base: [196, 162, 104], range: [22, 20, 16], band: [30, 26, 18], bands: 18, spot: [230, 205, 160] },
        { name: 'rust', base: [128, 70, 42], range: [34, 26, 18], band: [52, 34, 18], bands: 12, greatSpot: true, spot: [80, 36, 26] },
        { name: 'cream', base: [206, 192, 166], range: [18, 18, 18], band: [30, 28, 24], bands: 20, spot: [182, 146, 104] },
        { name: 'hot Jupiter', base: [116, 50, 42], range: [30, 18, 16], band: [62, 38, 26], bands: 10, greatSpot: true, spot: [235, 190, 130] },
    ],
    'gas-giant-cold': [
        { name: 'pale blue', base: [100, 130, 180], range: [40, 50, 30], band: [80, 60, 40], bands: 12, spot: [220, 230, 255] },
        { name: 'Neptune blue', base: [38, 66, 166], range: [30, 40, 40], band: [40, 50, 52], bands: 10, greatSpot: true, spot: [20, 30, 90] },
        { name: 'Uranus cyan', base: [130, 190, 200], range: [22, 22, 18], band: [24, 20, 18], bands: 16, spot: [205, 238, 240] },
        { name: 'teal', base: [56, 126, 136], range: [30, 40, 30], band: [50, 50, 40], bands: 12, spot: [190, 235, 230] },
        { name: 'lavender', base: [128, 116, 168], range: [30, 30, 30], band: [50, 46, 40], bands: 14, spot: [225, 215, 245] },
    ],
    'terrestrial-barren': [
        { name: 'Mercury brown', base: [100, 85, 70], range: [80, 65, 50] },
        { name: 'moon grey', base: [98, 96, 94], range: [86, 84, 82] },
        { name: 'rust', base: [108, 66, 48], range: [72, 46, 32] },
        { name: 'basalt', base: [52, 50, 50], range: [58, 54, 50], craters: 1.4 },
        { name: 'ash', base: [148, 142, 132], range: [62, 60, 56], craters: 0.6 },
    ],
    'terrestrial-desert': [
        { name: 'ochre', base: [160, 100, 50], range: [60, 40, 30], band: [30, 15, 0] },
        { name: 'Mars red', base: [150, 68, 40], range: [60, 36, 24], band: [30, 12, 0] },
        { name: 'sand', base: [184, 152, 96], range: [48, 40, 30], band: [24, 20, 10] },
        { name: 'salt', base: [204, 194, 172], range: [36, 34, 30], band: [14, 14, 14] },
        { name: 'umber', base: [108, 74, 50], range: [50, 36, 26], band: [22, 12, 6] },
    ],
    'ice-world': [
        { name: 'blue-white', base: [180, 195, 210], range: [70, 55, 45], crack: [90, 120, 190] },
        { name: 'Europa', base: [190, 178, 156], range: [52, 46, 40], crack: [120, 60, 40], cracks: 2.5 },
        { name: 'green ice', base: [156, 198, 192], range: [62, 46, 46], crack: [60, 110, 110] },
        { name: 'dirty grey', base: [128, 142, 162], range: [62, 62, 60], crack: [60, 66, 80] },
        { name: 'pure white', base: [214, 220, 228], range: [36, 32, 26], crack: [150, 170, 210], cracks: 0.5 },
    ],
    'volcanic': [
        { name: 'basalt and red lava', base: [30, 20, 15], range: [40, 25, 20], lava: [200, 80, 20] },
        { name: 'Io sulphur', base: [176, 156, 58], range: [52, 50, 30], lava: [150, 40, 0] },
        { name: 'ash and orange lava', base: [70, 64, 60], range: [48, 44, 40], lava: [210, 110, 20] },
        { name: 'obsidian, white-hot', base: [18, 16, 24], range: [26, 24, 30], lava: [255, 210, 120] },
        { name: 'red rock', base: [88, 38, 28], range: [46, 26, 20], lava: [240, 140, 40] },
    ],
    'terrestrial-habitable': [
        { name: 'Earth', sea: 0.45, ice: 0.85, ocean: [20, 50, 120], oceanRange: [40, 80, 80],
          low: [30, 90, 20], lowRange: [30, 50, 20], high: [80, 70, 30], highRange: [40, 30, 20] },
        { name: 'water world', sea: 0.6, ice: 0.88, ocean: [10, 60, 110], oceanRange: [30, 90, 80],
          low: [40, 110, 50], lowRange: [30, 50, 30], high: [90, 90, 60], highRange: [40, 30, 20] },
        { name: 'arid', sea: 0.33, ice: 0.92, ocean: [24, 58, 112], oceanRange: [40, 70, 70],
          low: [150, 120, 70], lowRange: [40, 36, 26], high: [120, 86, 54], highRange: [40, 30, 20] },
        { name: 'cold', sea: 0.45, ice: 0.62, ocean: [26, 50, 92], oceanRange: [30, 60, 70],
          low: [60, 90, 70], lowRange: [26, 36, 26], high: [96, 96, 90], highRange: [40, 40, 40] },
        { name: 'exotic', sea: 0.45, ice: 0.85, ocean: [30, 46, 110], oceanRange: [40, 70, 80],
          low: [94, 52, 112], lowRange: [36, 26, 40], high: [120, 80, 60], highRange: [40, 30, 20] },
    ],
    'unknown': [
        { name: 'grey', base: [100, 100, 100], range: [80, 80, 80], craters: 0 },
    ],
};
