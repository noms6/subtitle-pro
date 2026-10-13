"""Generates tools/i18n_overrides.json: hand-checked UI terms where machine translation picks the wrong sense.

    python tools/make_i18n_overrides.py && python tools/i18n_sync.py --write
"""
import json

TERMS = ["Add...", "Remove", "Clear", "Browse", "Start", "File", "Files", "Status", "Size", "Added",
         "Preview", "Output", "Log", "Ready", "Auto", "Skip", "Retry", "s"]
T = {
 "tr": ["Ekle...", "Kaldır", "Temizle", "Gözat", "Başlat", "Dosya", "Dosyalar", "Durum", "Boyut", "Eklendi", "Önizleme", "Çıktı", "Kayıt", "Hazır", "Otomatik", "Atla", "Yeniden dene", "sn"],
 "de": ["Hinzufügen...", "Entfernen", "Leeren", "Durchsuchen", "Starten", "Datei", "Dateien", "Status", "Größe", "Hinzugefügt", "Vorschau", "Ausgabe", "Protokoll", "Bereit", "Automatisch", "Überspringen", "Wiederholen", "s"],
 "fr": ["Ajouter...", "Supprimer", "Vider", "Parcourir", "Démarrer", "Fichier", "Fichiers", "Statut", "Taille", "Ajouté", "Aperçu", "Sortie", "Journal", "Prêt", "Auto", "Ignorer", "Réessayer", "s"],
 "es": ["Añadir...", "Quitar", "Vaciar", "Examinar", "Iniciar", "Archivo", "Archivos", "Estado", "Tamaño", "Añadido", "Vista previa", "Salida", "Registro", "Listo", "Automático", "Omitir", "Reintentar", "s"],
 "it": ["Aggiungi...", "Rimuovi", "Svuota", "Sfoglia", "Avvia", "File", "File", "Stato", "Dimensione", "Aggiunto", "Anteprima", "Output", "Registro", "Pronto", "Automatico", "Salta", "Riprova", "s"],
 "pt": ["Adicionar...", "Remover", "Limpar", "Procurar", "Iniciar", "Arquivo", "Arquivos", "Status", "Tamanho", "Adicionado", "Pré-visualizar", "Saída", "Registro", "Pronto", "Automático", "Pular", "Tentar novamente", "s"],
 "nl": ["Toevoegen...", "Verwijderen", "Wissen", "Bladeren", "Starten", "Bestand", "Bestanden", "Status", "Grootte", "Toegevoegd", "Voorbeeld", "Uitvoer", "Logboek", "Gereed", "Automatisch", "Overslaan", "Opnieuw", "s"],
 "sv": ["Lägg till...", "Ta bort", "Rensa", "Bläddra", "Starta", "Fil", "Filer", "Status", "Storlek", "Tillagd", "Förhandsgranska", "Utdata", "Logg", "Klar", "Automatiskt", "Hoppa över", "Försök igen", "s"],
 "da": ["Tilføj...", "Fjern", "Ryd", "Gennemse", "Start", "Fil", "Filer", "Status", "Størrelse", "Tilføjet", "Eksempel", "Output", "Log", "Klar", "Automatisk", "Spring over", "Prøv igen", "s"],
 "no": ["Legg til...", "Fjern", "Tøm", "Bla gjennom", "Start", "Fil", "Filer", "Status", "Størrelse", "Lagt til", "Forhåndsvisning", "Utdata", "Logg", "Klar", "Automatisk", "Hopp over", "Prøv igjen", "s"],
 "fi": ["Lisää...", "Poista", "Tyhjennä", "Selaa", "Aloita", "Tiedosto", "Tiedostot", "Tila", "Koko", "Lisätty", "Esikatselu", "Tuloste", "Loki", "Valmis", "Automaattinen", "Ohita", "Yritä uudelleen", "s"],
 "pl": ["Dodaj...", "Usuń", "Wyczyść", "Przeglądaj", "Rozpocznij", "Plik", "Pliki", "Stan", "Rozmiar", "Dodano", "Podgląd", "Wyjście", "Dziennik", "Gotowe", "Automatycznie", "Pomiń", "Ponów", "s"],
 "cs": ["Přidat...", "Odebrat", "Vymazat", "Procházet", "Spustit", "Soubor", "Soubory", "Stav", "Velikost", "Přidáno", "Náhled", "Výstup", "Protokol", "Připraveno", "Automaticky", "Přeskočit", "Opakovat", "s"],
 "sk": ["Pridať...", "Odobrať", "Vymazať", "Prehľadávať", "Spustiť", "Súbor", "Súbory", "Stav", "Veľkosť", "Pridané", "Náhľad", "Výstup", "Protokol", "Pripravené", "Automaticky", "Preskočiť", "Skúsiť znova", "s"],
 "sl": ["Dodaj...", "Odstrani", "Počisti", "Prebrskaj", "Začni", "Datoteka", "Datoteke", "Stanje", "Velikost", "Dodano", "Predogled", "Izhod", "Dnevnik", "Pripravljeno", "Samodejno", "Preskoči", "Poskusi znova", "s"],
 "hr": ["Dodaj...", "Ukloni", "Očisti", "Pregledaj", "Pokreni", "Datoteka", "Datoteke", "Status", "Veličina", "Dodano", "Pregled", "Izlaz", "Zapisnik", "Spremno", "Automatski", "Preskoči", "Pokušaj ponovno", "s"],
 "sr": ["Додај...", "Уклони", "Очисти", "Прегледај", "Покрени", "Датотека", "Датотеке", "Статус", "Величина", "Додато", "Преглед", "Излаз", "Дневник", "Спремно", "Аутоматски", "Прескочи", "Покушај поново", "с"],
 "hu": ["Hozzáadás...", "Eltávolítás", "Törlés", "Tallózás", "Indítás", "Fájl", "Fájlok", "Állapot", "Méret", "Hozzáadva", "Előnézet", "Kimenet", "Napló", "Kész", "Automatikus", "Kihagyás", "Újra", "mp"],
 "ro": ["Adaugă...", "Elimină", "Golește", "Răsfoiește", "Pornește", "Fișier", "Fișiere", "Stare", "Dimensiune", "Adăugat", "Previzualizare", "Ieșire", "Jurnal", "Gata", "Automat", "Omite", "Reîncearcă", "s"],
 "bg": ["Добави...", "Премахни", "Изчисти", "Избери", "Старт", "Файл", "Файлове", "Състояние", "Размер", "Добавен", "Преглед", "Изход", "Дневник", "Готово", "Автоматично", "Пропусни", "Опитай отново", "с"],
 "ru": ["Добавить...", "Удалить", "Очистить", "Обзор", "Начать", "Файл", "Файлы", "Состояние", "Размер", "Добавлен", "Предпросмотр", "Вывод", "Журнал", "Готово", "Авто", "Пропустить", "Повторить", "с"],
 "uk": ["Додати...", "Видалити", "Очистити", "Огляд", "Почати", "Файл", "Файли", "Стан", "Розмір", "Додано", "Попередній перегляд", "Вивід", "Журнал", "Готово", "Авто", "Пропустити", "Повторити", "с"],
 "el": ["Προσθήκη...", "Αφαίρεση", "Εκκαθάριση", "Αναζήτηση", "Έναρξη", "Αρχείο", "Αρχεία", "Κατάσταση", "Μέγεθος", "Προστέθηκε", "Προεπισκόπηση", "Έξοδος", "Καταγραφή", "Έτοιμο", "Αυτόματο", "Παράλειψη", "Επανάληψη", "δ"],
 "lt": ["Pridėti...", "Pašalinti", "Išvalyti", "Naršyti", "Pradėti", "Failas", "Failai", "Būsena", "Dydis", "Pridėta", "Peržiūra", "Išvestis", "Žurnalas", "Paruošta", "Automatinis", "Praleisti", "Kartoti", "s"],
 "lv": ["Pievienot...", "Noņemt", "Notīrīt", "Pārlūkot", "Sākt", "Fails", "Faili", "Statuss", "Izmērs", "Pievienots", "Priekšskatījums", "Izvade", "Žurnāls", "Gatavs", "Automātiski", "Izlaist", "Mēģināt vēlreiz", "s"],
 "et": ["Lisa...", "Eemalda", "Tühjenda", "Sirvi", "Alusta", "Fail", "Failid", "Olek", "Suurus", "Lisatud", "Eelvaade", "Väljund", "Logi", "Valmis", "Automaatne", "Jäta vahele", "Proovi uuesti", "s"],
 "id": ["Tambah...", "Hapus", "Bersihkan", "Telusuri", "Mulai", "Berkas", "Berkas", "Status", "Ukuran", "Ditambahkan", "Pratinjau", "Keluaran", "Log", "Siap", "Otomatis", "Lewati", "Coba lagi", "d"],
 "vi": ["Thêm...", "Xóa", "Làm trống", "Duyệt", "Bắt đầu", "Tệp", "Tệp", "Trạng thái", "Kích thước", "Đã thêm", "Xem trước", "Đầu ra", "Nhật ký", "Sẵn sàng", "Tự động", "Bỏ qua", "Thử lại", "giây"],
 "th": ["เพิ่ม...", "ลบ", "ล้าง", "เรียกดู", "เริ่ม", "ไฟล์", "ไฟล์", "สถานะ", "ขนาด", "เพิ่มเมื่อ", "แสดงตัวอย่าง", "ผลลัพธ์", "บันทึก", "พร้อม", "อัตโนมัติ", "ข้าม", "ลองใหม่", "วิ"],
 "ja": ["追加...", "削除", "クリア", "参照", "開始", "ファイル", "ファイル", "状態", "サイズ", "追加日時", "プレビュー", "出力", "ログ", "準備完了", "自動", "スキップ", "再試行", "秒"],
 "ko": ["추가...", "제거", "지우기", "찾아보기", "시작", "파일", "파일", "상태", "크기", "추가됨", "미리 보기", "출력", "로그", "준비됨", "자동", "건너뛰기", "다시 시도", "초"],
 "zh-CN": ["添加...", "移除", "清空", "浏览", "开始", "文件", "文件", "状态", "大小", "添加时间", "预览", "输出", "日志", "就绪", "自动", "跳过", "重试", "秒"],
 "zh-TW": ["新增...", "移除", "清除", "瀏覽", "開始", "檔案", "檔案", "狀態", "大小", "新增時間", "預覽", "輸出", "記錄", "就緒", "自動", "略過", "重試", "秒"],
 "ar": ["إضافة...", "إزالة", "مسح", "استعراض", "بدء", "ملف", "الملفات", "الحالة", "الحجم", "أُضيف", "معاينة", "المخرجات", "السجل", "جاهز", "تلقائي", "تخطي", "إعادة المحاولة", "ث"],
 "fa": ["افزودن...", "حذف", "پاک کردن", "مرور", "شروع", "فایل", "فایل‌ها", "وضعیت", "اندازه", "افزوده شد", "پیش‌نمایش", "خروجی", "گزارش", "آماده", "خودکار", "رد کردن", "تلاش دوباره", "ث"],
 "hi": ["जोड़ें...", "हटाएँ", "साफ़ करें", "ब्राउज़ करें", "शुरू करें", "फ़ाइल", "फ़ाइलें", "स्थिति", "आकार", "जोड़ा गया", "पूर्वावलोकन", "आउटपुट", "लॉग", "तैयार", "स्वचालित", "छोड़ें", "पुनः प्रयास करें", "से."],
}
EXTRA = {  # Words (counter label), Teal (colour), ETA (time left label)
 "tr": {"Words": "Kelime", "Teal": "Turkuaz", "ETA": "Kalan"},
 "de": {"Words": "Wörter", "Teal": "Petrol", "ETA": "Restzeit"},
 "fr": {"Words": "Mots", "Teal": "Bleu canard", "ETA": "Temps restant"},
 "es": {"Words": "Palabras", "Teal": "Verde azulado", "ETA": "Tiempo restante"},
 "it": {"Words": "Parole", "Teal": "Verde acqua", "ETA": "Tempo rimanente"},
 "pt": {"Words": "Palavras", "Teal": "Azul-petróleo", "ETA": "Tempo restante"},
 "ru": {"Words": "Слова", "Teal": "Бирюзовый", "ETA": "Осталось"},
 "uk": {"Words": "Слова", "Teal": "Бірюзовий", "ETA": "Залишилось"},
 "ja": {"Words": "単語数", "Teal": "ティール", "ETA": "残り時間"},
 "ko": {"Words": "단어 수", "Teal": "청록색", "ETA": "남은 시간"},
 "zh-CN": {"Words": "字数", "Teal": "青色", "ETA": "剩余时间"},
 "zh-TW": {"Words": "字數", "Teal": "青色", "ETA": "剩餘時間"},
 "ar": {"Words": "الكلمات", "Teal": "أزرق مخضر", "ETA": "الوقت المتبقي"},
 "fa": {"Words": "واژه‌ها", "Teal": "سبزآبی", "ETA": "زمان باقی‌مانده"},
}
THEME_KEYS = ["Theme:", "Accent color:", "Light mode", "Dark mode"]
THEME = {
 "tr": ["Tema:", "Vurgu rengi:", "Açık", "Koyu"], "de": ["Design:", "Akzentfarbe:", "Hell", "Dunkel"],
 "fr": ["Thème :", "Couleur d'accentuation :", "Clair", "Sombre"], "es": ["Tema:", "Color de énfasis:", "Claro", "Oscuro"],
 "it": ["Tema:", "Colore principale:", "Chiaro", "Scuro"], "pt": ["Tema:", "Cor de destaque:", "Claro", "Escuro"],
 "nl": ["Thema:", "Accentkleur:", "Licht", "Donker"], "sv": ["Tema:", "Accentfärg:", "Ljust", "Mörkt"],
 "da": ["Tema:", "Accentfarve:", "Lyst", "Mørkt"], "no": ["Tema:", "Uthevingsfarge:", "Lyst", "Mørkt"],
 "fi": ["Teema:", "Korostusväri:", "Vaalea", "Tumma"], "pl": ["Motyw:", "Kolor akcentu:", "Jasny", "Ciemny"],
 "cs": ["Motiv:", "Barva zvýraznění:", "Světlý", "Tmavý"], "sk": ["Motív:", "Farba zvýraznenia:", "Svetlý", "Tmavý"],
 "sl": ["Tema:", "Barva poudarka:", "Svetla", "Temna"], "hr": ["Tema:", "Boja isticanja:", "Svijetla", "Tamna"],
 "sr": ["Тема:", "Боја истицања:", "Светла", "Тамна"], "hu": ["Téma:", "Kiemelőszín:", "Világos", "Sötét"],
 "ro": ["Temă:", "Culoare de accent:", "Luminos", "Întunecat"], "bg": ["Тема:", "Цвят за акцент:", "Светла", "Тъмна"],
 "ru": ["Тема:", "Цвет акцента:", "Светлая", "Тёмная"], "uk": ["Тема:", "Колір акценту:", "Світла", "Темна"],
 "el": ["Θέμα:", "Χρώμα έμφασης:", "Φωτεινό", "Σκούρο"], "lt": ["Tema:", "Akcento spalva:", "Šviesi", "Tamsi"],
 "lv": ["Motīvs:", "Akcenta krāsa:", "Gaišs", "Tumšs"], "et": ["Teema:", "Rõhuvärv:", "Hele", "Tume"],
 "id": ["Tema:", "Warna aksen:", "Terang", "Gelap"], "vi": ["Chủ đề:", "Màu nhấn:", "Sáng", "Tối"],
 "th": ["ธีม:", "สีเน้น:", "สว่าง", "มืด"], "ja": ["テーマ：", "アクセントカラー：", "ライト", "ダーク"],
 "ko": ["테마:", "강조 색:", "밝게", "어둡게"], "zh-CN": ["主题：", "强调色：", "浅色", "深色"],
 "zh-TW": ["主題：", "強調色彩：", "淺色", "深色"], "ar": ["السمة:", "لون التمييز:", "فاتح", "داكن"],
 "fa": ["پوسته:", "رنگ تأکیدی:", "روشن", "تیره"], "hi": ["थीम:", "एक्सेंट रंग:", "लाइट", "डार्क"],
}
CANCEL = {"de": "Abbrechen", "ar": "إلغاء", "fa": "لغو", "hi": "रद्द करें", "ru": "Отмена", "uk": "Скасувати",
          "pl": "Anuluj", "nl": "Annuleren", "it": "Annulla", "pt": "Cancelar", "es": "Cancelar", "fr": "Annuler",
          "tr": "İptal", "ja": "キャンセル", "ko": "취소", "zh-CN": "取消", "zh-TW": "取消", "el": "Ακύρωση",
          "cs": "Zrušit", "sk": "Zrušiť", "hu": "Mégse", "ro": "Anulează", "sv": "Avbryt", "da": "Annuller",
          "no": "Avbryt", "fi": "Peruuta", "bg": "Отказ", "sr": "Откажи", "hr": "Odustani", "sl": "Prekliči",
          "lt": "Atšaukti", "lv": "Atcelt", "et": "Tühista", "id": "Batal", "vi": "Hủy", "th": "ยกเลิก"}
