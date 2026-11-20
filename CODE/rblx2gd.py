import math
import os
import sys
import threading
import webbrowser
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import messagebox

from tkinterdnd2 import DND_FILES, TkinterDnD

GD_UNIT = 30
OFFSET_X = 300
OFFSET_Y = 15
MAX_OBJECTS = 60000
MAX_PART_CELLS = 60000
BLOCK_ID = 1
SPIKE_ID = 8
PORTAL_ID = 13
ORB_ID = 36
BASEPLATE_NAMES = ("baseplate", "base plate", "floor", "ground")

MATERIAL_BLOCKS = {
    256: 1,
    272: 1,
    288: 1,
    512: 13,
    528: 36,
    784: 1,
    788: 1,
    800: 1,
    804: 8,
    816: 1,
    832: 1,
    848: 1,
    864: 1,
    880: 1,
    896: 1,
    1040: 1,
    1056: 12,
    1072: 1,
    1088: 13,
    1280: 1,
    1296: 1,
    1312: 1,
    1328: 1,
    1344: 1,
    1360: 1,
    1376: 1,
    1536: 1,
    1552: 1,
    1568: 1,
    1792: 1,
    2048: 1,
}

SPIKE_NAMES = ("spike", "saw", "blade", "trap", "barb")
PORTAL_NAMES = ("portal",)
ORB_NAMES = ("orb",)
SPECIAL_IDS = (SPIKE_ID, PORTAL_ID, ORB_ID)

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
    for item in root.iter("Item"):
        if item.get("class") != "Part":
            continue
        properties = _properties(item)
        cframe = properties.get("CFrame")
        size = _pick(properties, "size", "Size")
        if cframe is None or size is None:
            continue
        name = properties.get("Name")
        parts.append({
            "name": (name.text or "").strip() if name is not None else "",
            "x": _float(cframe, "X"),
            "y": _float(cframe, "Y"),
            "z": _float(cframe, "Z"),
            "sx": _float(size, "X"),
            "sy": _float(size, "Y"),
            "sz": _float(size, "Z"),
            "material": _int(properties.get("Material")),
        })
    return parts


def block_id(part):
    label = part["name"].lower()
    if any(keyword in label for keyword in SPIKE_NAMES):
        return SPIKE_ID
    if any(keyword in label for keyword in PORTAL_NAMES):
        return PORTAL_ID
    if any(keyword in label for keyword in ORB_NAMES):
        return ORB_ID
    return MATERIAL_BLOCKS.get(part["material"], 0)


def write_gmd(path, level_name, level_data):
    xml = f'''<?xml version="1.0"?><plist version="1.0" gjver="2.0"><dict><k>kCEK</k><i>4</i><k>k2</k><s>{level_name}</s><k>k4</k><s>{level_data}</s><k>k5</k><s>FGNgd</s><k>k101</k><s>0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0</s><k>k13</k><t/><k>k21</k><i>2</i><k>k16</k><i>1</i><k>k80</k><i>16</i><k>k50</k><i>47</i><k>k47</k><t/><k>k48</k><i>24</i><k>kI1</k><r>88.6167</r><k>kI2</k><r>116.756</r><k>kI3</k><r>0.7</r><k>kI5</k><i>3</i><k>kI6</k><d><k>0</k><s>0</s><k>1</k><s>0</s><k>2</k><s>0</s><k>3</k><s>0</s><k>4</k><s>0</s><k>5</k><s>0</s><k>6</k><s>0</s><k>7</k><s>0</s><k>8</k><s>0</s><k>9</k><s>0</s><k>10</k><s>0</s><k>11</k><s>0</s><k>12</k><s>0</s><k>13</k><s>0</s></d></dict></plist>'''
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(xml)


def _log(message):
    log_box.insert(tk.END, message + "\n")
    log_box.see(tk.END)


def is_baseplate(part):
    label = part["name"].lower()
    if any(keyword in label for keyword in BASEPLATE_NAMES):
        return True
    area = (part["sx"] / GD_UNIT) * (part["sz"] / GD_UNIT)
    return area >= 100 and part["sy"] <= GD_UNIT


