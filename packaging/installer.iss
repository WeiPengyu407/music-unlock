; 音乐解锁 Windows 安装包（Inno Setup）
; CI 中由 iscc 调用：dist\music-unlock\ 为 PyInstaller onedir 产物（含 assets）

#ifndef AppVersion
  #define AppVersion "1.0.3"
#endif

[Setup]
AppName=音乐解锁
AppVersion={#AppVersion}
AppPublisher=music-unlock
DefaultDirName={autopf}\音乐解锁
DefaultGroupName=音乐解锁
OutputDir=Output
OutputBaseFilename=音乐解锁-setup-windows-x86_64
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "dist\music-unlock\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\音乐解锁"; Filename: "{app}\music-unlock.exe"
Name: "{autodesktop}\音乐解锁"; Filename: "{app}\music-unlock.exe"

[Run]
Filename: "{app}\music-unlock.exe"; Description: "启动音乐解锁"; Flags: postinstall nowait skipifsilent
