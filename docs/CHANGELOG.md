# Galaxy Map Generator - Changelog

## Version 3.0 - Celestial Objects System

### Major Changes

#### 🌌 Complete Celestial Object System
- **Renamed Classes**: `StarClassification` → `CelestialObjectClassification`
- **New Object Types**: Support for 8 special object types beyond stars
- **Unified System**: Stars and special objects use same rendering pipeline
- **Smart Defaults**: `object_type` defaults to "star" for backward compatibility

#### 🕳️ Black Hole Rendering
- **Multi-layered accretion disk** with realistic visual effect
- **Three-layer system**: outer glow, middle disk, inner ring
- **Pure black core** with orange accretion disk (#ff4500)
- **Blur effects** for realistic appearance
- **Orange labels** for visibility against black core

#### 🌟 Special Objects Supported
1. **Black Hole** - Black core with glowing orange accretion disk
2. **Neutron Star** - Cyan with bright glow
3. **Pulsar** - Green with bright glow
4. **White Dwarf** - Pale blue compact star
5. **Wormhole** - Purple large object
6. **Anomaly** - Magenta mysterious object
7. **Nebula** - Hot pink large cloud (8.0× size)
8. **Quasar** - Bright yellow with glow

#### 📝 JSON Schema Changes
- **`galaxy_labels`** (was `labels`) - More descriptive field name
- **`celestial_objects`** (was `star_systems`) - Supports all object types
- **`object_type`** (new, optional) - Specifies object category, defaults to "star"
- **`spectral_class`** (was `type`) - Used for stellar classification
- **Backward compatible** - Old format still works

### New Features

#### Visual Enhancements
- Custom black hole rendering with accretion disk
- Per-object-type color schemes
- Glow effects for luminous objects
- Object-specific label colors (e.g., orange for black holes)
- CSS classes for each object type

#### Data Structure
- Cleaner separation between stars and special objects
- More descriptive field names
- Extensible for future object types
- Better semantic meaning

### Technical Improvements

#### New Methods
- `_create_black_hole()` - Specialized black hole renderer
- `CelestialObjectClassification.get_properties()` - Unified property getter
- Support for `secondary_color` in object properties

#### CSS Updates
- `.celestial-object` replaces `.star`
- `.object-dot` replaces `.star-dot`
- `.black-hole-accretion-*` classes for black hole layers
- Blur filters for accretion disk layers

### Migration Guide

#### Field Renaming
```json
# Old Format
{
  "labels": [...],
  "star_systems": [
    {"name": "Sol", "type": "G2V", ...}
  ]
}

# New Format (Recommended)
{
  "galaxy_labels": [...],
  "celestial_objects": [
    {
      "name": "Sol",
      "object_type": "star",
      "spectral_class": "G2V",
      ...
    }
  ]
}
```

#### Adding Special Objects
```json
{
  "celestial_objects": [
    {
      "name": "Cygnus X-1",
      "object_type": "black_hole",
      "x": 3700,
      "y": 2300
    }
  ]
}
```

### Documentation
- Added `CELESTIAL_OBJECTS.md` - Comprehensive guide
- Updated `example_data.json` with all object types
- Updated this `CHANGELOG.md`

### Backward Compatibility
✅ **100% Backward Compatible**
- Old field names (`labels`, `star_systems`) still work
- Old `type` field treated as `spectral_class`
- Automatic conversion to new format internally
- No breaking changes for existing JSON files

---

## Version 2.0 - Star Classification System

### New Features

#### 🌟 Star Classification System
- **Morgan-Keenan Classification**: Full support for O, B, A, F, G, K, M stellar types
- **Scientifically Accurate Colors**: Each star class rendered with realistic colors based on surface temperature
- **Dynamic Sizing**: Star size scales based on classification (larger for hot O/B stars, smaller for cool M stars)
- **Glow Effects**: Bright stars (O, B, A classes) automatically get a subtle glow effect
- **Type Labels**: Optional classification labels displayed below star names (e.g., "G2V")

#### 📊 Interactive Legend
- Automatic legend in top-right corner
- Shows all 7 star classes with example dots
- Displays temperature ranges for each class
- Includes unclassified star reference

#### 🎨 Enhanced Visual Effects
- **Star Hover Effects**:
  - Brightness increase (150%)
  - Bold labels
  - Intensified glow for bright stars
  - White outline on hover
- **Smooth Transitions**: All visual changes use CSS transitions for smooth animations

### JSON Format Updates

#### Optional `type` Field
Stars can now include an optional `type` field:

```json
{
  "name": "Sol",
  "type": "G2V",
  "x": 2800,
  "y": 2800,
  "coordinate_system": "graphic"
}
```

- If `type` is omitted, star renders as white (unclassified)
- First letter determines color/size (e.g., "G2V" → G class properties)
- Full type string is displayed on the map

### Technical Changes

#### New Class: `StarClassification`
- Centralized star property management
- Methods for getting color, size, temperature, description
- Easy to extend with new classifications

#### Updated Methods
- `add_star_systems()`: Now processes star type and applies classification
- `add_styles()`: Enhanced CSS with star-specific styles
- `create_legend()`: New method to generate classification legend

#### CSS Classes
New classes for styling:
- `.star-dot` - Main star circle
- `.star-glow` - Glow effect for bright stars
- `.star-label` - Star name text
- `.star-type-label` - Classification text

### Bug Fixes
- Fixed indentation error in class initialization
- Fixed rotation transform for labels (now includes center point)
- Added proper error handling in main()
- Corrected z-order comments for clarity

### Documentation
- Added `STAR_CLASSIFICATION.md` - Complete guide to using star classifications
- Updated `example_data.json` - Includes examples of all star types
- Added this `CHANGELOG.md`

### Example Usage

```bash
# Generate map with star classifications
python3 generate_galaxy_map.py \
  --input example_data.json \
  --output galaxy_map.svg \
  --width 5600 \
  --height 5600
```

### Star Types Reference

| Class | Example Stars | Temperature | Color |
|-------|---------------|-------------|-------|
| O | Zeta Puppis | 30,000+ K | Blue |
| B | Rigel, Spica | 10,000-30,000 K | Blue-white |
| A | Sirius, Vega | 7,500-10,000 K | White |
| F | Procyon | 6,000-7,500 K | Yellow-white |
| G | Sol, Alpha Centauri A | 5,200-6,000 K | Yellow |
| K | Arcturus, Aldebaran | 3,700-5,200 K | Orange |
| M | Proxima Centauri, Betelgeuse | <3,700 K | Red |

### Backward Compatibility
✅ **100% Backward Compatible**
- Existing JSON files without `type` field work perfectly
- All old features remain unchanged
- Stars without classification render as default white

---

## Version 1.0 - Initial Release

### Core Features
- SVG galaxy map generation
- Polar coordinate grid system (24 sectors × 15 rings)
- Galactic to graphic coordinate conversion
- Sector assignment and labeling
- Custom labels with rotation
- Interactive hover effects
- Inkscape layer support
