@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Ambiente nao encontrado. Rode primeiro o 1_preparar_ambiente.bat
    pause
    exit /b 1
)
echo Gerando em uma nova pasta dentro de dist. Versoes anteriores serao preservadas.
".venv\Scripts\python.exe" -B gerar_build.py
if errorlevel 1 (
    echo ERRO ao gerar o executavel. Confira as mensagens acima.
    pause
    exit /b 1
)
pause
