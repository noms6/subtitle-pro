# Yol Haritası

> Hatalar: [KNOWN_ISSUES.md](KNOWN_ISSUES.md) · Testler ve ölçümler: [TESTING.md](TESTING.md)

## Mimari (bugün)

```
            ┌──────────────── GUI (TranslatorGUI, ~3.600 satır) ───────────────┐
 dosyalar → │ kuyruk (Treeview) → _start() → worker thread → process_one(dosya) │
            └───────────────────────────────┬──────────────────────────────────┘
          .srt/.vtt → translate_lines()     │  .txt/.md/.csv → translate_text_file()
          .docx → translate_docx_file()     │  .pdf → translate_pdf_file()
                                            ▼
                        _build_translation_map(metinler)
                        1) tekilleştir  2) 100'lük partiler
                        3) 4 thread × birincil motor (Google/DeepL/Libre)
                        4) başarısız partiyi tek tek kurtar
                        5) None kalanlar → MyMemory (6 thread)
                                            ▼
                {kaynak: çeviri} → satırlara geri yerleştir (UTF-8 BOM)
```

## Hedef mimari

```
subtitle_pro/
  core/        cue modeli, srt/vtt/ass ayrıştırıcı-yazıcı, etiket koruma, satır dengeleme
  engines/     base (durum döndüren arayüz), google_batch, mymemory, deepl, libre, llm, offline
               rate_limiter (token bucket + 429 geri çekilme), cache (SQLite)
  formats/     docx (paragraf bazlı), pdf, text, markdown, csv
  pipeline.py  dosya → cue'lar → motor zinciri → rapor (UI'dan bağımsız, iptal edilebilir)
  cli.py       argparse, çıkış kodları, --json
  gui/         app, widgets, theme, dialogs, i18n — worker ile yalnızca kuyruk üzerinden konuşur
tests/
```

---

## Faz 0 — Depo ve test altyapısı ✅
- [x] git, `.gitignore`, telifli/kişisel dosyaların dışlanması, `settings.example.json`
- [x] `venv` + `requirements-dev.txt`, `pyproject.toml` (pytest, ruff)
- [x] 155 çevrimdışı test + 4 canlı test, bilinen hatalar `xfail(strict)` ile
- [x] GitHub Actions (Windows + Ubuntu/Xvfb, Python 3.10/3.12)
- [x] `tools/benchmark.py`

## Faz 1a — Arayüz ve dil ✅ (`ui-overhaul`)
- [x] İki sütunlu düzen, düz paneller, temaya uyan ilerleme halkası, kırpılmayan simge araç çubuğu
- [x] 37 dil paketi eşitlendi (çöp/kullanılmayan anahtarlar silindi, eksikler dolduruldu, 36 dil için elle kontrol edilmiş terimler)
- [x] Emoji önekli arama, bellek içi önbellek, gömülü Türkçe metinler kaldırıldı, yerel dil adları, 133 hedef dil adı
- [x] H4 worker↔Tk kuyruğu, H27, H38, H10/H11, H42, fare tekerleği, log filtreleri, ☰ menüsü
- [ ] RTL yerleşim (H69), ikincil diyalogların denetimi (H70), anadili konuşanlarca çeviri incelemesi

## Faz 1 — Doğruluk ve güvenlik (1–2 gün) · *ilk sürümden önce şart*
- [ ] **H1** Başarısız satırı asla başarı sayma; motor zinciri; "Kısmi" durum; CLI çıkış kodu (H35)
- [ ] **H3** Thread başına translator
- [x] **H4/H42** Ayar anlık görüntüsü + kuyruk tabanlı UI güncelleme; hata diyaloğu ana thread'de; log'a artımlı ekleme
- [x] **H27** Mesaj `except` içinde bağlanıyor
- [ ] **H50/H22** Import sırasında kurulum yok; eksik paket yalnızca özellik kullanılınca, onayla, `venv` içine
- [ ] **H41** `os.system` yerine `subprocess.run([...])` (liste argüman)
- [ ] **H51** Tüm HTTP isteklerine timeout; iptal beklemedeki isteği kessin
- [x] **H5/H6/H7** Dil listesi instance'dan; `_rebuild_target_lang_names` sınıfa; varsayılan hedef dil kodla
- [ ] **H8/H32/H9** MyMemory tam ISO eşlemesi + kaynak dil; mymemory_first'te Google yedeği; DeepL Web kaldır veya bağla
- [x] **H10/H11/H38** Ayarları birleştirerek kaydet, eksik ayarları ekle, `.get()`, tema yükleme sırası
- [ ] **H14/H44/H45** İptalde `.partial`, var olan çıktı için sor/yedekle, eksik dosyada hata
- [ ] **H20** Import yan etkileri · [x] **H21** Açılış ağ istekleri kaldırıldı

