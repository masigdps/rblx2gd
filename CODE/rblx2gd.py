import math
import os
import re
import sys
import threading
import webbrowser
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import messagebox

from tkinterdnd2 import DND_FILES, TkinterDnD


GD_UNIT = 30
GRID = 15
GROUND_Y = 15
BASE_CY = 0
MAX_OBJECTS = 60000
MAX_PART_CELLS = 60000

BLOCK_ID = 1
SPIKE_ID = 8
CUBE_PORTAL_ID = 12
SHIP_PORTAL_ID = 13
ORB_ID = 36

BASEPLATE_NAMES = ("baseplate", "base plate", "floor", "terrain")
SPIKE_NAMES = ("spike", "saw", "blade", "trap", "barb")
PORTAL_NAMES = ("portal",)
ORB_NAMES = ("orb",)
FINISH_NAMES = ("goal", "finish", "end")
SPECIAL_IDS = (SPIKE_ID, CUBE_PORTAL_ID, SHIP_PORTAL_ID, ORB_ID)

ROT_EPS = 1e-4

MATERIAL_BLOCKS = {
    256: 1,
    272: 1,
    288: 1,
    512: 1,
    528: 12,
    784: 1,
    788: 1,
    800: 1,
    804: 8,
    816: 1,
    820: 1,
    832: 1,
    836: 1,
    848: 1,
    864: 1,
    880: 1,
    896: 1,
    912: 1,
    1040: 1,
    1056: 1,
    1072: 1,
    1088: 13,
    1280: 1,
    1284: 1,
    1296: 1,
    1312: 1,
    1328: 1,
    1344: 1,
    1360: 1,
    1376: 36,
    1392: 1,
    1536: 1,
    1552: 1,
    1568: 1,
    1584: 1,
    1792: 1,
    2048: 1,
    2304: 1,
    2305: 1,
    2306: 1,
    2307: 1,
    2308: 1,
    2309: 1,
    2310: 1,
    2311: 1,
}

STOP_FLAG = False


def _properties(item):
    node = item.find("Properties")
    if node is None:
        return {}
    return {child.get("name"): child for child in node if child.get("name")}


def _pick(properties, *names):
    for name in names:
        node = properties.get(name)
        if node is not None:
            return node
    return None


def _float(node, tag, default=0.0):
    raw = node.findtext(tag) if node is not None else None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _int(node):
    try:
        return int((node.text or "").strip())
    except (AttributeError, TypeError, ValueError):
        return None


def parse_rbxlx(file_path):
    root = ET.parse(file_path).getroot()
    parts = []
    rotated = 0

    for item in root.iter("Item"):
        if item.get("class") not in ("Part", "BasePart"):
            continue
        properties = _properties(item)
        cframe = properties.get("CFrame")
        size = _pick(properties, "size", "Size")
        if cframe is None or size is None:
            continue

        rot_tags = ("R00", "R01", "R02", "R10", "R11", "R12", "R20", "R21", "R22")
        if any(cframe.find(tag) is not None for tag in rot_tags):
            rot = {tag: _float(cframe, tag, 1.0 if tag in ("R00", "R11", "R22") else 0.0)
                   for tag in rot_tags}
            axis_aligned = (
                abs(rot["R00"] - 1.0) <= ROT_EPS and abs(rot["R11"] - 1.0) <= ROT_EPS
                and abs(rot["R22"] - 1.0) <= ROT_EPS
                and all(abs(rot[t]) <= ROT_EPS for t in ("R01", "R02", "R10", "R12", "R20", "R21"))
            )
            if not axis_aligned:
                rotated += 1
                continue

        name = properties.get("Name")
        shape_node = _pick(properties, "Shape", "shape")
        parts.append({
            "name": (name.text or "").strip() if name is not None else "",
            "x": _float(cframe, "X"),
            "y": _float(cframe, "Y"),
            "z": _float(cframe, "Z"),
            "sx": _float(size, "X", 4.0),
            "sy": _float(size, "Y", 1.0),
            "sz": _float(size, "Z", 2.0),
            "material": _int(properties.get("Material")),
            "shape": (_int(shape_node) or 1) if shape_node is not None else 1,
        })
    return parts, {"rotated": rotated}


