"""Headless-ish GUI tests: the real TranslatorGUI is built, driven, and torn down.

Network side effects are disabled and settings are redirected to a temp file.
Skipped automatically when no display / Tk is available (e.g. Linux CI without Xvfb).
"""
import json
import os
import threading
import time
import types

import pytest

import translate_srt as T
from conftest import SAMPLE_SRT

tk = pytest.importorskip("tkinter")
try:
    _r = tk.Tk()
    _r.destroy()
except Exception:  # pragma: no cover
    pytest.skip("no display available for Tk", allow_module_level=True)

_real_sleep = time.sleep
_real_perf = time.perf_counter


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("gui")
    mp = pytest.MonkeyPatch()
    mp.setattr(T, "_SETTINGS_FILE", str(tmp / "settings.json"))
    mp.setattr(T, "_prebuild_ui_packs", lambda codes: None)
    mp.setattr(T, "_ensure_ui_json_has_all_texts", lambda codes: None)
    a = T.TranslatorGUI()
    a.root.withdraw()
    a._callback_errors = []
    a.root.report_callback_exception = lambda e, v, tb: a._callback_errors.append(v)
    a._dialog_threads = []
    a._showerror_calls = []

    def fake_ask(file_name, err):
        a._dialog_threads.append(threading.get_ident())
        return "skip"
    a._ask_error_action = fake_ask
    mp.setattr(T.messagebox, "showerror", lambda *x, **k: a._showerror_calls.append(x))
    mp.setattr(T.messagebox, "askyesno", lambda *x, **k: True)
    yield a
    try:
        a.root.destroy()
    except Exception:
        pass
    mp.undo()


@pytest.fixture
def clean(app):
    app._clear_files()
    app._cancel = False
    app._callback_errors.clear()
    app._dialog_threads.clear()
    app._showerror_calls.clear()
    app.skip_same_lang_var.set(True)
    app.engine_var.set("google")
    app.parallel_files_var.set(False)
    app.save_next_var.set(True)
    app.dict_mode_var.set("off")
    name = next(n for n, c in app.lang_map.items() if c == "tr")
    app.target_lang_var.set(name)
    return app


def pump(app, timeout=20.0):
    """Run the real Tk mainloop (as in production) until the worker thread finishes.

    The worker reads Tk variables and calls root.after() directly; that only works while
    mainloop() is running, so a manual update() loop is not enough (see H4)."""
    deadline = _real_perf() + timeout
    state = {"drain": 0}

    def check():
        done = app._thread is not None and not app._thread.is_alive()
        if done:
            state["drain"] += 1
        if state["drain"] > 5 or _real_perf() > deadline:
            app.root.quit()
        else:
            app.root.after(20, check)

    app.root.after(20, check)
    app.root.mainloop()
    assert app._thread is not None and not app._thread.is_alive(), "worker did not finish"


def status_of(app, path):
    return app.tree.set(app.file_items[path], "durum")


def make_srt(tmp_path, name="movie.en.srt", content=SAMPLE_SRT):
    p = tmp_path / name
    p.write_bytes(content.encode("utf-8"))
    return str(p)


# ---------- construction ----------
def test_gui_constructs_without_callback_errors(app):
    app.root.update()
    assert app._callback_errors == []


def test_title_and_queue_widgets_exist(app):
    assert hasattr(app, "tree") and hasattr(app, "tb_start")


def test_rebuild_target_lang_names_is_method(app):
    """H5 (fixed): was nested inside a module-level function."""
    assert hasattr(app, "_rebuild_target_lang_names")


def test_target_lang_map_is_built(app):
    app._rebuild_target_lang_names()
    assert len(app.target_lang_map) > 100


def test_many_target_languages(app):
    """H6 (fixed): full Google list instead of the 37-language fallback."""
    assert len(app.lang_map) > 100


# ---------- end-to-end ----------
def test_e2e_srt_translation(clean, engines, tmp_path):
    app = clean
    p = make_srt(tmp_path)
    app._add_file(p)
    app._start()
    pump(app)
    out = tmp_path / "movie.en.tr.srt"
    assert out.exists()
    text = out.read_bytes().decode("utf-8-sig")
    assert "TR<Stop! Stop the bus!>" in text
    assert "00:00:01,000 --> 00:00:02,500" in text
    assert status_of(app, p) == app._tr("Completed")
    assert app._callback_errors == []


