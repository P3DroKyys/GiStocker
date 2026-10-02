@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b 1
set "PATH=C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64;%PATH%"
set DISTUTILS_USE_SDK=1
cd /d "%~dp0\..\.."
".venv\Scripts\python.exe" -B auditoria\native_build\compilar_sqlcipher.py