def block_id(part, fast=False):
    if fast:
        return BLOCK_ID
    return MATERIAL_BLOCKS.get(part["material"], 0)


def is_baseplate(part):
    label = part["name"].lower()
    if any(keyword in label for keyword in BASEPLATE_NAMES):
        return True
    area = (part["sx"] / GD_UNIT) * (part["sz"] / GD_UNIT)
    return area >= 100 and part["sy"] <= GD_UNIT


def _xml_escape(text):
    text = str(text)
    for raw, repl in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"), ("'", "&apos;")):
        text = text.replace(raw, repl)
    return text


START_OBJECT = (
    "kS1,255,kS2,125,kS3,255,"
    "kS4,0,kS5,102,kS6,255,"
    "kS7,255,kS8,255,kS9,255,"
    "kS10,255,kS11,255,kS12,255,"
    "kS13,255,kS14,255,kS15,255,"
    "kS16,1,kS17,0,kS18,1,kS19,0,kS20,0,"
    "kA1,0,kA2,0,kA3,0,kA4,0,kA5,1,kA6,14,kA7,3,kA8,0,kA9,0,"
    "kA10,0,kA11,0,kA13,0,kA15,0,kA16,0,kA17,3,kA18,0,"
    "kA19,0,kA22,0,kA25,2,kA26,0,kA27,1,kA28,0,kA29,0,"
    "kA31,0,kA32,1,kA33,1,kA34,0,kA35,0,kA36,0,kA37,0,kA38,1,kA39,0,"
    "kA40,1,kA41,1,kA42,1,kA43,0,kA45,0,"
    "kS38,"
    "1_51_2_0_3_0_4_-1_11_255_12_255_13_255_6_1000_7_1_15_1_18_0_8_1|"
    "1_51_2_0_3_0_4_-1_11_255_12_255_13_255_6_1001_7_1_15_1_18_0_8_1|"
    "1_0_2_102_3_255_4_-1_11_255_12_255_13_255_6_1009_7_1_15_1_18_0_8_1|"
    "1_255_2_255_3_255_4_-1_11_255_12_255_13_255_6_1002_5_1_7_1_15_1_18_0_8_1|"
    "1_255_2_255_3_255_4_1_11_255_12_255_13_255_6_1_7_1_15_1_18_0_8_1|"
    "1_0_2_0_3_0_4_1_11_255_12_255_13_255_6_2_7_1_15_1_18_0_8_1|"
    "1_0_2_255_3_0_4_1_11_255_12_255_13_255_6_3_7_1_15_1_18_0_8_1|"
    "1_255_2_0_3_0_4_1_11_255_12_255_13_255_6_4_7_1_15_1_18_0_8_1|"
    "kS39,0"
)


def build_level(objects):
    return START_OBJECT + ";" + "".join(obj + ";" for obj in objects)


def _out_dir():
    return os.environ.get("RBLX2GD_OUT") or os.path.join(os.path.expanduser("~"), "Desktop")


def write_gmd(path, level_name, level_string):
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<plist version="1.0" gjver="2.0"><dict>'
        '<k>kCEK</k><i>4</i>'
        f'<k>k2</k><s>{_xml_escape(level_name)}</s>'
        f'<k>k4</k><s>{_xml_escape(level_string)}</s>'
        '<k>k13</k><t/><k>k21</k><i>2</i><k>k16</k><i>1</i>'
        '<k>k45</k><i>0</i><k>k80</k><i>16</i><k>k50</k><i>47</i><k>k47</k><t/>'
        f'<k>k48</k><i>{len(level_string)}</i>'
        '<k>kI2</k><r>0.0</r><k>kI3</k><r>1.0</r>'
        '</dict></plist>'
    )
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as handle:
        handle.write(xml)
    os.replace(tmp, path)


def _in_layers(part, z_layers):
    if z_layers is None:
        return True
    return any(part["z"] - part["sz"] / 2.0 <= z <= part["z"] + part["sz"] / 2.0 for z in z_layers)


