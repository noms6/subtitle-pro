"""_build_translation_map: engine routing, retries, fallback, concurrency, progress, cancel."""
import threading
import time

import pytest

import translate_srt as T
from conftest import fake_translate


def build(texts, **kw):
    kw.setdefault("target_lang", "tr")
    kw.setdefault("batch_size", 10)
    kw.setdefault("mm_workers", 4)
    return T._build_translation_map(texts, **kw)


TEXTS = [f"Line number {i}" for i in range(25)]


# ---------- happy paths ----------
def test_google_happy_path(engines):
    m = build(TEXTS, engine_mode="google")
    assert m == {t: fake_translate(t) for t in TEXTS}
    assert engines.count("mymemory") == 0


def test_auto_google_first_uses_google(engines):
    build(TEXTS, engine_mode="auto")
    assert engines.count("google") == len(TEXTS)


def test_mymemory_mode(engines):
    m = build(TEXTS, engine_mode="mymemory")
    assert all(v.startswith("MM<") for v in m.values())
    assert engines.count("google") == 0


def test_auto_mymemory_first_never_uses_google(engines):
    """`google` is only instantiated when use_google is True, which excludes mymemory_first,
    so the documented 'fill gaps with Google' step (line ~1369) is dead code."""
    engines.mm_always_fail = True
    m = build(TEXTS, engine_mode="auto", auto_priority="mymemory_first")
    assert engines.count("google") == 0
    assert all(m[t] == t for t in TEXTS)  # everything silently left untranslated


@pytest.mark.xfail(strict=True, reason="H32: auto+mymemory_first should fall back to Google for failed lines, but Google is never instantiated")
def test_mymemory_first_falls_back_to_google(engines):
    engines.mm_always_fail = True
    m = build(TEXTS, engine_mode="auto", auto_priority="mymemory_first")
    assert all(m[t] == fake_translate(t) for t in TEXTS)


def test_dedupe_before_requests(engines):
    build(["a", "b", "a", "a", "c", "b"], engine_mode="google")
    assert sorted(t for _, t in engines.calls) == ["a", "b", "c"]


def test_none_inputs_ignored(engines):
    m = build(["a", None, "b"], engine_mode="google")
    assert set(m) == {"a", "b"}


# ---------- H1: silent failure ----------
@pytest.mark.xfail(strict=True, reason="H1 (CRITICAL): when Google returns 429 the original text is stored as the 'translation' and MyMemory fallback never runs")
def test_rate_limited_google_falls_back_to_mymemory(engines):
    engines.google_always_fail = True
    m = build(TEXTS, engine_mode="google")
    assert all(m[t] != t for t in TEXTS)
    assert engines.count("mymemory") == len(TEXTS)


def test_rate_limited_google_returns_originals_silently(engines):
    """Characterises H1: no exception, no flag — caller cannot tell anything failed."""
    engines.google_always_fail = True
    m = build(TEXTS, engine_mode="google")
    assert m == {t: t for t in TEXTS}
    assert engines.count("mymemory") == 0


def test_rate_limit_mid_run_leaves_tail_untranslated(engines):
    """Real-world scenario seen in the sample movie: first ~N requests succeed, then 429."""
    engines.google_fail_after = 12
    m = build(TEXTS, engine_mode="google", batch_size=5)
    untranslated = [t for t in TEXTS if m[t] == t]
    assert 0 < len(untranslated) < len(TEXTS)
    assert engines.count("mymemory") == 0


@pytest.mark.xfail(strict=True, reason="H1: there is no way to know which lines failed (no status / exception / count)")
def test_failures_are_reported(engines):
    engines.google_always_fail = True
    result = build(TEXTS, engine_mode="google")
    assert hasattr(result, "failed") or isinstance(result, tuple)


# ---------- request amplification ----------
def test_one_bad_item_triggers_request_amplification(engines):
    """One permanently failing line in a batch of 10 makes the whole batch retry 3x and
    then every item individually: 10 lines cost ~3*k + 10..12 requests instead of 10."""
    engines.google_fail_texts = {"Line number 5"}
    build(TEXTS[:10], engine_mode="google", batch_size=10)
    assert engines.count("google") >= 3 * 6 + 10


@pytest.mark.xfail(strict=True, reason="H2: request count should stay close to the number of lines (+ small retry budget)")
def test_request_budget_with_one_bad_item(engines):
    engines.google_fail_texts = {"Line number 5"}
    build(TEXTS[:10], engine_mode="google", batch_size=10)
    assert engines.count("google") <= 10 + 3


def test_one_request_per_line_no_real_batching(engines):
    """Characterises H2: 'batch_size=100' still means one HTTP request per unique line."""
    texts = [f"t{i}" for i in range(100)]
    build(texts, engine_mode="google", batch_size=100)
    assert engines.count("google") == 100


