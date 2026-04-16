$LogGroups = @{
    "lambda_a" = "/aws/lambda/lambda_a"
    "lambda_b" = "/aws/lambda/lambda_b"
}

$env:PYTHONWARNINGS = "ignore:Unverified HTTPS request"
$env:AWS_CA_BUNDLE = $null
$env:PYTHONWARNINGS = "ignore"
$env:AWS_EXECUTION_ENV = "localstack"

# ==============================
# 🧹 Clean logs folder
# ==============================
$logDir = "./logs"

if (Test-Path $logDir) {
    Write-Host "Cleaning old logs..."
    Remove-Item "$logDir/*.log" -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "Creating logs folder..."
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

Write-Host "--- STARTING SQS BATCH TEST ---"

# ==============================
# 📦 PAYLOAD TO LAMBDA A
# ==============================
$payloadObj = @{
    target_destination = "http://localhost:4566/000000000000/my_queue"
    simulate_batch     = $true
    devices            = @(
        @{ device_id = "DEV_001"; device_imeis = @("111", "222") },
        @{ device_id = "DEV_002"; device_imeis = @("333") },
        @{ device_id = "DEV_003"; device_imeis = @("444", "555") }
    )
}

$payloadJson = $payloadObj | ConvertTo-Json -Depth 3 -Compress
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines("$(Get-Location)/input.json", $payloadJson, $utf8NoBom)

Write-Host "Invoking lambda_a to simulate SQS batch..."
Write-Host "Payload: $payloadJson"

# ==============================
# 🚀 INVOKE LAMBDA A
# ==============================
awslocal lambda invoke `
    --function-name lambda_a `
    --no-verify-ssl `
    --payload fileb://input.json `
    out.json | Out-Null

Write-Host "Waiting for SQS Batching Window to trigger Lambda B (12s)..."
Start-Sleep -Seconds 12

# ==============================
# 📝 FETCH LOGS
# ==============================
foreach ($name in $LogGroups.Keys) {
    $LogGroup = $LogGroups[$name]
    $OutputFile = "$LogDir/$name.log"
    $StartTime = [DateTimeOffset]::UtcNow.AddSeconds(-60).ToUnixTimeMilliseconds()

    Write-Host "Fetching logs for $name..."

    $response = awslocal logs filter-log-events `
        --log-group-name $LogGroup `
        --start-time $StartTime `
        --no-verify-ssl `
        --output json | ConvertFrom-Json

    if ($response.events.Count -gt 0) {
        foreach ($event in $response.events) {
            $event.message | Out-File -FilePath $OutputFile -Append
        }
        Write-Host "Updated $name logs"
    } else {
        Write-Host "No new logs for $name"
    }
}