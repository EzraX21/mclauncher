; Inno Setup 脚本：mclauncher.exe 安装包
#define MyAppName "mclauncher"
#define MyAppVersion "2.2.3"
#define MyAppPublisher "mclauncher"
#define MyAppExeName "mclauncher.exe"

[Setup]
AppId={{8E4B2C5A-3F1D-4C7E-9B2A-6D5F1A0C3E21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=mclauncher-{#MyAppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Files]
Source: "..\..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; TUI 需要终端，快捷方式直接用 cmd 打开
Name: "{group}\{#MyAppName}"; Filename: "{cmd}"; Parameters: "/k ""{app}\{#MyAppExeName}"""; WorkingDir: "{app}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{cmd}"; Parameters: "/k ""{app}\{#MyAppExeName}"""; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Run]
Filename: "{cmd}"; Parameters: "/k ""{app}\{#MyAppExeName}"""; WorkingDir: "{app}"; Description: "启动 mclauncher"; Flags: postinstall nowait skipifsilent
