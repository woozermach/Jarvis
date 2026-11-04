; Установщик Sayro (Inno Setup 6). Собирается GitHub Actions: .github/workflows/installer.yml
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
AppName=Sayro
AppVersion={#AppVersion}
AppVerName=Sayro {#AppVersion}
AppPublisher=Sayro
AppPublisherURL=https://github.com/woozermach/Jarvis
AppSupportURL=https://github.com/woozermach/Jarvis/issues
DefaultDirName={localappdata}\Programs\Sayro
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\build\out
OutputBaseFilename=SayroSetup
SetupIconFile=..\ui\jarvis.ico
UninstallDisplayIcon={app}\ui\jarvis.ico
UninstallDisplayName=Sayro
WizardStyle=modern
WizardSmallImageFile=small_55.bmp,small_64.bmp,small_83.bmp,small_110.bmp
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=4
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=no
ShowLanguageDialog=auto
UsePreviousTasks=yes

[Languages]
#include "languages.iss"

[CustomMessages]
DeleteData=Also delete your Sayro settings and data (API key, notes, memory, history)?
StartAfter=Start Sayro
; переводы этих двух строк — в installer/gen_languages.py (попадают в languages.iss)

[Tasks]
Name: desktopicon; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#Src}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Sayro"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\jarvis.py"""; WorkingDir: "{app}"; IconFilename: "{app}\ui\jarvis.ico"; Comment: "Sayro voice assistant"
Name: "{userdesktop}\Sayro"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\jarvis.py"""; WorkingDir: "{app}"; IconFilename: "{app}\ui\jarvis.ico"; Comment: "Sayro voice assistant"; Tasks: desktopicon

[Run]
Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\jarvis.py"""; WorkingDir: "{app}"; Description: "{cm:StartAfter}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{userstartup}\Sayro.lnk"

[Code]
{ Останавливает только копию Sayro из этой папки (по полному пути к jarvis.py). }
procedure StopSayro(Dir: String);
var
  Script, P: String;
  Rc: Integer;
begin
  P := Dir + '\jarvis.py';
  StringChangeEx(P, '''', '''''', True);
  Script := ExpandConstant('{tmp}');
  if Script = '' then Script := GetTempDir();
  Script := AddBackslash(Script) + 'sayro_stop.ps1';
  SaveStringToFile(Script,
    '$p = ''' + P + '''' + #13#10 +
    'Get-CimInstance Win32_Process -Filter "Name=''pythonw.exe'' OR Name=''python.exe''" | ' +
    'Where-Object { $_.CommandLine -and $_.CommandLine.ToLower().Contains($p.ToLower()) } | ' +
    'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }' + #13#10, False);
  Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -File "' + Script + '"', '', SW_HIDE, ewWaitUntilTerminated, Rc);
  DeleteFile(Script);
  Sleep(800);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  if DirExists(ExpandConstant('{app}')) then
    StopSayro(ExpandConstant('{app}'));
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
    StopSayro(ExpandConstant('{app}'));
  if CurUninstallStep = usPostUninstall then
  begin
    Keep := True;
    if not UninstallSilent then
      Keep := MsgBox(CustomMessage('DeleteData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) <> IDYES;
    CleanApp(ExpandConstant('{app}'), Keep);
  end;
end;
