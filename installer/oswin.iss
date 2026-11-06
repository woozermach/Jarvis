; Установщик Oswin (Inno Setup 6). Собирается GitHub Actions: .github/workflows/installer.yml
; Внутри — готовый Python 3.13 со всеми библиотеками в .venv\Scripts (тот же путь, что у ручной установки,
; поэтому обновления, перезапуск и автозапуск работают без изменений). Ставится без прав администратора.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Src
  #define Src "..\build\app"
#endif

[Setup]
AppId={{7C2B1E54-5A0D-4F8B-9C51-3E2D6B8A9F10}
AppName=Oswin
AppVersion={#AppVersion}
AppVerName=Oswin {#AppVersion}
AppPublisher=Oswin
AppPublisherURL=https://github.com/woozermach/Jarvis
AppSupportURL=https://github.com/woozermach/Jarvis/issues
DefaultDirName={localappdata}\Programs\Oswin
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\build\out
OutputBaseFilename=OswinSetup
SetupIconFile=..\ui\jarvis.ico
UninstallDisplayIcon={app}\ui\jarvis.ico
UninstallDisplayName=Oswin
WizardStyle=modern
WizardSmallImageFile=small_55.bmp,small_64.bmp,small_83.bmp,small_110.bmp
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=no
ShowLanguageDialog=auto
UsePreviousTasks=yes

[Languages]
#include "languages.iss"

[CustomMessages]
DeleteData=Also delete your Oswin settings and data (API key, notes, memory, history)?
StartAfter=Start Oswin
; переводы этих двух строк — в installer/gen_languages.py (попадают в languages.iss)

[Tasks]
Name: desktopicon; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#Src}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Oswin"; Filename: "{app}\Oswin.exe"; WorkingDir: "{app}"; IconFilename: "{app}\ui\jarvis.ico"; Comment: "Oswin voice assistant"; AppUserModelID: "oswin.assistant"
Name: "{userdesktop}\Oswin"; Filename: "{app}\Oswin.exe"; WorkingDir: "{app}"; IconFilename: "{app}\ui\jarvis.ico"; Comment: "Oswin voice assistant"; AppUserModelID: "oswin.assistant"; Tasks: desktopicon

[Run]
Filename: "{app}\Oswin.exe"; WorkingDir: "{app}"; Description: "{cm:StartAfter}"; Flags: nowait postinstall skipifsilent

[InstallDelete]
; ярлыки прежнего имени (Sayro, до 3.1)
Type: files; Name: "{userprograms}\Sayro.lnk"
Type: files; Name: "{userdesktop}\Sayro.lnk"

[UninstallDelete]
Type: files; Name: "{userstartup}\Oswin.lnk"
Type: files; Name: "{userstartup}\Sayro.lnk"

[Code]
{ Останавливает все python-процессы этой копии Oswin: ядро (jarvis.py), окно (core\window.py), помощник обновления. }
procedure StopOswin(Dir: String);
var
  Script, P: String;
  Rc: Integer;
begin
  P := AddBackslash(Dir);
  StringChangeEx(P, '''', '''''', True);
  Script := ExpandConstant('{tmp}');
  if Script = '' then Script := GetTempDir();
  Script := AddBackslash(Script) + 'oswin_stop.ps1';
  SaveStringToFile(Script,
    '$p = ''' + P + '''' + #13#10 +
    'Get-CimInstance Win32_Process -Filter "Name=''pythonw.exe'' OR Name=''python.exe'' OR Name=''Oswin.exe''" | ' +
    'Where-Object { ($_.ExecutablePath -and $_.ExecutablePath.ToLower().StartsWith($p.ToLower())) -or ' +
    '($_.CommandLine -and $_.CommandLine.ToLower().Contains($p.ToLower())) } | ' +
    'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }' + #13#10, False);
  Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -File "' + Script + '"', '', SW_HIDE, ewWaitUntilTerminated, Rc);
  DeleteFile(Script);
  Sleep(800);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  if DirExists(ExpandConstant('{app}')) then
    StopOswin(ExpandConstant('{app}'));
  Result := '';
end;

{ Удаляет всё в папке программы, кроме личных данных (если пользователь их оставляет). }
procedure CleanApp(Dir: String; KeepData: Boolean);
var
  F: TFindRec;
  N: String;
begin
  if FindFirst(Dir + '\*', F) then
  try
    repeat
      N := F.Name;
      if (N <> '.') and (N <> '..') then
      begin
        if KeepData and ((CompareText(N, 'data') = 0) or (CompareText(N, 'config.json') = 0) or
           (Pos('jarvis.log', Lowercase(N)) = 1)) then
          continue;
        if F.Attributes and FILE_ATTRIBUTE_DIRECTORY <> 0 then
          DelTree(Dir + '\' + N, True, True, True)
        else
          DeleteFile(Dir + '\' + N);
      end;
    until not FindNext(F);
  finally
    FindClose(F);
  end;
  if not KeepData then
    RemoveDir(Dir);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Keep: Boolean;
begin
  if CurUninstallStep = usUninstall then
    StopOswin(ExpandConstant('{app}'));
  if CurUninstallStep = usPostUninstall then
  begin
    Keep := True;
    if not UninstallSilent then
      Keep := MsgBox(CustomMessage('DeleteData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) <> IDYES;
    CleanApp(ExpandConstant('{app}'), Keep);
  end;
end;
