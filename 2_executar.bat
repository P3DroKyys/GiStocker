@echo off
REM ==========================================================================
REM  Abre o programa a partir do codigo-fonte (sem gerar .exe).
REM  Use durante o desenvolvimento: e instantaneo e ja reflete suas alteracoes.
REM ==========================================================================
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Ambiente nao encontrado. Rode primeiro o 1_preparar_ambiente.bat
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
