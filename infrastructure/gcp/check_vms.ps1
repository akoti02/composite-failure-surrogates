param([int]$DelaySeconds = 300)
Start-Sleep -Seconds $DelaySeconds
Write-Host @"
WAKE_UP_MONITOR — 100K SIMULATON MONITOR

YOU ARE MONITORING 4 GCP VMs running CalculiX FEA batch simulations.
Each VM runs batch_100k.py with nohup. Total target: 101,000 sims.

VMs:
  fea-runner-1  c2d-112  --vm 1 --workers 100  sims 1-25250
  fea-runner-2  c2d-112  --vm 2 --workers 100  sims 25251-50500
  fea-runner-3  c2d-112  --vm 3 --workers 100  sims 50501-75750
  fea-runner-4  c2d-56   --vm 4 --workers 50   sims 75751-101000
  Zone: us-central1-f

YOUR TASKS EVERY 5 MINUTES:
1. SSH into each VM and check: last log line, CSV line count, disk %, RAM, process count
2. Verify zero errors, processes alive, disk not filling, RAM available > 10GB
3. If a VM process died: restart with same command (resume picks up from CSV)
4. If a VM finished (BATCH COMPLETE in log): download CSV, then stop VM to save cost
5. When ALL 4 done: download all CSVs to C:\CalculiX\test_composite\results_100k\, merge them, stop all VMs
6. ALWAYS set a new 5-min alarm after checking
7. If user messages you: kill current alarm, handle user, then set fresh 5-min alarm

SSH helper: powershell.exe -ExecutionPolicy Bypass -File "C:\CalculiX\test_composite\run_on_vm.ps1" -VM <name> -Cmd "<command>"
Alarm: powershell.exe -ExecutionPolicy Bypass -File "C:\CalculiX\test_composite\check_vms.ps1" -DelaySeconds 300

Download command:
  gcloud compute scp fea-runner-N:/home/akoti/sims/results_vmN.csv C:\CalculiX\test_composite\results_100k\ --zone=us-central1-f

Stop VM command:
  gcloud compute instances stop fea-runner-N --zone=us-central1-f --quiet
"@