MISC = {"de": {"UI language:": "Oberflächensprache:", "Engine:": "Dienst:"}}
# "Open output folder" | "Open folder" | first-word for "<engine> first" (fmt with {e})
OPEN = {
 "ar": ("فتح مجلد الإخراج", "فتح المجلد", "{e} أولاً"), "bg": ("Отвори изходната папка", "Отвори папката", "Първо {e}"),
 "cs": ("Otevřít výstupní složku", "Otevřít složku", "Nejprve {e}"), "da": ("Åbn outputmappe", "Åbn mappe", "{e} først"),
 "de": ("Ausgabeordner öffnen", "Ordner öffnen", "{e} zuerst"), "el": ("Άνοιγμα φακέλου εξόδου", "Άνοιγμα φακέλου", "Πρώτα {e}"),
 "es": ("Abrir carpeta de salida", "Abrir carpeta", "Primero {e}"), "et": ("Ava väljundkaust", "Ava kaust", "Esmalt {e}"),
 "fa": ("باز کردن پوشه خروجی", "باز کردن پوشه", "اول {e}"), "fi": ("Avaa tulostekansio", "Avaa kansio", "{e} ensin"),
 "fr": ("Ouvrir le dossier de sortie", "Ouvrir le dossier", "{e} d'abord"), "hi": ("आउटपुट फ़ोल्डर खोलें", "फ़ोल्डर खोलें", "पहले {e}"),
 "hr": ("Otvori izlaznu mapu", "Otvori mapu", "Prvo {e}"), "hu": ("Kimeneti mappa megnyitása", "Mappa megnyitása", "Először {e}"),
 "id": ("Buka folder keluaran", "Buka folder", "{e} dulu"), "it": ("Apri cartella di output", "Apri cartella", "Prima {e}"),
 "ja": ("出力フォルダーを開く", "フォルダーを開く", "{e} を優先"), "ko": ("출력 폴더 열기", "폴더 열기", "{e} 우선"),
 "lt": ("Atidaryti išvesties aplanką", "Atidaryti aplanką", "Pirmiausia {e}"), "lv": ("Atvērt izvades mapi", "Atvērt mapi", "Vispirms {e}"),
 "nl": ("Uitvoermap openen", "Map openen", "Eerst {e}"), "no": ("Åpne utdatamappen", "Åpne mappe", "{e} først"),
 "pl": ("Otwórz folder wyjściowy", "Otwórz folder", "Najpierw {e}"), "pt": ("Abrir pasta de saída", "Abrir pasta", "Primeiro {e}"),
 "ro": ("Deschide folderul de ieșire", "Deschide folderul", "Întâi {e}"), "ru": ("Открыть папку вывода", "Открыть папку", "Сначала {e}"),
 "sk": ("Otvoriť výstupný priečinok", "Otvoriť priečinok", "Najprv {e}"), "sl": ("Odpri izhodno mapo", "Odpri mapo", "Najprej {e}"),
 "sr": ("Отвори излазну фасциклу", "Отвори фасциклу", "Прво {e}"), "sv": ("Öppna utdatamappen", "Öppna mapp", "{e} först"),
 "th": ("เปิดโฟลเดอร์ผลลัพธ์", "เปิดโฟลเดอร์", "{e} ก่อน"), "tr": ("Çıktı klasörünü aç", "Klasörü aç", "Önce {e}"),
 "uk": ("Відкрити папку виводу", "Відкрити папку", "Спочатку {e}"), "vi": ("Mở thư mục đầu ra", "Mở thư mục", "Ưu tiên {e}"),
 "zh-CN": ("打开输出文件夹", "打开文件夹", "优先 {e}"), "zh-TW": ("開啟輸出資料夾", "開啟資料夾", "優先 {e}"),
}
# "Export..." | "Progress" | "Remaining" | "ETA" (label before mm:ss) | "Elapsed"
PROG = {
 "ar": ("تصدير...", "التقدم", "المتبقي", "المتبقي", "المنقضي"), "bg": ("Експорт...", "Напредък", "Остава", "Остава", "Изминало"),
 "cs": ("Exportovat...", "Průběh", "Zbývá", "Zbývá", "Uplynulo"), "da": ("Eksportér...", "Fremdrift", "Tilbage", "Tilbage", "Forløbet"),
 "de": ("Exportieren...", "Fortschritt", "Verbleibend", "Restzeit", "Vergangen"), "el": ("Εξαγωγή...", "Πρόοδος", "Απομένει", "Απομένει", "Πέρασαν"),
 "es": ("Exportar...", "Progreso", "Restante", "Restante", "Transcurrido"), "et": ("Ekspordi...", "Edenemine", "Jäänud", "Jäänud", "Möödunud"),
 "fa": ("خروجی گرفتن...", "پیشرفت", "باقی‌مانده", "باقی‌مانده", "سپری‌شده"), "fi": ("Vie...", "Edistyminen", "Jäljellä", "Jäljellä", "Kulunut"),
 "fr": ("Exporter...", "Progression", "Restant", "Temps restant", "Écoulé"), "hi": ("निर्यात करें...", "प्रगति", "शेष", "शेष समय", "बीता समय"),
 "hr": ("Izvezi...", "Napredak", "Preostalo", "Preostalo", "Proteklo"), "hu": ("Exportálás...", "Folyamat", "Hátralévő", "Hátralévő", "Eltelt"),
 "id": ("Ekspor...", "Kemajuan", "Tersisa", "Sisa waktu", "Berlalu"), "it": ("Esporta...", "Avanzamento", "Rimanente", "Tempo rimanente", "Trascorso"),
 "ja": ("エクスポート...", "進捗", "残り", "残り時間", "経過"), "ko": ("내보내기...", "진행률", "남음", "남은 시간", "경과"),
 "lt": ("Eksportuoti...", "Eiga", "Liko", "Liko", "Praėjo"), "lv": ("Eksportēt...", "Norise", "Atlicis", "Atlicis", "Pagājis"),
 "nl": ("Exporteren...", "Voortgang", "Resterend", "Resterend", "Verstreken"), "no": ("Eksporter...", "Fremdrift", "Gjenstår", "Gjenstår", "Forløpt"),
 "pl": ("Eksportuj...", "Postęp", "Pozostało", "Pozostało", "Upłynęło"), "pt": ("Exportar...", "Progresso", "Restante", "Tempo restante", "Decorrido"),
 "ro": ("Exportă...", "Progres", "Rămas", "Timp rămas", "Scurs"), "ru": ("Экспорт...", "Ход выполнения", "Осталось", "Осталось", "Прошло"),
 "sk": ("Exportovať...", "Priebeh", "Zostáva", "Zostáva", "Uplynulo"), "sl": ("Izvozi...", "Napredek", "Preostalo", "Preostalo", "Preteklo"),
 "sr": ("Извези...", "Напредак", "Преостало", "Преостало", "Протекло"), "sv": ("Exportera...", "Förlopp", "Återstår", "Återstår", "Förflutet"),
 "th": ("ส่งออก...", "ความคืบหน้า", "เหลือ", "เวลาที่เหลือ", "ผ่านไป"), "tr": ("Dışa aktar...", "İlerleme", "Kalan", "Kalan", "Geçen"),
 "uk": ("Експорт...", "Хід виконання", "Залишилось", "Залишилось", "Минуло"), "vi": ("Xuất...", "Tiến độ", "Còn lại", "Thời gian còn lại", "Đã qua"),
 "zh-CN": ("导出...", "进度", "剩余", "剩余时间", "已用时"), "zh-TW": ("匯出...", "進度", "剩餘", "剩餘時間", "已用時間"),
}
for _c, _vals in PROG.items():
    MISC.setdefault(_c, {}).update(dict(zip(["Export...", "Progress", "Remaining", "ETA", "Elapsed"], _vals)))
for _c, (_o, _f, _first) in OPEN.items():
    MISC.setdefault(_c, {}).update({"Open output folder": _o, "Open folder": _f,
                                    "Google first": _first.format(e="Google"), "MyMemory first": _first.format(e="MyMemory")})
out = {}
for code, vals in T.items():
    assert len(vals) == len(TERMS), code
    out[code] = dict(zip(TERMS, vals))
    out[code].update(EXTRA.get(code, {}))
    out[code].update(dict(zip(THEME_KEYS, THEME[code])))
    out[code]["Cancel"] = CANCEL[code]
    out[code].update(MISC.get(code, {}))
out["_comment"] = "Hand-checked UI terms where machine translation picks the wrong sense (e.g. 'Clear' -> 'obvious'). Applied last by tools/i18n_sync.py."
import os
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n_overrides.json"), "w", encoding="utf-8", newline="\n") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
print(len(out) - 1, "languages")
