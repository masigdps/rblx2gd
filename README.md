# RBLX2GD

Converts Roblox Studio maps (`.rbxlx`) into Geometry Dash levels (`.gmd`) by projecting the 3D scene onto a side view and filling it with GD objects.

A spiritual successor to [MC2GD](https://github.com/masigdps) — same idea, same UI, different source format.

---

## Features

- Pure Python: only the standard library plus `tkinterdnd2` for drag & drop
- Side-view projection: Roblox `X`/`Y` become GD `X`/`Y`, `Z` is used as a depth slice
- Large parts are filled cell by cell instead of collapsing into a single cube
- Depth filtering, radius cropping and adjustable studs-per-block scale
- Draggable file input, console log, `CONVERT` / `STOP` controls
- Output is a GD 2.2 plist; the converter never opens a network connection and writes nothing outside the file you asked for

## Requirements

- Python 3.8+
- `tkinterdnd2` (only for the GUI)

```bash
pip install tkinterdnd2
```

`anvil`, `numpy` and friends are **not** required — the XML is read with the built-in `xml.etree.ElementTree`.

## Usage

```bash
python rblx2gd.py
```

1. Save your place in Studio via **File → Save to File As…** and keep the `.rbxlx` extension. A `.rbxl` file is binary and will be rejected.
2. Drag the file into the window, or paste its path into the field.
3. Fill in the parameters (see below).
4. Press **CONVERT**. The level lands on your Desktop as `<File Name>.gmd`.

If no Desktop folder exists, the file is written to your home directory instead.

## Parameters

| Field | Default | Meaning |
|---|---|---|
| **Drag .rbxlx file…** | — | Path to the Roblox XML place |
| **Z Layers** | `0` | One or more depth slices, comma separated. `all`, `*` or an empty field disables depth filtering |
| **Radius (0 = all)** | `0` | Keeps only parts with `\|x\|` within this many blocks from the map origin. `0` disables the filter |
| **Scale (studs/block)** | `1` | How many Roblox studs equal one Geometry Dash block |
| **Length (0 = all)** | `0` | Maximum level width in blocks. Everything past this column of the map is dropped. `0` keeps the full map |
| **File Name** | `rblx2gdfile` | Output file name (`<name>.gmd`) |
| **Level Name** | `rblx2gd level` | Level name shown in GD, max 20 characters |
| **Baseplate** | on | When unchecked, baseplates are excluded from the level |

### Choosing a scale

One block in Geometry Dash is 30 units, and the converter treats one stud as one unit.

```
scale ≈ map width in studs / desired width in blocks
```

The console prints the map extents on every run:

```
x: -256.0 .. 256.0
y: 0.0 .. 120.0
z: -256.0 .. 256.0
```

A 512×512 baseplate at `Scale = 1` would become 262 144 blocks and is skipped; at `Scale = 8` it fits comfortably.

### Keeping the level short

Geometry Dash chokes on very long levels and on uploads with a huge object string.
Two levers:

- **Length** caps the width in blocks — anything beyond that column of the map is cut, and the console reports `length limit: N blocks (cut X blocks, Y columns)`.
- **Scale** raises the studs-per-block ratio so the same map occupies fewer blocks.

The console always ends the run with the final size:

```text
width: 40 blocks, objects: 160
```

### Fast mode

The **fast (single-cell objects)** checkbox switches the fill rule:

- **off** — every part is filled cell by cell across its full projected rectangle (solid geometry)
- **on** — each part becomes a single object placed at the centre of its projected rectangle, and very wide flat parts are treated as baseplates

Object counts drop by one to two orders of magnitude, which is the reliable fix when GD refuses or mangles a long level. On a 67-block test map solid mode produced 208 objects and fast mode produced 8, with the layout still readable.

### Choosing a Z slice

A part is kept when its depth interval overlaps a requested layer:

```
z - Size.Z / 2  <=  requested layer  <=  z + Size.Z / 2
```

- `0` — only parts crossing the `z = 0` plane
- `0,40` — union of two slices
- `all` — every part, a flat side projection of the whole map

Start with `all`, then narrow down if background geometry floods the level.

## Geometry rules

- The projected rectangle is rounded to the block grid, then filled cell by cell
- Where parts overlap, a spike wins over a block; otherwise the first placement keeps the cell
- The map is cropped to its own bounds and shifted to `x = 300`, `y = 15` so the lowest row sits on the ground
- Parts larger than 60 000 blocks (typically a huge baseplate) are skipped and reported in the console
- The level stops growing at 60 000 objects; pressing `STOP` mid-run still writes a partial level

## Object mapping

| Roblox class | Result |
|---|---|
| `Part` (Block, Sphere, Cylinder, Ball) | filled with blocks |
| `WedgePart`, `CornerWedgePart`, `TrussPart`, `MeshPart`, `UnionOperation`, `NegateOperation` | skipped |

| Material | GD object |
|---|---|
| Plastic, SmoothPlastic, Neon, WoodPlanks, Marble, Basalt, Slate, Concrete, Granite, Brick, Pebble, Cobblestone, Rock, CorrodedMetal, DiamondPlate, Foil, Grass, Sand, Fabric, Snow, Mud, Ground, Sandstone, Ice, Glacier, Glass, Water | `1` — block |
| Metal | `13` — ship portal |
| Asphalt | `36` — yellow orb |
| Wood | `13` — yellow portal |
| CrackedLava | `8` — spike |
| Anything else, or no material | skipped |

A part whose name contains `spike`, `saw`, `blade`, `trap` or `barb` becomes a spike, `portal` becomes a yellow portal, `orb` becomes a yellow orb — these name rules override the material table.

## Output format

The `.gmd` file is an XML plist where `k4` holds the level string:

```
kS1,0,1,{objectId},2,{x},3,{y};1,{objectId},2,{x},3,{y};...
```

Each object is `1,<id>,2,<x>,3,<y>` terminated by a semicolon. Coordinates are integer GD units.

## Console log

```
loading: C:\Users\you\Downloads\Place.rbxlx
parts: 128
x: -256.0 .. 256.0
y: 0.0 .. 120.0
z: -256.0 .. 256.0
z filter: 128 / 128
blocks: 8421
done: C:\Users\you\Desktop\mylevel.gmd
```

Steps appear as `scanned: N / M`, oversized parts as `skip big part: <name>`, and any exception as `err: <message>`.

## Customising the mapping

All the tuning lives at the top of `rblx2gd.py`:

```python
GD_UNIT = 30
OFFSET_X = 300
OFFSET_Y = 15
MAX_OBJECTS = 60000
MAX_PART_CELLS = 60000
BLOCK_ID = 1
SPIKE_ID = 8
PORTAL_ID = 13
ORB_ID = 36
MATERIAL_BLOCKS = {256: 1, 1088: 13, 520: 36, ...}
SPIKE_NAMES = ("spike", "saw", "blade", "trap", "barb")
PORTAL_NAMES = ("portal",)
ORB_NAMES = ("orb",)
BASEPLATE_NAMES = ("baseplate", "base plate", "floor", "ground")
```

To map an additional material, add its Roblox enum value to `MATERIAL_BLOCKS`. Unknown materials resolve to `0`, which the converter treats as "skip this part".

### Baseplates

With **Baseplate** unchecked, a part is treated as a baseplate and dropped when either:

- its name contains `baseplate`, `base plate`, `floor` or `ground`, or
- its footprint is at least 100×100 blocks and it is 1 block thick or less

The console reports how many were dropped: `baseplate: off (skipped 2)`.

## Known limitations

- Rotation is ignored: a rotated part is filled by its axis-aligned bounding box, so slanted walls become rectangles
- Sphere and Cylinder parts are filled as rectangles, not curves
- Only `Part` is supported; wedges, meshes and unions are skipped
- Modelled on side-view projection: a map that reads well in 3D may need a narrower Z slice to read well in 2D
- Levels above roughly 60 000 objects are truncated

## Troubleshooting

| Message | Fix |
|---|---|
| `file must be .rbxlx` | Re-save from Studio with **Save to File As…** and the `.rbxlx` extension |
| `no Part objects found` | The place contains no `Part` instances, or the file is not a valid place |
| `nothing on these z layers` | Widen the Z filter or use `all` |
| `skip big part: Baseplate` | Raise `Scale` |
| `object cap reached` | Raise `Scale` or crop with `Radius` |

## Project structure

```
rblx2gd.py       GUI, parser, converter, GMD writer
rbxlx_parse.py   standalone parser: parse_rbxlx(file_path) -> list of part dicts
```

`rbxlx_parse.py` can be imported on its own if you only need the raw part data:

```python
from rbxlx_parse import parse_rbxlx

for part in parse_rbxlx("Place.rbxlx"):
    print(part["name"], part["x"], part["y"], part["z"])
```