def run_conversion(path, z_list, scale, radius, fn, ln, baseplate=True, max_len=0, fast=False):
    global STOP_FLAG

    _log(f"loading: {path}")
    parts = parse_rbxlx(path)
    _log(f"parts: {len(parts)}")
    if not parts:
        _log("no Part objects found")
        return
    if STOP_FLAG:
        _log("stopped")
        return

    xs = [p["x"] for p in parts]
    ys = [p["y"] for p in parts]
    zs = [p["z"] for p in parts]
    fill_area = 4 if fast else 1
    MODE_OBJECT_LIMIT = 20000 if fast else MAX_OBJECTS
    _log("mode: fast (one cell per part)" if fast else "mode: solid (filled parts)")
    _log(f"x: {min(xs):.1f} .. {max(xs):.1f}")
    _log(f"y: {min(ys):.1f} .. {max(ys):.1f}")
    _log(f"z: {min(zs):.1f} .. {max(zs):.1f}")

    selected = parts
    if z_list is not None:
        selected = [
            p for p in parts
            if any(p["z"] - p["sz"] / 2.0 <= z <= p["z"] + p["sz"] / 2.0 for z in z_list)
        ]
        _log(f"z filter: {len(selected)} / {len(parts)}")
        if not selected:
            _log("nothing on these z layers")
            return

    if radius > 0:
        limit = radius * scale
        before = len(selected)
        selected = [p for p in selected if abs(p["x"]) - p["sx"] / 2.0 <= limit]
        _log(f"radius filter: {len(selected)} / {before} (|x| <= {limit:g})")
        if not selected:
            _log("nothing inside radius")
            return

    cells = {}
    big_parts = 0
    skipped_baseplates = 0
    cap_hit = False

    for index, part in enumerate(selected, 1):
        if STOP_FLAG:
            break
        if index % 500 == 0:
            _log(f"scanned: {index} / {len(selected)}, blocks: {len(cells)}")

        if not baseplate and is_baseplate(part):
            skipped_baseplates += 1
            continue

        if fast and part["sx"] * part["sz"] > (scale * 6) ** 2 and part["sy"] <= scale * 3:
            skipped_baseplates += 1
            continue

        gid = block_id(part)
        if gid == 0:
            continue
        current_id = gid
        x0 = math.floor((part["x"] - part["sx"] / 2.0) / scale + 0.5)
        x1 = math.floor((part["x"] + part["sx"] / 2.0) / scale + 0.5)
        y0 = math.floor((part["y"] - part["sy"] / 2.0) / scale + 0.5)
        y1 = math.floor((part["y"] + part["sy"] / 2.0) / scale + 0.5)
        if x1 <= x0:
            x1 = x0 + 1
        if y1 <= y0:
            y1 = y0 + 1

        area = (x1 - x0) * (y1 - y0)
        if not fast and area > MAX_PART_CELLS:
            big_parts += 1
            _log(f"skip big part: {part['name']} ({area} blocks)")
            continue

        if fast:
            w = x1 - x0
            h = y1 - y0
            k = 1 if current_id in SPECIAL_IDS else 2
            x0 = x0 + max(0, (w - k) // 2)
            y0 = y0 + max(0, (h - k) // 2)
            x1 = x0 + min(k, w)
            y1 = y0 + min(k, h)

        for cx in range(x0, x1):
            for cy in range(y0, y1):
                current = cells.get((cx, cy))
                if current is None or (current == BLOCK_ID and gid != BLOCK_ID):
                    cells[(cx, cy)] = gid

        if len(cells) >= MODE_OBJECT_LIMIT:
            cap_hit = True
            break

    _log(f"blocks: {len(cells)} (limit {MODE_OBJECT_LIMIT})")
    if not baseplate:
        _log(f"baseplate: off (skipped {skipped_baseplates})")
    if big_parts:
        _log(f"skipped big parts: {big_parts}")
    if cap_hit:
        _log(f"object cap reached: {MODE_OBJECT_LIMIT}")
    if not cells:
        _log("0 blocks found")
        return
    if STOP_FLAG:
        _log("stopped: partial level")

    min_cx = min(key[0] for key in cells)
    min_cy = min(key[1] for key in cells)
    max_cx = max(key[0] for key in cells)
    width = max_cx - min_cx + 1

    length_cut = 0
    if max_len > 0 and width > max_len:
        cut_cx = min_cx + max_len
        removed = sum(1 for key in cells if key[0] >= cut_cx)
        cells = {key: gid for key, gid in cells.items() if key[0] < cut_cx}
        length_cut = removed
        if not cells:
            _log("length limit cut everything")
            return
        removed_cols = width - max_len
        _log(f"length limit: {max_len} blocks (cut {removed} blocks, {removed_cols} columns)")

    objects = []
    for (cx, cy), gid in sorted(cells.items()):
        px = (cx - min_cx) * GD_UNIT + OFFSET_X
        py = (cy - min_cy) * GD_UNIT + OFFSET_Y
        objects.append(f"1,{gid},2,{px},3,{py}")

    level = "kS1,0," + ";".join(objects) + ";"
    _log(f"width: {min(width, max_len) if max_len > 0 else width} blocks, objects: {len(objects)}")

    out_dir = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(out_dir):
        out_dir = os.path.expanduser("~")
    out = os.path.join(out_dir, f"{fn}.gmd")
    write_gmd(out, ln, level)
    _log(f"done: {out}")


def convert_worker(path, z_list, scale, radius, fn, ln, baseplate=True, max_len=0, fast=False):
    try:
        run_conversion(path, z_list, scale, radius, fn, ln, baseplate, max_len, fast)
    except Exception as ex:
        _log(f"err: {ex}")
    finally:
        btn_conv.config(state=tk.NORMAL)
        btn_stop.config(state=tk.DISABLED)


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
        messagebox.showerror("Err", "file must be .rbxlx")
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
        messagebox.showerror("Err", "lvl name max 20 chars")
        return

    try:
        scale = float(scale_val.replace(",", "."))
        radius = float(rad_val.replace(",", "."))
        max_len = int(len_val.replace(",", ".") or 0)
        if scale <= 0 or radius < 0 or max_len < 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("Err", "scale > 0, radius/length >= 0")
        return

    if z_val.lower() in ("", "all", "*"):
        z_list = None
    else:
        try:
            z_list = [float(v.replace(",", ".").strip()) for v in z_val.split(",")]
        except ValueError:
            messagebox.showerror("Err", "z layers: numbers or all")
            return

    btn_conv.config(state=tk.DISABLED)
    btn_stop.config(state=tk.NORMAL)

    baseplate = var_baseplate.get()
    fast = var_fast.get()

    threading.Thread(
        target=convert_worker,
        args=(path, z_list, scale, radius, fn, ln, baseplate, max_len, fast),
        daemon=True,
    ).start()


def stop_conv():
    global STOP_FLAG
    STOP_FLAG = True


def on_drop(event):
    raw = event.data.strip()
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
    global log_box, btn_conv, btn_stop, var_baseplate, var_fast

    root = TkinterDnD.Tk()
    root.title("rblx2gd BY FGNGD")
    root.geometry("500x750")
    root.configure(bg="white")
    root.protocol("WM_DELETE_WINDOW", sys.exit)

    f1 = tk.Frame(root, bg="white")
    f1.pack(pady=15, padx=20, fill="both", expand=True)

    f2 = tk.Frame(f1, bg="white")
    f2.pack(fill="x", pady=5)

    tk.Label(f2, text="RBLX2GD", bg="white", fg="black", font=("Arial", 16, "bold")).pack(side=tk.LEFT)
    tk.Button(f2, text="🔗", command=link, bg="white", bd=0, font=("Arial", 14), cursor="hand2").pack(side=tk.RIGHT)

    entry_path = tk.Entry(f1, width=50, bg="white", fg="black", bd=1, relief="solid")
    entry_path.insert(0, "Drag .rbxlx file...")
    entry_path.bind("<FocusIn>", lambda e: entry_path.delete(0, tk.END) if entry_path.get() == "Drag .rbxlx file..." else None)
    entry_path.pack(fill="x", pady=10)

    root.drop_target_register(DND_FILES)
    root.dnd_bind("<<Drop>>", on_drop)

    f3 = tk.Frame(f1, bg="white")
    f3.pack(fill="x", pady=5)

    tk.Label(f3, text="Z Layers:", bg="white", fg="black").grid(row=0, column=0, sticky="w", pady=3)
    entry_z = tk.Entry(f3, width=20, bg="white", fg="black", bd=1, relief="solid")
    entry_z.insert(0, "0")
    entry_z.grid(row=0, column=1, pady=3, padx=5)

    tk.Label(f3, text="Radius (0 = all):", bg="white", fg="black").grid(row=1, column=0, sticky="w", pady=3)
    entry_rad = tk.Entry(f3, width=10, bg="white", fg="black", bd=1, relief="solid")
    entry_rad.insert(0, "0")
    entry_rad.grid(row=1, column=1, pady=3, padx=5)

    tk.Label(f3, text="Scale (studs/block):", bg="white", fg="black").grid(row=2, column=0, sticky="w", pady=3)
    entry_scale = tk.Entry(f3, width=10, bg="white", fg="black", bd=1, relief="solid")
    entry_scale.insert(0, "1")
    entry_scale.grid(row=2, column=1, pady=3, padx=5)

    tk.Label(f3, text="Length (0 = all):", bg="white", fg="black").grid(row=3, column=0, sticky="w", pady=3)
    entry_len = tk.Entry(f3, width=10, bg="white", fg="black", bd=1, relief="solid")
    entry_len.insert(0, "0")
    entry_len.grid(row=3, column=1, pady=3, padx=5)

    tk.Label(f3, text="File Name:", bg="white", fg="black").grid(row=4, column=0, sticky="w", pady=3)
    entry_fn = tk.Entry(f3, width=20, bg="white", fg="black", bd=1, relief="solid")
    entry_fn.insert(0, "rblx2gdfile")
    entry_fn.grid(row=4, column=1, pady=3, padx=5)

    tk.Label(f3, text="Level Name:", bg="white", fg="black").grid(row=5, column=0, sticky="w", pady=3)
    entry_ln = tk.Entry(f3, width=20, bg="white", fg="black", bd=1, relief="solid")
    entry_ln.insert(0, "rblx2gd level")
    entry_ln.grid(row=5, column=1, pady=3, padx=5)

    tk.Label(f3, text="Baseplate:", bg="white", fg="black").grid(row=6, column=0, sticky="w", pady=3)
    var_baseplate = tk.BooleanVar(value=True)
    tk.Checkbutton(f3, text="include baseplate", variable=var_baseplate, bg="white", fg="black", activebackground="white", activeforeground="black", selectcolor="white", bd=0, highlightthickness=0).grid(row=6, column=1, sticky="w", padx=5)

    var_fast = tk.BooleanVar(value=False)
    tk.Checkbutton(f3, text="fast (single-cell objects)", variable=var_fast, bg="white", fg="black", activebackground="white", activeforeground="black", selectcolor="white", bd=0, highlightthickness=0).grid(row=7, column=1, sticky="w", padx=5)

    f4 = tk.Frame(f1, bg="white")
    f4.pack(pady=10)

    btn_conv = tk.Button(f4, text="CONVERT", command=do_convert, bg="#e0e0e0", fg="black", font=("Arial", 12), bd=1, relief="raised", width=15)
    btn_conv.pack(side=tk.LEFT, padx=5)

    btn_stop = tk.Button(f4, text="STOP", command=stop_conv, bg="#ffcccc", fg="black", font=("Arial", 12), bd=1, relief="raised", width=10, state=tk.DISABLED)
    btn_stop.pack(side=tk.LEFT, padx=5)

    tk.Label(f1, text="Console", bg="white", fg="black", font=("Arial", 10, "bold"), anchor="w").pack(fill="x")

    log_box = tk.Text(f1, height=12, bg="white", fg="black", font=("Consolas", 9), bd=1, relief="solid")
    log_box.pack(fill="both", expand=True, pady=5)

    root.mainloop()


if __name__ == "__main__":
    main()
