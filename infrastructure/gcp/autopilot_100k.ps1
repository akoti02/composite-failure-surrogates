$gcloud = 'C:\Users\akoti\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
$logFile = 'C:\CalculiX\test_composite\autopilot_100k.log'
$resultsDir = 'C:\CalculiX\test_composite\results_100k'
$zone = 'us-central1-f'

$vms = @(
    @{name='fea-runner-1'; vm=1; workers=100; logName='batch_100k_vm1.log'; csv='results_vm1.csv'},
    @{name='fea-runner-2'; vm=2; workers=100; logName='batch_100k_vm2.log'; csv='results_vm2.csv'},
    @{name='fea-runner-3'; vm=3; workers=100; logName='batch_100k_vm3.log'; csv='results_vm3.csv'},
    @{name='fea-runner-4'; vm=4; workers=50;  logName='batch_100k_vm4.log'; csv='results_vm4.csv'}
)

$completedVMs = @{}
$restartCounts = @{}
$stuckCounts = @{}
$lastSimCounts = @{}
foreach ($vm in $vms) {
    $restartCounts[$vm.name] = 0
    $stuckCounts[$vm.name] = 0
    $lastSimCounts[$vm.name] = 0
}

function Log($msg) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$ts] $msg"
    Add-Content -Path $logFile -Value $line -Encoding ASCII
    Write-Host $line
}

function RunOnVM($vmName, $cmd) {
    $result = & $gcloud compute ssh $vmName --zone=$zone --strict-host-key-checking=no --command=$cmd 2>&1
    return ($result -join "`n")
}

function RestartBatch($vmDef) {
    $vmName = $vmDef.name
    $vmNum = $vmDef.vm
    $workers = $vmDef.workers
    Log "ACTION: Restarting batch on $vmName (vm=$vmNum, workers=$workers)..."
    try {
        RunOnVM $vmName "pkill -f batch_100k 2>/dev/null; sleep 2; pkill -9 -f batch_100k 2>/dev/null; pkill -f ccx 2>/dev/null; sleep 1"
    } catch {}
    try {
        RunOnVM $vmName "sudo rm -rf /tmp/tmp* 2>/dev/null; sudo apt-get clean 2>/dev/null"
    } catch {}
    try {
        $launchCmd = "cd ~/sims && nohup python3 batch_100k.py --vm $vmNum --workers $workers > run.log 2>&1 & sleep 2 && echo LAUNCHED"
        $out = RunOnVM $vmName $launchCmd
        if ($out -match 'LAUNCHED') {
            Log "ACTION: $vmName restarted OK (attempt $($restartCounts[$vmName]))"
        } else {
            Log "ERROR: $vmName restart may have failed"
        }
    } catch {
        Log ("ERROR: $vmName restart exception: " + $_.Exception.Message)
    }
}

function DownloadResults($vmDef) {
    $vmName = $vmDef.name
    $csvName = $vmDef.csv
    Log "DOWNLOAD: Getting $csvName from $vmName..."
    if (-not (Test-Path $resultsDir)) { New-Item -ItemType Directory -Path $resultsDir -Force | Out-Null }
    try {
        & $gcloud compute scp "${vmName}:/home/akoti/sims/$csvName" "$resultsDir\$csvName" --zone=$zone --strict-host-key-checking=no 2>&1
        if (Test-Path "$resultsDir\$csvName") {
            $lineCount = (Get-Content "$resultsDir\$csvName" | Measure-Object).Count
            Log "DOWNLOAD: $csvName saved ($($lineCount - 1) data rows)"
            return $true
        }
    } catch {
        Log ("ERROR: Failed to download $csvName - " + $_.Exception.Message)
    }
    return $false
}

function StopVM($vmName) {
    Log "SHUTDOWN: Stopping $vmName to save cost..."
    try {
        & $gcloud compute instances stop $vmName --zone=$zone --quiet 2>&1
        Log "SHUTDOWN: $vmName stopped"
    } catch {
        Log ("ERROR: Failed to stop $vmName - " + $_.Exception.Message)
    }
}

function MergeResults {
    Log "MERGE: Combining all 4 CSV files..."
    $outFile = "$resultsDir\calculix_results_100k_merged.csv"
    $headerLine = $null
    $allDataRows = New-Object System.Collections.ArrayList
    foreach ($vm in $vms) {
        $csvPath = "$resultsDir\$($vm.csv)"
        if (Test-Path $csvPath) {
            $lines = Get-Content $csvPath
            if ($lines.Count -gt 1) {
                if (-not $headerLine) { $headerLine = $lines[0] }
                for ($i = 1; $i -lt $lines.Count; $i++) {
                    [void]$allDataRows.Add($lines[$i])
                }
            }
        }
    }
    if ($headerLine) {
        $headerLine | Out-File -FilePath $outFile -Encoding utf8
        $allDataRows | Out-File -FilePath $outFile -Append -Encoding utf8
        Log "MERGE: Combined CSV has $($allDataRows.Count) rows saved to $outFile"
    }
}