## Faz 2 — Performans (1–2 gün)
- [ ] `GoogleBatchEngine`: ≤4.500 karakterlik birleşik istek, `requests.Session`, JSON endpoint, satır sayısı doğrulama, uyuşmazlıkta ikiye bölerek yeniden deneme → **istek sayısı ~175× az** (H2)
- [ ] Token bucket (≤5 istek/sn) + 429'da üstel geri çekilme + jitter + otomatik motor değişimi (H47)
- [ ] SQLite çeviri önbelleği (kaynak hash + hedef + motor), yarıda kalan işi devam ettirme
- [ ] Ağır import'ları tembel yükle; GUI açılışı < 1 sn
- [ ] Hedef: tam film < 60 sn, çevrilmemiş satır = 0

## Faz 3 — Altyazı kalitesi (2–3 gün)
- [ ] Replik (cue) bazlı çeviri, sonra 42 karakter / en fazla 2 satır dengeli kırma (H12, H13)
- [ ] Etiket koruma: `<i> <b> <font>`, `{\an8}` (H12, H30)
- [ ] Zaman damgası/VTT ayrıştırıcıyı konuma göre yaz: index → timestamp → metin (H17, H18, H28, H29)
- [ ] Kodlama: `charset-normalizer` ile tespit, UTF-16 desteği (H19)
- [ ] Hatalı yanıt sezgisini metne değil HTTP durumuna dayandır (H33)

## Faz 4 — Mimari ayrıştırma (2–3 gün)
- [ ] Hedef mimariye göre modüllere böl; `except Exception: pass` yerine `logging` (H48)
- [ ] Tekrarlanan tanımları ve ölü kodu temizle (H49, H52)
- [ ] DOCX paragraf bazlı çeviri + köprü/metin kutusu (H25); PDF paragraf birleştirme ve kelime bazlı kırma (H26)
- [ ] Markdown kod bloklarını, CSV hücrelerini doğru işle (H31)
- [ ] Yerel pencere çerçevesi + DWM koyu başlık; tema tutarlılığı (H23, H39, H40)

## Faz 5 — Yeni özellikler
| Öncelik | Özellik | Neden |
|---|---|---|
| 1 | **LLM motoru** (Claude / OpenAI / yerel Ollama) + bağlam penceresi + terim sözlüğü istemde | Altyazı kalitesinde en büyük sıçrama: deyim, argo, karakter adları |
| 2 | **Yan yana düzenleyici**: orijinal/çeviri tablosu, satır düzenle, tekrar çevir, video önizleme (mpv/VLC) | Makine çevirisi her zaman düzeltme ister |
| 3 | **ASS/SSA, SBV, TTML** + **MKV'den gömülü altyazı çıkarma/gömme** (ffmpeg) | İndirilen videoların çoğunda altyazı gömülü |
| 4 | **Dizi modu**: S01E01…E10 tek iş, ortak sözlük + önbellek; **klasör izleme** | Toplu kullanım |
| 5 | Zamanlama: kaydırma, FPS dönüşümü, çakışma düzeltme, CPS (okuma hızı) uyarısı | Senkron sorunları |
| 6 | İki dilli altyazı çıktısı; SDH/HI temizliği (`[MÜZİK]`, konuşmacı adları) | Dil öğrenme, okunabilirlik |
| 7 | OpenSubtitles API ile hazır altyazı arama | Çeviriye hiç gerek kalmayabilir |
| 8 | Çevrimdışı motor (Argos Translate / NLLB) | İnternetsiz, limitsiz |
| 9 | Kalite kontrol: iki motoru karşılaştır, farklı satırları işaretle | Güven |
| 10 | Bildirim, iş geçmişi, sürükle-bırak klasör | Konfor |

## Faz 6 — Dağıtım
- [ ] PyInstaller tek `.exe` + GitHub Releases (Actions ile otomatik)
- [ ] Sürüm numaralandırma, CHANGELOG
- [ ] Kod imzalama (SmartScreen uyarısını azaltmak için)
