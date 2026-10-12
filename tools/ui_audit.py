"""UI localisation & layout audit.

Builds the real GUI, switches through every UI language in ui_translations.json and,
for each one, walks the whole widget tree (labels, buttons, check/radio buttons,
label frames, tree headings, menus) to report:

  * texts still in English (identical to the English UI)
  * texts that are hard-coded Turkish (visible in every language)
  * clipped widgets (requested width > allocated width)
  * time taken to switch language

Usage:  python tools/ui_audit.py [--langs tr,de,ja] [--json out.json] [--shots DIR]
"""
import argparse
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import translate_srt as T  # noqa: E402

TURKISH_CHARS = set("çğıöşüÇĞİÖŞÜ")
TURKISH_WORDS = re.compile(r"\b(Hazır|Çevir|Tamamlan|Dosya|Ekle|Kaldır|Temizle|Başlat|Seçil|kalan|geçen|kelime|Durum|Boyut|Eklendi|Atlandı|İptal)\w*", re.I)


def widget_texts(root):
    """Yield (path, kind, text, clipped) for every text-bearing widget."""
    stack = [root]
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        try:
            if not w.winfo_ismapped():
                continue
        except Exception:
            continue
        cls = w.winfo_class()
        text = None
        try:
            if "text" in w.keys():
                text = str(w.cget("text"))
        except Exception:
            pass
        if text and text.strip():
            clipped = False
            try:
                clipped = w.winfo_reqwidth() > w.winfo_width() + 2 and w.winfo_width() > 1
            except Exception:
                pass
            yield str(w), cls, text, clipped
        if cls == "Treeview":
            for col in w["columns"]:
                yield f"{w}#{col}", "Heading", str(w.heading(col, "text")), False
        if cls == "Menu":
            try:
                end = w.index("end")
                for i in range(0 if end is None else end + 1):
                    if w.type(i) in ("command", "checkbutton", "radiobutton", "cascade"):
                        yield f"{w}[{i}]", "MenuItem", str(w.entrycget(i, "label")), False
            except Exception:
                pass


def collect(app):
    app.root.update_idletasks()
    app.root.update()
    seen = {}
    for path, kind, text, clipped in widget_texts(app.root):
        seen[path] = (kind, text, clipped)
    try:
        seen["<title>"] = ("Title", app.root.title(), False)
        seen["<status>"] = ("Status", app.status_var.get(), False)
    except Exception:
        pass
    return seen


def switch(app, code):
    name = next((n for n, c in app.ui_lang_map.items() if c == code), None)
    if name is None:
        app._rebuild_ui_lang_names()
        name = next((n for n, c in app.ui_lang_map.items() if c == code), None)
    app.ui_lang_var.set(name or code)
    t0 = time.perf_counter()
    app._on_ui_lang_change()
    app.root.update()
    return time.perf_counter() - t0, name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--shots", default="")
    a = ap.parse_args()

    data = json.load(open(T._UI_CACHE_FILE, encoding="utf-8"))
    codes = [c for c in (a.langs.split(",") if a.langs else sorted(data)) if c]

    T._prebuild_ui_packs = lambda c: None
    T._ensure_ui_json_has_all_texts = lambda c: None
    T._SETTINGS_FILE = os.path.join(os.environ.get("TEMP", "/tmp"), "subtitle_pro_audit_settings.json")

    loads = {"n": 0}
    real_load = json.load

    def counting_load(*x, **k):
        loads["n"] += 1
        return real_load(*x, **k)
    T.json.load = counting_load

    app = T.TranslatorGUI()
    app.root.state("normal")
    app.root.geometry("1280x800+20+20")
    app._save_settings = lambda: None
    app.root.update()

    switch(app, "en")
    baseline = collect(app)
    report = {}
    for code in codes:
        loads["n"] = 0
        dt, name = switch(app, code)
        cur = collect(app)
        english, turkish, clipped = [], [], []
        for path, (_kind, text, clip) in cur.items():
            if clip:
                clipped.append(text)
            if code != "en" and path in baseline and baseline[path][1] == text and re.search("[A-Za-z]{3}", text):
                english.append(text)
            if code != "tr" and (TURKISH_WORDS.search(text) or (set(text) & TURKISH_CHARS)):
                turkish.append(text)
        total = len(cur)
        report[code] = {
            "name": name, "switch_ms": round(dt * 1000), "json_loads": loads["n"], "texts": total,
            "still_english": sorted(set(english)), "hardcoded_turkish": sorted(set(turkish)),
            "clipped": sorted(set(clipped)),
        }
        r = report[code]
        print(f"{code:6} {str(name)[:18]:18} switch={r['switch_ms']:5d}ms json_loads={r['json_loads']:3d} "
              f"texts={total:3d} english={len(r['still_english']):3d} turkish={len(r['hardcoded_turkish']):3d} clipped={len(r['clipped']):2d}")
        if a.shots:
            from PIL import ImageGrab
            os.makedirs(a.shots, exist_ok=True)
            app.root.lift()
            app.root.attributes("-topmost", True)
            app.root.update()
            time.sleep(0.4)
            x, y, w, h = app.root.winfo_rootx(), app.root.winfo_rooty(), app.root.winfo_width(), app.root.winfo_height()
            ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(os.path.join(a.shots, f"ui_{code}.png"))
            app.root.attributes("-topmost", False)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    app.root.destroy()


if __name__ == "__main__":
    main()
