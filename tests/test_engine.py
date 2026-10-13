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
def test_rate_limited_google_falls_back_to_mymemory(engines):
    """H1 (fixed in the C:\\torrent copy's engine): 429 from Google -> MyMemory fallback."""
    engines.google_always_fail = True
    m = build(TEXTS, engine_mode="google")
    assert all(m[t] != t for t in TEXTS)
    assert engines.count("mymemory") == len(TEXTS)


def test_all_engines_failing_still_returns_originals_silently(engines):
    """Remaining part of H1: when every engine fails the originals come back with no signal."""
    engines.google_always_fail = True
    engines.mm_always_fail = True
    m = build(TEXTS, engine_mode="google")
    assert m == {t: t for t in TEXTS}


def test_rate_limit_mid_run_is_recovered(engines):
    """Real-world scenario seen in the sample movie (first ~N requests succeed, then 429):
    used to leave 38% of the film in English; the tail now goes to the fallback engine."""
    engines.google_fail_after = 12
    m = build(TEXTS, engine_mode="google", batch_size=5)
    assert all(m[t] != t for t in TEXTS)
    assert engines.count("mymemory") > 0


@pytest.mark.xfail(strict=True, reason="H1: there is no way to know which lines failed (no status / exception / count)")
def test_failures_are_reported(engines):
    engines.google_always_fail = True
    result = build(TEXTS, engine_mode="google")
    assert hasattr(result, "failed") or isinstance(result, tuple)


# ---------- request amplification ----------
def test_request_budget_with_one_bad_item(engines):
    """H2 amplification fixed: one bad line no longer re-sends the whole batch 3x (was >= 28 requests)."""
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
def test_no_race_with_stateful_translator(monkeypatch):
    """H3 (fixed): deep_translator stores the text on the instance before requesting; with a
    shared instance and parallel batches results used to get swapped between lines. Requests
    are now serialised (semaphore 1 + HTTP lock), so every line keeps its own translation."""
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
    assert not swapped


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


# ---------- fast batched path (Google JSON endpoint) + circuit breaker ----------
class _FakeResp:
    def __init__(self, status, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload, text
        self.content = b"x"

    def json(self):
        return self._payload


class _FakeRequests:
    """Mimics translate_a/single: returns one segment per input line, or a scripted status."""
    def __init__(self, status=200, merge_lines=False):
        self.status, self.merge_lines, self.calls = status, merge_lines, []

    def post(self, url, params=None, data=None, headers=None, timeout=None):
        self.calls.append(data["q"])
        if self.status != 200:
            return _FakeResp(self.status)
        lines = data["q"].split("\n")
        if self.merge_lines and len(lines) > 1:     # Google sometimes joins lines -> count mismatch
            return _FakeResp(200, [[["TR<" + " ".join(lines) + ">", "x"]]])
        return _FakeResp(200, [[["\n".join("TR<" + ln + ">" for ln in lines), "x"]]])

    def get(self, *a, **k):
        return _FakeResp(429)


@pytest.fixture
def fake_http(monkeypatch):
    def make(**kw):
        fr = _FakeRequests(**kw)
        monkeypatch.setattr(T, "requests", fr)
        monkeypatch.setattr(T, "_BLOCKED_UNTIL", {})
        monkeypatch.setattr(T.time, "sleep", lambda s: None)
        return fr
    return make


def test_fast_path_translates_film_in_few_requests(fake_http):
    fr = fake_http()
    texts = [f"Dialogue line number {i} with some words." for i in range(1400)]
    m = T._build_translation_map(texts, target_lang="tr", batch_size=100, mm_workers=4, engine_mode="google")
    assert all(m[t] == f"TR<{t}>" for t in texts)
    assert len(fr.calls) <= 20          # was 1,400 requests (one per line)


def test_fast_path_bisects_on_line_count_mismatch(fake_http):
    """If Google merges lines, translations must never shift onto the wrong line."""
    fake_http(merge_lines=True)
    texts = ["one", "two", "three", "four", "five"]
    out = T._gtx_translate_lines(texts, "tr")
    assert out == [f"TR<{t}>" for t in texts]


def test_fast_path_429_blocks_endpoint(fake_http):
    fr = fake_http(status=429)
    assert T._gtx_translate_lines(["a", "b"], "tr") == [None, None]
    assert T._endpoint_blocked("gtx")
    n = len(fr.calls)
    T._gtx_translate_texts(["c", "d"], "tr")
    assert len(fr.calls) == n           # no further requests while blocked


def test_blocked_html_endpoint_fails_fast(fake_http, monkeypatch):
    """/m returning 429 used to cost ~56 s of retries per line; now it is skipped at once."""
    fake_http()

    class Sess:
        calls = 0

        def get(self, *a, **k):
            Sess.calls += 1
            return _FakeResp(429)
    monkeypatch.setattr(T, "_get_google_session", lambda: Sess())
    assert T._google_translate_one_http("Hello", "tr") is None
    assert T._google_translate_one_http("World", "tr") is None
    assert Sess.calls == 1


def test_identical_names_are_not_retried(fake_http, monkeypatch):
    """'Rick.' / 'Ah!' come back unchanged from a successful response: done, not failures."""
    fr = fake_http()
    monkeypatch.setattr(fr, "post", lambda url, params=None, data=None, **k: (
        fr.calls.append(data["q"]), _FakeResp(200, [[[data["q"], "x"]]]))[1])
    T._build_translation_map(["Rick.", "Ah!"], target_lang="tr", batch_size=10, mm_workers=2, engine_mode="google")
    assert len(fr.calls) == 1
