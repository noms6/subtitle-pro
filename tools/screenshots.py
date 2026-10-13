"""Render README screenshots of the real GUI (Windows; needs Pillow).

    python tools/screenshots.py docs/images
Produces screenshot-<theme>-<lang>.png (main window, sample files queued, mid-run state)
plus dialog-settings-<theme>.png and dialog-about.png.
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


def grab(widget, path):
    widget.update()
    time.sleep(0.4)
    widget.update()
    x, y, w, h = widget.winfo_rootx(), widget.winfo_rooty(), widget.winfo_width(), widget.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(path, optimize=True)
    print("saved", path)


def set_theme(app, theme, lang):
    app.dark_mode_var.set(theme == "dark")
    app.theme_var.set(theme)
    app._apply_theme()
    app._sync_header_combos()
    name = next(n for n, c in app.ui_lang_map.items() if c == lang)
    app.ui_lang_var.set(name)
    app._on_ui_lang_change()


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    T._SETTINGS_FILE = os.path.join(os.environ.get("TEMP", "/tmp"), "subtitle_pro_shots.json")
    if os.path.exists(T._SETTINGS_FILE):
        os.remove(T._SETTINGS_FILE)
    app = T.TranslatorGUI()
    app._save_settings = lambda: None
    app._set_maximized(False)
    app.root.geometry("1280x820+20+20")
    app.root.attributes("-topmost", True)
    for name in ("tests/fixtures/sample.en.srt", "README.md", "CONTRIBUTING.md"):
        app._add_file(os.path.join(ROOT, name))
    for theme, lang in SHOTS:
        set_theme(app, theme, lang)
        app._select_target_code("tr" if lang != "tr" else "en")
        app._log_entries.clear()
        app._refresh_log_view()
        app._log(f"{app._tr('File added')}: sample.en.srt", "ok")
        app._log(app._tr("Translation started..."), "info")
        app.circ.set(64, f"{app._tr('ETA')}: 00:12")
        app.progress_var.set(64)
        app.status_var.set(app._fmt_progress_label(64, 12, 1, 3, "sample.en.srt", 230, 360, 21))
        grab(app.root, os.path.join(out_dir, f"screenshot-{theme}-{lang}.png"))
    # empty state
    set_theme(app, "dark", "tr")
    app._clear_files()
    app.circ.set(0, f"{app._tr('ETA')}: --:--")
    app.progress_var.set(0)
    app.status_var.set(app._tr("Ready"))
    app._log_entries.clear()
    app._refresh_log_view()
    grab(app.root, os.path.join(out_dir, "screenshot-empty-dark-tr.png"))
    # dialogs
    for theme in ("light", "dark"):
        set_theme(app, theme, "tr")
        app._open_settings("translation")
        win = app._settings_win
        win.attributes("-topmost", True)
        grab(win, os.path.join(out_dir, f"dialog-settings-{theme}.png"))
        win.destroy()
    before = set(app.root.winfo_children())
    app._show_about()
    about = [w for w in app.root.winfo_children() if w not in before][0]
    about.attributes("-topmost", True)
    grab(about, os.path.join(out_dir, "dialog-about.png"))
    about.destroy()
    app.root.destroy()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "images"))
