@echo off
REM ==========================================================================
REM  Prepara o ambiente de desenvolvimento (rodar UMA VEZ por computador).
REM  Cria a pasta .venv com o Python isolado e instala as bibliotecas.
REM ==========================================================================
cd /d "%~dp0"
echo.
python -c "import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,14) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
    echo Esta versao requer Python 3.14 de 64 bits. A build pronta nao exige Python.
    pause
    exit /b 1
)
echo [1/3] Criando ambiente virtual em .venv ...
python -m venv .venv
if errorlevel 1 (
    echo.
    echo ERRO: Python nao encontrado. Instale o Python 3.14 de 64 bits em
    echo https://www.python.org/downloads/ marcando a opcao "Add Python to PATH".
    pause
    exit /b 1
)

echo [2/3] Atualizando o pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet

echo [3/3] Instalando bibliotecas (customtkinter, matplotlib, pandas, pyinstaller) ...
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 goto erro_dependencias
".venv\Scripts\python.exe" -m pip install --quiet pyinstaller==6.22.3
if errorlevel 1 goto erro_dependencias
goto ambiente_pronto
:erro_dependencias
(
    echo.
    echo ERRO ao instalar as bibliotecas. Verifique sua conexao com a internet.
    pause
    exit /b 1
)

echo.
:ambiente_pronto
echo Ambiente pronto! Agora use:
echo    2_executar.bat   - abre o programa para testar
echo    3_gerar_exe.bat  - gera o GestorEstoque.exe na pasta dist
echo.
pause
