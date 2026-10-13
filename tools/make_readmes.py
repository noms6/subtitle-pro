"""Generates README.md (English, main page) and docs/readme/README.<lang>.md (19 more languages).

Edit the TEXT dictionary below, then run:
    python tools/make_readmes.py
Screenshots come from:  python tools/readme_shots.py
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "noms6/subtitle-pro"

LANGS = [
    ("en", "English"), ("tr", "Türkçe"), ("de", "Deutsch"), ("fr", "Français"), ("es", "Español"),
    ("it", "Italiano"), ("pt", "Português"), ("nl", "Nederlands"), ("pl", "Polski"), ("sv", "Svenska"),
    ("ru", "Русский"), ("uk", "Українська"), ("ar", "العربية"), ("fa", "فارسی"), ("hi", "हिन्दी"),
    ("ja", "日本語"), ("ko", "한국어"), ("zh", "中文"), ("id", "Bahasa Indonesia"), ("vi", "Tiếng Việt"),
]
RTL = {"ar", "fa"}

TEXT = {
    "en": {
        "tagline": "Batch-translate subtitles and documents — timestamps, numbering and line breaks stay exactly as they were.",
        "features": "Features",
        "f_fast": "Fast: a full-length film (≈1,500 lines) is translated in about 12 seconds — lines are sent in batches",
        "f_subs": "Subtitles: SRT and VTT — cue numbers, timestamps, <i>tags</i> and line endings are preserved; UTF-8 output that Windows players read correctly",
        "f_docs": "Documents: TXT, Markdown, CSV, DOCX (body, tables, headers and footers) and PDF (saved as PDF or TXT)",
        "f_engines": "Engines: Google, MyMemory, DeepL API and LibreTranslate — if a service is rate-limited it automatically switches to another",
        "f_queue": "File queue with drag & drop, optional parallel processing, live progress and remaining time",
        "f_smart": "Skips files that are already in the target language; custom glossary (JSON/CSV) before or after translation",
        "f_ui": "Interface in 37 languages, light and dark themes with 6 accent colours; every setting is remembered",
        "f_cli": "Command line as well: `python translate_srt.py input.srt output.srt tr`",
        "screens": "Screenshots",
        "cap_main": "Main window",
        "cap_empty": "Empty queue — drop your files here",
        "cap_settings": "Settings",
        "cap_rtl": "Right-to-left languages",
        "install": "Install (Windows)",
        "i1": "Install [Python 3.10 or newer]({python}) and tick “Add python.exe to PATH”.",
        "i2": "Download the project ([ZIP]({zip})) or clone it, then install the dependencies:",
        "i3": "Double-click `run_app.bat` or `Subtitle PRO.pyw` — no console window stays open.",
        "usage": "How to use",
        "u1": "Add files with **Add...** or drag them into the window.",
        "u2": "Pick the target language and an engine (**Auto** is recommended).",
        "u3": "Press **▶ Start**. The result is saved next to the original, e.g. `movie.en.tr.srt`.",
        "u4": "Check the result — names and interjections such as “Ah!” are intentionally left unchanged.",
        "status": "Project status",
        "status_text": "Actively developed and covered by 270+ automated tests. Known issues and the roadmap are documented (in Turkish) in [KNOWN_ISSUES]({issues}) and [ROADMAP]({roadmap}).",
        "dev": "Development",
        "dev_text": "Architecture, tests and the translation guide: see the [main README]({main}#development).",
        "license": "License",
    },
    "tr": {
        "tagline": "Altyazıları ve belgeleri toplu çevir — zaman damgaları, numaralar ve satır yapısı olduğu gibi korunur.",
        "features": "Özellikler",
        "f_fast": "Hızlı: uzun metrajlı bir film (≈1.500 satır) yaklaşık 12 saniyede çevrilir — satırlar paketler hâlinde gönderilir",
        "f_subs": "Altyazılar: SRT ve VTT — sıra numaraları, zaman damgaları, <i>etiketler</i> ve satır sonları korunur; Windows oynatıcılarının doğru okuduğu UTF-8 çıktı",
        "f_docs": "Belgeler: TXT, Markdown, CSV, DOCX (gövde, tablolar, üst/alt bilgi) ve PDF (PDF ya da TXT olarak kaydedilir)",
        "f_engines": "Motorlar: Google, MyMemory, DeepL API ve LibreTranslate — bir servis engellenirse otomatik olarak diğerine geçer",
        "f_queue": "Sürükle-bırak destekli dosya kuyruğu, isteğe bağlı paralel işleme, canlı ilerleme ve kalan süre",
        "f_smart": "Zaten hedef dilde olan dosyaları atlar; çeviriden önce ya da sonra uygulanan özel sözlük (JSON/CSV)",
        "f_ui": "37 arayüz dili, 6 vurgu rengiyle açık ve koyu tema; tüm ayarlar hatırlanır",
        "f_cli": "Komut satırından da: `python translate_srt.py girdi.srt cikti.srt tr`",
        "screens": "Ekran görüntüleri",
        "cap_main": "Ana pencere",
        "cap_empty": "Boş kuyruk — dosyaları buraya bırakın",
        "cap_settings": "Ayarlar",
        "cap_rtl": "Sağdan sola diller",
        "install": "Kurulum (Windows)",
        "i1": "[Python 3.10 veya üstünü]({python}) kurun ve “Add python.exe to PATH” kutusunu işaretleyin.",
        "i2": "Projeyi indirin ([ZIP]({zip})) ya da klonlayın, ardından bağımlılıkları kurun:",
        "i3": "`run_app.bat` ya da `Subtitle PRO.pyw` dosyasına çift tıklayın — arkada konsol penceresi açık kalmaz.",
        "usage": "Kullanım",
        "u1": "**Ekle...** ile dosya seçin ya da dosyaları pencereye sürükleyin.",
        "u2": "Hedef dili ve motoru seçin (**Otomatik** önerilir).",
        "u3": "**▶ Başlat**'a basın. Sonuç orijinalin yanına kaydedilir, örn. `film.en.tr.srt`.",
        "u4": "Sonucu kontrol edin — isimler ve “Ah!” gibi ünlemler bilerek değiştirilmez.",
        "status": "Proje durumu",
        "status_text": "Aktif olarak geliştiriliyor, 270'ten fazla otomatik testle korunuyor. Bilinen sorunlar ve yol haritası: [KNOWN_ISSUES]({issues}) ve [ROADMAP]({roadmap}).",
        "dev": "Geliştirme",
        "dev_text": "Mimari, testler ve çeviri rehberi için [ana README]({main}#development) sayfasına bakın.",
        "license": "Lisans",
    },
    "de": {
        "tagline": "Untertitel und Dokumente stapelweise übersetzen — Zeitstempel, Nummerierung und Zeilenumbrüche bleiben exakt erhalten.",
        "features": "Funktionen",
        "f_fast": "Schnell: Ein ganzer Spielfilm (≈1.500 Zeilen) ist in etwa 12 Sekunden übersetzt — Zeilen werden gebündelt gesendet",
        "f_subs": "Untertitel: SRT und VTT — Nummern, Zeitstempel, <i>Tags</i> und Zeilenenden bleiben erhalten; UTF-8-Ausgabe, die Windows-Player korrekt lesen",
        "f_docs": "Dokumente: TXT, Markdown, CSV, DOCX (Text, Tabellen, Kopf- und Fußzeilen) und PDF (als PDF oder TXT gespeichert)",
        "f_engines": "Dienste: Google, MyMemory, DeepL API und LibreTranslate — wird ein Dienst gedrosselt, wird automatisch gewechselt",
        "f_queue": "Dateiwarteschlange mit Drag & Drop, optional parallele Verarbeitung, Live-Fortschritt und Restzeit",
        "f_smart": "Überspringt Dateien, die bereits in der Zielsprache sind; eigenes Glossar (JSON/CSV) vor oder nach der Übersetzung",
        "f_ui": "Oberfläche in 37 Sprachen, helles und dunkles Design mit 6 Akzentfarben; alle Einstellungen werden gespeichert",
        "f_cli": "Auch per Kommandozeile: `python translate_srt.py eingabe.srt ausgabe.srt de`",
        "screens": "Screenshots",
        "cap_main": "Hauptfenster",
        "cap_empty": "Leere Warteschlange — Dateien hier ablegen",
        "cap_settings": "Einstellungen",
        "cap_rtl": "Sprachen von rechts nach links",
        "install": "Installation (Windows)",
        "i1": "[Python 3.10 oder neuer]({python}) installieren und „Add python.exe to PATH“ ankreuzen.",
        "i2": "Projekt herunterladen ([ZIP]({zip})) oder klonen und die Abhängigkeiten installieren:",
        "i3": "`run_app.bat` oder `Subtitle PRO.pyw` doppelklicken — es bleibt kein Konsolenfenster offen.",
        "usage": "Verwendung",
        "u1": "Dateien mit **Hinzufügen...** wählen oder ins Fenster ziehen.",
        "u2": "Zielsprache und Dienst wählen (**Automatisch** wird empfohlen).",
        "u3": "**▶ Starten** drücken. Das Ergebnis wird neben dem Original gespeichert, z. B. `film.en.de.srt`.",
        "u4": "Ergebnis prüfen — Namen und Ausrufe wie „Ah!“ bleiben absichtlich unverändert.",
        "status": "Projektstatus",
        "status_text": "Wird aktiv entwickelt und durch über 270 automatisierte Tests abgesichert. Bekannte Probleme und Roadmap (auf Türkisch): [KNOWN_ISSUES]({issues}) und [ROADMAP]({roadmap}).",
        "dev": "Entwicklung",
        "dev_text": "Architektur, Tests und Übersetzungsleitfaden: siehe [Haupt-README]({main}#development).",
        "license": "Lizenz",
    },
    "fr": {
        "tagline": "Traduisez des sous-titres et des documents par lots — horodatages, numérotation et retours à la ligne restent intacts.",
        "features": "Fonctionnalités",
        "f_fast": "Rapide : un long métrage (≈1 500 lignes) est traduit en environ 12 secondes — les lignes sont envoyées par lots",
        "f_subs": "Sous-titres : SRT et VTT — numéros, horodatages, <i>balises</i> et fins de ligne sont conservés ; sortie UTF-8 lue correctement par les lecteurs Windows",
        "f_docs": "Documents : TXT, Markdown, CSV, DOCX (corps, tableaux, en-têtes et pieds de page) et PDF (enregistré en PDF ou TXT)",
        "f_engines": "Moteurs : Google, MyMemory, DeepL API et LibreTranslate — si un service est limité, l’application bascule automatiquement",
        "f_queue": "File de fichiers avec glisser-déposer, traitement parallèle optionnel, progression et temps restant en direct",
        "f_smart": "Ignore les fichiers déjà dans la langue cible ; glossaire personnalisé (JSON/CSV) avant ou après la traduction",
        "f_ui": "Interface en 37 langues, thèmes clair et sombre avec 6 couleurs d’accent ; tous les réglages sont mémorisés",
        "f_cli": "Aussi en ligne de commande : `python translate_srt.py entree.srt sortie.srt fr`",
        "screens": "Captures d’écran",
        "cap_main": "Fenêtre principale",
        "cap_empty": "File vide — déposez vos fichiers ici",
        "cap_settings": "Paramètres",
        "cap_rtl": "Langues de droite à gauche",
        "install": "Installation (Windows)",
        "i1": "Installez [Python 3.10 ou plus récent]({python}) et cochez « Add python.exe to PATH ».",
        "i2": "Téléchargez le projet ([ZIP]({zip})) ou clonez-le, puis installez les dépendances :",
        "i3": "Double-cliquez sur `run_app.bat` ou `Subtitle PRO.pyw` — aucune fenêtre de console ne reste ouverte.",
        "usage": "Utilisation",
        "u1": "Ajoutez des fichiers avec **Ajouter...** ou glissez-les dans la fenêtre.",
        "u2": "Choisissez la langue cible et un moteur (**Auto** est recommandé).",
        "u3": "Appuyez sur **▶ Démarrer**. Le résultat est enregistré à côté de l’original, p. ex. `film.en.fr.srt`.",
        "u4": "Vérifiez le résultat — les noms et interjections comme « Ah ! » restent volontairement inchangés.",
        "status": "État du projet",
        "status_text": "Développement actif, couvert par plus de 270 tests automatisés. Problèmes connus et feuille de route (en turc) : [KNOWN_ISSUES]({issues}) et [ROADMAP]({roadmap}).",
        "dev": "Développement",
        "dev_text": "Architecture, tests et guide de traduction : voir le [README principal]({main}#development).",
        "license": "Licence",
    },
    "es": {
        "tagline": "Traduce subtítulos y documentos por lotes — las marcas de tiempo, la numeración y los saltos de línea quedan intactos.",
        "features": "Características",
        "f_fast": "Rápido: una película completa (≈1.500 líneas) se traduce en unos 12 segundos — las líneas se envían por lotes",
        "f_subs": "Subtítulos: SRT y VTT — se conservan números, marcas de tiempo, <i>etiquetas</i> y finales de línea; salida UTF-8 que los reproductores de Windows leen bien",
        "f_docs": "Documentos: TXT, Markdown, CSV, DOCX (cuerpo, tablas, encabezados y pies) y PDF (guardado como PDF o TXT)",
        "f_engines": "Motores: Google, MyMemory, DeepL API y LibreTranslate — si un servicio se limita, cambia automáticamente a otro",
        "f_queue": "Cola de archivos con arrastrar y soltar, procesamiento en paralelo opcional, progreso y tiempo restante en vivo",
        "f_smart": "Omite los archivos que ya están en el idioma de destino; glosario propio (JSON/CSV) antes o después de traducir",
        "f_ui": "Interfaz en 37 idiomas, temas claro y oscuro con 6 colores de acento; se recuerdan todos los ajustes",
        "f_cli": "También por línea de comandos: `python translate_srt.py entrada.srt salida.srt es`",
        "screens": "Capturas de pantalla",
        "cap_main": "Ventana principal",
        "cap_empty": "Cola vacía — suelta tus archivos aquí",
        "cap_settings": "Ajustes",
        "cap_rtl": "Idiomas de derecha a izquierda",
        "install": "Instalación (Windows)",
        "i1": "Instala [Python 3.10 o posterior]({python}) y marca “Add python.exe to PATH”.",
        "i2": "Descarga el proyecto ([ZIP]({zip})) o clónalo y luego instala las dependencias:",
        "i3": "Haz doble clic en `run_app.bat` o `Subtitle PRO.pyw` — no queda ninguna ventana de consola abierta.",
        "usage": "Uso",
        "u1": "Añade archivos con **Añadir...** o arrástralos a la ventana.",
        "u2": "Elige el idioma de destino y un motor (se recomienda **Automático**).",
        "u3": "Pulsa **▶ Iniciar**. El resultado se guarda junto al original, p. ej. `pelicula.en.es.srt`.",
        "u4": "Revisa el resultado — los nombres e interjecciones como “¡Ah!” se dejan sin cambios a propósito.",
        "status": "Estado del proyecto",
        "status_text": "En desarrollo activo y cubierto por más de 270 pruebas automáticas. Problemas conocidos y hoja de ruta (en turco): [KNOWN_ISSUES]({issues}) y [ROADMAP]({roadmap}).",
        "dev": "Desarrollo",
        "dev_text": "Arquitectura, pruebas y guía de traducción: consulta el [README principal]({main}#development).",
        "license": "Licencia",
    },
    "it": {
        "tagline": "Traduci sottotitoli e documenti in blocco — timestamp, numerazione e a capo restano esattamente come sono.",
        "features": "Funzionalità",
        "f_fast": "Veloce: un film intero (≈1.500 righe) viene tradotto in circa 12 secondi — le righe vengono inviate a blocchi",
        "f_subs": "Sottotitoli: SRT e VTT — numeri, timestamp, <i>tag</i> e fine riga vengono mantenuti; output UTF-8 letto correttamente dai player di Windows",
        "f_docs": "Documenti: TXT, Markdown, CSV, DOCX (testo, tabelle, intestazioni e piè di pagina) e PDF (salvato come PDF o TXT)",
        "f_engines": "Motori: Google, MyMemory, DeepL API e LibreTranslate — se un servizio viene limitato passa automaticamente a un altro",
        "f_queue": "Coda di file con trascinamento, elaborazione parallela opzionale, avanzamento e tempo rimanente in tempo reale",
        "f_smart": "Salta i file già nella lingua di destinazione; glossario personalizzato (JSON/CSV) prima o dopo la traduzione",
        "f_ui": "Interfaccia in 37 lingue, tema chiaro e scuro con 6 colori principali; tutte le impostazioni vengono ricordate",
        "f_cli": "Anche da riga di comando: `python translate_srt.py input.srt output.srt it`",
        "screens": "Screenshot",
        "cap_main": "Finestra principale",
        "cap_empty": "Coda vuota — trascina qui i file",
        "cap_settings": "Impostazioni",
        "cap_rtl": "Lingue da destra a sinistra",
        "install": "Installazione (Windows)",
        "i1": "Installa [Python 3.10 o successivo]({python}) e spunta “Add python.exe to PATH”.",
        "i2": "Scarica il progetto ([ZIP]({zip})) o clonalo, poi installa le dipendenze:",
        "i3": "Fai doppio clic su `run_app.bat` o `Subtitle PRO.pyw` — nessuna finestra di console resta aperta.",
        "usage": "Come si usa",
        "u1": "Aggiungi file con **Aggiungi...** o trascinali nella finestra.",
        "u2": "Scegli la lingua di destinazione e un motore (si consiglia **Automatico**).",
        "u3": "Premi **▶ Avvia**. Il risultato viene salvato accanto all’originale, ad es. `film.en.it.srt`.",
        "u4": "Controlla il risultato — nomi e interiezioni come “Ah!” restano invariati di proposito.",
        "status": "Stato del progetto",
        "status_text": "In sviluppo attivo e coperto da oltre 270 test automatici. Problemi noti e roadmap (in turco): [KNOWN_ISSUES]({issues}) e [ROADMAP]({roadmap}).",
        "dev": "Sviluppo",
        "dev_text": "Architettura, test e guida alla traduzione: vedi il [README principale]({main}#development).",
        "license": "Licenza",
    },
    "pt": {
        "tagline": "Traduza legendas e documentos em lote — marcas de tempo, numeração e quebras de linha ficam exatamente como estavam.",
        "features": "Recursos",
        "f_fast": "Rápido: um filme inteiro (≈1.500 linhas) é traduzido em cerca de 12 segundos — as linhas são enviadas em lotes",
        "f_subs": "Legendas: SRT e VTT — números, marcas de tempo, <i>tags</i> e finais de linha são preservados; saída UTF-8 lida corretamente pelos players do Windows",
        "f_docs": "Documentos: TXT, Markdown, CSV, DOCX (corpo, tabelas, cabeçalhos e rodapés) e PDF (salvo como PDF ou TXT)",
        "f_engines": "Serviços: Google, MyMemory, DeepL API e LibreTranslate — se um serviço for limitado, troca automaticamente para outro",
        "f_queue": "Fila de arquivos com arrastar e soltar, processamento paralelo opcional, progresso e tempo restante ao vivo",
        "f_smart": "Ignora arquivos que já estão no idioma de destino; glossário próprio (JSON/CSV) antes ou depois da tradução",
        "f_ui": "Interface em 37 idiomas, temas claro e escuro com 6 cores de destaque; todas as configurações são lembradas",
        "f_cli": "Também pela linha de comando: `python translate_srt.py entrada.srt saida.srt pt`",
        "screens": "Capturas de tela",
        "cap_main": "Janela principal",
        "cap_empty": "Fila vazia — solte seus arquivos aqui",
        "cap_settings": "Configurações",
        "cap_rtl": "Idiomas da direita para a esquerda",
        "install": "Instalação (Windows)",
        "i1": "Instale o [Python 3.10 ou mais recente]({python}) e marque “Add python.exe to PATH”.",
        "i2": "Baixe o projeto ([ZIP]({zip})) ou clone-o e instale as dependências:",
        "i3": "Clique duas vezes em `run_app.bat` ou `Subtitle PRO.pyw` — nenhuma janela de console fica aberta.",
        "usage": "Como usar",
        "u1": "Adicione arquivos com **Adicionar...** ou arraste-os para a janela.",
        "u2": "Escolha o idioma de destino e um serviço (**Automático** é o recomendado).",
        "u3": "Pressione **▶ Iniciar**. O resultado é salvo ao lado do original, ex.: `filme.en.pt.srt`.",
        "u4": "Confira o resultado — nomes e interjeições como “Ah!” ficam inalterados de propósito.",
        "status": "Status do projeto",
        "status_text": "Em desenvolvimento ativo e coberto por mais de 270 testes automatizados. Problemas conhecidos e roteiro (em turco): [KNOWN_ISSUES]({issues}) e [ROADMAP]({roadmap}).",
        "dev": "Desenvolvimento",
        "dev_text": "Arquitetura, testes e guia de tradução: veja o [README principal]({main}#development).",
        "license": "Licença",
    },
    "nl": {
        "tagline": "Vertaal ondertitels en documenten in één keer — tijdcodes, nummering en regeleinden blijven precies zoals ze waren.",
        "features": "Functies",
        "f_fast": "Snel: een complete film (≈1.500 regels) is in ongeveer 12 seconden vertaald — regels worden in blokken verstuurd",
        "f_subs": "Ondertitels: SRT en VTT — nummers, tijdcodes, <i>tags</i> en regeleinden blijven behouden; UTF-8-uitvoer die Windows-spelers correct lezen",
        "f_docs": "Documenten: TXT, Markdown, CSV, DOCX (tekst, tabellen, kop- en voetteksten) en PDF (opgeslagen als PDF of TXT)",
        "f_engines": "Diensten: Google, MyMemory, DeepL API en LibreTranslate — wordt een dienst beperkt, dan wordt automatisch overgeschakeld",
        "f_queue": "Bestandswachtrij met slepen en neerzetten, optioneel parallel verwerken, live voortgang en resterende tijd",
        "f_smart": "Slaat bestanden over die al in de doeltaal zijn; eigen woordenlijst (JSON/CSV) voor of na het vertalen",
        "f_ui": "Interface in 37 talen, licht en donker thema met 6 accentkleuren; alle instellingen worden onthouden",
        "f_cli": "Ook via de opdrachtregel: `python translate_srt.py invoer.srt uitvoer.srt nl`",
        "screens": "Schermafbeeldingen",
        "cap_main": "Hoofdvenster",
        "cap_empty": "Lege wachtrij — sleep je bestanden hierheen",
        "cap_settings": "Instellingen",
        "cap_rtl": "Talen van rechts naar links",
        "install": "Installatie (Windows)",
        "i1": "Installeer [Python 3.10 of nieuwer]({python}) en vink “Add python.exe to PATH” aan.",
        "i2": "Download het project ([ZIP]({zip})) of kloon het en installeer daarna de afhankelijkheden:",
        "i3": "Dubbelklik op `run_app.bat` of `Subtitle PRO.pyw` — er blijft geen consolevenster open.",
        "usage": "Gebruik",
        "u1": "Voeg bestanden toe met **Toevoegen...** of sleep ze naar het venster.",
        "u2": "Kies de doeltaal en een dienst (**Automatisch** wordt aanbevolen).",
        "u3": "Druk op **▶ Starten**. Het resultaat wordt naast het origineel opgeslagen, bijv. `film.en.nl.srt`.",
        "u4": "Controleer het resultaat — namen en tussenwerpsels zoals “Ah!” blijven bewust ongewijzigd.",
        "status": "Projectstatus",
        "status_text": "Wordt actief ontwikkeld en afgedekt door meer dan 270 geautomatiseerde tests. Bekende problemen en roadmap (in het Turks): [KNOWN_ISSUES]({issues}) en [ROADMAP]({roadmap}).",
        "dev": "Ontwikkeling",
        "dev_text": "Architectuur, tests en vertaalgids: zie de [hoofd-README]({main}#development).",
        "license": "Licentie",
    },
    "pl": {
        "tagline": "Tłumacz napisy i dokumenty hurtowo — znaczniki czasu, numeracja i podziały wierszy pozostają dokładnie takie same.",
        "features": "Funkcje",
        "f_fast": "Szybko: cały film (≈1500 wierszy) zostaje przetłumaczony w około 12 sekund — wiersze są wysyłane paczkami",
        "f_subs": "Napisy: SRT i VTT — numery, znaczniki czasu, <i>tagi</i> i końce wierszy są zachowane; wynik w UTF-8 poprawnie odczytywany przez odtwarzacze w Windows",
        "f_docs": "Dokumenty: TXT, Markdown, CSV, DOCX (treść, tabele, nagłówki i stopki) oraz PDF (zapis jako PDF lub TXT)",
        "f_engines": "Usługi: Google, MyMemory, DeepL API i LibreTranslate — gdy usługa zostanie ograniczona, program automatycznie przełącza się na inną",
        "f_queue": "Kolejka plików z przeciąganiem i upuszczaniem, opcjonalne przetwarzanie równoległe, postęp i pozostały czas na żywo",
        "f_smart": "Pomija pliki, które są już w języku docelowym; własny słownik (JSON/CSV) przed lub po tłumaczeniu",
        "f_ui": "Interfejs w 37 językach, jasny i ciemny motyw z 6 kolorami akcentu; wszystkie ustawienia są zapamiętywane",
        "f_cli": "Także z wiersza poleceń: `python translate_srt.py wejscie.srt wyjscie.srt pl`",
        "screens": "Zrzuty ekranu",
        "cap_main": "Okno główne",
        "cap_empty": "Pusta kolejka — upuść tutaj pliki",
        "cap_settings": "Ustawienia",
        "cap_rtl": "Języki pisane od prawej do lewej",
        "install": "Instalacja (Windows)",
        "i1": "Zainstaluj [Pythona 3.10 lub nowszego]({python}) i zaznacz „Add python.exe to PATH”.",
        "i2": "Pobierz projekt ([ZIP]({zip})) lub sklonuj go, a następnie zainstaluj zależności:",
        "i3": "Kliknij dwukrotnie `run_app.bat` lub `Subtitle PRO.pyw` — nie zostaje otwarte żadne okno konsoli.",
        "usage": "Jak używać",
        "u1": "Dodaj pliki przyciskiem **Dodaj...** lub przeciągnij je do okna.",
        "u2": "Wybierz język docelowy i usługę (zalecane **Automatycznie**).",
        "u3": "Naciśnij **▶ Rozpocznij**. Wynik zapisuje się obok oryginału, np. `film.en.pl.srt`.",
        "u4": "Sprawdź wynik — imiona i wykrzyknienia takie jak „Ach!” celowo pozostają bez zmian.",
        "status": "Stan projektu",
        "status_text": "Aktywnie rozwijany i objęty ponad 270 testami automatycznymi. Znane problemy i plan rozwoju (po turecku): [KNOWN_ISSUES]({issues}) i [ROADMAP]({roadmap}).",
        "dev": "Rozwój",
        "dev_text": "Architektura, testy i przewodnik po tłumaczeniach: zobacz [główny README]({main}#development).",
        "license": "Licencja",
    },
    "sv": {
        "tagline": "Översätt undertexter och dokument i omgångar — tidskoder, numrering och radbrytningar förblir exakt som de var.",
        "features": "Funktioner",
        "f_fast": "Snabbt: en hel långfilm (≈1 500 rader) översätts på cirka 12 sekunder — raderna skickas i omgångar",
        "f_subs": "Undertexter: SRT och VTT — nummer, tidskoder, <i>taggar</i> och radslut bevaras; UTF-8-utdata som Windows-spelare läser korrekt",
        "f_docs": "Dokument: TXT, Markdown, CSV, DOCX (brödtext, tabeller, sidhuvuden och sidfötter) och PDF (sparas som PDF eller TXT)",
        "f_engines": "Tjänster: Google, MyMemory, DeepL API och LibreTranslate — om en tjänst begränsas byter programmet automatiskt",
        "f_queue": "Filkö med dra och släpp, valfri parallell bearbetning, förlopp och återstående tid i realtid",
        "f_smart": "Hoppar över filer som redan är på målspråket; egen ordlista (JSON/CSV) före eller efter översättningen",
        "f_ui": "Gränssnitt på 37 språk, ljust och mörkt tema med 6 accentfärger; alla inställningar sparas",
        "f_cli": "Även från kommandoraden: `python translate_srt.py in.srt ut.srt sv`",
        "screens": "Skärmbilder",
        "cap_main": "Huvudfönster",
        "cap_empty": "Tom kö — släpp dina filer här",
        "cap_settings": "Inställningar",
        "cap_rtl": "Språk som skrivs från höger till vänster",
        "install": "Installation (Windows)",
        "i1": "Installera [Python 3.10 eller senare]({python}) och kryssa i ”Add python.exe to PATH”.",
        "i2": "Ladda ner projektet ([ZIP]({zip})) eller klona det och installera sedan beroendena:",
        "i3": "Dubbelklicka på `run_app.bat` eller `Subtitle PRO.pyw` — inget konsolfönster blir kvar.",
        "usage": "Användning",
        "u1": "Lägg till filer med **Lägg till...** eller dra dem till fönstret.",
        "u2": "Välj målspråk och tjänst (**Automatiskt** rekommenderas).",
        "u3": "Tryck på **▶ Starta**. Resultatet sparas bredvid originalet, t.ex. `film.en.sv.srt`.",
        "u4": "Kontrollera resultatet — namn och interjektioner som ”Ah!” lämnas avsiktligt oförändrade.",
        "status": "Projektstatus",
        "status_text": "Utvecklas aktivt och täcks av över 270 automatiska tester. Kända problem och färdplan (på turkiska): [KNOWN_ISSUES]({issues}) och [ROADMAP]({roadmap}).",
        "dev": "Utveckling",
        "dev_text": "Arkitektur, tester och översättningsguide: se [huvud-README]({main}#development).",
        "license": "Licens",
    },
    "ru": {
        "tagline": "Пакетный перевод субтитров и документов — таймкоды, нумерация и переносы строк остаются в точности как были.",
        "features": "Возможности",
        "f_fast": "Быстро: полнометражный фильм (≈1500 строк) переводится примерно за 12 секунд — строки отправляются пакетами",
        "f_subs": "Субтитры: SRT и VTT — номера, таймкоды, <i>теги</i> и концы строк сохраняются; вывод в UTF-8, который правильно читают плееры Windows",
        "f_docs": "Документы: TXT, Markdown, CSV, DOCX (текст, таблицы, колонтитулы) и PDF (сохраняется как PDF или TXT)",
        "f_engines": "Сервисы: Google, MyMemory, DeepL API и LibreTranslate — если сервис ограничивает запросы, программа автоматически переключается на другой",
        "f_queue": "Очередь файлов с перетаскиванием, необязательная параллельная обработка, прогресс и оставшееся время в реальном времени",
        "f_smart": "Пропускает файлы, уже написанные на целевом языке; собственный глоссарий (JSON/CSV) до или после перевода",
        "f_ui": "Интерфейс на 37 языках, светлая и тёмная темы с 6 акцентными цветами; все настройки запоминаются",
        "f_cli": "Также из командной строки: `python translate_srt.py input.srt output.srt ru`",
        "screens": "Скриншоты",
        "cap_main": "Главное окно",
        "cap_empty": "Пустая очередь — перетащите файлы сюда",
        "cap_settings": "Настройки",
        "cap_rtl": "Языки с письмом справа налево",
        "install": "Установка (Windows)",
        "i1": "Установите [Python 3.10 или новее]({python}) и отметьте «Add python.exe to PATH».",
        "i2": "Скачайте проект ([ZIP]({zip})) или клонируйте его, затем установите зависимости:",
        "i3": "Дважды щёлкните `run_app.bat` или `Subtitle PRO.pyw` — окно консоли не остаётся открытым.",
        "usage": "Как пользоваться",
        "u1": "Добавьте файлы кнопкой **Добавить...** или перетащите их в окно.",
        "u2": "Выберите целевой язык и сервис (рекомендуется **Авто**).",
        "u3": "Нажмите **▶ Начать**. Результат сохраняется рядом с оригиналом, например `film.en.ru.srt`.",
        "u4": "Проверьте результат — имена и междометия вроде «Ах!» намеренно не изменяются.",
        "status": "Состояние проекта",
        "status_text": "Активно развивается и покрыт более чем 270 автотестами. Известные проблемы и план развития (на турецком): [KNOWN_ISSUES]({issues}) и [ROADMAP]({roadmap}).",
        "dev": "Разработка",
        "dev_text": "Архитектура, тесты и руководство по переводу: см. [основной README]({main}#development).",
        "license": "Лицензия",
    },
    "uk": {
        "tagline": "Пакетний переклад субтитрів і документів — таймкоди, нумерація та переноси рядків залишаються точно такими, як були.",
        "features": "Можливості",
        "f_fast": "Швидко: повнометражний фільм (≈1500 рядків) перекладається приблизно за 12 секунд — рядки надсилаються пакетами",
        "f_subs": "Субтитри: SRT і VTT — номери, таймкоди, <i>теги</i> й кінці рядків зберігаються; вивід у UTF-8, який правильно читають плеєри Windows",
        "f_docs": "Документи: TXT, Markdown, CSV, DOCX (текст, таблиці, колонтитули) і PDF (зберігається як PDF або TXT)",
        "f_engines": "Сервіси: Google, MyMemory, DeepL API і LibreTranslate — якщо сервіс обмежує запити, програма автоматично перемикається на інший",
        "f_queue": "Черга файлів із перетягуванням, необов’язкова паралельна обробка, поступ і залишок часу в реальному часі",
        "f_smart": "Пропускає файли, які вже написані цільовою мовою; власний глосарій (JSON/CSV) до або після перекладу",
        "f_ui": "Інтерфейс 37 мовами, світла й темна теми з 6 акцентними кольорами; усі налаштування запам’ятовуються",
        "f_cli": "Також із командного рядка: `python translate_srt.py input.srt output.srt uk`",
        "screens": "Знімки екрана",
        "cap_main": "Головне вікно",
        "cap_empty": "Порожня черга — перетягніть файли сюди",
        "cap_settings": "Налаштування",
        "cap_rtl": "Мови з письмом справа наліво",
        "install": "Встановлення (Windows)",
        "i1": "Встановіть [Python 3.10 або новіший]({python}) і позначте «Add python.exe to PATH».",
        "i2": "Завантажте проєкт ([ZIP]({zip})) або клонуйте його, потім встановіть залежності:",
        "i3": "Двічі клацніть `run_app.bat` або `Subtitle PRO.pyw` — вікно консолі не залишається відкритим.",
        "usage": "Як користуватися",
        "u1": "Додайте файли кнопкою **Додати...** або перетягніть їх у вікно.",
        "u2": "Виберіть цільову мову та сервіс (рекомендовано **Авто**).",
        "u3": "Натисніть **▶ Почати**. Результат зберігається поруч з оригіналом, наприклад `film.en.uk.srt`.",
        "u4": "Перевірте результат — імена та вигуки на кшталт «Ах!» навмисно не змінюються.",
        "status": "Стан проєкту",
        "status_text": "Активно розвивається й покритий понад 270 автотестами. Відомі проблеми та план розвитку (турецькою): [KNOWN_ISSUES]({issues}) і [ROADMAP]({roadmap}).",
        "dev": "Розробка",
        "dev_text": "Архітектура, тести та посібник із перекладу: див. [основний README]({main}#development).",
        "license": "Ліцензія",
    },
    "ar": {
        "tagline": "ترجمة الترجمات المرئية والمستندات دفعةً واحدة — تبقى الطوابع الزمنية والترقيم وفواصل الأسطر كما هي تمامًا.",
        "features": "الميزات",
        "f_fast": "سريع: يُترجَم فيلم كامل (≈1500 سطر) في نحو 12 ثانية — تُرسَل الأسطر على دفعات",
        "f_subs": "ملفات الترجمة: SRT وVTT — تُحفَظ الأرقام والطوابع الزمنية و<i>الوسوم</i> ونهايات الأسطر؛ مخرجات UTF-8 تقرؤها مشغلات Windows بشكل صحيح",
        "f_docs": "المستندات: TXT وMarkdown وCSV وDOCX (النص والجداول والرؤوس والتذييلات) وPDF (يُحفَظ بصيغة PDF أو TXT)",
        "f_engines": "الخدمات: Google وMyMemory وDeepL API وLibreTranslate — إذا قُيِّدت خدمة ينتقل البرنامج تلقائيًا إلى أخرى",
        "f_queue": "قائمة انتظار للملفات مع السحب والإفلات، ومعالجة متوازية اختيارية، وتقدّم ووقت متبقٍ مباشر",
        "f_smart": "يتخطى الملفات المكتوبة أصلًا باللغة الهدف؛ مسرد مخصص (JSON/CSV) قبل الترجمة أو بعدها",
        "f_ui": "واجهة بـ 37 لغة، وسمتان فاتحة وداكنة مع 6 ألوان تمييز؛ تُحفَظ جميع الإعدادات",
        "f_cli": "ومن سطر الأوامر أيضًا: `python translate_srt.py input.srt output.srt ar`",
        "screens": "لقطات الشاشة",
        "cap_main": "النافذة الرئيسية",
        "cap_empty": "قائمة فارغة — أفلت ملفاتك هنا",
        "cap_settings": "الإعدادات",
        "cap_rtl": "اللغات التي تُكتب من اليمين إلى اليسار",
        "install": "التثبيت (Windows)",
        "i1": "ثبّت [Python 3.10 أو أحدث]({python}) وحدِّد خيار “Add python.exe to PATH”.",
        "i2": "نزّل المشروع ([ZIP]({zip})) أو انسخه، ثم ثبّت الاعتماديات:",
        "i3": "انقر نقرًا مزدوجًا على `run_app.bat` أو `Subtitle PRO.pyw` — لا تبقى أي نافذة طرفية مفتوحة.",
        "usage": "طريقة الاستخدام",
        "u1": "أضف الملفات عبر **إضافة...** أو اسحبها إلى النافذة.",
        "u2": "اختر اللغة الهدف وخدمة الترجمة (يُنصح بـ **تلقائي**).",
        "u3": "اضغط **▶ بدء**. تُحفَظ النتيجة بجانب الملف الأصلي، مثل `film.en.ar.srt`.",
        "u4": "راجع النتيجة — تُترك الأسماء وأدوات التعجب مثل “آه!” دون تغيير عن قصد.",
        "status": "حالة المشروع",
        "status_text": "قيد التطوير النشط ومغطى بأكثر من 270 اختبارًا آليًا. المشكلات المعروفة وخطة العمل (بالتركية): [KNOWN_ISSUES]({issues}) و[ROADMAP]({roadmap}).",
        "dev": "التطوير",
        "dev_text": "البنية والاختبارات ودليل الترجمة: راجع [ملف README الرئيسي]({main}#development).",
        "license": "الترخيص",
    },
    "fa": {
        "tagline": "ترجمهٔ گروهی زیرنویس‌ها و اسناد — زمان‌بندی، شماره‌گذاری و شکست خطوط دقیقاً همان‌طور که بودند باقی می‌مانند.",
        "features": "ویژگی‌ها",
        "f_fast": "سریع: یک فیلم کامل (≈۱۵۰۰ خط) در حدود ۱۲ ثانیه ترجمه می‌شود — خطوط به‌صورت دسته‌ای ارسال می‌شوند",
        "f_subs": "زیرنویس‌ها: SRT و VTT — شماره‌ها، زمان‌بندی‌ها، <i>برچسب‌ها</i> و پایان خطوط حفظ می‌شوند؛ خروجی UTF-8 که پخش‌کننده‌های Windows درست می‌خوانند",
        "f_docs": "اسناد: TXT، Markdown، CSV، DOCX (متن، جدول‌ها، سرصفحه و پاصفحه) و PDF (ذخیره به‌صورت PDF یا TXT)",
        "f_engines": "سرویس‌ها: Google، MyMemory، DeepL API و LibreTranslate — اگر سرویسی محدود شود، برنامه خودکار به سرویس دیگری می‌رود",
        "f_queue": "صف فایل با کشیدن و رها کردن، پردازش موازی اختیاری، پیشرفت و زمان باقی‌مانده به‌صورت زنده",
        "f_smart": "فایل‌هایی را که از قبل به زبان مقصد هستند رد می‌کند؛ واژه‌نامهٔ سفارشی (JSON/CSV) پیش یا پس از ترجمه",
        "f_ui": "رابط کاربری به ۳۷ زبان، پوستهٔ روشن و تیره با ۶ رنگ تأکیدی؛ همهٔ تنظیمات به خاطر سپرده می‌شوند",
        "f_cli": "از خط فرمان هم: `python translate_srt.py input.srt output.srt fa`",
        "screens": "تصاویر صفحه",
        "cap_main": "پنجرهٔ اصلی",
        "cap_empty": "صف خالی — فایل‌ها را اینجا رها کنید",
        "cap_settings": "تنظیمات",
        "cap_rtl": "زبان‌های راست‌به‌چپ",
        "install": "نصب (Windows)",
        "i1": "[Python 3.10 یا جدیدتر]({python}) را نصب کنید و گزینهٔ «Add python.exe to PATH» را علامت بزنید.",
        "i2": "پروژه را دانلود کنید ([ZIP]({zip})) یا کلون کنید، سپس وابستگی‌ها را نصب کنید:",
        "i3": "روی `run_app.bat` یا `Subtitle PRO.pyw` دوبار کلیک کنید — هیچ پنجرهٔ کنسولی باز نمی‌ماند.",
        "usage": "نحوهٔ استفاده",
        "u1": "فایل‌ها را با **افزودن...** اضافه کنید یا به داخل پنجره بکشید.",
        "u2": "زبان مقصد و سرویس را انتخاب کنید (**خودکار** پیشنهاد می‌شود).",
        "u3": "**▶ شروع** را بزنید. نتیجه کنار فایل اصلی ذخیره می‌شود، مثلاً `film.en.fa.srt`.",
        "u4": "نتیجه را بررسی کنید — نام‌ها و صوت‌هایی مانند «آه!» عمداً تغییر نمی‌کنند.",
        "status": "وضعیت پروژه",
        "status_text": "در حال توسعهٔ فعال و تحت پوشش بیش از ۲۷۰ آزمون خودکار. مشکلات شناخته‌شده و نقشهٔ راه (به ترکی): [KNOWN_ISSUES]({issues}) و [ROADMAP]({roadmap}).",
        "dev": "توسعه",
        "dev_text": "معماری، آزمون‌ها و راهنمای ترجمه: [README اصلی]({main}#development) را ببینید.",
        "license": "مجوز",
    },
    "hi": {
        "tagline": "उपशीर्षक और दस्तावेज़ एक साथ अनुवाद करें — टाइमस्टैम्प, क्रमांक और पंक्ति-विराम बिल्कुल वैसे ही रहते हैं।",
        "features": "सुविधाएँ",
        "f_fast": "तेज़: पूरी फ़िल्म (≈1,500 पंक्तियाँ) लगभग 12 सेकंड में अनुवादित होती है — पंक्तियाँ बैच में भेजी जाती हैं",
        "f_subs": "उपशीर्षक: SRT और VTT — क्रमांक, टाइमस्टैम्प, <i>टैग</i> और पंक्ति-अंत सुरक्षित रहते हैं; UTF-8 आउटपुट जिसे Windows प्लेयर सही पढ़ते हैं",
        "f_docs": "दस्तावेज़: TXT, Markdown, CSV, DOCX (मुख्य पाठ, तालिकाएँ, हेडर और फ़ुटर) और PDF (PDF या TXT के रूप में सहेजा जाता है)",
        "f_engines": "सेवाएँ: Google, MyMemory, DeepL API और LibreTranslate — कोई सेवा सीमित होने पर अपने-आप दूसरी सेवा पर चला जाता है",
        "f_queue": "ड्रैग-एंड-ड्रॉप वाली फ़ाइल कतार, वैकल्पिक समानांतर प्रोसेसिंग, लाइव प्रगति और शेष समय",
        "f_smart": "जो फ़ाइलें पहले से लक्ष्य भाषा में हैं उन्हें छोड़ देता है; अनुवाद से पहले या बाद में अपनी शब्दावली (JSON/CSV)",
        "f_ui": "37 भाषाओं में इंटरफ़ेस, 6 एक्सेंट रंगों के साथ लाइट और डार्क थीम; सभी सेटिंग्स याद रखी जाती हैं",
        "f_cli": "कमांड लाइन से भी: `python translate_srt.py input.srt output.srt hi`",
        "screens": "स्क्रीनशॉट",
        "cap_main": "मुख्य विंडो",
        "cap_empty": "खाली कतार — अपनी फ़ाइलें यहाँ छोड़ें",
        "cap_settings": "सेटिंग्स",
        "cap_rtl": "दाएँ से बाएँ लिखी जाने वाली भाषाएँ",
        "install": "इंस्टॉलेशन (Windows)",
        "i1": "[Python 3.10 या नया]({python}) इंस्टॉल करें और “Add python.exe to PATH” चुनें।",
        "i2": "प्रोजेक्ट डाउनलोड करें ([ZIP]({zip})) या क्लोन करें, फिर निर्भरताएँ इंस्टॉल करें:",
        "i3": "`run_app.bat` या `Subtitle PRO.pyw` पर डबल-क्लिक करें — कोई कंसोल विंडो खुली नहीं रहती।",
        "usage": "उपयोग कैसे करें",
        "u1": "**जोड़ें...** से फ़ाइलें जोड़ें या उन्हें विंडो में खींचें।",
        "u2": "लक्ष्य भाषा और सेवा चुनें (**स्वचालित** की सलाह दी जाती है)।",
        "u3": "**▶ शुरू करें** दबाएँ। परिणाम मूल फ़ाइल के पास सहेजा जाता है, जैसे `film.en.hi.srt`।",
        "u4": "परिणाम जाँचें — नाम और “आह!” जैसे विस्मयादिबोधक जानबूझकर नहीं बदले जाते।",
        "status": "प्रोजेक्ट की स्थिति",
        "status_text": "सक्रिय रूप से विकसित और 270 से अधिक स्वचालित परीक्षणों से सुरक्षित। ज्ञात समस्याएँ और रोडमैप (तुर्की में): [KNOWN_ISSUES]({issues}) और [ROADMAP]({roadmap})।",
        "dev": "विकास",
        "dev_text": "आर्किटेक्चर, परीक्षण और अनुवाद मार्गदर्शिका: [मुख्य README]({main}#development) देखें।",
        "license": "लाइसेंस",
    },
    "ja": {
        "tagline": "字幕とドキュメントを一括翻訳 — タイムスタンプ、番号、改行はそのまま保たれます。",
        "features": "特長",
        "f_fast": "高速：映画1本分（約1,500行）を約12秒で翻訳 — 行はまとめて送信されます",
        "f_subs": "字幕：SRT と VTT — 番号、タイムスタンプ、<i>タグ</i>、改行コードを保持。Windows のプレーヤーで正しく読める UTF-8 で出力",
        "f_docs": "ドキュメント：TXT、Markdown、CSV、DOCX（本文、表、ヘッダー・フッター）、PDF（PDF または TXT で保存）",
        "f_engines": "翻訳サービス：Google、MyMemory、DeepL API、LibreTranslate — 制限を受けると自動で別のサービスに切り替え",
        "f_queue": "ドラッグ＆ドロップ対応のファイルキュー、並列処理（任意）、リアルタイムの進捗と残り時間",
        "f_smart": "すでに翻訳先の言語で書かれたファイルはスキップ。翻訳の前または後に適用するカスタム用語集（JSON/CSV）",
        "f_ui": "37言語の UI、6種類のアクセントカラーを選べるライト/ダークテーマ。設定はすべて保存されます",
        "f_cli": "コマンドラインでも：`python translate_srt.py input.srt output.srt ja`",
        "screens": "スクリーンショット",
        "cap_main": "メインウィンドウ",
        "cap_empty": "空のキュー — ここにファイルをドロップ",
        "cap_settings": "設定",
        "cap_rtl": "右から左に書く言語",
        "install": "インストール（Windows）",
        "i1": "[Python 3.10 以降]({python})をインストールし、「Add python.exe to PATH」にチェックを入れます。",
        "i2": "プロジェクトをダウンロード（[ZIP]({zip})）またはクローンし、依存関係をインストールします：",
        "i3": "`run_app.bat` または `Subtitle PRO.pyw` をダブルクリック — コンソールウィンドウは残りません。",
        "usage": "使い方",
        "u1": "**追加...** でファイルを選ぶか、ウィンドウにドラッグします。",
        "u2": "翻訳先の言語とサービスを選びます（**自動** がおすすめ）。",
        "u3": "**▶ 開始** を押します。結果は元のファイルの隣に保存されます（例：`film.en.ja.srt`）。",
        "u4": "結果を確認します — 人名や「Ah!」のような感嘆詞は意図的にそのまま残ります。",
        "status": "プロジェクトの状況",
        "status_text": "活発に開発中で、270 以上の自動テストで保護されています。既知の問題とロードマップ（トルコ語）：[KNOWN_ISSUES]({issues})、[ROADMAP]({roadmap})。",
        "dev": "開発",
        "dev_text": "アーキテクチャ、テスト、翻訳ガイドは[メインの README]({main}#development)をご覧ください。",
        "license": "ライセンス",
    },
    "ko": {
        "tagline": "자막과 문서를 한 번에 번역 — 타임스탬프, 번호, 줄바꿈이 그대로 유지됩니다.",
        "features": "기능",
        "f_fast": "빠름: 영화 한 편(약 1,500줄)을 약 12초 만에 번역 — 줄을 묶어서 전송합니다",
        "f_subs": "자막: SRT와 VTT — 번호, 타임스탬프, <i>태그</i>, 줄 끝을 유지하며 Windows 플레이어가 올바르게 읽는 UTF-8로 저장",
        "f_docs": "문서: TXT, Markdown, CSV, DOCX(본문, 표, 머리글/바닥글), PDF(PDF 또는 TXT로 저장)",
        "f_engines": "번역 서비스: Google, MyMemory, DeepL API, LibreTranslate — 서비스가 제한되면 자동으로 다른 서비스로 전환",
        "f_queue": "끌어서 놓기를 지원하는 파일 대기열, 선택적 병렬 처리, 실시간 진행률과 남은 시간",
        "f_smart": "이미 대상 언어로 된 파일은 건너뜀. 번역 전이나 후에 적용하는 사용자 용어집(JSON/CSV)",
        "f_ui": "37개 언어 UI, 6가지 강조 색이 있는 밝은/어두운 테마. 모든 설정이 저장됩니다",
        "f_cli": "명령줄에서도: `python translate_srt.py input.srt output.srt ko`",
        "screens": "스크린샷",
        "cap_main": "메인 창",
        "cap_empty": "빈 대기열 — 여기에 파일을 놓으세요",
        "cap_settings": "설정",
        "cap_rtl": "오른쪽에서 왼쪽으로 쓰는 언어",
        "install": "설치 (Windows)",
        "i1": "[Python 3.10 이상]({python})을 설치하고 “Add python.exe to PATH”를 체크하세요.",
        "i2": "프로젝트를 다운로드([ZIP]({zip}))하거나 클론한 뒤 의존성을 설치하세요:",
        "i3": "`run_app.bat` 또는 `Subtitle PRO.pyw`를 더블클릭하세요 — 콘솔 창이 남지 않습니다.",
        "usage": "사용 방법",
        "u1": "**추가...**로 파일을 추가하거나 창으로 끌어 놓으세요.",
        "u2": "대상 언어와 번역 서비스를 고르세요(**자동** 권장).",
        "u3": "**▶ 시작**을 누르세요. 결과는 원본 옆에 저장됩니다. 예: `film.en.ko.srt`",
        "u4": "결과를 확인하세요 — 이름과 “Ah!” 같은 감탄사는 일부러 그대로 둡니다.",
        "status": "프로젝트 상태",
        "status_text": "활발히 개발 중이며 270개 이상의 자동 테스트로 검증됩니다. 알려진 문제와 로드맵(터키어): [KNOWN_ISSUES]({issues}), [ROADMAP]({roadmap}).",
        "dev": "개발",
        "dev_text": "아키텍처, 테스트, 번역 가이드는 [메인 README]({main}#development)를 참고하세요.",
        "license": "라이선스",
    },
    "zh": {
        "tagline": "批量翻译字幕和文档 — 时间轴、编号和换行完全保持不变。",
        "features": "功能",
        "f_fast": "快速：一整部电影（约 1,500 行）大约 12 秒即可翻译完成 — 按批发送多行",
        "f_subs": "字幕：SRT 和 VTT — 保留编号、时间轴、<i>标签</i>和换行符；输出 Windows 播放器能正确读取的 UTF-8",
        "f_docs": "文档：TXT、Markdown、CSV、DOCX（正文、表格、页眉页脚）和 PDF（保存为 PDF 或 TXT）",
        "f_engines": "翻译服务：Google、MyMemory、DeepL API 和 LibreTranslate — 某个服务被限流时会自动切换到其他服务",
        "f_queue": "支持拖放的文件队列，可选并行处理，实时显示进度和剩余时间",
        "f_smart": "自动跳过已是目标语言的文件；可在翻译前或翻译后应用自定义术语表（JSON/CSV）",
        "f_ui": "37 种界面语言，浅色和深色主题，6 种强调色；所有设置都会被记住",
        "f_cli": "也可以使用命令行：`python translate_srt.py input.srt output.srt zh-CN`",
        "screens": "截图",
        "cap_main": "主窗口",
        "cap_empty": "空队列 — 把文件拖到这里",
        "cap_settings": "设置",
        "cap_rtl": "从右到左书写的语言",
        "install": "安装（Windows）",
        "i1": "安装 [Python 3.10 或更高版本]({python})，并勾选“Add python.exe to PATH”。",
        "i2": "下载项目（[ZIP]({zip})）或克隆仓库，然后安装依赖：",
        "i3": "双击 `run_app.bat` 或 `Subtitle PRO.pyw` — 不会留下控制台窗口。",
        "usage": "使用方法",
        "u1": "点击 **添加...** 选择文件，或直接把文件拖进窗口。",
        "u2": "选择目标语言和翻译服务（推荐 **自动**）。",
        "u3": "点击 **▶ 开始**。结果保存在原文件旁边，例如 `film.en.zh-CN.srt`。",
        "u4": "检查结果 — 人名和“Ah!”之类的感叹词会刻意保持原样。",
        "status": "项目状态",
        "status_text": "正在积极开发，并由 270 多个自动化测试保障。已知问题和路线图（土耳其语）：[KNOWN_ISSUES]({issues}) 和 [ROADMAP]({roadmap})。",
        "dev": "开发",
        "dev_text": "架构、测试和翻译指南：请参阅[主 README]({main}#development)。",
        "license": "许可证",
    },
    "id": {
        "tagline": "Terjemahkan subtitle dan dokumen sekaligus — stempel waktu, penomoran, dan jeda baris tetap persis seperti semula.",
        "features": "Fitur",
        "f_fast": "Cepat: satu film penuh (≈1.500 baris) diterjemahkan dalam sekitar 12 detik — baris dikirim per kelompok",
        "f_subs": "Subtitle: SRT dan VTT — nomor, stempel waktu, <i>tag</i>, dan akhir baris dipertahankan; keluaran UTF-8 yang dibaca dengan benar oleh pemutar Windows",
        "f_docs": "Dokumen: TXT, Markdown, CSV, DOCX (isi, tabel, header dan footer) serta PDF (disimpan sebagai PDF atau TXT)",
        "f_engines": "Layanan: Google, MyMemory, DeepL API, dan LibreTranslate — jika satu layanan dibatasi, aplikasi otomatis beralih ke layanan lain",
        "f_queue": "Antrean berkas dengan seret dan lepas, pemrosesan paralel opsional, kemajuan dan sisa waktu secara langsung",
        "f_smart": "Melewati berkas yang sudah dalam bahasa tujuan; glosarium sendiri (JSON/CSV) sebelum atau sesudah penerjemahan",
        "f_ui": "Antarmuka dalam 37 bahasa, tema terang dan gelap dengan 6 warna aksen; semua pengaturan diingat",
        "f_cli": "Juga lewat baris perintah: `python translate_srt.py input.srt output.srt id`",
        "screens": "Tangkapan layar",
        "cap_main": "Jendela utama",
        "cap_empty": "Antrean kosong — letakkan berkas di sini",
        "cap_settings": "Pengaturan",
        "cap_rtl": "Bahasa yang ditulis dari kanan ke kiri",
        "install": "Instalasi (Windows)",
        "i1": "Instal [Python 3.10 atau lebih baru]({python}) dan centang “Add python.exe to PATH”.",
        "i2": "Unduh proyek ([ZIP]({zip})) atau kloning, lalu instal dependensinya:",
        "i3": "Klik dua kali `run_app.bat` atau `Subtitle PRO.pyw` — tidak ada jendela konsol yang tertinggal.",
        "usage": "Cara menggunakan",
        "u1": "Tambahkan berkas dengan **Tambah...** atau seret ke jendela.",
        "u2": "Pilih bahasa tujuan dan layanan (**Otomatis** disarankan).",
        "u3": "Tekan **▶ Mulai**. Hasil disimpan di samping berkas asli, mis. `film.en.id.srt`.",
        "u4": "Periksa hasilnya — nama dan seruan seperti “Ah!” sengaja dibiarkan tidak berubah.",
        "status": "Status proyek",
        "status_text": "Dikembangkan secara aktif dan dilindungi lebih dari 270 pengujian otomatis. Masalah yang diketahui dan peta jalan (bahasa Turki): [KNOWN_ISSUES]({issues}) dan [ROADMAP]({roadmap}).",
        "dev": "Pengembangan",
        "dev_text": "Arsitektur, pengujian, dan panduan terjemahan: lihat [README utama]({main}#development).",
        "license": "Lisensi",
    },
    "vi": {
        "tagline": "Dịch hàng loạt phụ đề và tài liệu — mốc thời gian, số thứ tự và ngắt dòng được giữ nguyên.",
        "features": "Tính năng",
        "f_fast": "Nhanh: một bộ phim đầy đủ (≈1.500 dòng) được dịch trong khoảng 12 giây — các dòng được gửi theo lô",
        "f_subs": "Phụ đề: SRT và VTT — giữ nguyên số thứ tự, mốc thời gian, <i>thẻ</i> và ký tự xuống dòng; xuất UTF-8 mà trình phát trên Windows đọc đúng",
        "f_docs": "Tài liệu: TXT, Markdown, CSV, DOCX (nội dung, bảng, đầu trang và chân trang) và PDF (lưu dưới dạng PDF hoặc TXT)",
        "f_engines": "Dịch vụ: Google, MyMemory, DeepL API và LibreTranslate — nếu một dịch vụ bị giới hạn, ứng dụng tự động chuyển sang dịch vụ khác",
        "f_queue": "Hàng đợi tệp hỗ trợ kéo thả, xử lý song song tùy chọn, hiển thị tiến độ và thời gian còn lại theo thời gian thực",
        "f_smart": "Bỏ qua tệp đã ở ngôn ngữ đích; bảng thuật ngữ riêng (JSON/CSV) áp dụng trước hoặc sau khi dịch",
        "f_ui": "Giao diện 37 ngôn ngữ, giao diện sáng và tối với 6 màu nhấn; mọi cài đặt đều được ghi nhớ",
        "f_cli": "Cũng dùng được từ dòng lệnh: `python translate_srt.py input.srt output.srt vi`",
        "screens": "Ảnh chụp màn hình",
        "cap_main": "Cửa sổ chính",
        "cap_empty": "Hàng đợi trống — thả tệp vào đây",
        "cap_settings": "Cài đặt",
        "cap_rtl": "Ngôn ngữ viết từ phải sang trái",
        "install": "Cài đặt (Windows)",
        "i1": "Cài [Python 3.10 trở lên]({python}) và đánh dấu “Add python.exe to PATH”.",
        "i2": "Tải dự án ([ZIP]({zip})) hoặc sao chép kho mã, rồi cài các thư viện phụ thuộc:",
        "i3": "Nhấp đúp `run_app.bat` hoặc `Subtitle PRO.pyw` — không còn cửa sổ console nào mở.",
        "usage": "Cách sử dụng",
        "u1": "Thêm tệp bằng **Thêm...** hoặc kéo chúng vào cửa sổ.",
        "u2": "Chọn ngôn ngữ đích và dịch vụ (khuyên dùng **Tự động**).",
        "u3": "Nhấn **▶ Bắt đầu**. Kết quả được lưu cạnh tệp gốc, ví dụ `film.en.vi.srt`.",
        "u4": "Kiểm tra kết quả — tên riêng và thán từ như “Ah!” được cố ý giữ nguyên.",
        "status": "Tình trạng dự án",
        "status_text": "Đang được phát triển tích cực và được bảo vệ bởi hơn 270 kiểm thử tự động. Vấn đề đã biết và lộ trình (tiếng Thổ Nhĩ Kỳ): [KNOWN_ISSUES]({issues}) và [ROADMAP]({roadmap}).",
        "dev": "Phát triển",
        "dev_text": "Kiến trúc, kiểm thử và hướng dẫn dịch: xem [README chính]({main}#development).",
        "license": "Giấy phép",
    },
}

DEVELOPMENT = """## 🛠️ Development