def _cell_range(part, scale):
    cell = scale
    eps = 1e-6
    ranges = []
    for lo, hi in ((part["x"] - part["sx"] / 2.0, part["x"] + part["sx"] / 2.0),
                   (part["y"] - part["sy"] / 2.0, part["y"] + part["sy"] / 2.0)):
        width = hi - lo
        mid = (lo + hi) / 2.0
        if width <= cell * 1.01:
            start = end = int(round(mid / cell - 0.5))
        elif abs(width - round(width / cell) * cell) <= cell * 0.01:
            start = int(round(mid / cell - 0.5 - (round(width / cell) - 1) / 2.0))
            end = start + int(round(width / cell)) - 1
        else:
            start = int(math.floor(lo / cell + eps))
            end = int(math.ceil(hi / cell - eps)) - 1
            if end < start:
                start = end = int(math.floor(mid / cell))
        ranges.append((start, end))
    (cx0, cx1), (cy0, cy1) = ranges
    return cx0, cx1, cy0, cy1


def _one_part_one_block(parts, scale, z_layers, radius, x_center):
    cells = {}
    stats = {"filtered": 0, "big": 0}
    for part in parts:
        if STOP_FLAG:
            break
        if not _in_layers(part, z_layers):
            stats["filtered"] += 1
            continue
        if radius > 0 and abs(part["x"] - x_center) - part["sx"] / 2.0 > radius * scale:
            stats["filtered"] += 1
            continue
        gid = block_id(part)
        if gid == 0:
            continue
        cx = int(round((part["x"] - x_center) / scale - 0.5))
        cy = int(round(part["y"] / scale - 0.5))
        current = cells.get((cx, cy))
        if current is None or (current == BLOCK_ID and gid != BLOCK_ID):
            cells[(cx, cy)] = gid
        if len(cells) >= MAX_OBJECTS:
            break
    return cells, stats, False


def build_cells(parts, scale, z_layers, radius, x_center, fast, one_block=False):
    if one_block:
        return _one_part_one_block(parts, scale, z_layers, radius, x_center)
    cells = {}
    stats = {"filtered": 0, "big": 0}
    cap_hit = False

    for part in parts:
        if STOP_FLAG:
            break
        if not _in_layers(part, z_layers):
            stats["filtered"] += 1
            continue
        if radius > 0 and abs(part["x"] - x_center) - part["sx"] / 2.0 > radius * scale:
            stats["filtered"] += 1
            continue

        gid = block_id(part, fast)
        if gid == 0:
            continue

        if fast:
            cx0 = cx1 = int(round((part["x"] - x_center) / scale))
            cy0 = cy1 = int(round(part["y"] / GRID))
        else:
            cx0, cx1, cy0, cy1 = _cell_range(part, scale)
            cx0 -= int(round(x_center / scale))
            cx1 -= int(round(x_center / scale))

        if (cx1 - cx0 + 1) * (cy1 - cy0 + 1) > MAX_PART_CELLS:
            stats["big"] += 1
            continue

        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                current = cells.get((cx, cy))
                if current is None or (current == BLOCK_ID and gid != BLOCK_ID):
                    cells[(cx, cy)] = gid

        if len(cells) >= MAX_OBJECTS:
            cap_hit = True
            break

    return cells, stats, cap_hit


def cells_to_objects(cells):
    if not cells:
        return [], (0, 0, 0, 0)

    min_cx = min(k[0] for k in cells)
    max_cx = max(k[0] for k in cells)
    min_cy = min(k[1] for k in cells)
    max_cy = max(k[1] for k in cells)

    objects = []
    for (cx, cy) in sorted(cells):
        gid = cells[(cx, cy)]
        px = GRID + (cx - min_cx) * GRID
        py = GROUND_Y + (cy - min_cy) * GRID
        objects.append(f"1,{gid},2,{px},3,{py}")

    return objects, (max_cx - min_cx + 1, max_cy - min_cy + 1)


def cut_length(objects, max_len):
    if max_len <= 0 or not objects:
        return objects, 0
    max_x = max(int(float(o.split(",")[3])) for o in objects)
    if max_x <= max_len:
        return objects, 0
    kept = [o for o in objects if int(float(o.split(",")[3])) <= max_len]
    return kept, len(objects) - len(kept)


