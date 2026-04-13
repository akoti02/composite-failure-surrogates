$paths = @(
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
foreach ($p in $paths) {
    Get-ItemProperty $p -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match 'RP3' } | ForEach-Object {
        Write-Output "FOUND in registry: $($_.DisplayName) at $($_.PSPath)"
        Write-Output "  InstallLocation: $($_.InstallLocation)"
        Write-Output "  UninstallString: $($_.UninstallString)"
    }
}
Write-Output "Registry scan done"
