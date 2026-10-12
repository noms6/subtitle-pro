@echo off
setlocal

rem Change to script directory
cd /d "%~dp0"

rem Try Python launcher first
where py >nul 2>nul
if %errorlevel%==0 (
  py "%~dp0translate_srt.py" %*
  exit /b %errorlevel%
)

rem Try python.exe
where python >nul 2>nul
if %errorlevel%==0 (
  python "%~dp0translate_srt.py" %*
  exit /b %errorlevel%
)

echo Python bulunamadı. Indirme sayfasi aciliyor...
start "" "https://www.python.org/downloads/"
exit /b 1