def run_conversion(path, z_val, scale, radius, fn, ln, baseplate=True, max_len=0, fast=False, one_block=False):
    global STOP_FLAG

    _log(f"loading: {path}")
    parts, stats_read = parse_rbxlx(path)
    _log(f"parts: {len(parts)}")
    if stats_read["rotated"]:
        _log(f"skipped {stats_read['rotated']} rotated part(s) (CFrame with angles)")
    if not parts:
        _log("no Part objects found")
        return
    if STOP_FLAG:
        _log("stopped")
        return

    xs = [p["x"] for p in parts]
    ys = [p["y"] for p in parts]
    zs = [p["z"] for p in parts]
    _log("mode: 1 part = 1 block" if one_block else ("mode: fast (one cell per part)" if fast else "mode: solid (filled parts)"))
    _log(f"x: {min(xs):.1f} .. {max(xs):.1f}")
    _log(f"y: {min(ys):.1f} .. {max(ys):.1f}")
    _log(f"z: {min(zs):.1f} .. {max(zs):.1f}")

    z_val = (z_val or "").strip()
    if z_val.lower() in ("", "all", "*", "auto"):
        z_layers = None
    else:
        try:
            z_layers = [float(v.replace(",", ".").strip()) for v in z_val.split(",")]
        except ValueError:
            _log("bad z value")
            return

    layer_parts = [p for p in parts if _in_layers(p, z_layers)] if z_layers is not None else parts
    if radius > 0:
        x_center = (min(p["x"] for p in layer_parts) + max(p["x"] for p in layer_parts)) / 2.0
    else:
        x_center = min((p["x"] - p["sx"] / 2.0 for p in layer_parts), default=0.0)

    if baseplate:
        floor_parts = [p for p in parts if is_baseplate(p)]
        if floor_parts:
            work = [p for p in parts if not is_baseplate(p)]
            _log(f"baseplate: ignoring {len(floor_parts)} floor part(s)")
        else:
            work = parts
    else:
        work = [p for p in parts if not is_baseplate(p)]
        if len(work) != len(parts):
            _log(f"baseplate: skipped {len(parts) - len(work)} part(s)")

    if z_layers is None:
        buckets = {}
        for p in work:
            key = int(round(p["z"] / 8.0)) * 8
            buckets[key] = buckets.get(key, 0) + 1
        if buckets:
            densest = max(buckets, key=lambda k: buckets[k])
            z_layers = [float(densest)]
            _log(f"z auto: {densest} ({buckets[densest]} parts)")

    cells, stats_build, cap_hit = build_cells(work, scale, z_layers, radius, x_center, fast, one_block)

    if stats_build["filtered"]:
        _log(f"z/radius filter: dropped {stats_build['filtered']} part(s)")

    if cap_hit:
        _log(f"object cap reached: {MAX_OBJECTS}")

    if not cells:
        _log("0 blocks found")
        return

    objects, (width, height) = cells_to_objects(cells)
    if not objects:
        _log("0 blocks produced")
        return

    objects, removed = cut_length(objects, max_len)
    if removed:
        _log(f"length limit: cut {removed} object(s)")
        if not objects:
            _log("length limit cut everything")
            return

    width = (max(int(float(o.split(',')[3])) for o in objects) - GRID) // GRID + 1
    _log(f"size: {width} x {height} cells, objects: {len(objects)}")

    level_string = build_level(objects)

    out_dir = _out_dir()
    if not os.path.isdir(out_dir):
        out_dir = os.path.expanduser("~")
    out = os.path.join(out_dir, f"{fn}.gmd")
    write_gmd(out, ln, level_string)
    if STOP_FLAG:
        _log("stopped: partial level")
    _log(f"done: {out}")


def _log(message):
    log_box.insert(tk.END, message + "\n")
    log_box.see(tk.END)


def convert_worker(*args):
    try:
        run_conversion(*args)
    except Exception as ex:
        import traceback
        _log(f"err: {ex}")
        _log(traceback.format_exc())
    finally:
        root.after(0, lambda: (btn_conv.config(state=tk.NORMAL), btn_stop.config(state=tk.DISABLED)))


def _first_scale(path):
    parts, _ = parse_rbxlx(path)
    sizes = [round(p["sx"], 3) for p in parts if not is_baseplate(p)]
    return min(sizes) if sizes else 1.0