# ============================================================
Log "=========================================="
Log "AUTOPILOT 100K STARTED"
Log "Monitoring 4 VMs every 5 min"
Log "Auto-restart on crash, download on completion, stop VMs when done"
Log "=========================================="

while ($true) {
    $checkTime = Get-Date -Format 'HH:mm:ss'
    Log ""
    Log "--- CHECK at $checkTime ---"
    $allDone = $true
    $totalSimsDone = 0

    foreach ($vm in $vms) {
        $vmName = $vm.name
        if ($completedVMs[$vmName]) {
            Log ("  " + $vmName + " : DONE (downloaded + stopped)")
            $totalSimsDone += 25250
            continue
        }
        $allDone = $false

        try {
            $statusCmd = "tail -1 ~/sims/$($vm.logName) 2>/dev/null; echo XSEPX; wc -l ~/sims/$($vm.csv) 2>/dev/null || echo 0 none; echo XSEPX; df / --output=pcent | tail -1; echo XSEPX; ps aux | grep python3.batch_100k | grep -v grep | wc -l"
            $raw = RunOnVM $vmName $statusCmd
            $parts = $raw -split 'XSEPX'

            $lastLog = if ($parts.Count -gt 0) { $parts[0].Trim() } else { "?" }
            $csvPart = if ($parts.Count -gt 1) { $parts[1].Trim() } else { "0 none" }
            $diskPct = if ($parts.Count -gt 2) { $parts[2].Trim() } else { "?" }
            $procPart = if ($parts.Count -gt 3) { $parts[3].Trim() } else { "0" }

            $simsDone = 0
            if ($csvPart -match '^(\d+)') { $simsDone = [int]$Matches[1] - 1 }
            if ($simsDone -lt 0) { $simsDone = 0 }
            $totalSimsDone += $simsDone

            $procCount = 0
            if ($procPart -match '(\d+)') { $procCount = [int]$Matches[1] }

            $diskNum = 0
            if ($diskPct -match '(\d+)') { $diskNum = [int]$Matches[1] }

            # CHECK 1: Batch complete?
            if ($lastLog -match 'BATCH COMPLETE') {
                Log ("  " + $vmName + " : COMPLETE ($simsDone sims)")
                $ok = DownloadResults $vm
                if ($ok) {
                    $completedVMs[$vmName] = $true
                    StopVM $vmName
                }
                continue
            }

            # CHECK 2: Process alive?
            if ($procCount -eq 0 -and $simsDone -gt 0) {
                Log ("  " + $vmName + " : PROCESS DEAD ($simsDone sims, disk $diskPct)")
                $crashInfo = RunOnVM $vmName "tail -3 ~/sims/run.log 2>/dev/null"
                $crashOneLine = ($crashInfo -replace "`n", " | ").Trim()
                Log ("  " + $vmName + " crash: " + $crashOneLine)
                if ($restartCounts[$vmName] -lt 5) {
                    $restartCounts[$vmName]++
                    RestartBatch $vm
                } else {
                    Log ("  " + $vmName + " : MAX RESTARTS (5) reached")
                }
                continue
            }

            # CHECK 3: Disk > 90%?
            if ($diskNum -gt 90) {
                Log ("  " + $vmName + " : DISK WARNING ($diskPct) - cleaning")
                RunOnVM $vmName "sudo rm -rf /tmp/tmp* 2>/dev/null; sudo apt-get clean 2>/dev/null"
            }

            # CHECK 4: Progress stalled for 15+ min?
            if ($simsDone -eq $lastSimCounts[$vmName] -and $simsDone -gt 0 -and $lastLog -notmatch 'polygon') {
                $stuckCounts[$vmName]++
                if ($stuckCounts[$vmName] -ge 3) {
                    Log ("  " + $vmName + " : STUCK at $simsDone for 15+ min - restarting")
                    if ($restartCounts[$vmName] -lt 5) {
                        $restartCounts[$vmName]++
                        RestartBatch $vm
                    }
                    $stuckCounts[$vmName] = 0
                }
            } else {
                $stuckCounts[$vmName] = 0
            }
            $lastSimCounts[$vmName] = $simsDone

            Log ("  " + $vmName + " : " + $simsDone + " sims  disk=" + $diskPct + "  procs=" + $procCount + "  " + $lastLog)

        } catch {
            Log ("  " + $vmName + " : CONNECTION ERROR - " + $_.Exception.Message)
        }
    }

    $pct = [math]::Round(($totalSimsDone / 101000) * 100, 1)
    Log ("  TOTAL: " + $totalSimsDone + " / 101,000 (" + $pct + "%)")

    if ($allDone) {
        Log ""
        Log "=========================================="
        Log "ALL 4 VMs COMPLETE"
        Log "=========================================="
        MergeResults
        Log "AUTOPILOT FINISHED - results downloaded, VMs stopped, CSV merged"
        break
    }

    Start-Sleep -Seconds 300
}
