"""SRT/VTT line classification, whitespace handling, encoding detection, helpers."""
import pytest

import translate_srt as T


# ---------- timestamps ----------
@pytest.mark.parametrize("line", [
    "00:00:01,000 --> 00:00:02,000",
    "01:23:45,678 --> 01:23:47,000\r\n",
    "00:00:01.000 --> 00:00:02.000",
    "00:00:01.000 --> 00:00:02.000 align:start position:10%",
])
def test_timestamp_detected(line):
    assert T.is_timestamp(line)


@pytest.mark.parametrize("line", ["Hello", "00:00:01", "1", "", "-->"])
def test_non_timestamp(line):
    assert not T.is_timestamp(line)


@pytest.mark.xfail(strict=True, reason="H18: SRT timestamps with position coords (X1:.. Y1:..) are sent to the translator")
def test_srt_timestamp_with_coordinates():
    assert T.is_timestamp("00:00:01,000 --> 00:00:02,000 X1:100 X2:200 Y1:300 Y2:400")


@pytest.mark.xfail(strict=True, reason="H18: short VTT timestamps (mm:ss.ttt) are not recognised")
def test_vtt_short_timestamp():
    assert T.is_timestamp("00:01.000 --> 00:04.000")


@pytest.mark.xfail(strict=True, reason="H18: SRT with dot or single-digit hour (common in the wild) is not recognised")
def test_srt_lenient_timestamp():
    assert T.is_timestamp("0:00:01,000 --> 0:00:02,000")


# ---------- sequence numbers ----------
def test_sequence_number():
    assert T.is_sequence_number("12")
    assert T.is_sequence_number(" 7 \r\n")
    assert not T.is_sequence_number("12a")


@pytest.mark.xfail(strict=True, reason="H17: a dialogue line made only of digits (e.g. '2024', '911') is treated as a cue index and never translated")
def test_numeric_dialogue_line_is_translatable(engines, T_module):
    lines = ["1\n", "00:00:01,000 --> 00:00:02,000\n", "1984\n", "\n"]
    T.translate_lines(lines, target_lang="tr", engine_mode="google")
    # "1984" is dialogue here; only its position (after the timestamp) tells us so.
    assert ("google", "1984") in engines.calls


@pytest.mark.xfail(strict=True, reason="H28: UTF-8 BOM is kept as U+FEFF, so the first cue index '\\ufeff1' is sent to the translator")
def test_bom_first_index_not_translated(tmp_path, engines):
    p = tmp_path / "bom.srt"
    p.write_bytes("1\r\n00:00:01,000 --> 00:00:02,000\r\nHi\r\n".encode("utf-8-sig"))
    lines = T._read_lines_robust(str(p))
    T.translate_lines(lines, target_lang="tr", engine_mode="google")
    assert [t for _, t in engines.calls] == ["Hi"]


# ---------- VTT ----------
@pytest.mark.parametrize("line", ["WEBVTT", "WEBVTT - Movie", "NOTE this is a comment", "STYLE", "REGION"])
def test_vtt_meta(line):
    assert T.is_vtt_meta(line)


@pytest.mark.xfail(strict=True, reason="H17: dialogue starting with 'Note'/'Style'/'Region' is skipped as VTT metadata (also in SRT files)")
def test_dialogue_starting_with_note_is_translated():
    assert not T.is_vtt_meta("Note to self: buy milk.")


@pytest.mark.xfail(strict=True, reason="H29: VTT header fields (Kind:/Language:) are translated, corrupting the file header")
def test_vtt_header_fields_not_translated(engines):
    lines = ["WEBVTT\n", "Kind: captions\n", "Language: en\n", "\n",
             "00:00:01.000 --> 00:00:02.000\n", "Hello\n"]
    T.translate_lines(lines, target_lang="tr", engine_mode="google")
    assert [t for _, t in engines.calls] == ["Hello"]


@pytest.mark.xfail(strict=True, reason="H29: VTT cue identifiers (text line before a timestamp) are translated")
def test_vtt_cue_identifier_not_translated(engines):
    lines = ["WEBVTT\n", "\n", "intro-cue\n", "00:00:01.000 --> 00:00:02.000\n", "Hello\n"]
    T.translate_lines(lines, target_lang="tr", engine_mode="google")
    assert [t for _, t in engines.calls] == ["Hello"]


