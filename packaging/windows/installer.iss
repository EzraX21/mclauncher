; Inno Setup 脚本：MCL 桌面安装包（mclw.exe + mcl.exe）
#define MyAppName "MCL"
#define MyAppVersion GetEnv("MCL_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "0.0.0"
#endif
#define MyAppPublisher "mclauncher"
#define MyAppExeName "mclw.exe"

[Setup]
AppId={{8E4B2C5A-3F1D-4C7E-9B2A-6D5F1A0C3E21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=mcl-{#MyAppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
SetupIconFile=..\..\gui\assets\mcl.ico

[Files]
Source: "..\..\dist\mclw.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\dist\mcl.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{#MyAppName} 命令行"; Filename: "{cmd}"; Parameters: "/k ""{app}\mcl.exe"""; WorkingDir: "{app}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Run]
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "启动 MCL"; Flags: postinstall nowait skipifsilent
