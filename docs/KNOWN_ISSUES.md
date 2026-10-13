# Bilinen Hatalar ve Sorunlar

> Son denetim: 2026-10-13 · Kapsam: `translate_srt.py` (5.694 satır), Python 3.10 / Windows 10
> Yöntem: kod incelemesi + statik analiz (ruff) + otomatik testler (`tests/`) + canlı servis testleri + ekran görüntüsü incelemesi.

Her hata bir test ile belgelenmiştir. Testler `xfail(strict=True)` olarak işaretlidir: **hata düzeltildiğinde test "XPASS" verip CI'ı kırmızıya çevirir**, işaretin kaldırılması gerektiğini hatırlatır. "Karakterizasyon" testleri ise hatalı davranışın bugün gerçekten oluştuğunu kanıtlar.

**Önem seviyeleri:** 🔴 Kritik (veri kaybı / yanlış çıktı / çökme) · 🟠 Yüksek (özellik çalışmıyor) · 🟡 Orta · ⚪ Düşük

## Özet

> ✅ = `ui-overhaul` dalında düzeltildi (testi artık normal test olarak geçiyor).

| Seviye | Adet | En önemlileri |
|---|---|---|
| 🔴 Kritik | 7 | Sessiz çeviri kaybı (H1), sahte toplu çeviri (H2), thread yarışı (H3), Tk thread ihlali (H4), IP engeli (H47), HTTP zaman aşımı yok (H51), sormadan paket kurma (H50) |
| 🟠 Yüksek | 15 | Dil listesi/varsayılan dil, MyMemory dil eşlemesi, DeepL Web, ayarların silinmesi, tema kaybı, bağlam kaybı… |
| 🟡 Orta | 20 | Satır kırma, iptal, VTT başlıkları, BOM, DOCX/PDF kalite, CLI… |
| ⚪ Düşük | 10 | Kod kalitesi, küçük UI sorunları |

---

## 🔴 Kritik

