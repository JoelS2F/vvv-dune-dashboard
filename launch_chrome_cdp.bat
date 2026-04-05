@echo off
REM Launch Chrome with CDP port 9223 using your default profile
REM (port 9222 is reserved for TradingView per project memory)

echo.
echo === Chrome CDP Launcher for Dune Deployment ===
echo.
echo Step 1: Closing all existing Chrome windows...
taskkill /F /IM chrome.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul

echo Step 2: Launching Chrome with CDP on port 9223...
echo.
echo When Chrome opens:
echo   1. Verify you are signed into dune.com
echo   2. If not, sign in manually
echo   3. Leave Chrome open and run: python deploy_dune_cdp.py --execute
echo.

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
    --remote-debugging-port=9223 ^
    --remote-allow-origins=* ^
    --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data"

echo Chrome launched. Check the new window.
