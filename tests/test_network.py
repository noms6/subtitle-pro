"""Live smoke tests against real services. Opt-in:  pytest -m network

They are excluded by default (see pyproject.toml) because they are slow, depend on
third-party rate limits and can get your IP temporarily blocked by Google.
"""
import time

import pytest

pytestmark = pytest.mark.network


def test_google_single():
    from deep_translator import GoogleTranslator
    out = GoogleTranslator(source="en", target="tr").translate("Good morning")
    assert out and out != "Good morning"


def test_mymemory_single():
    from deep_translator import MyMemoryTranslator
    out = MyMemoryTranslator(source="en-GB", target="tr-TR").translate("Good morning")
    assert out and "MYMEMORY WARNING" not in out.upper()


def test_google_joined_request_keeps_line_count():
    """Proof of concept for real batching: N lines joined with '\\n' come back as N lines."""
    import requests
    texts = [f"Room number {i} has a red door." for i in range(1, 51)]
    r = requests.get(
        "https://translate.googleapis.com/translate_a/single",
        params={"client": "gtx", "sl": "en", "tl": "tr", "dt": "t", "q": "\n".join(texts)},
        timeout=20,
    )
    r.raise_for_status()
    out = "".join(seg[0] for seg in r.json()[0]).split("\n")
    assert len(out) == len(texts)


def test_pipeline_small_file():
    import translate_srt as T
    lines = ["1\n", "00:00:01,000 --> 00:00:02,000\n", "Where is the station?\n"]
    t0 = time.time()
    out = T.translate_lines(lines, target_lang="tr", engine_mode="auto")
    assert out[2].strip() != "Where is the station?", "untranslated (rate limited?)"
    assert time.time() - t0 < 30
