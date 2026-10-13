"""Screenshots for the multilingual README (Windows; needs Pillow).

    python tools/readme_shots.py
Writes docs/images/readme/<lang>.png (main window in that UI language, dark theme, mid-run)
plus English shots used by every README: main-light.png, empty-dark.png, settings-dark.png.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import translate_srt as T  # noqa: E402
from PIL import Image, ImageGrab  # noqa: E402

OUT = os.path.join(ROOT, "docs", "images", "readme")
# README language code -> UI language code
LANGS = {"en": "en", "tr": "tr", "de": "de", "fr": "fr", "es": "es", "it": "it", "pt": "pt", "nl": "nl",
         "pl": "pl", "sv": "sv", "ru": "ru", "uk": "uk", "ar": "ar", "fa": "fa", "hi": "hi", "ja": "ja",
         "ko": "ko", "zh": "zh-CN", "id": "id", "vi": "vi"}
TARGET = {"en": "tr", "tr": "en"}   # target language shown in the picker (default: Turkish)


def grab(widget, path, width=1100):
    widget.update()
    time.sleep(0.35)
    widget.update()
    x, y, w, h = widget.winfo_rootx(), widget.winfo_rooty(), widget.winfo_width(), widget.winfo_height()
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    if img.width > width:
        img = img.resize((width, int(img.height * width / img.width)), Image.LANCZOS)
    img.save(path, optimize=True)
    print("saved", os.path.relpath(path, ROOT))


def set_ui(app, theme, lang):
    app.dark_mode_var.set(theme == "dark")
    app.theme_var.set(theme)
    app._apply_theme()
    app._sync_header_combos()
    name = next(n for n, c in app.ui_lang_map.items() if c == lang)
    app.ui_lang_var.set(name)
    app._on_ui_lang_change()


def mid_run(app, files):
    app._clear_files()
    for f in files:
        app._add_file(f)
    app._log_entries.clear()
    app._refresh_log_view()
    app._log(f"{app._tr('File added')}: sample.en.srt", "ok")
    app._log(app._tr("Translation started..."), "info")
    app.circ.set(64, f"{app._tr('ETA')}: 00:04")
    app.progress_var.set(64)
    app.status_var.set(app._fmt_progress_label(64, 4, 1, 3, "sample.en.srt", 4218, 6590, 7))


def main():
    os.makedirs(OUT, exist_ok=True)
    T._SETTINGS_FILE = os.path.join(os.environ.get("TEMP", "/tmp"), "subtitle_pro_readme_shots.json")
    if os.path.exists(T._SETTINGS_FILE):
        os.remove(T._SETTINGS_FILE)
    app = T.TranslatorGUI()
    app._save_settings = lambda: None
    app._set_maximized(False)
    app.root.geometry("1280x800+20+20")
    app.root.attributes("-topmost", True)
    files = [os.path.join(ROOT, p) for p in ("tests/fixtures/sample.en.srt", "README.md", "CONTRIBUTING.md")]
    for code, ui in LANGS.items():
        set_ui(app, "dark", ui)
        app._select_target_code(TARGET.get(code, "tr"))
        mid_run(app, files)
        grab(app.root, os.path.join(OUT, f"{code}.png"))
    # shared English shots
    set_ui(app, "light", "en")
    app._select_target_code("tr")
    mid_run(app, files)
    grab(app.root, os.path.join(OUT, "main-light.png"))
    set_ui(app, "dark", "en")
    app._clear_files()
    app.circ.set(0, f"{app._tr('ETA')}: --:--")
    app.progress_var.set(0)
    app.status_var.set(app._tr("Ready"))
    app._log_entries.clear()
    app._refresh_log_view()
    grab(app.root, os.path.join(OUT, "empty-dark.png"))
    app._open_settings("translation")
    app._settings_win.attributes("-topmost", True)
    grab(app._settings_win, os.path.join(OUT, "settings-dark.png"), width=700)
    app._settings_win.destroy()
    app.root.destroy()


if __name__ == "__main__":
    main()
