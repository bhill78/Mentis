; The Mentis Windows installer. Built by tools/build_windows_installer.py, which
; passes VERSION, FILE_VERSION, COMMIT, STAGE (one release), CMD_FILE (mentis.cmd) and OUTFILE.
; Per user, no elevation. What it carries is declared in manifest.json, not here.
;
; It unpacks the release into $INSTDIR\.incoming and hands over to that release's own
; launcher (`arrive`, tools/installer/updater.py), which decides between a first
; install, the same build over itself and an update, and checks everything. So this is
; the same transaction as `mentis.cmd update`, and needs nothing of what is here.
; `/EXTRACT=<dir>` only unpacks: it is how `mentis.cmd update` reads this exe.
;
; It is not the Mark IV installer: that one registers as "Mentis" under
; %LOCALAPPDATA%\Mentis. This one registers as MentisServer under
; %LOCALAPPDATA%\Programs\Mentis, so neither can overwrite the other.

Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"

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
  ${GetParameters} $R9
  ClearErrors
  ${GetOptions} $R9 "/EXTRACT=" $R8
  IfErrors install
    SetOutPath $R8
    File /r "${STAGE}\*.*"
    SetErrorLevel 0  ; Quit in a section otherwise says 2, aborted
    Quit
  install:

  ; One install per Windows user: a second would take the first's uninstall entry.
  ReadRegStr $0 HKCU "${UNINST_KEY}" "InstallLocation"
  StrCmp $0 "" ours
  StrCmp $0 $INSTDIR ours
    MessageBox MB_OK|MB_ICONSTOP "Mentis is already installed in $0. Uninstall it first." /SD IDOK
    SetErrorLevel 2
    Quit
  ours:

  StrCpy $1 "$INSTDIR\.incoming"
  RMDir /r "$1"
  SetOutPath "$1"
  File /r "${STAGE}\*.*"
  SetOutPath "$INSTDIR"

  ; A person is shown what it would do, Brain migrations included; /S was told already.
  IfSilent arrive
  nsExec::ExecToStack '"$1\runtime\python.exe" -I -X utf8 "$1\app\launcher.py" arrive --root "$INSTDIR" --plan'
  Pop $2
  Pop $3
  StrCmp $2 "0" 0 refused
  StrCmp $3 "" arrive
  MessageBox MB_YESNO|MB_ICONQUESTION "$3$\r$\n$\r$\nGo ahead?" /SD IDYES IDYES arrive
    RMDir /r "$1"
    SetErrorLevel 2
    Quit

  arrive:
  nsExec::ExecToStack '"$1\runtime\python.exe" -I -X utf8 "$1\app\launcher.py" arrive --root "$INSTDIR" --yes'
  Pop $2
  Pop $3
  StrCmp $2 "0" arrived
  refused:
    RMDir /r "$1"
    MessageBox MB_OK|MB_ICONSTOP "$3" /SD IDOK
    SetErrorLevel $2
    Quit
  arrived:
  RMDir /r "$1"

  File "/oname=$INSTDIR\mentis.cmd" "${CMD_FILE}"
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
  ; Nothing to stop without this, and a broken mentis.cmd must not keep an uninstall out.
  IfFileExists "$INSTDIR\state\running.json" 0 stopped
  nsExec::Exec '"$INSTDIR\mentis.cmd" stop'
  Pop $1
  StrCmp $1 "0" stopped
    MessageBox MB_OK|MB_ICONSTOP "Mentis is running and could not be stopped, so nothing was removed." /SD IDOK
    SetErrorLevel 4
    Quit
  stopped:

  ; Only what the installer and the launcher made. The Brain and the workspace
  ; are outside this folder (setup refuses otherwise) and stay. Each release is
  ; locked read-only (mentis.readonly): that deny entry goes first.
  ExpandEnvStrings $2 "%USERNAME%"
  nsExec::Exec 'icacls "$INSTDIR\releases" /remove:d "$2" /T /C /Q'
  Pop $1
  RMDir /r "$INSTDIR\releases"
  RMDir /r "$INSTDIR\.incoming"
  RMDir /r "$INSTDIR\state"
  Delete "$INSTDIR\mentis.cmd"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"

  Delete "$SMPROGRAMS\Mentis\Mentis.lnk"
  Delete "$SMPROGRAMS\Mentis\Stop Mentis.lnk"
  RMDir "$SMPROGRAMS\Mentis"
  DeleteRegKey HKCU "${UNINST_KEY}"
SectionEnd
