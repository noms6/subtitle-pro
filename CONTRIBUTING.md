# Katkı Rehberi

## Geliştirme ortamı
```bash
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check tests tools
```

## Bir hatayı düzeltirken
1. [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) içinden hata numarasını bulun (ör. `H1`).
2. `tests/` altında o numarayı arayın: `xfail(strict=True, reason="H1: ...")`.
3. Düzeltmeden sonra test **XPASS** verir ve paket kırmızıya döner → `xfail` işaretini kaldırın.
   Aynı hatanın "karakterizasyon" testi (bugünkü yanlış davranışı doğrulayan) varsa onu silin veya tersine çevirin.
4. `KNOWN_ISSUES.md`'de satırı ✅ ile işaretleyin, commit mesajında numarayı belirtin: `fix(H1): ...`.

## Arayüz metni eklerken / çeviri düzeltirken
1. Metni kodda `self._tr("English text")` ile kullanın (değişkenle geçiyorsa `UI_EXTRA_KEYS` listesine ekleyin). Kısa ve belirsiz kelimelerden kaçının: "Start selected" değil "Translate selected files".
2. `python tools/i18n_sync.py --fill` → yeni anahtar 36 dile çevrilir, `tools/i18n_overrides.json` en son uygulanır.
3. `python tools/ui_audit.py --langs tr,de,ja` ile çevrilmemiş/kırpılan metin kalmadığını kontrol edin; `pytest tests/test_ui_i18n.py`.
4. Ana dilinizde yanlış bir terim görürseniz düzeltmeyi `tools/i18n_overrides.json`'a ekleyin.

## Kurallar
- Testler ağa çıkmamalı; `tests/conftest.py` içindeki `engines` fixture'ını kullanın. Canlı testler `@pytest.mark.network`.
- Worker thread'den Tk nesnelerine dokunmayın (H4).
- Yeni `except Exception: pass` eklemeyin; en azından log'a yazın.
- Telifli altyazı dosyalarını depoya eklemeyin; örnek gerekiyorsa `tests/fixtures/` altına kendi metninizi yazın.