def test_e2e_rate_limited_file_marked_done_but_untranslated(clean, engines, tmp_path):
    """Characterises H1 at user level: 429 everywhere -> file says 'Tamamlandı', content is English."""
    engines.google_always_fail = True
    app = clean
    p = make_srt(tmp_path)
    app._add_file(p)
    app._start()
    pump(app)
    text = (tmp_path / "movie.en.tr.srt").read_bytes().decode("utf-8-sig")
    assert "Stop! Stop the bus!" in text and "TR<" not in text
    assert status_of(app, p) == app._tr("Completed")


@pytest.mark.xfail(strict=True, reason="H1: a file whose lines failed must not be reported as 'Tamamlandı'")
def test_e2e_rate_limited_file_reported(clean, engines, tmp_path):
    engines.google_always_fail = True
    app = clean
    p = make_srt(tmp_path)
    app._add_file(p)
    app._start()
    pump(app)
    assert status_of(app, p) != app._tr("Completed")


def test_e2e_parallel_files(clean, engines, tmp_path):
    app = clean
    paths = [make_srt(tmp_path, f"ep{i}.srt") for i in range(4)]
    for p in paths:
        app._add_file(p)
    app.parallel_files_var.set(True)
    app.file_workers_var.set(3)
    app._start()
    pump(app)
    for i in range(4):
        assert (tmp_path / f"ep{i}.tr.srt").exists()


def test_e2e_output_directory(clean, engines, tmp_path):
    app = clean
    outdir = tmp_path / "out"
    outdir.mkdir()
    p = make_srt(tmp_path)
    app._add_file(p)
    app.save_next_var.set(False)
    app.outdir_var.set(str(outdir))
    app._start()
    pump(app)
    assert (outdir / "movie.en.tr.srt").exists()


def test_skip_same_language_can_be_disabled(  # H11 (fixed)
        clean, engines, tmp_path, monkeypatch):
    monkeypatch.setattr(T, "detect_language", lambda s: "tr")
    app = clean
    p = make_srt(tmp_path, content="1\n00:00:01,000 --> 00:00:02,000\nÇok güzel bir gün\n")
    app._add_file(p)
    app.skip_same_lang_var.set(False)
    app._start()
    pump(app)
    assert (tmp_path / "movie.en.tr.srt").exists()


