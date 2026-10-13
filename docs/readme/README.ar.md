<div align="center">

<img src="../../icon.png" width="84" alt="">

# Subtitle PRO

**ترجمة الترجمات المرئية والمستندات دفعةً واحدة — تبقى الطوابع الزمنية والترقيم وفواصل الأسطر كما هي تمامًا.**

[![Tests](https://github.com/noms6/subtitle-pro/actions/workflows/tests.yml/badge.svg)](https://github.com/noms6/subtitle-pro/actions/workflows/tests.yml) ![Python](https://img.shields.io/badge/python-3.10%2B-3776ab) ![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-555) ![UI languages](https://img.shields.io/badge/UI-37%20languages-8e44ad) [![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f)](../../LICENSE)

🌐 [English](../../README.md) · [Türkçe](README.tr.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português](README.pt.md) · [Nederlands](README.nl.md) · [Polski](README.pl.md) · [Svenska](README.sv.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · **العربية** · [فارسی](README.fa.md) · [हिन्दी](README.hi.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [中文](README.zh.md) · [Bahasa Indonesia](README.id.md) · [Tiếng Việt](README.vi.md)

<img src="../images/readme/ar.png" width="860" alt="Subtitle PRO">

</div>

<div dir="rtl">

## ✨ الميزات

- سريع: يُترجَم فيلم كامل (≈1500 سطر) في نحو 12 ثانية — تُرسَل الأسطر على دفعات
- ملفات الترجمة: SRT وVTT — تُحفَظ الأرقام والطوابع الزمنية و`<i>` الوسوم ونهايات الأسطر؛ مخرجات UTF-8 تقرؤها مشغلات Windows بشكل صحيح
- المستندات: TXT وMarkdown وCSV وDOCX (النص والجداول والرؤوس والتذييلات) وPDF (يُحفَظ بصيغة PDF أو TXT)
- الخدمات: Google وMyMemory وDeepL API وLibreTranslate — إذا قُيِّدت خدمة ينتقل البرنامج تلقائيًا إلى أخرى
- قائمة انتظار للملفات مع السحب والإفلات، ومعالجة متوازية اختيارية، وتقدّم ووقت متبقٍ مباشر
- يتخطى الملفات المكتوبة أصلًا باللغة الهدف؛ مسرد مخصص (JSON/CSV) قبل الترجمة أو بعدها
- واجهة بـ 37 لغة، وسمتان فاتحة وداكنة مع 6 ألوان تمييز؛ تُحفَظ جميع الإعدادات
- ومن سطر الأوامر أيضًا: `python translate_srt.py input.srt output.srt ar`

## 📥 التثبيت (Windows)

1. ثبّت [Python 3.10 أو أحدث](https://www.python.org/downloads/) وحدِّد خيار “Add python.exe to PATH”.
2. نزّل المشروع ([ZIP](https://github.com/noms6/subtitle-pro/archive/refs/heads/main.zip)) أو انسخه، ثم ثبّت الاعتماديات:

   ```bash
   py -m pip install -r requirements.txt tkinterdnd2 langdetect
   ```

3. انقر نقرًا مزدوجًا على `run_app.bat` أو `Subtitle PRO.pyw` — لا تبقى أي نافذة طرفية مفتوحة.

## 🧭 طريقة الاستخدام

1. أضف الملفات عبر **إضافة...** أو اسحبها إلى النافذة.
2. اختر اللغة الهدف وخدمة الترجمة (يُنصح بـ **تلقائي**).
3. اضغط **▶ بدء**. تُحفَظ النتيجة بجانب الملف الأصلي، مثل `film.en.ar.srt`.
4. راجع النتيجة — تُترك الأسماء وأدوات التعجب مثل “آه!” دون تغيير عن قصد.

## 🖼️ لقطات الشاشة

<table>
<tr><td align="center"><img src="../images/readme/main-light.png" alt=""><br>النافذة الرئيسية</td><td align="center"><img src="../images/readme/empty-dark.png" alt=""><br>قائمة فارغة — أفلت ملفاتك هنا</td></tr>
<tr><td align="center"><img src="../images/readme/settings-dark.png" alt=""><br>الإعدادات</td><td align="center"><img src="../images/readme/ar.png" alt=""><br>اللغات التي تُكتب من اليمين إلى اليسار</td></tr>
</table>

## 📊 حالة المشروع

قيد التطوير النشط ومغطى بأكثر من 270 اختبارًا آليًا. المشكلات المعروفة وخطة العمل (بالتركية): [KNOWN_ISSUES](../../docs/KNOWN_ISSUES.md) و[ROADMAP](../../docs/ROADMAP.md).

## 🛠️ التطوير

البنية والاختبارات ودليل الترجمة: راجع [ملف README الرئيسي](../../README.md#development).

## 📜 الترخيص

[MIT](../../LICENSE) © noms6

</div>
