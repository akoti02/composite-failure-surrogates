param(
    [string]$VM,
    [string]$Cmd
)
& 'C:\Users\akoti\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd' compute ssh $VM --zone=us-central1-f --strict-host-key-checking=no --command=$Cmd
