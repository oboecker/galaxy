/* Planet textures made off the page's thread: planet-look.js asks for a class, a look and a
 * width, and gets an ImageBitmap back — or null, and makes it itself.
 *
 * Flipped here: WebGL turns a canvas the right way up as it uploads it
 * (flipY), but not an ImageBitmap, so the bitmap comes upside down already
 * and the texture does not flip — the same texels either way.
 */
import { ProceduralPlanetTexture } from './planet-texture.js';

self.onmessage = async ({ data: { id, planetClass, look, size } }) => {
    try {
        const canvas = ProceduralPlanetTexture.canvas(planetClass, look, size);
        const bitmap = await createImageBitmap(canvas, { imageOrientation: 'flipY' });
        self.postMessage({ id, bitmap }, [bitmap]);
    } catch {
        self.postMessage({ id, bitmap: null });
    }
};