def test_error_dialog_on_main_thread(  # H4 (fixed): worker hands the dialog to the Tk thread
        clean, engines, tmp_path, monkeypatch):
    monkeypatch.setattr(T, "translate_lines", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    app = clean
    app._add_file(make_srt(tmp_path))
    app._start()
    pump(app)
    assert app._dialog_threads == [threading.get_ident()]


@pytest.mark.parametrize("attempt", range(5))  # H27 (fixed): used to lose the message in ~half of runs
def test_fatal_error_is_shown_to_user(clean, engines, tmp_path, monkeypatch, attempt):
    app = clean
    app._add_file(make_srt(tmp_path))
    # fail inside the worker, outside per-file handling (first thing _run does is log the start)
    monkeypatch.setattr(app, "_log", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full")))
    app._start()
    pump(app)
    assert app._showerror_calls and not app._callback_errors


@pytest.mark.xfail(strict=True, reason="H14: after Cancel, a half-translated file is written and marked 'Tamamlandı'")
def test_cancel_does_not_write_partial_file(clean, engines, tmp_path, monkeypatch):
    app = clean
    original = engines.FakeGoogle.translate

    def translate_then_cancel(self, text, **kw):
        app._cancel = True
        return original(self, text, **kw)
    monkeypatch.setattr(engines.FakeGoogle, "translate", translate_then_cancel)
    p = make_srt(tmp_path)
    app._add_file(p)
    app.batch_size_var.set(10)
    app._start()
    pump(app)
    assert not (tmp_path / "movie.en.tr.srt").exists() or status_of(app, p) != app._tr("Completed")


# ---------- settings ----------
def test_save_settings_preserves_api_keys(app):
    with open(T._SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({"deepl_api_key": "abc:fx", "libre_url": "http://localhost:5000"}, f)
    app._save_settings()
    cfg = json.load(open(T._SETTINGS_FILE, encoding="utf-8"))
    assert cfg.get("deepl_api_key") == "abc:fx"


@pytest.mark.parametrize("key", ["engine", "auto_priority", "dict_mode", "pdf_mode", "skip_same_lang"])
def test_settings_persist_all_options(app, key):
    app._save_settings()
    cfg = json.load(open(T._SETTINGS_FILE, encoding="utf-8"))
    assert key in cfg


def test_saved_dark_theme_applied_on_start(app, tmp_path, monkeypatch):
    """H38 (fixed): __init__ now calls _apply_loaded_settings after _load_settings."""
    s = tmp_path / "s.json"
    s.write_text(json.dumps({"dark": True}), encoding="utf-8")
    monkeypatch.setattr(T, "_SETTINGS_FILE", str(s))
    app.dark_mode_var.set(False)
    app.theme_var.set("light")
    app._load_settings()
    app._apply_loaded_settings()
    try:
        assert app.theme_var.get() == "dark"
        assert app.cmb_theme.current() == 1
    finally:
        app.dark_mode_var.set(False)
        app._apply_loaded_settings()


def test_settings_roundtrip_basic(app):
    app.batch_size_var.set(55)
    app._save_settings()
    app.batch_size_var.set(100)
    app._load_settings()
    assert app.batch_size_var.get() == 55


def test_corrupt_settings_file_is_ignored(app):
    with open(T._SETTINGS_FILE, "w", encoding="utf-8") as f:
        f.write("{not json")
    app._load_settings()  # must not raise


# ---------- file queue ----------
def test_add_file_filters(clean, tmp_path):
    app = clean
    good = make_srt(tmp_path)
    bad = tmp_path / "video.mkv"
    bad.write_bytes(b"x")
    app._add_file(good)
    app._add_file(good)
    app._add_file(str(bad))
    app._add_file(str(tmp_path / "missing.srt"))
    assert app.files == [os.path.normpath(good)]


def test_clear_files_clears_reverse_map(clean, tmp_path):
    app = clean
    app._add_file(make_srt(tmp_path))
    app._clear_files()
    assert app.item_to_path == {}


def test_drop_parsing_braced_paths(clean, monkeypatch):
    app = clean
    got = []
    monkeypatch.setattr(app, "_add_file", lambda p: got.append(p))
    app._on_drop(types.SimpleNamespace(data="{C:/My Movies/a b.srt} C:/x/y.srt"))
    assert got == [os.path.normpath("C:/My Movies/a b.srt"), os.path.normpath("C:/x/y.srt")]


# ---------- dictionary ----------
def test_apply_terms_plain(app):
    assert app._apply_terms("Hello Jill", {"Jill": "Ceyda"}) == "Hello Ceyda"


def test_apply_terms_default_has_no_word_boundary(app):
    """Default settings replace inside words: 'Al'->'Ali' turns 'Also' into 'Aliso'."""
    if hasattr(app, "dict_word_boundary_var"):
        app.dict_word_boundary_var.set(False)
    assert app._apply_terms("Also Al", {"Al": "Ali"}) == "Aliso Ali"


def test_load_custom_dict_csv_and_bad_json(app, tmp_path):
    c = tmp_path / "d.csv"
    c.write_text("Jill,Ceyda\nonly-one-col\n", encoding="utf-8")
    app._load_custom_dict(str(c))
    assert app.custom_terms == {"Jill": "Ceyda"}
    j = tmp_path / "d.json"
    j.write_text("[1,2,3]", encoding="utf-8")
    app._load_custom_dict(str(j))
    # A JSON list is accepted silently and later breaks _apply_terms (.items())
    assert app.custom_terms == [1, 2, 3]


@pytest.mark.xfail(strict=True, reason="H37: preview language hint always reports 'auto' (deep_translator never updates .source)")
def test_language_hint(app, engines):
    assert app._detect_language_hint("Bonjour tout le monde") not in ("auto", "?")


def test_worker_never_calls_tk_directly(clean, engines, tmp_path, monkeypatch):
    """H4 (fixed): every UI update from the worker goes through the queue drained on the Tk thread."""
    app = clean
    calls = []
    real_after = app.root.after

    def spy_after(ms, fn=None, *args):
        calls.append(threading.get_ident())
        return real_after(ms, fn, *args) if fn else real_after(ms)
    monkeypatch.setattr(app.root, "after", spy_after)
    app._add_file(make_srt(tmp_path))
    app._start()
    pump(app)
    main = threading.get_ident()
    assert calls and all(t == main for t in calls)
