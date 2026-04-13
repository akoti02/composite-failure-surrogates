$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\RP3.lnk")
$Shortcut.TargetPath = "C:\Users\akoti\University RP3 - Composite Failure Surrogate Modelling\rp3-app\src-tauri\target\release\rp3.exe"
$Shortcut.WorkingDirectory = "C:\Users\akoti\University RP3 - Composite Failure Surrogate Modelling\rp3-app\src-tauri\target\release"
$Shortcut.IconLocation = "C:\Users\akoti\University RP3 - Composite Failure Surrogate Modelling\rp3-app\src-tauri\icons\icon.ico,0"
$Shortcut.Description = "RP3 Composite Failure Surrogate"
$Shortcut.Save()
Write-Output "Shortcut created at: $env:APPDATA\Microsoft\Windows\Start Menu\Programs\RP3.lnk"
