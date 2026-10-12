"""translate_lines / translate_generic_lines: structure preservation and subtitle quality."""
import pytest

import translate_srt as T
from conftest import fake_translate


def _translatable(lines):
    return [l for l in lines if l.strip() and not T.is_sequence_number(l) and not T.is_timestamp(l)]


def test_structure_preserved(engines, sample_srt_lines):
    out = T.translate_lines(sample_srt_lines, target_lang="tr", engine_mode="google")
    assert len(out) == len(sample_srt_lines)
    for src, dst in zip(sample_srt_lines, out):
        if T.is_sequence_number(src) or T.is_timestamp(src) or not src.strip():
            assert src == dst, "indices, timestamps and blank lines must be byte-identical"
        else:
            assert dst != src
        assert dst.endswith("\r\n") == src.endswith("\r\n")


def test_leading_trailing_whitespace_preserved(engines, sample_srt_lines):
    out = T.translate_lines(sample_srt_lines, target_lang="tr", engine_mode="google")
    assert out[11] == "  " + fake_translate("Stop! Stop the bus!") + "  \r\n"


def test_duplicate_lines_translated_once(engines, sample_srt_lines):
    T.translate_lines(sample_srt_lines, target_lang="tr", engine_mode="google")
    texts = [t for _, t in engines.calls]
    assert texts.count("<i>Who am I?</i>") == 1


def test_no_translatable_lines_returns_input_without_calls(engines):
    lines = ["1\n", "00:00:01,000 --> 00:00:02,000\n", "\n"]
    assert T.translate_lines(lines, target_lang="tr") is lines
    assert engines.calls == []


def test_empty_input(engines):
    assert T.translate_lines([], target_lang="tr") == []


def test_lf_and_no_final_newline(engines):
    lines = ["1\n", "00:00:01,000 --> 00:00:02,000\n", "Hello"]
    out = T.translate_lines(lines, target_lang="tr", engine_mode="google")
    assert out[2] == fake_translate("Hello")


def test_html_tags_are_sent_to_engine(engines, sample_srt_lines):
    """Documents current behaviour: formatting tags go to the MT engine verbatim,
    which often mangles them (e.g. '< i >', translated attribute values)."""
    T.translate_lines(sample_srt_lines, target_lang="tr", engine_mode="google")
    assert ("google", "<i>Who am I?</i>") in engines.calls


@pytest.mark.xfail(strict=True, reason="H12: tags should be protected with placeholders, only plain text sent to the engine")
def test_tags_protected(engines, sample_srt_lines):
    T.translate_lines(sample_srt_lines, target_lang="tr", engine_mode="google")
    assert all("<i>" not in t for _, t in engines.calls)


@pytest.mark.xfail(strict=True, reason="H12: each line of a multi-line cue is translated separately, losing sentence context")
def test_multiline_cue_translated_as_one_sentence(engines, sample_srt_lines):
    T.translate_lines(sample_srt_lines, target_lang="tr", engine_mode="google")
    assert any("The story of my life" in t and "faint of heart" in t for _, t in engines.calls)


@pytest.mark.xfail(strict=True, reason="H30: ASS override tags like {\\an8} are sent to the engine")
def test_ass_override_tags_protected(engines):
    lines = ["1\n", "00:00:01,000 --> 00:00:02,000\n", "{\\an8}Top text\n"]
    T.translate_lines(lines, target_lang="tr", engine_mode="google")
    assert [t for _, t in engines.calls] == ["Top text"]


# ---------- soft wrap ----------
def test_soft_wrap_off_by_default(engines):
    long = "word " * 30
    lines = ["1\n", "00:00:01,000 --> 00:00:02,000\n", long.strip() + "\n"]
    out = T.translate_lines(lines, target_lang="tr", engine_mode="google")
    assert "\n" not in out[2][:-1]


@pytest.mark.xfail(strict=True, reason="H13: soft wrap inserts bare '\\n' inside CRLF files (mixed line endings)")
def test_soft_wrap_keeps_line_ending_style(monkeypatch):
    monkeypatch.setattr(T, "_build_translation_map", lambda texts, **kw: {t: t for t in texts})
    lines = ["1\r\n", "00:00:01,000 --> 00:00:02,000\r\n", ("a " * 60).strip() + "\r\n"]
    out = T.translate_lines(lines, target_lang="tr", wrap_limit=70)
    body = out[2][:-2]
    assert "\n" not in body.replace("\r\n", "")


@pytest.mark.xfail(strict=True, reason="H13: wrapping is per line, so a 2-line cue can become 4+ lines (subtitle standard: max 2 lines)")
def test_wrap_never_exceeds_two_lines_per_cue(monkeypatch):
    monkeypatch.setattr(T, "_build_translation_map", lambda texts, **kw: {t: (t + " ") * 3 for t in texts})
    lines = ["1\n", "00:00:01,000 --> 00:00:02,000\n",
             "This is a fairly long first line of dialogue\n",
             "and here is the second line of it\n"]
    out = T.translate_lines(lines, target_lang="tr", wrap_limit=42)
    cue_text = "".join(out[2:])
    assert cue_text.count("\n") <= 2


def test_soft_wrap_respects_limit(monkeypatch):
    monkeypatch.setattr(T, "_build_translation_map", lambda texts, **kw: {t: t for t in texts})
    text = " ".join(["kelime"] * 20)
    out = T.translate_lines(["1\n", "00:00:01,000 --> 00:00:02,000\n", text + "\n"], wrap_limit=30)
    assert all(len(seg) <= 30 for seg in out[2].rstrip("\n").split("\n"))


# ---------- generic text ----------
def test_generic_lines_translate_everything_non_blank(engines):
    lines = ["Title\n", "\n", "  body text\n", "123\n"]
    out = T.translate_generic_lines(lines, "tr", 100, 6, "google")
    assert out[1] == "\n"
    assert out[2] == "  " + fake_translate("body text") + "\n"
    # In plain text, numbers ARE sent to the engine (unlike SRT).
    assert out[3] == fake_translate("123") + "\n"


@pytest.mark.xfail(strict=True, reason="H31: Markdown code blocks / inline code are translated")
def test_markdown_code_block_untouched(engines):
    lines = ["# Title\n", "```\n", "print('hello')\n", "```\n"]
    T.translate_generic_lines(lines, "tr", 100, 6, "google")
    assert ("google", "print('hello')") not in engines.calls


@pytest.mark.xfail(strict=True, reason="H31: CSV is translated line-by-line including delimiters and quotes; cells/headers are not parsed")
def test_csv_cells_translated_individually(engines):
    lines = ['id,text\n', '1,"Hello, world"\n']
    T.translate_generic_lines(lines, "tr", 100, 6, "google")
    assert ("google", "Hello, world") in engines.calls
