import os
import json
import re
import sys
import time
import traceback
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional, Callable, Dict
import shutil
import csv
import ctypes
import importlib
import subprocess
import html as html_lib
try:
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore
try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:
    BeautifulSoup = None  # type: ignore
try:
    import srt_clean  # type: ignore
except Exception:
    srt_clean = None  # type: ignore
# Google HTML scraping is fragile; keep this at 1 to avoid Error 500 pages.
_API_SEM = threading.Semaphore(1)
_GOOGLE_HTTP_LOCK = threading.Lock()
_MYMEMORY_QUOTA_HIT = False
_GOOGLE_SESSION = None
_GOOGLE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Optional: force Windows title bar dark mode (best effort)
try:
    from ctypes import windll  # type: ignore
    try:
        windll.dwmapi.DwmSetWindowAttribute(windll.user32.GetForegroundWindow(), 20, (1,), 4)  # type: ignore[arg-type]
    except Exception:
        pass
except Exception:
    pass

# ---- Windows dark titlebar helper ----
def _enable_win_dark_titlebar(win_handle: Optional[int], enable: bool) -> None:
    try:
        if not sys.platform.startswith("win"):
            return
        import ctypes as _ct
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # Windows 10 1903+
        try:
            # Some builds use 19
            _ct.windll.dwmapi.DwmSetWindowAttribute
        except Exception:
            return
        value = _ct.c_int(1 if enable else 0)
        hwnd = _ct.c_void_p(int(win_handle or 0))
        if hwnd.value:
            _ct.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, _ct.byref(value), _ct.sizeof(value))
            # try alt attr id
            if enable:
                _ct.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, _ct.byref(value), _ct.sizeof(value))
    except Exception:
        pass

def _ascii_fallback(text: str) -> str:
    try:
        return text.encode("ascii", "ignore").decode("ascii")
    except Exception:
        return text
def _req_to_import_names(req: str) -> List[str]:
    """Map a requirement name to one or more import module names."""
    base = req.strip()
    # strip version spec
    for sep in ("==", ">=", "<=", "~=", ">", "<"):  # simple split
        if sep in base:
            base = base.split(sep, 1)[0].strip()
            break
    name = base.lower()
    mapping: Dict[str, List[str]] = {
        "deep-translator": ["deep_translator"],
        "ttkbootstrap": ["ttkbootstrap"],
        "python-docx": ["docx"],
        "docx2txt": ["docx2txt"],
        "pdfminer.six": ["pdfminer"],
        "reportlab": ["reportlab"],
    }
    if name in mapping:
        return mapping[name]
    # generic: replace dashes/dots with underscores
    return [name.replace('-', '_').replace('.', '_')]


def _parse_requirements_file(path: str) -> List[str]:
    try:
        reqs: List[str] = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as rf:
                for line in rf:
                    s = line.strip()
                    if not s or s.startswith("#"):
                        continue
                    reqs.append(s)
        return reqs
    except Exception:
        return []


def _module_available(mod_name: str) -> bool:
    try:
        spec = importlib.util.find_spec(mod_name)  # type: ignore[attr-defined]
        return spec is not None
    except Exception:
        try:
            importlib.import_module(mod_name)
            return True
        except Exception:
            return False


def _install_packages(packages: List[str]) -> None:
    if not packages:
        return
    try:
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade"] + packages
        subprocess.run(cmd, check=False)
    except Exception:
        pass


def _ensure_requirements() -> None:
    """Install any missing packages from requirements.txt before imports.

    Safe to call repeatedly; will only attempt to install missing ones.
    """
    try:
        req_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
        reqs = _parse_requirements_file(req_path)
        missing: List[str] = []
        for r in reqs:
            import_names = _req_to_import_names(r)
            if not any(_module_available(m) for m in import_names):
                missing.append(r)
        if missing:
            _install_packages(missing)
    except Exception:
        pass


# NOTE: Auto-install is now offered interactively in __main__ before launching

def _offer_install_missing_requirements() -> None:
    """Interactively ask to install missing packages from requirements.txt.

    Uses a tiny hidden Tk root to show a yes/no dialog. Falls back silently if Tk
    is unavailable. Safe to call even if everything is installed.
    """
    try:
        req_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
        reqs = _parse_requirements_file(req_path)
        missing: List[str] = []
        for r in reqs:
            import_names = _req_to_import_names(r)
            if not any(_module_available(n) for n in import_names):
                missing.append(r)
        if not missing:
            return
        try:
            import tkinter as _tk
            from tkinter import messagebox as _mb
            root = _tk.Tk(); root.withdraw()
            msg = "Bazı paketler eksik:\n\n  " + "\n  ".join(missing) + "\n\nŞimdi yüklemek ister misin?"
            if _mb.askyesno("Eksik paketler", msg):
                _install_packages(missing)
            try:
                root.destroy()
            except Exception:
                pass
        except Exception:
            # If Tk not available, skip interactivity
            pass
    except Exception:
        pass

try:
    from deep_translator import GoogleTranslator, MyMemoryTranslator
    try:
        from deep_translator.exceptions import TooManyRequests  # type: ignore
    except Exception:
        TooManyRequests = None  # type: ignore
    try:
        # Optional engines; may require API key or base URL
        from deep_translator import DeeplTranslator, LibreTranslator  # type: ignore
    except Exception:
        DeeplTranslator = None  # type: ignore
        LibreTranslator = None  # type: ignore
    # Optional: Selenium for DeepL Web automation
    try:
        from selenium import webdriver  # type: ignore
        from selenium.webdriver.common.by import By  # type: ignore
        from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
        from selenium.webdriver.support import expected_conditions as EC  # type: ignore
        try:
            from selenium.webdriver.chrome.options import Options as ChromeOptions  # type: ignore
        except Exception:
            ChromeOptions = None  # type: ignore
        try:
            from webdriver_manager.chrome import ChromeDriverManager  # type: ignore
        except Exception:
            ChromeDriverManager = None  # type: ignore
    except Exception:
        webdriver = None  # type: ignore
        By = None  # type: ignore
        WebDriverWait = None  # type: ignore
        EC = None  # type: ignore
        ChromeOptions = None  # type: ignore
        ChromeDriverManager = None  # type: ignore
except Exception as import_error:  # pragma: no cover
    try:
        _install_packages(["deep-translator"])  # attempt auto-install
        from deep_translator import GoogleTranslator, MyMemoryTranslator
        try:
            from deep_translator.exceptions import TooManyRequests  # type: ignore
        except Exception:
            TooManyRequests = None  # type: ignore
        try:
            from deep_translator import DeeplTranslator, LibreTranslator  # type: ignore
        except Exception:
            DeeplTranslator = None  # type: ignore
            LibreTranslator = None  # type: ignore
        # Try to install selenium if not present
        try:
            if webdriver is None:
                _install_packages(["selenium", "webdriver-manager"])  # best-effort
                from selenium import webdriver  # type: ignore
                from selenium.webdriver.common.by import By  # type: ignore
                from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
                from selenium.webdriver.support import expected_conditions as EC  # type: ignore
                from selenium.webdriver.chrome.options import Options as ChromeOptions  # type: ignore
                from webdriver_manager.chrome import ChromeDriverManager  # type: ignore
        except Exception:
            webdriver = None  # type: ignore
    except Exception:
        print("Dependency missing: deep-translator. Install it with:\n  py -m pip install --user deep-translator", file=sys.stderr)
        raise


# SRT and VTT timestamp patterns
TIMESTAMP_SRT = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}$")
TIMESTAMP_VTT = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}.*$")


def is_sequence_number(line: str) -> bool:
    return line.strip().isdigit()


def is_timestamp(line: str) -> bool:
    s = line.strip()
    return bool(TIMESTAMP_SRT.match(s) or TIMESTAMP_VTT.match(s))


def is_vtt_meta(line: str) -> bool:
    s = line.strip()
    if s == "":
        return False
    head = s.split()[0].upper()
    return head in {"WEBVTT", "NOTE", "STYLE", "REGION"}


def split_whitespace(line: str) -> Tuple[str, str, str]:
    """Return (leading_ws, core, trailing_ws)."""
    leading_len = len(line) - len(line.lstrip(" \t"))
    trailing_len = len(line) - len(line.rstrip(" \t"))
    leading = line[:leading_len]
    trailing = line[len(line) - trailing_len:] if trailing_len else ""
    core = line[leading_len: len(line) - trailing_len if trailing_len else len(line)]
    return leading, core, trailing


