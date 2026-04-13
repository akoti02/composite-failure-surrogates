$gcloud = 'C:\Users\akoti\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
$logFile = 'C:\CalculiX\test_composite\monitor_100k.log'
$vms = @(
    @{name='fea-runner-1'; logName='batch_100k_vm1.log'; csv='results_vm1.csv'},
    @{name='fea-runner-2'; logName='batch_100k_vm2.log'; csv='results_vm2.csv'},
    @{name='fea-runner-3'; logName='batch_100k_vm3.log'; csv='results_vm3.csv'},
    @{name='fea-runner-4'; logName='batch_100k_vm4.log'; csv='results_vm4.csv'}
)

$completed = @{}

while ($true) {
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $allDone = $true
    $totalSims = 0
    $report = "`n========== MONITOR CHECK: $timestamp ==========`n"

    foreach ($vm in $vms) {
        if ($completed[$vm.name]) {
            $report += "  $($vm.name): COMPLETED`n"
            $totalSims += 25250
            continue
        }

        try {
            $cmd = "tail -1 ~/sims/$($vm.logName) 2>/dev/null && echo '|||' && wc -l ~/sims/$($vm.csv) 2>/dev/null && echo '|||' && df -h / | tail -1 && echo '|||' && ps aux | grep '[b]atch_100k' | wc -l"
            $result = & $gcloud compute ssh $vm.name --zone=us-central1-f --strict-host-key-checking=no --command=$cmd 2>&1
            $output = $result -join "`n"

            # Parse CSV line count
            if ($output -match '(\d+)\s+/home') {
                $csvLines = [int]$Matches[1] - 1  # subtract header
                $totalSims += $csvLines
            }

            # Check if process is still running
            $parts = $output -split '\|\|\|'
            $lastLog = ($parts[0] -replace "`n","").Trim()

            # Check for BATCH COMPLETE in log
            if ($lastLog -match 'BATCH COMPLETE') {
                $completed[$vm.name] = $true
                $report += "  $($vm.name): FINISHED! $lastLog`n"
            } else {
                $allDone = $false
                $report += "  $($vm.name): $lastLog`n"
            }
        } catch {
            $allDone = $false
            $report += "  $($vm.name): ERROR checking - $($_.Exception.Message)`n"
        }
    }

    $report += "  --- TOTAL SIMS: ~$totalSims / 101,000 ---`n"
    $report += "================================================`n"

    # Write to log and console
    Add-Content -Path $logFile -Value $report
    Write-Host $report

    if ($allDone) {
        $finalMsg = "`n*** ALL 4 VMs COMPLETE! Total: ~$totalSims sims ***`n"
        Add-Content -Path $logFile -Value $finalMsg
        Write-Host $finalMsg
        break
    }

    # Sleep 5 minutes
    Start-Sleep -Seconds 300
}
