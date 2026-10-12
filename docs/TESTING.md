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
| `test_gui.py` | Kurulum, uçtan uca çeviri, paralel dosya, çıktı klasörü, hata diyaloğu thread'i, iptal, ayarlar, tema, kuyruk, sözlük | 36 |
| `test_network.py` | Canlı Google/MyMemory, birleşik istek kavram kanıtı, küçük dosya | 4 (varsayılan kapalı) |

## Son Sonuç (2026-10-13, Windows 10, Python 3.10.11)

```
94 passed, 59 xfailed, 2 xpassed, 4 deselected in 9.8s
```
- **59 xfailed** = belgelenmiş, henüz düzeltilmemiş hatalar.
- **2 xpassed** = H27 yarış testi (`strict=False`); 5 denemenin bazılarında hata mesajı gösteriliyor, bazılarında kayboluyor. Beklenen davranış.

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