def chunk(items: List[str], size: int) -> List[List[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def looks_turkish(text: str) -> bool:
    turkish_chars = set("çğıöşüÇĞİÖŞÜ")
    return any(ch in turkish_chars for ch in text)

def _count_words(text: str) -> int:
    try:
        # Simple heuristic: split on whitespace; robust and fast for progress needs
        return len((text or "").split())
    except Exception:
        return 0

# Robust text reading for legacy encodings (UTF-8, UTF-8 BOM, CP1254, Latin-1)
def _read_lines_robust(path: str) -> List[str]:
    for enc in ("utf-8", "utf-8-sig", "cp1254", "latin-1"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                return f.readlines()
        except UnicodeDecodeError:
            continue
        except Exception:
            break
    # Last resort raw bytes decode latin-1 to preserve bytes mapping
    try:
        with open(path, "rb") as f:
            data = f.read()
        return data.decode("latin-1", errors="replace").splitlines(True)
    except Exception:
        return []

# ---- PDF font helpers for proper Turkish glyphs ----
_PDF_FONT_NAME = None  # type: ignore

def _find_existing_file(paths: List[str]) -> Optional[str]:
    for p in paths:
        try:
            if p and os.path.isfile(p):
                return p
        except Exception:
            pass

        
    return None

def _register_pdf_unicode_font() -> Optional[str]:
    global _PDF_FONT_NAME
    if _PDF_FONT_NAME:
        return _PDF_FONT_NAME
    if 'pdfmetrics' not in globals() or pdfmetrics is None or TTFont is None:
        return None
    candidates: List[Tuple[str, List[str]]] = [
        ("DejaVuSans", [
            os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf"),
            os.path.join(os.environ.get("WINDIR", r"C:\\Windows"), "Fonts", "DejaVuSans.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]),
        ("ArialUnicode", [os.path.join(os.environ.get("WINDIR", r"C:\\Windows"), "Fonts", "arialuni.ttf")]),
        ("Arial", [os.path.join(os.environ.get("WINDIR", r"C:\\Windows"), "Fonts", "arial.ttf")]),
        ("SegoeUI", [os.path.join(os.environ.get("WINDIR", r"C:\\Windows"), "Fonts", "segoeui.ttf")]),
    ]
    for fname, paths in candidates:
        fpath = _find_existing_file(paths)
        if not fpath:
            continue
        try:
            pdfmetrics.registerFont(TTFont(fname, fpath))  # type: ignore
            _PDF_FONT_NAME = fname
            return _PDF_FONT_NAME
        except Exception:
            continue
    return None

# --- NEW: language detection using langdetect (optional) ---
try:
    from langdetect import detect as _ld_detect  # type: ignore
except Exception:
    _ld_detect = None

def detect_language(text: str) -> Optional[str]:
    try:
        if _ld_detect is None:
            return None
        sample = (text or "").strip()
        if not sample:
            return None
        # langdetect can throw; protect
        return _ld_detect(sample)
    except Exception:
        return None


def _map_lang_for_mymemory(target_lang: str) -> str:
    # Minimal mapper for MyMemory codes
    if target_lang.lower().startswith("tr"):
        return "tr-TR"
    if target_lang.lower().startswith("en"):
        return "en-GB"
    if target_lang.lower().startswith("de"):
        return "de-DE"
    if target_lang.lower().startswith("fr"):
        return "fr-FR"
    if target_lang.lower().startswith("es"):
        return "es-ES"
    if target_lang.lower().startswith("it"):
        return "it-IT"
    if target_lang.lower().startswith("ru"):
        return "ru-RU"
    return "tr-TR"


def translate_lines(
    lines: List[str],
    target_lang: str = "tr",
    batch_size: int = 100,
    mm_workers: int = 6,
    engine_mode: str = "auto",
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    auto_priority: str = "google_first",
    wrap_limit: int = 0,
) -> List[str]:
    """Translate SRT/VTT-like content lines to target_lang.

    - Preserves timestamps, sequence numbers, and whitespace.
    - Uses unified translation map builder (dedupe, batching, engine selection).
    - Supports optional progress callback and cancellation.
    """
    # Identify translatable lines (exclude sequence numbers, timestamps, blanks)
    to_translate_indices: List[int] = []
    cores: List[str] = []
    for idx, line in enumerate(lines):
        stripped = line.strip("\r\n")
        if stripped == "" or is_sequence_number(stripped) or is_timestamp(stripped) or is_vtt_meta(stripped):
            continue
        leading, core, trailing = split_whitespace(stripped)
        if core:
            to_translate_indices.append(idx)
            cores.append(core)

    if not to_translate_indices:
        return lines

    translated_map = _build_translation_map(
        cores,
        target_lang=target_lang,
        batch_size=batch_size,
        mm_workers=mm_workers,
        engine_mode=engine_mode,
        auto_priority=auto_priority,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )

    # Reconstruct lines with preserved whitespace and line-endings
    result = list(lines)
    def _soft_wrap(text: str, limit: int) -> str:
        try:
            if limit <= 0 or len(text) <= limit:
                return text
            words = text.split()
            out_lines = []
            cur = ""
            for w in words:
                add = (w if not cur else (" " + w))
                if len(cur) + len(add) <= limit:
                    cur += add
                else:
                    out_lines.append(cur)
                    cur = w
            if cur:
                out_lines.append(cur)
            return "\n".join(out_lines)
        except Exception:
            return text

    for idx in to_translate_indices:
        stripped = lines[idx].strip("\r\n")
        leading, core, trailing = split_whitespace(stripped)
        translated_core = translated_map.get(core, core)
        if wrap_limit and translated_core:
            translated_core = _soft_wrap(translated_core, wrap_limit)
        rebuilt = f"{leading}{translated_core}{trailing}"
        suffix = "\r\n" if lines[idx].endswith("\r\n") else ("\n" if lines[idx].endswith("\n") else "")
        result[idx] = rebuilt + suffix
    return result


def _cli_main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "--build-ui-json":
        # optional arg: comma-separated language codes
        codes_arg = sys.argv[2] if len(sys.argv) > 2 else "tr,de,fr,es,it,ru,ar,pt,ja,ko,zh-CN,zh-TW"
        codes = [c.strip() for c in codes_arg.split(",") if c.strip()]
        _ensure_ui_json_has_all_texts(codes)
        print(f"ui_translations.json updated for: {', '.join(codes)}")
        return
    if len(sys.argv) < 3:
        # No args → Launch GUI instead of exiting
        launch_gui()
        return

    input_path = sys.argv[1]
    output_path = sys.argv[2]
    target_lang = sys.argv[3] if len(sys.argv) > 3 else "tr"

    # Read preserving newlines
    with open(input_path, "r", encoding="utf-8", newline="") as f:
        lines = f.readlines()

    # Simple CLI progress
    last_pct = -1
    start_ts = time.time()
    def _progress(done: int, total: int) -> None:
        nonlocal last_pct
        pct = int(0 if total == 0 else (done * 100) / total)
        if pct != last_pct:
            last_pct = pct
            elapsed = time.time() - start_ts
            rate = done / elapsed if elapsed > 0 else 0
            remaining = (total - done) / rate if rate > 0 else 0
            print(f"Progress: {pct}%  ETA: {int(remaining)}s", file=sys.stderr)

    translated = translate_lines(lines, target_lang=target_lang, progress_callback=_progress, engine_mode="auto")

    # Write with UTF-8 BOM to improve Windows player compatibility
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        f.writelines(translated)

    print(f"Wrote: {output_path}")

    # Report any lines that still look untranslated so failures are visible
    # instead of silently shipping English text.
    unresolved = []
    for i, (src_line, dst_line) in enumerate(zip(lines, translated)):
        s = src_line.strip("\r\n")
        d = dst_line.strip("\r\n")
        if s == "" or is_sequence_number(s) or is_timestamp(s) or is_vtt_meta(s):
            continue
        if s == d and re.search(r"[A-Za-z]{2,}", s):
            unresolved.append((i + 1, s))
    if unresolved:
        print(f"Warning: {len(unresolved)} line(s) may still be untranslated:", file=sys.stderr)
        for ln, txt in unresolved[:50]:
            print(f"  line {ln}: {txt}", file=sys.stderr)


# -------------------- GUI --------------------
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from tkinter import font as tkfont
    # Optional drag&drop support
    try:
        from tkinterdnd2 import TkinterDnD, DND_FILES  # type: ignore
    except Exception:  # pragma: no cover
        TkinterDnD = None  # type: ignore
        DND_FILES = None  # type: ignore
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore
    filedialog = None  # type: ignore
    messagebox = None  # type: ignore
    TkinterDnD = None  # type: ignore
    DND_FILES = None  # type: ignore

# ttkbootstrap is intentionally not used: the app ships its own design system (_apply_design)
TBStyle = None  # type: ignore

# Optional format handlers
try:
    from docx import Document as DocxDocument  # type: ignore
except Exception:
    DocxDocument = None  # type: ignore

try:
    from pdfminer.high_level import extract_text as pdf_extract_text  # type: ignore
except Exception:
    pdf_extract_text = None  # type: ignore

try:
    from reportlab.pdfgen import canvas as rl_canvas  # type: ignore
    from reportlab.lib.pagesizes import A4  # type: ignore
    from reportlab.lib.units import mm  # type: ignore
    try:
        from reportlab.pdfbase import pdfmetrics  # type: ignore
        from reportlab.pdfbase.ttfonts import TTFont  # type: ignore
    except Exception:
        pdfmetrics = None  # type: ignore
        TTFont = None  # type: ignore
except Exception:
    rl_canvas = None  # type: ignore
    A4 = None  # type: ignore
    mm = None  # type: ignore

# Optional docx2txt for robust fallback extraction
try:
    import docx2txt  # type: ignore
except Exception:
    docx2txt = None  # type: ignore


# code -> English display name, filled from the translator's supported-language list
_LANG_NAMES_EN: Dict[str, str] = {}


def _get_supported_langs(ui_code: Optional[str] = None) -> Dict[str, str]:
    """Return mapping of 'Language Name' → 'code' for GoogleTranslator.
    Fallback to a curated subset if discovery fails.
    """
    try:
        # get_supported_languages is an instance method (calling it on the class raised
        # TypeError and silently fell back to 37 languages).
        langs = GoogleTranslator(source="auto", target="en").get_supported_languages(as_dict=True)
        if isinstance(langs, dict) and langs:
            # deep_translator returns {"english name": "code"}; older versions the reverse.
            k0, v0 = next(iter(langs.items()))
            name_to_code = langs if len(str(v0)) <= len(str(k0)) else {v: k for k, v in langs.items()}
            result = {}
            for name, code in name_to_code.items():
                pretty = " ".join(w if w.startswith("(") else w.capitalize() for w in str(name).split())
                pretty = re.sub(r"\((\w)", lambda m: "(" + m.group(1).upper(), pretty)
                result[pretty] = str(code)
                _LANG_NAMES_EN.setdefault(str(code), pretty)
            if len(result) > 50:
                return result
    except Exception:
        pass
    # Fallback common languages
    # Return English names if UI language is not Turkish; else Turkish names
    try:
        # Prefer explicitly provided ui_code; then current runtime; then settings; then OS/ENV; default 'en'
        ui_code_fb = ui_code
        if not ui_code_fb:
            try:
                if '_CURRENT_UI_LANG_CODE' in globals() and globals().get('_CURRENT_UI_LANG_CODE'):
                    ui_code_fb = globals().get('_CURRENT_UI_LANG_CODE')
            except Exception:
                pass
        if not ui_code_fb and os.path.exists(_SETTINGS_FILE):
            with open(_SETTINGS_FILE, "r", encoding="utf-8") as _rf_set_fb:
                _cfg_set_fb = json.load(_rf_set_fb) or {}
            ui_code_fb = _cfg_set_fb.get("ui_lang_code")
        if not ui_code_fb:
            try:
                import locale
                loc = None
                try:
                    loc_tuple = locale.getdefaultlocale()
                    if isinstance(loc_tuple, (list, tuple)) and loc_tuple and loc_tuple[0]:
                        loc = loc_tuple[0]
                except Exception:
                    pass
                if not loc:
                    loc = os.environ.get("LC_ALL") or os.environ.get("LANG") or "en"
                ui_code_fb = str(loc)
            except Exception:
                ui_code_fb = "en"
        ui_code_fb = str(ui_code_fb or "en")
    except Exception:
        ui_code_fb = "en"

    if str(ui_code_fb).lower().startswith("tr"):
        # Turkish display names → code
        return {
            "Türkçe": "tr",
            "İngilizce": "en",
            "Almanca": "de",
            "Fransızca": "fr",
            "İspanyolca": "es",
            "İtalyanca": "it",
            "Rusça": "ru",
            "Arapça": "ar",
            "Portekizce": "pt",
            "Hollandaca": "nl",
            "İsveççe": "sv",
            "Lehçe": "pl",
            "Ukraynaca": "uk",
            "Bulgarca": "bg",
            "Yunanca": "el",
            "Farsça": "fa",
            "Hintçe": "hi",
            "Japonca": "ja",
            "Korece": "ko",
            "Çince (Basitleştirilmiş)": "zh-CN",
            "Çince (Geleneksel)": "zh-TW",
            "Çekçe": "cs",
            "Romence": "ro",
            "Macarca": "hu",
            "Endonezce": "id",
            "Tayca": "th",
            "Vietnamca": "vi",
            "Hırvatça": "hr",
            "Slovakça": "sk",
            "Danca": "da",
            "Fince": "fi",
            "Norveççe": "no",
            "Sırpça": "sr",
            "Litvanca": "lt",
            "Letonca": "lv",
            "Estonca": "et",
            "Slovence": "sl",
        }
    else:
        # English display names → code
        return {
            "English": "en",
            "Turkish": "tr",
            "German": "de",
            "French": "fr",
            "Spanish": "es",
            "Italian": "it",
            "Russian": "ru",
            "Arabic": "ar",
            "Portuguese": "pt",
            "Dutch": "nl",
            "Swedish": "sv",
            "Polish": "pl",
            "Ukrainian": "uk",
            "Bulgarian": "bg",
            "Greek": "el",
            "Persian": "fa",
            "Hindi": "hi",
            "Japanese": "ja",
            "Korean": "ko",
            "Chinese (Simplified)": "zh-CN",
            "Chinese (Traditional)": "zh-TW",
            "Czech": "cs",
            "Romanian": "ro",
            "Hungarian": "hu",
            "Indonesian": "id",
            "Thai": "th",
            "Vietnamese": "vi",
            "Croatian": "hr",
            "Slovak": "sk",
            "Danish": "da",
            "Finnish": "fi",
            "Norwegian": "no",
            "Serbian": "sr",
            "Lithuanian": "lt",
            "Latvian": "lv",
            "Estonian": "et",
            "Slovene": "sl",
        }

_UI_CACHE_FILE = os.path.join(os.path.dirname(__file__), "ui_translations.json")
_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")
_BUILTIN_UI: Dict[str, Dict[str, str]] = {}
_CURRENT_UI_LANG_CODE: Optional[str] = None

# ---- UI language packs: loaded once, reloaded only when the file changes ----
_UI_PACKS_CACHE: Dict[str, object] = {"mtime": None, "data": {}}
_UI_AFFIX_RE = re.compile(r"^([^\w(\[]*)(.*?)(\s*)$", re.S)

# Native names (autonyms) for the UI-language picker, so users can find their language
UI_LANG_AUTONYMS: Dict[str, str] = {
    "ar": "العربية", "bg": "Български", "cs": "Čeština", "da": "Dansk", "de": "Deutsch",
    "el": "Ελληνικά", "en": "English", "es": "Español", "et": "Eesti", "fa": "فارسی",
    "fi": "Suomi", "fr": "Français", "hi": "हिन्दी", "hr": "Hrvatski", "hu": "Magyar",
    "id": "Bahasa Indonesia", "it": "Italiano", "ja": "日本語", "ko": "한국어", "lt": "Lietuvių",
    "lv": "Latviešu", "nl": "Nederlands", "no": "Norsk", "pl": "Polski", "pt": "Português",
    "ro": "Română", "ru": "Русский", "sk": "Slovenčina", "sl": "Slovenščina", "sr": "Српски",
    "sv": "Svenska", "th": "ไทย", "tr": "Türkçe", "uk": "Українська", "vi": "Tiếng Việt",
    "zh-CN": "简体中文", "zh-TW": "繁體中文",
}


# UI strings that reach _tr() through variables (tooltips, menus, engine list, status words).
# tools/i18n_sync.py extracts these together with every literal _tr("...") call.
UI_EXTRA_KEYS: List[str] = [
    "Remove missing", "Preview", "Open selected output", "Open selected out folder", "Reveal in Explorer",
    "Advanced settings...", "Type to filter by filename", "Auto",
    "Google first, MyMemory as fallback", "Google Translate (no key)", "MyMemory (no key, small daily quota)",
    "DeepL API (requires API key)", "DeepL website automation (experimental)", "LibreTranslate (self-hosted or API key)",
    "Start translation (Ctrl+R)", "Cancel (Esc)", "Translate only the selected files (Ctrl+Shift+R)",
    "Add files (Ctrl+O)", "Remove selected files from the list",
    "Add...", "Output settings...", "Preferences...", "Compact mode", "Font size", "About", "Exit",
    "Translating", "Completed", "Canceled", "Skipped", "Skipped (same language)", "Error", "Translation failed",
    "Unsupported extension", "Light mode", "Dark mode", "Blue", "Purple", "Green", "Orange", "Pink", "Teal",
    "Words", "Elapsed", "Remaining", "s", "Theme:", "Accent color:", "UI language:", "Settings",
    # Settings dialog (labels/options reach _tr through _labeled / _keyed_combo)
    "Appearance", "Translation", "Output", "Dictionary", "Engine:", "Engine selection: auto/google/mymemory.",
    "Auto priority:", "Auto priority decides which engine is tried first in auto mode.", "Google first", "MyMemory first",
    "Batch size (Google batch):", "Batch: how many unique lines are sent to Google at once.",
    "Fallback concurrent jobs (MyMemory):", "MyMemory concurrent jobs: number of lines translated in parallel (fallback).",
    "Output directory:", "PDF output as:", "Custom dictionary:", "Dictionary mode: off/pre/post/both.",
    "Off", "Before translation", "After translation", "Both", "File",
]


_LANG_NAMES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lang_names.json")
_LANG_NAMES_CACHE: Dict[str, object] = {"mtime": None, "data": {}}


def _lang_names_for(ui_code: str) -> Dict[str, str]:
    """Localized target-language names for a UI language (built by tools/i18n_sync.py --lang-names)."""
    try:
        mtime = os.path.getmtime(_LANG_NAMES_FILE)
        if _LANG_NAMES_CACHE["mtime"] != mtime:
            with open(_LANG_NAMES_FILE, "r", encoding="utf-8") as rf:
                _LANG_NAMES_CACHE["data"] = json.load(rf) or {}
            _LANG_NAMES_CACHE["mtime"] = mtime
        data = _LANG_NAMES_CACHE["data"]
        return data.get(ui_code) or data.get(str(ui_code).split("-")[0]) or {}  # type: ignore[union-attr]
    except Exception:
        return {}

def _load_ui_packs() -> Dict[str, Dict[str, str]]:
    """Return ui_translations.json as a dict, parsing it only when the file changes."""
    try:
        mtime = os.path.getmtime(_UI_CACHE_FILE)
    except OSError:
        return {}
    if _UI_PACKS_CACHE["mtime"] != mtime:
        try:
            with open(_UI_CACHE_FILE, "r", encoding="utf-8") as rf:
                data = json.load(rf) or {}
        except Exception:
            data = {}
        _UI_PACKS_CACHE["data"] = data if isinstance(data, dict) else {}
        _UI_PACKS_CACHE["mtime"] = mtime
    return _UI_PACKS_CACHE["data"]  # type: ignore[return-value]


def _ui_pack_for(code: str) -> Dict[str, str]:
    packs = _load_ui_packs()
    pack = packs.get(code) or packs.get(code.split("-")[0])
    if not pack:
        base = code.split("-")[0]
        pack = next((v for k, v in packs.items() if k.split("-")[0] == base), None)
    return pack if isinstance(pack, dict) else {}


def _ui_translate(text: str, code: str) -> str:
    """Translate a UI string. Leading icons/emoji and surrounding spaces are kept as-is, so
    "📂 Add..." is looked up as "Add..." and returned as "📂 <translation>"."""
    if not text or code == "en":
        return text
    pack = _ui_pack_for(code)
    hit = pack.get(text)
    if hit:
        return hit
    m = _UI_AFFIX_RE.match(text)
    if m and m.group(2):
        hit = pack.get(m.group(2))
        if hit:
            return f"{m.group(1)}{hit}{m.group(3)}"
    return text

# Optional API credentials (read from env and settings.json if present)
_DEEPL_API_KEY: Optional[str] = os.environ.get("DEEPL_API_KEY")
_LIBRE_URL: Optional[str] = os.environ.get("LIBRE_URL") or os.environ.get("LIBRE_API_URL")
_LIBRE_API_KEY: Optional[str] = os.environ.get("LIBRE_API_KEY")
try:
    if os.path.exists(_SETTINGS_FILE):
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as _rf_set:
            _cfg_set = json.load(_rf_set) or {}
        _DEEPL_API_KEY = _cfg_set.get("deepl_api_key", _DEEPL_API_KEY)
        _LIBRE_URL = _cfg_set.get("libre_url", _LIBRE_URL)
        _LIBRE_API_KEY = _cfg_set.get("libre_api_key", _LIBRE_API_KEY)
except Exception:
    pass

def _load_ui_base_texts() -> List[str]:
    """Load canonical UI text keys from ui_translations.json.
    Preference order: 'en' keys, else union of all language keys.
    Fallback to a minimal built-in set if file missing.
    """
    try:
        if os.path.exists(_UI_CACHE_FILE):
            with open(_UI_CACHE_FILE, "r", encoding="utf-8") as rf:
                data = json.load(rf) or {}
            if isinstance(data, dict):
                if isinstance(data.get("en"), dict) and data.get("en"):
                    return list(data["en"].keys())
                # union of all keys
                seen: Dict[str, bool] = {}
                keys: List[str] = []
                for lang_map in data.values():
                    if isinstance(lang_map, dict):
                        for k in lang_map.keys():
                            if k not in seen:
                                seen[k] = True
                                keys.append(k)
                if keys:
                    return keys
    except Exception:
        pass
    # Minimal fallback
    return [
        "Files","Add...","Remove","Clear","File","Status","Target language:",
        "Preview","Output","Start","Cancel","Dark theme","UI language:",
    ]

# Base UI texts list populated from ui_translations.json
_UI_BASE_TEXTS: List[str] = _load_ui_base_texts()

def _get_ui_langs_from_json() -> Dict[str, str]:
    """Return mapping of 'Language Name' → 'code' taken from ui_translations.json top-level keys.
    Falls back to at least English if file missing or malformed.
    """
    try:
        disk: Dict[str, Dict[str, str]] = {}
        if os.path.exists(_UI_CACHE_FILE):
            with open(_UI_CACHE_FILE, "r", encoding="utf-8") as rf:
                disk = json.load(rf) or {}
        if not isinstance(disk, dict):
            return {"English": "en"}
        # Build code->name map from supported langs, then map JSON codes to display names
        name_to_code = _get_supported_langs()
        code_to_name = {c: n for n, c in name_to_code.items()}
        # Display names for UI language list
        display_names_tr: Dict[str, str] = {
            "en": "İngilizce",
            "tr": "Türkçe",
            "es": "İspanyolca",
            "de": "Alman",
            "fr": "Fransızca",
            "it": "İtalyanca",
            "pt": "Portekizce",
            "nl": "Hollandaca",
            "sv": "İsveççe",
            "pl": "Lehçe",
            "ru": "Rusça",
            "uk": "Ukraynaca",
            "bg": "Bulgarca",
            "el": "Yunanca",
            "ar": "Arapça",
            "fa": "Farsça",
            "hi": "Hintçe",
            "ja": "Japonca",
            "ko": "Korece",
            "zh-CN": "Çince (Basitleştirilmiş)",
            "zh-TW": "Çince (Geleneksel)",
            "cs": "Çekçe",
            "ro": "Romence",
            "hu": "Macarca",
            "id": "Endonezce",
            "th": "Tayca",
            "vi": "Vietnamca",
            "hr": "Hırvatça",
            "sk": "Slovakça",
            "da": "Danca",
            "fi": "Fince",
            "no": "Norveççe",
            "sr": "Sırpça",
            "lt": "Litvanca",
            "lv": "Letonca",
            "et": "Estonca",
            "sl": "Slovence",
        }
        # Determine preferred display language for UI language list
        try:
            ui_code_fb2 = "en"
            if os.path.exists(_SETTINGS_FILE):
                with open(_SETTINGS_FILE, "r", encoding="utf-8") as _rf_set2:
                    _cfg_set2 = json.load(_rf_set2) or {}
                ui_code_fb2 = str(_cfg_set2.get("ui_lang_code") or "en")
        except Exception:
            ui_code_fb2 = "en"

        prefer_tr_names = str(ui_code_fb2).lower().startswith("tr")

        result: Dict[str, str] = {}
        for code, mapping in disk.items():
            if not isinstance(mapping, dict):
                continue
            lang_only = str(code).split("-")[0]
            # Choose display label based on preferred language
            name = None
            if prefer_tr_names:
                name = display_names_tr.get(code) or display_names_tr.get(lang_only)
                if not name:
                    name = code_to_name.get(code) or code_to_name.get(lang_only)
            else:
                name = code_to_name.get(code) or code_to_name.get(lang_only)
                if not name:
                    name = display_names_tr.get(code) or display_names_tr.get(lang_only)
            if not name:
                lc = str(code).lower()
                if lc in ("zh-cn", "zh_sg", "zh-hans"):
                    name = "Chinese (Simplified)"
                elif lc in ("zh-tw", "zh-hk", "zh-hant"):
                    name = "Chinese (Traditional)"
                else:
                    # Fallback: show code itself
                    name = str(code)
            result[name] = str(code)
        # Sort by display name for nicer UI
        if result:
            return {k: result[k] for k in sorted(result.keys(), key=lambda s: s.casefold())}
        return {"English": "en"}
    except Exception:
        return {"English": "en"}

def _localize_lang_name(code: str, ui_code: str) -> str:
    """Return localized display name for a language code, using ui_translations.json if possible.
    Fallback to English names or the code itself.
    """
    try:
        # Base English names by code
        name_en_map = {
            "en": "English", "tr": "Turkish", "es": "Spanish", "de": "German", "fr": "French",
            "it": "Italian", "pt": "Portuguese", "nl": "Dutch", "sv": "Swedish", "pl": "Polish",
            "ru": "Russian", "uk": "Ukrainian", "bg": "Bulgarian", "el": "Greek", "ar": "Arabic",
            "fa": "Persian", "hi": "Hindi", "ja": "Japanese", "ko": "Korean",
            "zh-CN": "Chinese (Simplified)", "zh-TW": "Chinese (Traditional)", "cs": "Czech", "ro": "Romanian",
            "hu": "Hungarian", "id": "Indonesian", "th": "Thai", "vi": "Vietnamese", "hr": "Croatian",
            "sk": "Slovak", "da": "Danish", "fi": "Finnish", "no": "Norwegian", "sr": "Serbian",
            "lt": "Lithuanian", "lv": "Latvian", "et": "Estonian", "sl": "Slovene",
        }
        base = name_en_map.get(code) or _LANG_NAMES_EN.get(code) or _lang_names_for("en").get(code) or code
        # Quick built-in localization for some UI languages
        ui = (ui_code or "en").lower()
        if ui.startswith("en"):
            # Explicit English mapping (ensures consistent casing/labels)
            en_map = {
                "en": "English", "tr": "Turkish", "es": "Spanish", "de": "German", "fr": "French",
                "it": "Italian", "pt": "Portuguese", "nl": "Dutch", "sv": "Swedish", "pl": "Polish",
                "ru": "Russian", "uk": "Ukrainian", "bg": "Bulgarian", "el": "Greek", "ar": "Arabic",
                "fa": "Persian", "hi": "Hindi", "ja": "Japanese", "ko": "Korean",
                "zh-CN": "Chinese (Simplified)", "zh-TW": "Chinese (Traditional)", "cs": "Czech", "ro": "Romanian",
                "hu": "Hungarian", "id": "Indonesian", "th": "Thai", "vi": "Vietnamese", "hr": "Croatian",
                "sk": "Slovak", "da": "Danish", "fi": "Finnish", "no": "Norwegian", "sr": "Serbian",
                "lt": "Lithuanian", "lv": "Latvian", "et": "Estonian", "sl": "Slovene",
            }
            return en_map.get(code, base)
        if ui.startswith("tr"):
            tr_map = {
                "en": "İngilizce", "tr": "Türkçe", "es": "İspanyolca", "de": "Almanca", "fr": "Fransızca",
                "it": "İtalyanca", "pt": "Portekizce", "nl": "Felemenkçe", "sv": "İsveççe", "pl": "Lehçe",
                "ru": "Rusça", "uk": "Ukraynaca", "bg": "Bulgarca", "el": "Yunanca", "ar": "Arapça",
                "fa": "Farsça", "hi": "Hintçe", "ja": "Japonca", "ko": "Korece",
                "zh-CN": "Çince (Basitleştirilmiş)", "zh-TW": "Çince (Geleneksel)", "cs": "Çekçe", "ro": "Rumence",
                "hu": "Macarca", "id": "Endonezce", "th": "Tayca", "vi": "Vietnamca", "hr": "Hırvatça",
                "sk": "Slovakça", "da": "Danca", "fi": "Fince", "no": "Norveççe", "sr": "Sırpça",
                "lt": "Litvanca", "lv": "Letonca", "et": "Estonca", "sl": "Slovence",
                "az": "Azerice", "kk": "Kazakça", "ky": "Kırgızca", "uz": "Özbekçe", "tk": "Türkmence",
                "tt": "Tatarca", "ug": "Uygurca", "ku": "Kürtçe (Kurmanci)", "ckb": "Kürtçe (Sorani)",
                "sq": "Arnavutça", "bs": "Boşnakça", "mk": "Makedonca", "ka": "Gürcüce", "hy": "Ermenice",
                "iw": "İbranice", "he": "İbranice", "ur": "Urduca", "bn": "Bengalce", "pa": "Pencapça",
                "ta": "Tamilce", "ms": "Malayca", "tl": "Filipince", "sw": "Svahili", "so": "Somalice",
                "am": "Amharca", "ca": "Katalanca", "eu": "Baskça", "gl": "Galiçyaca", "is": "İzlandaca",
                "ga": "İrlandaca", "cy": "Galce", "af": "Afrikaanca", "la": "Latince", "eo": "Esperanto",
                "be": "Belarusça", "mt": "Maltaca", "mn": "Moğolca", "ne": "Nepalce", "ps": "Peştuca",
                "yi": "Yidiş", "lb": "Lüksemburgca",
            }
            return tr_map.get(code) or _lang_names_for("tr").get(code) or base
        # Other UI languages: generated names (lang_names.json), else English
        return _lang_names_for(ui_code).get(code) or base
    except Exception:
        return code

def _prebuild_ui_packs(codes: List[str]) -> None:
    try:
        base = _UI_BASE_TEXTS
        disk = {}
        if os.path.exists(_UI_CACHE_FILE):
            try:
                with open(_UI_CACHE_FILE, "r", encoding="utf-8") as rf:
                    disk = json.load(rf) or {}
            except Exception:
                disk = {}
        for code in codes:
            try:
                if code in disk:
                    # Skip if already present
                    continue
                tr = GoogleTranslator(source="en", target=code)
                res = tr.translate_batch(base)
                mapping = {src: dst for src, dst in zip(base, res)}
                disk[code] = mapping
            except Exception:
                continue
        if disk:
            try:
                with open(_UI_CACHE_FILE, "w", encoding="utf-8") as wf:
                    json.dump(disk, wf, ensure_ascii=False, indent=2)
            except Exception:
                pass
    except Exception:
        pass


def _collect_ui_texts_from_source() -> List[str]:
    """Scan this source file for UI texts used via _tr("...") or literal text="...".
    Returns a de-duplicated list of base English strings.
    """
    try:
        path = __file__
    except Exception:
        return list(_UI_BASE_TEXTS)
    try:
        with open(path, "r", encoding="utf-8") as rf:
            src = rf.read()
    except Exception:
        return list(_UI_BASE_TEXTS)
    texts: List[str] = []
    try:
        # _tr("...") and _tr('...')
        texts += re.findall(r"_tr\(\s*\"(.*?)\"\s*\)", src)
        texts += re.findall(r"_tr\(\s*'(.*?)'\s*\)", src)
        # text="..." literals in widget constructors
        texts += re.findall(r"text=\s*\"(.*?)\"", src)
        texts += re.findall(r"title\(\s*\"(.*?)\"\s*\)", src)
    except Exception:
        pass
    # Merge with base list and normalize order without duplicates
    merged = list(dict.fromkeys(list(_UI_BASE_TEXTS) + texts))
    return merged


def _ensure_ui_json_has_all_texts(codes: List[str]) -> None:
    """Ensure ui_translations.json contains translations for all discovered UI texts.
    - Loads disk JSON
    - Translates missing texts for given language codes (plus any codes already in disk)
    - Writes back merged result
    """
    try:
        base_texts = _collect_ui_texts_from_source()
        disk: Dict[str, Dict[str, str]] = {}
        if os.path.exists(_UI_CACHE_FILE):
            try:
                with open(_UI_CACHE_FILE, "r", encoding="utf-8") as rf:
                    disk = json.load(rf) or {}
            except Exception:
                disk = {}
        # include any existing language codes in disk
        all_codes = sorted(set((codes or [])) | set(disk.keys()))
        if not all_codes:
            all_codes = ["tr", "de", "fr", "es", "it", "ru", "ar", "pt", "ja", "ko", "zh-CN", "zh-TW"]
        for code in all_codes:
            try:
                current = dict(disk.get(code, {}))
                missing = [t for t in base_texts if t not in current]
                if not missing:
                    continue
                translated: Dict[str, str] = {}
                try:
                    tr = GoogleTranslator(source="en", target=code)
                    res = tr.translate_batch(missing)
                    translated = {src: dst for src, dst in zip(missing, res)}
                except Exception:
                    translated = {}
                still_missing = [t for t in missing if not translated.get(t)]
                if still_missing:
                    try:
                        mm = MyMemoryTranslator(source="en-GB", target=_map_lang_for_mymemory(code))
                        for t in still_missing:
                            try:
                                translated[t] = mm.translate(t)
                            except Exception:
                                translated[t] = t
                    except Exception:
                        for t in still_missing:
                            translated[t] = t
                current.update(translated)
                disk[code] = current
            except Exception:
                continue
        if disk:
            try:
                with open(_UI_CACHE_FILE, "w", encoding="utf-8") as wf:
                    json.dump(disk, wf, ensure_ascii=False, indent=2)
            except Exception:
                pass
    except Exception:
        pass

def _is_python_installed_on_system() -> bool:
    """Best-effort check: is a system Python available (outside this runtime)?"""
    try:
        import shutil
        # Common launchers/binaries
        for name in ("python", "python3", "py"):
            if shutil.which(name):
                return True
        # Windows registry check
        try:
            import winreg  # type: ignore
            for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(root, r"Software\\Python\\PythonCore") as key:
                        # If at least one subkey exists, assume installed
                        try:
                            sub = winreg.EnumKey(key, 0)
                            if sub:
                                return True
                        except OSError:
                            pass
                except OSError:
                    continue
        except Exception:
            pass
        # Try invoking py/python quickly
        try:
            import subprocess
            for cmd in (("py", "-V"), ("python", "--version"), ("python3", "--version")):
                try:
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1)
                    return True
                except Exception:
                    continue
        except Exception:
            pass
    except Exception:
        pass
    return False


def _maybe_open_python_download_once() -> None:
    """If system-wide Python is not installed, open the download page.

    - Does nothing when Python is present (normal case).
    - If not present, opens the official downloads page.
    - Persists a user opt-out flag `python_download_suppressed` if set externally.
    """
    try:
        # Respect a suppression flag if user set it in settings.json
        try:
            cfg = {}
            if os.path.exists(_SETTINGS_FILE):
                with open(_SETTINGS_FILE, "r", encoding="utf-8") as rf:
                    cfg = json.load(rf) or {}
            if bool(cfg.get("python_download_suppressed", False)):
                return
        except Exception:
            pass

        if _is_python_installed_on_system():
            return
        try:
            import webbrowser
            opened = webbrowser.open("https://www.python.org/downloads/")
            if not opened:
                webbrowser.open("https://www.google.com/search?q=python+download")
        except Exception:
            pass
    except Exception:
        pass


_BAD_TRANSLATION_MARKERS = (
    "error 500",
    "server error",
    "that's an error",
    "that\u2019s an error",
    "please try again later",
    "that's all we know",
    "that\u2019s all we know",
    "!!1500",
    "mymemory warning",
    "you used all available free translations",
    "we're sorry",
    "we\u2019re sorry",
    "automated queries",
    "<html",
    "</html>",
    "<!doctype",
)


def _is_bad_translation(dst: Optional[str], src: Optional[str] = None) -> bool:
    if dst is None or not isinstance(dst, str):
        return True
    s = dst.strip()
    if not s:
        return True
    low = s.lower()
    if any(marker in low for marker in _BAD_TRANSLATION_MARKERS):
        return True
    if "error" in low and "500" in low:
        return True
    return False


def _get_google_session():
    global _GOOGLE_SESSION
    if requests is None:
        return None
    if _GOOGLE_SESSION is None:
        sess = requests.Session()
        sess.headers.update({
            "User-Agent": _GOOGLE_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        _GOOGLE_SESSION = sess
    return _GOOGLE_SESSION


def _extract_google_mobile_result(html_text: str) -> Optional[str]:
    if not html_text:
        return None
    # Note: do NOT run _is_bad_translation() on the raw page here — every
    # normal translate.google.com/m response is a full HTML document
    # (starts with "<!doctype html><html ...>"), which would always match
    # the "<html"/"<!doctype" bad-translation markers and make this
    # function reject every response, success or failure alike. The
    # extracted text below is what actually gets validated by callers.
    if BeautifulSoup is not None:
        try:
            soup = BeautifulSoup(html_text, "html.parser")
            el = soup.find("div", class_="result-container") or soup.find("div", class_="t0")
            if el is not None:
                out = (el.get_text() or "").strip()
                return html_lib.unescape(out) if out else None
        except Exception:
            pass
    m = re.search(r'class="result-container"[^>]*>([^<]+)', html_text)
    if m:
        return html_lib.unescape(m.group(1)).strip()
    return None


def _google_translate_one_http(text: str, target_lang: str, attempts: int = 6) -> Optional[str]:
    sess = _get_google_session()
    if sess is None or not text or not str(text).strip() or _endpoint_blocked("google_m"):
        return None
    src = str(text).strip()
    last_status = None
    for attempt in range(attempts):
        try:
            with _GOOGLE_HTTP_LOCK:
                resp = sess.get(
                    "https://translate.google.com/m",
                    params={"sl": "auto", "tl": target_lang, "q": src, "hl": "en"},
                    timeout=25,
                )
                last_status = resp.status_code
                body = resp.text or ""
            if last_status == 429:
                # IP is rate-limited; retrying only burns ~1 min per line. Stop using /m for a while.
                _block_endpoint("google_m")
                return None
            if last_status != 200:
                time.sleep(min(15.0, 1.2 * (attempt + 1)))
                continue
            out = _extract_google_mobile_result(body)
            if out and not _is_bad_translation(out, src):
                return out
            # A 200 with a bad/blocked body (Google's soft rate-limit page)
            # is transient — back off longer than a plain retry so the
            # block window has a chance to clear.
            time.sleep(min(15.0, 1.5 * (attempt + 1)))
            continue
        except Exception:
            pass
        time.sleep(min(10.0, 0.8 * (attempt + 1)))
    return None


def _mymemory_translate_one_http(text: str, target_lang: str) -> Optional[str]:
    global _MYMEMORY_QUOTA_HIT
    if _MYMEMORY_QUOTA_HIT or requests is None:
        return None
    src = (text or "").strip()
    if not src:
        return None
    target_code = _map_lang_for_mymemory(target_lang)
    try:
        resp = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": src[:450], "langpair": f"en|{target_code.split('-')[0]}"},
            headers={"User-Agent": _GOOGLE_UA},
            timeout=20,
        )
        data = resp.json() if resp.content else {}
    except Exception:
        return None
    blob = json.dumps(data, ensure_ascii=False).lower() if data else ""
    if resp.status_code == 429 or "mymemory warning" in blob or "you used all available" in blob:
        _MYMEMORY_QUOTA_HIT = True
        return None
    try:
        out = (data.get("responseData") or {}).get("translatedText")
    except Exception:
        out = None
    if out and not _is_bad_translation(out, src):
        return str(out).strip()
    return None


def _mm_translate_via_client(mymemory_obj, text: str) -> Optional[str]:
    """Translate one text with a deep_translator MyMemoryTranslator instance.

    Bails out immediately once the shared daily quota is known to be
    exhausted instead of burning several seconds of retries per line on a
    call that cannot possibly succeed.
    """
    global _MYMEMORY_QUOTA_HIT
    if _MYMEMORY_QUOTA_HIT:
        return None
    for attempt in range(5):
        try:
            _API_SEM.acquire()
            try:
                out = mymemory_obj.translate(text)
            finally:
                _API_SEM.release()
            if not _is_bad_translation(out, text):
                return out
            return None
        except Exception as e:
            if TooManyRequests is not None and isinstance(e, TooManyRequests):
                _MYMEMORY_QUOTA_HIT = True
                return None
            if "mymemory" in str(e).lower() and "available" in str(e).lower():
                _MYMEMORY_QUOTA_HIT = True
                return None
        time.sleep(0.6 * (attempt + 1))
    return None


def _google_translate_batch_safe(
    google,
    texts_batch: List[str],
    cancel_check: Optional[Callable[[], bool]] = None,
    target_lang: str = "tr",
) -> List[Optional[str]]:
    results: List[Optional[str]] = [None] * len(texts_batch)
    if not texts_batch:
        return results
    for idx, src in enumerate(texts_batch):
        if cancel_check and cancel_check():
            break
        out = _google_translate_one_http(src, target_lang)
        if out is None and google is not None and not _endpoint_blocked("google_m"):
            try:
                one = google.translate(src)
                if not _is_bad_translation(one, src):
                    out = one
            except Exception:
                out = None
        if out is None:
            out = _mymemory_translate_one_http(src, target_lang)
        results[idx] = out
        if not _endpoint_blocked("google_m"):
            time.sleep(0.12)
    return results


# ---- Fast path: Google's JSON endpoint, many lines per request ----------------------------
# translate.google.com/m (HTML scraping, one request per line) gets IP-blocked with HTTP 429
# for hours after a few hundred requests; each blocked line then cost ~56 s of retries, so a
# film took ~22 h and the progress bar did not move. The gtx JSON endpoint takes a whole block
# of lines in one request (~10 requests per film) and keeps working while /m is blocked.
_GTX_URL = "https://translate.googleapis.com/translate_a/single"
_GTX_MAX_CHARS = 3800
_GTX_MAX_LINES = 120
_BLOCKED_UNTIL: Dict[str, float] = {}   # endpoint -> time.time() until which we do not call it


def _endpoint_blocked(name: str) -> bool:
    return time.time() < _BLOCKED_UNTIL.get(name, 0.0)


def _block_endpoint(name: str, seconds: float = 600.0) -> None:
    _BLOCKED_UNTIL[name] = time.time() + seconds


def _gtx_request(block: str, target_lang: str) -> Optional[str]:
    """One request for a newline-joined block. Returns the translated block or None."""
    if requests is None or _endpoint_blocked("gtx"):
        return None
    for attempt in range(3):
        try:
            resp = requests.post(
                _GTX_URL,
                params={"client": "gtx", "sl": "auto", "tl": target_lang, "dt": "t"},
                data={"q": block},
                headers={"User-Agent": _GOOGLE_UA},
                timeout=30,
            )
        except Exception:
            time.sleep(1.0 + attempt)
            continue
        if resp.status_code == 429:
            _block_endpoint("gtx")
            return None
        if resp.status_code != 200:
            time.sleep(1.0 + attempt)
            continue
        try:
            data = resp.json()
            return "".join(seg[0] for seg in data[0] if seg and seg[0])
        except Exception:
            return None
    return None


def _gtx_translate_lines(lines: List[str], target_lang: str) -> List[Optional[str]]:
    """Translate lines in one request; if Google merges/splits lines (count mismatch), bisect
    so translations can never shift onto the wrong line."""
    if not lines:
        return []
    safe = [ln.replace("\n", " ") for ln in lines]
    out = _gtx_request("\n".join(safe), target_lang)
    if out is None:
        return [None] * len(lines)
    parts = out.split("\n")
    if len(parts) == len(lines):
        return [p.strip() or None for p in parts]
    if len(lines) == 1:
        return [out.strip() or None]
    mid = len(lines) // 2
    return _gtx_translate_lines(lines[:mid], target_lang) + _gtx_translate_lines(lines[mid:], target_lang)


def _gtx_translate_texts(texts: List[str], target_lang: str,
                         on_chunk: Optional[Callable[[List[str], List[Optional[str]]], None]] = None,
                         cancel_check: Optional[Callable[[], bool]] = None) -> Dict[str, str]:
    """Translate many texts in character-bounded chunks; returns only successful results."""
    result: Dict[str, str] = {}
    chunk_buf: List[str] = []
    size = 0
    chunks: List[List[str]] = []
    for t in texts:
        if chunk_buf and (size + len(t) + 1 > _GTX_MAX_CHARS or len(chunk_buf) >= _GTX_MAX_LINES):
            chunks.append(chunk_buf)
            chunk_buf, size = [], 0
        chunk_buf.append(t)
        size += len(t) + 1
    if chunk_buf:
        chunks.append(chunk_buf)
    for i, ch in enumerate(chunks):
        if (cancel_check and cancel_check()) or _endpoint_blocked("gtx"):
            break
        outs = _gtx_translate_lines(ch, target_lang)
        for src, dst in zip(ch, outs):
            if dst and not _is_bad_translation(dst, src):
                result[src] = dst
        if on_chunk:
            try:
                on_chunk(ch, outs)
            except Exception:
                pass
        if i + 1 < len(chunks):
            time.sleep(0.4)  # gentle pacing between requests
    return result


def _build_translation_map(
    texts: List[str],
    target_lang: str,
    batch_size: int,
    mm_workers: int,
    engine_mode: str = "auto",
    auto_priority: str = "google_first",
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Dict[str, str]:
    translated_map: Dict[str, str] = {}
    unique_texts = list(dict.fromkeys([t for t in texts if t is not None]))
    # Word counts for better progress metrics
    word_count_map: Dict[str, int] = {t: _count_words(t) for t in unique_texts}
    total_words = sum(word_count_map.values())
    batches = chunk(unique_texts, max(1, int(batch_size)))
    processed_words = 0
    if progress_callback:
        try:
            progress_callback(processed_words, max(1, total_words))
        except Exception:
            pass

    # Mode flags
    force_mymemory = (engine_mode == "mymemory")
    auto_mm_first = (engine_mode == "auto" and auto_priority == "mymemory_first")
    use_google = (engine_mode in ("auto", "google")) and not force_mymemory and not auto_mm_first
    use_deepl = (engine_mode == "deepl")
    use_libre = (engine_mode == "libre")

    # Instantiate translators lazily
    google = GoogleTranslator(source="auto", target=target_lang) if use_google else None
    mymemory = None

    confirmed_same: set = set()
    # Fast path: whole blocks through Google's JSON endpoint; only failures go the slow way
    if use_google and unique_texts:
        def _fast_progress(chunk_texts: List[str], outs: List[Optional[str]]) -> None:
            nonlocal processed_words
            processed_words += sum(word_count_map.get(t, 0) for t, o in zip(chunk_texts, outs) if o)
            if progress_callback:
                progress_callback(min(processed_words, total_words), max(1, total_words))
        translated_map.update(_gtx_translate_texts(unique_texts, target_lang, _fast_progress, cancel_check))
        # names / interjections ("Rick.", "Ah!") come back unchanged from a *successful* response:
        # they are done, not failures to retry
        confirmed_same.update(t for t, v in translated_map.items() if v.strip() == t.strip())
        batches = chunk([t for t in unique_texts if t not in translated_map], max(1, int(batch_size)))

    # Helper: primary engine batch call with global throttling
    def _primary_translate_batch(engine_name: str, texts_batch: List[str]) -> Optional[List[str]]:
        try:
            if cancel_check and cancel_check():
                return [t for t in texts_batch]
            _API_SEM.acquire()
            try:
                if engine_name == "google" and google is not None:
                    safe = _google_translate_batch_safe(google, texts_batch, cancel_check)
                    if any(v is not None for v in safe):
                        return safe  # type: ignore[return-value]
                    return None
                if engine_name == "deepl" and 'DeeplTranslator' in globals() and DeeplTranslator is not None and _DEEPL_API_KEY:
                    try:
                        deepl = DeeplTranslator(api_key=_DEEPL_API_KEY, source="auto", target=target_lang)  # type: ignore
                    except TypeError:
                        # Older signatures
                        deepl = DeeplTranslator(_DEEPL_API_KEY, source="auto", target=target_lang)  # type: ignore
                    # Some versions support translate_batch; fallback to per-item
                    if hasattr(deepl, "translate_batch"):
                        return deepl.translate_batch(texts_batch)  # type: ignore
                    return [deepl.translate(t) for t in texts_batch]  # type: ignore
                if engine_name == "libre" and 'LibreTranslator' in globals() and LibreTranslator is not None:
                    base_url = _LIBRE_URL or "https://libretranslate.com/"
                    try:
                        libre = LibreTranslator(source="auto", target=target_lang, api_url=base_url, api_key=_LIBRE_API_KEY)  # type: ignore
                    except TypeError:
                        try:
                            libre = LibreTranslator(source="auto", target=target_lang, base_url=base_url)  # type: ignore
                        except TypeError:
                            libre = LibreTranslator(source="auto", target=target_lang)  # type: ignore
                    if hasattr(libre, "translate_batch"):
                        return libre.translate_batch(texts_batch)  # type: ignore
                    return [libre.translate(t) for t in texts_batch]  # type: ignore
                if engine_name == "deepl_web":
                    # Best-effort Selenium automation of DeepL web. Slow and fragile.
                    if webdriver is None or WebDriverWait is None or (ChromeOptions is None and ChromeDriverManager is None):
                        return None
                    try:
                        # Initialize Chrome driver
                        options = ChromeOptions() if ChromeOptions is not None else None
                        if options is not None:
                            try:
                                options.add_argument("--headless=new")
                            except Exception:
                                options.add_argument("--headless")
                            options.add_argument("--disable-gpu")
                            options.add_argument("--no-sandbox")
                            options.add_argument("--lang=en-US,en")
                            options.add_argument("--disable-dev-shm-usage")
                        try:
                            if ChromeDriverManager is not None:
                                driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)  # type: ignore
                            else:
                                driver = webdriver.Chrome(options=options)  # type: ignore
                        except Exception:
                            # Fallback default init
                            driver = webdriver.Chrome()  # type: ignore
                        results: List[str] = []
                        try:
                            base_url = "https://www.deepl.com/translator"
                            driver.get(base_url)
                            # Try to accept cookies quietly
                            try:
                                WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
                            except Exception:
                                pass
                            # Prepare language mapping (simple)
                            tgt = target_lang
                            # Process each text sequentially to avoid mixing outputs
                            for txt in texts_batch:
                                if cancel_check and cancel_check():
                                    break
                                # Navigate via URL fragment with encoded text; more reliable than typing
                                try:
                                    import urllib.parse as _up
                                    url = f"https://www.deepl.com/translator#auto/{_up.quote(tgt)}/{_up.quote(txt[:4500])}"
                                    driver.get(url)
                                except Exception:
                                    driver.get(base_url)
                                # Wait for output to appear
                                out_text = None
                                try:
                                    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
                                    # Try multiple output selectors
                                    selectors = [
                                        'div[dl-test="translator-target"]',
                                        'textarea[dl-test="translator-target-input"]',
                                        'div.lmt__translations_as_text',
                                        'div.lmt__target_textarea',
                                        'div[aria-live="polite"]',
                                    ]
                                    for sel in selectors:
                                        try:
                                            el = WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                                            txt_out = el.text.strip()
                                            if not txt_out and hasattr(el, 'get_attribute'):
                                                txt_out = (el.get_attribute('value') or '').strip()
                                            if txt_out:
                                                out_text = txt_out
                                                break
                                        except Exception:
                                            continue
                                except Exception:
                                    out_text = None
                                results.append(out_text if out_text else txt)
                        finally:
                            try:
                                driver.quit()
                            except Exception:
                                pass
                        return results
                    except Exception:
                        return None
            finally:
                _API_SEM.release()
        except Exception:
            return None
        return None

    # Branch 1: MyMemory-first (auto + mmemory_first) – keep original logic with small tweaks
    if force_mymemory or auto_mm_first:
        if mymemory is None:
            target_code = _map_lang_for_mymemory(target_lang)
            mymemory = MyMemoryTranslator(source="en-GB", target=target_code)

        def _mm_translate_one(text: str) -> str:
            out = _mm_translate_via_client(mymemory, text)
            return out if out is not None else text

        # MyMemory concurrently
        with ThreadPoolExecutor(max_workers=max(1, min(mm_workers, 16))) as pool:
            futures = {pool.submit(_mm_translate_one, t): t for t in unique_texts}
            for fut in as_completed(futures):
                src = futures[fut]
                try:
                    translated_map[src] = fut.result()
                except Exception:
                    translated_map[src] = src
                processed_words += word_count_map.get(src, 0)
                if progress_callback:
                    try:
                        progress_callback(processed_words, max(1, total_words))
                    except Exception:
                        pass

        # If auto and Google is available, try to fill any unchanged entries
        if engine_mode == "auto" and auto_mm_first and google is not None:
            remaining = [t for t in unique_texts if translated_map.get(t) in (None, t)]
            if remaining:
                # Parallelize in batches against Google
                rem_batches = chunk(remaining, max(1, int(batch_size)))
                max_workers = max(1, min(4, len(rem_batches)))
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    futs = {pool.submit(_primary_translate_batch, "google", b): b for b in rem_batches}
                    for fut in as_completed(futs):
                        b = futs[fut]
                        res = fut.result()
                        if isinstance(res, list):
                            for src, dst in zip(b, res):
                                if dst is not None and not _is_bad_translation(dst, src):
                                    translated_map[src] = dst
                        processed_words += sum(word_count_map.get(s, 0) for s in b)
                        if progress_callback:
                            try:
                                progress_callback(min(processed_words, total_words), max(1, total_words))
                            except Exception:
                                pass
        return translated_map

    # Branch 2: Primary engine first (google/deepl/libre), with per-batch parallelization and MyMemory fallback per batch
    primary = "google" if use_google else ("deepl" if use_deepl else ("libre" if use_libre else None))
    unresolved: List[str] = []
    if primary is not None and batches:
        max_workers = max(1, min(4, len(batches)))
        if primary == "deepl_web":
            max_workers = 1  # avoid multiple browsers in parallel
        lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futs = {pool.submit(_primary_translate_batch, primary, b): b for b in batches}
            for fut in as_completed(futs):
                b = futs[fut]
                res = fut.result()
                if isinstance(res, list) and len(res) == len(b):
                    with lock:
                        for src, dst in zip(b, res):
                            if dst is not None and not _is_bad_translation(dst, src):
                                translated_map[src] = dst
                            else:
                                unresolved.append(src)
                else:
                    # Mark this batch for fallback
                    unresolved.extend(b)
                # Count only items that we actually received a translation for
                if isinstance(res, list) and len(res) == len(b):
                    processed_words += sum(word_count_map.get(s, 0) for s in b)
                if progress_callback:
                    try:
                        progress_callback(min(processed_words, total_words), max(1, total_words))
                    except Exception:
                        pass

    # Fallback with MyMemory for unresolved texts, if any
    remaining = [t for t in unique_texts if translated_map.get(t) is None]
    if remaining:
        if mymemory is None:
            target_code = _map_lang_for_mymemory(target_lang)
            mymemory = MyMemoryTranslator(source="en-GB", target=target_code)

        def _mm_translate_one_fb(text: str) -> str:
            out = _mm_translate_via_client(mymemory, text)
            return out if out is not None else text

        with ThreadPoolExecutor(max_workers=max(1, min(mm_workers, 16))) as pool:
            futures = {pool.submit(_mm_translate_one_fb, t): t for t in remaining}
            for fut in as_completed(futures):
                src = futures[fut]
                try:
                    translated_map[src] = fut.result()
                except Exception:
                    translated_map[src] = src
                processed_words += word_count_map.get(src, 0)
                if progress_callback:
                    try:
                        progress_callback(min(processed_words, total_words), max(1, total_words))
                    except Exception:
                        pass

    # Recovery pass: some lines fail only because of a transient blip (a
    # momentary block, a bad response). Rather than silently leaving the
    # original English text in place, retry those a few more times with
    # backoff before giving up for good.
    def _looks_untranslated(src: str) -> bool:
        if src in confirmed_same:
            return False
        cur = translated_map.get(src)
        if cur is None or _is_bad_translation(cur, src):
            return True
        return cur.strip() == src.strip() and bool(re.search(r"[A-Za-z]{2,}", src))

    pending = [t for t in unique_texts if _looks_untranslated(t)]
    max_rounds = 6
    for round_no in range(max_rounds):
        if not pending or (cancel_check and cancel_check()):
            break
        time.sleep(min(20.0, 2.0 * (round_no + 1)))
        translated_map.update(_gtx_translate_texts(pending, target_lang, cancel_check=cancel_check))
        pending = [t for t in pending if _looks_untranslated(t)]
        still_pending: List[str] = []
        for src in pending:
            if cancel_check and cancel_check():
                still_pending.append(src)
                continue
            out = _google_translate_one_http(src, target_lang, attempts=3)
            if out is None and not _MYMEMORY_QUOTA_HIT:
                out = _mymemory_translate_one_http(src, target_lang)
            if out and not _is_bad_translation(out, src):
                translated_map[src] = out
            else:
                still_pending.append(src)
        pending = still_pending

    # Finalize: ensure every unique text has a mapping
    for t in unique_texts:
        cur = translated_map.get(t)
        if cur is None or _is_bad_translation(cur, t):
            translated_map[t] = t
    return translated_map


def translate_generic_lines(
    lines: List[str],
    target_lang: str,
    batch_size: int,
    mm_workers: int,
    engine_mode: str = "auto",
    auto_priority: str = "google_first",
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> List[str]:
    # Identify translatable cores, preserve leading/trailing ws and line endings
    to_translate_indices: List[int] = []
    cores: List[str] = []
    for idx, line in enumerate(lines):
        stripped = line.strip("\r\n")
        leading, core, trailing = split_whitespace(stripped)
        if core:
            to_translate_indices.append(idx)
            cores.append(core)
    if not to_translate_indices:
        return lines
    translated_map = _build_translation_map(
        cores, target_lang, batch_size, mm_workers, engine_mode, auto_priority, progress_callback, cancel_check
    )
    result = list(lines)
    for idx in to_translate_indices:
        stripped = lines[idx].strip("\r\n")
        leading, core, trailing = split_whitespace(stripped)
        translated_core = translated_map.get(core, core)
        rebuilt = f"{leading}{translated_core}{trailing}"
        suffix = "\r\n" if lines[idx].endswith("\r\n") else ("\n" if lines[idx].endswith("\n") else "")
        result[idx] = rebuilt + suffix
    return result


# -------------------- File type helpers --------------------
SUPPORTED_EXTS = (".srt", ".vtt", ".txt", ".md", ".csv", ".docx", ".pdf")


def _out_path_same_ext(path: str, lang_code: str) -> str:
    base, ext = os.path.splitext(path)
    return base + f".{lang_code}{ext}"


def translate_text_file(
    path: str,
    target_lang: str,
    batch_size: int,
    mm_workers: int,
    engine_mode: str = "auto",
    auto_priority: str = "google_first",
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    with open(path, "r", encoding="utf-8", newline="") as f:
        lines = f.readlines()
    out_lines = translate_generic_lines(lines, target_lang, batch_size, mm_workers, engine_mode, auto_priority, progress_callback, cancel_check)
    outp = _out_path_same_ext(path, target_lang)
    with open(outp, "w", encoding="utf-8-sig", newline="") as wf:
        wf.writelines(out_lines)
    return outp


def translate_docx_file(
    path: str,
    target_lang: str,
    batch_size: int,
    mm_workers: int,
    engine_mode: str = "auto",
    auto_priority: str = "google_first",
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    # Early language detect – skip if already in target language
    try:
        try:
            if DocxDocument is not None:
                _doc = DocxDocument(path)
                _sample = " ".join([p.text for p in _doc.paragraphs[:40]])
            elif docx2txt is not None:
                _raw = docx2txt.process(path) or ""
                _sample = " ".join(_raw.splitlines()[:60])
            else:
                _sample = ""
            lg = detect_language(_sample)
            if lg and lg.lower().startswith(target_lang.lower()[:2]):
                # Copy-as is with new name
                outp_same = _out_path_same_ext(path, target_lang)
                try:
                    shutil.copy2(path, outp_same)
                    return outp_same
                except Exception:
                    pass
            
        except Exception:
            pass
    except Exception:
        pass
    # Attempt to hydrate cloud placeholder files (e.g., OneDrive) which may report size 0
    try:
        with open(path, 'rb') as _rf:
            _rf.read(1)
    except Exception:
        pass
    if DocxDocument is None:
        # Try a fallback to docx2txt if available to at least produce a translated TXT next to source
        if docx2txt is not None:
            try:
                raw = docx2txt.process(path) or ""
                lines = raw.splitlines(True)
                out_lines = translate_generic_lines(
                    lines,
                    target_lang=target_lang,
                    batch_size=batch_size,
                    mm_workers=mm_workers,
                    engine_mode=engine_mode,
                    auto_priority=auto_priority,
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                )
                outp_txt = _out_path_same_ext(path, target_lang).rsplit('.', 1)[0] + '.txt'
                with open(outp_txt, 'w', encoding='utf-8-sig', newline='') as wf:
                    wf.writelines(out_lines)
                return outp_txt
            except Exception:
                pass
        raise RuntimeError("python-docx is not installed (pip install python-docx) or the file could not be opened")
    # python-docx bazı bozuk/office paketlenmemiş dosyalarda PackageNotFoundError fırlatır; yakala ve fallback dene
    try:
        doc = DocxDocument(path)
    except Exception as e:
        if docx2txt is not None:
            try:
                raw = docx2txt.process(path) or ""
                lines = raw.splitlines(True)
                out_lines = translate_generic_lines(
                    lines,
                    target_lang=target_lang,
                    batch_size=batch_size,
                    mm_workers=mm_workers,
                    engine_mode=engine_mode,
                    auto_priority=auto_priority,
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                )
                outp_txt = _out_path_same_ext(path, target_lang).rsplit('.', 1)[0] + '.txt'
                with open(outp_txt, 'w', encoding='utf-8-sig', newline='') as wf:
                    wf.writelines(out_lines)
                return outp_txt
            except Exception:
                pass
        raise

    # Collect runs from body, tables, headers and footers
    runs: List[object] = []
    texts: List[str] = []

    def collect_from_paragraphs(pars) -> None:
        for p in pars:
            for r in getattr(p, 'runs', []) or []:
                t = r.text
                if not t:
                    continue
                lead, core, trail = split_whitespace(t)
                if core:
                    runs.append(r)
                    texts.append(core)

    # Body paragraphs and tables
    collect_from_paragraphs(doc.paragraphs)
    for tbl in getattr(doc, 'tables', []) or []:
        for row in tbl.rows:
            for cell in row.cells:
                collect_from_paragraphs(cell.paragraphs)
                for ctbl in getattr(cell, 'tables', []) or []:
                    for crow in ctbl.rows:
                        for ccell in crow.cells:
                            collect_from_paragraphs(ccell.paragraphs)

    # Headers and footers
    for sec in getattr(doc, 'sections', []) or []:
        try:
            if sec.header:
                collect_from_paragraphs(sec.header.paragraphs)
                for htbl in getattr(sec.header, 'tables', []) or []:
                    for hrow in htbl.rows:
                        for hcell in hrow.cells:
                            collect_from_paragraphs(hcell.paragraphs)
        except Exception:
            pass
        try:
            if sec.footer:
                collect_from_paragraphs(sec.footer.paragraphs)
                for ftbl in getattr(sec.footer, 'tables', []) or []:
                    for frow in ftbl.rows:
                        for fcell in frow.cells:
                            collect_from_paragraphs(fcell.paragraphs)
        except Exception:
            pass

    if not texts:
        outp = _out_path_same_ext(path, target_lang)
        doc.save(outp)
        return outp

    trans_map = _build_translation_map(
        texts,
        target_lang=target_lang,
        batch_size=batch_size,
        mm_workers=mm_workers,
        engine_mode=engine_mode,
        auto_priority=auto_priority,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )

    # Apply per-run preserving leading/trailing whitespace
    for r in runs:
        try:
            src = r.text
            if not src or not src.strip():
                continue
            lead, core, trail = split_whitespace(src)
            new_core = trans_map.get(core, core)
            r.text = f"{lead}{new_core}{trail}"
        except Exception:
            continue
    outp = _out_path_same_ext(path, target_lang)
    doc.save(outp)
    return outp


def translate_pdf_file(
    path: str,
    target_lang: str,
    batch_size: int,
    mm_workers: int,
    engine_mode: str = "auto",
    auto_priority: str = "google_first",
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    as_text: bool = False,
) -> str:
    if pdf_extract_text is None:
        raise RuntimeError("pdfminer.six is not installed (pip install pdfminer.six)")
    # Extract text only; ignore images/shapes, just textual content
    text = pdf_extract_text(path) or ""
    # Early language detect – skip if already in target language
    try:
        lg = detect_language(" ".join(text.split()[:200]))
        if lg and lg.lower().startswith(target_lang.lower()[:2]):
            outp_same = _out_path_same_ext(path, target_lang)
            # Create a simple copy of original text into a PDF to keep pipeline consistent
            # but since we want same textual content, just re-write extracted text
            # Alternatively, return original path – here we still emit translated container
    except Exception:
        pass
    lines = text.splitlines(True)
    out_lines = translate_generic_lines(
        lines,
        target_lang=target_lang,
        batch_size=batch_size,
        mm_workers=mm_workers,
        engine_mode=engine_mode,
        auto_priority=auto_priority,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )
    # If user prefers TXT output for PDFs, write as UTF-8 TXT and return
    if as_text:
        outp_txt = _out_path_same_ext(path, target_lang).rsplit('.', 1)[0] + '.txt'
        with open(outp_txt, 'w', encoding='utf-8-sig', newline='') as wf:
            wf.writelines(out_lines)
        return outp_txt

    if rl_canvas is None or A4 is None:
        raise RuntimeError("reportlab is not installed (pip install reportlab)")
    outp = _out_path_same_ext(path, target_lang)
    # Normalize whitespace – collapse multiple blank lines, trim trailing spaces
    norm_lines = []
    blank_run = 0
    for ln in out_lines:
        ln = ln.replace("\r", "")
        if ln.strip() == "":
            blank_run += 1
            if blank_run > 1:
                continue
        else:
            blank_run = 0
        norm_lines.append(ln)

    # Simple writer with dynamic wrap per page width (text-only PDF)
    page_w, page_h = A4
    margin = 15 * mm if mm else 40
    c = rl_canvas.Canvas(outp, pagesize=A4)
    # Use Unicode TTF if available for Turkish glyphs
    font_name = _register_pdf_unicode_font() or "Times-Roman"
    try:
        c.setFont(font_name, 11)
    except Exception:
        c.setFont("Times-Roman", 11)
    x = margin
    y = page_h - margin
    max_width = page_w - 2 * margin
    # approximate characters per line by average glyph width (~7 pt in Times 11)
    try:
        wrap_len = max(40, int(max_width / 7.0))
    except Exception:
        wrap_len = 95
    # Group paragraphs by blank lines to preserve structure
    paragraph = []
    def _flush_paragraph():
        nonlocal y
        if not paragraph:
            return
        text = "".join(paragraph)
        text = text.replace("\r", "")
        for para in text.splitlines():
            if not para:
                continue
            parts = [para[i:i+wrap_len] for i in range(0, len(para), wrap_len)] if len(para) > wrap_len else [para]
            for part in parts:
                if y < margin:
                    c.showPage()
                    try:
                        c.setFont(font_name, 11)
                    except Exception:
                        c.setFont("Times-Roman", 11)
                    y = page_h - margin
                txt_out = part.rstrip("\n")
                if font_name == "Times-Roman":
                    txt_out = _ascii_fallback(txt_out)
                c.drawString(x, y, txt_out)
                y -= 14
        y -= 6  # small spacing between paragraphs
        paragraph.clear()

    for line in norm_lines:
        if line.strip() == "":
            _flush_paragraph()
            continue
        paragraph.append(line)
    _flush_paragraph()
    c.save()
    return outp


# ---- UI helpers: Tooltip & Circular Progress ----
class _Tooltip:
    def __init__(self, widget, text: str, delay_ms: int = 600) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id = None
        self._tip_win = None
        try:
            widget.bind("<Enter>", self._schedule)
            widget.bind("<Leave>", self._unschedule)
            widget.bind("<ButtonPress>", self._unschedule)
        except Exception:
            pass

    def _schedule(self, _e=None) -> None:
        try:
            self._after_id = self.widget.after(self.delay_ms, self._show)
        except Exception:
            pass

    def _unschedule(self, _e=None) -> None:
        try:
            if self._after_id:
                self.widget.after_cancel(self._after_id)
                self._after_id = None
        except Exception:
            pass
        self._hide()

    def _show(self) -> None:
        if self._tip_win:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            self._tip_win = tk.Toplevel(self.widget)
            self._tip_win.wm_overrideredirect(True)
            self._tip_win.wm_geometry(f"+{x}+{y}")
            frm = ttk.Frame(self._tip_win, padding=(8, 6, 8, 6))
            lbl = ttk.Label(frm, text=self.text, justify="left", wraplength=360)
            frm.pack(fill="both", expand=True)
            lbl.pack(fill="both", expand=True)
        except Exception:
            self._tip_win = None

    def _hide(self) -> None:
        try:
            if self._tip_win:
                self._tip_win.destroy()
                self._tip_win = None
        except Exception:
            pass


class _CircularProgress(ttk.Frame):
    """Progress ring with the percentage drawn in the centre; colours follow the theme."""

    def __init__(self, parent, size: int = 160, thickness: int = 12) -> None:
        super().__init__(parent)
        self.size = size
        self.thickness = thickness
        self.color = "#3d7bfd"
        self.track = "#e2e8f0"
        self.text_color = "#1f2937"
        self.canvas = tk.Canvas(self, width=size, height=size, highlightthickness=0, bd=0)
        self.canvas.pack(pady=(4, 2))
        # kept for API compatibility (percentage is now drawn inside the ring)
        self.lbl_pct = ttk.Label(self, text="0%")
        try:
            eta_label = self.master._tr("ETA") + ": --:--"  # type: ignore[attr-defined]
        except Exception:
            eta_label = "ETA: --:--"
        self.lbl_eta = ttk.Label(self, text=eta_label)
        self.lbl_eta.pack()
        self._percent = 0
        self._sync_bg()
        self._draw(0)

    def _sync_bg(self) -> None:
        try:
            bg = ttk.Style().lookup("TFrame", "background") or self.winfo_toplevel().cget("bg")
            self.canvas.configure(bg=bg)
            fg = ttk.Style().lookup("TLabel", "foreground") or "#1f2937"
            self.text_color = fg
            self.track = TranslatorGUI._mix(self, bg, fg, 0.12)
        except Exception:
            pass

    def _draw(self, percent: int) -> None:
        self.canvas.delete("all")
        pad = self.thickness / 2 + 2
        x0 = y0 = pad
        x1 = y1 = self.size - pad
        try:
            self.canvas.create_oval(x0, y0, x1, y1, outline=self.track, width=self.thickness)
            if percent > 0:
                self.canvas.create_arc(x0, y0, x1, y1, start=90, extent=-min(359.9, percent * 3.6), style=tk.ARC,
                                       outline=self.color, width=self.thickness)
            self.canvas.create_text(self.size / 2, self.size / 2, text=f"{percent}%", fill=self.text_color,
                                    font=getattr(self, "_font", None) or ("Segoe UI", max(12, self.size // 7), "bold"))
        except Exception:
            pass

    def set(self, percent: int, eta_text: str = "ETA: --:--") -> None:
        p = max(0, min(100, int(percent)))
        self._percent = p
        self._draw(p)
        try:
            self.lbl_pct.configure(text=f"{p}%")
            self.lbl_eta.configure(text=eta_text)
        except Exception:
            pass

    def set_color(self, color: str) -> None:
        self.color = color
        self._sync_bg()
        self._draw(self._percent)

    def set_palette(self, bg: str, track: str, color: str, text: str, font=None) -> None:
        self.color, self.track, self.text_color = color, track, text
        self._font = font
        try:
            self.canvas.configure(bg=bg)
        except Exception:
            pass
        self._draw(self._percent)


class _RoundedCard(ttk.Frame):
    # shadow_offset=0 draws a 1px outline instead of a drop shadow (flat panel look)
    def __init__(self, parent, radius: int = 12, margin: int = 6, fill: str = "#ffffff", shadow: str = "#d6dce6", shadow_offset: int = 0, min_height: int = 96) -> None:
        super().__init__(parent)
        self.radius = radius
        self.margin = margin
        # content sits inside the rounded corners, otherwise its square corners cover them
        self.inset = margin + max(3, radius // 2)
        self.fill = fill
        self.shadow = shadow
        self.shadow_offset = shadow_offset
        self.min_height = max(1, int(min_height))
        self._shape_tag = "_rounded_card_shape"
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        try:
            self.canvas.configure(bg=self.fill)
        except Exception:
            pass
        self.canvas.pack(fill="both", expand=True)
        try:
            self.canvas.configure(height=self.min_height)
        except Exception:
            pass
        # Content frame rendered with card background
        self.content = ttk.Frame(self, style="CardInner.TFrame")
        # place content inside canvas window to follow resizing
        self._win_id = self.canvas.create_window((self.inset, self.inset), window=self.content, anchor="nw")
        self.canvas.bind("<Configure>", self._on_resize)
        self.content.bind("<Configure>", self._on_content_config)
        self._redraw()

    def _on_resize(self, _e=None) -> None:
        try:
            w = max(1, self.canvas.winfo_width())
            h = max(1, self.canvas.winfo_height())
            # update inner window width to fit card minus margins
            self.canvas.itemconfigure(self._win_id, width=max(1, w - 2 * self.inset))
            self.canvas.coords(self._win_id, self.inset, self.inset)
            self._redraw()
        except Exception:
            pass

    def set_colors(self, fill: str, shadow: str, outer: Optional[str] = None) -> None:
        """fill = card surface, shadow = outline colour, outer = page colour behind the rounded corners."""
        self.fill = fill
        self.shadow = shadow
        try:
            self.canvas.configure(bg=outer or self.fill)
        except Exception:
            pass
        self._redraw()

    def set_min_height(self, h: int) -> None:
        self.min_height = max(1, int(h))
        try:
            ch = max(self.min_height, self.content.winfo_reqheight() + 2 * self.inset)
            self.canvas.configure(height=ch)
        except Exception:
            pass

    def _rounded_rect(self, x1, y1, x2, y2, r, fill_color):
        try:
            # corners
            self.canvas.create_arc(x1, y1, x1+2*r, y1+2*r, start=90, extent=90, fill=fill_color, outline="", tags=(self._shape_tag,))
            self.canvas.create_arc(x2-2*r, y1, x2, y1+2*r, start=0, extent=90, fill=fill_color, outline="", tags=(self._shape_tag,))
            self.canvas.create_arc(x2-2*r, y2-2*r, x2, y2, start=270, extent=90, fill=fill_color, outline="", tags=(self._shape_tag,))
            self.canvas.create_arc(x1, y2-2*r, x1+2*r, y2, start=180, extent=90, fill=fill_color, outline="", tags=(self._shape_tag,))
            # edges and center
            self.canvas.create_rectangle(x1+r, y1, x2-r, y2, fill=fill_color, outline="", tags=(self._shape_tag,))
            self.canvas.create_rectangle(x1, y1+r, x2, y2-r, fill=fill_color, outline="", tags=(self._shape_tag,))
        except Exception:
            pass

    def _redraw(self) -> None:
        try:
            # delete only shapes, keep window item
            self.canvas.delete(self._shape_tag)
            w = max(1, self.canvas.winfo_width())
            h = max(self.min_height, self.canvas.winfo_height())
            r = max(0, min(self.radius, int(min(w, h) * 0.2)))
            # shadow (offset > 0) or 1px outline (offset == 0)
            grow = 1 if self.shadow_offset == 0 else 0
            sx = self.margin + self.shadow_offset - grow
            sy = self.margin + self.shadow_offset - grow
            ex = w - self.margin + self.shadow_offset + grow
            ey = h - self.margin + self.shadow_offset + grow
            self._rounded_rect(sx, sy, ex, ey, r + grow, self.shadow)
            # card
            x1 = self.margin
            y1 = self.margin
            x2 = w - self.margin
            y2 = h - self.margin
            self._rounded_rect(x1, y1, x2, y2, r, self.fill)
            # ensure content window is above shapes
            try:
                self.canvas.tag_raise(self._win_id)
            except Exception:
                pass
        except Exception:
            pass

    def _on_content_config(self, _e=None) -> None:
        try:
            needed = self.content.winfo_reqheight() + 2 * self.inset
            cur = self.canvas.winfo_height()
            target = max(self.min_height, needed)
            if abs(cur - target) > 1:
                self.canvas.configure(height=target)
                self._redraw()
        except Exception:
            pass


class _ScrollableFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview, style="Modern.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")
        self.content = ttk.Frame(self.canvas)
        self._win_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._on_content)
        self.canvas.bind("<Configure>", self._on_canvas)
        # Mouse wheel: active only while the pointer is over this frame, so other
        # scrollable areas (dialogs, lists) keep their own wheel handling.
        self.bind("<Enter>", self._bind_wheel)
        self.bind("<Leave>", self._unbind_wheel)

    _SELF_SCROLLING = ("Text", "Treeview", "Listbox", "TCombobox", "Spinbox", "TSpinbox")

    def _bind_wheel(self, _e=None):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind_all(seq, self._on_wheel)

    def _unbind_wheel(self, _e=None):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.unbind_all(seq)

    def _on_content(self, _e=None):
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            ch = self.canvas.winfo_height()
            if ch > 1:
                self.canvas.itemconfigure(self._win_id, height=max(ch, self.content.winfo_reqheight()))
        except Exception:
            pass

    def _on_canvas(self, _e=None):
        try:
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            if cw > 0:
                # Fill the window when it is taller than the content (no dead band at the bottom);
                # otherwise keep the natural height and scroll.
                self.canvas.itemconfigure(self._win_id, width=cw, height=max(ch, self.content.winfo_reqheight()))
        except Exception:
            pass

    def _on_wheel(self, event):
        try:
            w = getattr(event, "widget", None)
            if w is not None and hasattr(w, "winfo_class") and w.winfo_class() in self._SELF_SCROLLING:
                return
            if self.canvas.yview() == (0.0, 1.0):
                return  # everything visible, nothing to scroll
            if hasattr(event, 'delta') and event.delta:
                self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            elif hasattr(event, 'num'):
                if event.num == 4:
                    self.canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    self.canvas.yview_scroll(1, "units")
        except Exception:
            pass

class TranslatorGUI:
    def __init__(self) -> None:
        if tk is None:
            print("Tkinter not available. Use CLI: py translate_srt.py <in.srt> <out.srt> [lang]", file=sys.stderr)
            sys.exit(2)
        # Per-monitor DPI awareness must be set before the first window exists
        try:
            if sys.platform.startswith("win"):
                ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
        except Exception:
            pass
        self.root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()  # type: ignore[union-attr]
        # Build everything while hidden and show the finished window once. (It used to appear
        # immediately as a blank full-screen window with a native menubar, then re-layout,
        # shrink to 1024x680 and switch theme a few seconds later.)
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.title("Subtitle PRO")
        try:
            app_dir = os.path.dirname(os.path.abspath(__file__))
            icon_png = os.path.join(app_dir, "icon.png")
            if os.path.exists(icon_png):
                self._app_icon = tk.PhotoImage(file=icon_png)
                self.root.iconphoto(True, self._app_icon)
                self._logo_img = self._app_icon.subsample(max(1, self._app_icon.width() // 26))
            ico = os.path.join(app_dir, "icon.ico")
            if os.path.exists(ico):
                self.root.iconbitmap(default=ico)
        except Exception:
            self._logo_img = None
        self.root.minsize(980, 640)
        self._bs = None  # ttkbootstrap is no longer used: one deterministic design system instead
        self._style = ttk.Style(self.root)
        try:
            self._style.theme_use("clam")
        except Exception:
            pass

        # ---- state & tk variables (all created before settings are read) ----
        self.font_scale_var = tk.DoubleVar(value=1.0)
        self._base_fonts = {}
        self._base_font_sizes = {}
        self._init_base_fonts()
        self.ui_lang_var = tk.StringVar(value="English")
        self.ui_lang_code = "en"
        try:
            pre = self._read_settings_file()
            if pre.get("ui_lang_code"):
                self.ui_lang_code = str(pre["ui_lang_code"])
        except Exception:
            pass
        setattr(sys.modules[__name__], "_CURRENT_UI_LANG_CODE", self.ui_lang_code)
        self.lang_map = _get_supported_langs(self.ui_lang_code)
        self.ui_codes = sorted(set(_get_ui_langs_from_json().values()))
        self.ui_lang_map: Dict[str, str] = {}
        self.ui_lang_names: List[str] = []
        self.lang_names = sorted(self.lang_map.keys())
        self.target_lang_map: Dict[str, str] = {}
        self.target_lang_names: List[str] = []
        self.target_lang_var = tk.StringVar(value="")
        self._ui_cache: Dict[str, Dict[str, str]] = {}
        self.input_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar()
        self.progress_var = tk.DoubleVar(value=0.0)
        self.status_var = tk.StringVar(value="")
        self._thread: Optional[threading.Thread] = None
        self._cancel = False
        self._auto_output = True
        self._start_ts = 0.0
        self.batch_size_var = tk.IntVar(value=100)
        self.mm_workers_var = tk.IntVar(value=6)
        self.parallel_files_var = tk.BooleanVar(value=False)
        self.file_workers_var = tk.IntVar(value=2)
        self.dark_mode_var = tk.BooleanVar(value=False)
        self.accent_var = tk.StringVar(value="blue")
        self.compact_mode_var = tk.BooleanVar(value=False)
        self.bs_theme_var = tk.StringVar(value="")
        self.theme_profile_var = tk.StringVar(value="")
        self.file_items: Dict[str, str] = {}
        self.item_to_path: Dict[str, str] = {}
        self.file_added_ts: Dict[str, float] = {}
        self.files: List[str] = []
        self.dict_mode_var = tk.StringVar(value="off")
        self.dict_path_var = tk.StringVar(value="")
        self.dict_case_ins_var = tk.BooleanVar(value=False)
        self.dict_word_boundary_var = tk.BooleanVar(value=False)
        self.custom_terms: Dict[str, str] = {}
        self.engine_var = tk.StringVar(value="auto")
        self.auto_priority_var = tk.StringVar(value="google_first")
        self.save_next_var = tk.BooleanVar(value=True)
        self.outdir_var = tk.StringVar(value="")
        self.clean_after_var = tk.BooleanVar(value=False)
        self.pdf_mode_var = tk.StringVar(value="pdf")
        self.skip_same_lang_var = tk.BooleanVar(value=True)
        self.log_info_var = tk.BooleanVar(value=True)
        self.log_ok_var = tk.BooleanVar(value=True)
        self.log_err_var = tk.BooleanVar(value=True)
        self._log_entries: List[Tuple[str, str]] = []
        self._sort_reverse = {"dosya": False, "boyut": False, "durum": False, "eklenme": False}
        self._log_queue: "queue.Queue[Callable[[], object]]" = queue.Queue()

        # Settings first, so the very first frame already has the right theme/language/size
        self._load_settings()
        self._build_titlebar()
        self._build_ui()
        self._apply_loaded_settings()
        self._drain_after = self.root.after(50, self._drain_log_queue)
        # stop the queue pump with the window (avoids "invalid command name ..._drain_log_queue")
        self.root.bind("<Destroy>", lambda e: e.widget is self.root and self._stop_pump(), add="+")
        self._show_window()

    def _stop_pump(self) -> None:
        try:
            self.root.after_cancel(self._drain_after)
        except Exception:
            pass

    # ---------- window chrome (custom title bar, maximize, drag, resize) ----------
    def _work_area(self) -> Tuple[int, int, int, int]:
        """Desktop area without the taskbar (x, y, w, h)."""
        try:
            if sys.platform.startswith("win"):
                class RECT(ctypes.Structure):
                    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
                r = RECT()
                ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
                if r.r > r.l and r.b > r.t:
                    return r.l, r.t, r.r - r.l, r.b - r.t
        except Exception:
            pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _set_maximized(self, value: bool) -> None:
        x, y, w, h = self._work_area()
        if value:
            if not getattr(self, "_is_max", False):
                try:
                    self._normal_geometry = self.root.geometry()
                except Exception:
                    pass
            self.root.geometry(f"{w}x{h}+{x}+{y}")
        else:
            geo = getattr(self, "_normal_geometry", None)
            if not geo or geo.startswith("1x1"):
                nw, nh = min(1320, int(w * 0.85)), min(860, int(h * 0.88))
                geo = f"{nw}x{nh}+{x + (w - nw) // 2}+{y + (h - nh) // 2}"
            self.root.geometry(geo)
        self._is_max = value
        try:
            self._win_btn_max.configure(text="❐" if value else "☐")
        except Exception:
            pass

    def _toggle_maximize(self, _e=None) -> None:
        self._set_maximized(not getattr(self, "_is_max", False))

    def _minimize(self) -> None:
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        except Exception:
            try:
                self.root.iconify()
            except Exception:
                pass

    def _show_window(self) -> None:
        """Size, give the borderless window a taskbar button, then map it exactly once."""
        cfg = self._read_settings_file()
        x, y, w, h = self._work_area()
        nw, nh = min(1320, int(w * 0.85)), min(860, int(h * 0.88))
        self._normal_geometry = cfg.get("window_geometry") or f"{nw}x{nh}+{x + (w - nw) // 2}+{y + (h - nh) // 2}"
        self._set_maximized(bool(cfg.get("window_maximized", True)))
        self.root.update_idletasks()
        try:
            if sys.platform.startswith("win"):
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
                style = (style & ~0x00000080) | 0x00040000  # -TOOLWINDOW +APPWINDOW
                ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
        except Exception:
            pass
        # Map fully transparent, let Tk paint every widget, then reveal: the user never sees
        # the half-drawn first frame (cards filling in piece by piece).
        try:
            self.root.attributes("-alpha", 0.0)
        except Exception:
            pass
        self.root.deiconify()
        self.root.update()
        self.root.after(80, lambda: self.root.attributes("-alpha", 1.0))
        # Started via pyw/run_app.bat the process is not the foreground app, so Windows would open
        # the window *behind* other windows: raise it briefly as topmost, then release.
        self.root.attributes("-topmost", True)
        self.root.lift()
        try:
            self.root.focus_force()
        except Exception:
            pass
        self.root.after(400, lambda: self.root.attributes("-topmost", False))

    def fix_window_focus(self):  # kept for compatibility; _show_window does this once
        pass

    def enable_drag(self):
        def start_move(event):
            if getattr(self, "_is_max", False):
                return
            self._drag = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

        def on_motion(event):
            d = getattr(self, "_drag", None)
            if d:
                self.root.geometry(f"+{event.x_root - d[0]}+{event.y_root - d[1]}")

        def stop_move(_e):
            self._drag = None
        for w in [self.titlebar] + list(getattr(self, "_drag_widgets", [])):
            w.bind("<ButtonPress-1>", start_move)
            w.bind("<B1-Motion>", on_motion)
            w.bind("<ButtonRelease-1>", stop_move)
            w.bind("<Double-Button-1>", self._toggle_maximize)

    def _build_titlebar(self) -> None:
        """One bar: logo, app name, header controls, window buttons (was two stacked title rows)."""
        self.titlebar = tk.Frame(self.root, height=58, bd=0, highlightthickness=0)
        self.titlebar.pack(side="top", fill="x")
        self.titlebar.pack_propagate(False)
        self.titlebar_border = tk.Frame(self.root, height=1, bd=0)
        self.titlebar_border.pack(side="top", fill="x")
        left = tk.Frame(self.titlebar, bd=0)
        left.pack(side="left", fill="y", padx=(14, 0))
        self._tb_frames = [left]
        self._drag_widgets = [left]
        if getattr(self, "_logo_img", None) is not None:
            logo = tk.Label(left, image=self._logo_img, bd=0)
            logo.pack(side="left", padx=(0, 10))
            self._drag_widgets.append(logo)
        names = tk.Frame(left, bd=0)
        names.pack(side="left", fill="y")
        self._tb_frames.append(names)
        self.lbl_app_title = tk.Label(names, text="Subtitle PRO", bd=0, anchor="w")
        self.lbl_app_title.pack(anchor="w", pady=(9, 0))
        self.lbl_app_subtitle = tk.Label(names, text=self._tr("Batch subtitle & document translator"), bd=0, anchor="w")
        self.lbl_app_subtitle.pack(anchor="w")
        self._drag_widgets += [names, self.lbl_app_title, self.lbl_app_subtitle]

        # window buttons (Fluent-style): packed first so header controls sit to their left
        btns = tk.Frame(self.titlebar, bd=0)
        btns.pack(side="right", fill="y")
        self._tb_frames.append(btns)
        self._win_btns = []

        def win_btn(text, cmd, danger=False):
            b = tk.Label(btns, text=text, width=5, bd=0, cursor="hand2")
            b.pack(side="left", fill="y")
            b.bind("<Button-1>", lambda e: cmd())
            b._danger = danger  # type: ignore[attr-defined]
            b.bind("<Enter>", lambda e, w=b: self._win_btn_hover(w, True))
            b.bind("<Leave>", lambda e, w=b: self._win_btn_hover(w, False))
            self._win_btns.append(b)
            return b
        win_btn("—", self._minimize)
        self._win_btn_max = win_btn("☐", self._toggle_maximize)
        win_btn("✕", self._on_close, danger=True)

        self.header_right = ttk.Frame(self.titlebar, style="Title.TFrame")
        self.header_right.pack(side="right", padx=(0, 16))
        self.enable_drag()

    def _win_btn_hover(self, w, inside: bool) -> None:
        p = getattr(self, "_palette", None) or {}
        if inside:
            w.configure(bg="#e81123" if getattr(w, "_danger", False) else p.get("hover", "#e5e7eb"),
                        fg="#ffffff" if getattr(w, "_danger", False) else p.get("text", "#111827"))
        else:
            w.configure(bg=p.get("surface", "#ffffff"), fg=p.get("muted", "#6b7280"))

    def _build_ui(self) -> None:
        # Scrollable page (only scrolls when the window is smaller than the content)
        self.root_scroll = _ScrollableFrame(self.root)
        self.root_scroll.pack(fill="both", expand=True)
        self.root_scroll.content.configure(style="App.TFrame")
        self.root_scroll.canvas.configure(borderwidth=0, highlightthickness=0)
        page = self.root_scroll.content

        # ---- header controls (live in the title bar) ----
        hr = self.header_right
        self._tooltips = {}
        self._tooltip_keys = {}
        # Icons + tooltips instead of text labels: long translations pushed the menu off-screen
        self.lbl_hdr_theme = ttk.Label(hr, text="◐", style="Title.TLabel")
        self.lbl_hdr_theme.pack(side="left", padx=(0, 6))
        self.theme_var = tk.StringVar(value=("dark" if self.dark_mode_var.get() else "light"))
        self.cmb_theme = ttk.Combobox(hr, state="readonly", width=8)
        self.cmb_theme.pack(side="left", padx=(0, 14))

        def _on_theme_pick(_e=None):
            dark = self.cmb_theme.current() == 1
            self.theme_var.set("dark" if dark else "light")
            self.dark_mode_var.set(dark)
            self._apply_theme()
            self._refresh_status_bar()
            self._save_settings()
        self.cmb_theme.bind("<<ComboboxSelected>>", _on_theme_pick)
        self.lbl_hdr_accent = ttk.Label(hr, text="🎨", style="Title.TLabel")
        self.lbl_hdr_accent.pack(side="left", padx=(0, 6))
        self.cmb_accent = ttk.Combobox(hr, state="readonly", width=10)
        self.cmb_accent.pack(side="left", padx=(0, 14))

        def _on_accent_pick(_e=None):
            idx = self.cmb_accent.current()
            if 0 <= idx < len(self.ACCENTS):
                self.accent_var.set(self.ACCENTS[idx])
            self._apply_theme()
            self._save_settings()
        self.cmb_accent.bind("<<ComboboxSelected>>", _on_accent_pick)
        self.lbl_hdr_ui = ttk.Label(hr, text="🌐", style="Title.TLabel")
        self.lbl_hdr_ui.pack(side="left", padx=(0, 6))
        self._rebuild_ui_lang_names()
        self.cmb_ui_quick = ttk.Combobox(hr, state="readonly", values=self.ui_lang_names, textvariable=self.ui_lang_var, width=16, height=20)
        self.cmb_ui_quick.pack(side="left", padx=(0, 10))
        self.cmb_ui_quick.bind("<<ComboboxSelected>>", self._on_ui_lang_change)
        self.header_menu_btn = ttk.Menubutton(hr, text="☰", width=2, style="Icon.TMenubutton")
        self.header_menu_btn.pack(side="left")
        self.header_menu = tk.Menu(self.header_menu_btn, tearoff=False)
        # The native menubar never showed (borderless window); everything lives here.
        self.header_menu.add_command(label=self._tr("Add..."), command=self._add_files)
        self.header_menu.add_command(label=self._tr("Settings..."), command=self._open_settings)
        self.header_menu.add_separator()
        self.header_menu.add_checkbutton(label=self._tr("Compact mode"), onvalue=True, offvalue=False, variable=self.compact_mode_var,
                                         command=lambda: (self._apply_theme(), self._save_settings()))
        self.header_font_menu = tk.Menu(self.header_menu, tearoff=False)
        for scale in (0.9, 1.0, 1.1, 1.2, 1.3):
            self.header_font_menu.add_radiobutton(label=f"{int(scale * 100)}%", value=scale, variable=self.font_scale_var,
                                                  command=lambda: (self._apply_font_scale(), self._save_settings()))
        self.header_menu.add_cascade(label=self._tr("Font size"), menu=self.header_font_menu)
        self.header_menu.add_separator()
        self.header_menu.add_command(label=self._tr("About"), command=self._show_about)
        self.header_menu.add_command(label=self._tr("Exit"), command=self._on_close)
        self._header_menu_keys = [(0, "Add..."), (1, "Settings..."), (3, "Compact mode"), (4, "Font size"),
                                  (6, "About"), (7, "Exit")]
        self.header_menu_btn.configure(menu=self.header_menu)
        self._sync_header_combos()
        for attr, w, key in (("hdr_theme", self.cmb_theme, "Theme:"), ("hdr_theme_i", self.lbl_hdr_theme, "Theme:"),
                             ("hdr_accent", self.cmb_accent, "Accent color:"), ("hdr_accent_i", self.lbl_hdr_accent, "Accent color:"),
                             ("hdr_ui", self.cmb_ui_quick, "UI language:"), ("hdr_ui_i", self.lbl_hdr_ui, "UI language:"),
                             ("hdr_menu", self.header_menu_btn, "Settings")):
            self._tooltip_keys[attr] = key
            self._tooltips[attr] = _Tooltip(w, self._tr(key).rstrip(":： "))

        # ---- body: queue + log (left, flexible) | translation + progress (right, fixed) ----
        body = ttk.Frame(page, style="App.TFrame")
        body.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0, minsize=360)
        body.rowconfigure(0, weight=1)
        self.left_col = ttk.Frame(body, style="App.TFrame")
        self.left_col.grid(row=0, column=0, sticky="nsew")
        self.right_col = ttk.Frame(body, style="App.TFrame")
        self.right_col.grid(row=0, column=1, sticky="nsew")
        def tip(attr: str, widget, text: str) -> None:
            self._tooltip_keys[attr] = text
            self._tooltips[attr] = _Tooltip(widget, self._tr(text))

        # Files card
        files_card = _RoundedCard(self.left_col, min_height=320)
        files_card.pack(fill="both", expand=True, padx=4, pady=4)
        self.lbl_files_header = self._build_section_header(files_card.content, self._tr("📁 Files"))
        self.frm_files = ttk.Frame(files_card.content)
        self.frm_files.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        top_row = ttk.Frame(self.frm_files)
        top_row.pack(fill="x")
        self.btn_add = ttk.Button(top_row, text=self._tr("Add..."), command=self._add_files, style="Accent.TButton")
        self.btn_add.pack(side="left")
        self.btn_remove = ttk.Button(top_row, text=self._tr("Remove"), command=self._remove_selected)
        self.btn_remove.pack(side="left", padx=6)
        self.btn_clear = ttk.Button(top_row, text=self._tr("Clear"), command=self._clear_files)
        self.btn_clear.pack(side="left")
        self.tb_add = self.btn_add
        self.tb_remove_selected = self.btn_remove
        self.toolbar = ttk.Frame(top_row)
        self.toolbar.pack(side="right")
        for attr, icon, text, cmd in (
            ("tb_remove_missing", "🧹", "Remove missing", self._remove_missing),
            ("tb_preview", "👁", "Preview", self._preview_selected),
            ("tb_open_selected_out", "📄", "Open selected output", self._open_selected_output),
            ("tb_open_selected_outdir", "📂", "Open selected out folder", self._open_selected_output_folder),
            ("tb_reveal_src", "🗂", "Reveal in Explorer", self._reveal_in_explorer),
            ("tb_toggle_adv", "⚙", "Settings...", self._open_settings),
        ):
            b = ttk.Button(self.toolbar, text=icon, width=3, command=cmd, style="Icon.TButton")
            b.pack(side="left", padx=1)
            setattr(self, attr, b)
            tip(attr, b, text)
        self._adv_visible = False
        # Filter with a real placeholder
        filter_row = ttk.Frame(self.frm_files)
        filter_row.pack(fill="x", pady=(10, 8))
        self.filter_var = tk.StringVar()
        self.ent_filter = ttk.Entry(filter_row, textvariable=self.filter_var)
        self.ent_filter.pack(fill="x")
        self._filter_placeholder_on = False

        def _filter_placeholder(show: bool) -> None:
            if show and not self.filter_var.get():
                self._filter_placeholder_on = True
                self.ent_filter.configure(style="Placeholder.TEntry")
                self.filter_var.set("🔎  " + self._tr("Filter files..."))
            elif not show and self._filter_placeholder_on:
                self._filter_placeholder_on = False
                self.ent_filter.configure(style="TEntry")
                self.filter_var.set("")
        self._filter_placeholder = _filter_placeholder
        self.ent_filter.bind("<FocusIn>", lambda e: _filter_placeholder(False))
        self.ent_filter.bind("<FocusOut>", lambda e: _filter_placeholder(True))
        self.ent_filter.bind("<KeyRelease>", lambda e: self._apply_filter("" if self._filter_placeholder_on else self.filter_var.get().strip()))
        _filter_placeholder(True)
        tip("ent_filter", self.ent_filter, "Type to filter by filename")
        # Queue
        tree_wrap = ttk.Frame(self.frm_files, style="Field.TFrame")
        tree_wrap.pack(fill="both", expand=True)
        cols = ("dosya", "boyut", "durum", "eklenme")
        self.tree = ttk.Treeview(tree_wrap, columns=cols, show="headings", height=10, selectmode="extended")
        self.tree.heading("dosya", text=self._tr("File"), anchor="w")
        self.tree.heading("boyut", text=self._tr("Size"))
        self.tree.heading("durum", text=self._tr("Status"))
        self.tree.heading("eklenme", text=self._tr("Added"))
        self.tree.column("dosya", width=320, minwidth=180, anchor="w", stretch=True)
        self.tree.column("boyut", width=90, minwidth=70, anchor="e", stretch=False)
        self.tree.column("durum", width=150, minwidth=100, anchor="center", stretch=False)
        self.tree.column("eklenme", width=140, minwidth=110, anchor="center", stretch=False)
        tree_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview, style="Modern.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", self._on_preview_event)
        for c in cols:
            self.tree.heading(c, command=lambda c=c: self._sort_by_column(c))
        # Empty state shown over the list while the queue is empty
        self.empty_state = tk.Frame(self.tree, bd=0, cursor="hand2")
        self.lbl_empty_icon = tk.Label(self.empty_state, text="⇩", bd=0)
        self.lbl_empty_icon.pack()
        self.lbl_empty_title = tk.Label(self.empty_state, text="", bd=0)
        self.lbl_empty_title.pack(pady=(4, 2))
        self.lbl_empty_sub = tk.Label(self.empty_state, text="", bd=0)
        self.lbl_empty_sub.pack()
        for w in (self.empty_state, self.lbl_empty_icon, self.lbl_empty_title, self.lbl_empty_sub):
            w.bind("<Button-1>", lambda e: self._add_files())

        # Context menu
        self.tree_menu = tk.Menu(self.root, tearoff=False)
        self.tree_menu.add_command(label=self._tr("Preview"), command=self._preview_selected)
        self.tree_menu.add_command(label=self._tr("Remove"), command=self._remove_selected)
        self.tree_menu.add_separator()
        self.tree_menu.add_command(label=self._tr("Open folder"), command=lambda: self._open_folder_selected())

        def _open_menu(ev):
            try:
                iid = self.tree.identify_row(ev.y)
                if iid:
                    self.tree.selection_set(iid)
                self.tree_menu.tk_popup(ev.x_root, ev.y_root)
            finally:
                self.tree_menu.grab_release()
        self.tree.bind("<Button-3>", _open_menu)
        if TkinterDnD and DND_FILES:
            for target in (self.tree, self.empty_state, self.lbl_empty_title):
                try:
                    target.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
                    target.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore[attr-defined]
                except Exception:
                    pass

        # Log card
        log_card = _RoundedCard(self.left_col, min_height=180)
        log_card.pack(fill="x", padx=4, pady=(4, 4))
        self.lbl_log_header = self._build_section_header(log_card.content, self._tr("📝 Log"))
        frm_log = ttk.Frame(log_card.content)
        frm_log.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        lvl = ttk.Frame(frm_log)
        lvl.pack(fill="x", pady=(0, 6))
        self.chk_log_info = ttk.Checkbutton(lvl, text=self._tr("Info"), variable=self.log_info_var, command=self._refresh_log_view)
        self.chk_log_info.pack(side="left")
        self.chk_log_ok = ttk.Checkbutton(lvl, text=self._tr("OK"), variable=self.log_ok_var, command=self._refresh_log_view)
        self.chk_log_ok.pack(side="left", padx=(12, 0))
        self.chk_log_err = ttk.Checkbutton(lvl, text=self._tr("Error"), variable=self.log_err_var, command=self._refresh_log_view)
        self.chk_log_err.pack(side="left", padx=(12, 0))
        self.btn_log_clear = ttk.Button(lvl, text=self._tr("Clear"), command=lambda: (self._log_entries.clear(), self._refresh_log_view()), style="Small.TButton")
        self.btn_log_clear.pack(side="right")
        self.btn_log_export = ttk.Button(lvl, text=self._tr("Export..."), command=self._export_logs, style="Small.TButton")
        self.btn_log_export.pack(side="right", padx=(0, 6))
        log_wrap = ttk.Frame(frm_log, style="Field.TFrame")
        log_wrap.pack(fill="both", expand=True)
        self.txt_log = tk.Text(log_wrap, height=6, wrap="word", bd=0, highlightthickness=0, padx=10, pady=8)
        log_scroll = ttk.Scrollbar(log_wrap, orient="vertical", command=self.txt_log.yview, style="Modern.Vertical.TScrollbar")
        self.txt_log.configure(yscrollcommand=log_scroll.set, state="disabled")
        log_scroll.pack(side="right", fill="y")
        self.txt_log.pack(side="left", fill="both", expand=True)

        # Translation card (right)
        tr_card = _RoundedCard(self.right_col, min_height=250)
        tr_card.pack(fill="x", padx=4, pady=4)
        self.lbl_translate_header = self._build_section_header(tr_card.content, self._tr("🌍 Translation"))
        frm_lang = ttk.Frame(tr_card.content)
        frm_lang.pack(fill="x", padx=14, pady=(0, 14))
        self.lbl_target = ttk.Label(frm_lang, text=self._tr("Target language:"), style="Muted.TLabel")
        self.lbl_target.pack(anchor="w")
        try:
            self._rebuild_target_lang_names()
        except Exception:
            pass
        self.cmb_lang = ttk.Combobox(frm_lang, values=(self.target_lang_names or self.lang_names), textvariable=self.target_lang_var, state="readonly", height=20)
        self.cmb_lang.pack(fill="x", pady=(4, 12))
        self.cmb_lang.bind("<<ComboboxSelected>>", lambda e: (self._maybe_update_output_suggestion(), self._save_settings()))
        self.lbl_engine_main = ttk.Label(frm_lang, text=self._tr("Engine:"), style="Muted.TLabel")
        self.lbl_engine_main.pack(anchor="w")
        chips = ttk.Frame(frm_lang)
        chips.pack(fill="x", pady=(4, 14))
        self.engine_radios: Dict[str, object] = {}
        engines = (
            ("auto", "Auto", "Google first, MyMemory as fallback"),
            ("google", "Google", "Google Translate (no key)"),
            ("mymemory", "MyMemory", "MyMemory (no key, small daily quota)"),
            ("deepl", "DeepL", "DeepL API (requires API key)"),
            ("deepl_web", "DeepL (Web)", "DeepL website automation (experimental)"),
            ("libre", "Libre", "LibreTranslate (self-hosted or API key)"),
        )
        for i, (val, txt, ttip) in enumerate(engines):
            rb = ttk.Radiobutton(chips, text=self._tr(txt), value=val, variable=self.engine_var, style="Chip.Toolbutton",
                                 command=lambda: (self._refresh_status_bar(), self._save_settings()))
            rb.grid(row=i // 3, column=i % 3, sticky="ew", padx=2, pady=2)
            self.engine_radios[val] = rb
            tip(f"engine_{val}", rb, ttip)
        for col in range(3):
            chips.columnconfigure(col, weight=1, uniform="chips")
        run_row = ttk.Frame(frm_lang)
        run_row.pack(fill="x")
        # Cancel is packed first so the expanding Start button can never squeeze it
        self.tb_cancel = ttk.Button(run_row, text=self._tr("⏹ Cancel"), command=self._cancel_run, state="disabled", style="Danger.TButton")
        self.tb_cancel.pack(side="right", fill="y", padx=(6, 0))
        self.tb_start = ttk.Button(run_row, text=self._tr("▶ Start"), command=self._start, style="Big.Accent.TButton")
        self.tb_start.pack(side="left", fill="x", expand=True)
        self.tb_start_sel_text = tk.StringVar(value="▶ " + self._tr("Translate selected files"))
        self.tb_start_sel = ttk.Button(frm_lang, textvariable=self.tb_start_sel_text, command=self._start_selected)
        self.tb_start_sel.pack(fill="x", pady=(8, 0))
        tip("tb_start", self.tb_start, "Start translation (Ctrl+R)")
        tip("tb_cancel", self.tb_cancel, "Cancel (Esc)")
        tip("tb_start_sel", self.tb_start_sel, "Translate only the selected files (Ctrl+Shift+R)")
        tip("btn_add", self.btn_add, "Add files (Ctrl+O)")
        tip("btn_remove", self.btn_remove, "Remove selected files from the list")

        # Progress card (right)
        prog_card = _RoundedCard(self.right_col, min_height=230)
        prog_card.pack(fill="both", expand=True, padx=4, pady=4)
        self.lbl_progress_header = self._build_section_header(prog_card.content, self._tr("⌛ Progress"))
        frm_prog = ttk.Frame(prog_card.content)
        frm_prog.pack(fill="x", padx=14, pady=(0, 14))
        self.circ = _CircularProgress(frm_prog, size=148, thickness=12)
        self.circ.pack(pady=(0, 10))
        self.pbar = ttk.Progressbar(frm_prog, variable=self.progress_var, maximum=100, style="Thin.Horizontal.TProgressbar")
        self.pbar.pack(fill="x")
        self.lbl_status = ttk.Label(frm_prog, textvariable=self.status_var, wraplength=320, justify="left", style="Muted.TLabel")
        self.lbl_status.pack(anchor="w", fill="x", pady=(8, 0))

        # Footer: output controls + status
        foot_card = _RoundedCard(page, min_height=60)
        foot_card.pack(fill="x", padx=14, pady=(4, 12))
        self.lbl_output_header = self._build_section_header(foot_card.content, self._tr("📦 Output"))
        footer = ttk.Frame(foot_card.content)
        footer.pack(fill="x", padx=14, pady=(0, 12))
        self.chk_save_next_main = ttk.Checkbutton(footer, text=self._tr("Save next to source"), variable=self.save_next_var, command=self._save_settings)
        self.chk_save_next_main.pack(side="left")
        self.lbl_outdir_main = ttk.Label(footer, text=self._tr("Output directory:"), style="Muted.TLabel")
        self.lbl_outdir_main.pack(side="left", padx=(16, 6))
        # buttons are packed (from the right) before the expanding entry, so they are never squeezed
        self.btn_open_out_main = ttk.Button(footer, text=self._tr("Open output folder"), command=self._open_outdir)
        self.btn_open_out_main.pack(side="right", padx=(6, 0))
        self.btn_browse_main = ttk.Button(footer, text=self._tr("Browse"), command=self._choose_outdir)
        self.btn_browse_main.pack(side="right", padx=(6, 0))
        self.ent_outdir_main = ttk.Entry(footer, textvariable=self.outdir_var, width=20)
        self.ent_outdir_main.pack(side="left", fill="x", expand=True)
        self.status_bar = ttk.Label(foot_card.content, text="", style="Muted.TLabel")
        self.status_bar.pack(side="right", padx=14, pady=(0, 10))
        self.card_contexts = [(files_card, ''), (log_card, ''), (tr_card, ''), (prog_card, ''), (foot_card, '')]
        dnd_text = "(Drag-and-drop supported)" if (TkinterDnD and DND_FILES) else "(Install tkinterdnd2 for drag-and-drop)"
        self.lbl_dnd = ttk.Label(foot_card.content, text=self._tr(dnd_text), style="Muted.TLabel")
        self.lbl_dnd.pack(side="left", padx=14, pady=(0, 10))

        # ---- hidden widgets kept for dialogs / retranslation compatibility ----
        self._hidden = ttk.Frame(self.root)
        self.adv_container = self._hidden
        self.adv_inner = self._hidden
        self.adv_canvas = tk.Canvas(self._hidden)
        self.sep_hdr = ttk.Separator(self._hidden)
        self.frm_out = ttk.LabelFrame(self._hidden, text=self._tr("Output"))
        self.chk_save_next = ttk.Checkbutton(self.frm_out, text=self._tr("Save next to source"), variable=self.save_next_var)
        self.lbl_outdir = ttk.Label(self.frm_out, text=self._tr("Output directory:"))
        self.ent_outdir = ttk.Entry(self.frm_out, textvariable=self.outdir_var)
        self.btn_browse = ttk.Button(self.frm_out, text=self._tr("Browse"), command=self._choose_outdir)
        self.btn_open_out = ttk.Button(self.frm_out, text=self._tr("Open output folder"), command=self._open_outdir)
        self.chk_clean = ttk.Checkbutton(self.frm_out, text=self._tr("Remove [bracketed] notes from SRT after translate"), variable=self.clean_after_var)
        self.frm_adv = ttk.LabelFrame(self._hidden, text=self._tr("Advanced Settings"))
        self.lbl_batch = ttk.Label(self.frm_adv, text=self._tr("Batch size (Google batch):"))
        self.lbl_mm = ttk.Label(self.frm_adv, text=self._tr("Fallback concurrent jobs (MyMemory):"))
        self.lbl_engine = ttk.Label(self.frm_adv, text=self._tr("Engine:"))
        self.cmb_engine = ttk.Combobox(self.frm_adv, values=["auto", "google", "mymemory", "deepl", "deepl_web", "libre"], textvariable=self.engine_var, state="readonly")
        self.lbl_auto_priority = ttk.Label(self.frm_adv, text=self._tr("Auto priority:"))
        self.cmb_auto_priority = ttk.Combobox(self.frm_adv, values=["google_first", "mymemory_first"], textvariable=self.auto_priority_var, state="readonly")
        self.frm_perf = ttk.LabelFrame(self._hidden, text=self._tr("Appearance & Performance"))
        self.chk_dark = ttk.Checkbutton(self.frm_perf, text=self._tr("Dark theme"), variable=self.dark_mode_var, command=self._apply_theme)
        self.chk_parallel = ttk.Checkbutton(self.frm_perf, text=self._tr("Translate files in parallel"), variable=self.parallel_files_var)
        self.lbl_workers = ttk.Label(self.frm_perf, text=self._tr("Workers:"))
        self.btn_preview = ttk.Button(self.frm_perf, text=self._tr("Preview"), command=self._preview_selected)
        self.chk_compact = ttk.Checkbutton(self._hidden, text=self._tr("Compact mode"), variable=self.compact_mode_var)

        # initial design + texts (window is still hidden here)
        self._apply_theme()
        self._retranslate_ui(initial=True)
        self._apply_font_scale()
        self._ensure_ui_font_family()
        self._update_empty_state()
        # Shortcuts
        self.root.bind_all("<Control-o>", lambda e: self._add_files())
        self.root.bind_all("<Control-O>", lambda e: self._add_files())
        self.root.bind_all("<Control-r>", lambda e: self._start())
        self.root.bind_all("<Control-R>", lambda e: self._start())
        self.root.bind_all("<Control-Shift-R>", lambda e: self._start_selected())
        self.root.bind_all("<Escape>", lambda e: self._cancel_run())
        self._refresh_status_bar()

    def _update_empty_state(self) -> None:
        """Big drop target over the queue while it is empty."""
        try:
            self.lbl_empty_title.configure(text=self._tr("Drop subtitle or document files here"))
            self.lbl_empty_sub.configure(text=self._tr("or click Add... to choose files") + "   ·   SRT · VTT · TXT · MD · CSV · DOCX · PDF")
            if self.tree.get_children(""):
                self.empty_state.place_forget()
            else:
                self.empty_state.place(relx=0.5, rely=0.55, anchor="center")
        except Exception:
            pass

    def _fmt_size(self, n: int) -> str:
        try:
            f = float(n)
            for unit in ("B", "KB", "MB", "GB", "TB"):
                if f < 1024.0:
                    return f"{f:.1f} {unit}"
                f /= 1024.0
            return f"{f:.1f} PB"
        except Exception:
            return str(n)

    def _refresh_status_bar(self) -> None:
        self._update_empty_state()
        try:
            cnt = len(self.files)
            # Uses the hand-checked keys ("light"/"theme" alone were mistranslated, e.g. ja "光")
            theme = self._tr("Dark mode") if self.dark_mode_var.get() else self._tr("Light mode")
            eng = self.engine_var.get()
            engine_lbl = self._tr("Engine:").rstrip(":： ")
            self.status_bar.configure(text=f"{cnt} {self._tr('files')}  ·  {engine_lbl}: {eng}  ·  {theme}")
            try:
                # Keep the idle ETA label localized, but never reset a running progress ring
                running = bool(getattr(self, '_thread', None)) and self._thread.is_alive()
                if hasattr(self, 'circ') and not running:
                    self.circ.set(0, f"{self._tr('ETA')}: --:--")
            except Exception:
                pass
        except Exception:
            pass

    # ---------- i18n ----------
    def _on_ui_lang_change(self, event=None) -> None:
        try:
            # Preserve current target language selection by code across UI language switches
            try:
                current_target_name = self.target_lang_var.get()
                prev_code = None
                if getattr(self, 'target_lang_map', None):
                    prev_code = self.target_lang_map.get(current_target_name)
                if not prev_code:
                    prev_code = self.lang_map.get(current_target_name)
            except Exception:
                prev_code = None
            self.ui_lang_code = self.ui_lang_map.get(self.ui_lang_var.get(), "en")
            try:
                import sys as _sys
                setattr(_sys.modules[__name__], "_CURRENT_UI_LANG_CODE", self.ui_lang_code)
            except Exception:
                pass
        except Exception:
            self.ui_lang_code = self.lang_map.get(self.ui_lang_var.get(), "en")
        # Rebuild localized UI language names to reflect the new UI language
        try:
            self._rebuild_ui_lang_names()
            if hasattr(self, 'cmb_ui_quick'):
                self.cmb_ui_quick.configure(values=self.ui_lang_names)
        except Exception:
            pass
        # Rebuild target language names to match new UI language
        try:
            # Rebuild base language map with current UI to ensure consistent naming
            try:
                self.lang_map = _get_supported_langs(self.ui_lang_code)
            except Exception:
                pass
            self._rebuild_target_lang_names()
            if hasattr(self, 'cmb_lang'):
                self.cmb_lang.configure(values=(self.target_lang_names or self.lang_names))
            # Reselect previous target language by code if available
            try:
                if prev_code:
                    new_name = next((n for n,c in self.target_lang_map.items() if c == prev_code), None)
                    if new_name:
                        self.target_lang_var.set(new_name)
            except Exception:
                pass
        except Exception:
            pass
        # (A synchronous Google request used to run here and could freeze the window.)
        self._retranslate_ui()
        # Persist selection
        try:
            self._save_settings()
        except Exception:
            pass

    def _translate_texts(self, texts: List[str], target_code: str) -> Dict[str, str]:
        # JSON packs only (cached in memory); never blocks the UI on network
        return {t: _ui_translate(t, target_code) for t in texts}

    def _retranslate_ui(self, initial: bool = False) -> None:
        keys = {
            "title": "Subtitle PRO – Multi Translator",
            "files": "Files",
            "size": "Size",
            "added": "Added",
            "add": "Add...",
            "remove": "Remove",
            "clear": "Clear",
            "dnd_yes": "(Drag-and-drop supported)",
            "dnd_no": "(Install tkinterdnd2 for drag-and-drop)",
            "file": "File",
            "status": "Status",
            "target": "Target language:",
            "start": "Start",
            "cancel": "Cancel",
            "adv": "Advanced Settings",
            "batch": "Batch size (Google batch):",
            "mm": "Fallback concurrent jobs (MyMemory):",
            "perf": "Appearance & Performance",
            "dark": "Dark theme",
            "ui_lang": "UI language:",
            "parallel": "Translate files in parallel",
            "workers": "Workers:",
            "engine": "Engine:",
            "dict": "Custom dictionary:",
            "dict_browse": "Browse",
            "output": "Output",
            "save_next": "Save next to source",
            "out_dir": "Output directory:",
            "browse": "Browse",
            "open_out": "Open output folder",
            "preview": "Preview",
            "ready": "Ready",
            "must_add": "Add at least one file (SRT/VTT/TXT/MD/CSV/DOCX/PDF).",
            "translating": "Translating",
            "completed": "Completed",
            "canceled": "Canceled",
            "error": "Error",
            "translation_started": "Translation started...",
            "canceling": "Canceling...",
            "remaining": "Remaining",
            "seconds_short": "s",
        }
        texts = list(keys.values())
        mapping = self._translate_texts(texts, self.ui_lang_code)
        def tr(k: str) -> str:
            base = keys[k]
            return mapping.get(base, base)
        try:
            self.root.title(tr("title"))
            # Header quick labels
            if hasattr(self, 'lbl_hdr_theme'):
                pass  # header uses icons + tooltips
            if hasattr(self, 'lbl_hdr_accent'):
                pass  # header uses icons + tooltips
            if hasattr(self, 'lbl_hdr_ui'):
                pass  # header uses icons + tooltips
            if hasattr(self, 'lbl_files_header'):
                self.lbl_files_header.configure(text=self._tr("📁 Files"))
            if hasattr(self, 'lbl_tools_header'):
                self.lbl_tools_header.configure(text=self._tr("🛠 Tools"))
            if hasattr(self, 'lbl_progress_header'):
                self.lbl_progress_header.configure(text=self._tr("⌛ Progress"))
            if hasattr(self, 'lbl_log_header'):
                self.lbl_log_header.configure(text=self._tr("📝 Log"))
            if hasattr(self, 'lbl_output_header'):
                self.lbl_output_header.configure(text=self._tr("📦 Output"))
            self.btn_add.configure(text=tr("add"))
            self.btn_remove.configure(text=tr("remove"))
            self.btn_clear.configure(text=tr("clear"))
            # toolbar buttons
            self.tb_start.configure(text=tr("start"))
            self.tb_cancel.configure(text=tr("cancel"))
            self.lbl_dnd.configure(text=tr("dnd_yes") if (TkinterDnD and DND_FILES) else tr("dnd_no"))
            self.tree.heading("dosya", text=tr("file"))
            if 'boyut' in self.tree["columns"]:
                self.tree.heading("boyut", text=tr("size"))
            if 'durum' in self.tree["columns"]:
                self.tree.heading("durum", text=tr("status"))
            if 'eklenme' in self.tree["columns"]:
                self.tree.heading("eklenme", text=tr("added"))
            self.lbl_target.configure(text=tr("target"))
            try:
                self.tb_start.configure(text=tr("start"))
            except Exception:
                pass
            try:
                self.tb_cancel.configure(text=tr("cancel"))
            except Exception:
                pass
            self.frm_adv.configure(text=tr("adv"))
            self.lbl_batch.configure(text=tr("batch"))
            self.lbl_mm.configure(text=tr("mm"))
            self.lbl_engine.configure(text=self._tr("Engine:"))
            self.lbl_auto_priority.configure(text=self._tr("Auto priority:"))
            # engine/dict
            self.cmb_engine.configure(values=["auto", "google", "mymemory", "deepl", "deepl_web", "libre"])
            self.frm_adv.configure(text=tr("adv"))
            # direct labels for engine/dict
            # We keep static English label texts minimal to avoid lookup complexity
            self.frm_perf.configure(text=tr("perf"))
            self.chk_dark.configure(text=tr("dark"))
            if hasattr(self, 'chk_compact'):
                try:
                    self.chk_compact.configure(text=self._tr("Compact mode"))
                except Exception:
                    pass
            self.chk_parallel.configure(text=tr("parallel"))
            self.lbl_workers.configure(text=tr("workers"))
            if hasattr(self, 'btn_save_queue'):
                try: self.btn_save_queue.configure(text=self._tr("Save queue"))
                except Exception: pass
            if hasattr(self, 'btn_load_queue'):
                try: self.btn_load_queue.configure(text=self._tr("Load queue"))
                except Exception: pass
            if hasattr(self, 'chk_case_ins'):
                try: self.chk_case_ins.configure(text=self._tr("Case-insensitive terms"))
                except Exception: pass
            if hasattr(self, 'chk_word_boundary'):
                try: self.chk_word_boundary.configure(text=self._tr("Word-boundary only"))
                except Exception: pass
            self.btn_preview.configure(text=self._tr("Preview"))
            # toolbar buttons refresh (language switch)
            if hasattr(self, 'tb_start'):
                try: self.tb_start.configure(text=self._tr("▶ Start"))
                except Exception: pass
            if hasattr(self, 'tb_start_sel_text'):
                try:
                    self.tb_start_sel_text.set("▶ " + self._tr("Translate selected files"))
                except Exception:
                    pass
            # tb_start_sel uses a StringVar; above we already set tb_start_sel_text
            if hasattr(self, 'tb_cancel'):
                try: self.tb_cancel.configure(text=self._tr("⏹ Cancel"))
                except Exception: pass
            # Output section
            for w in self.root.winfo_children():
                pass
            # find last LabelFrame (frm_out)
            # We saved references when building
            self.frm_out.configure(text=self._tr("Output"))
            self.chk_save_next.configure(text=self._tr("Save next to source"))

            # Menubar texts (if created)
            try:
                if hasattr(self, 'menubar'):
                    # Rebuild cascade labels
                    self.menubar.entryconfigure(0, label=self._tr("File"))
                    self.menubar.entryconfigure(1, label=self._tr("View"))
                    self.menubar.entryconfigure(2, label=self._tr("Settings"))
                    self.menubar.entryconfigure(3, label=self._tr("Help"))
                if hasattr(self, 'm_view'):
                    # Update submenu cascade labels
                    # Find and update known child cascades by label indices if present
                    # Bootstrap theme
                    for i in range(self.m_view.index('end') + 1):
                        try:
                            lbl = self.m_view.entrycget(i, 'label')
                            if lbl in ("Bootstrap theme", self._tr("Bootstrap theme")):
                                self.m_view.entryconfigure(i, label=self._tr("Bootstrap theme"))
                            elif lbl.endswith("%"):
                                pass
                        except Exception:
                            pass
                    # Update known checkbuttons by index if present
                    try:
                        self.m_view.entryconfigure(0, label=self._tr("Dark theme"))
                    except Exception:
                        pass
                    try:
                        self.m_view.entryconfigure(1, label=self._tr("Compact mode"))
                    except Exception:
                        pass
                # Update File menu items
                if hasattr(self, 'm_file'):
                    try:
                        self.m_file.entryconfigure(0, label=self._tr("Add..."))
                    except Exception:
                        pass
                    try:
                        self.m_file.entryconfigure(2, label=self._tr("Exit"))
                    except Exception:
                        pass
                # Update Settings menu items
                if hasattr(self, 'm_settings'):
                    try:
                        self.m_settings.entryconfigure(0, label=self._tr("Output settings..."))
                    except Exception:
                        pass
                    try:
                        self.m_settings.entryconfigure(1, label=self._tr("Advanced settings..."))
                    except Exception:
                        pass
                    try:
                        self.m_settings.entryconfigure(3, label=self._tr("Preferences..."))
                    except Exception:
                        pass
                # Update Help menu items
                if hasattr(self, 'm_help'):
                    try:
                        self.m_help.entryconfigure(0, label=self._tr("About"))
                    except Exception:
                        pass
                # Update tree context menu items
                if hasattr(self, 'tree_menu') and self.tree_menu is not None:
                    try:
                        self.tree_menu.entryconfigure(0, label=self._tr("Preview"))
                    except Exception:
                        pass
                    try:
                        self.tree_menu.entryconfigure(1, label=self._tr("Remove"))
                    except Exception:
                        pass
                    try:
                        # index 2 is a separator
                        self.tree_menu.entryconfigure(3, label=self._tr("Open folder"))
                    except Exception:
                        pass
            except Exception:
                pass
            self.lbl_outdir.configure(text=self._tr("Output directory:"))
            self.btn_browse.configure(text=self._tr("Browse"))
            self.btn_open_out.configure(text=self._tr("Open output folder"))
            # Log panel controls
            if hasattr(self, 'chk_log_info'):
                try: self.chk_log_info.configure(text=self._tr("Info"))
                except Exception: pass
            if hasattr(self, 'chk_log_ok'):
                try: self.chk_log_ok.configure(text=self._tr("OK"))
                except Exception: pass
            if hasattr(self, 'chk_log_err'):
                try: self.chk_log_err.configure(text=self._tr("Error"))
                except Exception: pass
            if hasattr(self, 'btn_log_clear'):
                try: self.btn_log_clear.configure(text=self._tr("Clear"))
                except Exception: pass
            if hasattr(self, 'btn_log_export'):
                try: self.btn_log_export.configure(text=self._tr("Export..."))
                except Exception: pass
            # Footer output controls (visible at bottom)
            if hasattr(self, 'chk_save_next_main'):
                try: self.chk_save_next_main.configure(text=self._tr("Save next to source"))
                except Exception: pass
            if hasattr(self, 'lbl_outdir_main'):
                try: self.lbl_outdir_main.configure(text=self._tr("Output directory:"))
                except Exception: pass
            if hasattr(self, 'btn_browse_main'):
                try: self.btn_browse_main.configure(text=self._tr("Browse"))
                except Exception: pass
            if hasattr(self, 'btn_open_out_main'):
                try: self.btn_open_out_main.configure(text=self._tr("Open output folder"))
                except Exception: pass
            self._retranslate_new_layout()
            running = bool(getattr(self, '_thread', None)) and self._thread.is_alive()
            if initial or not running:
                self.status_var.set(tr("ready"))
        except Exception:
            pass

    def _tr(self, text: str) -> str:
        return _ui_translate(text, getattr(self, "ui_lang_code", "en"))

    def _fmt_progress_label(self, pct: float, remaining_sec: int, fi: int, file_total: int, name: str,
                            words_done: int = 0, words_total: int = 0, elapsed_sec: int = 0) -> str:
        sec = self._tr("s")
        parts = [f"{fi}/{file_total}  {int(pct)}%  {name}"]
        if words_total:
            parts.append(f"{self._tr('Words')}: {words_done}/{words_total}")
        parts.append(f"{self._tr('Elapsed')}: {int(elapsed_sec)} {sec}")
        parts.append(f"{self._tr('Remaining')}: {int(remaining_sec)} {sec}")
        return "  ·  ".join(parts)

    # ---------- Preview & language detect ----------
    def _on_preview_event(self, event=None) -> None:
        self._preview_selected()

    def _detect_language_hint(self, text: str) -> str:
        try:
            if not text.strip():
                return "?"
            tr = GoogleTranslator(source="auto", target="en")
            tr.translate(text[:5000])
            detected = getattr(tr, "source", None)
            return detected or "?"
        except Exception:
            return "?"

    def _apply_terms(self, text: str, terms: Dict[str, str]) -> str:
        # Apply dictionary with options
        if not terms:
            return text
        result = text
        ci = bool(self.dict_case_ins_var.get()) if hasattr(self, 'dict_case_ins_var') else False
        wb = bool(self.dict_word_boundary_var.get()) if hasattr(self, 'dict_word_boundary_var') else False
        if not ci and not wb:
            for src, dst in terms.items():
                if not src:
                    continue
                result = result.replace(src, dst)
            return result
        import re as _re
        flags = _re.IGNORECASE if ci else 0
        for src, dst in terms.items():
            if not src:
                continue
            pattern = _re.escape(src)
            if wb:
                pattern = r"\b" + pattern + r"\b"
            try:
                result = _re.sub(pattern, dst, result, flags=flags)
            except Exception:
                # fallback simple replace
                result = result.replace(src, dst)
        return result

    def _default_bs_theme(self) -> str:
        try:
            return "darkly" if bool(self.dark_mode_var.get()) else "flatly"
        except Exception:
            return "flatly"

    def _refresh_menu_bar(self) -> None:
        try:
            if hasattr(self.root, "menu"):
                try:
                    self.root.config(menu=self.root["menu"])
                except Exception:
                    pass
        except Exception:
            pass

    def _init_base_fonts(self) -> None:
        try:
            # cache a few common named fonts to scale later
            for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont", "TkFixedFont"):
                try:
                    fnt = tkfont.nametofont(name)
                    self._base_fonts[name] = fnt
                    try:
                        sz = fnt.cget('size')
                        if isinstance(sz, int):
                            self._base_font_sizes[name] = sz
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass

    # ---------- Output helpers ----------
    def _choose_outdir(self) -> None:
        path = filedialog.askdirectory(title=self._tr("Select output directory"))
        if path:
            self.outdir_var.set(path)

    # ---------- Dialogs ----------
    APP_VERSION = "0.2.0"
    REPO_URL = "https://github.com/noms6/subtitle-pro"

    def _make_dialog(self, title: str, width: int, height: int, modal: bool = False):
        """Common themed dialog: centred over the main window, native frame, consistent padding."""
        win = tk.Toplevel(self.root)
        win.withdraw()
        win.title(title)
        try:
            win.iconphoto(False, self._app_icon)
        except Exception:
            pass
        win.transient(self.root)
        self._apply_theme_to_toplevel(win)
        self.root.update_idletasks()
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = max(self.root.winfo_width(), width), max(self.root.winfo_height(), height)
        win.geometry(f"{width}x{height}+{rx + (rw - width) // 2}+{ry + max(40, (rh - height) // 3)}")
        win.minsize(min(width, 520), min(height, 360))
        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=18, pady=(16, 8))
        footer = ttk.Frame(win)
        footer.pack(fill="x", padx=18, pady=(0, 16))
        win.deiconify()
        if modal:
            win.grab_set()
        win.bind("<Escape>", lambda e: win.destroy())
        return win, body, footer

    def _labeled(self, parent, label: str, hint: str = "", grid=None):
        """Form field: muted label (with an ⓘ tooltip for the hint) above the control.
        Returns the row frame the control goes into. grid=(row, col) places it in a 2-column form."""
        box = ttk.Frame(parent)
        if grid is None:
            box.pack(fill="x", pady=(0, 14))
        else:
            box.grid(row=grid[0], column=grid[1], sticky="ew", padx=(0, 18) if grid[1] == 0 else 0, pady=(0, 14))
        head = ttk.Frame(box)
        head.pack(fill="x")
        ttk.Label(head, text=self._tr(label), style="Muted.TLabel").pack(side="left")
        if hint:
            info = ttk.Label(head, text=" ⓘ", style="Muted.TLabel", cursor="question_arrow")
            info.pack(side="left")
            _Tooltip(info, self._tr(hint), delay_ms=150)
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(4, 0))
        return row

    def _keyed_combo(self, parent, var, items, width=22):
        """Combobox showing translated labels for internal keys (no more raw 'google_first' / 'pre')."""
        cb = ttk.Combobox(parent, state="readonly", width=width, values=[self._tr(lbl) for _k, lbl in items])
        keys = [k for k, _l in items]
        try:
            cb.current(keys.index(var.get()))
        except ValueError:
            cb.current(0)
        cb.bind("<<ComboboxSelected>>", lambda e: (var.set(keys[cb.current()]), self._save_settings()))
        return cb

    def _open_settings(self, tab: str = "appearance") -> None:
        """One settings window (was three overlapping ones: Output, Preferences, a full-screen Advanced)."""
        win, body, footer = self._make_dialog(self._tr("Settings"), 700, 520)
        nb = ttk.Notebook(body)
        nb.pack(fill="both", expand=True)
        tabs = {}
        for key, label in (("appearance", "Appearance"), ("translation", "Translation"), ("output", "Output"),
                           ("dictionary", "Dictionary")):
            f = ttk.Frame(nb)
            nb.add(f, text=self._tr(label))
            inner = ttk.Frame(f)
            inner.pack(fill="both", expand=True, padx=16, pady=16)
            tabs[key] = inner

        # Appearance
        t = tabs["appearance"]
        row = self._labeled(t, "Theme:")
        theme_cb = self._keyed_combo(row, self.theme_var, [("light", "Light mode"), ("dark", "Dark mode")], 18)
        theme_cb.bind("<<ComboboxSelected>>", lambda e: (self.theme_var.set(["light", "dark"][theme_cb.current()]),
                                                          self.dark_mode_var.set(theme_cb.current() == 1),
                                                          self._apply_theme(), self._sync_header_combos(),
                                                          self._apply_theme_to_toplevel(win), self._save_settings()), add="+")
        theme_cb.pack(side="left")
        row = self._labeled(t, "Accent color:")
        acc_cb = self._keyed_combo(row, self.accent_var, [(a, a.capitalize()) for a in self.ACCENTS], 18)
        acc_cb.bind("<<ComboboxSelected>>", lambda e: (self._apply_theme(), self._sync_header_combos()), add="+")
        acc_cb.pack(side="left")
        row = self._labeled(t, "Font size")
        scales = [0.9, 1.0, 1.1, 1.2, 1.3]
        fs = ttk.Combobox(row, state="readonly", width=18, values=[f"{int(x * 100)}%" for x in scales])
        cur = min(scales, key=lambda x: abs(x - float(self.font_scale_var.get() or 1.0)))
        fs.current(scales.index(cur))
        fs.bind("<<ComboboxSelected>>", lambda e: (self.font_scale_var.set(scales[fs.current()]), self._apply_font_scale(), self._save_settings()))
        fs.pack(side="left")
        ttk.Checkbutton(t, text=self._tr("Compact mode"), variable=self.compact_mode_var,
                        command=lambda: (self._apply_theme(), self._save_settings())).pack(anchor="w")

        # Translation
        t = tabs["translation"]
        form = ttk.Frame(t)
        form.pack(fill="x")
        form.columnconfigure(0, weight=1, uniform="f")
        form.columnconfigure(1, weight=1, uniform="f")
        row = self._labeled(form, "Engine:", "Engine selection: auto/google/mymemory.", grid=(0, 0))
        self._keyed_combo(row, self.engine_var, [("auto", "Auto"), ("google", "Google"), ("mymemory", "MyMemory"),
                                                 ("deepl", "DeepL"), ("deepl_web", "DeepL (Web)"), ("libre", "Libre")]).pack(fill="x")
        row = self._labeled(form, "Auto priority:", "Auto priority decides which engine is tried first in auto mode.", grid=(0, 1))
        self._keyed_combo(row, self.auto_priority_var, [("google_first", "Google first"), ("mymemory_first", "MyMemory first")]).pack(fill="x")
        row = self._labeled(form, "Batch size (Google batch):", "Batch: how many unique lines are sent to Google at once.", grid=(1, 0))
        ttk.Spinbox(row, from_=10, to=500, textvariable=self.batch_size_var, width=8).pack(side="left")
        row = self._labeled(form, "Fallback concurrent jobs (MyMemory):", "MyMemory concurrent jobs: number of lines translated in parallel (fallback).", grid=(1, 1))
        ttk.Spinbox(row, from_=1, to=16, textvariable=self.mm_workers_var, width=8).pack(side="left")
        prow = ttk.Frame(t)
        prow.pack(fill="x", pady=(0, 12))
        ttk.Checkbutton(prow, text=self._tr("Translate files in parallel"), variable=self.parallel_files_var).pack(side="left")
        ttk.Label(prow, text=self._tr("Workers:"), style="Muted.TLabel").pack(side="left", padx=(16, 6))
        ttk.Spinbox(prow, from_=1, to=4, textvariable=self.file_workers_var, width=5).pack(side="left")
        ttk.Checkbutton(t, text=self._tr("Skip files that are already in the target language"), variable=self.skip_same_lang_var).pack(anchor="w")

        # Output
        t = tabs["output"]
        ttk.Checkbutton(t, text=self._tr("Save next to source"), variable=self.save_next_var).pack(anchor="w", pady=(0, 12))
        row = self._labeled(t, "Output directory:")
        ttk.Entry(row, textvariable=self.outdir_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=self._tr("Browse"), command=self._choose_outdir).pack(side="left", padx=(6, 0))
        row = self._labeled(t, "PDF output as:")
        ttk.Radiobutton(row, text="PDF", value="pdf", variable=self.pdf_mode_var).pack(side="left")
        ttk.Radiobutton(row, text="TXT", value="txt", variable=self.pdf_mode_var).pack(side="left", padx=(16, 0))
        ttk.Checkbutton(t, text=self._tr("Remove [bracketed] notes from SRT after translate"), variable=self.clean_after_var).pack(anchor="w")

        # Dictionary
        t = tabs["dictionary"]
        row = self._labeled(t, "Custom dictionary:", "Dictionary mode: off/pre/post/both.")
        self._keyed_combo(row, self.dict_mode_var, [("off", "Off"), ("pre", "Before translation"), ("post", "After translation"),
                                                    ("both", "Both")], 20).pack(side="left")
        row = self._labeled(t, "File")
        ttk.Entry(row, textvariable=self.dict_path_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=self._tr("Browse"), command=self._choose_dict).pack(side="left", padx=(6, 0))
        ttk.Checkbutton(t, text=self._tr("Case-insensitive terms"), variable=self.dict_case_ins_var).pack(anchor="w", pady=(0, 6))
        ttk.Checkbutton(t, text=self._tr("Word-boundary only"), variable=self.dict_word_boundary_var).pack(anchor="w")

        nb.select(list(tabs).index(tab) if tab in tabs else 0)

        def close():
            self._save_settings()
            self._refresh_status_bar()
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", close)
        ttk.Button(footer, text=self._tr("Close"), command=close, style="Accent.TButton").pack(side="right")
        self._settings_win = win

    # old entry points (header menu / gear button / shortcuts) open the right tab
    def _open_output_dialog(self) -> None:
        self._open_settings("output")

    def _open_preferences(self) -> None:
        self._open_settings("appearance")

    def _open_advanced_dialog(self) -> None:
        self._open_settings("translation")

    def _toggle_advanced(self) -> None:
        self._open_settings("translation")

    def _preview_selected(self) -> None:
        """First lines of the selected file. Offline language guess (the old version made a
        Google request on the UI thread and always reported 'auto')."""
        sel = self.tree.selection()
        if not sel:
            return
        path = self.item_to_path.get(sel[0])
        if not path or not os.path.isfile(path):
            return
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext in (".srt", ".vtt", ".txt", ".md", ".csv"):
                sample = "".join(_read_lines_robust(path)[:40])
            elif ext == ".docx" and DocxDocument:
                sample = "\n".join(p.text for p in DocxDocument(path).paragraphs[:40])
            elif ext == ".pdf" and pdf_extract_text:
                sample = "\n".join((pdf_extract_text(path) or "").splitlines()[:40])
            else:
                sample = ""
        except Exception as e:
            sample = f"{self._tr('Error')}: {e}"
        text_only = "\n".join(l for l in sample.splitlines() if l.strip() and not is_timestamp(l) and not is_sequence_number(l))
        lang = detect_language(text_only[:2000]) or "?"
        win, body, footer = self._make_dialog(f"{self._tr('Preview')} — {os.path.basename(path)}", 760, 520)
        meta = ttk.Frame(body)
        meta.pack(fill="x", pady=(0, 10))
        ttk.Label(meta, text=os.path.basename(path), style="Section.TLabel").pack(side="left")
        lang_name = _localize_lang_name(lang, self.ui_lang_code) if lang != "?" else "?"
        ttk.Label(meta, text=f"{self._tr('Lang:')} {lang_name}   ·   {self._fmt_size(os.path.getsize(path))}",
                  style="Muted.TLabel").pack(side="right")
        wrap = ttk.Frame(body, style="Field.TFrame")
        wrap.pack(fill="both", expand=True)
        txt = tk.Text(wrap, wrap="word", bd=0, highlightthickness=0, padx=12, pady=10)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=txt.yview, style="Modern.Vertical.TScrollbar")
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.insert("1.0", sample)
        txt.configure(state="disabled", font=self._fonts["mono"])
        self._apply_theme_to_toplevel(win)
        ttk.Button(footer, text=self._tr("Close"), command=win.destroy, style="Accent.TButton").pack(side="right")

    def _show_about(self) -> None:
        win, body, footer = self._make_dialog(self._tr("About"), 560, 400)
        top = ttk.Frame(body)
        top.pack(fill="x")
        if getattr(self, "_logo_img", None) is not None:
            self._about_logo = self._app_icon.subsample(max(1, self._app_icon.width() // 56))
            ttk.Label(top, image=self._about_logo).pack(side="left", padx=(0, 14))
        names = ttk.Frame(top)
        names.pack(side="left", fill="x")
        ttk.Label(names, text="Subtitle PRO", style="Section.TLabel").pack(anchor="w")
        ttk.Label(names, text=f"{self._tr('Version:')} {self.APP_VERSION}  ·  MIT", style="Muted.TLabel").pack(anchor="w")
        ttk.Label(body, text=self._tr("Batch subtitle & document translator"), wraplength=500).pack(anchor="w", pady=(16, 8))
        feats = [self._tr("Multi-format: SRT, VTT, TXT, MD, CSV, DOCX, PDF"),
                 self._tr("Engines: Auto / Google / MyMemory with fallback"),
                 self._tr("Dictionary pre/post apply, case/word-boundary options"),
                 self._tr("Queue, preview, drag&drop, logging, error policy"),
                 self._tr("Persistent settings, themes, accent & compact mode")]
        for f in feats:
            ttk.Label(body, text="•  " + f.lstrip("- "), style="Muted.TLabel", wraplength=500).pack(anchor="w", pady=1)
        link_row = ttk.Frame(body)
        link_row.pack(fill="x", pady=(16, 0))
        ttk.Label(link_row, text=self._tr("Project site:"), style="Muted.TLabel").pack(side="left")
        link = ttk.Label(link_row, text=self.REPO_URL.replace("https://", ""), cursor="hand2",
                         foreground=self._palette["accent"])
        link.pack(side="left", padx=(6, 0))
        link.bind("<Button-1>", lambda e: __import__("webbrowser").open(self.REPO_URL))
        ttk.Button(footer, text=self._tr("Close"), command=win.destroy, style="Accent.TButton").pack(side="right")

    def _choose_dict(self) -> None:
        path = filedialog.askopenfilename(title=self._tr("Select dictionary (JSON or CSV)"), filetypes=(("Dictionary", "*.json *.csv"), ("All files", "*.*")))
        if path:
            self.dict_path_var.set(path)
            self._load_custom_dict(path)

    def _load_custom_dict(self, path: str) -> None:
        try:
            mapping: Dict[str, str] = {}
            if path.lower().endswith(".json"):
                with open(path, "r", encoding="utf-8") as rf:
                    mapping = json.load(rf)
            elif path.lower().endswith(".csv"):
                with open(path, newline="", encoding="utf-8") as cf:
                    reader = csv.reader(cf)
                    for row in reader:
                        if len(row) >= 2:
                            mapping[row[0]] = row[1]
            self.custom_terms = mapping
        except Exception:
            self.custom_terms = {}

    def _open_outdir(self) -> None:
        path = self.outdir_var.get().strip()
        if not path:
            # try infer from first file
            if self.files:
                path = os.path.dirname(self.files[0])
        if path and os.path.isdir(path):
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f"open '{path}'")
            else:
                os.system(f"xdg-open '{path}'")

    def _open_folder_selected(self) -> None:
        try:
            sel = self.tree.selection()
            if not sel:
                return
            iid = sel[0]
            path = self.item_to_path.get(iid)
            if not path:
                return
            folder = os.path.dirname(path)
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f"open '{folder}'")
            else:
                os.system(f"xdg-open '{folder}'")
        except Exception:
            pass

    def _save_queue(self) -> None:
        if not self.files:
            return
        path = filedialog.asksaveasfilename(title="Save queue", defaultextension=".json", filetypes=(("JSON", "*.json"), ("All files", "*.*")))
        if not path:
            return
        try:
            data = {"files": self.files}
            with open(path, "w", encoding="utf-8") as wf:
                json.dump(data, wf, ensure_ascii=False, indent=2)
            self._log(self._tr("Queue saved:") + f" {path}", "ok")
        except Exception as e:
            self._log(self._tr("Queue save failed:") + f" {e}", "error")

    def _load_queue(self) -> None:
        path = filedialog.askopenfilename(title="Load queue", filetypes=(("JSON", "*.json"), ("All files", "*.*")))
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as rf:
                data = json.load(rf)
            files = data.get("files", [])
            for f in files:
                self._add_file(f)
            self._log(self._tr("Queue loaded:") + f" {len(files)} {self._tr('files')}", "ok")
        except Exception as e:
            self._log(self._tr("Queue load failed:") + f" {e}", "error")

    def _ask_error_action(self, file_name: str, err: str) -> str:
        try:
            dlg = tk.Toplevel(self.root)
            try:
                if TBStyle is not None and getattr(self, '_bs', None) is not None:
                    self._bs.style.master = dlg  # type: ignore[attr-defined]
                self._apply_theme()
            except Exception:
                pass
            dlg.title("Error")
            try:
                self._apply_theme_to_toplevel(dlg)
            except Exception:
                pass
            dlg.geometry("520x220")
            dlg.transient(self.root)
            dlg.grab_set()
            frm = ttk.Frame(dlg)
            frm.pack(fill="both", expand=True, padx=12, pady=12)
            ttk.Label(frm, text=f"{file_name}").pack(anchor="w")
            import tkinter.scrolledtext as scrolledtext
            txt = scrolledtext.ScrolledText(frm, height=6, wrap="word")
            txt.pack(fill="both", expand=True, pady=8)
            txt.insert("1.0", err)
            txt.configure(state="disabled")
            btns = ttk.Frame(frm)
            btns.pack(fill="x")
            res = {"v": "skip"}
            def set_res(v: str) -> None:
                res["v"] = v
                dlg.destroy()
            ttk.Button(btns, text=self._tr("Retry"), command=lambda: set_res("retry")).pack(side="left")
            ttk.Button(btns, text=self._tr("Skip"), command=lambda: set_res("skip")).pack(side="left", padx=6)
            ttk.Button(btns, text=self._tr("Cancel all"), command=lambda: set_res("cancel")).pack(side="left")
            dlg.wait_window()
            return res["v"]
        except Exception:
            return "skip"

    def _format_exception(self, e: Exception, path: Optional[str] = None) -> str:
        try:
            msg = str(e) or e.__class__.__name__
            import errno as _errno
            if isinstance(e, FileNotFoundError):
                return f"{self._tr('File not found')}{': ' + path if path else ''}\n{msg}"
            if isinstance(e, PermissionError):
                return f"{self._tr('Permission denied')}{': ' + path if path else ''}\n{msg}"
            if isinstance(e, IsADirectoryError):
                return f"{self._tr('A folder was opened as a file')}{': ' + path if path else ''}\n{msg}"
            if isinstance(e, UnicodeDecodeError):
                return f"{self._tr('Encoding error (UTF-8?)')}\n{msg}"
            if isinstance(e, OSError) and getattr(e, 'errno', None) == _errno.ENOSPC:
                return f"{self._tr('Not enough disk space')}\n{msg}"
            return f"{e.__class__.__name__}: {msg}"
        except Exception:
            return str(e) or "Bilinmeyen hata"

    _LOG_MAX = 5000

    # ---- Worker -> Tk thread hand-off. Workers never call Tk directly (Tkinter is not
    # thread-safe); they post callables that the Tk thread runs from _drain_log_queue. ----
    def _post(self, fn) -> None:
        self._log_queue.put(fn)

    def _call_on_ui(self, fn):
        """Run fn on the Tk thread and wait for its result (used for the error dialog)."""
        if threading.current_thread() is threading.main_thread():
            return fn()
        done = threading.Event()
        box: Dict[str, object] = {}

        def run():
            try:
                box["v"] = fn()
            except Exception as e:  # pragma: no cover
                box["e"] = e
            finally:
                done.set()
        self._post(run)
        done.wait()
        if "e" in box:
            raise box["e"]  # type: ignore[misc]
        return box.get("v")

    def _drain_log_queue(self) -> None:
        try:
            for _ in range(500):  # bounded per tick so the UI stays responsive
                fn = self._log_queue.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except queue.Empty:
            pass
        try:
            self._drain_after = self.root.after(50, self._drain_log_queue)
        except Exception:
            pass  # window destroyed

    def _log(self, message: str, level: str = "info") -> None:
        """Thread-safe: worker threads hand the entry to the Tk thread; the view is appended
        incrementally (it used to be fully redrawn on every call: 2,000 logs took 5.6 s)."""
        if threading.current_thread() is not threading.main_thread():
            # Never touch Tk from a worker: queue it; _drain_log_queue runs on the Tk thread.
            self._post(lambda m=message, lv=level: self._log(m, lv))
            return
        try:
            ts = time.strftime("%H:%M:%S")
            entry = (level, f"[{ts}] {message}")
            self._log_entries.append(entry)
            if len(self._log_entries) > self._LOG_MAX:
                del self._log_entries[: len(self._log_entries) - self._LOG_MAX]
            if self._log_level_visible(level):
                self._append_log_line(*entry)
        except Exception:
            pass

    def _log_level_visible(self, level: str) -> bool:
        flags = {"info": self.log_info_var, "ok": self.log_ok_var, "error": self.log_err_var}
        var = flags.get(level)
        return True if var is None else bool(var.get())

    def _append_log_line(self, level: str, line: str) -> None:
        tag = level if level in ("info", "ok", "error") else ()
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", line + "\n", tag)
        # keep the widget bounded as well
        excess = int(self.txt_log.index("end-1c").split(".")[0]) - 1000
        if excess > 0:
            self.txt_log.delete("1.0", f"{excess + 1}.0")
        self.txt_log.configure(state="disabled")
        self.txt_log.see("end")

    def _refresh_log_view(self) -> None:
        """Full redraw — only needed when a level filter changes or the log is cleared."""
        try:
            self.txt_log.configure(state="normal")
            self.txt_log.delete("1.0", "end")
            visible = [e for e in self._log_entries if self._log_level_visible(e[0])][-1000:]
            for lvl, line in visible:
                self.txt_log.insert("end", line + "\n", lvl if lvl in ("info", "ok", "error") else ())
            self.txt_log.configure(state="disabled")
            self.txt_log.see("end")
        except Exception:
            pass

    def _export_logs(self) -> None:
        try:
            path = filedialog.asksaveasfilename(title=self._tr("Export logs"), defaultextension=".txt", filetypes=(("Text", "*.txt"), ("All files", "*.*")))
            if not path:
                return
            with open(path, "w", encoding="utf-8") as wf:
                for _lvl, line in self._log_entries:
                    wf.write(line + "\n")
            messagebox.showinfo(self._tr("Log"), self._tr("Logs exported"))
        except Exception:
            pass

    def _copy_logs(self) -> None:
        try:
            txt = "\n".join([line for _lvl, line in self._log_entries])
            self.root.clipboard_clear()
            self.root.clipboard_append(txt)
            try:
                self._log(self._tr("Log copied to clipboard"), "ok")
            except Exception:
                pass
        except Exception:
            pass

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title=self._tr("Select files (SRT/VTT/TXT/MD/CSV/DOCX/PDF)"),
            filetypes=(
                ("Supported", "*.srt *.vtt *.txt *.md *.csv *.docx *.pdf"),
                ("All files", "*.*"),
            ),
        )
        if not paths:
            return
        for p in paths:
            # Normalize Windows paths and trim quotes
            p = str(p).strip().strip('"')
            self._add_file(p)

    def _remove_selected(self) -> None:
        sel = self.tree.selection()
        for iid in sel:
            path = self.item_to_path.get(iid)
            if path and path in self.files:
                self.files.remove(path)
            if path and path in self.file_items:
                del self.file_items[path]
            if iid in self.item_to_path:
                del self.item_to_path[iid]
            self.tree.delete(iid)
        self._refresh_status_bar()
        self._restripe_tree()

    def _remove_missing(self) -> None:
        try:
            removed = 0
            for iid in list(self.tree.get_children()):
                path = self.item_to_path.get(iid)
                if path and not os.path.exists(path):
                    if path in self.files:
                        self.files.remove(path)
                    if path in self.file_items:
                        del self.file_items[path]
                    if iid in self.item_to_path:
                        del self.item_to_path[iid]
                    try:
                        self.tree.delete(iid)
                        removed += 1
                    except Exception:
                        pass
            if removed:
                self._log(f"Removed {removed} missing items", "ok")
            self._refresh_status_bar()
            self._restripe_tree()
        except Exception:
            pass

    def _open_selected_output(self) -> None:
        try:
            sel = self.tree.selection()
            if not sel:
                return
            iid = sel[0]
            src = self.item_to_path.get(iid)
            if not src:
                return
            lang_name = self.target_lang_var.get()
            code = (self.target_lang_map.get(lang_name)
                    if getattr(self, 'target_lang_map', None)
                    else self.lang_map.get(lang_name, "tr"))
            outp = _out_path_same_ext(src, code)
            if not os.path.exists(outp):
                messagebox.showinfo(self._tr("Output"), self._tr("Output file not found. Translate first."))
                return
            if sys.platform.startswith("win"):
                os.startfile(outp)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f"open '{outp}'")
            else:
                os.system(f"xdg-open '{outp}'")
        except Exception:
            pass

    def _open_selected_output_folder(self) -> None:
        try:
            sel = self.tree.selection()
            if not sel:
                return
            iid = sel[0]
            src = self.item_to_path.get(iid)
            if not src:
                return
            lang_name = self.target_lang_var.get()
            code = (self.target_lang_map.get(lang_name)
                    if getattr(self, 'target_lang_map', None)
                    else self.lang_map.get(lang_name, "tr"))
            outp = _out_path_same_ext(src, code)
            folder = os.path.dirname(outp)
            if not os.path.exists(folder):
                messagebox.showinfo(self._tr("Output"), self._tr("Output folder not found."))
                return
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f"open '{folder}'")
            else:
                os.system(f"xdg-open '{folder}'")
        except Exception:
            pass

    def _reveal_in_explorer(self) -> None:
        try:
            sel = self.tree.selection()
            if not sel:
                return
            iid = sel[0]
            src = self.item_to_path.get(iid)
            if not src or not os.path.exists(src):
                return
            if sys.platform.startswith("win"):
                os.system(f'explorer /select,"{src}"')
            elif sys.platform == "darwin":
                os.system(f"open -R '{src}'")
            else:
                folder = os.path.dirname(src)
                os.system(f"xdg-open '{folder}'")
        except Exception:
            pass

    def _clear_files(self) -> None:
        self.files.clear()
        self.file_items.clear()
        self.item_to_path.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._refresh_status_bar()
        self._restripe_tree()

    def _on_drop(self, event) -> None:
        try:
            raw = str(event.data)
            items = []
            buf = ""; brace = False
            for ch in raw:
                if ch == '{':
                    brace = True; buf = ""; continue
                if ch == '}':
                    brace = False; items.append(buf); buf = ""; continue
                if ch == ' ' and not brace:
                    if buf.strip():
                        items.append(buf.strip()); buf = ""
                    continue
                buf += ch
            if buf.strip():
                items.append(buf.strip())
        except Exception:
            items = [str(event.data)]
        for p in items:
            self._add_file(self._normalize_path(p))

    def _add_file(self, path: str) -> None:
        path = self._normalize_path(path)
        if not os.path.isfile(path):
            self._log(f"{self._tr('File not found')}: {path}", "error")
            return
        if not path.lower().endswith(SUPPORTED_EXTS):
            self._log(f"{self._tr('Unsupported extension')}: {os.path.basename(path)}", "error")
            return
        if path in self.files:
            return
        self.files.append(path)
        iid = f"f{len(self.file_items)+1}_{abs(hash(path))}"
        self.file_items[path] = iid
        self.item_to_path[iid] = path
        try:
            self.file_added_ts[path] = time.time()
            added_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.file_added_ts[path]))
        except Exception:
            added_str = ""
        base_name = os.path.basename(path)
        try:
            size_bytes = os.path.getsize(path)
            if size_bytes == 0:
                try:
                    with open(path, 'rb') as rf:
                        rf.read(1)
                    size_bytes = os.path.getsize(path)
                except Exception:
                    pass
        except Exception:
            size_bytes = 0
        self.tree.insert("", "end", iid=iid, values=(base_name, self._fmt_size(size_bytes), self._tr("Ready"), added_str))
        try:
            self._log(f"{self._tr('File added')}: {base_name} ({self._fmt_size(size_bytes)})", "ok")
        except Exception:
            pass
        self._refresh_status_bar()
        self._restripe_tree()

    def _normalize_path(self, p: str) -> str:
        try:
            q = str(p).strip().strip('"')
            q = os.path.expanduser(q)
            q = os.path.normpath(q)
            return q
        except Exception:
            return str(p)

    def _restripe_tree(self) -> None:
        try:
            for idx, iid in enumerate(self.tree.get_children()):
                self.tree.item(iid, tags=("evenrow",) if idx % 2 == 0 else ("oddrow",))
        except Exception:
            pass

    def _tree_set_safe(self, iid: str, column: str, value: str) -> None:
        try:
            if hasattr(self, 'tree') and self.tree is not None and self.tree.exists(iid):
                self.tree.set(iid, column=column, value=value)
        except Exception:
            # Ignore if item no longer exists or widget disposed
            pass

    def _apply_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        try:
            for iid in self.tree.get_children():
                name = str(self.tree.set(iid, "dosya")).lower()
                visible = (text in name) if text else True
                if visible:
                    self.tree.reattach(iid, "", "end")
                else:
                    self.tree.detach(iid)
            # Re-stripe only visible items
            visible_ids = self.tree.get_children("")
            for idx, iid in enumerate(visible_ids):
                self.tree.item(iid, tags=("evenrow",) if idx % 2 == 0 else ("oddrow",))
        except Exception:
            pass

    def _sort_by_column(self, col: str) -> None:
        try:
            data = []
            for iid in self.tree.get_children(""):
                vals = self.tree.item(iid, "values")
                if col == "dosya":
                    key = vals[0]
                elif col == "boyut":
                    # parse size like "1.2 MB"
                    key_s = vals[1]
                    key = self._parse_size(key_s)
                else:
                    if col == "durum":
                        key = vals[2]
                    else:
                        # eklenme: use epoch if we have it
                        pth = self.item_to_path.get(iid, "")
                        key = self.file_added_ts.get(pth, 0.0)
                data.append((key, iid))
            rev = self._sort_reverse.get(col, False)
            data.sort(key=lambda x: x[0], reverse=rev)
            self._sort_reverse[col] = not rev
            for idx, (_k, iid) in enumerate(data):
                self.tree.move(iid, "", idx)
            self._restripe_tree()
        except Exception:
            pass

    def _parse_size(self, s: str) -> int:
        try:
            parts = s.split()
            if not parts:
                return 0
            val = float(parts[0])
            unit = (parts[1] if len(parts) > 1 else "B").upper()
            mult = {"B":1, "KB":1024, "MB":1024**2, "GB":1024**3, "TB":1024**4}.get(unit, 1)
            return int(val * mult)
        except Exception:
            return 0

    def _maybe_update_output_suggestion(self) -> None:
        if not self._auto_output:
            return
        if not self.files:
            return
        # Suggestion is shown only for info; outputs are per-file now
        first = self.files[0]
        lang_name = self.target_lang_var.get()
        code = (self.target_lang_map.get(lang_name)
                if getattr(self, 'target_lang_map', None)
                else self.lang_map.get(lang_name, "tr"))
        base, ext = os.path.splitext(first)
        self.output_path_var.set(base + f".{code}{ext}")

    def _start(self) -> None:
        # Ensure target language names reflect current UI language right before start
        try:
            # Preserve current code before rebuild
            current_target_name = self.target_lang_var.get()
            prev_code = None
            if getattr(self, 'target_lang_map', None):
                prev_code = self.target_lang_map.get(current_target_name)
            if not prev_code:
                prev_code = self.lang_map.get(current_target_name)
            self._rebuild_target_lang_names()
            if hasattr(self, 'cmb_lang'):
                self.cmb_lang.configure(values=(self.target_lang_names or self.lang_names))
            # Reselect by code if we had one
            if prev_code:
                new_name = next((n for n,c in self.target_lang_map.items() if c == prev_code), None)
                if new_name:
                    self.target_lang_var.set(new_name)
        except Exception:
            pass
        in_path = self.input_path_var.get().strip()  # legacy single-file fallback
        out_path = self.output_path_var.get().strip()
        lang_name = self.target_lang_var.get()
        code = (self.target_lang_map.get(lang_name)
                if getattr(self, 'target_lang_map', None)
                else self.lang_map.get(lang_name, "tr"))
        targets = list(self.files)
        # Fallback: allow single file via old inputs
        if not targets and in_path:
            targets = [in_path]
        if not targets:
            messagebox.showerror(self._tr("Error"), self._tr("Add at least one file (SRT/VTT/TXT/MD/CSV/DOCX/PDF)."))
            return

        self._cancel = False
        self._start_ts = time.time()
        # Snapshot every Tk variable here, on the main thread: the worker must not touch Tk.
        try:
            bs_snap = max(10, min(500, int(self.batch_size_var.get())))
        except Exception:
            bs_snap = 100
        try:
            mw_snap = max(1, min(16, int(self.mm_workers_var.get())))
        except Exception:
            mw_snap = 6
        parallel_snap = bool(self.parallel_files_var.get())
        try:
            workers_snap = max(1, min(int(self.file_workers_var.get() or 1), 4)) if parallel_snap else 1
        except Exception:
            workers_snap = 1
        cfg = {
            "engine": self.engine_var.get().lower(),
            "priority": self.auto_priority_var.get() if hasattr(self, 'auto_priority_var') else 'google_first',
            "dict_mode": self.dict_mode_var.get(),
            "skip_same": bool(self.skip_same_lang_var.get()),
            "save_next": bool(self.save_next_var.get()),
            "outdir": self.outdir_var.get().strip(),
            "clean_after": bool(self.clean_after_var.get()),
            "pdf_txt": (self.pdf_mode_var.get() == "txt") if hasattr(self, 'pdf_mode_var') else False,
        }
        tr_ = {k: self._tr(k) for k in ("Translating", "Completed", "Canceled", "Skipped", "Skipped (same language)",
                                          "Error", "Translation failed", "Unsupported extension")}
        try:
            self._save_settings()
        except Exception:
            pass  # never block a translation because settings could not be written
        try:
            self.tb_start.configure(state="disabled")
        except Exception:
            pass
        try:
            self.tb_cancel.configure(state="normal")
        except Exception:
            pass
        self.status_var.set(self._tr("Translation started..."))
        self.progress_var.set(0)

        def _progress(done: int, total: int, file_idx: int = 0, file_total: int = 1, file_name: str = "") -> None:
            pct = 0 if total == 0 else (done * 100.0) / total
            elapsed = time.time() - self._start_ts
            rate = (done / elapsed) if elapsed > 0 else 0
            remaining = ((total - done) / rate) if rate > 0 else 0
            def _update_ui() -> None:
                self.progress_var.set(pct)
                done_i, total_i = int(done), int(total)
                label =self._fmt_progress_label(pct, int(remaining), file_idx, file_total, file_name,
                                                 words_done=done_i, words_total=total_i, elapsed_sec=int(elapsed))
                self.status_var.set(label)
                # Update circular progress
                try:
                    m, s = divmod(int(remaining), 60)
                    self.circ.set(int(pct), f"ETA: {m:02d}:{s:02d}")
                except Exception:
                    pass
            self._post(_update_ui)

        def _cancel_check() -> bool:
            return self._cancel

        def _run() -> None:
            try:
                bs, mw = bs_snap, mw_snap
                total_files = len(targets)
                parallel, workers = parallel_snap, workers_snap
                if parallel and workers > 1:
                    self._post(lambda: (self.pbar.configure(mode="indeterminate"), self.pbar.start(12)))
                else:
                    self._post(lambda: (self.pbar.configure(mode="determinate"), self.pbar.stop()))
                self._log(f"Started translation | files={total_files} | lang={code} | batch={bs} | mm_jobs={mw} | parallel={parallel}", "info")
                try:
                    eng_sel = cfg["engine"]
                    if eng_sel == "deepl" and not (_DEEPL_API_KEY or ""):
                        self._log(self._tr("DeepL API key not found; falling back to MyMemory."), "info")
                    if eng_sel == "libre" and not (_LIBRE_URL or ""):
                        self._log(self._tr("LibreTranslate URL not set; falling back to MyMemory."), "info")
                except Exception:
                    pass

                def process_one(path: str, idx: int, attempt: int = 0) -> None:
                    if self._cancel:
                        return
                    iid_local = self.file_items.get(path)
                    if iid_local:
                        self._post(lambda i=iid_local: self._tree_set_safe(i, "durum", tr_["Translating"]))
                    ext_local = os.path.splitext(path)[1].lower()
                    def _file_progress(done: int, total: int, p=path, fi=idx):
                        name = os.path.basename(p)
                        _progress(done, total, fi, total_files, name)
                        if iid_local:
                            self._post(lambda i=iid_local, d=done, t=total: self._tree_set_safe(i, "durum", f"%{int(0 if t==0 else d*100/t)}"))
                    try:
                        if ext_local in (".srt", ".vtt"):
                            lines_local = _read_lines_robust(path)
                            # Optional language detect (skip if source equals target)
                            try:
                                do_skip = False
                                if cfg["skip_same"]:
                                    sample = "".join(lines_local[:60])
                                    src_guess = detect_language(sample)
                                    if src_guess and src_guess.lower().startswith(code.lower()[:2]):
                                        if code.lower().startswith("tr"):
                                            if looks_turkish(sample):
                                                do_skip = True
                                        else:
                                            do_skip = True
                                if do_skip:
                                    if iid_local:
                                        self._post(lambda i=iid_local: self._tree_set_safe(i, "durum", tr_["Skipped (same language)"]))
                                    self._log(f"{tr_['Skipped (same language)']}: {os.path.basename(path)} [{src_guess}]", "info")
                                    return
                            except Exception:
                                pass
                            # Apply custom dictionary (pre)
                            if cfg["dict_mode"] in ("pre", "both") and self.custom_terms:
                                lines_local = [self._apply_terms(line, self.custom_terms) for line in lines_local]
                            translated_local = translate_lines(
                                lines_local,
                                target_lang=code,
                                batch_size=bs,
                                mm_workers=mw,
                                engine_mode=cfg["engine"],
                                auto_priority=cfg["priority"],
                                progress_callback=_file_progress,
                                cancel_check=_cancel_check,
                                wrap_limit=70,
                            )
                            # Apply custom dictionary (post)
                            if cfg["dict_mode"] in ("post", "both") and self.custom_terms:
                                translated_local = [self._apply_terms(line, self.custom_terms) for line in translated_local]
                            # Determine output path
                            if cfg["save_next"] or not cfg["outdir"]:
                                outp_local = _out_path_same_ext(path, code)
                            else:
                                base = os.path.basename(path)
                                stem, ext = os.path.splitext(base)
                                outp_local = os.path.join(cfg["outdir"], f"{stem}.{code}{ext}")
                            with open(outp_local, "w", encoding="utf-8-sig", newline="") as wf:
                                wf.writelines(translated_local)
                            if cfg["clean_after"] and srt_clean and outp_local.lower().endswith(".srt"):
                                try:
                                    srt_clean.process_file(outp_local)
                                except Exception:
                                    pass
                        elif ext_local in (".txt", ".md", ".csv"):
                            # Language detect & skip
                            try:
                                do_skip_t = False
                                if cfg["skip_same"]:
                                    _s = "".join(_read_lines_robust(path)[:60])
                                    sg = detect_language(_s)
                                    if sg and sg.lower().startswith(code.lower()[:2]):
                                        if code.lower().startswith("tr"):
                                            if looks_turkish(_s):
                                                do_skip_t = True
                                        else:
                                            do_skip_t = True
                                if do_skip_t:
                                    if iid_local:
                                        self._post(lambda i=iid_local: self._tree_set_safe(i, "durum", tr_["Skipped (same language)"]))
                                    self._log(f"{tr_['Skipped (same language)']}: {os.path.basename(path)} [{sg}]", "info")
                                    return
                            except Exception:
                                pass
                            if cfg["save_next"] or not cfg["outdir"]:
                                outp_tmp = translate_text_file(path, code, bs, mw, cfg["engine"], cfg["priority"], _file_progress, _cancel_check)
                            else:
                                # translate and move to outdir
                                outp_tmp = translate_text_file(path, code, bs, mw, cfg["engine"], cfg["priority"], _file_progress, _cancel_check)
                                dest = os.path.join(cfg["outdir"], os.path.basename(outp_tmp))
                                try:
                                    os.replace(outp_tmp, dest)
                                except Exception:
                                    shutil.copy2(outp_tmp, dest)
                            # Apply post terms for text-based outputs
                            if cfg["dict_mode"] in ("post", "both") and self.custom_terms:
                                try:
                                    with open(outp_tmp, "r", encoding="utf-8", newline="") as rf:
                                        content = rf.read()
                                    content = self._apply_terms(content, self.custom_terms)
                                    with open(outp_tmp, "w", encoding="utf-8-sig", newline="") as wf:
                                        wf.write(content)
                                except Exception:
                                    pass
                        elif ext_local == ".docx":
                            outp_tmp = translate_docx_file(
                                path,
                                target_lang=code,
                                batch_size=bs,
                                mm_workers=mw,
                                engine_mode=cfg["engine"],
                                auto_priority=cfg["priority"],
                                progress_callback=_file_progress,
                                cancel_check=_cancel_check,
                            )
                            if not (cfg["save_next"] or not cfg["outdir"]):
                                dest = os.path.join(cfg["outdir"], os.path.basename(outp_tmp))
                                try:
                                    os.replace(outp_tmp, dest)
                                except Exception:
                                    shutil.copy2(outp_tmp, dest)
                        elif ext_local == ".pdf":
                            outp_tmp = translate_pdf_file(
                                path,
                                target_lang=code,
                                batch_size=bs,
                                mm_workers=mw,
                                engine_mode=cfg["engine"],
                                auto_priority=cfg["priority"],
                                progress_callback=_file_progress,
                                cancel_check=_cancel_check,
                                as_text=cfg["pdf_txt"],
                            )
                            if not (cfg["save_next"] or not cfg["outdir"]):
                                dest = os.path.join(cfg["outdir"], os.path.basename(outp_tmp))
                                try:
                                    os.replace(outp_tmp, dest)
                                except Exception:
                                    shutil.copy2(outp_tmp, dest)
                        else:
                            raise RuntimeError(f"{tr_['Unsupported extension']}: {ext_local}")
                        if iid_local:
                            self._post(lambda i=iid_local: self._tree_set_safe(i, "durum", tr_["Completed"]))
                        self._log(f"Done: {os.path.basename(path)}", "ok")
                    except Exception as e:
                        pretty = self._format_exception(e, path)
                        action = self._call_on_ui(lambda: self._ask_error_action(os.path.basename(path), pretty))
                        self._log(f"Error on {os.path.basename(path)}: {pretty} -> action={action}", "error")
                        if action == "retry" and attempt < 2:
                            try:
                                process_one(path, idx, attempt + 1)
                                return
                            except Exception:
                                pass
                        elif action == "skip":
                            if iid_local:
                                self._post(lambda i=iid_local: self._tree_set_safe(i, "durum", tr_["Skipped"]))
                            return
                        else:
                            # cancel all
                            self._cancel = True
                        if iid_local:
                            self._post(lambda i=iid_local, err=str(e): self._tree_set_safe(i, "durum", f"{tr_['Error']}: {err}"))

                if workers == 1:
                    for idx, path in enumerate(targets, start=1):
                        process_one(path, idx)
                else:
                    completed = 0
                    from concurrent.futures import ThreadPoolExecutor as _Pool, as_completed as _as_completed
                    with _Pool(max_workers=workers) as pool:
                        fut_map = {pool.submit(process_one, p, i): (p, i) for i, p in enumerate(targets, start=1)}
                        for fut in _as_completed(fut_map):
                            completed += 1
                            self._post(lambda c=completed: self.status_var.set(f"{tr_['Completed']}: {c}/{total_files}"))

                if parallel and workers > 1:
                    self._post(lambda: self.pbar.stop())
                self._post(lambda: (self.pbar.configure(mode="determinate"), self.status_var.set(tr_["Completed"] if not self._cancel else tr_["Canceled"])))
                self._log("All done" if not self._cancel else "Canceled by user", "info")
            except Exception as e:
                msg = f"{tr_['Translation failed']}:\n{e}"  # bound now: `e` is deleted after this block
                self._post(lambda m=msg: messagebox.showerror(tr_["Error"], m))
            finally:
                def _restore_buttons():
                    try:
                        self.tb_start.configure(state="normal")
                    except Exception:
                        pass
                    try:
                        self.tb_cancel.configure(state="disabled")
                    except Exception:
                        pass
                self._post(_restore_buttons)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def _start_selected(self) -> None:
        sel = self.tree.selection()
        if not sel:
            # fallback to all
            return self._start()
        selected_paths = [self.item_to_path.get(i) for i in sel]
        selected_paths = [p for p in selected_paths if p]
        if not selected_paths:
            return self._start()
        try:
            if not messagebox.askyesno(self._tr("Confirm"), f"{self._tr('Translate selected files?')} ({len(selected_paths)})"):
                return
        except Exception:
            pass
        # Temporarily replace files list with selected subset, run start, then restore
        backup = list(self.files)
        try:
            self.files = selected_paths
            self._start()
        finally:
            self.files = backup

    def _cancel_run(self) -> None:
        self._cancel = True
        self.status_var.set(self._tr("Canceling..."))

    # Confirm close if work in progress
    def _on_close(self) -> None:
        try:
            busy = False
            try:
                if getattr(self, '_thread', None) and self._thread.is_alive():
                    busy = True
            except Exception:
                busy = False
            if busy:
                try:
                    if not messagebox.askyesno(self._tr("Confirm"), self._tr("A translation is running. Close anyway?")):
                        return
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self._save_settings()          # remembers window size/maximized state
            self.root.update_idletasks()   # flush pending <<ThemeChanged>> before the interpreter goes away
            self.root.destroy()
        except Exception:
            pass

    def run(self) -> None:
        self.root.mainloop()

    # ---------- Settings (persist) ----------
    # settings.json key -> (attribute holding a tk variable, type)
    _SETTINGS_VARS = {
        "dark": ("dark_mode_var", bool), "accent": ("accent_var", str), "compact": ("compact_mode_var", bool),
        "bs_theme": ("bs_theme_var", str), "theme_profile": ("theme_profile_var", str), "font_scale": ("font_scale_var", float),
        "batch": ("batch_size_var", int), "mm_workers": ("mm_workers_var", int), "parallel": ("parallel_files_var", bool),
        "file_workers": ("file_workers_var", int), "save_next": ("save_next_var", bool), "out_dir": ("outdir_var", str),
        "engine": ("engine_var", str), "auto_priority": ("auto_priority_var", str), "dict_mode": ("dict_mode_var", str),
        "dict_path": ("dict_path_var", str), "dict_case_insensitive": ("dict_case_ins_var", bool),
        "dict_word_boundary": ("dict_word_boundary_var", bool), "pdf_mode": ("pdf_mode_var", str),
        "skip_same_lang": ("skip_same_lang_var", bool), "clean_after": ("clean_after_var", bool),
    }

    def _read_settings_file(self) -> Dict[str, object]:
        try:
            if os.path.exists(_SETTINGS_FILE):
                with open(_SETTINGS_FILE, "r", encoding="utf-8") as rf:
                    cfg = json.load(rf)
                return cfg if isinstance(cfg, dict) else {}
        except Exception:
            pass
        return {}

    def _load_settings(self) -> None:
        cfg = self._read_settings_file()
        for key, (attr, typ) in self._SETTINGS_VARS.items():
            var = getattr(self, attr, None)
            if var is None or key not in cfg:
                continue
            try:
                var.set(typ(cfg[key]))
            except Exception:
                pass
        ui_code = str(cfg.get("ui_lang_code") or "")
        if ui_code and (ui_code in self.ui_lang_map.values() or ui_code in getattr(self, "ui_codes", [])):
            self.ui_lang_code = ui_code
        self._saved_target_code = cfg.get("target_lang")

    def _apply_loaded_settings(self) -> None:
        """Re-apply settings that _build_ui already consumed with defaults."""
        steps = [
            lambda: self.theme_var.set("dark" if self.dark_mode_var.get() else "light"),
            self._sync_header_combos,
            self._apply_theme,
            self._apply_font_scale,
            lambda: self._rebuild_ui_lang_names(),
            lambda: self.cmb_ui_quick.configure(values=self.ui_lang_names),
            lambda: self._select_target_code(self._default_target_code(getattr(self, "_saved_target_code", None))),
            lambda: self._load_custom_dict(self.dict_path_var.get()) if self.dict_path_var.get() else None,
            self._retranslate_ui,
            self._refresh_status_bar,
        ]
        for step in steps:
            try:
                step()
            except Exception:
                pass

    def _apply_settings_to_ui(self) -> None:
        # Kept for older call sites; settings are now applied by _apply_loaded_settings
        try:
            if self.engine_var.get() not in ("auto", "google", "mymemory", "deepl", "deepl_web", "libre"):
                self.engine_var.set("auto")
            if self.auto_priority_var.get() not in ("google_first", "mymemory_first"):
                self.auto_priority_var.set("google_first")
            if self.dict_mode_var.get() not in ("off", "pre", "post", "both"):
                self.dict_mode_var.set("off")
        except Exception:
            pass

    def _save_settings(self) -> None:
        """Merge into the existing file so keys we don't manage (API keys etc.) survive."""
        try:
            cfg = self._read_settings_file()
            for key, (attr, typ) in self._SETTINGS_VARS.items():
                var = getattr(self, attr, None)
                if var is not None:
                    try:
                        cfg[key] = typ(var.get())
                    except Exception:
                        pass
            cfg["ui_lang_code"] = str(self.ui_lang_code)
            cfg["window_maximized"] = bool(getattr(self, "_is_max", True))
            if not getattr(self, "_is_max", True):
                try:
                    cfg["window_geometry"] = self.root.geometry()
                except Exception:
                    pass
            code = self._current_target_code() if hasattr(self, "target_lang_var") else None
            if code:
                cfg["target_lang"] = code
            tmp = _SETTINGS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as wf:
                json.dump(cfg, wf, ensure_ascii=False, indent=2)
            os.replace(tmp, _SETTINGS_FILE)
        except Exception:
            pass

    # ---- UI language list helpers ----
    def _rebuild_ui_lang_names(self) -> None:
        """UI-language picker shows each language in its own script (autonym), e.g. 'Deutsch', '日本語'."""
        try:
            name_to_code: Dict[str, str] = {}
            for code in getattr(self, 'ui_codes', []) or []:
                label = UI_LANG_AUTONYMS.get(code) or _localize_lang_name(code, self.ui_lang_code)
                if label in name_to_code and name_to_code[label] != code:
                    label = f"{label} ({code})"
                name_to_code[label] = code
            names = sorted(name_to_code, key=lambda s: s.casefold())
            self.ui_lang_map = {n: name_to_code[n] for n in names} or {"English": "en"}
            self.ui_lang_names = names or ["English"]
            cur_name = next((n for n, c in self.ui_lang_map.items() if c == self.ui_lang_code), None)
            if cur_name:
                self.ui_lang_var.set(cur_name)
        except Exception:
            self.ui_lang_map = {"English": "en"}
            self.ui_lang_names = ["English"]

    def _rebuild_target_lang_names(self) -> None:
        """Localized target-language names (keyed by display name) built from self.lang_map codes.
        Keeps the current selection by language code."""
        cur_code = self._current_target_code()
        name_to_code: Dict[str, str] = {}
        for code in sorted(set(self.lang_map.values())):
            label = _localize_lang_name(code, self.ui_lang_code)
            if label in name_to_code and name_to_code[label] != code:
                label = f"{label} ({code})"
            name_to_code[label] = code
        names = sorted(name_to_code, key=lambda s: s.casefold())
        self.target_lang_map = {n: name_to_code[n] for n in names}
        self.target_lang_names = names
        if cur_code:
            self._select_target_code(cur_code)

    def _current_target_code(self) -> Optional[str]:
        name = self.target_lang_var.get() if hasattr(self, 'target_lang_var') else ""
        return (getattr(self, 'target_lang_map', {}) or {}).get(name) or self.lang_map.get(name)

    def _select_target_code(self, code: str) -> bool:
        for mapping in (getattr(self, 'target_lang_map', {}) or {}, self.lang_map):
            name = next((n for n, c in mapping.items() if c == code), None)
            if name:
                self.target_lang_var.set(name)
                return True
        return False

    def _default_target_code(self, saved: Optional[str] = None) -> str:
        """Saved choice -> UI language (if not English) -> Turkish -> English."""
        codes = set(self.lang_map.values())
        for c in (saved, self.ui_lang_code if self.ui_lang_code != "en" else None, "tr", "en"):
            if c and c in codes:
                return c
        return next(iter(sorted(codes)), "en")

    def _retranslate_new_layout(self) -> None:
        """Texts introduced by the two-column layout; each step isolated so one failure
        cannot leave the rest of the UI untranslated."""
        steps = [
            lambda: self.lbl_translate_header.configure(text=self._tr("🌍 Translation")),
            lambda: self.lbl_app_subtitle.configure(text=self._tr("Batch subtitle & document translator")),
            lambda: self.lbl_engine_main.configure(text=self._tr("Engine:")),
            lambda: self.engine_radios["auto"].configure(text=self._tr("Auto")),
            lambda: self.tb_start.configure(text=self._tr("▶ Start")),
            lambda: self.tb_cancel.configure(text=self._tr("⏹ Cancel")),
            lambda: self.btn_add.configure(text=self._tr("Add...")),
            lambda: self.btn_remove.configure(text=self._tr("Remove")),
            lambda: self._filter_placeholder(True) if self._filter_placeholder_on else None,
        ]
        if self._filter_placeholder_on:
            steps.insert(0, lambda: self.filter_var.set("🔎 " + self._tr("Filter files...")))
        for step in steps:
            try:
                step()
            except Exception:
                pass
        self._sync_header_combos()
        self._retranslate_queue_statuses()
        self._update_empty_state()
        for attr, key in getattr(self, '_tooltip_keys', {}).items():
            try:
                self._tooltips[attr].text = self._tr(key)
            except Exception:
                pass
        for idx, key in getattr(self, '_header_menu_keys', []):
            try:
                self.header_menu.entryconfigure(idx, label=self._tr(key))
            except Exception:
                pass
        self._refresh_status_bar()

    ACCENTS = ("blue", "purple", "green", "orange", "pink", "teal")
    _QUEUE_STATUS_KEYS = ("Ready", "Translating", "Completed", "Skipped", "Skipped (same language)", "Canceled")

    def _retranslate_queue_statuses(self) -> None:
        """Queue 'Status' cells were written in the UI language of the moment; re-map them."""
        prev = getattr(self, "_queue_status_lang", "en")
        new = self.ui_lang_code
        if prev == new or not hasattr(self, "tree"):
            self._queue_status_lang = new
            return
        back = {_ui_translate(k, prev): k for k in self._QUEUE_STATUS_KEYS}
        err_prev, err_new = _ui_translate("Error", prev), _ui_translate("Error", new)
        for iid in self.tree.get_children(""):
            try:
                val = self.tree.set(iid, "durum")
                if val in back:
                    self.tree.set(iid, "durum", _ui_translate(back[val], new))
                elif val.startswith(err_prev + ":"):
                    self.tree.set(iid, "durum", err_new + val[len(err_prev):])
            except Exception:
                pass
        self._queue_status_lang = new

    def _sync_header_combos(self) -> None:
        """Translated labels for theme/accent pickers, selected from the internal keys."""
        try:
            self.cmb_theme.configure(values=[self._tr("Light mode"), self._tr("Dark mode")])
            self.cmb_theme.current(1 if self.dark_mode_var.get() else 0)
            self.cmb_accent.configure(values=[self._tr(a.capitalize()) for a in self.ACCENTS])
            acc = self.accent_var.get()
            self.cmb_accent.current(self.ACCENTS.index(acc) if acc in self.ACCENTS else 0)
        except Exception:
            pass

    @staticmethod
    def _mix(widget, a: str, b: str, t: float) -> str:
        try:
            ra, ga, ba = (v / 257 for v in widget.winfo_rgb(a))
            rb, gb, bb = (v / 257 for v in widget.winfo_rgb(b))
            return "#%02x%02x%02x" % (int(ra + (rb - ra) * t), int(ga + (gb - ga) * t), int(ba + (bb - ba) * t))
        except Exception:
            return a

    @staticmethod
    def _contrast_fg(widget, bg: str) -> str:
        """Readable text colour for a background (fixes white-on-white title in light theme)."""
        try:
            r, g, b = (v / 65535 for v in widget.winfo_rgb(bg))
            return "#1f2937" if (0.2126 * r + 0.7152 * g + 0.0722 * b) > 0.55 else "#f8fafc"
        except Exception:
            return "#1f2937"

    # ======================= Design system =======================
    # One palette-driven theme on top of ttk 'clam'. Replaces the previous mix of ttkbootstrap
    # themes + ~550 lines of per-widget colour patches, which rendered differently per machine.
    ACCENT_HEX = {
        "blue": ("#2563eb", "#3b82f6"), "purple": ("#7c3aed", "#8b5cf6"), "green": ("#059669", "#10b981"),
        "orange": ("#ea580c", "#f97316"), "pink": ("#db2777", "#ec4899"), "teal": ("#0d9488", "#14b8a6"),
    }

    def _palette_for(self, dark: bool, accent: str) -> Dict[str, str]:
        a_light, a_dark = self.ACCENT_HEX.get(accent, self.ACCENT_HEX["blue"])
        if dark:
            p = {"bg": "#0d1117", "surface": "#161b22", "surface2": "#1f2630", "border": "#2b3340",
                 "text": "#e6edf3", "muted": "#8b949e", "hover": "#262f3b", "accent": a_dark,
                 "ok": "#3fb950", "err": "#f85149", "danger": "#f85149"}
        else:
            p = {"bg": "#eef1f5", "surface": "#ffffff", "surface2": "#f5f7fa", "border": "#dfe4ea",
                 "text": "#1b2230", "muted": "#667085", "hover": "#eef2f7", "accent": a_light,
                 "ok": "#15803d", "err": "#dc2626", "danger": "#dc2626"}
        p["accent_hover"] = self._mix(self.root, p["accent"], "#000000" if not dark else "#ffffff", 0.14)
        p["sel"] = self._mix(self.root, p["surface"], p["accent"], 0.22 if dark else 0.14)
        p["stripe"] = self._mix(self.root, p["surface"], p["bg"], 0.45)
        return p

    def _font_family(self) -> str:
        try:
            avail = set(tkfont.families(self.root))
        except Exception:
            avail = set()
        code = (self.ui_lang_code or "en").lower()
        prefs = {"zh": ["Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans SC"], "ja": ["Yu Gothic UI", "Meiryo UI", "Meiryo"],
                 "ko": ["Malgun Gothic", "Noto Sans KR"], "th": ["Leelawadee UI", "Tahoma"], "hi": ["Nirmala UI"]}
        for fam in prefs.get(code[:2], []) + ["Segoe UI Variable Text", "Segoe UI", "Helvetica Neue", "DejaVu Sans", "Arial"]:
            if fam in avail:
                return fam
        return "TkDefaultFont"

    def _apply_design(self) -> None:
        dark = bool(self.dark_mode_var.get())
        p = self._palette_for(dark, self.accent_var.get())
        self._palette = p
        compact = bool(self.compact_mode_var.get())
        try:
            scale = float(self.font_scale_var.get() or 1.0)
        except Exception:
            scale = 1.0
        fam = self._font_family()

        def sz(n):
            return max(7, int(round(n * scale)))
        # fonts
        for name, size, weight in (("TkDefaultFont", 10, "normal"), ("TkTextFont", 10, "normal"),
                                   ("TkMenuFont", 10, "normal"), ("TkHeadingFont", 9, "bold"), ("TkTooltipFont", 9, "normal")):
            try:
                tkfont.nametofont(name).configure(family=fam, size=sz(size), weight=weight)
            except Exception:
                pass
        mono = next((f for f in ("Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Courier New") if f in set(tkfont.families(self.root))), "TkFixedFont")
        spec = {"title": (fam, 12, "bold"), "sub": (fam, 9, "normal"), "section": (fam, 11, "bold"), "small": (fam, 9, "normal"),
                "bold": (fam, 10, "bold"), "big": (fam, 11, "bold"), "mono": (mono, 9, "normal"), "hero": (fam, 30, "normal"),
                "ring": (fam, 20, "bold")}
        if not hasattr(self, "_fonts"):
            self._fonts = {k: tkfont.Font(root=self.root) for k in spec}  # created once, reconfigured on change
        for k, (f, n, w) in spec.items():
            self._fonts[k].configure(family=f, size=sz(n), weight=w)
        pad_btn = (10, 5) if compact else (14, 7)
        row_h = sz(26 if compact else 32)
        s = self._style
        s.configure(".", background=p["surface"], foreground=p["text"], fieldbackground=p["surface2"],
                    bordercolor=p["border"], lightcolor=p["surface"], darkcolor=p["surface"], troughcolor=p["surface2"],
                    focuscolor=p["accent"], selectbackground=p["accent"], selectforeground="#ffffff",
                    insertcolor=p["text"], relief="flat", font="TkDefaultFont")
        s.configure("App.TFrame", background=p["bg"])
        for st in ("TFrame", "CardInner.TFrame"):
            s.configure(st, background=p["surface"])
        s.configure("Field.TFrame", background=p["surface2"])
        s.configure("Title.TFrame", background=p["surface"])
        s.configure("Title.TLabel", background=p["surface"], foreground=p["muted"])
        s.configure("TLabel", background=p["surface"], foreground=p["text"])
        s.configure("Muted.TLabel", background=p["surface"], foreground=p["muted"])
        s.configure("Section.TLabel", background=p["surface"], foreground=p["text"], font=self._fonts["section"])
        # buttons
        s.configure("TButton", background=p["surface2"], foreground=p["text"], bordercolor=p["border"],
                    lightcolor=p["surface2"], darkcolor=p["surface2"], padding=pad_btn, focusthickness=0, anchor="center")
        s.map("TButton", background=[("disabled", p["surface2"]), ("pressed", p["border"]), ("active", p["hover"])],
              bordercolor=[("focus", p["accent"]), ("active", p["accent"])], foreground=[("disabled", p["muted"])],
              lightcolor=[("active", p["hover"])], darkcolor=[("active", p["hover"])])
        for st, font, padding in (("Accent.TButton", "bold", pad_btn), ("Big.Accent.TButton", "big", (16, 11 if not compact else 7))):
            s.configure(st, background=p["accent"], foreground="#ffffff", bordercolor=p["accent"], lightcolor=p["accent"],
                        darkcolor=p["accent"], font=self._fonts[font], padding=padding)
            s.map(st, background=[("disabled", p["border"]), ("pressed", p["accent_hover"]), ("active", p["accent_hover"])],
                  bordercolor=[("active", p["accent_hover"])], lightcolor=[("active", p["accent_hover"])],
                  darkcolor=[("active", p["accent_hover"])], foreground=[("disabled", p["muted"])])
        s.configure("Danger.TButton", background=p["surface2"], foreground=p["danger"], bordercolor=p["border"],
                    lightcolor=p["surface2"], darkcolor=p["surface2"], padding=pad_btn)
        s.map("Danger.TButton", background=[("disabled", p["surface2"]), ("active", p["danger"])],
              foreground=[("disabled", p["muted"]), ("active", "#ffffff")], bordercolor=[("active", p["danger"])])
        s.configure("Small.TButton", padding=(10, 3), font=self._fonts["small"])
        s.configure("Icon.TButton", background=p["surface"], bordercolor=p["surface"], lightcolor=p["surface"],
                    darkcolor=p["surface"], padding=(6, 4))
        s.map("Icon.TButton", background=[("active", p["hover"])], bordercolor=[("active", p["border"])])
        s.configure("Icon.TMenubutton", background=p["surface"], foreground=p["text"], bordercolor=p["surface"],
                    lightcolor=p["surface"], darkcolor=p["surface"], arrowcolor=p["surface"], padding=(8, 4))
        s.map("Icon.TMenubutton", background=[("active", p["hover"])])
        # engine chips
        s.configure("Chip.Toolbutton", background=p["surface2"], foreground=p["text"], bordercolor=p["border"],
                    lightcolor=p["surface2"], darkcolor=p["surface2"], padding=(8, 6), anchor="center")
        s.map("Chip.Toolbutton",
              background=[("selected", p["accent"]), ("active", p["hover"])],
              foreground=[("selected", "#ffffff")], bordercolor=[("selected", p["accent"]), ("active", p["accent"])],
              lightcolor=[("selected", p["accent"])], darkcolor=[("selected", p["accent"])])
        # check / radio
        for st in ("TCheckbutton", "TRadiobutton"):
            s.configure(st, background=p["surface"], foreground=p["text"], indicatorbackground=p["surface2"],
                        indicatorforeground=p["accent"], indicatorcolor=p["surface2"], bordercolor=p["border"])
            s.map(st, background=[("active", p["surface"])], indicatorcolor=[("selected", p["accent"]), ("pressed", p["hover"])],
                  foreground=[("disabled", p["muted"])])
        # inputs
        for st in ("TEntry", "Placeholder.TEntry", "TCombobox", "TSpinbox"):
            s.configure(st, fieldbackground=p["surface2"], background=p["surface2"], foreground=p["text"],
                        bordercolor=p["border"], lightcolor=p["surface2"], darkcolor=p["surface2"],
                        arrowcolor=p["muted"], padding=(8, 5))
            s.map(st, bordercolor=[("focus", p["accent"]), ("hover", p["muted"])],
                  lightcolor=[("focus", p["accent"])], fieldbackground=[("readonly", p["surface2"]), ("disabled", p["surface"])],
                  foreground=[("readonly", p["text"]), ("disabled", p["muted"])],
                  selectbackground=[("readonly", p["surface2"])], selectforeground=[("readonly", p["text"])],
                  background=[("readonly", p["surface2"]), ("active", p["hover"])], arrowcolor=[("active", p["text"])])
        s.configure("Placeholder.TEntry", foreground=p["muted"])
        s.map("Placeholder.TEntry", foreground=[("!disabled", p["muted"])])
        s.configure("Title.TCombobox")
        # tree
        s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        s.configure("Treeview", background=p["surface2"], fieldbackground=p["surface2"], foreground=p["text"],
                    bordercolor=p["surface2"], rowheight=row_h, font="TkDefaultFont")
        s.map("Treeview", background=[("selected", p["sel"])], foreground=[("selected", p["text"])])
        s.configure("Treeview.Heading", background=p["surface2"], foreground=p["muted"], bordercolor=p["border"],
                    lightcolor=p["surface2"], darkcolor=p["surface2"], relief="flat", padding=(10, 7), font=self._fonts["small"])
        s.map("Treeview.Heading", background=[("active", p["hover"])], foreground=[("active", p["text"])])
        try:
            self.tree.tag_configure("evenrow", background=p["surface2"])
            self.tree.tag_configure("oddrow", background=self._mix(self.root, p["surface2"], p["border"], 0.35))
        except Exception:
            pass
        # progress & scrollbars
        s.configure("Thin.Horizontal.TProgressbar", troughcolor=p["surface2"], background=p["accent"], bordercolor=p["surface2"],
                    lightcolor=p["accent"], darkcolor=p["accent"], thickness=6)
        s.configure("TProgressbar", background=p["accent"])
        for orient in ("Vertical", "Horizontal"):
            st = f"Modern.{orient}.TScrollbar"
            s.layout(st, [(f"{orient}.Scrollbar.trough", {"children": [(f"{orient}.Scrollbar.thumb", {"expand": True, "sticky": "nswe"})],
                                                          "sticky": "ns" if orient == "Vertical" else "we"})])
            s.configure(st, troughcolor=p["surface2"], background=p["border"], bordercolor=p["surface2"],
                        lightcolor=p["border"], darkcolor=p["border"], arrowsize=9, width=9)
            s.map(st, background=[("active", p["muted"]), ("pressed", p["muted"])])
        s.configure("TSeparator", background=p["border"])
        s.configure("TLabelframe", background=p["surface"], bordercolor=p["border"], lightcolor=p["surface"], darkcolor=p["surface"])
        s.configure("TLabelframe.Label", background=p["surface"], foreground=p["muted"], font=self._fonts["bold"])
        s.configure("TNotebook", background=p["surface"], bordercolor=p["border"], tabmargins=(0, 4, 0, 0))
        s.configure("TNotebook.Tab", background=p["surface2"], foreground=p["muted"], bordercolor=p["border"],
                    lightcolor=p["surface2"], darkcolor=p["surface2"], padding=(16, 7))
        s.map("TNotebook.Tab", background=[("selected", p["accent"]), ("active", p["hover"])],
              foreground=[("selected", "#ffffff"), ("active", p["text"])],
              lightcolor=[("selected", p["accent"])], darkcolor=[("selected", p["accent"])], bordercolor=[("selected", p["accent"])])
        s.configure("TMenubutton", background=p["surface2"], foreground=p["text"], bordercolor=p["border"], arrowcolor=p["muted"], padding=(8, 4))
        s.configure("TScale", background=p["surface"], troughcolor=p["surface2"])
        # combobox drop-downs (existing ones too)
        for opt, val in (("*TCombobox*Listbox.background", p["surface"]), ("*TCombobox*Listbox.foreground", p["text"]),
                         ("*TCombobox*Listbox.selectBackground", p["accent"]), ("*TCombobox*Listbox.selectForeground", "#ffffff"),
                         ("*TCombobox*Listbox.font", "TkDefaultFont"), ("*TCombobox*Listbox.borderWidth", 0)):
            self.root.option_add(opt, val)
        for cb in ("cmb_theme", "cmb_accent", "cmb_ui_quick", "cmb_lang"):
            try:
                pop = self.root.tk.call("ttk::combobox::PopdownWindow", getattr(self, cb))
                self.root.tk.call(f"{pop}.f.l", "configure", "-background", p["surface"], "-foreground", p["text"],
                                  "-selectbackground", p["accent"], "-selectforeground", "#ffffff")
            except Exception:
                pass
        # classic Tk widgets
        self.root.configure(bg=p["bg"])
        try:
            self.root_scroll.canvas.configure(bg=p["bg"])
        except Exception:
            pass
        if hasattr(self, "titlebar"):
            self.titlebar.configure(bg=p["surface"])
            self.titlebar_border.configure(bg=p["border"])
            for f in getattr(self, "_tb_frames", []):
                f.configure(bg=p["surface"])
            for w in self.titlebar.winfo_children():
                for c in [w] + list(w.winfo_children()):
                    if isinstance(c, tk.Label):
                        c.configure(bg=p["surface"])
            self.lbl_app_title.configure(bg=p["surface"], fg=p["text"], font=self._fonts["title"])
            self.lbl_app_subtitle.configure(bg=p["surface"], fg=p["muted"], font=self._fonts["sub"])
            for b in getattr(self, "_win_btns", []):
                b.configure(bg=p["surface"], fg=p["muted"], font=self._fonts["small"])
        for m in ("header_menu", "header_font_menu", "tree_menu"):
            try:
                getattr(self, m).configure(bg=p["surface"], fg=p["text"], activebackground=p["sel"], activeforeground=p["text"],
                                           selectcolor=p["accent"], bd=0, relief="flat", font="TkMenuFont")
            except Exception:
                pass
        if hasattr(self, "txt_log"):
            self.txt_log.configure(bg=p["surface2"], fg=p["text"], insertbackground=p["text"], selectbackground=p["sel"],
                                   selectforeground=p["text"], font=self._fonts["mono"])
            self.txt_log.tag_configure("info", foreground=p["muted"])
            self.txt_log.tag_configure("ok", foreground=p["ok"])
            self.txt_log.tag_configure("error", foreground=p["err"])
        if hasattr(self, "empty_state"):
            for w in (self.empty_state, self.lbl_empty_icon, self.lbl_empty_title, self.lbl_empty_sub):
                w.configure(bg=p["surface2"])
            self.lbl_empty_icon.configure(fg=p["accent"], font=self._fonts["hero"])
            self.lbl_empty_title.configure(fg=p["text"], font=self._fonts["big"])
            self.lbl_empty_sub.configure(fg=p["muted"], font=self._fonts["small"])
        for card, _ctx in getattr(self, "card_contexts", []):
            card.set_colors(fill=p["surface"], shadow=p["border"], outer=p["bg"])
        if hasattr(self, "circ"):
            self.circ.set_palette(bg=p["surface"], track=p["border"], color=p["accent"], text=p["text"], font=self._fonts["ring"])
        if hasattr(self, "lbl_status"):
            try:
                self.lbl_status.configure(wraplength=max(220, int(320 * scale)))
            except Exception:
                pass

    def _apply_theme(self) -> None:
        self._apply_design()

    def _apply_bootstrap_styles(self) -> None:
        self._apply_design()

    def _apply_card_colors(self) -> None:
        self._apply_design()

    def _apply_font_scale(self) -> None:
        self._apply_design()

    def _ensure_ui_font_family(self) -> None:
        self._apply_design()

    def _apply_theme_to_toplevel(self, win) -> None:
        """Dialogs: ttk widgets follow the global styles; colour the window and any classic Tk widgets."""
        p = getattr(self, "_palette", None) or self._palette_for(bool(self.dark_mode_var.get()), self.accent_var.get())
        try:
            win.configure(bg=p["surface"])
        except Exception:
            pass
        stack = list(win.winfo_children())
        while stack:
            w = stack.pop()
            stack.extend(w.winfo_children())
            cls = w.winfo_class()
            try:
                if cls in ("Text", "Listbox"):
                    w.configure(bg=p["surface2"], fg=p["text"], insertbackground=p["text"], selectbackground=p["sel"],
                                highlightthickness=0, bd=0)
                elif cls in ("Frame", "Canvas", "Label", "Toplevel"):
                    w.configure(bg=p["surface"])
                    if cls == "Label":
                        w.configure(fg=p["text"])
                elif cls == "Spinbox":
                    w.configure(bg=p["surface2"], fg=p["text"], buttonbackground=p["surface2"], insertbackground=p["text"])
            except Exception:
                pass

    def _build_section_header(self, parent, title: str, ctx: str = "") -> ttk.Label:
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=14, pady=(12, 8))
        lbl = ttk.Label(row, text=title, style="Section.TLabel")
        lbl.pack(side="left")
        return lbl


def launch_gui() -> None:
    app = TranslatorGUI()
    app.run()


if __name__ == "__main__":
    try:
        _maybe_open_python_download_once()
        _offer_install_missing_requirements()
        _cli_main()
    except Exception as e:
        # Started without a console (pyw / run_app.bat): stderr goes nowhere, so also write a
        # log next to the app and show a message box instead of failing silently.
        details = traceback.format_exc()
        try:
            print(f"ERROR: {e}\n{details}", file=sys.stderr)
        except Exception:
            pass
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "subtitle_pro_error.log")
        try:
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + details + "\n")
        except Exception:
            pass
        try:
            if tk is not None:
                _r = tk.Tk()
                _r.withdraw()
                messagebox.showerror("Subtitle PRO", f"{e}\n\n{log_path}")
                _r.destroy()
        except Exception:
            pass
        sys.exit(1)



