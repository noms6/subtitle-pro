"""Render README screenshots of the real GUI (Windows; needs Pillow).

    python tools/screenshots.py docs/images
Produces screenshot-<theme>-<lang>.png with a few sample files queued.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import translate_srt as T  # noqa: E402
from PIL import ImageGrab  # noqa: E402

SHOTS = [("light", "tr"), ("dark", "tr"), ("light", "en"), ("dark", "ja"), ("light", "de"), ("light", "ar")]


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    T._prebuild_ui_packs = lambda c: None
    T._ensure_ui_json_has_all_texts = lambda c: None
    T._SETTINGS_FILE = os.path.join(os.environ.get("TEMP", "/tmp"), "subtitle_pro_shots.json")
    app = T.TranslatorGUI()
    app._save_settings = lambda: None
    app.root.state("normal")
    app.root.geometry("1280x820+20+20")
    sample = os.path.join(ROOT, "tests", "fixtures", "sample.en.srt")
    app._add_file(sample)
    for name in ("README.md", "CONTRIBUTING.md"):
        app._add_file(os.path.join(ROOT, name))
    app.root.update()
    for theme, lang in SHOTS:
        app.dark_mode_var.set(theme == "dark")
        app.theme_var.set(theme)
        app._apply_theme()
        name = next(n for n, c in app.ui_lang_map.items() if c == lang)
        app.ui_lang_var.set(name)
        app._on_ui_lang_change()
        app._select_target_code("tr" if lang != "tr" else "en")
        app._log_entries.clear()
        app._refresh_log_view()
        app._log(f"{app._tr('File added')}: sample.en.srt", "ok")
        app._log(app._tr("Translation started..."), "info")
        app.circ.set(64, f"{app._tr('ETA')}: 00:12")
        app.progress_var.set(64)
        app.status_var.set(app._fmt_progress_label(64, 12, 1, 3, "sample.en.srt", 230, 360, 21))
        app.root.lift()
        app.root.attributes("-topmost", True)
        app.root.update()
        time.sleep(0.5)
        app.root.update()
        x, y, w, h = app.root.winfo_rootx(), app.root.winfo_rooty(), app.root.winfo_width(), app.root.winfo_height()
        path = os.path.join(out_dir, f"screenshot-{theme}-{lang}.png")
        ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(path, optimize=True)
        print("saved", path)
    app.root.destroy()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "images"))
