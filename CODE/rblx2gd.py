import math
import os
import re
import sys
import threading
import traceback
import webbrowser
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import messagebox

from tkinterdnd2 import DND_FILES, TkinterDnD


BLOCK = 1
SPIKE = 8
CUBE_PORTAL = 12
SHIP_PORTAL = 13
ORB = 36

GRID = 15
GROUND_Y = 15
GD_UNIT = 30
MAX_OBJECTS = 60000
MAX_PART_CELLS = 60000
ROT_EPS = 1e-4
EPS = 1e-6

ROTATION_TAGS = ["R00", "R01", "R02", "R10", "R11", "R12", "R20", "R21", "R22"]
IDENTITY_TAGS = ["R00", "R11", "R22"]
BASEPLATE_NAMES = ["baseplate", "base plate", "floor", "terrain"]

MATERIAL_MAP = {
    256: BLOCK,
    272: BLOCK,
    288: BLOCK,
    512: BLOCK,
    528: CUBE_PORTAL,
    784: BLOCK,
    788: BLOCK,
    800: BLOCK,
    804: SPIKE,
    816: BLOCK,
    820: BLOCK,
    832: BLOCK,
    836: BLOCK,
    848: BLOCK,
    864: BLOCK,
    880: BLOCK,
    896: BLOCK,
    912: BLOCK,
    1040: BLOCK,
    1056: BLOCK,
    1072: BLOCK,
    1088: SHIP_PORTAL,
    1280: BLOCK,
    1284: BLOCK,
    1296: BLOCK,
    1312: BLOCK,
    1328: BLOCK,
    1344: BLOCK,
    1360: BLOCK,
    1376: ORB,
    1392: BLOCK,
    1536: BLOCK,
    1552: BLOCK,
    1568: BLOCK,
    1584: BLOCK,
    1792: BLOCK,
    2048: BLOCK,
    2304: BLOCK,
    2305: BLOCK,
    2306: BLOCK,
    2307: BLOCK,
    2308: BLOCK,
    2309: BLOCK,
    2310: BLOCK,
    2311: BLOCK,
}

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

STOP_FLAG = False


class Settings:
    def __init__(self):
        self.z = "auto"
        self.scale = 1.0
        self.radius = 0.0
        self.max_len = 0
        self.baseplate = True
        self.fast = False
        self.one_block = False
        self.file_name = "rblx2gdfile"
        self.level_name = "rblx2gd level"


def read_properties(item):
    node = item.find("Properties")
    if node is None:
        return {}

    result = {}
    for child in node:
        name = child.get("name")
        if name is not None:
            result[name] = child
    return result


def read_text(node):
    if node is None:
        return ""
    if node.text is None:
        return ""
    return node.text.strip()


def read_float(node, tag, default):
    if node is None:
        return default

    text = node.findtext(tag)
    if text is None:
        return default

    try:
        return float(text)
    except ValueError:
        return default


def read_int(node):
    if node is None:
        return None

    text = node.text
    if text is None:
        return None

    try:
        return int(text.strip())
    except ValueError:
        return None


def is_rotated(frame):
    for tag in ROTATION_TAGS:
        if frame.find(tag) is None:
            continue

        wanted = 0.0
        for identity_tag in IDENTITY_TAGS:
            if tag == identity_tag:
                wanted = 1.0

        value = read_float(frame, tag, wanted)
        if abs(value - wanted) > ROT_EPS:
            return True

    return False


def parse_parts(path):
    root = ET.parse(path).getroot()
    parts = []
    rotated = 0

    for item in root.iter("Item"):
        part_class = item.get("class")
        if part_class != "Part" and part_class != "BasePart":
            continue

        properties = read_properties(item)
        frame = properties.get("CFrame")

        size = properties.get("size")
        if size is None:
            size = properties.get("Size")

        if frame is None or size is None:
            continue

        if is_rotated(frame):
            rotated = rotated + 1
            continue

        part = {}
        part["name"] = read_text(properties.get("Name"))
        part["x"] = read_float(frame, "X", 0.0)
        part["y"] = read_float(frame, "Y", 0.0)
        part["z"] = read_float(frame, "Z", 0.0)
        part["sx"] = read_float(size, "X", 4.0)
        part["sy"] = read_float(size, "Y", 1.0)
        part["sz"] = read_float(size, "Z", 2.0)
        part["material"] = read_int(properties.get("Material"))
        parts.append(part)

    return parts, rotated


def object_id(part):
    material = part["material"]
    if material in MATERIAL_MAP:
        return MATERIAL_MAP[material]
    return 0


