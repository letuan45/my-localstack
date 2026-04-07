$LogGroups = @{
    "lambda_a" = "/aws/lambda/lambda_a"
    "lambda_b" = "/aws/lambda/lambda_b"
}

$env:PYTHONWARNINGS = "ignore:Unverified HTTPS request"
$env:AWS_CA_BUNDLE = $null
$env:PYTHONWARNINGS = "ignore"
$env:AWS_EXECUTION_ENV = "localstack"

$LogDir = "./logs"
if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

$devices = @(
    @{ device_id = "DEV_001"; imei = "111"; tenant_id = "/test1" },
    @{ device_id = "DEV_002"; imei = "222"; tenant_id = "/test2" },
    @{ device_id = "DEV_003"; imei = "333"; tenant_id = "/test3" }
)

Write-Host "--- STARTING BATCH TEST ---"

foreach ($dev in $devices) {
    $payloadJson = $dev | ConvertTo-Json -Compress

    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllLines("$(Get-Location)/input.json", $payloadJson, $utf8NoBom)

    Write-Host "Invoking lambda_a for device: $($dev.device_id)"

    awslocal lambda invoke `
        --function-name lambda_a `
        --no-verify-ssl `
        --payload fileb://input.json `
        out.json | Out-Null
}

Write-Host "Waiting for SQS Batching Window (10s)..."
Start-Sleep -Seconds 12

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