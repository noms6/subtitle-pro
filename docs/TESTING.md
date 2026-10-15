# Test Rehberi ve Rapor

## Çalıştırma

```bash
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest            # çevrimdışı paket (~10 sn)
.venv\Scripts\python -m pytest -m network # canlı servis testleri (isteğe bağlı)
.venv\Scripts\python tools\benchmark.py   # performans ölçümü (çevrimdışı)
```

Linux'ta GUI testleri için sanal ekran: `xvfb-run -a python -m pytest`.

## Yaklaşım

| İlke | Nasıl |
|---|---|
| **Ağ yok** | `tests/conftest.py` Google ve MyMemory'yi sahte motorlarla değiştirir. Sahte motorlar her çağrıyı kaydeder; 429, gecikme ve kalıcı hata canlandırılabilir. Geri çekilme `sleep`'leri devre dışıdır. |
| **Hatalar test olarak yaşar** | Bilinen her hata `@pytest.mark.xfail(strict=True, reason="H<no>: ...")`. Düzeltilince test XPASS verir ve `strict` sayesinde başarısız sayılır → işareti kaldırmanız gerekir. |
| **Karakterizasyon** | Hatanın bugün gerçekten oluştuğunu kanıtlayan normal testler (ör. `test_rate_limited_google_returns_originals_silently`). Düzeltme sırasında bilinçli olarak güncellenir. |
| **Gerçek GUI** | `test_gui.py` gerçek `TranslatorGUI`'yi kurar, gerçek `mainloop` ile worker thread'i çalıştırır, çıktıyı diskten doğrular. Ayarlar geçici dosyaya yönlendirilir, ağ ve modal diyaloglar kapatılır. |
| **Gerçek formatlar** | DOCX (python-docx), PDF (reportlab ile üretilip pdfminer ile geri okunur) testleri gerçek dosyalarla çalışır. |

## Dosyalar

| Dosya | Kapsam | Test |
|---|---|---|
| `test_parsing.py` | Zaman damgası/sıra no/VTT meta, boşluk, kodlama tespiti, requirements ayrıştırma, dil eşlemeleri | 55 |
| `test_translate_lines.py` | Satır yapısının korunması, CRLF, tekilleştirme, etiketler, satır kırma, Markdown/CSV | 17 |
| `test_engine.py` | Motor yönlendirme, 429, fallback, istek sayısı, thread yarışı, ilerleme, iptal | 28 |
| `test_formats.py` | TXT, DOCX (gövde/tablo/üstbilgi/köprü), PDF (Türkçe glif, kelime bölme), CLI | 19 |
| `test_gui.py` | Kurulum, uçtan uca çeviri, paralel dosya, çıktı klasörü, worker↔Tk thread ayrımı, iptal, ayarlar, tema, kuyruk, sözlük | 36 |
| `test_ui_i18n.py` | 37 dil paketi, emoji önek araması, önbellek, canlı dil değişiminde tüm görünür metinler, **ikincil pencereler**, kırpılma, kaydırma, log, tema, menü, **tek seferde açılış** | 152 |
| `test_network.py` | Canlı Google/MyMemory, birleşik istek kavram kanıtı, küçük dosya | 4 (varsayılan kapalı) |

## Son Sonuç (2026-10-13, Windows 10, Python 3.10.11)

```
270 passed, 40 xfailed, 4 deselected in 38.7s      (main, hızlı motor + 20 dilli README sonrası)
264 passed, 42 xfailed, 4 deselected in 17.7s      (ui-overhaul dalı, 2. tur)
252 passed, 42 xfailed, 4 deselected in 13.5s      (ui-overhaul dalı, 1. tur)
94 passed, 59 xfailed, 2 xpassed, 4 deselected     (ilk sürüm, main)
```
- **42 xfailed** = belgelenmiş, henüz düzeltilmemiş hatalar (çoğu çeviri motoru: H1, H2, H3, H12…).
- Arayüz turunda 17 xfail XPASS verdi ve normal teste çevrildi (H4, H5, H6, H7, H10, H11, H27, H36, H38).

## Arayüz denetimi (`tools/ui_audit.py`)

Gerçek GUI, 37 dilin her birine geçirilip tüm görünür widget metinleri toplanır.

| Ölçüm (dil başına) | Önce | Sonra |
|---|---|---|
| İngilizce kalan görünür metin (56 metinden) | 22–45 (16 dilde 45) | 6–7 (yalnızca marka adları) |
| Yanlış alfabe (ör. Japonca pakette Korece) | 5 | 0 |
| Kırpılan widget | 2 | 0 |
| Dil değişiminde JSON okuma | 40 | 0 |
| Dil değişim süresi | ~220 ms | ~100 ms |
| Ana sayfa içerik yüksekliği (1280×720) | 1.370 px (tekerlek çalışmıyor) | 886 px (tekerlek çalışıyor) |
| `_log` × 2.000 | 5.6 sn | 0.51 sn |

### Canlı servis testleri
| Test | Sonuç | Not |
|---|---|---|
| `test_mymemory_single` | ✅ | |
| `test_google_joined_request_keeps_line_count` | ✅ | 50 satır tek istekte, satır sayısı korunuyor |
| `test_google_single` | ❌ 429 | İlk engelden 1.5 saat sonra hâlâ engelli (H47) |
| `test_pipeline_small_file` | ❌ | 1 satır bile çevrilmedi, MyMemory'ye düşülmedi (H1) |

## Performans Ölçümleri

`tools/benchmark.py` (sahte motor, istek başına 50 ms):

| Dosya | Replik | Benzersiz satır | Çok satırlı replik | Şu anki istek | Toplu istek (tahmin) |
|---|---|---|---|---|---|
| Örnek film (1080p, 2008) | 1.057 | 1.401 | 410 (%39) | **1.401** | **8** (175×) |
| `tests/fixtures/sample.en.srt` | 11 | 14 | 4 | 13 | 1 |

Canlı ölçümler:

| Senaryo | Süre |
|---|---|
| 80 satır, mevcut yöntem (Google, 4 thread) | 55.6 sn |
| 80 satır, tek birleşik istek | **1.0 sn** |
| 100 satırlık SRT, mevcut yöntem | 85.7 sn (0 satır çevrildi — 429) |
| GUI açılışı | 2.9 sn |
| Modül import | 0.7 sn |
| `_log` × 2.000 | 5.6 sn |

## Statik Analiz

`ruff check translate_srt.py --select F,E9,B,PLE,S`: 38 bulgu → 1 tanımsız isim (H27), 8 kullanılmayan değişken, 11 shell enjeksiyonu kalıbı (H41), 4 `zip()` uzunluk kontrolsüz (motor eksik sonuç döndürürse satırlar sessizce düşer).
