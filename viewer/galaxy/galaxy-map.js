/* The 3D galaxy map: a module, as the
 * star-system map is — `createGalaxyMap(root, options)` draws into `root`
 * and gives back { reload, locate, destroy }. A site's page and an editor
 * both import it; the camera,
 * clicks and search are the shared ones (../space/).
 *
 * options: config (the data's URLs, below), title (HTML for the info box),
 * links ({ system: name => URL or null } — where a star's system map is;
 * the host page decides: an editor's form, a site's article; a procedural one's with { procedural: id }), focus (a star's name:
 * selected and flown to once loaded), uncharted (a procedural system's id: the
 * layer shown, it selected).
 */
import * as THREE from 'three'
import * as PLANET_LOOK from '../planet/planet-look.js'
import { createNavigator } from '../space/camera.js'
import { attachPointer, foldable, steeringHint, TOUCH } from '../space/pointer.js'
import { createSearch } from '../space/search.js'
import { createStarField } from './star-field.js'
import { createBlackHole, HORIZON } from '../space/black-hole.js'
import { createPulsarBeams } from '../space/pulsar.js'
import { createEffects, qualityButton } from '../space/effects.js'
import { PHYSICAL, SATURATED, starColourButton, starColourMode } from '../space/star-colours.js'
import { createSky } from '../space/sky.js'
import { icon, toggleIcon } from '../space/icons.js'
import { createNebulaField } from './nebula-field.js'

const LABEL_LIMIT = 200          // star names shown at once: the nearest within LABEL_REACH
const LABEL_REACH = 5000         // ly from the camera, beyond which a name has faded out
const HINT = steeringHint('star')
const HOVER_HINT = TOUCH ? '' : 'Hover over another star to see distance'   // no hover on a touch screen

function markup(title) {
    return `<div class="galaxy-map-wrapper">
    <div id="canvas-container"></div>
    <div id="labels-container"></div>
    <div id="search-container" class="space-bar">
      <button type="button" class="space-tool icon-button" id="toggle-grid-btn" title="Grid: cylindrical, the sectors — switch to Cartesian">${icon('global')}</button>
      <button type="button" class="space-tool icon-button" id="focus-center-btn" title="Focus on Galactic Center">${icon('focus-3')}</button>
      <button type="button" class="space-tool icon-button" id="toggle-territories-btn" title="Toggle Nation Territories" aria-pressed="true" data-toggle-icon="hexagon" hidden></button>
    </div>
    <div id="territory-controls" hidden>
      <select id="territory-world" title="World branch" hidden></select>
      <input type="range" id="territory-time" min="0" max="0" step="1" value="0" title="Point in time" hidden>
      <span id="territory-date"></span>
    </div>
    <div id="info">${title}<br><span id="star-info">Hover over a star for details</span></div>
    <div id="controls">${HINT}</div>
  </div>`;
}