# ---------- whitespace / helpers ----------
@pytest.mark.parametrize("line,expected", [
    ("  hi  ", ("  ", "hi", "  ")),
    ("\thi", ("\t", "hi", "")),
    ("hi", ("", "hi", "")),
    pytest.param("   ", ("   ", "", ""), marks=pytest.mark.xfail(
        strict=True, reason="H34 (low): whitespace-only input is returned twice (lead and trail both = input)")),
    ("", ("", "", "")),
])
def test_split_whitespace(line, expected):
    lead, core, trail = T.split_whitespace(line)
    assert lead + core + trail == line
    if core:
        assert (lead, core, trail) == expected


def test_chunk():
    assert T.chunk(list("abcde"), 2) == [["a", "b"], ["c", "d"], ["e"]]
    assert T.chunk([], 3) == []


def test_looks_turkish():
    assert T.looks_turkish("Güzel bir gün")
    assert not T.looks_turkish("Nice day")


def test_out_path_same_ext():
    assert T._out_path_same_ext(r"C:\a\movie.en.srt", "tr") == r"C:\a\movie.en.tr.srt"


@pytest.mark.parametrize("req,mods", [
    ("deep-translator==1.11.4", ["deep_translator"]),
    ("python-docx", ["docx"]),
    ("pdfminer.six", ["pdfminer"]),
    ("ttkbootstrap>=1.10", ["ttkbootstrap"]),
    ("some-pkg", ["some_pkg"]),
])
def test_req_to_import_names(req, mods):
    assert T._req_to_import_names(req) == mods


@pytest.mark.xfail(strict=True, reason="H22: requirement markers/extras are not stripped ('pkg[extra]; python_version<\"3.11\"')")
def test_req_with_extras_and_markers():
    assert T._req_to_import_names('requests[socks]; python_version < "3.11"') == ["requests"]


def test_requirements_parser_skips_comments(tmp_path):
    f = tmp_path / "r.txt"
    f.write_text("# c\n\nfoo==1\n  bar  \n", encoding="utf-8")
    assert T._parse_requirements_file(str(f)) == ["foo==1", "bar"]


# ---------- encodings ----------
@pytest.mark.parametrize("enc,text", [
    ("utf-8", "Çılgın gün\n"),
    ("cp1254", "Çılgın gün\n"),
    ("latin-1", "café crème\n"),
])
def test_read_lines_robust_encodings(tmp_path, enc, text):
    p = tmp_path / f"f_{enc}.txt"
    p.write_bytes(text.encode(enc))
    assert T._read_lines_robust(str(p)) == [text]


def test_read_lines_robust_keeps_crlf(tmp_path):
    p = tmp_path / "crlf.srt"
    p.write_bytes(b"a\r\nb\r\n")
    assert T._read_lines_robust(str(p)) == ["a\r\n", "b\r\n"]


def test_read_lines_robust_missing_file_returns_empty():
    # Silently returns [] — the GUI then writes an empty output instead of reporting the error.
    assert T._read_lines_robust("does/not/exist.srt") == []


@pytest.mark.xfail(strict=True, reason="H19: UTF-16 subtitles (saved by Notepad/Subtitle Edit 'Unicode') decode as cp1254 garbage")
def test_read_lines_robust_utf16(tmp_path):
    p = tmp_path / "u16.srt"
    p.write_bytes("Merhaba\r\n".encode("utf-16"))
    assert T._read_lines_robust(str(p)) == ["Merhaba\r\n"]


# ---------- language helpers ----------
@pytest.mark.parametrize("code,expected", [("tr", "tr-TR"), ("en", "en-GB"), ("de", "de-DE")])
def test_mymemory_mapping_known(code, expected):
    assert T._map_lang_for_mymemory(code) == expected


@pytest.mark.xfail(strict=True, reason="H8: unknown targets silently map to Turkish (ja -> tr-TR)")
@pytest.mark.parametrize("code", ["ja", "ko", "ar", "nl", "zh-CN", "pt"])
def test_mymemory_mapping_unknown_is_not_turkish(code):
    assert T._map_lang_for_mymemory(code) != "tr-TR"


@pytest.mark.xfail(strict=True, reason="H6: GoogleTranslator.get_supported_languages is called on the class -> TypeError -> 37-language fallback")
def test_supported_languages_full_list():
    assert len(T._get_supported_langs("en")) > 100


@pytest.mark.xfail(strict=True, reason="H7: Turkish fallback map has no 'Turkish' key, so the GUI default target becomes the first alphabetical entry ('Almanca')")
def test_turkish_fallback_contains_default_name():
    langs = T._get_supported_langs("tr")
    assert "Turkish" in langs or langs.get(sorted(langs)[0]) == "tr"
