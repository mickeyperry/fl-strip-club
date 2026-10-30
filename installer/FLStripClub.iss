; FL Strip Club installer (Inno Setup 6). Built by ..\build.bat after PyInstaller.
#define AppVersion "1.1.0"

[Setup]
AppId={{9C2E7A41-3B6D-4F1A-8E52-7D0C4B1A6F93}
AppName=FL Strip Club
AppVersion={#AppVersion}
AppVerName=FL Strip Club {#AppVersion}
AppPublisher=Pafu Igniters
AppPublisherURL=https://github.com/mickeyperry/fl-strip-club
AppSupportURL=https://github.com/mickeyperry/fl-strip-club/issues
DefaultDirName={autopf}\FL Strip Club
DefaultGroupName=FL Strip Club
DisableDirPage=yes
; 1.1 renamed Strip Silence -> FL Strip Club: install to the new folder, not the old one
UsePreviousAppDir=no
UsePreviousGroup=no
DisableProgramGroupPage=yes
; per-user install: no admin prompt
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=FLStripClub-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
; same dark Pafu look as ReWasp (brand\make_brand.py)
WizardStyle=modern dark hidebevels
WizardBackColor=#0B0B0F
DisableWelcomePage=no
UninstallDisplayName=FL Strip Club: strip silence for FL Studio
UninstallDisplayIcon={app}\FLStripClub.exe
SetupIconFile=..\brand\app.ico
WizardImageFile=..\brand\wizard_small.png,..\brand\wizard.png
WizardSmallImageFile=..\brand\corner_small.png,..\brand\corner.png
WizardImageBackColor=#0B0B0F
CloseApplications=yes
ChangesAssociations=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "contextmenu"; Description: "Add ""Strip silence"" to the right-click menu of .flp files"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\FLStripClub\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\FL Strip Club"; Filename: "{app}\FLStripClub.exe"
Name: "{group}\Uninstall FL Strip Club"; Filename: "{uninstallexe}"
Name: "{autodesktop}\FL Strip Club"; Filename: "{app}\FLStripClub.exe"; Tasks: desktopicon

[InstallDelete]
; leftovers of the Strip Silence 1.0 install (same AppId, old name)
Type: filesandordirs; Name: "{autopf}\Strip Silence"
Type: filesandordirs; Name: "{autoprograms}\Strip Silence"
Type: files; Name: "{autodesktop}\Strip Silence.lnk"

[Registry]
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.flp\shell\StripSilence"; Flags: deletekey dontcreatekey
; right-click a .flp > Strip silence (doesn't touch which program opens .flp files)
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.flp\shell\FLStripClub"; ValueType: string; ValueName: ""; ValueData: "Strip silence (FL Strip Club)"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.flp\shell\FLStripClub"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\FLStripClub.exe"",0"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.flp\shell\FLStripClub\command"; ValueType: string; ValueName: ""; ValueData: """{app}\FLStripClub.exe"" ""%1"""; Tasks: contextmenu

[Run]
Filename: "{app}\FLStripClub.exe"; Description: "Open FL Strip Club"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\FL Strip Club"

[Messages]
WelcomeLabel1=FL Strip Club
WelcomeLabel2=Cuts the silence out of the audio clips in your FL Studio playlist. Every sound stays exactly where it was in the song; only the empty stretches go.%n%nPreview every cut before you save, and your original project is never changed.%n%nMade by Mickey Perry, aka Pafu Igniters (breakbeat, trance and drum & bass), who also does motion design and animation. I made this to tidy up my own stem-heavy projects. I hope it saves you some clicking too.
FinishedHeadingLabel=FL Strip Club is installed
FinishedLabel=Save your project in FL Studio, then open it in FL Strip Club (or right-click the .flp file > Strip silence).
FinishedLabelNoIcons=Save your project in FL Studio, then open it in FL Strip Club (or right-click the .flp file > Strip silence).

[Code]
procedure OpenLink(Sender: TObject);
var
  Code: Integer;
begin
  ShellExec('open', TNewStaticText(Sender).Hint, '', '', SW_SHOWNORMAL, ewNoWait, Code);
end;

// links under the finish text: the music, then the motion design / animation work
procedure AddLink(var Y: Integer; const Caption, Url: String; Heading: Boolean);
var
  L: TNewStaticText;
begin
  L := TNewStaticText.Create(WizardForm);
  L.Parent := WizardForm.FinishedPage;
  L.Left := WizardForm.FinishedLabel.Left;
  L.Top := Y;
  L.Caption := Caption;
  if Heading then begin
    L.Font.Style := [fsBold];
    Y := Y + L.Height + ScaleY(4);
  end else begin
    L.Hint := Url;
    L.Cursor := crHand;
    L.Font.Color := $872DFF;   // #ff2d87 (BGR)
    L.Font.Style := [fsUnderline];
    L.OnClick := @OpenLink;
    L.Left := L.Left + ScaleX(12);
    Y := Y + L.Height + ScaleY(2);
  end;
end;

procedure AddLinks;
var
  Y: Integer;
begin
  // below the "Open FL Strip Club" checkbox
  Y := WizardForm.RunList.Top + ScaleY(44);
  AddLink(Y, 'Pafu Igniters (music)', '', True);
  AddLink(Y, 'SoundCloud', 'https://soundcloud.com/pafu', False);
  AddLink(Y, 'Bandcamp', 'https://pafu.bandcamp.com', False);
  Y := Y + ScaleY(12);
  AddLink(Y, 'Mickey Perry (motion design and animation)', '', True);
  AddLink(Y, 'mickeyperry.github.io', 'https://mickeyperry.github.io/', False);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then AddLinks;
end;

// The app window is drawn by Microsoft Edge WebView2 (built into Windows 11 and current Windows 10).
function HasWebView2: Boolean;
var
  V, K: String;
begin
  K := 'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Result := (RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\' + K, 'pv', V) and (V <> '') and (V <> '0.0.0.0')) or
            (RegQueryStringValue(HKLM, 'SOFTWARE\' + K, 'pv', V) and (V <> '') and (V <> '0.0.0.0')) or
            (RegQueryStringValue(HKCU, 'Software\' + K, 'pv', V) and (V <> '') and (V <> '0.0.0.0'));
end;

function InitializeSetup: Boolean;
var
  Code: Integer;
begin
  Result := True;
  if not HasWebView2 then
    if MsgBox('FL Strip Club needs the Microsoft Edge WebView2 Runtime, which is not on this PC.' + #13#10#13#10 +
              'Open the download page now? (Install it, then run this setup again.)', mbConfirmation, MB_YESNO) = IDYES then begin
      ShellExec('open', 'https://developer.microsoft.com/microsoft-edge/webview2/#download-section', '', '', SW_SHOWNORMAL, ewNoWait, Code);
      Result := False;
    end;
end;
