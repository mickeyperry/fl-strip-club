@echo off
rem Builds dist\FLStripClub (PyInstaller), the Windows installer and the macOS zip.
rem Needs: pip install -r requirements.txt pyinstaller pillow, and Inno Setup 6.
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --windowed --name FLStripClub --icon brand\app.ico ^
  --add-data "index.html;." --add-data "brand\icon.png;brand" --add-data "brand\app.ico;brand" ^
  --add-data "brand\SpaceGrotesk.ttf;brand" --version-file version_info.txt app.py || exit /b 1
"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" /Q installer\FLStripClub.iss || exit /b 1
python build_mac_zip.py || exit /b 1
echo Done: installer\Output and dist\FLStripClub-mac-*.zip
