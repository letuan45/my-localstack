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
$LogDir = "./logs"

if (Test-Path $LogDir) {
    Write-Host "Cleaning old logs..."
    Remove-Item "$LogDir/*.log" -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "Creating logs folder..."
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

Write-Host "--- TRACING SQS SINGLE MESSAGE ---"

# ==============================
# 📦 PAYLOAD TO LAMBDA A
# ==============================
$payloadObj = @{
    target_destination = "http://localhost:4566/000000000000/my_queue"
    simulate_batch     = $false
    device_id = "123123123123"
    device_imeis = @("111111111", "222222222")
    tenant_id = "/dev1"
}

$payloadJson = $payloadObj | ConvertTo-Json -Compress
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines("$(Get-Location)/input.json", $payloadJson, $utf8NoBom)

Write-Host "Invoking lambda_a to send SQS message..."
Write-Host "Payload: $payloadJson"

# ==============================
# 🚀 INVOKE LAMBDA A
# ==============================
awslocal lambda invoke `
    --function-name lambda_a `
    --no-verify-ssl `
    --payload fileb://input.json `
    out.json | Out-Null

Write-Host "Waiting for SQS delivery to Lambda B (5s)..."
Start-Sleep -Seconds 5

# ==============================
# 📝 FETCH LOGS
# ==============================
foreach ($name in $LogGroups.Keys) {
    $LogGroup = $LogGroups[$name]
    $OutputFile = "$LogDir/$name.log"

    $StartTime = [DateTimeOffset]::UtcNow.AddMinutes(-1).ToUnixTimeMilliseconds()

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
        Write-Host "Done: $name"
    } else {
        Write-Host "No new logs for $name"
    }
}