# Working in this repository

A guide for agents and people changing the engine. What the engine is and
how to use it: [README.md](README.md).

## Layout

| Path | What |
|---|---|
| `viewer/` | The 3D maps, ES modules on three.js: `galaxy/` (galaxy map), `system/` (star-system map), `planet/` (planet look, textures, globe view), `space/` (shared camera, pointer, search, sky, effects, calendar, manifest, icons). Published as the npm package's only files. |
| `python/` | The `galaxy` package (uv): catalogue and validation, procedural galaxy, orbits, travel, gate networks, territories, the SVG map, the build. CLIs in `galaxy/cli/`, shipped data in `galaxy/data/`, tests in `tests/`. |
| `examples/minimal/` | A complete small project; the tests and the demo use it. |
| `demo/` | `index.html` showing the example's maps; `demo/data/` is built, not committed. |
| `tools/icons.mjs` | Generates `viewer/space/icons.js` from the `remixicon` dev dependency. |
| `docs/` | Reference documentation (below). |

## Commands

| Command | Does |
|---|---|
| `make install` | `uv sync` in `python/` and `npm install`. |
| `make test` | The library's tests (`cd python && uv run pytest -q`). |
| `cd python && uv run pytest` | The same, verbose; add a path or `-k` to narrow. |
| `make demo` | Builds `examples/minimal` into `demo/data/` (procedural galaxy within 5 000 ly of Sol) and serves http://localhost:8040/demo/. |
| `make icons` | Regenerates `viewer/space/icons.js`; add a name to `NAMES` in `tools/icons.mjs` first. Never edit `icons.js` by hand. |

The viewer has no build step and no test suite; check a viewer change in
the demo.

## Conventions

- **No repository layout in the library.** Every file is found through a
  project (`galaxy.project`: `--project`, `GALAXY_PROJECT`, or
  `project.use`). Files the engine ships are named with `@` (`@real-sky`,
  `@milky-way`). Tests run against a temporary project
  (`python/tests/conftest.py`) or the example.
- **The library is generic.** No story's names, places or rules in code,
  data or tests; a project's own ways of travel, calendar, medium and names
  come from its files (`travel.json` `modes`, `calendar.json`,
  `medium.json`, `namer`).
- **Neutral comments.** Say what the code does and why. No personal names,
  no history of decisions, no story lore.
- **Deterministic output.** The same input writes the same bytes: seeded
  randomness (by name or id, never the process's hash), stable ordering,
  JSON as `galaxy.jsonstore.dumps`. Writes are atomic (`galaxy.fs`).
- **Additive data formats.** Optional fields stay absent until they carry
  information; derived fields (`planet_count`, `index`, `spectral_class`
  from `stars`) are recomputed by `galaxy.schema.normalise`, never trusted.
- **The viewer imports `three` by name** (`three`, `three/addons/…`); the
  host supplies it. No other runtime dependency, nothing fetched from
  remote.
- A data format change touches its reader and writer on both sides
  (Python export, viewer reader), the example, and `docs/data-formats.md`.

## Documentation

| File | Covers |
|---|---|
| [README.md](README.md) | Overview, project file, build, viewer quick start, credits. |
| [docs/data-formats.md](docs/data-formats.md) | Every file a project supplies and the build writes. |
| [docs/viewer.md](docs/viewer.md) | The three maps' options, endpoints, shared modules, browser state. |
| [docs/svg-map.md](docs/svg-map.md) | The 2D SVG map and its coordinate conversion. |

Keep them true to the code; a module's own header comment is the most
detailed account of it.
