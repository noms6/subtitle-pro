"""UI localisation and layout regressions (language packs, live language switching, layout)."""
import json
import os
import sys
import time

import pytest

import translate_srt as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import i18n_sync  # noqa: E402

PACKS = json.load(open(T._UI_CACHE_FILE, encoding="utf-8"))
KEYS = i18n_sync.extract_keys(open(os.path.join(ROOT, "translate_srt.py"), encoding="utf-8").read())
LANGS = sorted(c for c in PACKS if c != "en")
# Words legitimately spelled the same as English in some languages
COGNATES = {"Info", "OK", "Log", "Status", "Start", "Auto", "ETA", "Output", "Version:", "Lang:", "Orange", "Pink",
            "Teal", "Accent:", "Performance", "Preferences...", "Progress", "Multi-format: SRT, VTT, TXT, MD, CSV, DOCX, PDF",
            "Engine", "PDF", "TXT", "Dictionary", "Error", "Workers:"}


# ---------- language pack data ----------
def test_every_language_has_every_key():
    for code in PACKS:
        missing = set(KEYS) - set(PACKS[code])
        assert not missing, f"{code}: {sorted(missing)[:5]}"


def test_no_junk_or_unused_keys():
    for code, pack in PACKS.items():
        extra = set(pack) - set(KEYS)
        assert not extra, f"{code}: unused/junk keys {sorted(extra)[:5]}"


@pytest.mark.parametrize("code", LANGS)
def test_language_is_actually_translated(code):
    """Before: 16 languages had ~136/162 strings still in English."""
    pack = PACKS[code]
    untranslated = [k for k in KEYS if pack[k] == k and k not in i18n_sync.KEEP and k not in COGNATES and len(k) > 2]
    assert len(untranslated) <= 3, f"{code}: {untranslated}"


@pytest.mark.parametrize("code", LANGS)
def test_no_wrong_script(code):
    """Before: the Japanese pack contained Korean strings."""
    bad = {k: v for k, v in PACKS[code].items() if i18n_sync.wrong_script(code, v)}
    assert not bad, f"{code}: {list(bad.items())[:3]}"


@pytest.mark.parametrize("code", LANGS)
def test_punctuation_kept(code):
    for k, v in PACKS[code].items():
        if k.endswith(":"):
            assert v.rstrip().endswith((":", "：")), (code, k, v)
        if k.endswith("..."):
            assert v.endswith(("...", "…")), (code, k, v)


def test_hand_checked_terms_applied():
    over = json.load(open(os.path.join(ROOT, "tools", "i18n_overrides.json"), encoding="utf-8"))
    for code, terms in over.items():
        if code.startswith("_"):
            continue
        for k, v in terms.items():
            if k in PACKS[code]:
                assert PACKS[code][k] == v, (code, k)
    assert PACKS["ar"]["Clear"] != "واضح"          # used to mean "obvious"
    assert PACKS["ar"]["Teal"] != "البط البري"     # used to mean "wild duck"


# ---------- runtime lookup ----------
def test_icon_prefix_is_stripped_for_lookup():
    assert T._ui_translate("📂 Add...", "tr") == "📂 " + PACKS["tr"]["Add..."]
    assert T._ui_translate("▶ Start", "de") == "▶ " + PACKS["de"]["Start"]
    assert T._ui_translate("(Drag-and-drop supported)", "tr") == PACKS["tr"]["(Drag-and-drop supported)"]


def test_unknown_text_and_english_pass_through():
    assert T._ui_translate("Totally unknown", "tr") == "Totally unknown"
    assert T._ui_translate("Start", "en") == "Start"


def test_regional_code_falls_back_to_base_language():
    assert T._ui_translate("Start", "de-AT") == PACKS["de"]["Start"]


def test_packs_parsed_once(monkeypatch):
    """Before: _tr() re-read and parsed the 270 KB JSON on every call (~40x per language switch)."""
    T._load_ui_packs()
    calls = {"n": 0}
    real = json.load
    monkeypatch.setattr(T.json, "load", lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1), real(*a, **k))[1])
    for _ in range(500):
        T._ui_translate("Start", "tr")
    assert calls["n"] == 0


def test_lang_names_localized():
    assert T._localize_lang_name("tr", "ja") == "トルコ語"
    assert T._localize_lang_name("de", "tr") == "Almanca"   # was "Alman"
    assert T._localize_lang_name("af", "en") != "af"         # unknown codes used to show raw


def test_ui_language_picker_uses_autonyms():
    for code in PACKS:
        assert code in T.UI_LANG_AUTONYMS


# ---------- live GUI ----------
tk = pytest.importorskip("tkinter")
try:
    _r = tk.Tk()
    _r.destroy()
except Exception:  # pragma: no cover
    pytest.skip("no display available for Tk", allow_module_level=True)

import ui_audit  # noqa: E402


