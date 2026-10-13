@echo off
rem Starts Subtitle PRO without leaving a console window open.
rem (Running "py translate_srt.py" here used to keep a black cmd window open behind the app.)
setlocal
cd /d "%~dp0"

rem Command-line use (arguments given): keep the console so progress is visible
if not "%~1"=="" goto console

where pyw >nul 2>nul
if %errorlevel%==0 (
  start "" pyw "%~dp0translate_srt.py"
  exit /b 0
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw "%~dp0translate_srt.py"
  exit /b 0
)

:console
where py >nul 2>nul
if %errorlevel%==0 (
  py "%~dp0translate_srt.py" %*
  exit /b %errorlevel%
)
where python >nul 2>nul
if %errorlevel%==0 (
  python "%~dp0translate_srt.py" %*
  exit /b %errorlevel%
)

echo Python bulunamadi. Indirme sayfasi aciliyor...
start "" "https://www.python.org/downloads/"
exit /b 1
