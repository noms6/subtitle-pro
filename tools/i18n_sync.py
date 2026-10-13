"""Keep ui_translations.json in sync with the UI strings used in translate_srt.py.

    python tools/i18n_sync.py            # report only
    python tools/i18n_sync.py --fill     # machine-translate missing/untranslated entries, then
                                         # apply tools/i18n_overrides.json (hand-checked terms)
    python tools/i18n_sync.py --write    # also prune unused / junk keys and save

Keys = every literal _tr("...") call + the `keys` dict in _retranslate_ui + UI_EXTRA_KEYS.
Leading icons are stripped ("📂 Add..." -> "Add..."), matching runtime lookup.
"""
import argparse
import ast
import json
import os
import re
import sys
import time
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "translate_srt.py")
PACKS = os.path.join(ROOT, "ui_translations.json")
OVERRIDES = os.path.join(ROOT, "tools", "i18n_overrides.json")

AFFIX = re.compile(r"^([^\w(\[]*)(.*?)(\s*)$", re.S)
# Never translated (brand / format names)
KEEP = {"Google", "MyMemory", "DeepL", "DeepL (Web)", "Libre", "PDF", "TXT", "Subtitle PRO – Multi Translator"}
SCRIPTS = {
    "ja": {"CJK", "HIRAGANA", "KATAKANA"}, "zh-CN": {"CJK"}, "zh-TW": {"CJK"}, "ko": {"HANGUL", "CJK"},
    "ar": {"ARABIC"}, "fa": {"ARABIC"}, "ru": {"CYRILLIC"}, "uk": {"CYRILLIC"}, "bg": {"CYRILLIC"},
    "sr": {"CYRILLIC"}, "el": {"GREEK"}, "hi": {"DEVANAGARI"}, "th": {"THAI"},
}
GOOGLE_CODE = {"no": "no", "zh-CN": "zh-CN", "zh-TW": "zh-TW"}


def core(text):
    m = AFFIX.match(text)
    return (m.group(2) if m else text).strip()


def extract_keys(src):
    keys = set()
    for m in re.finditer(r'_tr\(\s*(["\'])((?:\\.|(?!\1).)*)\1\s*\)', src):
        keys.add(ast.literal_eval(m.group(1) + m.group(2) + m.group(1)))
    block = re.search(r"def _retranslate_ui\(.*?keys = \{(.*?)\n        \}", src, re.S)
    if block:
        for m in re.finditer(r'"\w+":\s*"((?:\\.|[^"])*)"', block.group(1)):
            keys.add(ast.literal_eval('"' + m.group(1) + '"'))
    extra = re.search(r"UI_EXTRA_KEYS: List\[str\] = \[(.*?)\]\n", src, re.S)
    if extra:
        keys.update(ast.literal_eval("[" + extra.group(1) + "]"))
    out = set()
    for k in keys:
        c = core(k)
        if c and re.search(r"[A-Za-z]", c):
            out.add(c)
    return sorted(out)


def scripts_of(s):
    found = set()
    for ch in s:
        if ch.isalpha():
            name = unicodedata.name(ch, "")
            for sc in ("HANGUL", "CJK", "HIRAGANA", "KATAKANA", "ARABIC", "CYRILLIC", "GREEK", "DEVANAGARI", "THAI", "LATIN"):
                if name.startswith(sc):
                    found.add(sc)
                    break
    return found


def wrong_script(code, value):
    exp = SCRIPTS.get(code)
    if not exp:
        return bool(scripts_of(value) - {"LATIN"})
    return bool(scripts_of(value) - exp - {"LATIN"})


def needs_work(code, key, value):
    if key in KEEP:
        return False
    if not value or not str(value).strip():
        return True
    if value == key and len(key) > 2:
        return True
    return wrong_script(code, value)


def fix_punct(code, key, value):
    # MT often lower-cases short labels ("kelimeler"); UI labels start with a capital
    if key[:1].isupper() and value[:1].islower() and code not in ("de",):
        value = value[:1].upper() + value[1:]
    cjk = code in ("ja", "zh-CN", "zh-TW")
    colon = "：" if cjk else ":"
    if key.endswith(":") and not value.rstrip().endswith((":", "：")):
        value = value.rstrip(" .。") + colon
    if key.endswith("...") and value.endswith(" ..."):
        value = value[:-4] + "..."
    if key.endswith("...") and not value.endswith(("...", "…")):
        value = value.rstrip(" .。") + "..."
    if key.startswith("(") and key.endswith(")") and not value.startswith(("(", "（")):
        value = "(" + value.strip("()（） ") + ")"
    return value


