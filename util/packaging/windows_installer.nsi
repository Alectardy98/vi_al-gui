; Offline, per-user installation. Keyboard settings and add-ons are preserved.
Unicode True
!include "MUI2.nsh"
!include "x64.nsh"
Name "Vi_al"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\Vi_al"
InstallDirRegKey HKCU "Software\Vi_al\Installer" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "Vi_al"
VIAddVersionKey "FileDescription" "Vi_al Setup"
VIAddVersionKey "CompanyName" "Alectardy98"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "Vi_al contributors; based on Vial"
!define MUI_ICON "${APPICON}"
!define MUI_UNICON "${APPICON}"
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "Vi_al requires 64-bit Windows."
    Abort
  ${EndIf}
  SetShellVarContext current
  SetRegView 64
FunctionEnd

Section "Vi_al"
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD}\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Vi_al"
  CreateShortcut "$SMPROGRAMS\Vi_al\Vi_al.lnk" "$INSTDIR\Vi_al.exe" "" "$INSTDIR\Vi_al.exe"
  WriteRegStr HKCU "Software\Vi_al\Installer" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Vi_al" "DisplayName" "Vi_al"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Vi_al" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Vi_al" "Publisher" "Alectardy98"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Vi_al" "DisplayIcon" "$INSTDIR\Vi_al.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Vi_al" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Vi_al" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Vi_al" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  SetRegView 64
  ; Remove only the known payload; never recursively delete a chosen directory.
  !include "${UNINSTALL_FILES}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$SMPROGRAMS\Vi_al\Vi_al.lnk"
  RMDir "$SMPROGRAMS\Vi_al"
  DeleteRegKey HKCU "Software\Vi_al\Installer"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Vi_al"
SectionEnd
