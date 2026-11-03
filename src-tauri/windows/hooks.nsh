; FANBOX Archiver NSIS hooks.

!macro NSIS_HOOK_PREUNINSTALL
  ; Remove the per-user background backup tasks; archives and settings are kept.
  ; The app re-creates them on its next start if it is installed again.
  nsExec::Exec 'schtasks /Delete /TN "FANBOX Archiver\Scheduled Backup Wake" /F'
  Pop $0
  nsExec::Exec 'schtasks /Delete /TN "FANBOX Archiver\Scheduled Backup" /F'
  Pop $0
!macroend
