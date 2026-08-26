; 音乐解锁 Windows 安装包（Inno Setup）
; Source 相对 .iss 所在目录；CI 在仓库根目录调用 iscc。

#ifndef AppVersion
  #define AppVersion "1.0.4"
#endif
#ifndef AppArch
  #define AppArch "x86_64"
#endif

[Setup]
AppName=音乐解锁
AppVersion={#AppVersion}
AppPublisher=music-unlock
DefaultDirName={autopf}\音乐解锁
DefaultGroupName=音乐解锁
OutputDir=..\Output
OutputBaseFilename=music-unlock-setup-windows-{#AppArch}
Compression=lzma2
SolidCompression=yes
#if AppArch == "arm64"
ArchitecturesAllowed=arm64
ArchitecturesInstallIn64BitMode=arm64
#else
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#endif

[Files]
Source: "..\dist\music-unlock\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\音乐解锁"; Filename: "{app}\music-unlock.exe"
Name: "{autodesktop}\音乐解锁"; Filename: "{app}\music-unlock.exe"

[Run]
Filename: "{app}\music-unlock.exe"; Description: "启动音乐解锁"; Flags: postinstall nowait skipifsilent
