; AI Research Lab installer
; Build a runnable one-folder application first, then compile this file with
; Inno Setup.  The installer packages everything under dist\AI Research Lab.

#define AppName "AI Research Lab"
#define AppVersion "0.2.0-pre.2"
#define AppPublisher "EricLKIM"
#define AppURL "https://github.com/EricLKIM/AI-Research-Lab"
#define AppExeName "AI Research Lab.exe"
#define BuildDir "dist\AI Research Lab"

[Setup]
AppId={{E1B1CB84-711E-4A9C-9A7F-7C9C0C8C8A10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE
OutputDir=installer
OutputBaseFilename=AI-Research-Lab-Setup-{#AppVersion}
SetupIconFile=topic.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LanguageDetectionMethod=none
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; Do not add vault, .env, GUI settings, or .obsidian to the build folder.
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\topic.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\topic.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  ApiKeyPage: TInputQueryWizardPage;
  VaultPage: TInputDirWizardPage;
  HasExistingInstallerSettings: Boolean;

function UserDataDir(): String;
begin
  Result := ExpandConstant('{localappdata}\AI Research Lab');
end;

function InstallerSettingsMarkerPath(): String;
begin
  Result := AddBackslash(UserDataDir()) + '.installer-settings-v1';
end;

function JsonPath(Value: String): String;
begin
  Result := Value;
  StringChangeEx(Result, '\', '\\', True);
end;

function InitialOutputLanguage(): String;
begin
  if ActiveLanguage = 'korean' then begin
    Result := '한국어';
  end else begin
    Result := 'English';
  end;
end;

procedure UpdateEnvValue(EnvPath: String; Key: String; Value: String);
var
  Content: AnsiString;
  LineStart: Integer;
  LineEnd: Integer;
  KeyPrefix: AnsiString;
begin
  KeyPrefix := Key + '=';
  if not LoadStringFromFile(EnvPath, Content) then begin
    SaveStringToFile(EnvPath, KeyPrefix + Value + #13#10, False);
    exit;
  end;

  LineStart := 1;
  while LineStart <= Length(Content) do begin
    LineEnd := LineStart;
    while (LineEnd <= Length(Content)) and (Content[LineEnd] <> #13) and (Content[LineEnd] <> #10) do begin
      LineEnd := LineEnd + 1;
    end;
    if Copy(Content, LineStart, Length(KeyPrefix)) = KeyPrefix then begin
      Content := Copy(Content, 1, LineStart - 1) + KeyPrefix + Value +
        Copy(Content, LineEnd, Length(Content));
      SaveStringToFile(EnvPath, Content, False);
      exit;
    end;
    LineStart := LineEnd + 1;
    if (LineStart <= Length(Content)) and (Content[LineStart] = #10) then begin
      LineStart := LineStart + 1;
    end;
  end;

  if (Content <> '') and (Content[Length(Content)] <> #10) then begin
    Content := Content + #13#10;
  end;
  SaveStringToFile(EnvPath, Content + KeyPrefix + Value + #13#10, False);
end;

procedure UpdateJsonStringSetting(SettingsPath: String; Key: String; Value: String);
var
  Content: AnsiString;
  Marker: AnsiString;
  ValueStart: Integer;
  ValueEnd: Integer;
begin
  if not LoadStringFromFile(SettingsPath, Content) then begin
    exit;
  end;
  Marker := '"' + Key + '": "';
  ValueStart := Pos(Marker, Content);
  if ValueStart = 0 then begin
    exit;
  end;
  ValueStart := ValueStart + Length(Marker);
  ValueEnd := ValueStart;
  while (ValueEnd <= Length(Content)) and (Content[ValueEnd] <> '"') do begin
    ValueEnd := ValueEnd + 1;
  end;
  if ValueEnd > Length(Content) then begin
    exit;
  end;
  Content := Copy(Content, 1, ValueStart - 1) + JsonPath(Value) +
    Copy(Content, ValueEnd, Length(Content));
  SaveStringToFile(SettingsPath, Content, False);
end;

procedure InitializeWizard();
begin
  HasExistingInstallerSettings := FileExists(InstallerSettingsMarkerPath());
  if HasExistingInstallerSettings then begin
    exit;
  end;

  ApiKeyPage := CreateInputQueryPage(
    wpSelectDir,
    'OpenAI API key',
    'Optional: enable GPT-assisted summaries and analysis',
    'Both fields are optional. You can add or change them later in the app settings.'
  );
  ApiKeyPage.Add('OpenAI API key:', True);
  ApiKeyPage.Add('OpenAI-compatible API base (optional):', False);

  VaultPage := CreateInputDirPage(
    ApiKeyPage.ID,
    'Markdown output folder',
    'Choose where Obsidian-compatible Markdown notes will be saved',
    'This folder can be an existing Obsidian vault or a new folder. You can change it later in the app settings.',
    False,
    ''
  );
  VaultPage.Add('Markdown output folder:');
  VaultPage.Values[0] := ExpandConstant('{userdesktop}\AI_research');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  SettingsPath: String;
  EnvPath: String;
  VaultPath: String;
  ApiKey: String;
  ApiBase: String;
  SettingsJson: AnsiString;
begin
  if (CurStep <> ssPostInstall) or HasExistingInstallerSettings then begin
    exit;
  end;

  ForceDirectories(UserDataDir());
  VaultPath := RemoveBackslashUnlessRoot(VaultPage.Values[0]);
  if VaultPath <> '' then begin
    ForceDirectories(VaultPath);
  end;

  SettingsPath := AddBackslash(UserDataDir()) + 'gui_settings.json';
  if not FileExists(SettingsPath) then begin
    SettingsJson := '{' + #13#10 +
      '  "vault_path": "' + JsonPath(VaultPath) + '",' + #13#10 +
      '  "output_language": "' + InitialOutputLanguage() + '"' + #13#10 +
      '}' + #13#10;
    SaveStringToFile(SettingsPath, SettingsJson, False);
  end else begin
    UpdateJsonStringSetting(SettingsPath, 'vault_path', VaultPath);
    UpdateJsonStringSetting(SettingsPath, 'output_language', InitialOutputLanguage());
  end;

  ApiKey := Trim(ApiKeyPage.Values[0]);
  if ApiKey <> '' then begin
    EnvPath := AddBackslash(UserDataDir()) + '.env';
    UpdateEnvValue(EnvPath, 'OPENAI_API_KEY', ApiKey);
  end;
  ApiBase := Trim(ApiKeyPage.Values[1]);
  if ApiBase <> '' then begin
    EnvPath := AddBackslash(UserDataDir()) + '.env';
    UpdateEnvValue(EnvPath, 'OPENAI_API_BASE', ApiBase);
  end;
  SaveStringToFile(InstallerSettingsMarkerPath(), '1' + #13#10, False);
end;
