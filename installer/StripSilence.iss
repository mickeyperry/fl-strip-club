; Strip Silence installer (Inno Setup 6). Built by ..\build.bat after PyInstaller.
#define AppVersion "1.0.0"

[Setup]
AppId={{9C2E7A41-3B6D-4F1A-8E52-7D0C4B1A6F93}
AppName=Strip Silence
AppVersion={#AppVersion}
AppVerName=Strip Silence {#AppVersion}
AppPublisher=Pafu Igniters
AppPublisherURL=https://github.com/mickeyperry/strip-silence
AppSupportURL=https://github.com/mickeyperry/strip-silence/issues
DefaultDirName={autopf}\Strip Silence
DefaultGroupName=Strip Silence
DisableDirPage=yes
DisableProgramGroupPage=yes
; per-user install: no admin prompt
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=StripSilence-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
; same dark Pafu look as ReWasp (brand\make_brand.py)
WizardStyle=modern dark hidebevels
WizardBackColor=#0B0B0F
DisableWelcomePage=no
UninstallDisplayName=Strip Silence for FL Studio
UninstallDisplayIcon={app}\StripSilence.exe
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
Source: "..\dist\StripSilence\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Strip Silence"; Filename: "{app}\StripSilence.exe"
Name: "{group}\Uninstall Strip Silence"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Strip Silence"; Filename: "{app}\StripSilence.exe"; Tasks: desktopicon

[Registry]
; right-click a .flp > Strip silence (doesn't touch which program opens .flp files)
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.flp\shell\StripSilence"; ValueType: string; ValueName: ""; ValueData: "Strip silence"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.flp\shell\StripSilence"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\StripSilence.exe"",0"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.flp\shell\StripSilence\command"; ValueType: string; ValueName: ""; ValueData: """{app}\StripSilence.exe"" ""%1"""; Tasks: contextmenu

[Run]
Filename: "{app}\StripSilence.exe"; Description: "Open Strip Silence"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\Strip Silence"

[Messages]
WelcomeLabel1=Strip Silence
WelcomeLabel2=Cuts the silence out of the audio clips in your FL Studio playlist. Every sound stays exactly where it was in the song; only the empty stretches go.%n%nPreview every cut before you save, and your original project is never changed.%n%nMade by Mickey Perry, aka Pafu Igniters (breakbeat, trance and drum & bass), who also does motion design and animation. I made this to tidy up my own stem-heavy projects. I hope it saves you some clicking too.
FinishedHeadingLabel=Strip Silence is installed
FinishedLabel=Save your project in FL Studio, then open it in Strip Silence (or right-click the .flp file > Strip silence).
FinishedLabelNoIcons=Save your project in FL Studio, then open it in Strip Silence (or right-click the .flp file > Strip silence).

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
  // below the "Open Strip Silence" checkbox
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
    if MsgBox('Strip Silence needs the Microsoft Edge WebView2 Runtime, which is not on this PC.' + #13#10#13#10 +
              'Open the download page now? (Install it, then run this setup again.)', mbConfirmation, MB_YESNO) = IDYES then begin
      ShellExec('open', 'https://developer.microsoft.com/microsoft-edge/webview2/#download-section', '', '', SW_SHOWNORMAL, ewNoWait, Code);
      Result := False;
    end;
end;