@pytest.fixture(scope="module")
def gui(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setattr(T, "_SETTINGS_FILE", str(tmp_path_factory.mktemp("ui") / "settings.json"))
    mp.setattr(T, "_prebuild_ui_packs", lambda codes: None)
    mp.setattr(T, "_ensure_ui_json_has_all_texts", lambda codes: None)
    app = T.TranslatorGUI()
    app.root.state("normal")
    app.root.geometry("1280x800+0+0")
    app._save_settings = lambda: None
    app.root.update()
    yield app
    app.root.destroy()
    mp.undo()


BRANDS = {"Google", "MyMemory", "DeepL", "DeepL (Web)", "Libre", "Subtitle PRO – Multi Translator", "☰", "🌐"}


@pytest.mark.parametrize("code", ["tr", "de", "ja", "ar", "ru", "zh-CN", "fr", "es"])
def test_switching_language_translates_every_visible_text(gui, code):
    ui_audit.switch(gui, "en")
    base = ui_audit.collect(gui)
    ui_audit.switch(gui, code)
    cur = ui_audit.collect(gui)
    still = sorted({t for p, (_k, t, _c) in cur.items()
                    if p in base and base[p][1] == t and t not in BRANDS and any(c.isalpha() for c in t)
                    and t not in COGNATES and t.strip("▶⏹ ") not in COGNATES})
    assert not still, f"{code}: still English: {still}"


@pytest.mark.parametrize("code", ["tr", "de", "ja", "fi"])
def test_no_clipped_widgets(gui, code):
    ui_audit.switch(gui, code)
    clipped = [t for _p, (_k, t, c) in ui_audit.collect(gui).items() if c]
    assert not clipped, f"{code}: {clipped}"


def test_language_switch_is_fast(gui):
    ui_audit.switch(gui, "en")
    dt, _ = ui_audit.switch(gui, "tr")
    assert dt < 1.0


def test_target_picker_localized_and_selection_kept(gui):
    ui_audit.switch(gui, "en")
    gui._select_target_code("tr")
    ui_audit.switch(gui, "ja")
    assert gui.target_lang_var.get() == "トルコ語"
    assert gui._current_target_code() == "tr"


def test_status_bar_reflects_theme_and_language(gui):
    ui_audit.switch(gui, "en")
    gui.dark_mode_var.set(False)
    gui._refresh_status_bar()
    assert "Light mode" in gui.status_bar.cget("text")
    assert "Dark mode" not in gui.status_bar.cget("text")   # used to always say "theme:dark"


def test_mouse_wheel_scrolls_main_page(gui):
    """Before: a hidden panel's bind_all stole the wheel; the main page never scrolled."""
    gui.root.geometry("1280x600")
    gui.root.update()
    canvas = gui.root_scroll.canvas
    canvas.yview_moveto(0)
    gui.root_scroll._bind_wheel()
    canvas.event_generate("<MouseWheel>", delta=-120, x=50, y=50)
    gui.root.update()
    assert canvas.yview()[0] > 0
    gui.root.geometry("1280x800")


def test_log_filter_checkbox_controls_view(gui):
    """Before: the filter vars were re-created after the checkbuttons were bound."""
    assert str(gui.chk_log_info.cget("variable")) == str(gui.log_info_var)
    gui._log_entries.clear()
    gui._refresh_log_view()
    gui._log("an info line", "info")
    gui._log("an error line", "error")
    gui.log_info_var.set(False)
    gui._refresh_log_view()
    text = gui.txt_log.get("1.0", "end")
    assert "an error line" in text and "an info line" not in text
    gui.log_info_var.set(True)


def test_log_is_fast(gui):
    """Before: every _log redrew the whole widget (2,000 lines took 5.6 s)."""
    t0 = time.perf_counter()
    for i in range(2000):
        gui._log(f"line {i}", "info")
    assert time.perf_counter() - t0 < 1.5


def test_log_from_worker_thread_is_marshalled(gui):
    import threading
    gui._log_entries.clear()
    t = threading.Thread(target=lambda: gui._log("from worker", "ok"))
    t.start()
    t.join()
    deadline = time.perf_counter() + 2
    while time.perf_counter() < deadline and not any("from worker" in l for _v, l in gui._log_entries):
        gui.root.update()
        time.sleep(0.02)
    assert any("from worker" in line for _lvl, line in gui._log_entries)


def test_titlebar_text_readable_in_light_theme(gui):
    """Before: white title on a near-white bar."""
    bg = "#f5f7fb"
    assert gui._contrast_fg(gui.root, bg) == "#1f2937"
    assert gui._contrast_fg(gui.root, "#111827") == "#f8fafc"


def test_header_menu_exposes_hidden_menubar_items(gui):
    """The native menubar is invisible (overrideredirect); its items must be in the ☰ menu."""
    labels = [gui.header_menu.entrycget(i, "label") for i in range(gui.header_menu.index("end") + 1)
              if gui.header_menu.type(i) != "separator"]
    ui_audit.switch(gui, "en")
    labels = [gui.header_menu.entrycget(i, "label") for i in range(gui.header_menu.index("end") + 1)
              if gui.header_menu.type(i) != "separator"]
    for item in ("Font size", "Compact mode", "Preferences...", "About"):
        assert item in labels


def test_theme_and_accent_pickers_localized(gui):
    ui_audit.switch(gui, "tr")
    assert gui.cmb_theme.cget("values")[1] == PACKS["tr"]["Dark mode"]
    assert PACKS["tr"]["Teal"] in gui.cmb_accent.cget("values")


def test_default_target_language(gui):
    gui.ui_lang_code = "en"
    assert gui._default_target_code(None) == "tr"
    assert gui._default_target_code("ja") == "ja"
    gui.ui_lang_code = "de"
    assert gui._default_target_code(None) == "de"
    gui.ui_lang_code = "en"
