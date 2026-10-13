<div align="center">

<img src="../../icon.png" width="84" alt="">

# Subtitle PRO

**Пакетный перевод субтитров и документов — таймкоды, нумерация и переносы строк остаются в точности как были.**

[![Tests](https://github.com/noms6/subtitle-pro/actions/workflows/tests.yml/badge.svg)](https://github.com/noms6/subtitle-pro/actions/workflows/tests.yml) ![Python](https://img.shields.io/badge/python-3.10%2B-3776ab) ![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-555) ![UI languages](https://img.shields.io/badge/UI-37%20languages-8e44ad) [![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f)](../../LICENSE)

🌐 [English](../../README.md) · [Türkçe](README.tr.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português](README.pt.md) · [Nederlands](README.nl.md) · [Polski](README.pl.md) · [Svenska](README.sv.md) · **Русский** · [Українська](README.uk.md) · [العربية](README.ar.md) · [فارسی](README.fa.md) · [हिन्दी](README.hi.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [中文](README.zh.md) · [Bahasa Indonesia](README.id.md) · [Tiếng Việt](README.vi.md)

<img src="../images/readme/ru.png" width="860" alt="Subtitle PRO">

</div>

## ✨ Возможности

- Быстро: полнометражный фильм (≈1500 строк) переводится примерно за 12 секунд — строки отправляются пакетами
- Субтитры: SRT и VTT — номера, таймкоды, `<i>` теги и концы строк сохраняются; вывод в UTF-8, который правильно читают плееры Windows
- Документы: TXT, Markdown, CSV, DOCX (текст, таблицы, колонтитулы) и PDF (сохраняется как PDF или TXT)
- Сервисы: Google, MyMemory, DeepL API и LibreTranslate — если сервис ограничивает запросы, программа автоматически переключается на другой
- Очередь файлов с перетаскиванием, необязательная параллельная обработка, прогресс и оставшееся время в реальном времени
- Пропускает файлы, уже написанные на целевом языке; собственный глоссарий (JSON/CSV) до или после перевода
- Интерфейс на 37 языках, светлая и тёмная темы с 6 акцентными цветами; все настройки запоминаются
- Также из командной строки: `python translate_srt.py input.srt output.srt ru`

## 📥 Установка (Windows)

1. Установите [Python 3.10 или новее](https://www.python.org/downloads/) и отметьте «Add python.exe to PATH».
2. Скачайте проект ([ZIP](https://github.com/noms6/subtitle-pro/archive/refs/heads/main.zip)) или клонируйте его, затем установите зависимости:

   ```bash
   py -m pip install -r requirements.txt tkinterdnd2 langdetect
   ```

3. Дважды щёлкните `run_app.bat` или `Subtitle PRO.pyw` — окно консоли не остаётся открытым.

## 🧭 Как пользоваться

1. Добавьте файлы кнопкой **Добавить...** или перетащите их в окно.
2. Выберите целевой язык и сервис (рекомендуется **Авто**).
3. Нажмите **▶ Начать**. Результат сохраняется рядом с оригиналом, например `film.en.ru.srt`.
4. Проверьте результат — имена и междометия вроде «Ах!» намеренно не изменяются.

## 🖼️ Скриншоты

<table>
<tr><td align="center"><img src="../images/readme/main-light.png" alt=""><br>Главное окно</td><td align="center"><img src="../images/readme/empty-dark.png" alt=""><br>Пустая очередь — перетащите файлы сюда</td></tr>
<tr><td align="center"><img src="../images/readme/settings-dark.png" alt=""><br>Настройки</td><td align="center"><img src="../images/readme/ar.png" alt=""><br>Языки с письмом справа налево</td></tr>
</table>

## 📊 Состояние проекта

Активно развивается и покрыт более чем 270 автотестами. Известные проблемы и план развития (на турецком): [KNOWN_ISSUES](../../docs/KNOWN_ISSUES.md) и [ROADMAP](../../docs/ROADMAP.md).

## 🛠️ Разработка

Архитектура, тесты и руководство по переводу: см. [основной README](../../README.md#development).

## 📜 Лицензия

[MIT](../../LICENSE) © noms6