# ---------- invalid-response heuristic ----------
@pytest.mark.xfail(strict=True, reason="H33: legitimate dialogue containing 'server error' / 'too many requests' is treated as an engine error and left untranslated")
def test_dialogue_mentioning_server_error(engines, monkeypatch):
    m = build(["The site shows a server error again."], engine_mode="google")
    # fake engine echoes input inside TR<...>, which contains 'server error'
    assert m["The site shows a server error again."] != "The site shows a server error again."


# ---------- language handling ----------
def test_invalid_target_language_raises(engines):
    """CLI with a typo ('trr') crashes with a traceback instead of a friendly message."""
    from deep_translator.exceptions import LanguageNotSupportedException
    with pytest.raises(LanguageNotSupportedException):
        build(["x"], target_lang="trr", engine_mode="google")


@pytest.mark.xfail(strict=True, reason="H8: MyMemory source is hard-coded to en-GB, so non-English sources are mistranslated")
def test_mymemory_source_not_hardcoded(engines):
    build(["Bonjour"], engine_mode="mymemory")
    assert engines.mm_kwargs[0][0] != "en-GB"


def test_mymemory_japanese_target_becomes_turkish(engines):
    """Characterises H8 end-to-end: asking for Japanese via MyMemory yields a Turkish target."""
    build(["Hello"], target_lang="ja", engine_mode="mymemory")
    assert engines.mm_kwargs[0][1] == "tr-TR"


@pytest.mark.xfail(strict=True, reason="H9: engine 'deepl_web' is offered in the UI but routes everything to MyMemory")
def test_deepl_web_is_used(engines):
    build(["Hello"], engine_mode="deepl_web")
    assert engines.count("mymemory") == 0


def test_deepl_without_key_silently_uses_mymemory(engines, monkeypatch):
    monkeypatch.setattr(T, "_DEEPL_API_KEY", None)
    m = build(["Hello"], engine_mode="deepl")
    assert m["Hello"] == "MM<Hello>"


# ---------- concurrency ----------
def test_single_translator_instance_shared_across_threads(engines):
    """Characterises H3: one GoogleTranslator object is used by up to 4 threads."""
    build([f"x{i}" for i in range(80)], engine_mode="google", batch_size=10)
    google_instances = [i for e, i in engines.instances if e == "google"]
    assert len(google_instances) == 1


def test_race_with_stateful_translator(monkeypatch):
    """Simulates deep_translator's real pattern (store text in self._url_params, then request).
    With a shared instance and parallel batches, results get swapped between lines."""
    import translate_srt as TT

    class StatefulGoogle:
        def __init__(self, source="auto", target="tr", **kw):
            self._params = {}

        def translate(self, text, **kw):
            self._params["q"] = text
            _real_sleep(0.001)          # network round-trip window
            return "TR<" + self._params["q"] + ">"

        def translate_batch(self, batch, **kw):
            return [self.translate(t) for t in batch]

    _real_sleep = time.sleep
    monkeypatch.setattr(TT, "GoogleTranslator", StatefulGoogle)
    texts = [f"line-{i}" for i in range(120)]
    m = TT._build_translation_map(texts, target_lang="tr", batch_size=10, mm_workers=4, engine_mode="google")
    swapped = [t for t in texts if m[t] != f"TR<{t}>"]
    assert swapped, "expected cross-thread mix-ups with a shared stateful translator"


# ---------- progress ----------
def test_progress_monotonic_and_complete(engines):
    seen = []
    build(TEXTS, engine_mode="google", progress_callback=lambda d, t: seen.append((d, t)))
    dones = [d for d, _ in seen]
    assert dones == sorted(dones)
    assert seen[-1][0] == seen[-1][1]


def test_progress_callback_exception_does_not_abort(engines):
    def boom(d, t):
        raise RuntimeError("ui gone")
    m = build(TEXTS, engine_mode="google", progress_callback=boom)
    assert len(m) == len(TEXTS)


def test_progress_called_from_worker_threads(engines):
    """Progress is reported from pool threads; GUI callers must marshal to the Tk thread."""
    main = threading.get_ident()
    threads = set()
    build(TEXTS, engine_mode="mymemory", progress_callback=lambda d, t: threads.add(threading.get_ident()))
    assert threads  # main thread drives as_completed, so this one is actually main
    assert main in threads


# ---------- cancel ----------
def test_cancel_returns_originals_as_translations(engines):
    """Characterises H14: cancelled lines are stored as 'translated' (identical to source)."""
    m = build(TEXTS, engine_mode="google", cancel_check=lambda: True)
    assert m == {t: t for t in TEXTS}
    assert engines.count("google") == 0


@pytest.mark.xfail(strict=True, reason="H14: cancellation should be signalled (exception/flag), not look like a finished translation")
def test_cancel_is_signalled(engines):
    with pytest.raises(Exception):  # noqa: B017 - any signal is acceptable
        build(TEXTS, engine_mode="google", cancel_check=lambda: True)


def test_cancel_does_not_stop_mymemory_pool(engines):
    """MyMemory branch ignores cancel_check entirely: every line is still requested."""
    build(TEXTS, engine_mode="mymemory", cancel_check=lambda: True)
    assert engines.count("mymemory") == len(TEXTS)