def google_batch(texts, target):
    import requests
    out = []
    for i in range(0, len(texts), 40):
        chunk = texts[i:i + 40]
        r = requests.get("https://translate.googleapis.com/translate_a/single",
                         params={"client": "gtx", "sl": "en", "tl": GOOGLE_CODE.get(target, target), "dt": "t",
                                 "q": "\n".join(chunk)}, timeout=30)
        r.raise_for_status()
        lines = "".join(seg[0] for seg in r.json()[0]).split("\n")
        if len(lines) != len(chunk):  # fall back to one request per string
            lines = []
            for t in chunk:
                rr = requests.get("https://translate.googleapis.com/translate_a/single",
                                  params={"client": "gtx", "sl": "en", "tl": GOOGLE_CODE.get(target, target), "dt": "t", "q": t},
                                  timeout=30)
                rr.raise_for_status()
                lines.append("".join(seg[0] for seg in rr.json()[0]))
                time.sleep(0.2)
        out.extend(l.strip() for l in lines)
        time.sleep(0.3)
    return out


def build_lang_names(ui_codes):
    """lang_names.json: {ui_code: {target_code: localized language name}} for the target picker."""
    sys.path.insert(0, ROOT)
    import translate_srt as T
    T._get_supported_langs("en")
    en_names = dict(sorted(T._LANG_NAMES_EN.items()))
    codes, names = list(en_names), list(en_names.values())
    out = {"en": en_names}
    for ui in ui_codes:
        if ui == "en":
            continue
        try:
            res = google_batch(names, ui)
        except Exception as e:
            print(f"  {ui}: failed: {e}")
            continue
        loc = {}
        for code, en, v in zip(codes, names, res):
            v = (v or en).strip()
            if v[:1].islower() and ui not in ("de",):
                v = v[:1].upper() + v[1:]
            loc[code] = v
        out[ui] = loc
        print(f"{ui:6} {len(loc)} names")
    path = os.path.join(ROOT, "lang_names.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print("written", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fill", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--lang-names", action="store_true")
    ap.add_argument("--langs", default="")
    a = ap.parse_args()
    if a.lang_names:
        packs = json.load(open(PACKS, encoding="utf-8"))
        return build_lang_names([c for c in (a.langs.split(",") if a.langs else sorted(packs)) if c])

    keys = extract_keys(open(SRC, encoding="utf-8").read())
    packs = json.load(open(PACKS, encoding="utf-8"))
    overrides = json.load(open(OVERRIDES, encoding="utf-8")) if os.path.exists(OVERRIDES) else {}
    langs = [c for c in (a.langs.split(",") if a.langs else sorted(packs)) if c]
    print(f"{len(keys)} UI keys in source")

    new_packs = {}
    for code in sorted(packs):
        old = packs[code]
        # carry over existing translations, looked up by core key (old file also had emoji-prefixed keys)
        by_core = {}
        for k, v in old.items():
            c = core(k)
            if c and isinstance(v, str):
                by_core.setdefault(c, core(v) if core(k) != k else v)
        pack = {}
        for k in keys:
            v = by_core.get(k, "")
            pack[k] = k if (code == "en" or k in KEEP) else v
        todo = [k for k in keys if code != "en" and needs_work(code, k, pack[k])]
        if a.fill and todo and code in langs:
            try:
                res = google_batch(todo, code)
                for k, v in zip(todo, res):
                    if v:
                        pack[k] = v
            except Exception as e:
                print(f"  {code}: machine translation failed: {e}")
        for k, v in (overrides.get(code) or {}).items():
            if k in pack:
                pack[k] = v
        for k in keys:
            if pack[k] and code != "en":
                pack[k] = fix_punct(code, k, pack[k])
        left = [k for k in keys if code != "en" and needs_work(code, k, pack[k])]
        unused = sorted(set(old) - set(keys))
        print(f"{code:6} todo={len(todo):3d} remaining={len(left):3d} pruned={len(unused):3d}")
        new_packs[code] = {k: pack[k] if pack[k] else k for k in keys}

    if a.write or a.fill:
        with open(PACKS, "w", encoding="utf-8", newline="\n") as f:
            json.dump(new_packs, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        print("written", PACKS)


if __name__ == "__main__":
    sys.exit(main())
