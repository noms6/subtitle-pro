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

## Kurallar
- Testler ağa çıkmamalı; `tests/conftest.py` içindeki `engines` fixture'ını kullanın. Canlı testler `@pytest.mark.network`.
- Worker thread'den Tk nesnelerine dokunmayın (H4).
- Yeni `except Exception: pass` eklemeyin; en azından log'a yazın.
- Telifli altyazı dosyalarını depoya eklemeyin; örnek gerekiyorsa `tests/fixtures/` altına kendi metninizi yazın.
