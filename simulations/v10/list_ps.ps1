Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
    Select-Object ProcessId, CreationDate,
        @{N='Cmd';E={if($_.CommandLine.Length -gt 100){$_.CommandLine.Substring(0,100)+'...'}else{$_.CommandLine}}} |
    Sort-Object CreationDate |
    Format-Table -AutoSize
