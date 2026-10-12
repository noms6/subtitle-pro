"""Offline benchmark: request count and wall time of the current pipeline vs. real batching.

Usage:  python tools/benchmark.py [subtitle.srt] [--latency 0.05]

A fake engine with fixed per-request latency replaces Google, so results are reproducible
and no network is used. The "batched" column estimates a pipeline that joins lines into
<=4500-character requests (measured live: 80 lines in one request ~1.0 s).
"""
import argparse
import math
import os
import re
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import translate_srt as T  # noqa: E402


def analyse(lines):
    cues, cur = [], []
    for ln in lines:
        s = ln.strip("\r\n")
        if not s.strip():
            if cur:
                cues.append(cur)
            cur = []
        elif not T.is_sequence_number(s) and not T.is_timestamp(s):
            cur.append(s.strip())
    if cur:
        cues.append(cur)
    texts = [t for c in cues for t in c]
    uniq = list(dict.fromkeys(texts))
    tagged = sum(1 for t in texts if re.search(r"<[^>]+>|\{\\", t))
    return {
        "cues": len(cues),
        "text_lines": len(texts),
        "unique_lines": len(uniq),
        "multi_line_cues": sum(1 for c in cues if len(c) > 1),
        "lines_with_tags": tagged,
        "chars_unique": sum(len(t) for t in uniq),
        "max_line_len": max((len(t) for t in texts), default=0),
    }


def run_current(lines, latency):
    calls = {"n": 0}
    lock = threading.Lock()
    real_sleep = time.sleep

    class Fake:
        def __init__(self, *a, **k):
            pass

        def translate(self, text, **k):
            with lock:
                calls["n"] += 1
            real_sleep(latency)
            return text[::-1]

        def translate_batch(self, batch, **k):
            return [self.translate(t) for t in batch]

    T.GoogleTranslator = Fake
    t0 = time.perf_counter()
    T.translate_lines(lines, target_lang="tr", engine_mode="google")
    return time.perf_counter() - t0, calls["n"]


def bench_log(n=2000):
    """GUI _log redraws the whole log widget (up to 1000 lines) on every call."""
    T._prebuild_ui_packs = lambda c: None
    T._ensure_ui_json_has_all_texts = lambda c: None
    app = T.TranslatorGUI()
    app.root.withdraw()
    t0 = time.perf_counter()
    for i in range(n):
        app._log(f"line {i}", "info")
    dt = time.perf_counter() - t0
    app.root.destroy()
    return dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("srt", nargs="?", default=os.path.join(ROOT, "tests", "fixtures", "sample.en.srt"))
    ap.add_argument("--latency", type=float, default=0.05)
    ap.add_argument("--no-gui", action="store_true")
    a = ap.parse_args()

    lines = T._read_lines_robust(a.srt)
    st = analyse(lines)
    print(f"File: {os.path.basename(a.srt)}")
    for k, v in st.items():
        print(f"  {k:18} {v}")

    dt, n = run_current(lines, a.latency)
    batched_requests = max(1, math.ceil(st["chars_unique"] / 4500))
    print(f"\nSimulated latency per request: {a.latency*1000:.0f} ms")
    print(f"  current pipeline : {n:5d} requests, {dt:6.2f} s")
    print(f"  batched (est.)   : {batched_requests:5d} requests, {batched_requests * max(a.latency, 1.0) / 4:6.2f} s (4 workers, ~1 s/request)")
    print(f"  request reduction: {n / batched_requests:.0f}x")
    if not a.no_gui:
        try:
            print(f"\nGUI _log x2000: {bench_log():.2f} s (full Text widget redraw per call)")
        except Exception as e:  # no display
            print(f"GUI benchmark skipped: {e}")


if __name__ == "__main__":
    main()
