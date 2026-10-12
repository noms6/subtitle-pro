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
import urllib.parse
try:
    import srt_clean  # type: ignore
except Exception:
    srt_clean = None  # type: ignore
_API_SEM = threading.Semaphore(4)

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

# Optional ttkbootstrap for modern theming
try:
    from ttkbootstrap import Style as TBStyle  # type: ignore
except Exception:
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
    "Words", "Elapsed", "Remaining", "s",
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
    def _is_invalid_translation(t: Optional[str]) -> bool:
        if not isinstance(t, str): return False
        lower_t = t.lower()
        if "error 500" in lower_t: return True
        if "server error" in lower_t: return True
        if "that’s an error" in lower_t: return True
        if "that's an error" in lower_t: return True
        if "too many requests" in lower_t: return True
        if "mymemory warning" in lower_t: return True
        return False

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

    def _primary_translate_batch(engine_name: str, texts_batch: List[str]) -> Optional[List[str]]:
        if not texts_batch:
            return []
        
        # We will do up to 3 retries for the batch. If the batch still fails, we will NOT return None,
        # but rather we will return a list with None for failed items, OR we will fall back to per-item translation.
        for attempt in range(3):
            try:
                if cancel_check and cancel_check():
                    return [t for t in texts_batch]
                _API_SEM.acquire()
                try:
                    res = None
                    if engine_name == "google" and google is not None:
                        res = google.translate_batch(texts_batch)
                    elif engine_name == "deepl" and 'DeeplTranslator' in globals() and DeeplTranslator is not None and _DEEPL_API_KEY:
                        try:
                            deepl = DeeplTranslator(api_key=_DEEPL_API_KEY, source="auto", target=target_lang)  # type: ignore
                        except TypeError:
                            deepl = DeeplTranslator(_DEEPL_API_KEY, source="auto", target=target_lang)  # type: ignore
                        if hasattr(deepl, "translate_batch"):
                            res = deepl.translate_batch(texts_batch)  # type: ignore
                        else:
                            res = [deepl.translate(t) for t in texts_batch]  # type: ignore
                    elif engine_name == "libre" and 'LibreTranslator' in globals() and LibreTranslator is not None:
                        base_url = _LIBRE_URL or "https://libretranslate.com/"
                        try:
                            libre = LibreTranslator(source="auto", target=target_lang, api_url=base_url, api_key=_LIBRE_API_KEY)  # type: ignore
                        except TypeError:
                            try:
                                libre = LibreTranslator(source="auto", target=target_lang, base_url=base_url)  # type: ignore
                            except TypeError:
                                libre = LibreTranslator(source="auto", target=target_lang)  # type: ignore
                        if hasattr(libre, "translate_batch"):
                            res = libre.translate_batch(texts_batch)  # type: ignore
                        else:
                            res = [libre.translate(t) for t in texts_batch]  # type: ignore
                    elif engine_name == "deepl_web":
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
                            results_web: List[str] = []
                            try:
                                base_url_web = "https://www.deepl.com/translator"
                                driver.get(base_url_web)
                                # Try to accept cookies quietly
                                try:
                                    cookie_btn = WebDriverWait(driver, 3).until(
                                        EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="cookie-banner-strict-accept-selected"]'))
                                    )
                                    cookie_btn.click()
                                except Exception:
                                    pass

                                for txt in texts_batch:
                                    if cancel_check and cancel_check():
                                        break
                                    if not txt.strip():
                                        results_web.append(txt)
                                        continue
                                    driver.get("about:blank")
                                    tgt = target_lang.upper()
                                    if tgt == "EN": tgt = "EN-US"
                                    if tgt == "PT": tgt = "PT-BR"
                                    url = f"https://www.deepl.com/translator#auto/{urllib.parse.quote(tgt)}/{urllib.parse.quote(txt[:4500])}"
                                    driver.get(url)
                                    try:
                                        out_elem = WebDriverWait(driver, 10).until(
                                            EC.presence_of_element_located((By.CSS_SELECTOR, 'd-textarea[aria-labelledby="translation-results-heading"]'))
                                        )
                                        time.sleep(1)
                                        results_web.append(out_elem.text or txt)
                                    except Exception:
                                        results_web.append(txt)
                            finally:
                                driver.quit()
                            res = results_web
                        except Exception:
                            res = None

                    if isinstance(res, list) and len(res) == len(texts_batch):
                        # Filter invalid here so we can retry!
                        if any(_is_invalid_translation(r) for r in res):
                            raise ValueError("Invalid translation response from primary engine")
                        return res
                finally:
                    _API_SEM.release()
            except Exception:
                time.sleep(1.0 * (attempt + 1))
        
        # If batch mode failed, we can fallback to per-item translation for Google Translator to salvage it
        # This will prevent the whole batch of 100 from being skipped just because 1 failed or rate limited
        salvaged = []
        if engine_name == "google" and google is not None:
            for t in texts_batch:
                if cancel_check and cancel_check():
                    salvaged.append(t)
                    continue
                _API_SEM.acquire()
                try:
                    for _ in range(2):
                        try:
                            # Try translating this single item
                            tmp = google.translate(t)
                            if not _is_invalid_translation(tmp):
                                salvaged.append(tmp)
                                break
                        except Exception:
                            time.sleep(0.5)
                    else:
                        salvaged.append(t)
                finally:
                    _API_SEM.release()
            return salvaged
            
        return None

    # Branch 1: MyMemory-first (auto + mmemory_first) – keep original logic with small tweaks
    if force_mymemory or auto_mm_first:
        if mymemory is None:
            target_code = _map_lang_for_mymemory(target_lang)
            mymemory = MyMemoryTranslator(source="en-GB", target=target_code)

        def _mm_translate_one(text: str) -> str:
            for attempt in range(5):
                try:
                    _API_SEM.acquire()
                    try:
                        res = mymemory.translate(text)
                        if _is_invalid_translation(res):
                            raise ValueError("Invalid translation response")
                        return res
                    finally:
                        _API_SEM.release()
                except Exception:
                    time.sleep(0.6 * (attempt + 1))
            return text

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
                        if isinstance(res, list) and not any(_is_invalid_translation(r) for r in res):
                            for src, dst in zip(b, res):
                                translated_map[src] = dst if dst is not None else src
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
                if isinstance(res, list) and len(res) == len(b) and not any(_is_invalid_translation(r) for r in res):
                    with lock:
                        for src, dst in zip(b, res):
                            translated_map[src] = dst if dst is not None else src
                else:
                    # If primary fails, retry individually to salvage the batch
                    # This helps translate completely without failing the whole batch
                    with lock:
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
            for attempt in range(5):
                try:
                    _API_SEM.acquire()
                    try:
                        res = mymemory.translate(text)
                        if _is_invalid_translation(res):
                            raise ValueError("Invalid translation response")
                        return res
                    finally:
                        _API_SEM.release()
                except Exception:
                    time.sleep(0.6 * (attempt + 1))
            return text

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

    # Finalize: ensure every unique text has a mapping
    for t in unique_texts:
        if t not in translated_map:
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
                                    font=("Segoe UI", max(12, self.size // 7), "bold"))
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


class _RoundedCard(ttk.Frame):
    # shadow_offset=0 draws a 1px outline instead of a drop shadow (flat panel look)
    def __init__(self, parent, radius: int = 12, margin: int = 6, fill: str = "#ffffff", shadow: str = "#d6dce6", shadow_offset: int = 0, min_height: int = 96) -> None:
        super().__init__(parent)
        self.radius = radius
        self.margin = margin
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
        self._win_id = self.canvas.create_window((margin, margin), window=self.content, anchor="nw")
        self.canvas.bind("<Configure>", self._on_resize)
        self.content.bind("<Configure>", self._on_content_config)
        self._redraw()

    def _on_resize(self, _e=None) -> None:
        try:
            w = max(1, self.canvas.winfo_width())
            h = max(1, self.canvas.winfo_height())
            # update inner window width to fit card minus margins
            self.canvas.itemconfigure(self._win_id, width=max(1, w - 2 * self.margin))
            self.canvas.coords(self._win_id, self.margin, self.margin)
            self._redraw()
        except Exception:
            pass

    def set_colors(self, fill: str, shadow: str) -> None:
        self.fill = fill
        self.shadow = shadow
        try:
            self.canvas.configure(bg=self.fill)
        except Exception:
            pass
        self._redraw()

    def set_min_height(self, h: int) -> None:
        self.min_height = max(1, int(h))
        try:
            ch = max(self.min_height, self.content.winfo_reqheight() + 2 * self.margin)
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
            needed = self.content.winfo_reqheight() + 2 * self.margin
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
        except Exception:
            pass

    def _on_canvas(self, _e=None):
        try:
            cw = self.canvas.winfo_width()
            if cw > 0:
                self.canvas.itemconfigure(self._win_id, width=cw)
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
        # Root with optional DnD
        if TkinterDnD:
            self.root = TkinterDnD.Tk()  # type: ignore
        else:
            self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.after(10, self.fix_window_focus)
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(10, lambda: self.root.attributes("-topmost", False))
        self.root.title("Subtitle PRO")
        # Başlık çubuğunu koyu yapmayı dene (hemen, kök pencere oluşunca)
        try:
            _enable_win_dark_titlebar(self.root.winfo_id(), True)
            try:
                # Ek olarak doğrudan DWM çağrısı (bazı sistemlerde daha etkili)
                import ctypes as _ct
                hwnd = _ct.c_void_p(int(self.root.winfo_id()))
                if hwnd.value:
                    val = _ct.c_int(1)
                    _ct.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, _ct.byref(val), _ct.sizeof(val))
            except Exception:
                pass
        except Exception:
            pass
        # Uygulama simgesi
        try:
            app_dir = os.path.dirname(__file__)
            png_icon_pref = os.path.join(app_dir, "app_icon.png")  # tercih edilen
            png_icon = os.path.join(app_dir, "icon.png")           # geri dönüş
            ico_icon = os.path.join(app_dir, "icon.ico")
            try:
                pick_png = png_icon_pref if os.path.exists(png_icon_pref) else png_icon
                if os.path.exists(pick_png):
                    self._app_icon = tk.PhotoImage(file=pick_png)
                    self.root.iconphoto(True, self._app_icon)
            except Exception:
                pass
            try:
                if os.path.exists(ico_icon):
                    self.root.iconbitmap(default=ico_icon)
            except Exception:
                pass
        except Exception:
            pass
        # Enable per-monitor DPI awareness on Windows for crisp UI
        try:
            if sys.platform.startswith("win"):
                ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
        except Exception:
            pass
        # Start in a comfortable size, allow free resize; open maximized when possible
        self.root.geometry("1024x680")
        self.root.resizable(True, True)
        try:
            self.root.minsize(1024, 680)
        except Exception:
            pass
        try:
            self.root.state("zoomed")
        except Exception:
            # Fallback to near-fullscreen geometry
            try:
                sw = self.root.winfo_screenwidth(); sh = self.root.winfo_screenheight()
                w = max(1024, int(sw * 0.92)); h = max(680, int(sh * 0.88))
                x = (sw - w) // 2; y = (sh - h) // 2
                self.root.geometry(f"{w}x{h}+{x}+{y}")
            except Exception:
                pass
        # Preferred minimum size when showing advanced sections
        self._show_min_w = 1024
        self._show_min_h = 680
        try:
            style = ttk.Style()
            style.theme_use("clam")
            # Softer, modern spacing
            style.configure("TButton", padding=(12, 8))
            style.configure("Accent.TButton", padding=(14, 10))
            style.configure("TProgressbar", thickness=14)
            style.configure("TLabelframe", padding=8)
            style.configure("Treeview", rowheight=32)
            # Modern rounded buttons and inputs
            style.configure("TButton", relief="flat")
            style.map("TButton", relief=[("pressed", "flat"), ("active", "flat")])
            # Inputs spacing & modern combobox feel
            try:
                style.configure("TEntry", padding=(10, 6))
                style.configure("TCombobox", padding=(10, 6))
                style.configure("TMenubutton", padding=(10, 6))
            except Exception:
                pass
            # Treeview polish: larger heading paddings and nicer selection
            try:
                style.configure("Treeview.Heading", padding=(8, 6))
                style.map("Treeview",
                          background=[("selected", "#e6f0ff")],
                          foreground=[("selected", "#0f172a")])
            except Exception:
                pass
            # Scrollbar styling (vertical)
            style.layout("Modern.Vertical.TScrollbar",
                         [("Vertical.Scrollbar.trough",
                           {"children": [("Vertical.Scrollbar.thumb", {"expand": True, "sticky": "nswe"})],
                            "sticky": "ns"})])
            style.configure("Modern.Vertical.TScrollbar", troughcolor="#e8ebf2", background="#c3c9d6", bordercolor="#e8ebf2", lightcolor="#c3c9d6", darkcolor="#c3c9d6")
            style.map("Modern.Vertical.TScrollbar",
                      background=[("active", "#9aa3b6"), ("pressed", "#818aa0")])
            # Modern horizontal scrollbar
            style.layout("Modern.Horizontal.TScrollbar",
                         [("Horizontal.Scrollbar.trough",
                           {"children": [("Horizontal.Scrollbar.thumb", {"expand": True, "sticky": "nswe"})],
                            "sticky": "we"})])
            style.configure("Modern.Horizontal.TScrollbar", troughcolor="#e8ebf2", background="#c3c9d6", bordercolor="#e8ebf2", lightcolor="#c3c9d6", darkcolor="#c3c9d6")
            style.map("Modern.Horizontal.TScrollbar",
                      background=[("active", "#9aa3b6"), ("pressed", "#818aa0")])
        except Exception:
            pass

        # ttkbootstrap - initialize early
        self._bs = None
        if TBStyle is not None:
            try:
                self._bs = TBStyle(theme=self._default_bs_theme(), master=self.root)  # type: ignore
            except Exception:
                self._bs = None

        # Font scaling
        self.font_scale_var = tk.DoubleVar(value=1.1)
        self._base_fonts = {}
        self._base_font_sizes = {}
        self._init_base_fonts()

        # Initialize UI language defaults before building language maps
        self.ui_lang_var = tk.StringVar(value=("English"))
        self.ui_lang_code = "en"
        try:
            import sys as _sys
            setattr(_sys.modules[__name__], "_CURRENT_UI_LANG_CODE", self.ui_lang_code)
        except Exception:
            pass
        # If settings has a saved UI language, apply it BEFORE building language maps
        try:
            if os.path.exists(_SETTINGS_FILE):
                with open(_SETTINGS_FILE, "r", encoding="utf-8") as _rf_pre:
                    _cfg_pre = json.load(_rf_pre) or {}
                ui_code_pre = _cfg_pre.get("ui_lang_code")
                if ui_code_pre:
                    self.ui_lang_code = str(ui_code_pre)
                    try:
                        import sys as _sys
                        setattr(_sys.modules[__name__], "_CURRENT_UI_LANG_CODE", self.ui_lang_code)
                    except Exception:
                        pass
        except Exception:
            pass
        # Build UI language list from ui_translations.json (localized later)
        self.lang_map = _get_supported_langs(self.ui_lang_code)  # display name (localized) -> code, for target languages
        # Start with codes from JSON; we'll localize names per current UI lang
        _ui_map_raw = _get_ui_langs_from_json()  # name (initial) -> code
        self.ui_codes = sorted(set(_ui_map_raw.values()))
        self.ui_lang_map = {}  # localized name -> code (filled below)
        self.ui_lang_names = []
        self.lang_names = sorted(self.lang_map.keys())
        # Localized target language display map will be built based on UI language
        self.target_lang_map: Dict[str, str] = {}
        self.target_lang_names: List[str] = []
        self.target_lang_var = tk.StringVar(value="Turkish" if "Turkish" in self.lang_map else (self.lang_names[0] if self.lang_names else ""))
        # UI language defaults already initialized above
        self._ui_cache: Dict[str, Dict[str, str]] = {}

        self.input_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar()
        self.progress_var = tk.DoubleVar(value=0.0)
        self.status_var = tk.StringVar(value=self._tr("Ready"))

        self._thread: Optional[threading.Thread] = None
        self._cancel = False
        self._auto_output = True  # auto-update output path suggestion
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
        self._style = ttk.Style()
        self.file_items: Dict[str, str] = {}  # path -> iid
        self.item_to_path: Dict[str, str] = {}  # iid -> path
        self.file_added_ts: Dict[str, float] = {}
        self.files: List[str] = []
        # Custom dictionary
        self.dict_mode_var = tk.StringVar(value="off")  # off/pre/post/both
        self.dict_path_var = tk.StringVar(value="")
        self.custom_terms: Dict[str, str] = {}
        # Engine selection
        self.engine_var = tk.StringVar(value="auto")  # auto/google/mymemory

        # Output related state used in both main UI and dialogs
        self.save_next_var = tk.BooleanVar(value=True)
        self.outdir_var = tk.StringVar(value="")
        self.clean_after_var = tk.BooleanVar(value=False)
        self.pdf_mode_var = tk.StringVar(value="pdf")  # 'pdf' or 'txt'
        # Skip files that already appear to be in target language
        self.skip_same_lang_var = tk.BooleanVar(value=True)

        self._log_queue: "queue.Queue[Callable[[], object]]" = queue.Queue()
        self._build_ui()
        self._load_settings()
        self.root.after(100, self._drain_log_queue)
        # UI language packs ship with the app (ui_translations.json). They used to be
        # re-translated through Google on every launch, which burned the rate limit;
        # regenerate them explicitly with:  translate_srt.py --build-ui-json

        # --- Custom Fluent Titlebar ---
        bg_color = self._bs.colors.bg if getattr(self, '_bs', None) is not None else self.root.cget('bg')
        fg_color = self._contrast_fg(self.root, bg_color)
        self.titlebar = tk.Frame(self.root, bg=bg_color, relief="flat", height=32)
        self.titlebar.place(x=0, y=0, relwidth=1)

        # --- Sol taraf: başlık ---

        title_label = tk.Label(self.titlebar, text="Subtitle PRO – Multi Translator",
                               bg=bg_color, fg=fg_color,
                               font=("Segoe UI", 10, "bold"))
        title_label.pack(side="left", padx=10, pady=4)


        # --- Sağ taraf: pencere kontrol butonları ---
        btn_frame = tk.Frame(self.titlebar, bg=bg_color)
        btn_frame.pack(side="right", padx=(0, 6), pady=0)

        def close_app():
            self._on_close()  # asks for confirmation while a translation is running

        def minimize():
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                SW_MINIMIZE = 6
                ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
            except Exception:
                pass

        def maximize_restore():
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                SW_SHOWMAXIMIZED = 3
                SW_SHOWNORMAL = 1
                # Check if window is maximized using IsZoomed
                if ctypes.windll.user32.IsZoomed(hwnd):
                    # Restore to normal
                    ctypes.windll.user32.ShowWindow(hwnd, SW_SHOWNORMAL)
                else:
                    # Maximize
                    ctypes.windll.user32.ShowWindow(hwnd, SW_SHOWMAXIMIZED)
            except Exception:
                # Fallback: try toggling via geometry
                try:
                    if self.root.winfo_width() >= self.root.winfo_screenwidth() - 10:
                        # Likely maximized, restore
                        self.root.geometry("1024x680")
                    else:
                        # Maximize
                        sw = self.root.winfo_screenwidth()
                        sh = self.root.winfo_screenheight()
                        self.root.geometry(f"{sw}x{sh}+0+0")
                except Exception:
                    pass

        # --- Yeni buton stilleri ---
        def make_btn(parent, text, command, fg, hover_bg, active_fg):
            b = tk.Label(parent, text=text, bg=bg_color, fg=fg,
                         width=5, height=1, font=("Segoe UI", 11, "bold"))
            b.pack(side="left", padx=1)
            b.bind("<Enter>", lambda e, btn=b: btn.config(bg=hover_bg, fg=active_fg))
            b.bind("<Leave>", lambda e, btn=b: btn.config(bg=bg_color, fg=fg))
            b.bind("<Button-1>", lambda e: command())
            return b

        # --- Renkli ve görünür hale getirme ---
        make_btn(btn_frame, "–", minimize, fg="#69c0ff", hover_bg="#1f3b4d", active_fg="white")   # Minimize
        make_btn(btn_frame, "□", maximize_restore, fg="#d9d9d9", hover_bg="#333333", active_fg="white")  # Maximize
        make_btn(btn_frame, "✕", close_app, fg="#ff4d4f", hover_bg="#a8071a", active_fg="white")  # Close

        # --- Titlebar'ı sürükleme ---
        self.root.after(10, self.enable_drag)

        # Settings are loaded after _build_ui, so re-apply everything that depends on them
        # (previously a saved dark theme / font size / target language was ignored on start).
        self._apply_loaded_settings()

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        # Ensure log/sort vars exist before any UI uses them
        try:
            if not hasattr(self, 'log_info_var'):
                self.log_info_var = tk.BooleanVar(value=True)
            if not hasattr(self, 'log_ok_var'):
                self.log_ok_var = tk.BooleanVar(value=True)
            if not hasattr(self, 'log_err_var'):
                self.log_err_var = tk.BooleanVar(value=True)
            if not hasattr(self, '_log_entries'):
                self._log_entries = []
            if not hasattr(self, '_sort_reverse'):
                self._sort_reverse = {"dosya": False, "boyut": False, "durum": False, "eklenme": False}
        except Exception:
            pass

        # Spacer to avoid custom titlebar overlap
        try:
            if not hasattr(self, '_top_spacer'):
                bgc = self._bs.colors.bg if getattr(self, '_bs', None) is not None else self.root.cget('bg')
                self._top_spacer = tk.Frame(self.root, height=32, bg=bgc)
                self._top_spacer.pack(side="top", fill="x")
        except Exception:
            pass

        # Title bar (modern header) inside scrollable root
        self.root_scroll = _ScrollableFrame(self.root)
        self.root_scroll.pack(fill="both", expand=True)
        try:
            # Remove any default borders/highlights that appear as white lines
            if hasattr(self.root_scroll, 'canvas'):
                self.root_scroll.canvas.configure(borderwidth=0, highlightthickness=0)
            if hasattr(self.root_scroll, 'content'):
                self.root_scroll.content.configure(borderwidth=0, relief="flat")
        except Exception:
            pass
        titlebar = ttk.Frame(self.root_scroll.content, style="AppHeader.TFrame")
        try:
            titlebar.configure(borderwidth=0, relief="flat")
        except Exception:
            pass
        titlebar.pack(fill="x", padx=10, pady=(10, 6))
        left_hdr = ttk.Frame(titlebar)
        left_hdr.pack(side="left")
        ttk.Label(left_hdr, text="🌐", font=("Segoe UI Emoji", 16), style="AppHeader.TLabel").pack(side="left", padx=(0, 8))
        ttl = ttk.Frame(left_hdr, style="AppHeader.TFrame")
        ttl.pack(side="left")
        ttk.Label(ttl, text=self._tr("Subtitle PRO – Multi Translator"), font=("Segoe UI", 14, "bold"), style="AppHeader.TLabel").pack(anchor="w")
        self.lbl_app_subtitle = ttk.Label(ttl, text=self._tr("Batch subtitle & document translator"), style="AppHeader.TLabel")
        self.lbl_app_subtitle.pack(anchor="w")
        # subtle separator line under header (ttk with themed style)
        # (separator not packed: it rendered as a stray line across the top of the header)
        self.sep_hdr = ttk.Separator(titlebar, orient="horizontal", style="AppSeparator.TSeparator")
        right_hdr = ttk.Frame(titlebar)
        right_hdr.pack(side="right")
        # Theme switch
        self.lbl_hdr_theme = ttk.Label(right_hdr, text=self._tr("Theme:"))
        self.lbl_hdr_theme.pack(side="left", padx=(0, 6))
        # theme_var / accent_var hold internal keys; the comboboxes show translated labels
        self.theme_var = tk.StringVar(value=("dark" if self.dark_mode_var.get() else "light"))
        self.cmb_theme = ttk.Combobox(right_hdr, state="readonly", width=9)
        self.cmb_theme.pack(side="left", padx=(0, 12))

        def _on_theme_pick(_e=None):
            dark = self.cmb_theme.current() == 1
            self.theme_var.set("dark" if dark else "light")
            self.dark_mode_var.set(dark)
            self._apply_theme()
            self._refresh_menu_bar()
            self._refresh_status_bar()
            self._save_settings()
        self.cmb_theme.bind("<<ComboboxSelected>>", _on_theme_pick)
        # Accent selector
        self.lbl_hdr_accent = ttk.Label(right_hdr, text=self._tr("Accent color:"))
        self.lbl_hdr_accent.pack(side="left", padx=(0, 6))
        self.cmb_accent = ttk.Combobox(right_hdr, state="readonly", width=10)
        self.cmb_accent.pack(side="left", padx=(0, 12))

        def _on_accent_pick(_e=None):
            idx = self.cmb_accent.current()
            if 0 <= idx < len(self.ACCENTS):
                self.accent_var.set(self.ACCENTS[idx])
            self._apply_theme()
            self._refresh_menu_bar()
            self._save_settings()
        self.cmb_accent.bind("<<ComboboxSelected>>", _on_accent_pick)
        self._sync_header_combos()
        # Header menu (About / Settings)
        try:
            self.header_menu_btn = ttk.Menubutton(right_hdr, text="☰", width=3)
            self.header_menu_btn.pack(side="left", padx=(0, 12))
            self.header_menu = tk.Menu(self.header_menu_btn, tearoff=False)
            # The native menubar is invisible because the window uses overrideredirect, so
            # everything users need must also be reachable from this header menu.
            self.header_menu.add_command(label=self._tr("Add..."), command=self._add_files)
            self.header_menu.add_separator()
            self.header_menu.add_command(label=self._tr("Output settings..."), command=self._open_output_dialog)
            self.header_menu.add_command(label=self._tr("Advanced settings..."), command=self._open_advanced_dialog)
            self.header_menu.add_command(label=self._tr("Preferences..."), command=self._open_preferences)
            self.header_menu.add_separator()
            self.header_menu.add_checkbutton(label=self._tr("Compact mode"), onvalue=True, offvalue=False, variable=self.compact_mode_var,
                                             command=lambda: (self._apply_theme(), self._save_settings()))
            self.header_font_menu = tk.Menu(self.header_menu, tearoff=False)
            for scale in (0.9, 1.0, 1.1, 1.2, 1.3):
                self.header_font_menu.add_radiobutton(label=f"{int(scale*100)}%", value=scale, variable=self.font_scale_var,
                                                      command=lambda: (self._apply_font_scale(), self._save_settings()))
            self.header_menu.add_cascade(label=self._tr("Font size"), menu=self.header_font_menu)
            self.header_menu.add_separator()
            self.header_menu.add_command(label=self._tr("About"), command=self._show_about)
            self.header_menu.add_command(label=self._tr("Exit"), command=self._on_close)
            self._header_menu_keys = [(0, "Add..."), (2, "Output settings..."), (3, "Advanced settings..."),
                                      (4, "Preferences..."), (6, "Compact mode"), (7, "Font size"), (9, "About"), (10, "Exit")]
            self.header_menu_btn.configure(menu=self.header_menu)
            try:
                # Apply modern style to menubutton if bootstrap available
                if TBStyle is not None:
                    self.header_menu_btn.configure(style='secondary.TMenubutton')
            except Exception:
                pass
        except Exception:
            pass
        # UI language quick selector
        self.lbl_hdr_ui = ttk.Label(right_hdr, text=self._tr("UI language:"))
        self.lbl_hdr_ui.pack(side="left", padx=(0, 6))
        # Localize UI language names for current UI language
        self._rebuild_ui_lang_names()
        self.cmb_ui_quick = ttk.Combobox(right_hdr, state="readonly", values=self.ui_lang_names, textvariable=self.ui_lang_var, width=18)
        self.cmb_ui_quick.pack(side="left")
        self.cmb_ui_quick.bind("<<ComboboxSelected>>", self._on_ui_lang_change)

        # ---- Body: file queue + log on the left (flexible), translation panel on the right ----
        body = ttk.Frame(self.root_scroll.content)
        body.pack(fill="both", expand=True, padx=6)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0, minsize=380)
        body.rowconfigure(0, weight=1)
        self.left_col = ttk.Frame(body)
        self.left_col.grid(row=0, column=0, sticky="nsew")
        self.right_col = ttk.Frame(body)
        self.right_col.grid(row=0, column=1, sticky="nsew")
        # Tooltips are re-translated on UI language change: attr -> English source text
        self._tooltips: Dict[str, object] = {}
        self._tooltip_keys: Dict[str, str] = {}

        # File queue (rounded card)
        files_card = _RoundedCard(self.left_col, min_height=300)
        files_card.pack(fill="both", expand=True, padx=6, pady=6)
        self.lbl_files_header = self._build_section_header(files_card.content, self._tr("📁 Files"), ctx="info")
        # Plain frame: a LabelFrame here repeated the section title ("Files" twice)
        self.frm_files = ttk.Frame(files_card.content)
        self.frm_files.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        top_row = ttk.Frame(self.frm_files)
        top_row.pack(fill="x")
        self.btn_add = ttk.Button(top_row, text=self._tr("Add..."), command=self._add_files)
        self.btn_add.pack(side="left")
        self.btn_remove = ttk.Button(top_row, text=self._tr("Remove"), command=self._remove_selected)
        self.btn_remove.pack(side="left", padx=6)
        self.btn_clear = ttk.Button(top_row, text=self._tr("Clear"), command=self._clear_files)
        self.btn_clear.pack(side="left")
        if TkinterDnD and DND_FILES:
            self.lbl_dnd = ttk.Label(self.frm_files, text=self._tr("(Drag-and-drop supported)"), foreground="#94a3b8")
            self.lbl_dnd.pack(side="bottom", anchor="w", pady=(4, 0))  # below the list: keeps the button row short
        else:
            self.lbl_dnd = ttk.Label(self.frm_files, text=self._tr("(Install tkinterdnd2 for drag-and-drop)"), foreground="#94a3b8")
            self.lbl_dnd.pack(side="bottom", anchor="w", pady=(4, 0))
        # Secondary actions as compact icon buttons (their labels live in tooltips)
        self.toolbar = ttk.Frame(top_row)
        self.toolbar.pack(side="right")

        def _icon_btn(attr: str, icon: str, tip: str, cmd) -> None:
            b = ttk.Button(self.toolbar, text=icon, width=4, command=cmd)
            b.pack(side="left", padx=1)
            setattr(self, attr, b)
            self._tooltip_keys[attr] = tip
            self._tooltips[attr] = _Tooltip(b, self._tr(tip))

        _icon_btn("tb_remove_missing", "🧹", "Remove missing", self._remove_missing)
        _icon_btn("tb_preview", "👁", "Preview", self._preview_selected)
        _icon_btn("tb_open_selected_out", "📄", "Open selected output", self._open_selected_output)
        _icon_btn("tb_open_selected_outdir", "📂", "Open selected out folder", self._open_selected_output_folder)
        _icon_btn("tb_reveal_src", "🗂", "Reveal in Explorer", self._reveal_in_explorer)
        _icon_btn("tb_toggle_adv", "⚙", "Advanced settings...", self._open_advanced_dialog)
        self._adv_visible = False
        # Aliases kept for older code paths (tooltips/retranslation refer to these names)
        self.tb_add = self.btn_add
        self.tb_remove_selected = self.btn_remove
        # Filter row with a real placeholder (old version filtered by the placeholder text itself)
        filter_row = ttk.Frame(self.frm_files)
        filter_row.pack(fill="x", pady=(6, 0))
        self.filter_var = tk.StringVar()
        self.ent_filter = ttk.Entry(filter_row, textvariable=self.filter_var)
        self.ent_filter.pack(fill="x")
        self._filter_placeholder_on = False

        def _filter_placeholder(show: bool) -> None:
            if show and not self.filter_var.get():
                self._filter_placeholder_on = True
                self.ent_filter.configure(foreground="#94a3b8")
                self.filter_var.set("🔎 " + self._tr("Filter files..."))
            elif not show and self._filter_placeholder_on:
                self._filter_placeholder_on = False
                self.ent_filter.configure(foreground="")
                self.filter_var.set("")
        self._filter_placeholder = _filter_placeholder
        self.ent_filter.bind("<FocusIn>", lambda e: _filter_placeholder(False))
        self.ent_filter.bind("<FocusOut>", lambda e: _filter_placeholder(True))
        self.ent_filter.bind("<KeyRelease>", lambda e: self._apply_filter("" if self._filter_placeholder_on else self.filter_var.get().strip()))
        _filter_placeholder(True)
        self._tooltip_keys["ent_filter"] = "Type to filter by filename"
        self._tooltips["ent_filter"] = _Tooltip(self.ent_filter, self._tr("Type to filter by filename"))

        cols = ("dosya", "boyut", "durum", "eklenme")
        self.tree = ttk.Treeview(self.frm_files, columns=cols, show="headings")
        try:
            self.tree.configure(borderwidth=0, highlightthickness=0)
        except Exception:
            pass
        self.tree.heading("dosya", text=self._tr("File"))
        self.tree.heading("boyut", text=self._tr("Size"))
        self.tree.heading("durum", text=self._tr("Status"))
        self.tree.heading("eklenme", text=self._tr("Added"))
        self.tree.column("dosya", width=520, anchor="w")
        self.tree.column("boyut", width=120, anchor="center")
        self.tree.column("durum", width=140, anchor="center")
        self.tree.column("eklenme", width=160, anchor="center")
        # We'll store file path in iid text via separate hidden column-like
        self.tree.pack(fill="both", expand=True, pady=6)
        self.tree.bind("<Double-1>", self._on_preview_event)
        # Click to sort by column
        try:
            self.tree.heading("dosya", command=lambda c="dosya": self._sort_by_column(c))
            self.tree.heading("boyut", command=lambda c="boyut": self._sort_by_column(c))
            self.tree.heading("durum", command=lambda c="durum": self._sort_by_column(c))
            self.tree.heading("eklenme", command=lambda c="eklenme": self._sort_by_column(c))
        except Exception:
            pass
        # Alternating row colors
        try:
            self.tree.tag_configure('oddrow', background='#f3f6fb')
            self.tree.tag_configure('evenrow', background='#ffffff')
        except Exception:
            pass

        # Compact mode (reachable from the header menu; widget kept for retranslation/state)
        self.chk_compact = ttk.Checkbutton(self.toolbar, text=self._tr("Compact mode"), variable=self.compact_mode_var, command=lambda: (self._apply_theme(), self._refresh_menu_bar(), self._save_settings()))
        # Menu bar
        try:
            self.menubar = tk.Menu(self.root)
            self.root.config(menu=self.menubar)
            # Keep references for runtime retranslation
            self.m_file = tk.Menu(self.menubar, tearoff=False)
            self.m_view = tk.Menu(self.menubar, tearoff=False)
            self.m_settings = tk.Menu(self.menubar, tearoff=False)
            self.m_help = tk.Menu(self.menubar, tearoff=False)
            self.menubar.add_cascade(label=self._tr("File"), menu=self.m_file)
            self.menubar.add_cascade(label=self._tr("View"), menu=self.m_view)
            self.menubar.add_cascade(label=self._tr("Settings"), menu=self.m_settings)
            self.menubar.add_cascade(label=self._tr("Help"), menu=self.m_help)
            # File
            self.m_file.add_command(label=self._tr("Add..."), command=self._add_files)
            self.m_file.add_separator()
            self.m_file.add_command(label=self._tr("Exit"), command=self.root.destroy)
            # View
            self.m_view.add_checkbutton(label=self._tr("Dark theme"), onvalue=True, offvalue=False, variable=self.dark_mode_var, command=lambda: (self._apply_theme(), self._refresh_menu_bar(), self._save_settings()))
            self.m_view.add_checkbutton(label=self._tr("Compact mode"), onvalue=True, offvalue=False, variable=self.compact_mode_var, command=lambda: (self._apply_theme(), self._refresh_menu_bar(), self._save_settings()))
            if TBStyle is not None:
                themes = ["flatly","darkly","cosmo","cyborg","journal","litera","lumen","minty","pulse","sandstone","simplex","solar","superhero","united","yeti"]
                sm = tk.Menu(self.m_view, tearoff=False)
                def _set_bs_theme(tname: str) -> None:
                    try:
                        self.bs_theme_var.set(tname)
                        # Recreate or switch ttkbootstrap style consistently
                        if getattr(self, '_bs', None) is None:
                            self._bs = TBStyle(theme=tname, master=self.root)  # type: ignore
                        else:
                            try:
                                self._bs.theme_use(tname)  # type: ignore
                            except Exception:
                                # Some versions require reinit for full apply
                                self._bs = TBStyle(theme=tname, master=self.root)  # type: ignore
                        # Re-apply component styles and refresh UI
                        self._apply_bootstrap_styles()
                        self.root.update_idletasks()
                        self._save_settings()
                    except Exception:
                        pass
                for th in themes:
                    sm.add_radiobutton(label=th, value=th, variable=self.bs_theme_var, command=lambda tn=th: _set_bs_theme(tn))
                self.m_view.add_cascade(label=self._tr("Bootstrap theme"), menu=sm)
            # Font scale submenu
            fm = tk.Menu(self.m_view, tearoff=False)
            for scale in (0.9, 1.0, 1.1, 1.2, 1.3):
                fm.add_radiobutton(label=f"{int(scale*100)}%", value=scale, variable=self.font_scale_var, command=lambda s=scale: (self.font_scale_var.set(s), self._apply_font_scale(), self._save_settings()))
            self.m_view.add_cascade(label=self._tr("Font size"), menu=fm)
            # Settings
            self.m_settings.add_command(label=self._tr("Output settings..."), command=self._open_output_dialog)
            self.m_settings.add_command(label=self._tr("Advanced settings..."), command=self._open_advanced_dialog)
            self.m_settings.add_separator()
            self.m_settings.add_command(label=self._tr("Preferences..."), command=self._open_preferences)
            # Help
            self.m_help.add_command(label=self._tr("About"), command=self._show_about)
        except Exception:
            pass

        # Context menu on tree
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

        # Drop target area (bind to tree)
        if TkinterDnD and DND_FILES:
            try:
                self.tree.drop_target_register(DND_FILES)  # type: ignore
                self.tree.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore
            except Exception:
                pass
        # Ensure the tree has a minimum height
        try:
            self.tree.configure(height=10)
        except Exception:
            pass

        # ---- Right panel: translation settings + start/cancel ----
        tr_card = _RoundedCard(self.right_col, min_height=230)
        tr_card.pack(fill="x", padx=6, pady=6)
        self.lbl_translate_header = self._build_section_header(tr_card.content, self._tr("🌍 Translation"), ctx="primary")
        frm_lang = ttk.Frame(tr_card.content)
        frm_lang.pack(fill="x", padx=12, pady=(0, 10))
        self.lbl_target = ttk.Label(frm_lang, text=self._tr("Target language:"))
        self.lbl_target.pack(anchor="w")
        try:
            self._rebuild_target_lang_names()
        except Exception:
            pass
        self.cmb_lang = ttk.Combobox(frm_lang, values=(self.target_lang_names or self.lang_names), textvariable=self.target_lang_var, state="readonly", height=20)
        self.cmb_lang.pack(fill="x", pady=(2, 10))
        self.cmb_lang.bind("<<ComboboxSelected>>", lambda e: (self._maybe_update_output_suggestion(), self._save_settings()))
        self.lbl_engine_main = ttk.Label(frm_lang, text=self._tr("Engine:"))
        self.lbl_engine_main.pack(anchor="w")
        eng_grid = ttk.Frame(frm_lang)
        eng_grid.pack(fill="x", pady=(2, 10))
        self.engine_radios: Dict[str, object] = {}
        engines = (
            ("auto", "Auto", "Google first, MyMemory as fallback"),
            ("google", "Google", "Google Translate (no key)"),
            ("mymemory", "MyMemory", "MyMemory (no key, small daily quota)"),
            ("deepl", "DeepL", "DeepL API (requires API key)"),
            ("deepl_web", "DeepL (Web)", "DeepL website automation (experimental)"),
            ("libre", "Libre", "LibreTranslate (self-hosted or API key)"),
        )
        for i, (val, txt, tip) in enumerate(engines):
            rb = ttk.Radiobutton(eng_grid, text=self._tr(txt), value=val, variable=self.engine_var,
                                 command=lambda: (self._refresh_status_bar(), self._save_settings()))
            rb.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 16), pady=1)
            self.engine_radios[val] = rb
            self._tooltip_keys[f"engine_{val}"] = tip
            self._tooltips[f"engine_{val}"] = _Tooltip(rb, self._tr(tip))
        run_row = ttk.Frame(frm_lang)
        run_row.pack(fill="x")
        self.tb_start = ttk.Button(run_row, text=self._tr("▶ Start"), command=self._start, style="Primary.TButton")
        self.tb_start.pack(side="left", fill="x", expand=True)
        self.tb_cancel = ttk.Button(run_row, text=self._tr("⏹ Cancel"), command=self._cancel_run, state="disabled", style="Danger.TButton")
        self.tb_cancel.pack(side="left", padx=(6, 0))
        self.tb_start_sel_text = tk.StringVar(value="▶ " + self._tr("Translate selected files"))
        self.tb_start_sel = ttk.Button(frm_lang, textvariable=self.tb_start_sel_text, command=self._start_selected)
        self.tb_start_sel.pack(fill="x", pady=(6, 0))
        for attr, tip in (("tb_start", "Start translation (Ctrl+R)"), ("tb_cancel", "Cancel (Esc)"),
                          ("tb_start_sel", "Translate only the selected files (Ctrl+Shift+R)"),
                          ("btn_add", "Add files (Ctrl+O)"), ("btn_remove", "Remove selected files from the list")):
            self._tooltip_keys[attr] = tip
            self._tooltips[attr] = _Tooltip(getattr(self, attr), self._tr(tip))

        # Progress (right panel)
        prog_card = _RoundedCard(self.right_col, min_height=180)
        prog_card.pack(fill="both", expand=True, padx=6, pady=6)
        self.lbl_progress_header = self._build_section_header(prog_card.content, self._tr("⌛ Progress"), ctx="primary")
        frm_prog = ttk.Frame(prog_card.content)
        frm_prog.pack(fill="x", padx=12, pady=(0, 10))
        self.circ = _CircularProgress(frm_prog, size=150, thickness=14)
        self.circ.pack(pady=(0, 8))
        try:
            self.circ.set(0, f"{self._tr('ETA')}: --:--")
        except Exception:
            pass
        self.pbar = ttk.Progressbar(frm_prog, variable=self.progress_var, maximum=100)
        self.pbar.pack(fill="x")
        self.lbl_status = ttk.Label(frm_prog, textvariable=self.status_var, wraplength=340, justify="left")
        self.lbl_status.pack(anchor="w", fill="x", pady=(6, 0))

        # Advanced container with scrollable area
        self.adv_container = ttk.Frame(self.root)
        self.adv_canvas = tk.Canvas(self.adv_container, highlightthickness=0, bd=0)
        self.adv_vscroll = ttk.Scrollbar(self.adv_container, orient="vertical", command=self.adv_canvas.yview, style="Modern.Vertical.TScrollbar")
        self.adv_canvas.configure(yscrollcommand=self.adv_vscroll.set)
        self.adv_canvas.pack(side="left", fill="both", expand=True)
        # Ensure visible default height
        try:
            self.adv_canvas.configure(height=320)
        except Exception:
            pass
        self.adv_vscroll.pack(side="right", fill="y")
        self.adv_inner = ttk.Frame(self.adv_canvas)
        self.adv_canvas.create_window((0, 0), window=self.adv_inner, anchor="nw")
        self.adv_inner.bind("<Configure>", lambda e: self.adv_canvas.configure(scrollregion=self.adv_canvas.bbox("all")))
        # Mouse-wheel support
        def _adv_on_wheel(event):
            delta = 0
            if hasattr(event, 'delta') and event.delta:
                delta = -1 * (event.delta // 120)
            elif hasattr(event, 'num'):
                delta = -1 if event.num == 4 else (1 if event.num == 5 else 0)
            if delta:
                self.adv_canvas.yview_scroll(delta, "units")
        # Bind only while hovered; a global bind_all here used to hijack the main page's wheel
        for _seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.adv_canvas.bind(_seq, _adv_on_wheel)
        # Resize advanced area proportionally as the window changes
        self._adv_height_ratio = 0.4  # 40% of window height
        def _on_root_resize(event):
            try:
                total_h = max(self.root.winfo_height(), 1)
                target_h = int(total_h * self._adv_height_ratio)
                self.adv_canvas.configure(height=max(220, target_h))
            except Exception:
                pass
        self.root.bind('<Configure>', _on_root_resize)
        # Set initial advanced canvas height proportionally
        try:
            self.root.update_idletasks()
            init_total = max(self.root.winfo_height(), 1)
            self.adv_canvas.configure(height=max(260, int(init_total * self._adv_height_ratio)))
        except Exception:
            pass

        # Output options (moved to a separate window via menu; keep a hidden frame for i18n consistency)
        self.frm_out = ttk.LabelFrame(self.adv_inner, text=self._tr("Output"), style="Card.TLabelframe")
        # Do not pack here; shown in separate dialog
        rowo1 = ttk.Frame(self.frm_out)
        rowo1.pack(fill="x", pady=2)
        self.save_next_var = tk.BooleanVar(value=True)
        self.chk_save_next = ttk.Checkbutton(rowo1, text=self._tr("Save next to source"), variable=self.save_next_var)
        self.chk_save_next.pack(side="left")
        rowo2 = ttk.Frame(self.frm_out)
        rowo2.pack(fill="x", pady=2)
        self.lbl_outdir = ttk.Label(rowo2, text=self._tr("Output directory:"))
        self.lbl_outdir.pack(side="left")
        self.outdir_var = tk.StringVar(value="")
        self.ent_outdir = ttk.Entry(rowo2, textvariable=self.outdir_var)
        self.ent_outdir.pack(side="left", fill="x", expand=True, padx=6)
        self.btn_browse = ttk.Button(rowo2, text=self._tr("Browse"), command=self._choose_outdir)
        self.btn_browse.pack(side="left")
        self.btn_open_out = ttk.Button(rowo2, text=self._tr("Open output folder"), command=self._open_outdir)
        self.btn_open_out.pack(side="left", padx=6)
        # Post-process options
        rowo3 = ttk.Frame(self.frm_out)
        rowo3.pack(fill="x", pady=2)
        self.clean_after_var = tk.BooleanVar(value=False)
        self.chk_clean = ttk.Checkbutton(rowo3, text=self._tr("Remove [bracketed] notes from SRT after translate"), variable=self.clean_after_var)
        self.chk_clean.pack(side="left")
        # PDF output mode
        rowo4 = ttk.Frame(self.frm_out)
        rowo4.pack(fill="x", pady=2)
        ttk.Label(rowo4, text=self._tr("PDF output as:")).pack(side="left")
        ttk.Radiobutton(rowo4, text=self._tr("PDF"), value="pdf", variable=self.pdf_mode_var).pack(side="left", padx=(8,0))
        ttk.Radiobutton(rowo4, text=self._tr("TXT"), value="txt", variable=self.pdf_mode_var).pack(side="left", padx=(8,0))

        # Log panel in rounded card
        log_card = _RoundedCard(self.left_col, min_height=170)
        log_card.pack(fill="both", expand=False, padx=6, pady=6)
        self.lbl_log_header = self._build_section_header(log_card.content, self._tr("📝 Log"), ctx="secondary")
        frm_log = ttk.Frame(log_card.content)
        frm_log.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        # Log level filters
        lvl = ttk.Frame(frm_log)
        lvl.pack(fill="x", pady=(0, 4))
        self.chk_log_info = ttk.Checkbutton(lvl, text=self._tr("Info"), variable=self.log_info_var, command=self._refresh_log_view)
        self.chk_log_info.pack(side="left")
        self.chk_log_ok = ttk.Checkbutton(lvl, text=self._tr("OK"), variable=self.log_ok_var, command=self._refresh_log_view)
        self.chk_log_ok.pack(side="left", padx=(8,0))
        self.chk_log_err = ttk.Checkbutton(lvl, text=self._tr("Error"), variable=self.log_err_var, command=self._refresh_log_view)
        self.chk_log_err.pack(side="left", padx=(8,0))
        self.btn_log_clear = ttk.Button(lvl, text=self._tr("Clear"), command=lambda: (self._log_entries.clear(), self._refresh_log_view()))
        self.btn_log_clear.pack(side="right")
        self.btn_log_export = ttk.Button(lvl, text=self._tr("Export..."), command=self._export_logs)
        self.btn_log_export.pack(side="right", padx=(0,6))
        import tkinter.scrolledtext as scrolledtext
        self.txt_log = scrolledtext.ScrolledText(frm_log, height=5, wrap="word")
        self.txt_log.pack(fill="both", expand=True)
        try:
            self.txt_log.configure(relief="flat", borderwidth=0)
            # Colored tags for levels
            self.txt_log.tag_configure('info', foreground='#64748b')
            self.txt_log.tag_configure('ok', foreground='#16a34a')
            self.txt_log.tag_configure('error', foreground='#ef4444')
        except Exception:
            pass

        # Footer: Output controls + status bar in rounded card
        foot_card = _RoundedCard(self.root_scroll.content, min_height=80)
        foot_card.pack(fill="x", padx=12, pady=(0, 8))
        self.lbl_output_header = self._build_section_header(foot_card.content, self._tr("📦 Output"), ctx="secondary")
        footer = ttk.Frame(foot_card.content)
        footer.pack(fill="x", **pad)

        # Keep references with context for theme updates
        self.card_contexts = [
            (files_card, 'info'),
            (tr_card, 'primary'),
            (prog_card, 'primary'),
            (log_card, 'secondary'),
            (foot_card, 'secondary'),
        ]
        left_foot = ttk.Frame(footer)
        left_foot.pack(side="left", fill="x", expand=True)
        self.chk_save_next_main = ttk.Checkbutton(left_foot, text=self._tr("Save next to source"), variable=self.save_next_var, command=self._save_settings)
        self.chk_save_next_main.pack(side="left")
        self.lbl_outdir_main = ttk.Label(left_foot, text=self._tr("Output directory:"))
        self.lbl_outdir_main.pack(side="left", padx=(10, 6))
        self.ent_outdir_main = ttk.Entry(left_foot, textvariable=self.outdir_var, width=36)
        self.ent_outdir_main.pack(side="left")
        self.btn_browse_main = ttk.Button(left_foot, text=self._tr("Browse"), command=self._choose_outdir)
        self.btn_browse_main.pack(side="left", padx=(6, 0))
        self.btn_open_out_main = ttk.Button(left_foot, text=self._tr("Open output folder"), command=self._open_outdir)
        self.btn_open_out_main.pack(side="left", padx=(6, 0))
        # Own row under the output controls, so it is never squeezed/clipped by them
        right_foot = ttk.Frame(foot_card.content)
        right_foot.pack(side="bottom", fill="x", padx=10, pady=(0, 6))
        self.status_bar = ttk.Label(right_foot, text="")
        self.status_bar.pack(side="right")

        # Advanced settings (no longer shown inline)
        self.frm_adv = ttk.LabelFrame(self.adv_inner, text=self._tr("Advanced Settings"), style="Card.TLabelframe")
        row1 = ttk.Frame(self.frm_adv)
        row1.pack(fill="x", pady=2)
        self.lbl_batch = ttk.Label(row1, text=self._tr("Batch size (Google batch):"))
        self.lbl_batch.pack(side="left")
        Spinbox = getattr(ttk, "Spinbox", tk.Spinbox)
        spn_batch = Spinbox(row1, from_=10, to=500, textvariable=self.batch_size_var, width=8)
        spn_batch.pack(side="left", padx=8)
        row2 = ttk.Frame(self.frm_adv)
        row2.pack(fill="x", pady=2)
        self.lbl_mm = ttk.Label(row2, text=self._tr("Fallback concurrent jobs (MyMemory):"))
        self.lbl_mm.pack(side="left")
        spn_mm = Spinbox(row2, from_=1, to=16, textvariable=self.mm_workers_var, width=8)
        spn_mm.pack(side="left", padx=8)
        # Engine row
        row_eng = ttk.Frame(self.frm_adv)
        row_eng.pack(fill="x", pady=2)
        self.lbl_engine = ttk.Label(row_eng, text=self._tr("Engine:"))
        self.lbl_engine.pack(side="left")
        self.cmb_engine = ttk.Combobox(row_eng, values=["auto", "google", "mymemory", "deepl", "deepl_web", "libre"], textvariable=self.engine_var, state="readonly", width=12)
        self.cmb_engine.pack(side="left", padx=8)
        self.lbl_auto_priority = ttk.Label(row_eng, text=self._tr("Auto priority:"))
        self.lbl_auto_priority.pack(side="left", padx=(12, 4))
        self.auto_priority_var = tk.StringVar(value="google_first")
        self.cmb_auto_priority = ttk.Combobox(row_eng, values=["google_first", "mymemory_first"], textvariable=self.auto_priority_var, state="readonly", width=16)
        self.cmb_auto_priority.pack(side="left")
        # Custom dictionary row
        row_dict = ttk.Frame(self.frm_adv)
        row_dict.pack(fill="x", pady=2)
        ttk.Label(row_dict, text=self._tr("Custom dictionary:")).pack(side="left")
        self.cmb_dict_mode = ttk.Combobox(row_dict, values=["off", "pre", "post", "both"], textvariable=self.dict_mode_var, state="readonly", width=8)
        self.cmb_dict_mode.pack(side="left", padx=6)
        self.ent_dict = ttk.Entry(row_dict, textvariable=self.dict_path_var)
        self.ent_dict.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row_dict, text=self._tr("Browse"), command=self._choose_dict).pack(side="left")

        # Appearance & performance (no longer shown inline)
        self.frm_perf = ttk.LabelFrame(self.adv_inner, text=self._tr("Appearance & Performance"), style="Card.TLabelframe")
        rowp1 = ttk.Frame(self.frm_perf)
        rowp1.pack(fill="x", pady=2)
        self.chk_dark = ttk.Checkbutton(rowp1, text=self._tr("Dark theme"), variable=self.dark_mode_var, command=self._apply_theme)
        self.chk_dark.pack(side="left")
        rowp2 = ttk.Frame(self.frm_perf)
        rowp2.pack(fill="x", pady=2)
        self.chk_parallel = ttk.Checkbutton(rowp2, text=self._tr("Translate files in parallel"), variable=self.parallel_files_var)
        self.chk_parallel.pack(side="left")
        self.lbl_workers = ttk.Label(rowp2, text=self._tr("Workers:"))
        self.lbl_workers.pack(side="left", padx=(10, 0))
        spn_fw = Spinbox(rowp2, from_=1, to=4, textvariable=self.file_workers_var, width=5)
        spn_fw.pack(side="left", padx=8)
        # Preview button
        self.btn_preview = ttk.Button(self.frm_perf, text=self._tr("Preview"), command=self._preview_selected)
        self.btn_preview.pack(anchor="w", pady=4)

        # Initially keep advanced sections hidden (advanced moved to separate dialog)
        self._adv_visible = False
        # initial theme and i18n
        self._apply_theme()
        self._retranslate_ui(initial=True)
        self._apply_settings_to_ui()
        self._apply_bootstrap_styles()
        self._apply_font_scale()
        self._ensure_ui_font_family()
        # Shortcuts
        self.root.bind_all("<Control-o>", lambda e: self._add_files())
        self.root.bind_all("<Control-O>", lambda e: self._add_files())
        self.root.bind_all("<Control-r>", lambda e: self._start())
        self.root.bind_all("<Control-R>", lambda e: self._start())
        self.root.bind_all("<Control-Shift-R>", lambda e: self._start_selected())
        self.root.bind_all("<Escape>", lambda e: self._cancel_run())
        # Queue save/load buttons
        # Queue controls moved to advanced dialog
        # Dictionary options
        # Dict options moved to advanced dialog; keep variables
        self.dict_case_ins_var = tk.BooleanVar(value=False)
        self.dict_word_boundary_var = tk.BooleanVar(value=False)
        # NOTE: log filter vars / _log_entries / _sort_reverse are created at the top of
        # _build_ui. Re-creating them here (as before) detached the log filter checkboxes.
        self._refresh_status_bar()

    def _flatten_borders_recursive(self, widget, bg_color: str | None = None) -> None:
        try:
            try:
                if bg_color is not None:
                    widget.configure(borderwidth=0, highlightthickness=0, relief="flat", background=bg_color)
                else:
                    widget.configure(borderwidth=0, highlightthickness=0, relief="flat")
            except Exception:
                pass
            for child in widget.winfo_children():
                self._flatten_borders_recursive(child, bg_color)
        except Exception:
            pass

    def _apply_theme_to_toplevel(self, win) -> None:
        try:
            # Bind ttkbootstrap style to this toplevel if available
            if TBStyle is not None and getattr(self, '_bs', None) is not None:
                try:
                    self._bs.style.master = win  # type: ignore[attr-defined]
                except Exception:
                    pass
            bg = None
            fg = None
            try:
                bg = self._bs.colors.bg if getattr(self, '_bs', None) is not None else self.root.cget('bg')
                fg = self._bs.colors.fg if getattr(self, '_bs', None) is not None else '#ffffff'
            except Exception:
                bg = self.root.cget('bg')
                fg = '#ffffff'
            try:
                win.configure(bg=bg, highlightthickness=0)
            except Exception:
                pass
            try:
                for w in win.winfo_children():
                    try:
                        # Tk widgetlerde fg de uygulanabilir
                        if hasattr(w, 'configure'):
                            try:
                                w.configure(bg=bg, fg=fg)
                            except Exception:
                                w.configure(bg=bg)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass
    def _apply_bg_recursive(self, widget, bg: str) -> None:
        try:
            # Apply to Tk widgets where possible; ttk may ignore 'bg'
            for w in ([widget] + list(widget.winfo_children())):
                try:
                    w.configure(bg=bg)
                except Exception:
                    pass
            # --- Update custom titlebar colors to match theme ---
            try:
                if hasattr(self, 'titlebar'):
                    bgc = self._bs.colors.bg if getattr(self, '_bs', None) is not None else self.root.cget('bg')
                    fgc = self._bs.colors.fg if getattr(self, '_bs', None) is not None else '#ffffff'
                    self.titlebar.configure(bg=bgc)
                    for w in self.titlebar.winfo_children():
                        try:
                            if isinstance(w, (tk.Label, tk.Button, tk.Frame)):
                                # Some widgets (like Frame) may not support fg
                                try:
                                    w.configure(bg=bgc, fg=fgc)
                                except Exception:
                                    w.configure(bg=bgc)
                        except Exception:
                            pass
            except Exception:
                pass
            # Tema değiştiğinde titlebar ve menü bar renklerini güncelle
            try:
                bgc = self._bs.colors.bg if getattr(self, '_bs', None) is not None else self.root.cget('bg')
                fgc = self._contrast_fg(self.root, bgc)
                # Titlebar
                if hasattr(self, 'titlebar'):
                    self.titlebar.configure(bg=bgc)
                    for b in self.titlebar.winfo_children():
                        if isinstance(b, tk.Label):
                            # Başlık etiketi için bg ve fg güncelle
                            b.configure(bg=bgc, fg=fgc)
                        elif isinstance(b, tk.Frame):
                            # Frame için bg güncelle
                            b.configure(bg=bgc)
                            # Frame içindeki butonlar için sadece bg güncelle, fg'yi koru (özel renkler)
                            for c in b.winfo_children():
                                if isinstance(c, tk.Label):
                                    c.configure(bg=bgc)
                # Menü bar
                if hasattr(self, 'menu_bar'):
                    self.menu_bar.configure(bg=bgc)
                    for w in self.menu_bar.winfo_children():
                        if isinstance(w, tk.Label):
                            w.configure(bg=bgc, fg=fgc)
                # Top spacer
                if hasattr(self, '_top_spacer'):
                    try:
                        self._top_spacer.configure(bg=bgc)
                    except Exception:
                        pass
            except Exception:
                pass
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
                self.lbl_hdr_theme.configure(text=self._tr("Theme:"))
            if hasattr(self, 'lbl_hdr_accent'):
                self.lbl_hdr_accent.configure(text=self._tr("Accent color:"))
            if hasattr(self, 'lbl_hdr_ui'):
                self.lbl_hdr_ui.configure(text=self._tr("UI language:"))
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

    def _preview_selected(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        path = self.item_to_path.get(iid)
        if not path or not os.path.isfile(path):
            return
        try:
            ext = os.path.splitext(path)[1].lower()
            sample = ""
            if ext in (".srt", ".vtt", ".txt", ".md", ".csv"):
                with open(path, "r", encoding="utf-8", newline="") as f:
                    sample = "".join([f.readline() for _ in range(20)])
            elif ext == ".docx" and DocxDocument:
                doc = DocxDocument(path)
                parts = [p.text for p in doc.paragraphs[:20]]
                sample = "\n".join(parts)
            elif ext == ".pdf" and pdf_extract_text:
                txt = (pdf_extract_text(path) or "").splitlines()
                sample = "\n".join(txt[:20])
            lang_hint = self._detect_language_hint(sample)
        except Exception as e:
            sample = f"Error reading file: {e}"
            lang_hint = "?"

        win = tk.Toplevel(self.root)
        try:
            if TBStyle is not None and getattr(self, '_bs', None) is not None:
                self._bs.style.master = win  # type: ignore[attr-defined]
            self._apply_theme()
        except Exception:
            pass
        win.title(self._tr("Preview"))
        try:
            self._apply_theme_to_toplevel(win)
        except Exception:
            pass
        win.geometry("700x420")
        win.transient(self.root)
        win.grab_set()
        frm = ttk.Frame(win)
        frm.pack(fill="both", expand=True, padx=10, pady=10)
        hdr = ttk.Frame(frm)
        hdr.pack(fill="x")
        ttk.Label(hdr, text=os.path.basename(path)).pack(side="left")
        ttk.Label(hdr, text=f" | {self._tr('Lang:')} {lang_hint}").pack(side="left", padx=8)
        import tkinter.scrolledtext as scrolledtext
        txt = scrolledtext.ScrolledText(frm, wrap="word")
        txt.pack(fill="both", expand=True, pady=6)
        txt.insert("1.0", sample)
        txt.configure(state="disabled")

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

    def fix_window_focus(self):
        """Pencerenin focus kaybettiğinde kaybolmamasını sağlar."""
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = style & ~WS_EX_TOOLWINDOW
            style = style | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            self.root.withdraw()
            self.root.after(10, self.root.deiconify)
        except Exception:
            pass

    def enable_drag(self):
        def start_move(event):
            self._x = event.x
            self._y = event.y
        def stop_move(_event):
            self._x = None
            self._y = None
        def on_motion(event):
            x = self.root.winfo_pointerx() - self._x
            y = self.root.winfo_pointery() - self._y
            self.root.geometry(f"+{x}+{y}")
        try:
            self.titlebar.bind("<ButtonPress-1>", start_move)
            self.titlebar.bind("<ButtonRelease-1>", stop_move)
            self.titlebar.bind("<B1-Motion>", on_motion)
        except Exception:
            pass

    def _apply_theme_impl(self) -> None:
        try:
            # If ttkbootstrap is available, prefer its theming and avoid overriding with manual styles
            if TBStyle is not None:
                try:
                    theme = (self.bs_theme_var.get() or '').strip()
                    if not theme:
                        theme = self._default_bs_theme()
                    if getattr(self, '_bs', None) is None:
                        self._bs = TBStyle(theme=theme, master=self.root)  # type: ignore
                    else:
                        try:
                            self._bs.theme_use(theme)  # type: ignore
                        except Exception:
                            self._bs = TBStyle(theme=theme, master=self.root)  # type: ignore
                    # Apply component styles for the selected theme (we will still apply our overrides below)
                    self._apply_bootstrap_styles()
                    self.root.update_idletasks()
                except Exception:
                    # fall back to manual ttk styling
                    pass
            if self.dark_mode_var.get():
                # Softer dark palette
                bg = "#0f1319"
                fg = "#e6eaf0"
                acc_map = {
                    "blue": "#5ea1ff",
                    "purple": "#a78bfa",
                    "green": "#34d399",
                    "orange": "#fbbf24",
                    "pink": "#f472b6",
                    "teal": "#2dd4bf",
                }
                acc = acc_map.get(self.accent_var.get(), "#5ea1ff")
                panel = "#121722"
                surface = "#151b26"
                border = "#232a36"
                self.root.configure(bg=bg)
                try:
                    # Global defaults to avoid white tk backgrounds/edges
                    self.root.option_add("*Background", bg)
                    self.root.option_add("*Foreground", fg)
                    self.root.option_add("*foreground", fg)
                    self.root.option_add("*highlightBackground", bg)
                    self.root.option_add("*highlightColor", bg)
                    self.root.option_add("*activeBackground", bg)
                    self.root.option_add("*selectBackground", acc)
                except Exception:
                    pass
                self._style.theme_use("clam")
                for sty in ("TFrame", "TLabel", "TLabelframe", "TLabelframe.Label"):
                    self._style.configure(sty, background=bg, foreground=fg)
                # Also enforce base widget fg/bg to avoid white bars
                self._style.configure("TLabel", background=bg, foreground=fg)
                self._style.configure("TCheckbutton", background=bg, foreground=fg)
                self._style.configure("TButton", background=surface, foreground=fg)
                # Flatten borders completely
                self._style.configure("TFrame", borderwidth=0, relief="flat")
                self._style.configure("TLabelframe", borderwidth=0, relief="flat", bordercolor=bg, lightcolor=bg, darkcolor=bg)
                self._style.configure("TLabelframe.Label", background=bg)
                # Minimize default highlights/borders
                try:
                    self.root.option_add("*highlightThickness", 0)
                    self.root.option_add("*borderWidth", 0)
                    self.root.option_add("*activeBackground", bg)
                    self.root.option_add("*selectForeground", fg)
                except Exception:
                    pass
                # Rounded look using reliefs and padding
                self._style.configure("TLabelframe", relief="flat", borderwidth=0)
                self._style.configure("TLabelframe.Label", padding=(6, 0, 6, 0))
                btn_pad = (8, 4) if self.compact_mode_var.get() else (12, 8)
                self._style.configure("TButton", background=surface, foreground=fg, padding=btn_pad, borderwidth=0)
                self._style.map("TButton", background=[("active", acc)], foreground=[("active", "#ffffff")])
                self._style.configure("Treeview", background=surface, fieldbackground=surface, foreground=fg, bordercolor=border, relief="flat")
                self._style.configure("Treeview.Heading", background=panel, foreground=fg)
                try:
                    self._style.map('Treeview', background=[('selected', '#204060')], foreground=[('selected', '#ffffff')])
                    # Prevent white-on-white headers on hover/press in dark theme
                    self._style.map('Treeview.Heading',
                                     background=[('active', panel), ('pressed', '#1a2740')],
                                     foreground=[('active', fg), ('pressed', '#ffffff')])
                except Exception:
                    pass
                # Notebook and tabs
                try:
                    self._style.configure('TNotebook', background=panel, bordercolor=border)
                    self._style.configure('TNotebook.Tab', background=surface, foreground=fg)
                    self._style.map('TNotebook.Tab', background=[('selected', '#1a2740'), ('active', surface)], foreground=[('selected', '#ffffff'), ('active', fg)])
                except Exception:
                    pass
                # Zebra rows
                try:
                    self.tree.tag_configure('oddrow', background='#18202b')
                    self.tree.tag_configure('evenrow', background='#141b25')
                except Exception:
                    pass
                self._style.configure("TProgressbar", troughcolor=panel, background=acc)
                # Header/app separator (dark)
                try:
                    self._style.configure("AppSeparator.TSeparator", background=border)
                    self._style.configure("AppSeparator.TSeparator", thickness=1)
                except Exception:
                    pass
                # Inputs and menus
                try:
                    self._style.configure("TEntry", fieldbackground=surface, foreground=fg, bordercolor=border, relief="flat")
                    self._style.configure("Toolbar.TEntry", fieldbackground=surface, foreground=fg, bordercolor=border, relief="flat")
                    self._style.map("TEntry", fieldbackground=[('readonly', surface), ('active', surface)], foreground=[('readonly', fg), ('active', fg)])
                    self._style.map("Toolbar.TEntry", fieldbackground=[('readonly', surface), ('active', surface)], foreground=[('readonly', fg), ('active', fg)])
                    self._style.configure("TCombobox", fieldbackground=surface, foreground=fg, background=surface, bordercolor=border, relief="flat")
                    self._style.map("TCombobox", fieldbackground=[('readonly', surface), ('active', surface)], foreground=[('readonly', fg), ('active', fg)])
                    self.root.option_add("*TCombobox*Listbox.background", panel)
                    self.root.option_add("*TCombobox*Listbox.foreground", fg)
                    self.root.option_add("*TCombobox*Listbox.selectBackground", acc)
                    self.root.option_add("*TCombobox*Listbox.selectForeground", '#ffffff')
                    self.root.option_add("*Entry*highlightThickness", 0)
                    self.root.option_add("*Combobox*highlightThickness", 0)
                    self._style.configure("Toolbar.TCheckbutton", background=surface, foreground=fg)
                    # Ensure key comboboxes adopt dark style
                    try:
                        for cb_name in [
                            'cmb_theme','cmb_accent','cmb_ui_quick','cmb_lang',
                            'cmb_engine','cmb_auto_priority','cmb_dict_mode'
                        ]:
                            if hasattr(self, cb_name):
                                getattr(self, cb_name).configure(style='TCombobox')
                    except Exception:
                        pass
                except Exception:
                    pass
                try:
                    self._style.configure("TMenubutton", background=panel, foreground=fg)
                    self._style.configure("TSeparator", background=panel)
                    # Some ttk builds need separate style name
                    self._style.configure("Separator", background=panel)
                except Exception:
                    pass
                # App header & buttons
                self._style.configure("AppHeader.TFrame", background="#0e141c")
                self._style.configure("AppHeader.TLabel", background="#0e141c", foreground=fg)
                # Windows titlebar dark-aware
                try:
                    _enable_win_dark_titlebar(self.root.winfo_id(), True)
                except Exception:
                    pass
                # Header separator color
                try:
                    if hasattr(self, 'sep_hdr'):
                        self.sep_hdr.configure(bg=border)
                except Exception:
                    pass
                self._style.configure("Primary.TButton", background=acc, foreground="#ffffff", padding=btn_pad)
                self._style.map("Primary.TButton", background=[("active", "#4c8af5")])
                self._style.configure("Danger.TButton", background="#f05252", foreground="#ffffff", padding=btn_pad)
                self._style.map("Danger.TButton", background=[("active", "#ef4444")])
                # Ensure all frames have flat borders to avoid white lines
                try:
                    self._flatten_borders_recursive(self.root, bg)
                except Exception:
                    pass
                # Ensure any open Toplevels inherit theme
                try:
                    for w in self.root.winfo_children():
                        if isinstance(w, tk.Toplevel) or w.winfo_class() == 'Toplevel':
                            self._apply_theme_to_toplevel(w)
                except Exception:
                    pass
                try:
                    self.txt_log.configure(bg="#121418", fg=fg, insertbackground=fg)
                except Exception:
                    pass
                try:
                    self.circ.set_color(acc)
                except Exception:
                    pass
                # Canvas and menu backgrounds (dark)
                try:
                    if hasattr(self, 'root_scroll') and hasattr(self.root_scroll, 'canvas'):
                        self.root_scroll.canvas.configure(bg=bg)
                except Exception:
                    pass
                try:
                    if hasattr(self, 'adv_canvas'):
                        self.adv_canvas.configure(bg=bg)
                except Exception:
                    pass
                try:
                    if hasattr(self, 'circ') and hasattr(self.circ, 'canvas'):
                        self.circ.canvas.configure(bg=panel)
                except Exception:
                    pass
                try:
                    if hasattr(self, 'menubar'):
                        self.menubar.configure(bg=panel, fg=fg, activebackground=surface, activeforeground=fg)
                except Exception:
                    pass
                try:
                    if hasattr(self, 'header_menu'):
                        self.header_menu.configure(bg=panel, fg=fg, activebackground=surface, activeforeground=fg)
                except Exception:
                    pass
                try:
                    if hasattr(self, 'tree_menu') and self.tree_menu is not None:
                        self.tree_menu.configure(bg=panel, fg=fg, activebackground=surface, activeforeground=fg)
                except Exception:
                    pass
                # Rounded cards colors
                try:
                    for card in (getattr(self, 'cards', []) or []):
                        card.set_colors(fill="#151b26", shadow="#0a0f16")
                    # Card styles (inner frames & labelframes)
                    self._style.configure("CardInner.TFrame", background="#151b26")
                    try:
                        if hasattr(self, 'toolbar'):
                            self.toolbar.configure(bg="#151b26")
                    except Exception:
                        pass
                    self._style.configure("Card.TLabelframe", background="#151b26", borderwidth=0, relief="flat")
                    self._style.configure("Card.TLabelframe.Label", background="#151b26", foreground=fg)
                except Exception:
                    pass
            else:
                # Softer light palette
                bg = "#f5f7fb"
                fg = "#1e2430"
                acc_map = {
                    "blue": "#3b82f6",
                    "purple": "#8b5cf6",
                    "green": "#22c55e",
                    "orange": "#f59e0b",
                    "pink": "#ec4899",
                    "teal": "#14b8a6",
                }
                acc = acc_map.get(self.accent_var.get(), "#3b82f6")
                panel = "#ffffff"
                surface = "#ffffff"
                border = "#e9edf4"
                self.root.configure(bg=bg)
                try:
                    self.root.option_add("*Background", bg)
                    self.root.option_add("*Foreground", fg)
                    self.root.option_add("*foreground", fg)
                    self.root.option_add("*highlightBackground", bg)
                    self.root.option_add("*highlightColor", bg)
                    self.root.option_add("*activeBackground", bg)
                    self.root.option_add("*selectBackground", acc)
                except Exception:
                    pass
                self._style.theme_use("clam")
                for sty in ("TFrame", "TLabel", "TLabelframe", "TLabelframe.Label"):
                    self._style.configure(sty, background=bg, foreground=fg)
                self._style.configure("TLabel", background=bg, foreground=fg)
                self._style.configure("TCheckbutton", background=bg, foreground=fg)
                self._style.configure("TButton", background=surface, foreground=fg)
                self._style.configure("TFrame", borderwidth=0, relief="flat")
                self._style.configure("TLabelframe", borderwidth=0, relief="flat", bordercolor=bg, lightcolor=bg, darkcolor=bg)
                self._style.configure("TLabelframe.Label", background=bg)
                try:
                    self.root.option_add("*highlightThickness", 0)
                    self.root.option_add("*borderWidth", 0)
                    self.root.option_add("*activeBackground", bg)
                    self.root.option_add("*selectForeground", fg)
                except Exception:
                    pass
                self._style.configure("TLabelframe", relief="flat", borderwidth=0)
                self._style.configure("TLabelframe.Label", padding=(6, 0, 6, 0))
                btn_pad = (8, 4) if self.compact_mode_var.get() else (12, 8)
                self._style.configure("TButton", background=panel, foreground=fg, padding=btn_pad, borderwidth=0)
                self._style.map("TButton", background=[("active", acc)], foreground=[("active", "#ffffff")])
                self._style.configure("Treeview", background=surface, fieldbackground=surface, foreground=fg, bordercolor=border, relief="flat")
                self._style.configure("Treeview.Heading", background="#f0f2f7", foreground=fg)
                try:
                    self._style.map('Treeview', background=[('selected', '#dbeafe')], foreground=[('selected', '#1e293b')])
                    # Prevent white-on-white headers on hover/press in light theme
                    self._style.map('Treeview.Heading',
                                     background=[('active', '#e8edf7'), ('pressed', '#dbeafe')],
                                     foreground=[('active', fg), ('pressed', '#1e293b')])
                except Exception:
                    pass
                # Notebook and tabs
                try:
                    self._style.configure('TNotebook', background=panel, bordercolor=border)
                    self._style.configure('TNotebook.Tab', background=surface, foreground=fg)
                    self._style.map('TNotebook.Tab', background=[('selected', '#e8f1ff')], foreground=[('selected', '#1e2430')])
                except Exception:
                    pass
                # Zebra rows
                try:
                    self.tree.tag_configure('oddrow', background='#f1f4fa')
                    self.tree.tag_configure('evenrow', background='#ffffff')
                except Exception:
                    pass
                self._style.configure("TProgressbar", troughcolor="#eef2f7", background=acc)
                # Header/app separator (light)
                try:
                    self._style.configure("AppSeparator.TSeparator", background=border)
                    self._style.configure("AppSeparator.TSeparator", thickness=1)
                except Exception:
                    pass
                # Inputs and menus
                try:
                    self._style.configure("TEntry", fieldbackground=surface, foreground=fg)
                    self._style.map("TEntry", fieldbackground=[('active', surface)])
                    self._style.configure("TCombobox", fieldbackground=surface, foreground=fg, background=surface, bordercolor=border, relief="flat")
                    self._style.map("TCombobox", fieldbackground=[('active', surface)], foreground=[('active', fg)])
                    self.root.option_add("*TCombobox*Listbox.background", '#ffffff')
                    self.root.option_add("*TCombobox*Listbox.foreground", fg)
                    self.root.option_add("*TCombobox*Listbox.selectBackground", acc)
                    self.root.option_add("*TCombobox*Listbox.selectForeground", '#ffffff')
                    self.root.option_add("*Entry*highlightThickness", 0)
                    self.root.option_add("*Combobox*highlightThickness", 0)
                except Exception:
                    pass
                try:
                    self._style.configure("TMenubutton", background=panel, foreground=fg)
                    self._style.configure("TSeparator", background="#e6ebf5")
                    self._style.configure("Separator", background="#e6ebf5")
                except Exception:
                    pass
                self._style.configure("AppHeader.TFrame", background="#edf2fe")
                self._style.configure("AppHeader.TLabel", background="#edf2fe", foreground=fg)
                try:
                    _enable_win_dark_titlebar(self.root.winfo_id(), False)
                except Exception:
                    pass
                try:
                    if hasattr(self, 'sep_hdr'):
                        self.sep_hdr.configure(bg=border)
                except Exception:
                    pass
                self._style.configure("Primary.TButton", background=acc, foreground="#ffffff", padding=btn_pad)
                self._style.map("Primary.TButton", background=[("active", "#2f6fe9")])
                self._style.configure("Danger.TButton", background="#f05252", foreground="#ffffff", padding=btn_pad)
                self._style.map("Danger.TButton", background=[("active", "#ef4444")])
                try:
                    self._flatten_borders_recursive(self.root, bg)
                except Exception:
                    pass
                # Ensure any open Toplevels inherit theme
                try:
                    for w in self.root.winfo_children():
                        if isinstance(w, tk.Toplevel) or w.winfo_class() == 'Toplevel':
                            self._apply_theme_to_toplevel(w)
                except Exception:
                    pass
                try:
                    self.txt_log.configure(bg="#ffffff", fg=fg, insertbackground=fg)
                except Exception:
                    pass
                try:
                    self.circ.set_color(acc)
                except Exception:
                    pass
                # Canvas and menu backgrounds (light)
                try:
                    if hasattr(self, 'root_scroll') and hasattr(self.root_scroll, 'canvas'):
                        self.root_scroll.canvas.configure(bg=bg)
                except Exception:
                    pass
                try:
                    if hasattr(self, 'adv_canvas'):
                        self.adv_canvas.configure(bg=bg)
                except Exception:
                    pass
                try:
                    if hasattr(self, 'circ') and hasattr(self.circ, 'canvas'):
                        self.circ.canvas.configure(bg=bg)
                except Exception:
                    pass
                try:
                    if hasattr(self, 'menubar'):
                        self.menubar.configure(bg=panel, fg=fg, activebackground="#f0f0f0", activeforeground=fg)
                except Exception:
                    pass
                try:
                    if hasattr(self, 'header_menu'):
                        self.header_menu.configure(bg=panel, fg=fg, activebackground="#f0f0f0", activeforeground=fg)
                except Exception:
                    pass
                try:
                    if hasattr(self, 'tree_menu') and self.tree_menu is not None:
                        self.tree_menu.configure(bg=panel, fg=fg, activebackground="#f0f0f0", activeforeground=fg)
                except Exception:
                    pass
                # Menü varsayılanlarını light için de belirgin yap (beyaz kalmasın)
                try:
                    self.root.option_add("*Menu.background", panel)
                    self.root.option_add("*Menu.foreground", fg)
                    self.root.option_add("*Menu.activeBackground", "#e8f1ff")
                    self.root.option_add("*Menu.activeForeground", fg)
                    self.root.option_add("*Menu.relief", "flat")
                    self.root.option_add("*Menu.borderWidth", 0)
                    self.root.option_add("*Menu.font", "Segoe UI 9")
                    if hasattr(self.root, "menu"):
                        self.root.config(menu=self.root["menu"])
                except Exception:
                    pass
                try:
                    for card in (getattr(self, 'cards', []) or []):
                        card.set_colors(fill="#ffffff", shadow="#e4e9f3")
                    self._style.configure("CardInner.TFrame", background="#ffffff")
                    try:
                        if hasattr(self, 'toolbar'):
                            self.toolbar.configure(bg="#ffffff")
                    except Exception:
                        pass
                    self._style.configure("Card.TLabelframe", background="#ffffff", borderwidth=0, relief="flat")
                    self._style.configure("Card.TLabelframe.Label", background="#ffffff", foreground=fg)
                except Exception:
                    pass
        except Exception:
            pass

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

    def _apply_bootstrap_styles_impl(self) -> None:
        if TBStyle is None:
            return
        try:
            # Base backgrounds to current theme
            try:
                base_bg = self.root.cget("bg")
                self._style.configure("TFrame", background=base_bg)
                self._style.configure("TLabel", background=base_bg)
            except Exception:
                pass
            # Buttons
            if hasattr(self, 'tb_start'):
                self.tb_start.configure(style='primary.TButton')
            if hasattr(self, 'tb_start_sel'):
                self.tb_start_sel.configure(style='primary.TButton')
            if hasattr(self, 'tb_cancel'):
                self.tb_cancel.configure(style='danger.TButton')
            if hasattr(self, 'tb_add'):
                self.tb_add.configure(style='info.TButton')
            if hasattr(self, 'tb_remove_missing'):
                self.tb_remove_missing.configure(style='warning.TButton')
            if hasattr(self, 'tb_remove_selected'):
                self.tb_remove_selected.configure(style='danger.TButton')
            if hasattr(self, 'tb_preview'):
                self.tb_preview.configure(style='secondary.TButton')
            if hasattr(self, 'tb_toggle_adv'):
                self.tb_toggle_adv.configure(style='secondary.TButton')
            if hasattr(self, 'btn_browse'):
                self.btn_browse.configure(style='secondary.TButton')
            if hasattr(self, 'btn_open_out'):
                self.btn_open_out.configure(style='link.TButton')
            if hasattr(self, 'btn_pick_dict'):
                self.btn_pick_dict.configure(style='secondary.TButton')
            if hasattr(self, 'tb_open_selected_out'):
                self.tb_open_selected_out.configure(style='link.TButton')
            if hasattr(self, 'tb_open_selected_outdir'):
                self.tb_open_selected_outdir.configure(style='link.TButton')
            if hasattr(self, 'tb_reveal_src'):
                self.tb_reveal_src.configure(style='link.TButton')
            # Comboboxes
            if hasattr(self, 'cmb_theme'):
                self.cmb_theme.configure(style='info.TCombobox')
            if hasattr(self, 'cmb_accent'):
                self.cmb_accent.configure(style='secondary.TCombobox')
            if hasattr(self, 'cmb_ui_quick'):
                self.cmb_ui_quick.configure(style='info.TCombobox')
            if hasattr(self, 'cmb_lang'):
                self.cmb_lang.configure(style='info.TCombobox')
            if hasattr(self, 'cmb_engine'):
                self.cmb_engine.configure(style='secondary.TCombobox')
            if hasattr(self, 'cmb_auto_priority'):
                self.cmb_auto_priority.configure(style='secondary.TCombobox')
            # Entries
            if hasattr(self, 'ent_outdir_main'):
                self.ent_outdir_main.configure(style='secondary.TEntry')
            if hasattr(self, 'ent_filter'):
                self.ent_filter.configure(style='secondary.TEntry')
            # Checkbuttons (switch-like)
            if hasattr(self, 'chk_compact'):
                self.chk_compact.configure(style='success.TCheckbutton')
            if hasattr(self, 'chk_dark'):
                self.chk_dark.configure(style='info.TCheckbutton')
            if hasattr(self, 'chk_parallel'):
                self.chk_parallel.configure(style='success.TCheckbutton')
            if hasattr(self, 'chk_save_next'):
                self.chk_save_next.configure(style='secondary.TCheckbutton')
            if hasattr(self, 'chk_clean'):
                self.chk_clean.configure(style='warning.TCheckbutton')
            # Frames / LabelFrames
            if hasattr(self, 'toolbar'):
                self.toolbar.configure(style='secondary.TFrame')
            if hasattr(self, 'frm_files'):
                self.frm_files.configure(style='secondary.TLabelframe')
            if hasattr(self, 'frm_perf'):
                self.frm_perf.configure(style='secondary.TLabelframe')
            if hasattr(self, 'frm_adv'):
                self.frm_adv.configure(style='secondary.TLabelframe')
            if hasattr(self, 'frm_out'):
                self.frm_out.configure(style='secondary.TLabelframe')
            # Status bar label
            if hasattr(self, 'status_bar'):
                self.status_bar.configure(style='secondary.TLabel')
            # Progressbar
            if hasattr(self, 'pbar'):
                try:
                    self.pbar.configure(style='primary-striped.TProgressbar')
                except Exception:
                    self.pbar.configure(style='primary.TProgressbar')
            # Rounded cards by context color (if available)
            try:
                for card, ctx in getattr(self, 'card_contexts', []):
                    if self.dark_mode_var.get():
                        if ctx == 'primary':
                            card.set_colors(fill='#122235', shadow='#0b1623')
                        elif ctx == 'info':
                            card.set_colors(fill='#10232d', shadow='#0a1720')
                        elif ctx == 'secondary':
                            card.set_colors(fill='#151b26', shadow='#0a0f16')
                        elif ctx == 'warning':
                            card.set_colors(fill='#3a2f12', shadow='#1f1809')
                        else:
                            card.set_colors(fill='#151b26', shadow='#0a0f16')
                    else:
                        if ctx == 'primary':
                            card.set_colors(fill='#eaf2ff', shadow='#d4def1')
                        elif ctx == 'info':
                            card.set_colors(fill='#e9fbff', shadow='#d5eef3')
                        elif ctx == 'secondary':
                            card.set_colors(fill='#ffffff', shadow='#e4e9f3')
                        elif ctx == 'warning':
                            card.set_colors(fill='#fff7e6', shadow='#f0e7cf')
                        else:
                            card.set_colors(fill='#ffffff', shadow='#e4e9f3')
            except Exception:
                pass
            # Notebook tab styling
            try:
                s = ttk.Style()
                s.configure('TNotebook.Tab', padding=(14, 8))
                if bool(self.dark_mode_var.get()):
                    s.map('TNotebook.Tab', background=[('selected', '#163a5f')], foreground=[('selected', '#ffffff')])
                else:
                    s.map('TNotebook.Tab', background=[('selected', '#e8f1ff')], foreground=[('selected', '#1f2329')])
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

    def _ensure_ui_font_family(self) -> None:
        try:
            code = (self.ui_lang_code or "en").lower()
            avail = set()
            try:
                avail = set(tkfont.families())
            except Exception:
                avail = set()
            def pick(candidates):
                for fam in candidates:
                    if fam in avail:
                        return fam
                return None
            chosen = None
            if code.startswith("zh"):
                chosen = pick(["Microsoft YaHei", "SimSun", "Noto Sans SC", "Arial Unicode MS", "DejaVu Sans", "Segoe UI"])
            elif code.startswith("ja"):
                chosen = pick(["Meiryo", "Yu Gothic", "Noto Sans JP", "Arial Unicode MS", "DejaVu Sans", "Segoe UI"])
            elif code.startswith("ko"):
                chosen = pick(["Malgun Gothic", "Noto Sans KR", "Arial Unicode MS", "DejaVu Sans", "Segoe UI"])
            elif code.startswith("ar"):
                chosen = pick(["Segoe UI", "Tahoma", "Arial", "DejaVu Sans"])
            else:
                chosen = pick(["Segoe UI", "Arial", "DejaVu Sans"]) or "Segoe UI"
            if not chosen:
                return
            for name, fnt in self._base_fonts.items():
                try:
                    fnt.configure(family=chosen)
                except Exception:
                    pass
        except Exception:
            pass

    def _apply_font_scale(self) -> None:
        try:
            scale = float(self.font_scale_var.get() or 1.0)
            for name, fnt in self._base_fonts.items():
                try:
                    base_size = self._base_font_sizes.get(name)
                    if isinstance(base_size, int):
                        new_size = max(8, int(round(base_size * scale)))
                        fnt.configure(size=new_size)
                except Exception:
                    pass
        except Exception:
            pass

    def _build_section_header(self, parent, title: str, ctx: str = "secondary") -> ttk.Label:
        try:
            row = ttk.Frame(parent)
            row.pack(fill="x", padx=10, pady=(8, 6))
            if not hasattr(self, "_section_font"):
                base = tkfont.nametofont("TkDefaultFont").actual()
                size = int(base.get("size", 9))
                size = size + 1 if size > 0 else size - 1  # negative = pixels in Tk
                self._section_font = tkfont.Font(family=base.get("family"), size=size, weight="bold")
            lbl = ttk.Label(row, text=title, font=self._section_font)
            lbl.pack(side="left")
            # Style hint via context color using bootstrap cards mapping
            if TBStyle is not None:
                if ctx == 'primary':
                    lbl.configure(style='primary.TLabel')
                elif ctx == 'info':
                    lbl.configure(style='info.TLabel')
                elif ctx == 'warning':
                    lbl.configure(style='warning.TLabel')
                else:
                    lbl.configure(style='secondary.TLabel')
            return lbl
        except Exception:
            return ttk.Label(parent, text=title)

    # ---------- Output helpers ----------
    def _choose_outdir(self) -> None:
        path = filedialog.askdirectory(title="Select output directory")
        if path:
            self.outdir_var.set(path)

    def _open_output_dialog(self) -> None:
        # Open output settings in a separate resizable window at ~60% of root size
        try:
            win = tk.Toplevel(self.root)
            try:
                if TBStyle is not None and getattr(self, '_bs', None) is not None:
                    self._bs.style.master = win  # type: ignore[attr-defined]
                self._apply_theme()
            except Exception:
                pass
            win.title(self._tr("Output"))
            try:
                self._apply_theme_to_toplevel(win)
            except Exception:
                pass
            rw = max(self.root.winfo_width(), 800)
            rh = max(self.root.winfo_height(), 560)
            win.geometry(f"{int(rw*0.6)}x{int(rh*0.6)}")
            win.resizable(True, True)
            frm = ttk.Frame(win)
            frm.pack(fill="both", expand=True, padx=12, pady=12)
            # Reuse existing output controls by cloning their variables
            out_frame = ttk.LabelFrame(frm, text=self._tr("Output"), style="Card.TLabelframe")
            out_frame.pack(fill="both", expand=True)
            row1 = ttk.Frame(out_frame)
            row1.pack(fill="x", pady=6)
            c1 = ttk.Checkbutton(row1, text=self._tr("Save next to source"), variable=self.save_next_var)
            try:
                if TBStyle is not None:
                    c1.configure(style='success.TCheckbutton')
            except Exception:
                pass
            c1.pack(side="left")
            row2 = ttk.Frame(out_frame)
            row2.pack(fill="x", pady=6)
            ttk.Label(row2, text=self._tr("Output directory:")).pack(side="left")
            ent = ttk.Entry(row2, textvariable=self.outdir_var)
            try:
                if TBStyle is not None:
                    ent.configure(style='secondary.TEntry')
            except Exception:
                pass
            ent.pack(side="left", fill="x", expand=True, padx=8)
            b1 = ttk.Button(row2, text=self._tr("Browse"), command=self._choose_outdir)
            b2 = ttk.Button(row2, text=self._tr("Open output folder"), command=self._open_outdir)
            try:
                if TBStyle is not None:
                    b1.configure(style='secondary.TButton')
                    b2.configure(style='link.TButton')
            except Exception:
                pass
            b1.pack(side="left")
            b2.pack(side="left", padx=6)
            row3 = ttk.Frame(out_frame)
            row3.pack(fill="x", pady=6)
            c2 = ttk.Checkbutton(row3, text=self._tr("Remove [bracketed] notes from SRT after translate"), variable=self.clean_after_var)
            try:
                if TBStyle is not None:
                    c2.configure(style='warning.TCheckbutton')
            except Exception:
                pass
            c2.pack(side="left")
            okb = ttk.Button(frm, text="OK", command=win.destroy)
            try:
                if TBStyle is not None:
                    okb.configure(style='primary.TButton')
            except Exception:
                pass
            okb.pack(side="right", pady=8)
        except Exception:
            pass

    def _open_preferences(self) -> None:
        try:
            win = tk.Toplevel(self.root)
            try:
                if TBStyle is not None and getattr(self, '_bs', None) is not None:
                    self._bs.style.master = win  # type: ignore[attr-defined]
                self._apply_theme()
            except Exception:
                pass
            win.title(self._tr("Preferences..."))
            try:
                self._apply_theme_to_toplevel(win)
            except Exception:
                pass
            rw = max(self.root.winfo_width(), 820)
            rh = max(self.root.winfo_height(), 600)
            win.geometry(f"{int(rw*0.55)}x{int(rh*0.55)}")
            win.resizable(True, True)
            frm = ttk.Frame(win, style="TFrame")
            frm.pack(fill="both", expand=True, padx=16, pady=16)
            # Theme row
            r1 = ttk.Frame(frm); r1.pack(fill="x", pady=6)
            ttk.Label(r1, text=self._tr("Dark theme")).pack(side="left")
            c_dark = ttk.Checkbutton(r1, variable=self.dark_mode_var, command=lambda: (self._apply_theme(), self._refresh_menu_bar(), self._save_settings()))
            try:
                if TBStyle is not None:
                    c_dark.configure(style='info.TCheckbutton')
            except Exception:
                pass
            c_dark.pack(side="left", padx=6)
            ttk.Label(r1, text=self._tr("Compact mode")).pack(side="left", padx=(16,0))
            c_comp = ttk.Checkbutton(r1, variable=self.compact_mode_var, command=lambda: (self._apply_theme(), self._refresh_menu_bar(), self._save_settings()))
            try:
                if TBStyle is not None:
                    c_comp.configure(style='success.TCheckbutton')
            except Exception:
                pass
            c_comp.pack(side="left", padx=6)
            # Accent
            r2 = ttk.Frame(frm); r2.pack(fill="x", pady=6)
            ttk.Label(r2, text=self._tr("Accent color:")).pack(side="left")
            cb_acc = ttk.Combobox(r2, state="readonly", values=["blue","purple","green","orange","pink","teal"], textvariable=self.accent_var, width=12)
            try:
                if TBStyle is not None:
                    cb_acc.configure(style='secondary.TCombobox')
            except Exception:
                pass
            cb_acc.pack(side="left", padx=6)
            # Theme profile
            r2b = ttk.Frame(frm); r2b.pack(fill="x", pady=6)
            ttk.Label(r2b, text=self._tr("Theme profile:")).pack(side="left")
            profiles = ["", "Soft Blue (Light)", "Soft Purple (Dark)", "Midnight Teal (Dark)"]
            cb_prof = ttk.Combobox(r2b, state="readonly", values=profiles, textvariable=self.theme_profile_var, width=22)
            try:
                if TBStyle is not None:
                    cb_prof.configure(style='secondary.TCombobox')
            except Exception:
                pass
            cb_prof.pack(side="left", padx=6)
            # Bootstrap theme
            if TBStyle is not None:
                r3 = ttk.Frame(frm); r3.pack(fill="x", pady=6)
                ttk.Label(r3, text=self._tr("Bootstrap theme")).pack(side="left")
                themes = ["flatly","darkly","cosmo","cyborg","journal","litera","lumen","minty","pulse","sandstone","simplex","solar","superhero","united","yeti"]
                cb_bs = ttk.Combobox(r3, state="readonly", values=themes, textvariable=self.bs_theme_var, width=18)
                try:
                    cb_bs.configure(style='info.TCombobox')
                except Exception:
                    pass
                cb_bs.pack(side="left", padx=6)
            # Font scale
            r4 = ttk.Frame(frm); r4.pack(fill="x", pady=6)
            ttk.Label(r4, text=self._tr("Font size")).pack(side="left")
            fs = ttk.Combobox(r4, state="readonly", values=["90%","100%","110%","120%","130%"], width=10)
            try:
                if TBStyle is not None:
                    fs.configure(style='secondary.TCombobox')
            except Exception:
                pass
            fs.pack(side="left", padx=6)
            def _apply_prefs():
                try:
                    v = fs.get().replace('%','')
                    if v:
                        self.font_scale_var.set(float(v)/100.0)
                except Exception:
                    pass
                # Apply theme profile
                try:
                    prof = (self.theme_profile_var.get() or "").strip()
                    if prof == "Soft Blue (Light)":
                        self.dark_mode_var.set(False)
                        self.accent_var.set("blue")
                    elif prof == "Soft Purple (Dark)":
                        self.dark_mode_var.set(True)
                        self.accent_var.set("purple")
                    elif prof == "Midnight Teal (Dark)":
                        self.dark_mode_var.set(True)
                        self.accent_var.set("teal")
                except Exception:
                    pass
                self._apply_font_scale()
                self._apply_theme()
                try:
                    self._refresh_menu_bar()
                except Exception:
                    pass
                self._apply_bootstrap_styles()
                self._save_settings()
            btn_apply = ttk.Button(frm, text=self._tr("Apply"), command=_apply_prefs)
            btn_close = ttk.Button(frm, text=self._tr("Close"), command=win.destroy)
            try:
                if TBStyle is not None:
                    btn_apply.configure(style='primary.TButton')
                    btn_close.configure(style='secondary.TButton')
            except Exception:
                pass
            btn_apply.pack(side="right")
            btn_close.pack(side="right", padx=(0,8))
        except Exception:
            pass

    def _toggle_advanced(self) -> None:
        # Forward to advanced dialog
        self._open_advanced_dialog()

    def _open_advanced_dialog(self) -> None:
        try:
            win = tk.Toplevel(self.root)
            try:
                if TBStyle is not None and getattr(self, '_bs', None) is not None:
                    self._bs.style.master = win  # type: ignore[attr-defined]
                self._apply_theme()
            except Exception:
                pass
            win.title(self._tr("Advanced Settings"))
            try:
                self._apply_theme_to_toplevel(win)
            except Exception:
                pass
            # Open maximized when possible; otherwise cover the screen
            try:
                win.state("zoomed")
            except Exception:
                sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
                win.geometry(f"{sw}x{sh}+0+0")
            win.minsize(960, 640)
            win.resizable(True, True)
            container = ttk.Frame(win)
            container.pack(fill="both", expand=True)
            cvs = tk.Canvas(container, highlightthickness=0, bd=0)
            vbar = ttk.Scrollbar(container, orient="vertical", command=cvs.yview, style="Modern.Vertical.TScrollbar")
            cvs.configure(yscrollcommand=vbar.set)
            cvs.pack(side="left", fill="both", expand=True)
            vbar.pack(side="right", fill="y")
            inner = ttk.Frame(cvs)
            inner_id = cvs.create_window((0, 0), window=inner, anchor="nw")
            # Force dark backgrounds for advanced dialog if dark mode
            try:
                bg = self._bs.colors.bg if getattr(self, '_bs', None) is not None else (self.root.cget('bg'))
                win.configure(bg=bg)
                try:
                    container.configure(style="TFrame")
                except Exception:
                    pass
                try:
                    cvs.configure(bg=bg)
                except Exception:
                    pass
                try:
                    inner.configure(style="TFrame")
                except Exception:
                    try:
                        inner.configure(bg=bg)
                    except Exception:
                        pass
            except Exception:
                pass
            def _on_inner_config(event=None):
                try:
                    cvs.configure(scrollregion=cvs.bbox("all"))
                    # Make content width follow canvas width for responsive layout
                    cw = cvs.winfo_width()
                    if cw > 0:
                        cvs.itemconfigure(inner_id, width=cw)
                except Exception:
                    pass
            def _on_canvas_config(event=None):
                try:
                    cw = cvs.winfo_width()
                    if cw > 0:
                        cvs.itemconfigure(inner_id, width=cw)
                except Exception:
                    pass
            inner.bind("<Configure>", _on_inner_config)
            cvs.bind("<Configure>", _on_canvas_config)

            # Tabs for advanced settings
            nb = ttk.Notebook(inner)
            nb.pack(fill="both", expand=True, padx=12, pady=8)
            tab_general = ttk.Frame(nb)
            tab_engine = ttk.Frame(nb)
            tab_dict = ttk.Frame(nb)
            tab_perf = ttk.Frame(nb)
            nb.add(tab_general, text="🧰 " + self._tr("General"))
            nb.add(tab_engine, text="⚙️ " + self._tr("Engine"))
            nb.add(tab_dict, text="📖 " + self._tr("Dictionary"))
            nb.add(tab_perf, text="🚀 " + self._tr("Performance"))

            # General (batch/mm)
            sec1 = ttk.LabelFrame(tab_general, text=self._tr("General"), style="Card.TLabelframe")
            sec1.pack(fill="x", padx=6, pady=6)
            r1 = ttk.Frame(sec1); r1.pack(fill="x", pady=4)
            Spinbox = getattr(ttk, "Spinbox", tk.Spinbox)
            ttk.Label(r1, text=self._tr("Batch size (Google batch):")).pack(side="left")
            ttk.Label(r1, text=" ?", foreground="#888").pack(side="left")
            r1_tip = self._tr("Batch: how many unique lines are sent to Google at once.")
            r1_tip_label = ttk.Label(sec1)
            def _enter_r1(e): r1_tip_label.configure(text=r1_tip)
            def _leave_r1(e): r1_tip_label.configure(text="")
            r1.bind("<Enter>", _enter_r1); r1.bind("<Leave>", _leave_r1)
            sp1 = Spinbox(r1, from_=10, to=500, textvariable=self.batch_size_var, width=8)
            sp1.pack(side="left", padx=8)
            r2 = ttk.Frame(sec1); r2.pack(fill="x", pady=4)
            ttk.Label(r2, text=self._tr("Fallback concurrent jobs (MyMemory):")).pack(side="left")
            ttk.Label(r2, text=" ?", foreground="#888").pack(side="left")
            r2_tip = self._tr("MyMemory concurrent jobs: number of lines translated in parallel (fallback).")
            r2_tip_label = ttk.Label(sec1)
            def _enter_r2(e): r2_tip_label.configure(text=r2_tip)
            def _leave_r2(e): r2_tip_label.configure(text="")
            r2.bind("<Enter>", _enter_r2); r2.bind("<Leave>", _leave_r2)
            r1_tip_label.pack(fill="x")
            r2_tip_label.pack(fill="x")
            sp2 = Spinbox(r2, from_=1, to=16, textvariable=self.mm_workers_var, width=8)
            sp2.pack(side="left", padx=8)

            # Engine
            sec2 = ttk.LabelFrame(tab_engine, text=self._tr("Engine:"), style="Card.TLabelframe")
            sec2.pack(fill="x", padx=6, pady=6)
            r3 = ttk.Frame(sec2); r3.pack(fill="x", pady=4)
            ttk.Label(r3, text=self._tr("Engine:")).pack(side="left")
            ttk.Label(r3, text=" ?", foreground="#888").pack(side="left")
            cb_engine = ttk.Combobox(r3, values=["auto", "google", "mymemory", "deepl", "deepl_web", "libre"], textvariable=self.engine_var, state="readonly", width=12)
            try:
                if TBStyle is not None:
                    cb_engine.configure(style='secondary.TCombobox')
            except Exception:
                pass
            cb_engine.pack(side="left", padx=8)
            ttk.Label(r3, text=self._tr("Auto priority:")).pack(side="left", padx=(12, 4))
            ttk.Label(r3, text=" ?", foreground="#888").pack(side="left")
            cb_ap = ttk.Combobox(r3, values=["google_first", "mymemory_first"], textvariable=self.auto_priority_var, state="readonly", width=16)
            try:
                if TBStyle is not None:
                    cb_ap.configure(style='secondary.TCombobox')
            except Exception:
                pass
            cb_ap.pack(side="left")
            # tips
            r3_tip1 = self._tr("Engine selection: auto/google/mymemory.")
            r3_tip2 = self._tr("Auto priority decides which engine is tried first in auto mode.")
            r3_tip = ttk.Label(sec2)
            def _enter_r3(e): r3_tip.configure(text=r3_tip1 + "  " + r3_tip2)
            def _leave_r3(e): r3_tip.configure(text="")
            r3.bind("<Enter>", _enter_r3); r3.bind("<Leave>", _leave_r3)
            r3_tip.pack(fill="x")

            # Dictionary
            sec3 = ttk.LabelFrame(tab_dict, text=self._tr("Custom dictionary:"), style="Card.TLabelframe")
            sec3.pack(fill="x", padx=6, pady=6)
            rd1 = ttk.Frame(sec3); rd1.pack(fill="x", pady=4)
            cb_dm = ttk.Combobox(rd1, values=["off", "pre", "post", "both"], textvariable=self.dict_mode_var, state="readonly", width=8)
            try:
                if TBStyle is not None:
                    cb_dm.configure(style='secondary.TCombobox')
            except Exception:
                pass
            cb_dm.pack(side="left", padx=6)
            ttk.Label(rd1, text=" ?", foreground="#888").pack(side="left")
            ent_dp = ttk.Entry(rd1, textvariable=self.dict_path_var)
            try:
                if TBStyle is not None:
                    ent_dp.configure(style='secondary.TEntry')
            except Exception:
                pass
            ent_dp.pack(side="left", fill="x", expand=True, padx=6)
            btn_dp = ttk.Button(rd1, text=self._tr("Browse"), command=self._choose_dict)
            try:
                if TBStyle is not None:
                    btn_dp.configure(style='secondary.TButton')
            except Exception:
                pass
            btn_dp.pack(side="left")
            rd1_tip = self._tr("Dictionary mode: off/pre/post/both.")
            rd1_tip_label = ttk.Label(sec3)
            def _enter_rd1(e): rd1_tip_label.configure(text=rd1_tip)
            def _leave_rd1(e): rd1_tip_label.configure(text="")
            rd1.bind("<Enter>", _enter_rd1); rd1.bind("<Leave>", _leave_rd1)
            rd2 = ttk.Frame(sec3); rd2.pack(fill="x", pady=4)
            ttk.Checkbutton(rd2, text=self._tr("Case-insensitive terms"), variable=self.dict_case_ins_var).pack(side="left")
            ttk.Label(rd2, text=" ?", foreground="#888").pack(side="left")
            ttk.Checkbutton(rd2, text=self._tr("Word-boundary only"), variable=self.dict_word_boundary_var).pack(side="left", padx=10)
            ttk.Label(rd2, text=" ?", foreground="#888").pack(side="left")
            rd2_tip = ttk.Label(sec3)
            def _enter_rd2(e): rd2_tip.configure(text=self._tr("Case-insensitive matching."))
            def _leave_rd2(e): rd2_tip.configure(text="")
            rd2.bind("<Enter>", _enter_rd2); rd2.bind("<Leave>", _leave_rd2)
            rd2_tip.pack(fill="x")

            # Appearance & performance
            sec4 = ttk.LabelFrame(tab_perf, text=self._tr("Appearance & Performance"), style="Card.TLabelframe")
            sec4.pack(fill="x", padx=6, pady=6)
            ttk.Checkbutton(sec4, text=self._tr("Dark theme"), variable=self.dark_mode_var, command=self._apply_theme).pack(anchor="w", pady=2)
            rp = ttk.Frame(sec4); rp.pack(fill="x", pady=4)
            ttk.Checkbutton(rp, text=self._tr("Translate files in parallel"), variable=self.parallel_files_var).pack(side="left")
            ttk.Label(rp, text=" ?", foreground="#888").pack(side="left")
            ttk.Label(rp, text=self._tr("Workers:")).pack(side="left", padx=(10, 0))
            rp_tip = ttk.Label(sec4)
            def _enter_rp(e): rp_tip.configure(text=self._tr("Translate multiple files concurrently.") + "  " + self._tr("Number of concurrent files."))
            def _leave_rp(e): rp_tip.configure(text="")
            rp.bind("<Enter>", _enter_rp); rp.bind("<Leave>", _leave_rp)
            rp_tip.pack(fill="x")
            Spinbox(rp, from_=1, to=4, textvariable=self.file_workers_var, width=5).pack(side="left", padx=8)

            ok_adv = ttk.Button(win, text="OK", command=win.destroy)
            try:
                if TBStyle is not None:
                    ok_adv.configure(style='primary.TButton')
            except Exception:
                pass
            ok_adv.pack(side="right", padx=12, pady=10)
        except Exception:
            pass

    def _choose_dict(self) -> None:
        path = filedialog.askopenfilename(title="Select dictionary (JSON or CSV)", filetypes=(("Dictionary", "*.json *.csv"), ("All files", "*.*")))
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
            self.root.after(50, self._drain_log_queue)
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
            path = filedialog.asksaveasfilename(title="Export logs", defaultextension=".txt", filetypes=(("Text", "*.txt"), ("All files", "*.*")))
            if not path:
                return
            with open(path, "w", encoding="utf-8") as wf:
                for _lvl, line in self._log_entries:
                    wf.write(line + "\n")
            messagebox.showinfo("Logs", "Logs exported")
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

    def _show_about(self) -> None:
        try:
            win = tk.Toplevel(self.root)
            try:
                if TBStyle is not None and getattr(self, '_bs', None) is not None:
                    self._bs.style.master = win  # type: ignore[attr-defined]
                self._apply_theme()
            except Exception:
                pass
            win.title(self._tr("About"))
            try:
                self._apply_theme_to_toplevel(win)
            except Exception:
                pass
            win.geometry("520x360")
            win.resizable(False, False)
            frm = ttk.Frame(win)
            frm.pack(fill="both", expand=True, padx=16, pady=16)
            ttk.Label(frm, text=f"🌐 {self._tr('Subtitle Translator')}", font=("Segoe UI", 14, "bold")).pack(anchor="w")
            ttk.Label(frm, text=f"{self._tr('Version:')} 1.0.0").pack(anchor="w", pady=(4, 0))
            ttk.Label(frm, text=self._tr("Desktop-like Tkinter UI with i18n, themes, and batch translation.")).pack(anchor="w", pady=(2, 8))
            info = (
                f"{self._tr('Features:')}\n"
                f"{self._tr('- Multi-format: SRT, VTT, TXT, MD, CSV, DOCX, PDF')}\n"
                f"{self._tr('- Engines: Auto / Google / MyMemory with fallback')}\n"
                f"{self._tr('- Dictionary pre/post apply, case/word-boundary options')}\n"
                f"{self._tr('- Queue, preview, drag&drop, logging, error policy')}\n"
                f"{self._tr('- Persistent settings, themes, accent & compact mode')}"
            )
            import tkinter.scrolledtext as scrolledtext
            txt = scrolledtext.ScrolledText(frm, height=10, wrap="word")
            txt.pack(fill="both", expand=True)
            txt.insert("1.0", info)
            txt.configure(state="disabled")
            # links
            link_row = ttk.Frame(frm)
            link_row.pack(fill="x", pady=(8, 0))
            ttk.Label(link_row, text=self._tr("Project site:")).pack(side="left")
            lbl = ttk.Label(link_row, text="nicegui.io", foreground="#2563eb", cursor="hand2")
            lbl.pack(side="left", padx=(6, 0))
            def _open_link(_e=None):
                try:
                    import webbrowser
                    webbrowser.open("https://nicegui.io/")
                except Exception:
                    pass
            lbl.bind("<Button-1>", _open_link)
            ttk.Button(frm, text=self._tr("OK"), command=win.destroy, style="Primary.TButton").pack(anchor="e", pady=(12, 0))
        except Exception:
            pass

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

    # ---- Theme wrappers: every theme change ends with consistent card/titlebar colours ----
    def _apply_theme(self) -> None:
        try:
            self._apply_theme_impl()
        finally:
            self._apply_card_colors()

    def _apply_bootstrap_styles(self) -> None:
        try:
            self._apply_bootstrap_styles_impl()
        finally:
            self._apply_card_colors()

    @staticmethod
    def _mix(widget, a: str, b: str, t: float) -> str:
        try:
            ra, ga, ba = (v / 257 for v in widget.winfo_rgb(a))
            rb, gb, bb = (v / 257 for v in widget.winfo_rgb(b))
            return "#%02x%02x%02x" % (int(ra + (rb - ra) * t), int(ga + (gb - ga) * t), int(ba + (bb - ba) * t))
        except Exception:
            return a

    def _apply_card_colors(self) -> None:
        """Flat panels: card fill = window background, thin outline. Inner widgets keep their
        default styles, so nothing renders on a mismatched background (old 'patchy' look and
        the black drop-shadows came from cards that never received theme colours)."""
        try:
            style = ttk.Style()
            bg = style.lookup("TFrame", "background") or self.root.cget("bg")
            fg = style.lookup("TLabel", "foreground") or self._contrast_fg(self.root, bg)
            outline = self._mix(self.root, bg, fg, 0.16)
            for card, _ctx in getattr(self, "card_contexts", []):
                card.set_colors(fill=bg, shadow=outline)
            style.configure("CardInner.TFrame", background=bg)
            # Same background for every control that sits on a panel (radios used to show grey boxes)
            for st in ("TRadiobutton", "TCheckbutton", "AppHeader.TFrame", "AppHeader.TLabel"):
                style.configure(st, background=bg)
            for st in ("TRadiobutton", "TCheckbutton"):
                # explicit foreground too: in dark mode radios kept dark text on the dark panel
                style.configure(st, foreground=fg)
                style.map(st, background=[("active", bg), ("!active", bg)], foreground=[("disabled", outline), ("!disabled", fg)])
            try:
                self.root_scroll.canvas.configure(bg=bg)
            except Exception:
                pass
            title_fg = self._contrast_fg(self.root, bg)
            if hasattr(self, "titlebar"):
                self.titlebar.configure(bg=bg)
                for w in self.titlebar.winfo_children():
                    if isinstance(w, tk.Label):
                        w.configure(bg=bg, fg=title_fg)
                    elif isinstance(w, tk.Frame):
                        w.configure(bg=bg)
                        for c in w.winfo_children():
                            if isinstance(c, tk.Label):
                                c.configure(bg=bg)
            if hasattr(self, "_top_spacer"):
                self._top_spacer.configure(bg=bg)
            if hasattr(self, "circ"):
                self.circ.set_color(style.lookup("TProgressbar", "background") or "#3b82f6")
        except Exception:
            pass

    @staticmethod
    def _contrast_fg(widget, bg: str) -> str:
        """Readable text colour for a background (fixes white-on-white title in light theme)."""
        try:
            r, g, b = (v / 65535 for v in widget.winfo_rgb(bg))
            return "#1f2937" if (0.2126 * r + 0.7152 * g + 0.0722 * b) > 0.55 else "#f8fafc"
        except Exception:
            return "#1f2937"


def launch_gui() -> None:
    app = TranslatorGUI()
    app.run()


if __name__ == "__main__":
    try:
        _maybe_open_python_download_once()
        _offer_install_missing_requirements()
        _cli_main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)



