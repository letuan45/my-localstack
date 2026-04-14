$LogGroups = @{
    "lambda_a" = "/aws/lambda/lambda_a"
    "lambda_b" = "/aws/lambda/lambda_b"
    "lambda_c" = "/aws/lambda/lambda_c"
}

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

$payloadObj = @{
    device_id = "SNS_FANOUT_TEST"
    imei      = "999999"
    tenant_id = "/prod"
}

$payloadJson = $payloadObj | ConvertTo-Json -Compress
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines("$(Get-Location)/input.json", $payloadJson, $utf8NoBom)

Write-Host "--- TRACING SNS FAN-OUT ---"
Write-Host "Invoking lambda_a to publish to SNS Topic..."

# Gọi lambda_a
awslocal lambda invoke `
    --function-name lambda_a `
    --no-verify-ssl `
    --payload fileb://input.json `
    out.json | Out-Null

Write-Host "Waiting for SNS to fan-out to B and C (20s)..."
Start-Sleep -Seconds 20

# Fetch logs cho cả 3 Lambda
foreach ($name in $LogGroups.Keys) {
    $LogGroup = $LogGroups[$name]
    $StartTime = [DateTimeOffset]::UtcNow.AddMinutes(-5).ToUnixTimeMilliseconds()

    Write-Host "Fetching logs for $name..."
    $response = awslocal logs filter-log-events --log-group-name $LogGroup --start-time $StartTime --no-verify-ssl --output json | ConvertFrom-Json

    if ($response.events.Count -gt 0) {
        $response.events.message | Out-File -FilePath "./logs/$name.log" -Append
        Write-Host "Done: $name"
    }
}