### H1 — Rate limit (429) durumunda çeviri sessizce kayboluyor
- **Yer:** `_build_translation_map` → `_primary_translate_batch` ([translate_srt.py:1306-1327](../translate_srt.py#L1306-L1327)), ana döngü [1404](../translate_srt.py#L1404), fallback koşulu [1423](../translate_srt.py#L1423)
- **Ne oluyor:** Parti 3 kez başarısız olunca satırlar tek tek deneniyor; yine olmazsa **orijinal metin** sonuç listesine ekleniyor. Ana döngü bunu başarı sayıyor, MyMemory yedeği yalnızca `None` değerler için çalıştığından hiç devreye girmiyor. Dosya "Tamamlandı" olarak işaretleniyor, CLI 0 ile çıkıyor.
- **Kanıt:**
  - Canlı: 100 satırlık SRT 86 sn sürdü, **0 satır çevrildi**. 1 satırlık dosya "auto" modda çevrilmedi (MyMemory çalışır durumdayken).
  - Örnek filmin önceki çıktısında 1.467 diyalog satırının **553'ü (%38)** çevrilmemiş.
  - Testler: `test_engine.py::test_rate_limited_google_returns_originals_silently`, `test_rate_limit_mid_run_leaves_tail_untranslated`, `test_gui.py::test_e2e_rate_limited_file_marked_done_but_untranslated`, `tests/test_network.py::test_pipeline_small_file`
- **Çözüm:** Satır başına durum (`ok/failed/skipped`); başarısız satırlar `None` kalsın → motor zinciri → hâlâ başarısızsa dosya "Kısmi (N satır)" olarak raporlansın, CLI sıfırdan farklı kodla çıksın.

### H2 — "Toplu çeviri" aslında satır başına bir HTTP isteği
- **Yer:** `google.translate_batch(...)` [1208](../translate_srt.py#L1208); `deep_translator 1.11.4` `_translate_batch` içeride her metin için `requests.get` yapıyor (HTML kazıma + BeautifulSoup, bağlantı yeniden kullanımı yok).
- **Ölçüm (`tools/benchmark.py`, örnek film):** 1.401 benzersiz satır = **1.401 istek**. Gerçek gecikmeyle (~0.7 sn/istek, 4 eşzamanlı) ≈ 4 dk; ancak Google ~200 istekten sonra 429 verdiği için tam bir film **pratikte asla bitmiyor**.
- **Kanıt:** canlı 80 satır = 55.6 sn (1.4 satır/sn). Aynı 80 satır tek istekte (`translate_a/single`, `\n` ile birleşik) = **1.0 sn**, 80/80 satır doğru döndü. Film için **8 istek** yeterli (175× az).
- **Testler:** `test_one_request_per_line_no_real_batching`, `test_one_bad_item_triggers_request_amplification` (tek bozuk satır 10'luk partide ≥28 isteğe yol açıyor), `test_request_budget_with_one_bad_item` (xfail), `test_network.py::test_google_joined_request_keeps_line_count`

### H3 — Tek translator nesnesi 4 thread arasında paylaşılıyor
- **Yer:** [1191](../translate_srt.py#L1191) `google = GoogleTranslator(...)` tüm pool worker'larında ortak. deep_translator `translate()` her çağrıda `self._url_params`'ı değiştirip sonra istek atıyor.
- **Kanıt:** `test_race_with_stateful_translator` — aynı desene sahip sahte motorla **satırların çevirileri birbirine karışıyor**. `test_single_translator_instance_shared_across_threads`.
- **Çözüm:** Thread başına nesne (`threading.local`) veya durumsuz HTTP istemcisi.

### ✅ H4 — Worker thread doğrudan Tkinter'a erişiyor *(düzeltildi: `ui-overhaul`)*
- **Yer:** `_start._run` içinde `self.*_var.get()`, `self._log()` (Text widget'ını yeniden çiziyor), `_save_settings()`; hata diyaloğu `_ask_error_action` ([4729](../translate_srt.py#L4729)) worker'dan `Toplevel` + `grab_set` + `wait_window` açıyor.
- **Kanıt:** Ana döngü çalışmazken worker `RuntimeError: main thread is not in main loop` ile çöküyor (test geliştirme sırasında gözlendi) → pencere kapanırken çeviri sürüyorsa aynı hata. `test_error_dialog_requested_from_worker_thread`.
- **Çözüm (uygulandı):** Ayarlar başlangıçta ana thread'de anlık görüntüye alınıyor; worker tüm UI güncellemelerini (`_post`) bir kuyruğa koyuyor, Tk thread'i 50 ms'de bir boşaltıyor; hata diyaloğu `_call_on_ui` ile ana thread'de açılıyor. Test: `test_worker_never_calls_tk_directly`, `test_error_dialog_on_main_thread`.

### H47 — Google IP engeli uzun sürüyor (operasyonel)
- **Kanıt:** İlk 429'dan **1.5 saat sonra** `translate.google.com/m` hâlâ 429 dönüyor; aynı IP'den `translate.googleapis.com/translate_a/single` ve MyMemory sorunsuz.
- **Etki:** H1 ile birleşince kullanıcı saatlerce "başarılı" ama çevrilmemiş dosyalar üretir.
- **Çözüm:** H2 (istek sayısını 100× azalt) + token-bucket hız sınırlayıcı + 429'da motor değiştirme + kullanıcıya görünür uyarı.

### H51 — HTTP isteklerinde zaman aşımı yok
- **Yer:** deep_translator `requests.get(...)` `timeout` parametresi olmadan çağrılıyor.
- **Etki:** Askıda kalan bir bağlantı worker'ı süresiz kilitler; İptal düğmesi beklemedeki isteği kesemez, `_API_SEM` slotu sonsuza dek dolu kalır.

### H50 — Import sırasında kullanıcıya sormadan paket kurulumu
- **Yer:** [202-225](../translate_srt.py#L202-L225): `deep_translator` import edilemezse modül yüklenirken `pip install --upgrade deep-translator` (ve selenium, webdriver-manager) **onay almadan**, aktif/global Python'a çalıştırılıyor. `__main__` ayrıca her açılışta eksik paket diyaloğu gösteriyor ([5688](../translate_srt.py#L5688)).
- **Risk:** Ortam bozulması, kurumsal makinelerde politika ihlali, tedarik zinciri riski.

---

## 🟠 Yüksek

| # | Sorun | Yer | Kanıt / Test |
|---|---|---|---|
| ✅ H5 | `_rebuild_target_lang_names` sınıf metodu değil; modül seviyesindeki `_rebuild_ui_lang_names(self)` içine girintilenmiş. Her çağrı `AttributeError`, sessizce yutuluyor; yerelleştirilmiş hedef dil haritası hiç oluşmuyor | [884-958](../translate_srt.py#L884-L958) | `test_rebuild_target_lang_names_is_method`, `test_target_lang_map_is_always_empty` |
| ✅ H6 | `GoogleTranslator.get_supported_languages` sınıf üzerinden çağrılıyor (instance metodu) → `TypeError` → 133 yerine **37 dil** | [556](../translate_srt.py#L556) | `test_supported_languages_full_list`, `test_many_target_languages` |
| ✅ H7 | Arayüz Türkçe iken varsayılan hedef dil **"Almanca"** (Türkçe yedek listede `"Turkish"` anahtarı yok, alfabetik ilk seçiliyor) | [2239](../translate_srt.py#L2239) | `test_turkish_fallback_contains_default_name`, ekran görüntüsü `docs/images/issue-default-target-and-theme.png` |
| H8 | MyMemory: bilinmeyen hedef diller `tr-TR`'ye düşüyor (Japonca → Türkçe); kaynak dil sabit `en-GB` | [354-370](../translate_srt.py#L354-L370), [1335](../translate_srt.py#L1335) | `test_mymemory_mapping_unknown_is_not_turkish[*]`, `test_mymemory_japanese_target_becomes_turkish`, `test_mymemory_source_not_hardcoded` |
| H9 | "DeepL (Web)" arayüzde var ama `primary` hiçbir zaman `deepl_web` olamıyor → her şey MyMemory'ye gidiyor; Selenium kodu ölü | [1392-1397](../translate_srt.py#L1392) | `test_deepl_web_is_used` |
| ✅ H10 | `_save_settings` dosyayı sıfırdan yazıyor: `deepl_api_key`, `libre_url`, `libre_api_key` **siliniyor**; motor, öncelik, sözlük, PDF modu, "aynı dili atla" hiç kaydedilmiyor | [5627](../translate_srt.py#L5627) | `test_save_settings_preserves_api_keys`, `test_settings_persist_all_options[*]` |
| ✅ H11 | "Aynı dildeki dosyayı atla" kapatılamıyor: `bool(BooleanVar)` her zaman `True` | [5250](../translate_srt.py#L5250), [5303](../translate_srt.py#L5303) | `test_skip_same_language_can_be_disabled` |
| H12 | Çok satırlı replikler satır satır çevriliyor (bağlam kaybı: "Stop!" → "Durmak!"); `<i>` gibi etiketler motora gidiyor. Örnek filmde 1.057 replikten **410'u (%39)** çok satırlı | [373-447](../translate_srt.py#L373) | `test_multiline_cue_translated_as_one_sentence`, `test_tags_protected` |
| ✅ H27 | Genel hata işleyicisi `except` sonrasında silinen `e`'yi lambda içinde kullanıyor → **yarış**: mesaj bazen gösteriliyor, bazen `NameError` ile kayboluyor (5 denemenin 2–3'ünde) | [5415-5416](../translate_srt.py#L5415) | `test_fatal_error_is_shown_to_user[*]`, ruff F821 |
| H32 | `auto` + `mymemory_first`: Google hiç oluşturulmadığından "boşlukları Google ile doldur" adımı ölü kod; MyMemory başarısızsa her şey çevrilmeden kalıyor | [1186](../translate_srt.py#L1186), [1369](../translate_srt.py#L1369) | `test_auto_mymemory_first_never_uses_google`, `test_mymemory_first_falls_back_to_google` |
| ✅ H38 | Kayıtlı koyu tema her açılışta kayboluyor: tema `_build_ui` içinde uygulanıyor, ayarlar ondan **sonra** yükleniyor | [2281-2282](../translate_srt.py#L2281), [2901](../translate_srt.py#L2901) | `test_saved_dark_theme_applied_on_start`, ekran görüntüsü |
| H41 | macOS/Linux'ta klasör/dosya açma `os.system(f"open '{path}'")` → adında `'` olan dosya **komut enjeksiyonu** (indirilen dosya adları kullanıcı kontrolünde değil) | [4678-4697](../translate_srt.py#L4678), [4954-4959](../translate_srt.py#L4954) | ruff S605 |
| H14 | İptal edilince yarım çevrilmiş dosya yazılıyor ve "Tamamlandı" görünüyor; MyMemory havuzu iptali hiç dinlemiyor | [1202](../translate_srt.py#L1202), [1353](../translate_srt.py#L1353) | `test_cancel_returns_originals_as_translations`, `test_cancel_does_not_stop_mymemory_pool`, `test_cancel_does_not_write_partial_file` |
| ✅ H21 | Her açılışta arka planda 20 dil için Google'a UI çeviri istekleri (429 kotasını tüketir, `ui_translations.json`'u yeniden yazar) | [2287](../translate_srt.py#L2287) | kod incelemesi |
| H44 | Var olan çıktı dosyası (ör. elle düzeltilmiş `film.tr.srt`) **sormadan üzerine yazılıyor** | tüm yazıcılar | `test_text_file_overwrites_existing_output_without_asking` |

---

## 🟡 Orta

| # | Sorun | Yer | Test |
|---|---|---|---|
| H13 | Yumuşak satır kırma CRLF dosyaya çıplak `\n` ekliyor (karışık satır sonu); kırma satır bazlı, 2 satırlık replik 4+ satıra çıkabiliyor; `wrap_limit=70` sabit (standart 42) | [418-446](../translate_srt.py#L418), [5280](../translate_srt.py#L5280) | `test_soft_wrap_keeps_line_ending_style`, `test_wrap_never_exceeds_two_lines_per_cue` |
| ✅ H15 | Hata diyaloğunda "Yeniden dene" sınırsız özyineleme | [5383](../translate_srt.py#L5383) | kod incelemesi |
| H16 | TXT + çıktı klasörü: "post" sözlük taşınmış dosyanın eski yolunu açıyor, sessizce uygulanmıyor | [5323-5338](../translate_srt.py#L5323) | kod incelemesi |
| H17 | Sadece rakamdan oluşan diyalog ("1984") çevrilmiyor; "Note/Style/Region" ile başlayan diyalog VTT meta sayılıp atlanıyor (SRT'de bile) | [233](../translate_srt.py#L233), [242](../translate_srt.py#L242) | `test_numeric_dialogue_line_is_translatable`, `test_dialogue_starting_with_note_is_translated` |
| H18 | Konum bilgili SRT zaman damgası, kısa VTT (`00:01.000`), tek haneli saat tanınmıyor → motora gönderiliyor | [229-230](../translate_srt.py#L229) | `test_srt_timestamp_with_coordinates`, `test_vtt_short_timestamp`, `test_srt_lenient_timestamp` |
| H19 | CLI ve TXT katı UTF-8 okuyor (CP1254 dosya çöker); UTF-16 altyazılar çöp karaktere dönüşüyor | [468](../translate_srt.py#L468), [1520](../translate_srt.py#L1520), [276](../translate_srt.py#L276) | `test_cli_cp1254_input`, `test_text_file_cp1254`, `test_read_lines_robust_utf16` |
| H20 | Modül import edilirken **ön plandaki başka bir uygulamanın** başlık çubuğu koyu yapılıyor (`GetForegroundWindow`) | [23-30](../translate_srt.py#L23) | kod incelemesi |
| H22 | Her açılışta eksik paket diyaloğu; requirements ayrıştırıcı extras/marker'ları anlamıyor | [140](../translate_srt.py#L140), [59](../translate_srt.py#L59) | `test_req_with_extras_and_markers` |
| H23 | `overrideredirect(True)`: Aero Snap, Win+ok, pencere kenarından boyutlandırma yok; Alt-Tab/görev çubuğu için hack gerekiyor | [2078](../translate_srt.py#L2078) | kod incelemesi |
| H24 | Paralel dosya modunda ilerleme/ETA tek `_start_ts` ile karışıyor; çubuk belirsiz moda geçiyor | [5174](../translate_srt.py#L5174) | kod incelemesi |
| H25 | DOCX "run" bazlı: kalın/italik ile bölünen cümle parça parça çevriliyor; köprü (hyperlink), metin kutusu, dipnot metinleri atlanıyor | [1623-1690](../translate_srt.py#L1623) | `test_docx_translates_run_fragments`, `test_docx_paragraph_level`, `test_docx_hyperlink_text_translated` |
| H26 | PDF: görsel satırlar ayrı çevriliyor (cümleler bölünüyor); karakter sayısıyla satır kırma kelimeleri ortadan kesiyor; "aynı dil" kontrolü ölü kod | [1714-1786](../translate_srt.py#L1714) | `test_pdf_sentence_across_lines`, `test_pdf_wrap_does_not_split_words` |
| H28 | UTF-8 BOM'lu dosyada ilk satır `﻿1` olarak okunuyor → sıra numarası motora gönderiliyor | [276](../translate_srt.py#L276) | `test_bom_first_index_not_translated` |
| H29 | VTT başlık alanları (`Kind:`, `Language:`) ve cue kimlikleri çevriliyor → dosya başlığı bozuluyor | [242](../translate_srt.py#L242) | `test_vtt_header_fields_not_translated`, `test_vtt_cue_identifier_not_translated` |
| H30 | ASS override etiketleri (`{\an8}`) motora gidiyor | — | `test_ass_override_tags_protected` |
| H31 | Markdown kod blokları çevriliyor; CSV hücre değil satır olarak (ayraç/tırnaklarla) çevriliyor | [1466](../translate_srt.py#L1466) | `test_markdown_code_block_untouched`, `test_csv_cells_translated_individually` |
| H33 | "server error", "too many requests" içeren **gerçek diyalog** motor hatası sanılıyor ve çevrilmeden kalıyor | [1159-1168](../translate_srt.py#L1159) | `test_dialogue_mentioning_server_error` |
| H35 | CLI: `argparse` yok (`--help` dosya adı sanılıyor), geçersiz dil kodunda traceback, tüm satırlar başarısız olsa da çıkış kodu 0 | [450](../translate_srt.py#L450) | `test_cli_has_no_help_flag`, `test_invalid_target_language_raises`, `test_cli_nonzero_exit_on_total_failure` |
| ✅ H42 | `_log` her çağrıda log panelini (1000 satıra kadar) baştan çiziyor: 2.000 mesaj = **5.6 sn**; üstelik worker thread'den çağrılıyor | [4786-4812](../translate_srt.py#L4786) | `tools/benchmark.py` |
| H45 | Kuyruğa eklendikten sonra silinen dosya: `_read_lines_robust` boş liste döner → boş çıktı yazılır, "Tamamlandı" | [276-291](../translate_srt.py#L276) | `test_read_lines_robust_missing_file_returns_empty` |

---

## ⚪ Düşük / Kod kalitesi

| # | Sorun |
|---|---|
| H34 | `split_whitespace("   ")` boşluğu ikiye katlıyor (pratikte boş satırlar önceden atlandığı için zararsız) — `test_split_whitespace[...]` |
| ✅ H36 | `_clear_files` `item_to_path` sözlüğünü temizlemiyor — `test_clear_files_clears_reverse_map` |
| H37 | Önizlemedeki dil ipucu her zaman `auto` (deep_translator `.source`'u güncellemiyor) — `test_language_hint` |
| ✅ H39 | Açık temada özel başlık çubuğundaki uygulama adı beyaz zemin üzerine beyaz (görünmüyor) — ekran görüntüsü |
| ✅ H40 | Koyu temada "Motor" radyo düğmeleri açık renk kalıyor; 1280 px genişlikte araç çubuğu taşıyor; kartlarda siyah gölge artıkları — ekran görüntüleri |
| H46 | Özel sözlük olarak JSON liste kabul ediliyor, sonra `_apply_terms` her satırda hata veriyor; sözlük varsayılanda kelime sınırı olmadan değiştiriyor ("Al"→"Ali" ⇒ "Also"→"Aliso") — `test_load_custom_dict_csv_and_bad_json`, `test_apply_terms_default_has_no_word_boundary` |
| H48 | 418 adet `except Exception`, 293 `pass`: hatalar görünmüyor (H1, H5, H27'nin fark edilmemesinin nedeni) |
| H49 | Tekrarlanan tanımlar: `_tr` (3442/3546), `_fmt_progress_label` (3445/3549), `clean_after_var` (2276/2770), `_rebuild_ui_lang_names` (884/5650); 8 kullanılmayan değişken (ruff F841) |
| H52 | 5.700 satır tek dosya; `_build_ui` ~560, `_apply_theme` ~400 satır; test ve CI yoktu |
| H53 | API anahtarları `settings.json`'da düz metin; `settings.json` artık `.gitignore`'da, örnek dosya: `settings.example.json` |

---

## Arayüz ve dil denetimi (2026-10-13, `tools/ui_audit.py`)

Gerçek GUI kurulup 37 arayüz dilinin her birine geçilerek tüm görünür widget metinleri toplandı. Bulunanlar ve durumları:

| # | Sorun | Önce | Sonra |
|---|---|---|---|
| ✅ H54 | Dil paketleri büyük ölçüde çevrilmemiş: 16 dilde görünür metinlerin ~%80'i İngilizce, Almanca'da bile 25/56 | dil başına 22–45 İngilizce metin | yalnızca marka adları (Google, DeepL…) |
| ✅ H55 | Japonca pakette **Korece** metinler ("선택 항목 시작") | 5 giriş | 0 — `test_no_wrong_script[*]` |
| ✅ H56 | Emoji önekli metinler ("📂 Add...") JSON'daki "Add..." anahtarıyla hiç eşleşmiyordu | araç çubuğu her dilde İngilizce | önek ayrılıp çeviriliyor |
| ✅ H57 | `_tr()` her çağrıda 273 KB JSON'u diskten okuyup ayrıştırıyordu | dil değişimi başına 40 okuma, ~220 ms | 0 okuma (mtime önbelleği), ~100 ms |
| ✅ H58 | Kodda gömülü Türkçe metinler ("Hazır", "Çeviriliyor", "Tamamlandı", ilerleme satırı, onay diyalogları) her dilde Türkçe görünüyordu | ~25 metin | hepsi çeviri anahtarı |
| ✅ H59 | Log filtre kutuları çalışmıyordu (değişkenler bağlandıktan sonra yeniden oluşturuluyordu) | bağlantı yok | `test_log_filter_checkbox_controls_view` |
| ✅ H60 | Fare tekerleği ana sayfayı kaydırmıyordu (gizli panelin `bind_all`'u tekerleği çalıyordu); içerik 1.370 px, görünen 587 px | kaydırma yok | çalışıyor; içerik 886 px |
| ✅ H61 | Yerel menü çubuğu `overrideredirect` yüzünden görünmüyor → Yazı boyutu, Kompakt mod, Tercihler erişilemezdi | erişilemez | ☰ menüsünde |
| ✅ H62 | 12 düğmelik araç çubuğu 1280 px'te taşıyor, düğmeler kırpılıyordu | 2 kırpılan widget | 0 — `test_no_clipped_widgets[*]` |
| ✅ H63 | Hedef dil/motor şeridi kaydırma alanının dışında, temasız; koyu temada açık renk radyo kutuları | | sağ panelde, temalı |
| ✅ H64 | Kartlarda siyah gölge, iç çerçevelerde uyumsuz arka planlar (kartlar hiç tema rengi almıyordu) | | düz panel + ince kenarlık |
| ✅ H65 | Arayüz dili değişince UI thread'inde **senkron Google isteği** (pencere donabiliyordu) | | kaldırıldı |
| ✅ H66 | Makine çevirisi anlam hataları: ar "Clear"→"açık/belirgin", ar "Teal"→"yaban ördeği", ar "Theme"→"konu", ar "Accent"→"şive", ja "Start selected"→"Başlat seçildi", tr "Light mode"→"Işık modu", ja "light"→"光" | | belirsiz kaynak metinler yeniden yazıldı + 36 dil için elle kontrol edilmiş terim tablosu (`tools/i18n_overrides.json`) |
| ✅ H67 | Kuyruk durumları dil değişince güncellenmiyor; durum çubuğu açık temada "theme:dark" yazıyordu | | `_retranslate_queue_statuses`, `test_status_bar_reflects_theme_and_language` |
| ✅ H68 | Hedef dil listesi Türkçe dışındaki arayüzlerde İngilizce (veya çıplak kod: "af"); arayüz dili listesi yerel adlar yerine İngilizce | | `lang_names.json` (37 × 133 ad) + yerel adlar ("Deutsch", "日本語") |
| H69 | Sağdan sola diller (Arapça, Farsça): metinler doğru çiziliyor ama yerleşim aynalanmıyor (Tk'nin RTL desteği yok) | açık | — |
| ✅ H70 | İkincil pencereler denetlenmemişti | — | `test_dialogs_are_translated[*]` (Ayarlar/Hakkında/Önizleme × tr/de/ja) |
| ✅ H71 | **Açılışta iki farklı arayüz:** pencere kurulurken görünüyordu — önce tam ekran beyaz pencere + yerel menü şeridi (0–3,5 sn), sonra 1024×680'e küçülüp sol üste geçiyor, tema sonradan değişiyordu (`state("zoomed")` çerçevesiz pencerede çalışmıyor, `fix_window_focus` gizle/göster yapıyordu) | ekran kaydıyla doğrulandı | pencere gizli kurulur, çalışma alanı boyutunda **bir kez** gösterilir — `test_window_shown_once_and_sized` |
| ✅ H72 | Görünüm iki sistemden geliyordu (ttkbootstrap temaları + ~550 satır elle renk yaması) → makineye/ayara göre farklı görünüm (ör. "pulse" teması turkuaz düğmeler) | | tek palet tabanlı tasarım sistemi (`_apply_design`), ttkbootstrap kaldırıldı |
| ✅ H73 | Hakkında penceresindeki proje bağlantısı alakasız bir projeye (nicegui.io) gidiyordu; sürüm/başlık eskiydi | | GitHub deposu — `test_about_links_to_this_project` |
| ✅ H74 | Önizleme UI thread'inde Google'a istek atıyordu (donma + kota) ve dosyayı katı UTF-8 okuyordu | | çevrimdışı langdetect + `_read_lines_robust` — `test_preview_is_offline` |
| ✅ H75 | "Gelişmiş ayarlar" birkaç alan için tam ekran açılıyordu; değerler ham anahtar ("google_first", "pre", "blue"); ayarlar 3 pencereye dağınık, koyu tema 3 yerde | | tek **Ayarlar** penceresi (Görünüm/Çeviri/Çıktı/Sözlük), yerelleştirilmiş seçenekler |
| ✅ H76 | Makine çevirisi anlam hataları (2. tur): "Open output folder" → es/fr/pt "açık durumdaki klasör", uk "açık kaynak klasörü"; "Google first" → sv "önce Google'la", hi "önce Google'da ara", sr "Гоогле" | | 36 dil için elle düzeltildi |
| ✅ H77 | Uygulama adı iki kez (özel başlık çubuğu + başlık satırı); açık temada beyaz kutu içinde | | tek başlık çubuğu: logo, ad, tema/vurgu/dil, ☰, pencere düğmeleri |
| ✅ H78 | Kapanışta `invalid command name ..._drain_log_queue` / `ThemeChanged` hataları (pencere yok edildikten sonra çalışan zamanlayıcılar) | | zamanlayıcı iptal ediliyor, bekleyen görevler boşaltılıyor |

Ekran görüntüleri: `docs/images/screenshot-*.png`, `dialog-*.png`. Önceki hâl: `docs/images/issue-default-target-and-theme.png`.

## Depo hijyeni (GitHub öncesi)
- Telifli film altyazıları (`Superhero Movie ... .srt`, `test_sub*.srt`) ve kişisel `settings.json` depoya **eklenmez** (`.gitignore`). Testler için özgün örnek: `tests/fixtures/sample.en.srt`.
- `translate_srt1.py` (kullanılmayan eski kopya) ve ağa bağımlı manuel `test_runner*.py` betikleri depo dışında tutuldu.