def is_baseplate(part):
    label = part["name"].lower()
    for name in BASEPLATE_NAMES:
        if name in label:
            return True

    area = (part["sx"] / GD_UNIT) * (part["sz"] / GD_UNIT)
    if area >= 100 and part["sy"] <= GD_UNIT:
        return True

    return False


def in_layer(part, z_layers):
    if z_layers is None:
        return True

    low = part["z"] - part["sz"] / 2.0
    high = part["z"] + part["sz"] / 2.0

    for z in z_layers:
        if low <= z and z <= high:
            return True

    return False


def span(low, high, cell):
    width = high - low
    middle = (low + high) / 2.0

    if width <= cell * 1.01:
        index = int(round(middle / cell - 0.5))
        return index, index

    steps = round(width / cell)
    if abs(width - steps * cell) <= cell * 0.01:
        steps = int(steps)
        start = int(round(middle / cell - 0.5 - (steps - 1) / 2.0))
        end = start + steps - 1
        return start, end

    start = int(math.floor(low / cell + EPS))
    end = int(math.ceil(high / cell - EPS)) - 1

    if end < start:
        start = int(math.floor(middle / cell))
        end = start

    return start, end


def part_span(part, cell):
    left = part["x"] - part["sx"] / 2.0
    right = part["x"] + part["sx"] / 2.0
    bottom = part["y"] - part["sy"] / 2.0
    top = part["y"] + part["sy"] / 2.0

    x0, x1 = span(left, right, cell)
    y0, y1 = span(bottom, top, cell)

    return x0, x1, y0, y1


def cell_box(part, settings, center, shift):
    if settings.one_block:
        cx = int(round((part["x"] - center) / settings.scale - 0.5))
        cy = int(round(part["y"] / settings.scale - 0.5))
        return cx, cx, cy, cy

    if settings.fast:
        cx = int(round((part["x"] - center) / settings.scale))
        cy = int(round(part["y"] / GRID))
        return cx, cx, cy, cy

    x0, x1, y0, y1 = part_span(part, settings.scale)
    x0 = x0 - shift
    x1 = x1 - shift

    return x0, x1, y0, y1


def rasterize(parts, settings, center, z_layers):
    cells = {}
    skipped = 0
    capped = False
    shift = int(round(center / settings.scale))

    for part in parts:
        if STOP_FLAG:
            break

        if not in_layer(part, z_layers):
            skipped = skipped + 1
            continue

        if settings.radius > 0:
            distance = abs(part["x"] - center) - part["sx"] / 2.0
            if distance > settings.radius * settings.scale:
                skipped = skipped + 1
                continue

        gid = object_id(part)
        if settings.fast and not settings.one_block:
            gid = BLOCK

        if gid == 0:
            continue

        x0, x1, y0, y1 = cell_box(part, settings, center, shift)

        width = x1 - x0 + 1
        height = y1 - y0 + 1
        if width * height > MAX_PART_CELLS:
            continue

        for cx in range(x0, x1 + 1):
            for cy in range(y0, y1 + 1):
                current = cells.get((cx, cy))
                if current is None:
                    cells[(cx, cy)] = gid
                elif current == BLOCK and gid != BLOCK:
                    cells[(cx, cy)] = gid

        if len(cells) >= MAX_OBJECTS:
            if not settings.one_block:
                capped = True
            break

    return cells, skipped, capped


def object_x(text):
    fields = text.split(",")
    return int(fields[3])


def objects_from(cells, max_len):
    if len(cells) == 0:
        return [], 0, 0, 0

    keys = list(cells.keys())
    min_x = keys[0][0]
    max_x = keys[0][0]
    min_y = keys[0][1]
    max_y = keys[0][1]

    for cell in keys:
        cx = cell[0]
        cy = cell[1]

        if cx < min_x:
            min_x = cx
        if cx > max_x:
            max_x = cx
        if cy < min_y:
            min_y = cy
        if cy > max_y:
            max_y = cy

    keys.sort()
    objects = []

    for cell in keys:
        cx = cell[0]
        cy = cell[1]
        gid = cells[cell]

        px = GRID + (cx - min_x) * GRID
        py = GROUND_Y + (cy - min_y) * GRID
        objects.append(f"1,{gid},2,{px},3,{py}")

    removed = 0
    if max_len > 0:
        need_cut = False
        for obj in objects:
            if object_x(obj) > max_len:
                need_cut = True
                break

        if need_cut:
            kept = []
            for obj in objects:
                if object_x(obj) <= max_len:
                    kept.append(obj)
                else:
                    removed = removed + 1
            objects = kept

    width = 0
    if len(objects) > 0:
        widest = 0
        for obj in objects:
            x = object_x(obj)
            if x > widest:
                widest = x
        width = (widest - GRID) // GRID + 1

    height = max_y - min_y + 1

    return objects, removed, width, height