def _first_layer(path):
    parts, _ = parse_rbxlx(path)
    scene = [p for p in parts if not is_baseplate(p)]
    if not scene:
        return "auto"
    counts = {}
    for p in scene:
        key = round(p["z"], 3)
        counts[key] = counts.get(key, 0) + 1
    return str(max(counts, key=lambda k: counts[k]))


def auto_scale():
    path = entry_path.get().strip()
    if not path or not os.path.isfile(path):
        messagebox.showerror("Err", "pick a .rbxlx file")
        return
    try:
        value = _first_scale(path)
    except Exception as ex:
        messagebox.showerror("Err", str(ex))
        return
    entry_scale.delete(0, tk.END)
    entry_scale.insert(0, f"{value:g}")


def auto_layer():
    path = entry_path.get().strip()
    if not path or not os.path.isfile(path):
        messagebox.showerror("Err", "pick a .rbxlx file")
        return
    try:
        value = _first_layer(path)
    except Exception as ex:
        messagebox.showerror("Err", str(ex))
        return
    entry_z.delete(0, tk.END)
    entry_z.insert(0, value)


def do_convert(e=None):
    global STOP_FLAG
    STOP_FLAG = False

    path = entry_path.get().strip()
    z_val = entry_z.get().strip()
    scale_val = entry_scale.get().strip()
    len_val = entry_len.get().strip()
    rad_val = entry_rad.get().strip()
    fn = entry_fn.get().strip()
    ln = entry_ln.get().strip()

    log_box.delete("1.0", tk.END)

    if not path or not os.path.isfile(path):
        messagebox.showerror("Err", "pick a .rbxlx file")
        return
    if not path.lower().endswith(".rbxlx"):
        messagebox.showerror("Err", "file must be .rbxlx (SV as XML, not .rbxl)")
        return
    if not fn:
        messagebox.showerror("Err", "filename empty")
        return
    if any(ch in fn for ch in '\\/:*?"<>|'):
        messagebox.showerror("Err", "bad filename")
        return
    if fn.lower().endswith(".gmd"):
        fn = fn[:-4]
    if not ln or len(ln) > 20 or not all(ch.isalnum() or ch == " " for ch in ln):
        messagebox.showerror("Err", "lvl name max 20 chars, letters/digits/spaces only")
        return

    try:
        scale = float(scale_val.replace(",", "."))
        radius = float(rad_val.replace(",", "."))
        max_len = int(float(len_val.replace(",", ".") or 0))
        if scale <= 0 or radius < 0 or max_len < 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("Err", "scale > 0, radius/length >= 0")
        return

    btn_conv.config(state=tk.DISABLED)
    btn_stop.config(state=tk.NORMAL)

    threading.Thread(
        target=convert_worker,
        args=(path, z_val, scale, radius, fn, ln, var_baseplate.get(), max_len, var_fast.get(), var_one_block.get()),
        daemon=True,
    ).start()


def stop_conv():
    global STOP_FLAG
    STOP_FLAG = True


def on_drop(event):
    raw = event.data.strip()
    candidates = [a or b for a, b in re.findall(r"\{([^}]*)\}|(\S+)", raw)]
    path = next((c for c in candidates if c.lower().endswith(".rbxlx")), "")
    if not path:
        path = raw.split("} {")[0].strip("{}").strip()
    if not path:
        return
    entry_path.delete(0, tk.END)
    entry_path.insert(0, path)
    if entry_fn.get().strip() in ("", "rblx2gdfile"):
        stem = os.path.splitext(os.path.basename(path))[0]
        stem = "".join(ch for ch in stem if ch.isalnum() or ch in " _-")[:30]
        if stem:
            entry_fn.delete(0, tk.END)
            entry_fn.insert(0, stem)


def link():
    webbrowser.open("https://masigdps.fun")


