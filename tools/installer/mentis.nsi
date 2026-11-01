; The Mentis Windows installer. Built by tools/build_windows_installer.py, which
; passes VERSION, FILE_VERSION, COMMIT, STAGE (the folder to install) and OUTFILE.
; Per user, no elevation. What it carries is declared in manifest.json, not here.
;
; It is not the Mark IV installer: that one registers as "Mentis" under
; %LOCALAPPDATA%\Mentis. This one registers as MentisServer under
; %LOCALAPPDATA%\Programs\Mentis, so neither can overwrite the other.

Unicode true
!include "MUI2.nsh"

!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\MentisServer"

Name "Mentis ${VERSION}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\Mentis"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails nevershow
ShowUninstDetails nevershow

VIProductVersion "${FILE_VERSION}"
VIAddVersionKey "ProductName" "Mentis"
VIAddVersionKey "ProductVersion" "${VERSION}+${COMMIT}"
VIAddVersionKey "FileVersion" "${FILE_VERSION}"
VIAddVersionKey "FileDescription" "Mentis server and Fluid setup"
VIAddVersionKey "LegalCopyright" ""

!define MUI_FINISHPAGE_RUN "$INSTDIR\mentis.cmd"
!define MUI_FINISHPAGE_RUN_PARAMETERS "open"
!define MUI_FINISHPAGE_RUN_TEXT "Set up and open Mentis now"

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Mentis"
  ; One install per Windows user: a second would take the first's uninstall entry.
  ReadRegStr $0 HKCU "${UNINST_KEY}" "InstallLocation"
  StrCmp $0 "" fresh
  StrCmp $0 $INSTDIR same
    MessageBox MB_OK|MB_ICONSTOP "Mentis is already installed in $0. Uninstall it first." /SD IDOK
    SetErrorLevel 3
    Quit
  same:
    IfFileExists "$INSTDIR\mentis.cmd" 0 fresh
    nsExec::Exec '"$INSTDIR\mentis.cmd" stop'
    Pop $1
    StrCmp $1 "0" +4
      MessageBox MB_OK|MB_ICONSTOP "Mentis is running and could not be stopped." /SD IDOK
      SetErrorLevel 4
      Quit
    RMDir /r "$INSTDIR\runtime"
    RMDir /r "$INSTDIR\app"
  fresh:

  SetOutPath "$INSTDIR"
  File /r "${STAGE}\*.*"
  WriteUninstaller "$INSTDIR\uninstall.exe"

  CreateDirectory "$SMPROGRAMS\Mentis"
  CreateShortcut "$SMPROGRAMS\Mentis\Mentis.lnk" "$INSTDIR\mentis.cmd" "open"
  CreateShortcut "$SMPROGRAMS\Mentis\Stop Mentis.lnk" "$INSTDIR\mentis.cmd" "stop"

  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "Mentis (server and Fluid)"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}+${COMMIT}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "Mentis"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  IfFileExists "$INSTDIR\mentis.cmd" 0 stopped
  nsExec::Exec '"$INSTDIR\mentis.cmd" stop'
  Pop $1
  StrCmp $1 "0" stopped
    MessageBox MB_OK|MB_ICONSTOP "Mentis is running and could not be stopped, so nothing was removed." /SD IDOK
    SetErrorLevel 4
    Quit
  stopped:

  ; Only what the installer and the launcher made. The Brain and the workspace
  ; are outside this folder (setup refuses otherwise) and stay.
  RMDir /r "$INSTDIR\runtime"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\state"
  Delete "$INSTDIR\mentis.cmd"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"

  Delete "$SMPROGRAMS\Mentis\Mentis.lnk"
  Delete "$SMPROGRAMS\Mentis\Stop Mentis.lnk"
  RMDir "$SMPROGRAMS\Mentis"
  DeleteRegKey HKCU "${UNINST_KEY}"
SectionEnd