def parse_layers(text):
    text = text.strip()
    lowered = text.lower()

    if text == "" or lowered == "all" or lowered == "*" or lowered == "auto":
        return None

    layers = []
    for piece in text.split(","):
        piece = piece.strip()
        piece = piece.replace(",", ".")
        layers.append(float(piece))

    return layers


def escape(value):
    value = value.replace("&", "&amp;")
    value = value.replace("<", "&lt;")
    value = value.replace(">", "&gt;")
    value = value.replace('"', "&quot;")
    value = value.replace("'", "&apos;")
    return value


def write_gmd(path, level_name, level_string):
    name = escape(level_name)
    level = escape(level_string)
    size = len(level_string)

    xml = '<?xml version="1.0" encoding="UTF-8"?>'
    xml = xml + '<plist version="1.0" gjver="2.0"><dict>'
    xml = xml + '<k>kCEK</k><i>4</i>'
    xml = xml + '<k>k2</k><s>' + name + '</s>'
    xml = xml + '<k>k4</k><s>' + level + '</s>'
    xml = xml + '<k>k13</k><t/><k>k21</k><i>2</i><k>k16</k><i>1</i>'
    xml = xml + '<k>k45</k><i>0</i><k>k80</k><i>16</i><k>k50</k><i>47</i><k>k47</k><t/>'
    xml = xml + '<k>k48</k><i>' + str(size) + '</i>'
    xml = xml + '<k>kI2</k><r>0.0</r><k>kI3</k><r>1.0</r>'
    xml = xml + '</dict></plist>'

    temp_path = path + ".tmp"
    handle = open(temp_path, "w", encoding="utf-8", newline="")
    try:
        handle.write(xml)
    finally:
        handle.close()

    os.replace(temp_path, path)


def convert(path, settings, log=print):
    log("loading: " + path)

    parts, rotated = parse_parts(path)
    log("parts: " + str(len(parts)))

    if rotated > 0:
        log("skipped " + str(rotated) + " rotated part(s) (CFrame with angles)")

    if len(parts) == 0:
        log("no Part objects found")
        return

    if STOP_FLAG:
        log("stopped")
        return

    if settings.one_block:
        log("mode: 1 part = 1 block")
    elif settings.fast:
        log("mode: fast (one cell per part)")
    else:
        log("mode: solid (filled parts)")

    xs = []
    ys = []
    zs = []
    for part in parts:
        xs.append(part["x"])
        ys.append(part["y"])
        zs.append(part["z"])

    log(f"x: {min(xs):.1f} .. {max(xs):.1f}")
    log(f"y: {min(ys):.1f} .. {max(ys):.1f}")
    log(f"z: {min(zs):.1f} .. {max(zs):.1f}")

    try:
        z_layers = parse_layers(settings.z)
    except ValueError:
        log("bad z value")
        return

    if z_layers is None:
        layer_parts = parts
    else:
        layer_parts = []
        for part in parts:
            if in_layer(part, z_layers):
                layer_parts.append(part)

    if settings.radius > 0:
        xs = []
        for part in layer_parts:
            xs.append(part["x"])
        center = (min(xs) + max(xs)) / 2.0
    else:
        edges = []
        for part in layer_parts:
            edges.append(part["x"] - part["sx"] / 2.0)

        if len(edges) == 0:
            center = 0.0
        else:
            center = min(edges)

    floors = []
    work = []
    for part in parts:
        if is_baseplate(part):
            floors.append(part)
        else:
            work.append(part)

    if settings.baseplate:
        if len(floors) > 0:
            log(f"baseplate: ignoring {len(floors)} floor part(s)")
        else:
            work = parts
    else:
        if len(floors) > 0:
            log(f"baseplate: skipped {len(floors)} part(s)")

    if z_layers is None:
        buckets = {}
        for part in work:
            key = int(round(part["z"] / 8.0)) * 8
            if key in buckets:
                buckets[key] = buckets[key] + 1
            else:
                buckets[key] = 1

        if len(buckets) > 0:
            best = None
            best_count = -1
            for key in buckets:
                if buckets[key] > best_count:
                    best_count = buckets[key]
                    best = key

            z_layers = [float(best)]
            log(f"z auto: {best} ({best_count} parts)")

    cells, skipped, capped = rasterize(work, settings, center, z_layers)

    if skipped > 0:
        log(f"z/radius filter: dropped {skipped} part(s)")

    if capped:
        log(f"object cap reached: {MAX_OBJECTS}")

    if len(cells) == 0:
        log("0 blocks found")
        return

    objects, removed, width, height = objects_from(cells, settings.max_len)

    if removed > 0:
        log(f"length limit: cut {removed} object(s)")

    if len(objects) == 0:
        log("length limit cut everything")
        return

    log(f"size: {width} x {height} cells, objects: {len(objects)}")

    pieces = []
    for obj in objects:
        pieces.append(obj)
        pieces.append(";")
    level_string = START_OBJECT + ";" + "".join(pieces)

    out_dir = os.environ.get("RBLX2GD_OUT")
    if out_dir is None or out_dir == "":
        out_dir = os.path.join(os.path.expanduser("~"), "Desktop")

    if not os.path.isdir(out_dir):
        out_dir = os.path.expanduser("~")

    out = os.path.join(out_dir, settings.file_name + ".gmd")
    write_gmd(out, settings.level_name, level_string)

    if STOP_FLAG:
        log("stopped: partial level")

    log("done: " + out)


