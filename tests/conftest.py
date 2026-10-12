"""Shared fixtures: offline fake translation engines so the suite never hits the network."""
import os
import sys
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import translate_srt as T  # noqa: E402
from deep_translator.exceptions import TooManyRequests  # noqa: E402


def fake_translate(text: str) -> str:
    """Deterministic 'translation': easy to assert, never equal to the input."""
    return f"TR<{text}>"


class FakeEngineState:
    """Records every call made to fake engines, across all instances and threads."""

    def __init__(self):
        self.lock = threading.Lock()
        self.calls = []            # (engine, text)
        self.instances = []        # (engine, instance)
        self.threads = set()
        self.google_fail_after = None   # int: raise 429 after N successful calls
        self.google_always_fail = False
        self.google_fail_texts = set()  # texts that always raise
        self.mm_always_fail = False
        self.latency = 0.0
        self.mm_kwargs = []

    def record(self, engine, text):
        with self.lock:
            self.calls.append((engine, text))
            self.threads.add(threading.get_ident())
            return sum(1 for e, _ in self.calls if e == engine)

    def count(self, engine):
        return sum(1 for e, _ in self.calls if e == engine)


@pytest.fixture
def engines(monkeypatch):
    state = FakeEngineState()

    class FakeGoogle:
        def __init__(self, source="auto", target="en", **kw):
            if target not in ("tr", "en", "de", "fr", "es", "ja", "it", "ru", "zh-CN"):
                from deep_translator.exceptions import LanguageNotSupportedException
                raise LanguageNotSupportedException(target)
            self.source, self.target = source, target
            state.instances.append(("google", self))

        def translate(self, text, **kw):
            n = state.record("google", text)
            if state.latency:
                time.sleep(state.latency)
            if state.google_always_fail or text in state.google_fail_texts:
                raise TooManyRequests()
            if state.google_fail_after is not None and n > state.google_fail_after:
                raise TooManyRequests()
            return fake_translate(text)

        def translate_batch(self, batch, **kw):
            # Mirrors deep_translator 1.11.4: one request per item, no real batching.
            return [self.translate(t) for t in batch]

        def get_supported_languages(self, as_dict=False):
            return {"turkish": "tr", "english": "en"} if as_dict else ["turkish", "english"]

    class FakeMyMemory:
        def __init__(self, source="en-GB", target="tr-TR", **kw):
            state.mm_kwargs.append((source, target))
            state.instances.append(("mymemory", self))

        def translate(self, text, **kw):
            state.record("mymemory", text)
            if state.mm_always_fail:
                raise TooManyRequests()
            return f"MM<{text}>"

    monkeypatch.setattr(T, "GoogleTranslator", FakeGoogle)
    monkeypatch.setattr(T, "MyMemoryTranslator", FakeMyMemory)
    # Retry back-off sleeps would make failure-path tests take minutes.
    monkeypatch.setattr(T.time, "sleep", lambda s: None)
    state.FakeGoogle = FakeGoogle
    return state


@pytest.fixture
def T_module():
    return T


SAMPLE_SRT = (
    "1\r\n"
    "00:00:01,000 --> 00:00:02,500\r\n"
    "<i>Who am I?</i>\r\n"
    "\r\n"
    "2\r\n"
    "00:00:03,000 --> 00:00:05,000\r\n"
    "The story of my life\r\n"
    "is not for the faint of heart.\r\n"
    "\r\n"
    "3\r\n"
    "00:00:06,000 --> 00:00:07,000\r\n"
    "  Stop! Stop the bus!  \r\n"
    "\r\n"
    "4\r\n"
    "00:00:08,000 --> 00:00:09,000\r\n"
    "<i>Who am I?</i>\r\n"
)


@pytest.fixture
def sample_srt_lines():
    return SAMPLE_SRT.splitlines(True)
