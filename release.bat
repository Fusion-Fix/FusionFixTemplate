@echo off
setlocal
cd /d "%~dp0"
if not exist "bin\Release\{{PROJECT_NAME}}{{TARGET_EXTENSION}}" exit /b 1
call tools\EmbedPDB\EmbedPDB.exe bin\Release\{{PROJECT_NAME}}{{TARGET_EXTENSION}}
if errorlevel 1 exit /b %errorlevel%

powershell -NoProfile -ExecutionPolicy Bypass -File "sign.ps1" -SearchPaths ".\bin\Release\{{PROJECT_NAME}}{{TARGET_EXTENSION}}"
if errorlevel 1 exit /b %errorlevel%

copy /y "bin\Release\{{PROJECT_NAME}}{{TARGET_EXTENSION}}" "data\plugins\{{PROJECT_NAME}}{{TARGET_EXTENSION}}"
if errorlevel 1 exit /b %errorlevel%

if exist "{{PROJECT_NAME}}.zip" del "{{PROJECT_NAME}}.zip"
7z a "{{PROJECT_NAME}}.zip" ".\data\*" ^
-xr!*\.gitkeep
exit /b %errorlevel%