class App:
    def __init__(self, root):
        self.root = root
        root.title("rblx2gd BY FGNGD")
        root.geometry("520x760")
        root.configure(bg="white")
        root.protocol("WM_DELETE_WINDOW", sys.exit)

        outer = tk.Frame(root, bg="white")
        outer.pack(pady=15, padx=20, fill="both", expand=True)

        header = tk.Frame(outer, bg="white")
        header.pack(fill="x", pady=5)

        title = tk.Label(header, text="RBLX2GD", bg="white", fg="black", font=("Arial", 16, "bold"))
        title.pack(side=tk.LEFT)

        link_button = tk.Button(header, text="🔗", command=open_site, bg="white", bd=0,
                                font=("Arial", 14), cursor="hand2")
        link_button.pack(side=tk.RIGHT)

        self.path_entry = tk.Entry(outer, width=55, bg="white", fg="black", bd=1, relief="solid")
        self.path_entry.insert(0, "Drag .rbxlx file...")
        self.path_entry.bind("<FocusIn>", self.clear_placeholder)
        self.path_entry.pack(fill="x", pady=10)

        root.drop_target_register(DND_FILES)
        root.dnd_bind("<<Drop>>", self.on_drop)

        fields = tk.Frame(outer, bg="white")
        fields.pack(fill="x", pady=5)

        self.z_entry = self.add_field(fields, 0, "Z Layers (all/auto):", "auto", 24)
        self.rad_entry = self.add_field(fields, 1, "Radius (0 = all):", "0", 10)
        self.scale_entry = self.add_field(fields, 2, "Scale (studs/block):", "1", 10)
        self.len_entry = self.add_field(fields, 3, "Length in blocks (0 = all):", "0", 10)
        self.fn_entry = self.add_field(fields, 4, "File Name:", "rblx2gdfile", 24)
        self.ln_entry = self.add_field(fields, 5, "Level Name:", "rblx2gd level", 24)

        label = tk.Label(fields, text="Baseplate:", bg="white", fg="black")
        label.grid(row=6, column=0, sticky="w", pady=3)

        self.var_baseplate = tk.BooleanVar(value=True)
        self.var_fast = tk.BooleanVar(value=False)
        self.var_one_block = tk.BooleanVar(value=False)

        self.add_check(fields, 6, "skip floor / baseplate", self.var_baseplate)
        self.add_check(fields, 7, "fast (single-cell objects)", self.var_fast)
        self.add_check(fields, 8, "1 part = 1 block", self.var_one_block)

        buttons = tk.Frame(outer, bg="white")
        buttons.pack(pady=10)

        self.btn_convert = tk.Button(buttons, text="CONVERT", command=self.start, bg="#e0e0e0",
                                     fg="black", font=("Arial", 12), bd=1, relief="raised", width=15)
        self.btn_convert.pack(side=tk.LEFT, padx=5)

        self.btn_stop = tk.Button(buttons, text="STOP", command=self.stop, bg="#ffcccc", fg="black",
                                  font=("Arial", 12), bd=1, relief="raised", width=10, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        console_label = tk.Label(outer, text="Console", bg="white", fg="black",
                                 font=("Arial", 10, "bold"), anchor="w")
        console_label.pack(fill="x")

        self.console = tk.Text(outer, height=12, bg="white", fg="black",
                               font=("Consolas", 9), bd=1, relief="solid")
        self.console.pack(fill="both", expand=True, pady=5)

    def add_field(self, parent, row, label_text, default, width):
        label = tk.Label(parent, text=label_text, bg="white", fg="black")
        label.grid(row=row, column=0, sticky="w", pady=3)

        entry = tk.Entry(parent, width=width, bg="white", fg="black", bd=1, relief="solid")
        entry.insert(0, default)
        entry.grid(row=row, column=1, pady=3, padx=5)

        return entry

    def add_check(self, parent, row, label_text, variable):
        check = tk.Checkbutton(parent, text=label_text, variable=variable, bg="white", fg="black",
                               activebackground="white", activeforeground="black", selectcolor="white",
                               bd=0, highlightthickness=0)
        check.grid(row=row, column=1, sticky="w", padx=5)

    def log(self, message):
        self.console.insert(tk.END, message + "\n")
        self.console.see(tk.END)

    def clear_placeholder(self, event=None):
        current = self.path_entry.get()
        if current == "Drag .rbxlx file...":
            self.path_entry.delete(0, tk.END)

    def start(self, event=None):
        global STOP_FLAG
        STOP_FLAG = False

        self.console.delete("1.0", tk.END)

        path = self.path_entry.get().strip()
        filename = self.fn_entry.get().strip()
        level_name = self.ln_entry.get().strip()

        if path == "" or not os.path.isfile(path):
            messagebox.showerror("Err", "pick a .rbxlx file")
            return

        if not path.lower().endswith(".rbxlx"):
            messagebox.showerror("Err", "file must be .rbxlx (SV as XML, not .rbxl)")
            return

        if filename == "":
            messagebox.showerror("Err", "filename empty")
            return

        for symbol in '\\/:*?"<>|':
            if symbol in filename:
                messagebox.showerror("Err", "bad filename")
                return

        if filename.lower().endswith(".gmd"):
            filename = filename[:-4]

        if level_name == "" or len(level_name) > 20:
            messagebox.showerror("Err", "lvl name max 20 chars, letters/digits/spaces only")
            return

        for symbol in level_name:
            if not symbol.isalnum() and symbol != " ":
                messagebox.showerror("Err", "lvl name max 20 chars, letters/digits/spaces only")
                return

        try:
            scale = float(self.scale_entry.get().strip().replace(",", "."))
            radius = float(self.rad_entry.get().strip().replace(",", "."))

            length_text = self.len_entry.get().strip().replace(",", ".")
            if length_text == "":
                length_text = "0"
            max_len = int(float(length_text))
        except ValueError:
            messagebox.showerror("Err", "scale > 0, radius/length >= 0")
            return

        if scale <= 0 or radius < 0 or max_len < 0:
            messagebox.showerror("Err", "scale > 0, radius/length >= 0")
            return

        settings = Settings()
        settings.z = self.z_entry.get().strip()
        settings.scale = scale
        settings.radius = radius
        settings.max_len = max_len
        settings.baseplate = self.var_baseplate.get()
        settings.fast = self.var_fast.get()
        settings.one_block = self.var_one_block.get()
        settings.file_name = filename
        settings.level_name = level_name

        self.btn_convert.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)

        thread = threading.Thread(target=self.worker, args=(path, settings))
        thread.daemon = True
        thread.start()

    def worker(self, path, settings):
        try:
            convert(path, settings, self.log)
        except Exception as error:
            self.log("err: " + str(error))
            self.log(traceback.format_exc())
        finally:
            self.root.after(0, self.done)

    def done(self):
        self.btn_convert.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

    def stop(self):
        global STOP_FLAG
        STOP_FLAG = True

    def on_drop(self, event):
        raw = event.data.strip()

        found = []
        for piece in re.findall(r"\{([^}]*)\}|(\S+)", raw):
            first = piece[0]
            second = piece[1]
            if first != "":
                found.append(first)
            else:
                found.append(second)

        path = ""
        for candidate in found:
            if candidate.lower().endswith(".rbxlx"):
                path = candidate
                break

        if path == "":
            path = raw.split("} {")[0].strip("{}").strip()

        if path == "":
            return

        self.path_entry.delete(0, tk.END)
        self.path_entry.insert(0, path)

        if self.fn_entry.get().strip() == "" or self.fn_entry.get().strip() == "rblx2gdfile":
            base_name = os.path.splitext(os.path.basename(path))[0]

            cleaned = ""
            for symbol in base_name:
                if symbol.isalnum() or symbol in " _-":
                    cleaned = cleaned + symbol

            cleaned = cleaned[:30]
            if cleaned != "":
                self.fn_entry.delete(0, tk.END)
                self.fn_entry.insert(0, cleaned)


def open_site():
    webbrowser.open("https://masigdps.fun")


def main():
    root = TkinterDnD.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