### Run from source

```bash
python -m venv .venv
.venv\\Scripts\\python -m pip install -r requirements.txt tkinterdnd2 langdetect
.venv\\Scripts\\python translate_srt.py                      # GUI
.venv\\Scripts\\python translate_srt.py in.srt out.tr.srt tr  # CLI
```

| Optional package | Used for |
|---|---|
| `tkinterdnd2` | drag & drop |
| `langdetect` | skipping files already in the target language, preview language hint |
| `python-docx`, `docx2txt` | DOCX |
| `pdfminer.six`, `reportlab` | reading / writing PDF |

API keys for DeepL / LibreTranslate go into environment variables (`DEEPL_API_KEY`, `LIBRE_URL`, `LIBRE_API_KEY`)
or `settings.json` (see `settings.example.json`).

### How translation works

```
file -> lines -> unique texts (deduplicated)
     -> Google JSON endpoint, many lines per request (bisected if Google merges lines)
     -> failures: Google per line -> MyMemory -> recovery rounds
     -> each endpoint gets a 10-minute circuit breaker after HTTP 429
     -> translations put back in place; numbers, timestamps, whitespace and CRLF untouched
```

### Project layout

```
translate_srt.py        app: GUI (Tkinter, own design system) + CLI + translation engine
ui_translations.json    UI strings, 37 languages
lang_names.json         target-language names in every UI language
run_app.bat             launcher without a console window (also: "Subtitle PRO.pyw")
tests/                  pytest suite (offline; fake engines, real GUI, real DOCX/PDF)
tools/
  ui_audit.py           opens the real GUI in every language, reports untranslated / clipped widgets
  i18n_sync.py          syncs ui_translations.json with the source, fills missing strings
  i18n_overrides.json   hand-checked terms where machine translation picks the wrong sense
  make_readmes.py       generates these READMEs (20 languages)
  readme_shots.py       README screenshots
  benchmark.py          offline request-count benchmark
docs/                   KNOWN_ISSUES, TESTING, ROADMAP (Turkish), screenshots
```