export function createGalaxyMap(root, options = {}) {

        // Where the data comes from: each page names its files (a site's,
        // an editor's draft, the maps site's). Without one, that
        // layer is not drawn: no territories, trips, procedural galaxy.
        const CONFIG = Object.assign({
            // The catalogue's layers, merged in order by name (galaxy.catalogue):
            // [{ id, label, url, real?, icon?, shown? }] — each a switch on the
            // map; `real` draws its stars as the real sky's (small, no glow, no
            // stem, named when hovered). Without layers, `galaxy` is the one file.
            layers: null,
            galaxy: null,
            textures: null,
            // Their height maps, for the globes' relief.
            heights: null,
            textureBase: '',
            territories: null,
            // The stored trips with their routes (galaxy.trips).
            trips: null,
            // travel.json, whose `maps` says how travel looks.
            travelSettings: null,
            // The procedural galaxy (galaxy.procedural): its systems, its gate
            // network over both, fetched when first shown; without it, no
            // layer and no button.
            procedural: null,
            proceduralGates: null,
            // The travel planner's departure field, empty.
            departPlaceholder: 'a date — optional',
        }, options.config || {});

        // Get container dimensions
        root.innerHTML = markup(options.title || '');
        const links = options.links || {};
        const byId = id => root.querySelector('#' + id);
        // The toggles in the markup draw their icon, filled while pressed.
        root.querySelectorAll('[data-toggle-icon]').forEach(button => toggleIcon(button, button.dataset.toggleIcon));
        const container = byId('canvas-container');
        let containerWidth = container.clientWidth;
        let containerHeight = container.clientHeight;

        // Saturated star colours here, physical at a button (../space/star-colours.js).
        let colourMode = starColourMode('galaxy', 'saturated');
        const colourOf = properties => (properties ? (colourMode === 'physical' ? properties.physical : properties.color) : 0xffffff);

        // Spectral type properties (matching SVG generator)
        const spectralProperties = {
            'O': {
                color: SATURATED.O, physical: PHYSICAL.O,
                radius: 1.5,  // Bigger!
                hasGlow: true,
                temperature: '30,000+ K',
                description: 'Blue, extremely hot and luminous'
            },
            'B': {
                color: SATURATED.B, physical: PHYSICAL.B,
                radius: 1.2,  // Bigger!
                hasGlow: true,
                temperature: '10,000-30,000 K',
                description: 'Blue-white, hot and luminous'
            },
            'A': {
                color: SATURATED.A, physical: PHYSICAL.A,
                radius: 1.1,  // Bigger!
                hasGlow: true,
                temperature: '7,500-10,000 K',
                description: 'White, strong hydrogen lines'
            },
            'F': {
                color: SATURATED.F, physical: PHYSICAL.F,
                radius: 0.9,  // Bigger!
                hasGlow: true,
                temperature: '6,000-7,500 K',
                description: 'Yellow-white'
            },
            'G': {
                color: SATURATED.G, physical: PHYSICAL.G,
                radius: 0.8,  // Bigger!
                hasGlow: true,
                temperature: '5,200-6,000 K',
                description: 'Yellow, like Sol'
            },
            'K': {
                color: SATURATED.K, physical: PHYSICAL.K,
                radius: 0.7,  // Bigger!
                hasGlow: true,
                temperature: '3,700-5,200 K',
                description: 'Orange, cooler main sequence'
            },
            'M': {
                color: SATURATED.M, physical: PHYSICAL.M,
                radius: 0.4,
                hasGlow: false,
                temperature: '<3,700 K',
                description: 'Red, coolest and most common'
            },
            'default': {
                color: 0xFFFFFF, physical: 0xFFFFFF,  // White
                radius: 0.5,
                hasGlow: false,
                temperature: 'Unknown',
                description: 'Unclassified'
            }
        };

        // Stellar remnants (galaxy.stars.REMNANTS): a system whose
        // object_type names one. Small, hard points — a white dwarf blue-white,
        // a neutron star or pulsar cyan-white; a black hole a point the eye
        // does not see (black, added on: nothing), drawn by its overlay — still
        // a point of the field for hover and picking.
        const remnantProperties = {
            white_dwarf: { color: 0xdfe8ff, physical: 0xdfe8ff, radius: 0.25, hasGlow: false, label: 'White dwarf' },
            neutron_star: { color: 0xb4f6ff, physical: 0xb4f6ff, radius: 0.15, hasGlow: false, label: 'Neutron star' },
            pulsar: { color: 0xa8ffea, physical: 0xa8ffea, radius: 0.15, hasGlow: false, label: 'Pulsar' },
            // A dim orange point from afar; near, hidden in its horizon.
            black_hole: { color: 0x9a4a18, physical: 0x9a4a18, radius: 0.2, hasGlow: false, label: 'Black hole' },
        };

        // A planet's look — texture, light, tilt, rings, atmosphere — is the
        // shared planet module's (../planet/planet-look.js), which the page


        // Centralized texture loading system with caching, async loading,
        // placeholder support, and memory management.
        const TextureManager = {
            cache: new Map(),
            refCount: new Map(),
            loader: new THREE.TextureLoader(),
            _placeholder: null,

            // Load a texture by path. Returns the cached texture if available,
            // otherwise starts an async load and calls onLoad when ready.
            // Always returns a usable texture immediately (placeholder if loading).
            load(path, onLoad, onError) {
                // Return cached texture immediately
                if (this.cache.has(path)) {
                    const cached = this.cache.get(path);
                    // Increment reference count
                    this.refCount.set(path, (this.refCount.get(path) || 0) + 1);
                    if (onLoad) onLoad(cached);
                    return cached;
                }

                // Return placeholder immediately, swap when loaded
                const placeholder = this.getPlaceholder();

                this.loader.load(
                    path,
                    (texture) => {
                        texture.colorSpace = THREE.SRGBColorSpace;
                        this.cache.set(path, texture);
                        this.refCount.set(path, 1);
                        if (onLoad) onLoad(texture);
                    },
                    undefined,
                    (err) => {
                        console.warn(`TextureManager: Failed to load "${path}", using fallback.`, err);
                        if (onError) onError(err);
                    }
                );

                return placeholder;
            },

            // Return a reusable solid-color placeholder texture (gray).
            // Created once and shared across all pending loads.
            getPlaceholder() {
                if (!this._placeholder) {
                    const canvas = document.createElement('canvas');
                    canvas.width = 4;
                    canvas.height = 4;
                    const ctx = canvas.getContext('2d');
                    ctx.fillStyle = '#888888';
                    ctx.fillRect(0, 0, 4, 4);
                    this._placeholder = new THREE.CanvasTexture(canvas);
                }
                return this._placeholder;
            },

            // Dispose a specific texture by path and remove from cache.
            // Uses reference counting to only dispose when no references remain.
            dispose(path) {
                const count = (this.refCount.get(path) || 1) - 1;
                this.refCount.set(path, count);

                if (count <= 0) {
                    // Only dispose when no references remain
                    if (this.cache.has(path)) {
                        const texture = this.cache.get(path);
                        texture.dispose();
                        this.cache.delete(path);
                    }
                    this.refCount.delete(path);
                }
            }
        };

        // Simple hash function to convert string to number
        function hashString(str) {
            let hash = 0;
            for (let i = 0; i < str.length; i++) {
                const char = str.codePointAt(i);
                hash = ((hash << 5) - hash) + char;
                hash = hash & hash; // Convert to 32bit integer
            }
            return Math.abs(hash);
        }

        // Escape HTML to prevent XSS attacks
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Transform internal position coordinates to JSON format
        function transformPosition(internalPos) {
            return {
                x: internalPos.x,
                y: -internalPos.z,
                z: internalPos.y
            };
        }

        // Format position coordinates as string
        function formatPosition(pos) {
            const transformed = transformPosition(pos);
            return `(${transformed.x.toFixed(0)}, ${transformed.y.toFixed(0)}, ${transformed.z.toFixed(0)}) ly`;
        }

        // A planet's size (galaxy.json's `radius`, km) and what follows from
        // it — galaxy.bodies, which this mirrors.
        const EARTH_RADIUS = 6371;
        const GAS_GIANT_GRAVITY = { 'gas-giant-cold': 1.1, 'gas-giant-warm': 2.0 };

        function planetGravity(planet) {
            if (GAS_GIANT_GRAVITY[planet.class]) return GAS_GIANT_GRAVITY[planet.class];
            const g = Math.pow(planet.radius / EARTH_RADIUS, 1.7);
            return planet.class === 'ice-world' ? g * 0.6 : g;
        }

        function planetSize(planet) {
            if (typeof planet.radius !== 'number') return '';
            return ` <span style="opacity:.7">${planet.radius.toLocaleString('en')} km, ` +
                `${planetGravity(planet).toFixed(2)} g</span>`;
        }

        // The sphere drawn for a planet: Earth's size the old fixed 8, the rest
        // compressed so a gas giant does not swallow its neighbours — Mars
        // about 6.4, Jupiter about 18.6. No radius: 8.
        function planetDisplayRadius(planet) {
            if (typeof planet.radius !== 'number') return 8;
            return 8 * Math.min(2.4, Math.max(0.6, Math.pow(planet.radius / EARTH_RADIUS, 0.35)));
        }

        // Build planet info string for display
        function buildPlanetInfo(starUserData) {
            let planetInfo = '';
            if (starUserData.planetCount > 0) {
                planetInfo = `<br>Planets: ${starUserData.planetCount}`;
                if (starUserData.planets && starUserData.planets.length > 0) {
                    const planetList = starUserData.planets
                        .map((p, idx) => `${p.index || (idx + 1)}. ${escapeHtml(p.name)}${planetSize(p)}`)
                        .join('<br>');
                    planetInfo += `<br><small>${planetList}</small>`;
                }
            }
            return planetInfo;
        }

        // Build star info HTML display
        function buildStarInfoHTML(starUserData, options = {}) {
            const posStr = formatPosition(starUserData.position);
            const planetInfo = buildPlanetInfo(starUserData);
            const label = options.label || '';

            const uncharted = starUserData.procedural ? ' <small class="galaxy-uncharted">· uncharted</small>' : '';
            let html = `<strong>${escapeHtml(starUserData.name)}${label}</strong>${uncharted}<br>
                Spectral Type: ${escapeHtml(starUserData.spectralType || 'Unknown')}<br>
                Position (x,y,z): ${posStr}${planetInfo}<br>`;

            // Into its system map: the selected star's, where the
            // page has one — or double-click the star.
            const into = selectedStar && starUserData === selectedStar.userData && links.system
                ? systemLink(starUserData) : null;
            if (into) html += `<a class="space-link" href="${escapeHtml(into)}">Enter system ${icon('arrow-right-s')}</a><br>`;

            if (options.targetStar) {
                const distance = options.distance.toFixed(1);
                html += `<br><strong>Target: ${escapeHtml(options.targetStar.name)}</strong><br>
                    Distance: ${distance} ly`;
            } else if (options.hintText) {
                html += `<em>${options.hintText}</em>`;
            }

            return html;
        }

        // Reset hover state on a star (scale and line visibility)
        function resetStarHoverState(star) {
            if (star.isStarRecord) {
                if (field) field.setHovered(-1);
                // A black hole's or pulsar's overlay back to its size.
                if (star.overlay) star.overlay.scale.setScalar(star.overlay.userData.base);
                return;
            }
            star.scale.set(1, 1, 1);
            star.children.forEach(child => {
                if (child instanceof THREE.Line) {
                    child.visible = true;
                }
            });
        }

        // Math.radians polyfill for converting degrees to radians
        if (!Math.radians) {
            Math.radians = function (degrees) {
                return degrees * Math.PI / 180;
            };
        }

        // Function to get spectral properties from spectral type
        function getSpectralProperties(spectralClass, starName = '') {
            if (!spectralClass || spectralClass === 'Unknown') {
                // If no spectral type, assign one based on star name for consistency
                const spectralTypes = ['O', 'B', 'A', 'F', 'G', 'K', 'M'];
                const hash = hashString(starName);
                const typeIndex = hash % spectralTypes.length;
                return spectralProperties[spectralTypes[typeIndex]];
            }

            // Extract the main spectral class letter (first character)
            const mainClass = spectralClass.charAt(0).toUpperCase();
            return spectralProperties[mainClass] || spectralProperties.default;
        }

        // Create a rectangular grid for the coordinate system
        function createRectangularGrid(width, height, divisionsW, divisionsH, color) {
            const geometry = new THREE.BufferGeometry();
            const vertices = [];

            for (let i = 0; i <= divisionsW; i++) {
                const x = (i / divisionsW - 0.5) * width;
                vertices.push(x, -height / 2, 0, x, height / 2, 0);
            }

            for (let i = 0; i <= divisionsH; i++) {
                const y = (i / divisionsH - 0.5) * height;
                vertices.push(-width / 2, y, 0, width / 2, y, 0);
            }

            geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
            const material = new THREE.LineBasicMaterial({color: color, transparent: true, opacity: 0.3});
            return new THREE.LineSegments(geometry, material);
        }

        // Scene setup
        const scene = new THREE.Scene();
        // The nebulae (nebula-field.js): declared before the first frame draws.
        const NEBULAE_KEY = 'galaxy-nebulae';
        let nebulaeShown = (() => { try { return localStorage.getItem(NEBULAE_KEY) !== 'hidden'; } catch { return true; } })();
        let nebulaField = null;
        let onNebulaeChosen = null;            // the choice made on another map of the page
        // Each nebula a point the search finds ("Orion Nebula") and flies to.
        let nebulaItems = [];
        // The catalogue's (galaxy.json) and the procedural layer's, drawn while it shows.
        let storyNebulae = [], procNebulae = null;
        const refreshNebulae = () => showNebulae([...storyNebulae, ...(procShown && procNebulae ? procNebulae : [])]);
        // The sky beyond the galaxy (../space/sky.js): fewer and fainter than on
        // a system map, no band, so that none reads as one of the map's stars.
        scene.add(createSky({ count: 2000, brightness: 0.4, seed: 'galaxy' }));
        scene.background = new THREE.Color(0x000000);

        // Camera setup
        const camera = new THREE.PerspectiveCamera(
            75,
            containerWidth / containerHeight,
            0.1,
            100000
        );
        camera.position.set(5000, 3000, -30000);
        camera.lookAt(0, 0, -25000);

        // Renderer setup
        const renderer = new THREE.WebGLRenderer({
            antialias: true,
            alpha: false,
            // As the star-system map: the shared camera fits near and far to the distance.
            logarithmicDepthBuffer: true,
            // A stencil: a black hole's horizon keeps the light effects' glow off it (../space/effects.js).
            stencil: true,
            powerPreference: 'high-performance',
            failIfMajorPerformanceCaveat: false  // Still render even without GPU acceleration
        });
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.0;
        renderer.setSize(containerWidth, containerHeight);
        renderer.setPixelRatio(window.devicePixelRatio);
        container.appendChild(renderer.domElement);

        // The shared camera (../space/camera.js): drag to turn, right-drag to
        // pan, wheel to zoom; go-to flights. As before: 2,000 ly from the
        // first view's centre, zoom from 100 to 50,000.
        // Out far enough for the whole galaxy: 50,000 ly in
        // radius, the view ±0.77 of the distance high (75°), with a margin.
        const nav = createNavigator(camera, renderer.domElement, { reach: () => 50000, minDistance: 100, maxDistance: 75000 });
        nav.place(new THREE.Vector3(0, 0, -23000), new THREE.Vector3(0, 0, -25000));
        let frameId = 0;

        // Raycaster for star hover detection
        const raycaster = new THREE.Raycaster();
        const mouse = new THREE.Vector2();
        let hoveredStar = null;
        let selectedStar = null;
        let selectionIndicator = null;


        // Array to hold star objects
        const stars = [];

        // Reference to galactic center
        let galacticCenterObject = null;

        // Hover line
        let hoverLine = null;
        let hoverFlowLine = null;
        let hoverFlowProgress = 0;
        const numFlowSegments = 100;

        // Grid system state
        // The sector grid first: the 2D map's sectors, 15 rings × 24 beams.
        let currentGridSystem = 'cylindrical';
        let cartesianGridGroup = null;
        let cylindricalGridGroup = null;

        // Container for labels
        const labelsContainer = byId('labels-container');
        // The names shown, from a pool: the nearest stars' (updateLabels).
        const labelPool = [];
        let centreLabel = null;
        // Every star in three draws (./star-field.js), rebuilt when the data is.
        let field = null;
        let pointerInside = false;
        // The hover is looked for again only when the pointer or the view
        // moved: over 10,000 stars, every frame cost more than the drawing.
        let hoverStale = true, lastHit = null;
        const lastView = new THREE.Matrix4();
        // Which stars get names, chosen again a few times a second.
        let labelsChosen = [], labelsFrame = 0;
        const LABEL_EVERY = 10;

        // Planet orbits
        let planetOrbitsGroup = null;
        let orbitingPlanets = [];
        const planetLabels = [];

        // Where "Enter system" leads: the page's own link for a system — for
        // a procedural one with its id, which the page opens from its block
        // of details (galaxy.procedural.group).
        function systemLink(data) {
            return data.procedural ? links.system(data.name, { procedural: data.procedural }) : links.system(data.name);
        }

        // Function to create a star visualization
        // A star as the map keeps it: where it is and what it is — drawn by
        // the field, all stars at once (rebuildField).
        function createStar(star) {
            const props = remnantProperties[star.objectType] || getSpectralProperties(star.spectralType, star.name);
            stars.push({
                isStarRecord: true,
                index: stars.length,
                fieldIndex: -1,
                position: new THREE.Vector3(star.x, star.y, star.z),
                radius: 30 * props.radius * (star.real ? REAL_SIZE : 1),
                userData: {
                    name: star.name,
                    real: star.real,
                    layers: star.layers,
                    // Its id in the procedural galaxy (galaxy.procedural): one
                    // of the layer's, not the catalogue's.
                    procedural: star.procedural || null,
                    // A remnant says what it is where a star says its class.
                    spectralType: remnantProperties[star.objectType] ? remnantProperties[star.objectType].label
                        : star.spectralType,
                    objectType: star.objectType || null,
                    position: {x: star.x, y: star.y, z: star.z},
                    properties: props,
                    planets: star.planets || [],
                    planetCount: star.planetCount || 0
                },
            });
        }

        // The catalogue's layers, each shown or hidden in the Layers panel,
        // remembered for every galaxy map. A real layer's stars are much
        // smaller than the others, without glow or stem, named only when
        // hovered or chosen. `layers` is a list, or the URL of one (a
        // layers/index.json the library writes: galaxy.catalogue.layer_index),
        // its files beside it.
        const REAL_SIZE = 0.25;
        const REAL_KEY = 'galaxy-real-stars';
        let LAYERS = [];
        const layerKey = layer => layer.key || (layer.real ? REAL_KEY : `galaxy-layer-${layer.id}`);
        const layerShown = {};
        const layersReady = (typeof CONFIG.layers === 'string'
            ? fetch(CONFIG.layers).then(r => (r.ok ? r.json() : [])).catch(() => [])
                .then(list => list.map(layer => ({ ...layer, url: new URL(layer.url, new URL(CONFIG.layers, location.href)).href })))
            : Promise.resolve(CONFIG.layers || [{ id: 'catalogue', url: CONFIG.galaxy, toggle: false }]))
            .then(list => {
                LAYERS = list.filter(layer => layer.url);
                LAYERS.forEach(layer => {
                    layerShown[layer.id] = (() => {
                        try { const v = localStorage.getItem(layerKey(layer)); return v ? v !== 'hidden' : layer.shown !== false; }
                        catch { return layer.shown !== false; }
                    })();
                });
                return LAYERS;
            });
        const layerListeners = [];              // the choices made on another map of the page
        // The procedural galaxy: the systems the catalogue does not
        // name, as many as round Sol, laid out by the arms — a layer like the
        // real stars, hidden at first (its file is fetched when first shown),
        // drawn as the catalogue's stars, named only when hovered or chosen; its
        // gate network, over both, replaces the stored one while it shows.
        const PROC_KEY = 'galaxy-procedural';
        let procShown = (() => { try { return localStorage.getItem(PROC_KEY) === 'shown'; } catch { return false; } })();
        let procDots = null, procLinks = null, procLoading = null;
        let showProcedural = async () => {};    // the layer shown, not remembered (set by its button)
        // The stems to the galactic plane and their discs:
        // shown or hidden by ⊥, remembered for every galaxy map.
        const STEMS_KEY = 'galaxy-stems';
        let stemsShown = (() => { try { return localStorage.getItem(STEMS_KEY) !== 'hidden'; } catch { return true; } })();
        // A system is in every layer that names it, and shown while one of them is.
        const inShownLayer = st => !st.userData.layers || st.userData.layers.some(id => layerShown[id] !== false);
        const isShown = st => inShownLayer(st) && (procShown || !st.userData.procedural);
        // The stars the field draws, in its order: star.fieldIndex.
        let fieldStars = [];

        function rebuildField() {
            if (field) {
                scene.remove(field.object);
                field.dispose();
            }
            stars.forEach(st => { st.fieldIndex = -1; });
            fieldStars = stars.filter(isShown);
            fieldStars.forEach((st, k) => { st.fieldIndex = k; });
            field = createStarField(fieldStars.map(st => ({
                position: st.position, colour: colourOf(st.userData.properties), radius: st.radius,
                glow: st.userData.properties.hasGlow && !st.userData.real, stem: !st.userData.real,
                occludes: st.userData.objectType !== 'black_hole',
            })));
            field.setStems(stemsShown);
            scene.add(field.object);
            buildRemnants();
        }

        // ── What a remnant shows beyond its point ───────────────
        // A black hole: the galactic centre's (../space/black-hole.js), its
        // horizon STELLAR_HORIZON in radius — at a star's scale on this map,
        // where a sun is drawn some 25 ly across — its disc tipped its own way:
        // a real object, growing as the camera comes near. A pulsar: two
        // beams fading out from its poles (../space/pulsar.js), sweeping round
        // a tilted spin axis. A few dozen of each: one object apiece.
        const STELLAR_HORIZON = 18;         // ly, as drawn
        const BEAM_LENGTH = 220;            // ly
        const remnantGroup = new THREE.Group();
        scene.add(remnantGroup);
        const pulsars = [], holes = [];
        function buildRemnants() {
            remnantGroup.children.slice().forEach(o => {
                remnantGroup.remove(o);
                o.traverse(p => {
                    if (p.geometry) p.geometry.dispose();
                    if (p.material) { if (p.material.map) p.material.map.dispose(); p.material.dispose(); }
                });
            });
            pulsars.length = 0;
            holes.length = 0;
            stars.forEach(st => { st.overlay = null; });
            for (const st of fieldStars) {
                const kind = st.userData.objectType;
                if (kind === 'black_hole') {
                    const hole = createBlackHole();
                    hole.scale.setScalar(STELLAR_HORIZON / HORIZON);
                    hole.position.copy(st.position);
                    const h = hashString(st.userData.name);
                    hole.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0),
                        new THREE.Vector3(Math.sin(h * 0.7), 1.2, Math.cos(h * 1.3)).normalize());
                    hole.userData.base = hole.scale.x;          // its size unhovered
                    st.overlay = hole;
                    remnantGroup.add(hole);
                    holes.push(hole);
                } else if (kind === 'pulsar') {
                    // Its beams along a magnetic axis tilted from the spin axis,
                    // both seeded by the name: each pulsar its own way.
                    const h = hashString(st.userData.name);
                    const spin = new THREE.Vector3(Math.sin(h), 1, Math.cos(h * 1.7)).normalize();
                    const spinner = createPulsarBeams(BEAM_LENGTH, 0x9ffff0, 0.5 + (h % 7) / 10);
                    const holder = new THREE.Group();                     // lays the spin axis where it points
                    holder.position.copy(st.position);
                    holder.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), spin);
                    holder.add(spinner);
                    holder.userData.base = 1;
                    st.overlay = holder;
                    remnantGroup.add(holder);
                    pulsars.push({ spinner, rate: 1.5 + (h % 5) * 0.4 });
                }
            }
        }
        // A turn every second or so — a real pulsar's is milliseconds to
        // seconds; slower here, so the eye follows the sweep.
        function spinPulsars(seconds) {
            for (const p of pulsars) p.spinner.userData.spin(seconds * p.rate);
            for (const hole of holes) hole.userData.update(seconds);
        }

        // Calculate a deterministic axial rotation speed for a planet.
        // Range: 0.0005 to 0.002 radians per frame.
        function calculateRotationSpeed(planetName) {
            const hash = hashString(planetName || 'unknown');
            const normalized = (hash % 10000) / 10000; // 0..1
            return 0.0005 + normalized * 0.0015;
        }

        // Create planet orbits for a selected star
        function createPlanetOrbits(star) {
            // Remove old orbits if they exist
            removePlanetOrbits();

            const planets = star.userData.planets;
            if (!planets || planets.length === 0) {
                return;
            }

            planetOrbitsGroup = new THREE.Group();
            planetOrbitsGroup.position.copy(star.position);

            const baseOrbitRadius = 60; // Base orbital radius
            const orbitSpacing = 25; // Least space between orbits
            // Room for each planet with its atmosphere (at most 1.3× its
            // radius) or its rings: a larger planet pushes the next orbit out.
            const sizes = planets.map(planetDisplayRadius);
            const reach = planets.map((planet, i) => sizes[i] * Math.max(1.3,
                ...PLANET_LOOK.ringBands(planet).map(band => band.outer)));
            const orbits = [];
            sizes.forEach((size, i) => {
                orbits.push(i === 0 ? baseOrbitRadius + Math.max(0, reach[i] - 10)
                    : orbits[i - 1] + Math.max(orbitSpacing, reach[i - 1] + reach[i] + 6));
            });
            // Lit by its star, as the star-system map lights its planets.
            const starColour = colourOf(star.userData.properties);
            planetOrbitsGroup.add(new THREE.PointLight(starColour, 2.5, 0, 0));
            planetOrbitsGroup.add(new THREE.AmbientLight(0xffffff, 0.25));

            console.time('PlanetTexture:systemSetup');
            planets.forEach((planet, index) => {
                const orbitRadius = orbits[index];
                const size = sizes[index];
                const planetColor = colourOf(star.userData.properties);

                // Create orbit ring (fading trace)
                const orbitGeometry = new THREE.RingGeometry(orbitRadius - 1, orbitRadius + 1, 64);
                const orbitMaterial = new THREE.MeshBasicMaterial({
                    color: planetColor,
                    transparent: true,
                    opacity: 0.2,
                    side: THREE.DoubleSide
                });
                const orbitRing = new THREE.Mesh(orbitGeometry, orbitMaterial);
                orbitRing.rotation.x = Math.PI / 2;
                planetOrbitsGroup.add(orbitRing);

                // The planet as every map draws it (planet-look.js): lit, tilted,
                // ringed, its map or its class's texture, its atmosphere. Its
                // map loads later: the texture swapped in then.
                const texturePath = planet.texture || null;
                const map = texturePath ? TextureManager.load(texturePath, loaded => {
                    globe.material.map = loaded;
                    globe.material.needsUpdate = true;
                }) : null;
                const globe = PLANET_LOOK.createGlobe(THREE, planet,
                    { map, relief: planet.relief || null, name: planet.name === '?' ? `planet-${planet.index || 0}` : planet.name });
                globe.scale.setScalar(size);
                // Its atmosphere lit from its star's side (planet-look.js).
                if (globe.userData.setLight) globe.userData.setLight(star.position);
                // Its rings shaded by it, away from its star (planet-look.js).
                globe.userData.setShadows({ suns: [star.position] });
                // On its orbit: a holder moved along it, the globe turning in it.
                const planetMesh = new THREE.Group();
                planetMesh.add(globe);

                // Calculate orbital speed (inversely proportional to distance with more dramatic difference)
                // Using power of 1.5 instead of 0.5 for more distinct speed differences
                const baseSpeed = 0.8;
                const distanceRatio = orbitRadius / baseOrbitRadius;
                const orbitalSpeed = baseSpeed / Math.pow(distanceRatio, 1.5);

                // Random starting angle for variety
                const startAngle = Math.random() * Math.PI * 2;

                // Create planet label
                const planetLabel = document.createElement('div');
                planetLabel.className = 'star-label';
                planetLabel.style.fontSize = '9px';
                planetLabel.style.padding = '1px 4px';
                const planetName = planet.name === '?' ? `Planet ${planet.index}` : planet.name;
                planetLabel.textContent = planetName;
                labelsContainer.appendChild(planetLabel);
                planetLabels.push(planetLabel);

                // Store planet data for animation
                // Deterministic axial rotation speed (reuses planetName from label above)
                const rotationSpeed = calculateRotationSpeed(planetName);

                orbitingPlanets.push({
                    mesh: planetMesh,
                    globe: globe,
                    orbitRadius: orbitRadius,
                    angle: startAngle,
                    speed: orbitalSpeed,
                    index: index,
                    label: planetLabel,
                    texturePath: texturePath,
                    rotationSpeed: rotationSpeed,
                    cloudSphere: globe.userData.clouds || null
                });

                planetOrbitsGroup.add(planetMesh);

                // Create fading trail effect
                const trailSegments = 32;
                const trailGeometry = new THREE.BufferGeometry();
                const trailPositions = new Float32Array(trailSegments * 3);
                const trailColors = new Float32Array(trailSegments * 3);

                const color = new THREE.Color(planetColor);

                for (let i = 0; i < trailSegments; i++) {
                    const angle = startAngle - (i / trailSegments) * Math.PI * 0.5; // Trail 90 degrees behind
                    trailPositions[i * 3] = Math.cos(angle) * orbitRadius;
                    trailPositions[i * 3 + 1] = 0;
                    trailPositions[i * 3 + 2] = Math.sin(angle) * orbitRadius;

                    // Fade from bright to transparent
                    const alpha = 1 - (i / trailSegments);
                    trailColors[i * 3] = color.r * alpha;
                    trailColors[i * 3 + 1] = color.g * alpha;
                    trailColors[i * 3 + 2] = color.b * alpha;
                }

                trailGeometry.setAttribute('position', new THREE.BufferAttribute(trailPositions, 3));
                trailGeometry.setAttribute('color', new THREE.BufferAttribute(trailColors, 3));

                const trailMaterial = new THREE.LineBasicMaterial({
                    vertexColors: true,
                    transparent: true,
                    opacity: 0.8,
                    linewidth: 2,
                    blending: THREE.AdditiveBlending
                });

                const trailLine = new THREE.Line(trailGeometry, trailMaterial);

                // Store trail data for animation
                orbitingPlanets.at(-1).trail = trailLine;
                orbitingPlanets.at(-1).trailSegments = trailSegments;

                planetOrbitsGroup.add(trailLine);
            });

            console.timeEnd('PlanetTexture:systemSetup');
            scene.add(planetOrbitsGroup);
        }

        // Remove planet orbits
        function removePlanetOrbits() {
            // A map texture is TextureManager's to release; the generated ones
            // and the clouds are the planet module's, shared: kept.
            orbitingPlanets.forEach(planet => {
                if (planet.texturePath) {
                    TextureManager.dispose(planet.texturePath);
                }
                if (planet.mesh) {
                    planet.mesh.traverse(child => {
                        if (child.geometry) child.geometry.dispose();
                        if (child.material) child.material.dispose();
                    });
                }
            });

            if (planetOrbitsGroup) {
                scene.remove(planetOrbitsGroup);
                planetOrbitsGroup = null;
            }
            // Remove planet labels
            planetLabels.forEach(label => {
                if (label?.parentNode) {
                    label.remove();
                }
            });
            planetLabels.length = 0;
            orbitingPlanets = [];
        }

        // Toggle between grid systems
        function toggleGridSystem() {
            if (currentGridSystem === 'cartesian') {
                currentGridSystem = 'cylindrical';
                cartesianGridGroup.visible = false;
                cylindricalGridGroup.visible = true;
                // The button shows the grid shown (a toggle
                // says its state): a globe for rings and rays, a grid for squares.
                byId('toggle-grid-btn').innerHTML = icon('global');
                byId('toggle-grid-btn').title = 'Grid: cylindrical, the sectors — switch to Cartesian';
            } else {
                currentGridSystem = 'cartesian';
                cartesianGridGroup.visible = true;
                cylindricalGridGroup.visible = false;
                byId('toggle-grid-btn').innerHTML = icon('layout-grid');
                byId('toggle-grid-btn').title = 'Grid: Cartesian — switch to cylindrical, the sectors';
            }
        }

        function createCartesianAxes() {
            const axisLengthXY = 50000;
            const axisLengthZ = 5000;
            const axisGroup = new THREE.Group();

            const xAxisGeometry = new THREE.BufferGeometry().setFromPoints([
                new THREE.Vector3(-axisLengthXY, 0, 0),
                new THREE.Vector3(axisLengthXY, 0, 0)
            ]);
            const xAxisMaterial = new THREE.LineBasicMaterial({color: 0xff0000, linewidth: 2});
            const xAxis = new THREE.Line(xAxisGeometry, xAxisMaterial);
            axisGroup.add(xAxis);

            const xLabelGeometry = new THREE.SphereGeometry(100, 16, 16);
            const xLabelMaterial = new THREE.MeshBasicMaterial({color: 0xff0000});
            const xLabelPos = new THREE.Mesh(xLabelGeometry, xLabelMaterial);
            xLabelPos.position.set(axisLengthXY + 300, 0, 0);
            axisGroup.add(xLabelPos);

            const xLabelNeg = new THREE.Mesh(xLabelGeometry.clone(), xLabelMaterial.clone());
            xLabelNeg.position.set(-axisLengthXY - 300, 0, 0);
            xLabelNeg.scale.set(0.7, 0.7, 0.7);
            axisGroup.add(xLabelNeg);

            const yAxisGeometry = new THREE.BufferGeometry().setFromPoints([
                new THREE.Vector3(0, -axisLengthZ, 0),
                new THREE.Vector3(0, axisLengthZ, 0)
            ]);
            const yAxisMaterial = new THREE.LineBasicMaterial({color: 0x00ff00, linewidth: 2});
            const yAxis = new THREE.Line(yAxisGeometry, yAxisMaterial);
            axisGroup.add(yAxis);

            const yLabelGeometry = new THREE.SphereGeometry(80, 16, 16);
            const yLabelMaterial = new THREE.MeshBasicMaterial({color: 0x00ff00});
            const yLabelPos = new THREE.Mesh(yLabelGeometry, yLabelMaterial);
            yLabelPos.position.set(0, axisLengthZ + 200, 0);
            axisGroup.add(yLabelPos);

            const yLabelNeg = new THREE.Mesh(yLabelGeometry.clone(), yLabelMaterial.clone());
            yLabelNeg.position.set(0, -axisLengthZ - 200, 0);
            yLabelNeg.scale.set(0.7, 0.7, 0.7);
            axisGroup.add(yLabelNeg);

            const zAxisGeometry = new THREE.BufferGeometry().setFromPoints([
                new THREE.Vector3(0, 0, -axisLengthXY),
                new THREE.Vector3(0, 0, axisLengthXY)
            ]);
            const zAxisMaterial = new THREE.LineBasicMaterial({color: 0x0000ff, linewidth: 2});
            const zAxis = new THREE.Line(zAxisGeometry, zAxisMaterial);
            axisGroup.add(zAxis);

            const zLabelGeometry = new THREE.SphereGeometry(100, 16, 16);
            const zLabelMaterial = new THREE.MeshBasicMaterial({color: 0x0000ff});
            const zLabelPos = new THREE.Mesh(zLabelGeometry, zLabelMaterial);
            zLabelPos.position.set(0, 0, axisLengthXY + 300);
            axisGroup.add(zLabelPos);

            const zLabelNeg = new THREE.Mesh(zLabelGeometry.clone(), zLabelMaterial.clone());
            zLabelNeg.position.set(0, 0, -axisLengthXY - 300);
            zLabelNeg.scale.set(0.7, 0.7, 0.7);
            axisGroup.add(zLabelNeg);


            const xyGrid = createRectangularGrid(axisLengthXY * 2, axisLengthZ * 2, 100, 100, 0x444444);
            axisGroup.add(xyGrid);

            const xzGrid = createRectangularGrid(axisLengthXY * 2, axisLengthXY * 2, 100, 20, 0x333333);
            xzGrid.rotation.x = Math.PI / 2;
            axisGroup.add(xzGrid);

            const yzGrid = createRectangularGrid(axisLengthXY * 2, axisLengthZ * 2, 100, 20, 0x2a2a2a);
            yzGrid.rotation.y = Math.PI / 2;
            axisGroup.add(yzGrid);

            scene.add(axisGroup);
            return axisGroup;
        }

        function createCylindricalGrid() {
            const gridGroup = new THREE.Group();

            const ringWidth = 3554;
            const numRings = 15;
            const numBeams = 24;
            const beamAngle = 15;

            const centerRadius = ringWidth;
            const centerCircleGeometry = new THREE.CircleGeometry(centerRadius, 64);
            const centerCircleMaterial = new THREE.MeshBasicMaterial({
                color: 0x444444,
                transparent: true,
                opacity: 0.3,
                side: THREE.DoubleSide
            });
            const centerCircle = new THREE.Mesh(centerCircleGeometry, centerCircleMaterial);
            centerCircle.rotation.x = Math.PI / 2;
            gridGroup.add(centerCircle);

            const centerOutlineGeometry = new THREE.RingGeometry(centerRadius - 10, centerRadius + 10, 64);
            const centerOutlineMaterial = new THREE.MeshBasicMaterial({
                color: 0x888888,
                transparent: true,
                opacity: 0.7,
                side: THREE.DoubleSide
            });
            const centerOutline = new THREE.Mesh(centerOutlineGeometry, centerOutlineMaterial);
            centerOutline.rotation.x = Math.PI / 2;
            gridGroup.add(centerOutline);

            for (let ring = 1; ring <= numRings; ring++) {
                const innerRadius = centerRadius + (ring - 1) * ringWidth;

                const ringGeometry = new THREE.RingGeometry(innerRadius, innerRadius + 20, 128);
                const ringMaterial = new THREE.MeshBasicMaterial({
                    color: 0x666666,
                    transparent: true,
                    opacity: 0.6,
                    side: THREE.DoubleSide
                });
                const ringMesh = new THREE.Mesh(ringGeometry, ringMaterial);
                ringMesh.rotation.x = Math.PI / 2;
                gridGroup.add(ringMesh);
            }

            const maxRadius = centerRadius + numRings * ringWidth + ringWidth;

            for (let beam = 0; beam < numBeams; beam++) {
                const angleDeg = beam * beamAngle;
                const angleRad = -Math.radians(angleDeg);

                const startX = centerRadius * Math.sin(angleRad);
                const startZ = centerRadius * Math.cos(angleRad);
                const endX = maxRadius * Math.sin(angleRad);
                const endZ = maxRadius * Math.cos(angleRad);

                const beamGeometry = new THREE.BufferGeometry().setFromPoints([
                    new THREE.Vector3(startX, 0, startZ),
                    new THREE.Vector3(endX, 0, endZ)
                ]);
                const beamMaterial = new THREE.LineBasicMaterial({
                    color: 0x666666,
                    transparent: true,
                    opacity: 0.6
                });
                const beamLine = new THREE.Line(beamGeometry, beamMaterial);
                gridGroup.add(beamLine);
            }

            const planeSize = maxRadius * 2;
            const planeHeight = 10000;

            function createVerticalGridPlane(rotationY) {
                const planeGroup = new THREE.Group();

                for (let h = -planeHeight / 2; h <= planeHeight / 2; h += ringWidth) {
                    const lineGeometry = new THREE.BufferGeometry().setFromPoints([
                        new THREE.Vector3(-planeSize / 2, h, 0),
                        new THREE.Vector3(planeSize / 2, h, 0)
                    ]);
                    const lineMaterial = new THREE.LineBasicMaterial({
                        color: 0x4a4a4a,
                        transparent: true,
                        opacity: 0.5
                    });
                    const line = new THREE.Line(lineGeometry, lineMaterial);
                    planeGroup.add(line);
                }

                for (let v = -planeSize / 2; v <= planeSize / 2; v += ringWidth) {
                    const lineGeometry = new THREE.BufferGeometry().setFromPoints([
                        new THREE.Vector3(v, -planeHeight / 2, 0),
                        new THREE.Vector3(v, planeHeight / 2, 0)
                    ]);
                    const lineMaterial = new THREE.LineBasicMaterial({
                        color: 0x4a4a4a,
                        transparent: true,
                        opacity: 0.5
                    });
                    const line = new THREE.Line(lineGeometry, lineMaterial);
                    planeGroup.add(line);
                }

                planeGroup.rotation.y = rotationY;
                return planeGroup;
            }

            const verticalPlane1 = createVerticalGridPlane(0);
            gridGroup.add(verticalPlane1);

            const verticalPlane2 = createVerticalGridPlane(Math.PI / 2);
            gridGroup.add(verticalPlane2);

            scene.add(gridGroup);
            return gridGroup;
        }


        cartesianGridGroup = createCartesianAxes();
        cylindricalGridGroup = createCylindricalGrid();
        cartesianGridGroup.visible = false;
        // The grids are a backdrop: drawn first and writing no depth. The
        // cylindrical one's filled centre lies in the galactic plane with the
        // black hole's accretion disc, and hid or flickered over it.
        for (const grid of [cartesianGridGroup, cylindricalGridGroup]) {
            grid.traverse(o => {
                if (!o.material) return;
                o.material.depthWrite = false;
                o.renderOrder = -1;
            });
        }



        // The black hole at the centre (../space/black-hole.js).
        function createGalacticCenter() {
            const centerGroup = createBlackHole();
            centerGroup.position.set(0, 0, 0);
            scene.add(centerGroup);

            centreLabel = document.createElement('div');
            centreLabel.className = 'star-label';
            centreLabel.textContent = 'Galactic Center';
            labelsContainer.appendChild(centreLabel);

            return centerGroup;
        }

        galacticCenterObject = createGalacticCenter();

        function focusGalacticCenter() {
            nav.goTo(new THREE.Vector3(0, 0, 0), { follow: false });
        }

        function focusOnStar(star) {
            nav.goTo(star.position.clone(), { item: star, follow: false });
        }

        /* Several ring pieces as one geometry: one mesh, one draw. */
        function joined(parts) {
            const position = [], index = [];
            for (const part of parts) {
                const base = position.length / 3;
                position.push(...part.attributes.position.array);
                index.push(...part.index.array.map(i => i + base));
                part.dispose();
            }
            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute('position', new THREE.Float32BufferAttribute(position, 3));
            geometry.setIndex(index);
            return geometry;
        }

        function createSelectionIndicator(star) {
            // Remove old indicator if exists
            if (selectionIndicator) {
                scene.remove(selectionIndicator);
                selectionIndicator = null;
            }

            if (!star) return;

            // Create a rotating ring around the selected star
            const indicatorGroup = new THREE.Group();

            // Rings sized to be outside the maximum star glow (~112 units).
            // Smooth circles show no spin: the outer one in four arcs with
            // gaps, the inner one with ticks.
            const ringGeometry = joined([0, 1, 2, 3].map(k =>
                new THREE.RingGeometry(120, 135, 32, 1, (k + 0.1) * Math.PI / 2, 0.8 * Math.PI / 2)));
            const ringMaterial = new THREE.MeshBasicMaterial({
                color: 0x00ffff,
                transparent: true,
                opacity: 0.8,
                side: THREE.DoubleSide,
                // No depth of its own: in the galactic plane, as a black
                // hole's disc is, the disc failed against it pixel by pixel.
                depthWrite: false
            });
            const ring = new THREE.Mesh(ringGeometry, ringMaterial);
            ring.rotation.x = Math.PI / 2;
            ring.renderOrder = 4;           // over a black hole's disc and halo (3)
            indicatorGroup.add(ring);

            // Add a second smaller ring for more emphasis
            const innerRingGeometry = joined([new THREE.RingGeometry(105, 112, 128),
                ...Array.from({ length: 12 }, (_, k) =>
                    new THREE.RingGeometry(112, 119, 1, 1, (k / 12 - 0.004) * 2 * Math.PI, 0.008 * 2 * Math.PI))]);
            const innerRingMaterial = new THREE.MeshBasicMaterial({
                color: 0xffffff,
                transparent: true,
                opacity: 0.6,
                side: THREE.DoubleSide,
                depthWrite: false
            });
            const innerRing = new THREE.Mesh(innerRingGeometry, innerRingMaterial);
            innerRing.rotation.x = Math.PI / 2;
            innerRing.renderOrder = 4;
            indicatorGroup.add(innerRing);

            indicatorGroup.position.copy(star.position);
            indicatorGroup.userData.isSelectionIndicator = true;

            scene.add(indicatorGroup);
            selectionIndicator = indicatorGroup;
        }

        function selectStar(star) {
            // Selected under the pointer: back to its size, the mark is enough.
            if (star && hoveredStar === star) resetStarHoverState(star);
            selectedStar = star;
            createSelectionIndicator(star);
            createPlanetOrbits(star);

            // Update info display
            if (star) {
                byId('star-info').innerHTML = buildStarInfoHTML(
                    star.userData,
                    { hintText: HOVER_HINT }
                );
            }
        }

        function deselectStar() {
            selectedStar = null;
            if (selectionIndicator) {
                scene.remove(selectionIndicator);
                selectionIndicator = null;
            }
            removePlanetOrbits();
            byId('star-info').innerHTML = 'Hover over a star for details';
        }

        // The shared search (../space/search.js): the stars and the galactic centre.
        const searchables = () => {
            const shown = stars.filter(isShown);
            const all = galacticCenterObject ? [...shown, galacticCenterObject] : shown;
            return nebulaeShown ? [...all, ...nebulaItems] : all;
        };
        // Bloom and tone mapping, shared (../space/effects.js), and their toggle.
        // Milder than the system map's: a star's core is twice white here, and
        // the glow of hundreds of them spread wide tinted the whole map
        // (measured, an empty patch's brightness: 33 at the system map's
        // settings, 18 here; 7 with the effects off).
        const fx = createEffects(renderer, scene, camera, { strength: 0.35, radius: 0.05, threshold: 1.8 });
        fx.setSize(containerWidth, containerHeight);
        const removeQuality = qualityButton(byId('search-container'));
        // On a phone the details fold to their first lines, a tap unfolds them.
        const removeFold = foldable(byId('info'));
        const removeColours = starColourButton(byId('search-container'), 'galaxy', 'saturated', mode => {
            colourMode = mode;
            rebuildField();
        });
        const search = createSearch(byId('search-container'), {
            placeholder: 'Search for a star...',
            items: searchables,
            title: star => star.userData.name,
            detail: star => {
                const nebula = star.userData.nebula;
                if (nebula) return `${nebula.kind} nebula | ${Math.round(2 * Math.max(...nebula.size)).toLocaleString('en-GB')} ly across`;
                const pos = star.userData.position;
                return `${star.userData.spectralType || 'Unknown'} | Position: (${pos.x.toFixed(0)}, ${(-pos.z).toFixed(0)}, ${pos.y.toFixed(0)}) ly`;
            },
            choose: star => {
                const nebula = star.userData.nebula;
                // A nebula: flown to, framed by its size; nothing to select.
                if (nebula) nav.goTo(star.position.clone(), { distance: Math.max(...nebula.size) * 5, follow: false });
                else { selectStar(star); focusOnStar(star); }
            },
        });

        byId('toggle-grid-btn').addEventListener('click', () => toggleGridSystem());
        byId('focus-center-btn').addEventListener('click', () => focusGalacticCenter());
        byId('toggle-territories-btn').addEventListener('click', () => toggleTerritories());

        // Where the pointer is, for the hover each frame.
        const onMove = (e) => {
            const rect = container.getBoundingClientRect();
            mouse.x = ((e.clientX - rect.left) / containerWidth) * 2 - 1;
            mouse.y = -((e.clientY - rect.top) / containerHeight) * 2 + 1;
            hoverStale = true;
        };
        renderer.domElement.addEventListener('pointermove', onMove);
        renderer.domElement.addEventListener('pointerenter', () => { pointerInside = true; });
        renderer.domElement.addEventListener('pointerleave', () => { pointerInside = false; });

        // The star under a click: the nearest hit's top group.
        function starAt(e) {
            if (e) onMove(e);
            const k = field ? field.nearest(mouse, camera, containerWidth, containerHeight) : -1;
            if (k >= 0) return fieldStars[k];
            if (!galacticCenterObject) return null;
            raycaster.setFromCamera(mouse, camera);
            return raycaster.intersectObject(galacticCenterObject, true).length ? galacticCenterObject : null;
        }

        // The shared clicks (../space/pointer.js): a click goes to a star —
        // selects it and flies there; a click on nothing, or Esc, lets go.
        const detachPointer = attachPointer(renderer.domElement, {
            pick: starAt,
            onPick: star => { selectStar(star); travelPick(star); focusOnStar(star); },
            onNothing: () => { nav.letGo(); deselectStar(); },
            onEscape: () => { if (selectedStar) { nav.letGo(); deselectStar(); } },
            live: () => root.isConnected,
        });
        renderer.domElement.addEventListener('contextmenu', (e) => e.preventDefault());
        // Double-click a star: into its system map, where the page has one.
        renderer.domElement.addEventListener('dblclick', (e) => {
            const star = starAt(e);
            const into = star && star.isStarRecord && links.system ? systemLink(star.userData) : null;
            if (into) location.href = into;
        });

        const onResize = () => {
            const newWidth = container.clientWidth;
            const newHeight = container.clientHeight;
            camera.aspect = newWidth / newHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(newWidth, newHeight);
            fx.setSize(newWidth, newHeight);
            containerWidth = newWidth;
            containerHeight = newHeight;
        };
        globalThis.addEventListener('resize', onResize);

        // Trail update optimization - only update every N frames
        let trailUpdateCounter = 0;
        const TRAIL_UPDATE_INTERVAL = 3;

        // Remove the hover lines, freeing their geometry and material: a new
        // pair is made for every star the pointer reaches.
        function clearHoverLines() {
            for (const line of [hoverLine, hoverFlowLine]) {
                if (!line) continue;
                scene.remove(line);
                line.geometry.dispose();
                line.material.dispose();
            }
            hoverLine = null;
            hoverFlowLine = null;
            hoverFlowProgress = 0;
        }

        function animate() {
            frameId = requestAnimationFrame(animate);
            nav.update();
            if (nebulaField) nebulaField.update(camera, containerHeight, renderer.getPixelRatio());

            if (!lastView.equals(camera.matrixWorld)) { lastView.copy(camera.matrixWorld); hoverStale = true; }
            if (hoverStale) { lastHit = pointerInside ? starAt(null) : null; hoverStale = false; }
            const hit = lastHit;
            let currentlyHovering = null;

            if (hit) {
                const starGroup = hit;
                {
                    currentlyHovering = starGroup;

                    const isNewStar = (hoveredStar !== starGroup);

                    if (isNewStar) {
                        if (hoveredStar) {
                            resetStarHoverState(hoveredStar);
                        }

                        clearHoverLines();

                        hoveredStar = starGroup;

                        // The selected one does not grow under the pointer
                        //: it is marked already.
                        if (starGroup !== selectedStar) {
                            if (starGroup.isStarRecord) {
                                field.setHovered(starGroup.fieldIndex);
                                // Its overlay grows with it, as the galactic centre does.
                                if (starGroup.overlay) starGroup.overlay.scale.setScalar(starGroup.overlay.userData.base * 1.3);
                            } else {
                                // The galactic centre: grown whole — its parts apart,
                                // the horizon outgrew its photon ring and hid it.
                                starGroup.scale.setScalar(1.3);
                            }
                        }

                        // Only create hover lines if a star is selected
                        if (selectedStar && selectedStar !== starGroup) {
                            const lineGeometry = new THREE.BufferGeometry().setFromPoints([
                                selectedStar.position.clone(),
                                starGroup.position.clone()
                            ]);

                            const starColor = colourOf(starGroup.userData.properties);

                            const lineMaterial = new THREE.LineBasicMaterial({
                                color: starColor,
                                transparent: true,
                                opacity: 0.3
                            });

                            hoverLine = new THREE.Line(lineGeometry, lineMaterial);
                            scene.add(hoverLine);

                            const flowGeometry = new THREE.BufferGeometry();
                            const flowPositions = new Float32Array(numFlowSegments * 3);
                            const flowColors = new Float32Array(numFlowSegments * 3);

                            const color = new THREE.Color(starColor);

                            for (let i = 0; i < numFlowSegments; i++) {
                                const t = i / (numFlowSegments - 1);
                                flowPositions[i * 3] = selectedStar.position.x + (starGroup.position.x - selectedStar.position.x) * t;
                                flowPositions[i * 3 + 1] = selectedStar.position.y + (starGroup.position.y - selectedStar.position.y) * t;
                                flowPositions[i * 3 + 2] = selectedStar.position.z + (starGroup.position.z - selectedStar.position.z) * t;

                                flowColors[i * 3] = color.r;
                                flowColors[i * 3 + 1] = color.g;
                                flowColors[i * 3 + 2] = color.b;
                            }

                            flowGeometry.setAttribute('position', new THREE.BufferAttribute(flowPositions, 3));
                            flowGeometry.setAttribute('color', new THREE.BufferAttribute(flowColors, 3));

                            const flowMaterial = new THREE.LineBasicMaterial({
                                vertexColors: true,
                                transparent: true,
                                opacity: 1,
                                linewidth: 3,
                                blending: THREE.AdditiveBlending
                            });

                            hoverFlowLine = new THREE.Line(flowGeometry, flowMaterial);
                            scene.add(hoverFlowLine);
                        }
                    }

                    if (hoverFlowLine && selectedStar) {
                        const positions = hoverFlowLine.geometry.attributes.position.array;
                        for (let i = 0; i < numFlowSegments; i++) {
                            const t = i / (numFlowSegments - 1);
                            positions[i * 3] = selectedStar.position.x + (starGroup.position.x - selectedStar.position.x) * t;
                            positions[i * 3 + 1] = selectedStar.position.y + (starGroup.position.y - selectedStar.position.y) * t;
                            positions[i * 3 + 2] = selectedStar.position.z + (starGroup.position.z - selectedStar.position.z) * t;
                        }
                        hoverFlowLine.geometry.attributes.position.needsUpdate = true;
                    }

                    const info = starGroup.userData;

                    // Show distance from selected star if one is selected
                    if (selectedStar && selectedStar !== starGroup) {
                        const distance = selectedStar.position.distanceTo(starGroup.position);
                        byId('star-info').innerHTML = buildStarInfoHTML(
                            selectedStar.userData,
                            { targetStar: info, distance: distance }
                        );
                    } else if (selectedStar && selectedStar === starGroup) {
                        // Hovering over the selected star itself
                        byId('star-info').innerHTML = buildStarInfoHTML(
                            selectedStar.userData,
                            { hintText: HOVER_HINT }
                        );
                    } else {
                        // No star selected, just show hover info
                        byId('star-info').innerHTML = buildStarInfoHTML(
                            info,
                            { hintText: 'Click to select this star' }
                        );
                    }
                }
            }

            if (!currentlyHovering && hoveredStar) {
                resetStarHoverState(hoveredStar);

                clearHoverLines();

                hoveredStar = null;

                // Show selected star info if one is selected, otherwise show default message
                if (selectedStar) {
                    byId('star-info').innerHTML = buildStarInfoHTML(
                        selectedStar.userData,
                        { hintText: HOVER_HINT }
                    );
                } else {
                    byId('star-info').textContent = 'Hover over a star for details';
                }
            }

            flowRoute();

            if (hoverFlowLine) {
                const colors = hoverFlowLine.geometry.attributes.color.array;

                const baseColor = new THREE.Color();
                if (hoverFlowLine.userData.baseColor) {
                    baseColor.copy(hoverFlowLine.userData.baseColor);
                } else {
                    baseColor.setRGB(colors[0], colors[1], colors[2]);
                    hoverFlowLine.userData.baseColor = baseColor.clone();
                }

                hoverFlowProgress += 0.02;
                if (hoverFlowProgress >= 1) {
                    hoverFlowProgress -= 1;
                }

                const flowLength = 0.3;

                for (let i = 0; i < numFlowSegments; i++) {
                    const t = i / (numFlowSegments - 1);

                    let distanceFromFlow = Math.abs(t - hoverFlowProgress);

                    if (distanceFromFlow > 0.5) {
                        distanceFromFlow = 1 - distanceFromFlow;
                    }

                    let alpha = 0;
                    if (distanceFromFlow < flowLength / 2) {
                        const normalized = distanceFromFlow / (flowLength / 2);
                        alpha = Math.cos(normalized * Math.PI / 2);
                        alpha = alpha * alpha;
                    }

                    colors[i * 3] = baseColor.r * alpha;
                    colors[i * 3 + 1] = baseColor.g * alpha;
                    colors[i * 3 + 2] = baseColor.b * alpha;
                }

                hoverFlowLine.geometry.attributes.color.needsUpdate = true;
            }

            const time = Date.now() * 0.001;

            // Animate selection indicator
            if (selectionIndicator) {
                // Rotate both rings in opposite directions
                selectionIndicator.children[0].rotation.z = time * 0.5;  // Outer ring
                selectionIndicator.children[1].rotation.z = -time * 0.7;  // Inner ring (counter-rotate)

                // Pulse the opacity slightly
                const pulse = Math.sin(time * 2) * 0.2 + 0.8;
                selectionIndicator.children.forEach(child => {
                    if (child.material) {
                        const baseopacity = child === selectionIndicator.children[0] ? 0.8 : 0.6;
                        child.material.opacity = baseopacity * pulse;
                    }
                });
            }

            // Animate orbiting planets
            if (orbitingPlanets.length > 0) {
                orbitingPlanets.forEach(planet => {
                    // Update angle based on orbital speed
                    planet.angle += planet.speed * 0.01;

                    // Axial rotation (independent of orbital speed)
                    if (planet.rotationSpeed) {
                        planet.globe.rotateY(planet.rotationSpeed);           // about its own, tilted axis
                    }

                    // Cloud rotation at 1.5x planet rotation speed
                    if (planet.cloudSphere && planet.rotationSpeed) {
                        planet.cloudSphere.rotation.y += planet.rotationSpeed * 1.5;
                    }

                    // Update planet position
                    planet.mesh.position.x = Math.cos(planet.angle) * planet.orbitRadius;
                    planet.mesh.position.y = 0;
                    planet.mesh.position.z = Math.sin(planet.angle) * planet.orbitRadius;

                    // Update planet label position
                    if (planet.label && planetOrbitsGroup && selectedStar) {
                        // Get world position of planet
                        const planetWorldPos = new THREE.Vector3();
                        planetWorldPos.copy(planet.mesh.position);
                        planetWorldPos.add(planetOrbitsGroup.position);

                        // Project to screen space
                        const screenPos = planetWorldPos.clone().project(camera);

                        if (screenPos.z < 1) {
                            const x = (screenPos.x * 0.5 + 0.5) * containerWidth;
                            const y = (-screenPos.y * 0.5 + 0.5) * containerHeight;

                            planet.label.style.left = (x + 12) + 'px';
                            planet.label.style.top = (y - 5) + 'px';
                            planet.label.style.display = 'block';

                            // Calculate opacity based on distance from camera
                            const distance = camera.position.distanceTo(planetWorldPos);
                            const maxDistance = 2000;
                            const minDistance = 200;
                            let opacity = 1;

                            if (distance > maxDistance) {
                                opacity = 0;
                            } else if (distance > minDistance) {
                                opacity = 1 - (distance - minDistance) / (maxDistance - minDistance);
                            }

                            planet.label.style.opacity = opacity.toString();
                        } else {
                            planet.label.style.display = 'none';
                        }
                    }

                    // Update trail positions (optimized to update every N frames)
                    if (planet.trail && (trailUpdateCounter % TRAIL_UPDATE_INTERVAL === 0)) {
                        const trailPositions = planet.trail.geometry.attributes.position.array;
                        const trailColors = planet.trail.geometry.attributes.color.array;

                        const starColor = colourOf(selectedStar?.userData.properties);
                        const color = new THREE.Color(starColor);

                        for (let i = 0; i < planet.trailSegments; i++) {
                            const trailAngle = planet.angle - (i / planet.trailSegments) * Math.PI * 0.5;
                            trailPositions[i * 3] = Math.cos(trailAngle) * planet.orbitRadius;
                            trailPositions[i * 3 + 1] = 0;
                            trailPositions[i * 3 + 2] = Math.sin(trailAngle) * planet.orbitRadius;

                            // Fade from bright to transparent
                            const alpha = 1 - (i / planet.trailSegments);
                            trailColors[i * 3] = color.r * alpha;
                            trailColors[i * 3 + 1] = color.g * alpha;
                            trailColors[i * 3 + 2] = color.b * alpha;
                        }

                        planet.trail.geometry.attributes.position.needsUpdate = true;
                        planet.trail.geometry.attributes.color.needsUpdate = true;
                    }
                });
            }

            trailUpdateCounter++;

            if (galacticCenterObject) galacticCenterObject.userData.update(performance.now() / 1000);

            // Seconds since the page opened, not since 1970: the shader works
            // in 32-bit floats, where 1.8 billion seconds move in steps of
            // minutes — the pulse and twinkle stood still.
            if (field) field.update(performance.now() / 1000, camera, containerHeight, renderer);
            spinPulsars(performance.now() / 1000);

            updateLabels();

            fx.render();
        }

        // A name beside a point on screen, faded with its distance; false if
        // the point is behind the camera.
        function placeLabel(label, position) {
            const screenPos = position.clone().project(camera);
            if (screenPos.z > 1) return false;
            label.style.left = ((screenPos.x * 0.5 + 0.5) * containerWidth + 15) + 'px';
            label.style.top = ((-screenPos.y * 0.5 + 0.5) * containerHeight - 5) + 'px';
            const distance = camera.position.distanceTo(position);
            const opacity = distance > LABEL_REACH ? 0 : distance > 500 ? 1 - (distance - 500) / (LABEL_REACH - 500) : 1;
            label.style.opacity = String(opacity);
            return opacity > 0;
        }

        // The names of the nearest stars (at most LABEL_LIMIT, within
        // LABEL_REACH), the selected and the hovered one always: a page
        // element per star moved every frame cost more than the stars.
        function chooseLabels() {
            const shown = [];
            for (const star of stars) {
                if (star.userData.real || star.userData.procedural) continue;   // named when hovered or chosen only
                if (!isShown(star)) continue;                                    // its layer switched off
                const d = camera.position.distanceTo(star.position);
                if (d < LABEL_REACH) shown.push([d, star]);
            }
            shown.sort((a, b) => a[0] - b[0]);
            return shown.slice(0, LABEL_LIMIT).map(([, star]) => star);
        }

        function updateLabels() {
            if (labelsFrame++ % LABEL_EVERY === 0) labelsChosen = chooseLabels();
            const chosen = labelsChosen.slice();
            for (const extra of [selectedStar, hoveredStar]) {
                if (extra && extra.isStarRecord && !chosen.includes(extra)) chosen.push(extra);
            }
            chosen.forEach((star, k) => {
                let label = labelPool[k];
                if (!label) {
                    label = document.createElement('div');
                    label.className = 'star-label';
                    labelsContainer.appendChild(label);
                    labelPool.push(label);
                }
                if (label.textContent !== star.userData.name) label.textContent = star.userData.name;
                label.style.display = placeLabel(label, star.position) ? 'block' : 'none';
            });
            for (let k = chosen.length; k < labelPool.length; k++) labelPool[k].style.display = 'none';
            if (centreLabel && galacticCenterObject) {
                centreLabel.style.display = placeLabel(centreLabel, galacticCenterObject.position) ? 'block' : 'none';
            }
        }

        animate();

        // Globe textures by planet name, published with the maps
        // (planets/index.json). Missing or unreadable
        // means none: every planet falls back to its procedural texture.
        async function loadManifest(url) {
            try {
                const response = url ? await fetch(url) : null;
                if (!response || !response.ok) return {};
                const manifest = await response.json();
                Object.keys(manifest).forEach(name => { manifest[name] = CONFIG.textureBase + manifest[name]; });
                return manifest;
            } catch (error) {
                return {};
            }
        }
        const loadTextureManifest = () => Promise.all([loadManifest(CONFIG.textures), loadManifest(CONFIG.heights)])
            .then(([textures, heights]) => ({ textures, heights }));

        // The layers merged as galaxy.catalogue merges them: by name, a later
        // layer's fields over an earlier one's, its `_removed` taken away; a
        // system belongs to every layer that names it (Sol in a story's layer
        // as well as the real sky's). Gate links joined, nebulae by name.
        async function loadLayers() {
            await layersReady;
            const docs = await Promise.all(LAYERS.map(layer => fetch(layer.url)
                .then(r => (r.ok ? r.json() : {})).catch(() => ({}))));
            const systems = new Map(), nebulae = new Map(), links = [];
            docs.forEach((doc, k) => {
                (doc.star_systems || []).forEach(obj => {
                    const earlier = systems.get(obj.name);
                    const merged = { ...earlier, ...obj, _layers: [...(earlier ? earlier._layers : []), LAYERS[k]] };
                    // The fields a later layer takes away (`_removed`).
                    (obj._removed || []).forEach(key => { delete merged[key]; });
                    delete merged._removed;
                    systems.set(obj.name, merged);
                });
                (doc.nebulae || []).forEach(n => nebulae.set(n.name, { ...(nebulae.get(n.name) || {}), ...n }));
                links.push(...(doc.gate_links || []));
            });
            return { star_systems: [...systems.values()], nebulae: [...nebulae.values()], gate_links: links };
        }

        async function loadStarData() {
            try {
                const [data, { textures, heights }] = await Promise.all([loadLayers(), loadTextureManifest()]);

                stars.length = 0;

                if (data.star_systems) {
                    data.star_systems.forEach(obj => {
                        if (obj.x !== undefined && obj.y !== undefined) {
                            const star = {
                                name: obj.name,
                                x: obj.x,
                                y: obj.z || 0,
                                z: -obj.y,
                                spectralType: obj.spectral_class || 'Unknown',
                                objectType: obj.object_type,
                                // Drawn as the real sky's: only real layers name it, or (one
                                // file, no layers) a star with a catalogue number.
                                real: CONFIG.layers ? obj._layers.every(layer => layer.real)
                                    : (obj.stars || []).some(s => s.hip),
                                layers: obj._layers.map(layer => layer.id),
                                // The planets only: no dwarf planets (`dwarf: true`) on the
                                // galaxy map (Sol's eight).
                                planets: (obj.planets || []).filter(p => !p.dwarf).map(p =>
                                    textures[p.name] ? { ...p, texture: textures[p.name], relief: heights[p.name] } : p),
                                planetCount: obj.planet_count || 0
                            };

                            createStar(star);
                        }
                    });
                }

                if (procDots) procDots.forEach(createStar);
                rebuildField();
                storyNebulae = data.nebulae || [];
                refreshNebulae();
                labelsFrame = 0;
                lastHit = null;
                hoverStale = true;
                gateLinks = data.gate_links || [];
                drawGateNetwork();
                console.log(`Loaded ${stars.length} stars from JSON`);
            } catch (error) {
                console.error('Error loading star data:', error);
            }
        }

        // ── The gate network (galaxy.json `gate_links`; galaxy.gatenet) ─────
        // An overlay, toggled by ⌗: every gate link a faint cyan
        // line between its stars, a provisional one fainter. The button
        // shows once there are links.
        let gateLinks = [];
        // How travel looks — route colours, the streaming glow, the drive
        // slider, the gate overlay — from travel.json's `maps`, the one place
        // both maps read it from. Without it, no travel is drawn.
        // Its `modes` are the project's ways of travel beyond the own drive
        // and the gates, each with its label.
        var travelLook = null, travelModes = {};
        const travelLookReady = (CONFIG.travelSettings ? fetch(CONFIG.travelSettings) : Promise.resolve(null))
            .then(response => (response && response.ok ? response.json() : null))
            .then(settings => {
                travelLook = settings && settings.maps;
                travelModes = (settings && settings.modes) || {};
                return travelLook;
            })
            .catch(() => null);
        const gateGroup = new THREE.Group();
        gateGroup.visible = false;
        scene.add(gateGroup);
        (function gateButton() {
            const holder = byId('search-container');
            if (!holder) return;
            const button = document.createElement('button');
            button.className = 'space-tool icon-button';
            button.id = 'toggle-gates-btn';
            button.title = 'Toggle the gate network';
            toggleIcon(button, 'arrow-left-right');
            button.style.display = 'none';
            button.setAttribute('aria-pressed', 'false');
            button.addEventListener('click', () => {
                gateGroup.visible = !gateGroup.visible;
                button.setAttribute('aria-pressed', String(gateGroup.visible));
            });
            holder.appendChild(button);
        })();

        // The Layers panel: a switch for each layer, and the procedural
        // galaxy's; a system shows while a layer naming it is switched on.
        const layersPanel = (function () {
            const holder = byId('search-container');
            if (!holder) return null;
            const wrap = document.createElement('div');
            wrap.className = 'galaxy-layers';
            wrap.hidden = true;
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'space-tool icon-button';
            button.id = 'toggle-layers-btn';
            button.title = 'Layers';
            button.setAttribute('aria-expanded', 'false');
            button.setAttribute('aria-haspopup', 'true');
            button.innerHTML = icon('stack');
            const panel = document.createElement('div');
            panel.className = 'galaxy-layers-panel';
            panel.hidden = true;
            // The catalogue's layers first (known once their list is), then the procedural galaxy.
            const groups = { layers: document.createElement('div'), more: document.createElement('div') };
            panel.append(groups.layers, groups.more);
            const open = shown => {
                panel.hidden = !shown;
                button.setAttribute('aria-expanded', String(shown));
            };
            button.addEventListener('click', () => open(panel.hidden));
            const onOutside = event => { if (!wrap.contains(event.target)) open(false); };
            const onKey = event => { if (event.key === 'Escape' && !panel.hidden) { open(false); button.focus(); } };
            document.addEventListener('pointerdown', onOutside);
            document.addEventListener('keydown', onKey);
            layerListeners.push(['pointerdown', onOutside, document], ['keydown', onKey, document]);
            wrap.append(button, panel);
            holder.appendChild(wrap);
            // A row: its checkbox, icon and label; `set(shown)` is called on a change.
            const row = (name, iconName, shown, set, id, group = 'layers') => {
                const label = document.createElement('label');
                label.className = 'galaxy-layers-row';
                const box = document.createElement('input');
                box.type = 'checkbox';
                box.checked = shown;
                if (id) box.id = id;
                box.addEventListener('change', () => set(box.checked));
                label.append(box);
                label.insertAdjacentHTML('beforeend', `${icon(iconName)}<span>${escapeHtml(name)}</span>`);
                groups[group].appendChild(label);
                wrap.hidden = false;
                return box;
            };
            return { row };
        })();

        layersReady.then(() => LAYERS.filter(layer => layer.toggle !== false && LAYERS.length > 1).forEach(layer => {
            if (!layersPanel) return;
            const setShown = shown => {
                layerShown[layer.id] = shown;
                box.checked = shown;
                const gone = obj => obj && obj.isStarRecord && !isShown(obj);
                if (gone(selectedStar)) deselectStar();
                if (gone(hoveredStar)) { resetStarHoverState(hoveredStar); hoveredStar = null; }
                rebuildField();
                drawGateNetwork();
                labelsFrame = 0;
                hoverStale = true;
            };
            const box = layersPanel.row(layer.label || layer.id, layer.icon || 'star', layerShown[layer.id], shown => {
                try { localStorage.setItem(layerKey(layer), shown ? 'shown' : 'hidden'); } catch { /* this page only */ }
                setShown(shown);
                globalThis.dispatchEvent(new CustomEvent(layerKey(layer), { detail: shown }));
            }, `toggle-layer-${layer.id}`);
            // Chosen on another map of the page (a 2D map, say): followed.
            const listener = event => { if (event.detail !== layerShown[layer.id]) setShown(event.detail); };
            globalThis.addEventListener(layerKey(layer), listener);
            layerListeners.push([layerKey(layer), listener]);
        }));

        // The procedural galaxy's dots and network, fetched once.
        function loadProcedural() {
            if (!procLoading) {
                const json = url => fetch(url).then(r => (r.ok ? r.json() : null)).catch(() => null);
                procLoading = Promise.all([json(CONFIG.procedural), json(CONFIG.proceduralGates)]).then(([dots, gates]) => {
                    procNebulae = (dots && dots.nebulae) || [];
                    procDots = ((dots && dots.systems) || []).map(d => ({
                        name: d.name, x: d.x, y: d.z || 0, z: -d.y, spectralType: d.spectral_class || 'Unknown',
                        objectType: d.object_type,
                        procedural: d.id, planetCount: d.planet_count || 0,
                    }));
                    procLinks = (gates && gates.links) || null;
                    procDots.forEach(createStar);
                });
            }
            return procLoading;
        }

        (function proceduralRow() {
            if (!layersPanel || !CONFIG.procedural) return;
            let box = null;
            const show = () => { box.checked = procShown; };
            const setShown = async shown => {
                procShown = shown;
                show();
                if (shown) await loadProcedural();
                if (procShown !== shown) return;                 // pressed again while loading
                if (!shown && selectedStar && selectedStar.userData && selectedStar.userData.procedural) deselectStar();
                if (hoveredStar && hoveredStar.userData && hoveredStar.userData.procedural) { resetStarHoverState(hoveredStar); hoveredStar = null; }
                rebuildField();
                refreshNebulae();
                labelsFrame = 0;
                hoverStale = true;
                drawGateNetwork();
            };
            box = layersPanel.row('the uncharted systems (procedural)', 'sparkling', procShown, shown => {
                try { localStorage.setItem(PROC_KEY, shown ? 'shown' : 'hidden'); } catch { /* this page only */ }
                setShown(shown);
            }, 'toggle-procedural', 'more');
            showProcedural = () => setShown(true);
            if (procShown) setShown(true);
        })();

        // ── Nebulae ─────────────
        // Soft sprites through each nebula's ellipsoid (nebula-field.js);
        // shown or hidden by their button, the choice kept for every visit.
        const nebulaButton = (function () {
            const holder = byId('search-container');
            if (!holder) return null;
            const button = document.createElement('button');
            button.className = 'space-tool icon-button';
            button.id = 'toggle-nebulae-btn';
            button.hidden = true;
            toggleIcon(button, 'haze');
            const show = () => {
                button.setAttribute('aria-pressed', String(nebulaeShown));
                button.title = nebulaeShown ? 'Hide the nebulae' : 'Show the nebulae';
            };
            show();
            const setShown = shown => {
                nebulaeShown = shown;
                show();
                if (nebulaField) nebulaField.object.visible = nebulaeShown;
            };
            button.addEventListener('click', () => {
                try { localStorage.setItem(NEBULAE_KEY, !nebulaeShown ? 'shown' : 'hidden'); } catch { /* this page only */ }
                setShown(!nebulaeShown);
                globalThis.dispatchEvent(new CustomEvent(NEBULAE_KEY, { detail: nebulaeShown }));
            });
            // Chosen on another map of the page (a 2D map, say): followed.
            onNebulaeChosen = event => { if (event.detail !== nebulaeShown) setShown(event.detail); };
            globalThis.addEventListener(NEBULAE_KEY, onNebulaeChosen);
            holder.appendChild(button);
            return button;
        })();
        function showNebulae(list) {
            if (nebulaField) { scene.remove(nebulaField.object); nebulaField.dispose(); nebulaField = null; }
            if (nebulaButton) nebulaButton.hidden = !(list && list.length);
            nebulaItems = [];
            if (!list || !list.length) return;
            nebulaItems = list.map(n => {
                const item = new THREE.Object3D();
                item.position.set(n.x, n.z || 0, -n.y);
                item.userData = { name: n.name, nebula: n, position: item.position };
                return item;
            });
            nebulaField = createNebulaField(list);
            nebulaField.object.visible = nebulaeShown;
            scene.add(nebulaField.object);
        }

        (function stemsButton() {
            const holder = byId('search-container');
            if (!holder) return;
            const button = document.createElement('button');
            button.className = 'space-tool icon-button';
            button.id = 'toggle-stems-btn';
            toggleIcon(button, 'arrow-down');
            const show = () => {
                button.setAttribute('aria-pressed', String(stemsShown));
                button.title = stemsShown ? 'Hide the stems to the galactic plane' : 'Show the stems to the galactic plane';
            };
            show();
            button.addEventListener('click', () => {
                stemsShown = !stemsShown;
                try { localStorage.setItem(STEMS_KEY, stemsShown ? 'shown' : 'hidden'); } catch { /* this page only */ }
                show();
                if (field) field.setStems(stemsShown);
            });
            holder.appendChild(button);
        })();

        async function drawGateNetwork() {
            const look = await travelLookReady;
            if (!look) return;
            gateGroup.children.slice().forEach(line => {
                gateGroup.remove(line);
                line.geometry.dispose();
                line.material.dispose();
            });
            // Only between stars shown: a layer switched off takes its links along.
            const at = new Map(stars.filter(isShown).map(st => [st.userData.name, st.position]));
            const shownLinks = procShown && procLinks ? procLinks : gateLinks;
            for (const grade of ['permanent', 'provisional']) {
                const points = [];
                shownLinks.filter(link => (link.grade || 'permanent') === grade).forEach(link => {
                    const a = at.get(link.from), b = at.get(link.to);
                    if (a && b) points.push(a.clone(), b.clone());
                });
                if (!points.length) continue;
                gateGroup.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(points),
                    new THREE.LineBasicMaterial({ color: look.gate_overlay.colour, transparent: true,
                        opacity: look.gate_overlay.opacity[grade] })));
            }
            const button = byId('toggle-gates-btn');
            if (button) button.style.display = gateLinks.length ? '' : 'none';
        }

        // Nation territories through time, computed by galaxy/cli/territories.py.
        // Optional: the files are absent until there are nations, and then the
        // map is unchanged. index.json lists every interval of every world
        // branch; each points at a snapshot file, fetched when first shown.
        // Coordinates are galactic, mapped (x, z, -y) like the stars.
        const territoryGroup = new THREE.Group();
        scene.add(territoryGroup);
        const territoryBase = CONFIG.territories;
        const territorySnapshots = new Map();
        let territoryIndex = [];
        let territoryLayer = null;

        // Faint faces, brighter where the surface is seen edge-on: the shell
        // reads as a boundary while the stars inside stay visible.
        function territoryMaterial(color) {
            return new THREE.ShaderMaterial({
                uniforms: {color: {value: new THREE.Color(color)}, fade: {value: 0}},
                vertexShader: `
                    #include <common>
                    #include <logdepthbuf_pars_vertex>
                    varying vec3 vNormal;
                    varying vec3 vView;
                    void main() {
                        vec4 mv = modelViewMatrix * vec4(position, 1.0);
                        vNormal = normalize(normalMatrix * normal);
                        vView = normalize(-mv.xyz);
                        gl_Position = projectionMatrix * mv;
                        #include <logdepthbuf_vertex>
                    }`,
                fragmentShader: `
                    #include <common>
                    #include <logdepthbuf_pars_fragment>
                    uniform vec3 color;
                    uniform float fade;
                    varying vec3 vNormal;
                    varying vec3 vView;
                    void main() {
                        #include <logdepthbuf_fragment>
                        float rim = 1.0 - abs(dot(normalize(vNormal), normalize(vView)));
                        gl_FragColor = vec4(color, (0.015 + 0.2 * pow(rim, 3.0)) * fade);
                    }`,
                transparent: true,
                depthWrite: false,
                side: THREE.DoubleSide
            });
        }

        function buildTerritoryLayer(snapshot) {
            const layer = new THREE.Group();
            const byName = new Map(stars.map(s => [s.userData.name, s]));
            snapshot.territories.forEach(t => {
                const positions = new Float32Array(t.vertices.length * 3);
                t.vertices.forEach(([x, y, z], i) => positions.set([x, z, -y], i * 3));
                const geometry = new THREE.BufferGeometry();
                geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
                geometry.setIndex(t.faces.flat());
                geometry.computeVertexNormals();
                layer.add(new THREE.Mesh(geometry, territoryMaterial(t.color)));

                // Member stars get a halo in the nation colour, so membership
                // shows even when the shell is seen face-on.
                t.members.forEach(name => {
                    const star = byName.get(name);
                    if (!star) return;
                    const halo = new THREE.Mesh(
                        new THREE.SphereGeometry(90, 24, 24),
                        new THREE.MeshBasicMaterial({
                            color: t.color, transparent: true, opacity: 0,
                            blending: THREE.AdditiveBlending, depthWrite: false
                        })
                    );
                    halo.position.copy(star.position);
                    layer.add(halo);
                });
            });
            return layer;
        }

        function setLayerFade(layer, fade) {
            layer.traverse(o => {
                if (!o.material) return;
                if (o.material.uniforms) o.material.uniforms.fade.value = fade;
                else o.material.opacity = 0.35 * fade;
            });
        }

        function disposeLayer(layer) {
            territoryGroup.remove(layer);
            layer.traverse(o => {
                o.geometry?.dispose();
                o.material?.dispose();
            });
        }

        // Shapes before and after a change differ in topology, so they cannot
        // morph; a short cross-fade shows what moved instead.
        // Fetches can finish out of order while the slider moves, so only the
        // latest request may draw — otherwise an older snapshot lands last and
        // the map disagrees with the date shown.
        let latestSnapshotRequest = 0;
        async function showSnapshot(entry) {
            const request = ++latestSnapshotRequest;
            let snapshot = territorySnapshots.get(entry.file);
            if (!snapshot) {
                snapshot = await (await fetch(territoryBase + entry.file)).json();
                territorySnapshots.set(entry.file, snapshot);
            }
            if (request !== latestSnapshotRequest) return;
            const previous = territoryLayer;
            const layer = buildTerritoryLayer(snapshot);
            territoryGroup.add(layer);
            territoryLayer = layer;
            // Timed from the first frame's own timestamp: rAF time and
            // performance.now() need not share an origin, and when they differ
            // the fade never advances.
            let start = null;
            const step = now => {
                if (start === null) start = now;
                const f = Math.min(1, Math.max(0, (now - start) / 400));
                setLayerFade(layer, f);
                if (previous) setLayerFade(previous, 1 - f);
                if (f < 1) requestAnimationFrame(step);
                else if (previous) disposeLayer(previous);
            };
            requestAnimationFrame(step);
        }

        // The world selector offers 'original' (holdings valid in every
        // branch) plus each branch that differs; the slider steps through that
        // branch's intervals.
        const worldSelect = byId('territory-world');
        const timeSlider = byId('territory-time');
        const dateLabel = byId('territory-date');

        function territoryWorld() {
            return worldSelect.value === '' ? null : worldSelect.value;
        }

        function intervalsFor(world) {
            return territoryIndex.filter(e => e.world === world);
        }

        function intervalLabel(e) {
            if (e.from && e.to) return `${e.from} – ${e.to}`;
            if (e.from) return `since ${e.from}`;
            if (e.to) return `before ${e.to}`;
            return 'all recorded time';
        }

        function showInterval() {
            const entry = intervalsFor(territoryWorld())[Number(timeSlider.value)];
            if (!entry) return;
            dateLabel.textContent = intervalLabel(entry);
            showSnapshot(entry);
        }

        function switchWorld() {
            // Stay at the same moment where the new branch has it.
            const lastWorld = worldSelect.dataset.last === '' ? null : worldSelect.dataset.last;
            const current = (intervalsFor(lastWorld)[Number(timeSlider.value)] || {}).from;
            const list = intervalsFor(territoryWorld());
            const same = list.findIndex(e => e.from === current);
            timeSlider.max = String(list.length - 1);
            timeSlider.value = String(same >= 0 ? same : Math.min(Number(timeSlider.value), list.length - 1));
            timeSlider.hidden = list.length < 2;
            worldSelect.dataset.last = worldSelect.value;
            showInterval();
        }

        async function loadTerritories() {
            // None given (the public maps site): no territories, nothing fetched.
            if (!territoryBase) return;
            try {
                const response = await fetch(territoryBase + 'index.json');
                if (!response.ok) return;
                territoryIndex = (await response.json()).snapshots;
            } catch (error) {
                return;
            }
            if (!territoryIndex.length) return;
            const worlds = [...new Set(territoryIndex.map(e => e.world))];
            worlds.forEach(w => {
                const option = document.createElement('option');
                option.value = w ?? '';
                option.textContent = w === null ? 'original' : `world ${w}`;
                worldSelect.appendChild(option);
            });
            worldSelect.hidden = worlds.length < 2;
            worldSelect.dataset.last = worldSelect.value;
            const list = intervalsFor(null);
            timeSlider.max = String(list.length - 1);
            timeSlider.value = String(list.length - 1);  // the latest state first
            timeSlider.hidden = list.length < 2;
            worldSelect.addEventListener('change', switchWorld);
            timeSlider.addEventListener('input', showInterval);
            byId('territory-controls').hidden = false;
            byId('toggle-territories-btn').hidden = false;
            showInterval();
        }

        function toggleTerritories() {
            territoryGroup.visible = !territoryGroup.visible;
            byId('territory-controls').hidden = !territoryGroup.visible;
            byId('toggle-territories-btn').setAttribute('aria-pressed', String(territoryGroup.visible));
        }


        // ── Travel ─────────────────
        // Only where a page names a planner (an editor sets CONFIG.travel):
        // a trip between two stars, every way compared, the chosen one drawn.
        // Galaxy coordinates (x, y, height) are the scene's (x, -z, y).
        const routeColour = kind => (travelLook.route_colours[kind] || '#ffffff');
        // var, not const: the animation loop, which streams a route, starts before this line runs.
        var travel = { panel: null, route: null, chosen: null, query: null, options: null, trips: null, flow: 0 };
        travelLookReady.then(look => {
            if (!look) return;
            TRAVEL_DRIVES = [...BUILT_IN_DRIVES, ...Object.entries(travelModes).map(([name, mode]) => [name, mode.label || name])];
            if (CONFIG.travel) setUpTravel();
            setUpTrips();
        });

        function setUpTravel() {
            const button = document.createElement('button');
            button.className = 'space-tool icon-button';
            button.id = 'toggle-travel-btn';
            button.title = 'Travel: a trip between two stars';
            toggleIcon(button, 'route');
            button.setAttribute('aria-pressed', 'false');
            byId('search-container').appendChild(button);
            const panel = document.createElement('div');
            panel.id = 'travel-panel';
            panel.className = 'travel-panel';
            panel.hidden = true;
            panel.innerHTML = `
                <div class="travel-row">
                    <label>From <input id="travel-from" list="travel-stars" autocomplete="off"></label>
                    <label>To <input id="travel-to" list="travel-stars" autocomplete="off"></label>
                </div>
                <div class="travel-row">
                    <label title="The drive this trip flies: its way is drawn; every way is compared below">Drive
                        <input type="range" id="travel-drive" min="0" max="${TRAVEL_DRIVES.length - 1}" step="1" value="${TRAVEL_DRIVES.findIndex(([way]) => way === 'own drive')}"></label>
                </div>
                <div id="travel-drive-text" class="travel-via">Own drive</div>
                <div class="travel-row" id="travel-setting">
                    <label title="The own drive's share of its speed, chosen per trip">Speed
                        <input type="range" id="travel-eff" min="0" max="${shareSteps()}" step="1" value="${shareSteps()}"></label>
                </div>
                <div id="travel-eff-text" class="travel-via">at full speed</div>
                <div class="travel-row">
                    <label>Leaving <input id="travel-depart" placeholder="${escapeHtml(CONFIG.departPlaceholder)}" autocomplete="off"></label>
                    <button type="button" id="travel-go">Plan</button>
                </div>
                <datalist id="travel-stars"></datalist>
                <div id="travel-hint">Click a star for the start, another for the destination.</div>
                <div id="travel-none" class="travel-via" role="status" hidden></div>
                <div id="travel-results"></div>
                <div id="trip-keep" hidden>
                    <h4>Keep this trip</h4>
                    <div class="travel-row">
                        <label>Name <input id="trip-keep-name" autocomplete="off"></label>
                        <label>Arrive by <input id="trip-keep-by" placeholder="optional" autocomplete="off"></label>
                        <button type="button" id="trip-keep-go">Keep</button>
                    </div>
                    <div id="trip-keep-hint" class="travel-via"></div>
                </div>
                <h4>Stored trips</h4>
                <div id="travel-stored" class="travel-via">None yet.</div>`;
            document.querySelector('.galaxy-map-wrapper').appendChild(panel);
            travel.panel = panel;
            button.addEventListener('click', () => {
                panel.hidden = !panel.hidden;
                button.setAttribute('aria-pressed', String(!panel.hidden));
                if (panel.hidden) clearRoute();
                panel.querySelector('#travel-stars').innerHTML = stars.map(st => st.userData.name).sort()
                    .map(n => `<option value="${escapeHtml(n)}"></option>`).join('');
            });
            panel.querySelector('#travel-go').addEventListener('click', planTrip);
            // The own drive's share of its speed (galaxy.travel.drive_share): a
            // thousandth to all of it, a tenth of a decade a step — as the
            // star-system map's slider, whose range reaches further down.
            const slider = panel.querySelector('#travel-eff');
            slider.addEventListener('input', showShare);
            slider.addEventListener('change', () => { if (travel.query) planTrip(); });
            // The drive: its way drawn
            // from the plan there is; the speed only for the own drive.
            const drive = panel.querySelector('#travel-drive');
            drive.addEventListener('input', showDrive);
            drive.addEventListener('change', () => { if (travel.options) chooseDrive(TRAVEL_DRIVES[+drive.value][0]); });
            panel.querySelector('#trip-keep-go').addEventListener('click', keepTrip);
            panel.querySelector('#trip-keep-name').addEventListener('input', () => {
                travel.replacing = null;
                panel.querySelector('#trip-keep-go').textContent = 'Keep';
            });
            panel.querySelectorAll('input').forEach(input =>
                input.addEventListener('keydown', e => { if (e.key === 'Enter') planTrip(); }));
        }

        // A star clicked while the panel is open: the start, then the
        // destination — and the trip is planned.
        function travelPick(star) {
            if (!travel.panel || travel.panel.hidden) return;
            const from = travel.panel.querySelector('#travel-from'), to = travel.panel.querySelector('#travel-to');
            const name = star.userData.name;
            if (!from.value || to.value) {
                from.value = name;
                to.value = '';
                clearRoute();
                travel.panel.querySelector('#travel-results').innerHTML = '';
                travel.panel.querySelector('#travel-hint').textContent = `From ${name} — now click the destination.`;
            } else if (name !== from.value) {
                to.value = name;
                planTrip();
            }
        }

        // The drive slider's stops between the stars, slowest first: the way
        // names galaxy.travel gives. Sublight is a system's (centuries here).
        // The drive slider's ways: the gates and the own drive, then the
        // project's modes (set when travel.json is read).
        const BUILT_IN_DRIVES = [['gates', 'Jump gate'], ['own drive', 'Own drive']];
        var TRAVEL_DRIVES = BUILT_IN_DRIVES;
        const driveLabel = way => (TRAVEL_DRIVES.find(([w]) => w === way) || [way, way])[1];

        // A speed between the stars: ly a day, and as multiples
        // of light — a light-year a year — rounded as a reader takes them.
        function lySpeed(lyPerDay) {
            const round = n => Number(n.toPrecision(3)).toLocaleString('en');
            return `${round(lyPerDay)} ly/day (${round(lyPerDay * 365.25)} c)`;
        }

        function showDrive() {
            const panel = travel.panel, way = TRAVEL_DRIVES[+panel.querySelector('#travel-drive').value][0];
            panel.querySelector('#travel-drive-text').textContent = driveLabel(way);
            panel.querySelector('#travel-setting').hidden = panel.querySelector('#travel-eff-text').hidden = way !== 'own drive';
            showShare();
        }

        /* A drive chosen — by the slider or a row: its way drawn, or why not. */
        function chooseDrive(way) {
            const panel = travel.panel;
            panel.querySelector('#travel-drive').value = String(TRAVEL_DRIVES.findIndex(([w]) => w === way));
            showDrive();
            travel.chosen = way;
            const option = travel.options.find(o => o.name === way);
            panel.querySelectorAll('#travel-results .travel-option').forEach(r => r.classList.toggle('is-chosen', r.dataset.way === way));
            const none = panel.querySelector('#travel-none');
            none.hidden = !!(option && option.reachable);
            panel.querySelector('#trip-keep').hidden = !(option && option.reachable);
            if (option && option.reachable) { drawRoute(option); return; }
            clearRoute();
            none.textContent = option ? `${driveLabel(way)}: ${option.why}.`
                : `${driveLabel(way)}: no way on this trip${way === 'gates' ? ' — no gate link, or none faster than the own drive'
                    : (travelModes[way] || {}).from_point ? ` — ${travel.query.start} has no ${travelModes[way].from_point}` : ''}.`;
        }

        // The slider: from travel.json's lowest share to all of it, a tenth of
        // a decade a step.
        function shareSteps() { return Math.round(-Math.log10(travelLook.drive_share_min.galaxy) * 10); }
        function shareOf(value) { const top = shareSteps(); return value >= top ? 1 : 10 ** ((value - top) / 10); }

        /* The share, and once planned the own drive's speed at it in average
         * web — scaled with the slider as it moves. */
        function showShare() {
            const panel = travel.panel, share = shareOf(+panel.querySelector('#travel-eff').value);
            const own = travel.options && travel.options.find(o => o.name === 'own drive' && o.rate);
            panel.querySelector('#travel-eff-text').textContent = shareText(share)
                + (own ? ` — ${lySpeed(own.rate / travel.query.share * share)} in average web` : '');
        }

        function shareText(share) {
            return share >= 1 ? 'at full speed' : `at 1/${Math.round(1 / share).toLocaleString('en')} of its speed`;
        }

        /* A way, as both maps show it: its name, how long, when it arrives;
         * under it the stops and how far. */
        function wayLine(option, unit) {
            if (!option.reachable && option.reachable !== undefined) {
                return `<strong>${escapeHtml(driveLabel(option.name))}</strong> <span class="travel-via">— ${escapeHtml(option.why)}</span>`;
            }
            const far = option.legs.reduce((sum, leg) => sum + (leg[unit] || 0), 0);
            const stops = option.legs.slice(0, -1).map(leg => leg.end);
            const how = [stops.length ? `via ${stops.map(escapeHtml).join(', ')}` : '',
                unit === 'ly' ? `${Math.round(far).toLocaleString('en')} ly` : `${far.toFixed(3)} AU`,
                // While moving; a jump has none — a shortcut, not a flight.
                unit === 'ly' && option.average ? `${lySpeed(option.average)} while moving` : ''].filter(Boolean).join(' · ');
            return `<strong>${escapeHtml(driveLabel(option.name))}</strong> ${duration(option.days)}`
                + (option.arrival ? ` <span class="travel-via">arrives ${escapeHtml(option.arrival)}</span>` : '')
                + `<br><span class="travel-via">${how}</span>`;
        }

        function duration(days) {
            if (days < 1 / 24 / 60) return `${+(days * 86400).toPrecision(2)} s`;
            if (days < 1 / 24) return `${Math.round(days * 24 * 60)} min`;
            if (days < 2) return `${(days * 24).toFixed(1)} h`;
            return `${days.toFixed(1)} days`;
        }

        async function planTrip() {
            const panel = travel.panel;
            const params = new URLSearchParams({
                start: panel.querySelector('#travel-from').value.trim(),
                end: panel.querySelector('#travel-to').value.trim(),
                depart: panel.querySelector('#travel-depart').value.trim(),
            });
            const share = shareOf(+panel.querySelector('#travel-eff').value);
            if (share < 1) params.set('efficiency', String(share));
            const hint = panel.querySelector('#travel-hint'), results = panel.querySelector('#travel-results');
            if (!params.get('start') || !params.get('end')) return;
            hint.textContent = 'Planning…';
            let data;
            try {
                const response = await fetch(`${CONFIG.travel}?${params}`);
                data = await response.json();
                if (!response.ok) throw new Error(data.error || response.statusText);
            } catch (error) {
                hint.textContent = String(error.message || error);
                results.innerHTML = '';
                return;
            }
            hint.textContent = `${data.start} → ${data.end}`;
            travel.query = { start: params.get('start'), end: params.get('end'), depart: params.get('depart'), share };
            travel.options = data.options;
            panel.querySelector('#trip-keep-hint').textContent = '';
            results.innerHTML = '';
            // Every way, each at its setting (the comparison
            // stays, under the sliders); a row chooses its drive.
            data.options.forEach(option => {
                const row = document.createElement('button');
                row.type = 'button';
                row.className = 'travel-option' + (option.reachable ? '' : ' is-blocked');
                row.dataset.way = option.name;
                row.innerHTML = wayLine(option, 'ly');
                row.addEventListener('click', () => chooseDrive(option.name));
                results.appendChild(row);
            });
            chooseDrive(TRAVEL_DRIVES[+panel.querySelector('#travel-drive').value][0]);
        }

        // ── Stored trips (galaxy.json `trips`, galaxy.trips) ───────────────
        // Shown on every map that has them, read-only; an editor keeps a
        // planned trip (CONFIG.tripSave) and removes one.

        function tripLine(trip) {
            const option = trip.option;
            if (!option) return `<strong>${escapeHtml(trip.name)}</strong> <span class="travel-via">— ${escapeHtml(trip.error || 'no route')}</span>`;
            const check = trip.check
                ? (trip.check.in_time
                    ? ` <span class="trip-in-time">${icon('check')} ${trip.check.spare_days.toFixed(1)} days to spare</span>`
                    : ` <span class="trip-late">${icon('close')} late by ${(-trip.check.spare_days).toFixed(1)} days</span>`)
                : '';
            const share = trip.efficiency && trip.efficiency < 1 && option.name === 'own drive' ? ` ${shareText(trip.efficiency)}` : '';
            return `<strong>${escapeHtml(trip.name)}</strong><br>`
                + `<span class="travel-via">${escapeHtml(trip.start)} → ${escapeHtml(trip.end)}, ${escapeHtml(driveLabel(option.name))}${escapeHtml(share)}, ${duration(option.days)}`
                + (option.arrival ? `, arrives ${escapeHtml(option.arrival)}` : '') + `</span>${check}`
                + (trip.note ? `<br><span class="trip-note">${escapeHtml(trip.note)}</span>` : '');
        }

        function listTrips(holder) {
            const list = (travel.trips && travel.trips.galaxy) || [];
            holder.innerHTML = list.length ? '' : 'None yet.';
            list.forEach(trip => {
                const line = document.createElement('div');
                line.className = 'trip-row';
                const row = document.createElement('button');
                row.type = 'button';
                row.className = 'travel-option' + (trip.option ? '' : ' is-blocked');
                row.innerHTML = tripLine(trip);
                if (trip.option) {
                    row.addEventListener('click', () => {
                        document.querySelectorAll('.trip-row .travel-option').forEach(r => r.classList.remove('is-chosen'));
                        row.classList.add('is-chosen');
                        drawRoute(trip.option);
                    });
                }
                line.appendChild(row);
                if (CONFIG.tripSave) {
                    const remove = document.createElement('button');
                    remove.type = 'button';
                    remove.className = 'trip-delete';
                    remove.title = `Remove the trip ${trip.name}`;
                    remove.setAttribute('aria-label', remove.title);
                    remove.innerHTML = icon('close');
                    // Asked first, in the row, as on the star-system map.
                    remove.addEventListener('click', () => {
                        const ask = document.createElement('div');
                        ask.className = 'trip-confirm';
                        ask.setAttribute('role', 'alertdialog');
                        ask.innerHTML = `<span>Remove the trip <strong>${escapeHtml(trip.name)}</strong>? It goes with the next save.</span>`;
                        const yes = document.createElement('button'), no = document.createElement('button');
                        yes.type = no.type = 'button';
                        yes.className = 'trip-confirm-yes';
                        yes.textContent = 'Remove';
                        no.textContent = 'Cancel';
                        const buttons = document.createElement('span');
                        buttons.className = 'trip-confirm-buttons';
                        buttons.append(no, yes);
                        ask.appendChild(buttons);
                        line.replaceWith(ask);
                        no.addEventListener('click', () => { ask.replaceWith(line); remove.focus(); });
                        yes.addEventListener('click', async () => {
                            const response = await fetch(`${CONFIG.tripSave}/${encodeURIComponent(trip.name)}`, { method: 'DELETE' });
                            const hint = byId('trip-keep-hint');
                            if (hint) hint.textContent = response.ok ? `Removed the trip ${trip.name} from the draft.` : `${trip.name} could not be removed.`;
                            await loadTrips();
                            if (response.ok && CONFIG.onChange) CONFIG.onChange();
                        });
                        no.focus();
                    });
                    line.appendChild(remove);
                }
                holder.appendChild(line);
            });
        }

        async function loadTrips() {
            if (!CONFIG.trips) { travel.trips = null; return; }      // none given: nothing fetched
            try {
                const response = await fetch(CONFIG.trips, { cache: 'no-store' });
                travel.trips = response.ok ? await response.json() : null;
            } catch (error) {
                travel.trips = null;
            }
            const stored = byId('travel-stored');
            if (stored) listTrips(stored);
            const panel = byId('trips-panel');
            if (panel) listTrips(panel.querySelector('.trips-list'));
            const button = byId('toggle-trips-btn');
            if (button) button.style.display = ((travel.trips && travel.trips.galaxy) || []).length ? '' : 'none';
        }

        /* Where there is no planner (a site): a ⚑ button and a
         * panel listing the stored trips, once there are any. */
        function setUpTrips() {
            if (!CONFIG.trips) return;
            if (!CONFIG.travel) {
                const button = document.createElement('button');
                button.className = 'space-tool icon-button';
                button.id = 'toggle-trips-btn';
                button.title = 'Trips: the journeys of the story';
                toggleIcon(button, 'flag');
                button.style.display = 'none';
                button.setAttribute('aria-pressed', 'false');
                byId('search-container').appendChild(button);
                const panel = document.createElement('div');
                panel.id = 'trips-panel';
                panel.className = 'travel-panel';
                panel.hidden = true;
                panel.innerHTML = '<h4>Trips</h4><div class="trips-list travel-via"></div>';
                document.querySelector('.galaxy-map-wrapper').appendChild(panel);
                button.addEventListener('click', () => {
                    panel.hidden = !panel.hidden;
                    button.setAttribute('aria-pressed', String(!panel.hidden));
                    if (panel.hidden) clearRoute();
                });
            }
            loadTrips();
        }

        async function keepTrip() {
            const panel = travel.panel, hint = panel.querySelector('#trip-keep-hint');
            const button = panel.querySelector('#trip-keep-go');
            if (!travel.query || !CONFIG.tripSave) return;
            const name = panel.querySelector('#trip-keep-name').value.trim();
            // A name in use asks first: Keep replaced that trip without a word
            //.
            const all = travel.trips ? [...(travel.trips.galaxy || []), ...Object.values(travel.trips.systems || {}).flat()] : [];
            const taken = !!name && all.some(t => t.name === name);
            if (taken && travel.replacing !== name) {
                travel.replacing = name;
                button.textContent = `Replace ${name}`;
                hint.textContent = `A trip named ${name} is stored already: Replace it, or give this one another name.`;
                return;
            }
            // The drive's setting kept with it: the own drive's share.
            const { share, ...query } = travel.query;
            const body = new URLSearchParams({ ...query, way: travel.chosen || '', name,
                by: panel.querySelector('#trip-keep-by').value.trim(),
                ...(travel.chosen === 'own drive' && share < 1 ? { efficiency: String(share) } : {}) });
            const response = await fetch(CONFIG.tripSave, { method: 'POST', body });
            const data = await response.json();
            travel.replacing = null;
            button.textContent = 'Keep';
            if (!response.ok) { hint.textContent = data.error || response.statusText; return; }
            hint.textContent = `${taken ? 'Replaced' : 'Kept'} the trip ${data.name} — it goes with the next save.`;
            await loadTrips();
            if (CONFIG.onChange) CONFIG.onChange();
        }

        function clearRoute() {
            if (travel.route) {
                scene.remove(travel.route);
                travel.route.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
                travel.route = null;
            }
        }

        /* A route as the distance line between two stars is drawn: each leg a faint line in its colour with a glow
         * streaming along it, start to end; a stop a small white point.
         * The star-system map draws its routes the same way
         * (system-map.js, streamLine). */

        function streamLine(points, colour, opacity = 1) {
            const group = new THREE.Group();
            group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),
                new THREE.LineBasicMaterial({ color: colour, transparent: true, opacity: travelLook.stream.line_opacity * opacity })));
            // Evenly along the length, so the glow keeps its pace over bends.
            const lengths = points.slice(1).map((p, k) => p.distanceTo(points[k]));
            const total = lengths.reduce((a, b) => a + b, 0) || 1;
            const positions = new Float32Array(travelLook.stream.samples * 3);
            for (let i = 0; i < travelLook.stream.samples; i++) {
                let left = total * i / (travelLook.stream.samples - 1), k = 0;
                while (k < lengths.length - 1 && left > lengths[k]) { left -= lengths[k]; k++; }
                const at = points[k].clone().lerp(points[k + 1] || points[k], lengths[k] ? Math.min(1, left / lengths[k]) : 0);
                positions.set([at.x, at.y, at.z], i * 3);
            }
            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
            geometry.setAttribute('color', new THREE.BufferAttribute(new Float32Array(travelLook.stream.samples * 3), 3));
            const flow = new THREE.Line(geometry, new THREE.LineBasicMaterial({
                vertexColors: true, transparent: true, opacity, blending: THREE.AdditiveBlending }));
            flow.userData.stream = new THREE.Color(colour);
            group.add(flow);
            return group;
        }

        /* Each frame: the glow a step further along every leg, a pulse of a
         * third of its length — as the distance line's. */
        function flowRoute() {
            if (!travel || !travel.route) return;
            const stream = travelLook.stream;
            travel.flow = (travel.flow + stream.step_per_frame) % 1;
            travel.route.traverse(line => {
                const colour = line.userData && line.userData.stream;
                if (!colour) return;
                const colors = line.geometry.attributes.color.array;
                for (let i = 0; i < travelLook.stream.samples; i++) {
                    let d = Math.abs(i / (travelLook.stream.samples - 1) - travel.flow);
                    d = Math.min(d, 1 - d);
                    const a = d < stream.pulse_share ? Math.cos(d / stream.pulse_share * Math.PI / 2) ** 2 : 0;
                    colors[i * 3] = colour.r * a; colors[i * 3 + 1] = colour.g * a; colors[i * 3 + 2] = colour.b * a;
                }
                line.geometry.attributes.color.needsUpdate = true;
            });
        }

        function stopPoints(points) {
            const geometry = new THREE.BufferGeometry().setFromPoints(points);
            return new THREE.Points(geometry, new THREE.PointsMaterial({
                color: 0xffffff, size: travelLook.stop_pixels, sizeAttenuation: false, transparent: true, opacity: 0.9 }));
        }

        function drawRoute(option) {
            clearRoute();
            const group = new THREE.Group();
            const scenePoint = p => new THREE.Vector3(p[0], p[2], -p[1]);
            const stops = [];
            option.legs.forEach((leg, k) => {
                const points = leg.points.map(scenePoint);
                if (points.length < 2) return;
                group.add(streamLine(points, routeColour(leg.kind), travelLook.route_opacity[leg.kind] ?? 1));
                if (k > 0) stops.push(points[0]);
            });
            if (stops.length) group.add(stopPoints(stops));
            scene.add(group);
            travel.route = group;
            travel.flow = 0;
            // The whole route in view.
            const sphere = new THREE.Box3().setFromObject(group).getBoundingSphere(new THREE.Sphere());
            // From above the plane, at least 0.9 rad up: level with it, a long route is a line.
            const now = camera.position.clone().sub(nav.controls.target).normalize();
            const up = Math.max(Math.asin(Math.max(-1, Math.min(1, now.y))), 0.9), round = Math.hypot(now.x, now.z) || 1;
            const direction = new THREE.Vector3(now.x / round * Math.cos(up), Math.sin(up), now.z / round * Math.cos(up));
            nav.goTo(sphere.center, { distance: Math.max(100, Math.min(50000, sphere.radius * 2.0)), follow: false, direction });
        }

        // The data again, after it changed: an editor's draft (the selection,
        // the camera and the territories stay).
        const reload = () => {
            const selected = selectedStar && selectedStar.userData.name;
            return loadStarData().then(() => {
                deselectStar();
                const again = selected && stars.find(st => st.userData.name === selected);
                if (again) selectStar(again);
            });
        };

        // Use absolute path from site root to work from any page location
        loadStarData().then(async () => {
            // Arrived from a system map: its star selected and in view — an
            // uncharted one's with the procedural layer shown.
            if (options.uncharted && CONFIG.procedural) await showProcedural();
            const star = options.uncharted
                ? stars.find(st => st.userData.procedural === options.uncharted)
                : options.focus && stars.find(st => st.userData.name === options.focus);
            if (star) { selectStar(star); focusOnStar(star); search.show(star.userData.name); }
            return loadTerritories();
        });

        return {
            reload,
            // A star by name selected and flown to, as the search does; false
            // when there is none (an editor's ◎, say).
            locate(name) {
                const star = stars.find(st => st.userData.name === name);
                if (!star) return false;
                selectStar(star); focusOnStar(star); search.show(name);
                return true;
            },
            destroy() {
                cancelAnimationFrame(frameId);
                if (field) field.dispose();
                if (nebulaField) nebulaField.dispose();
                detachPointer();
                search.dispose();
                nav.dispose();
                removeQuality();
                removeColours();
                removeFold();
                fx.dispose();
                PLANET_LOOK.releaseTextures();
                globalThis.removeEventListener('resize', onResize);
                layerListeners.forEach(([key, listener, target = globalThis]) => target.removeEventListener(key, listener));
                if (onNebulaeChosen) globalThis.removeEventListener(NEBULAE_KEY, onNebulaeChosen);
                renderer.dispose();
                renderer.forceContextLoss();   // or the context outlives the page: browsers cap them at about 16
                root.innerHTML = '';
            },
        };
}