def main():
    global entry_path, entry_z, entry_scale, entry_len, entry_rad, entry_fn, entry_ln
    global log_box, btn_conv, btn_stop, var_baseplate, var_fast, var_one_block, root

    root = TkinterDnD.Tk()
    root.title("rblx2gd BY FGNGD")
    root.geometry("520x760")
    root.configure(bg="white")
    root.protocol("WM_DELETE_WINDOW", sys.exit)

    f1 = tk.Frame(root, bg="white")
    f1.pack(pady=15, padx=20, fill="both", expand=True)

    f2 = tk.Frame(f1, bg="white")
    f2.pack(fill="x", pady=5)

    tk.Label(f2, text="RBLX2GD", bg="white", fg="black", font=("Arial", 16, "bold")).pack(side=tk.LEFT)
    tk.Button(f2, text="🔗", command=link, bg="white", bd=0, font=("Arial", 14), cursor="hand2").pack(side=tk.RIGHT)

    entry_path = tk.Entry(f1, width=55, bg="white", fg="black", bd=1, relief="solid")
    entry_path.insert(0, "Drag .rbxlx file...")
    entry_path.bind("<FocusIn>", lambda e: entry_path.delete(0, tk.END) if entry_path.get() == "Drag .rbxlx file..." else None)
    entry_path.pack(fill="x", pady=10)

    root.drop_target_register(DND_FILES)
    root.dnd_bind("<<Drop>>", on_drop)

    f3 = tk.Frame(f1, bg="white")
    f3.pack(fill="x", pady=5)

    def field(row, label, default, width=24):
        tk.Label(f3, text=label, bg="white", fg="black").grid(row=row, column=0, sticky="w", pady=3)
        entry = tk.Entry(f3, width=width, bg="white", fg="black", bd=1, relief="solid")
        entry.insert(0, default)
        entry.grid(row=row, column=1, pady=3, padx=5)
        return entry

    entry_z = field(0, "Z Layers (all/auto):", "auto")
    entry_rad = field(1, "Radius (0 = all):", "0", 10)
    entry_scale = field(2, "Scale (studs/block):", "1", 10)
    entry_len = field(3, "Length in blocks (0 = all):", "0", 10)
    entry_fn = field(4, "File Name:", "rblx2gdfile")
    entry_ln = field(5, "Level Name:", "rblx2gd level")

    tk.Label(f3, text="Baseplate:", bg="white", fg="black").grid(row=6, column=0, sticky="w", pady=3)
    var_baseplate = tk.BooleanVar(value=True)
    tk.Checkbutton(f3, text="skip floor / baseplate", variable=var_baseplate, bg="white", fg="black",
                   activebackground="white", activeforeground="black", selectcolor="white",
                   bd=0, highlightthickness=0).grid(row=6, column=1, sticky="w", padx=5)

    var_fast = tk.BooleanVar(value=False)
    tk.Checkbutton(f3, text="fast (single-cell objects)", variable=var_fast, bg="white", fg="black",
                   activebackground="white", activeforeground="black", selectcolor="white",
                   bd=0, highlightthickness=0).grid(row=7, column=1, sticky="w", padx=5)

    var_one_block = tk.BooleanVar(value=False)
    tk.Checkbutton(f3, text="1 part = 1 block", variable=var_one_block, bg="white", fg="black",
                   activebackground="white", activeforeground="black", selectcolor="white",
                   bd=0, highlightthickness=0).grid(row=8, column=1, sticky="w", padx=5)

    f4 = tk.Frame(f1, bg="white")
    f4.pack(pady=10)

    btn_conv = tk.Button(f4, text="CONVERT", command=do_convert, bg="#e0e0e0", fg="black",
                         font=("Arial", 12), bd=1, relief="raised", width=15)
    btn_conv.pack(side=tk.LEFT, padx=5)

    btn_stop = tk.Button(f4, text="STOP", command=stop_conv, bg="#ffcccc", fg="black",
                         font=("Arial", 12), bd=1, relief="raised", width=10, state=tk.DISABLED)
    btn_stop.pack(side=tk.LEFT, padx=5)

    tk.Label(f1, text="Console", bg="white", fg="black", font=("Arial", 10, "bold"), anchor="w").pack(fill="x")

    log_box = tk.Text(f1, height=12, bg="white", fg="black", font=("Consolas", 9), bd=1, relief="solid")
    log_box.pack(fill="both", expand=True, pady=5)

    root.mainloop()


if __name__ == "__main__":
    main()
