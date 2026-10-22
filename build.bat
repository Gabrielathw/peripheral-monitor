@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "SAIDA=%LOCALAPPDATA%\PeripheralMonitor_build"

echo ============================================
echo   Criando o programa "Peripheral Monitor"...
echo   (pode demorar 2 a 5 minutos, nao feche!)
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERRO: nao encontrei a pasta .venv. Rode este arquivo dentro da pasta MonitorPerifericos.
    pause
    exit /b 1
)

echo [0/3] Fechando o programa antigo, se estiver aberto...
taskkill /f /im PeripheralMonitor.exe >nul 2>&1
taskkill /f /im MeusPerifericos.exe >nul 2>&1
timeout /t 2 /nobreak >nul
if exist "dist\PeripheralMonitor.exe" del /f /q "dist\PeripheralMonitor.exe" >nul 2>&1

echo [1/3] Instalando as ferramentas necessarias...
".venv\Scripts\python.exe" -m pip install --upgrade pyinstaller
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo [2/3] Montando o programa...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed --icon="%~dp0icon.ico" --name PeripheralMonitor --collect-all customtkinter --collect-all bleak --collect-submodules winrt --distpath "%SAIDA%\dist" --workpath "%SAIDA%\work" --specpath "%SAIDA%" "%~dp0main.py"

if errorlevel 1 (
    echo.
    echo ERRO ao montar o programa. Tire um print desta tela e me mande.
    pause
    exit /b 1
)

echo.
echo [3/3] PRONTO!
echo O seu programa esta em:
echo     %SAIDA%\dist\PeripheralMonitor.exe
echo.

rem Tenta tambem copiar para a pasta dist do projeto (se der erro, tudo bem)
if not exist "dist" mkdir "dist" >nul 2>&1
copy /y "%SAIDA%\dist\PeripheralMonitor.exe" "dist\PeripheralMonitor.exe" >nul 2>&1

explorer "%SAIDA%\dist"
pause
