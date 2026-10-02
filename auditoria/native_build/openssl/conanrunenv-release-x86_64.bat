@echo off
chcp 65001 > nul
@echo off


setlocal
echo @echo off > "%~dp0/deactivate_conanrunenv-release-x86_64.bat"
echo echo Restoring environment for conanrunenv-release-x86_64.bat >> "%~dp0/deactivate_conanrunenv-release-x86_64.bat"
for %%v in (OPENSSL_MODULES) do (
    set foundenvvar=
    for /f "delims== tokens=1,2" %%a in ('set') do (
        if /I "%%a" == "%%v" (
            echo set "%%a=%%b">> "%~dp0/deactivate_conanrunenv-release-x86_64.bat"
            set foundenvvar=1
        )
    )
    if not defined foundenvvar (
        echo set %%v=>> "%~dp0/deactivate_conanrunenv-release-x86_64.bat"
    )
)
endlocal




set "OPENSSL_MODULES=C:\SOFTWA~1\CODIGO\ESTOQU~1\AUDITO~1\NATIVE~1\CONAN_~1\p\b\opens48ec178f9b800\p\lib\ossl-modules"