@echo off
setlocal
cd /d "%~dp0"
if not exist "smdm_native_host.exe" (
  echo smdm_native_host.exe not found. Extract the complete package first.
  pause
  exit /b 1
)
if not exist "SimpleDownloadManagerPro.exe" (
  echo SimpleDownloadManagerPro.exe not found. Extract the complete package first.
  pause
  exit /b 1
)
set "HOSTDIR=%APPDATA%\Mozilla\NativeMessagingHosts"
if not exist "%HOSTDIR%" mkdir "%HOSTDIR%"
set "HOSTPATH=%~dp0smdm_native_host.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=$env:HOSTPATH; $j=@{name='com.simpledownloadmanagerpro.host';description='Simple Download Manager Pro Native Host';path=$p;type='stdio';allowed_extensions=@('smdm-firefox-connector@example.com')} | ConvertTo-Json -Depth 4; [IO.File]::WriteAllText('%HOSTDIR%\com.simpledownloadmanagerpro.host.json',$j,(New-Object System.Text.UTF8Encoding($false)))"
if errorlevel 1 (
  echo Could not write Firefox native host manifest.
  pause
  exit /b 1
)
reg add "HKCU\Software\Mozilla\NativeMessagingHosts\com.simpledownloadmanagerpro.host" /ve /t REG_SZ /d "%HOSTDIR%\com.simpledownloadmanagerpro.host.json" /f
echo.
echo Native host installed. Now install the Firefox extension from the firefox-extension folder.
pause