### Tests

```bash
.venv\\Scripts\\python -m pip install -r requirements-dev.txt
.venv\\Scripts\\python -m pytest            # offline, ~35 s
.venv\\Scripts\\python -m pytest -m network # optional live checks
```

Known bugs are recorded as `xfail(strict=True)`: once a bug is fixed the test reports XPASS and CI goes red until
the marker is removed — the test suite doubles as the bug list. See [docs/TESTING.md](docs/TESTING.md).

### Translations

Add UI text with `self._tr("English text")`, then run `python tools/i18n_sync.py --fill` and
`python tools/ui_audit.py`. Wrong term in your language? Add it to `tools/make_i18n_overrides.py`.
README texts live in `tools/make_readmes.py`.
"""


def _code_tags(s):
    """'<i>tags</i>' would render as italics and swallow the tag; show it as code instead."""
    return re.sub(r"<i>(.*?)</i>", r"`<i>` \1", s)


def language_bar(current, root, docs):
    links = []
    for code, name in LANGS:
        if code == current:
            links.append(f"**{name}**")
        elif code == "en":
            links.append(f"[{name}]({root}README.md)")
        else:
            links.append(f"[{name}]({docs}README.{code}.md)")
    return " · ".join(links)


def render(code):
    t = TEXT[code]
    main = code == "en"
    root = "" if main else "../../"
    img = "docs/images/readme/" if main else "../images/readme/"
    links = {
        "python": "https://www.python.org/downloads/",
        "zip": f"https://github.com/{REPO}/archive/refs/heads/main.zip",
        "issues": f"{root}docs/KNOWN_ISSUES.md",
        "roadmap": f"{root}docs/ROADMAP.md",
        "main": f"{root}README.md",
    }
    badges = (
        f"[![Tests](https://github.com/{REPO}/actions/workflows/tests.yml/badge.svg)](https://github.com/{REPO}/actions/workflows/tests.yml) "
        "![Python](https://img.shields.io/badge/python-3.10%2B-3776ab) "
        "![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-555) "
        "![UI languages](https://img.shields.io/badge/UI-37%20languages-8e44ad) "
        f"[![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f)]({root}LICENSE)"
    )
    head = [
        '<div align="center">',
        "",
        f'<img src="{root}icon.png" width="84" alt="">',
        "",
        "# Subtitle PRO",
        "",
        f"**{t['tagline']}**",
        "",
        badges,
        "",
        f"🌐 {language_bar(code, root, '' if not main else 'docs/readme/')}",
        "",
        f'<img src="{img}{code}.png" width="860" alt="Subtitle PRO">',
        "",
        "</div>",
        "",
    ]
    body = [
        f"## ✨ {t['features']}",
        "",
        *["- " + _code_tags(t[k]) for k in ("f_fast", "f_subs", "f_docs", "f_engines", "f_queue", "f_smart", "f_ui", "f_cli")],
        "",
        f"## 📥 {t['install']}",
        "",
        f"1. {t['i1'].format(**links)}",
        f"2. {t['i2'].format(**links)}",
        "",
        "   ```bash",
        "   py -m pip install -r requirements.txt tkinterdnd2 langdetect",
        "   ```",
        "",
        f"3. {t['i3']}",
        "",
        f"## 🧭 {t['usage']}",
        "",
        *[f"{i}. {t[k]}" for i, k in enumerate(("u1", "u2", "u3", "u4"), 1)],
        "",
        f"## 🖼️ {t['screens']}",
        "",
        "<table>",
        f'<tr><td align="center"><img src="{img}main-light.png" alt=""><br>{t["cap_main"]}</td>'
        f'<td align="center"><img src="{img}empty-dark.png" alt=""><br>{t["cap_empty"]}</td></tr>',
        f'<tr><td align="center"><img src="{img}settings-dark.png" alt=""><br>{t["cap_settings"]}</td>'
        f'<td align="center"><img src="{img}ar.png" alt=""><br>{t["cap_rtl"]}</td></tr>',
        "</table>",
        "",
        f"## 📊 {t['status']}",
        "",
        t["status_text"].format(**links),
        "",
    ]
    if main:
        body += [DEVELOPMENT, ""]
    else:
        body += [f"## 🛠️ {t['dev']}", "", t["dev_text"].format(**links), ""]
    body += [f"## 📜 {t['license']}", "", f"[MIT]({root}LICENSE) © noms6", ""]
    if code in RTL:
        body = ['<div dir="rtl">', "", *body, "</div>", ""]
    return "\n".join(head + body)


def main():
    keys = set(TEXT["en"])
    for code, _ in LANGS:
        assert code in TEXT, f"missing language {code}"
        assert set(TEXT[code]) == keys, (code, keys ^ set(TEXT[code]))
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(render("en"))
    out = os.path.join(ROOT, "docs", "readme")
    os.makedirs(out, exist_ok=True)
    for code, _ in LANGS[1:]:
        with open(os.path.join(out, f"README.{code}.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(render(code))
    print(f"{len(LANGS)} READMEs written")


if __name__ == "__main__":
    main()
