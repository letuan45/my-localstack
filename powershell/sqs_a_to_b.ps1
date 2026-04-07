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

$payloadObj = @{
    device_id = "123123123123"
    imei = "111111111"
    tenant_id   = "/dev1"
}

$payloadJson = $payloadObj | ConvertTo-Json -Compress

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines("$(Get-Location)/input.json", $payloadJson, $utf8NoBom)

Write-Host "Invoking lambda_a with data: $payloadJson"

awslocal lambda invoke `
    --function-name lambda_a `
    --no-verify-ssl `
    --payload fileb://input.json `
    out.json | Out-Null

Start-Sleep -Seconds 2

foreach ($name in $LogGroups.Keys) {

    $LogGroup = $LogGroups[$name]
    $OutputFile = "$LogDir/$name.log"

    $StartTime = [DateTimeOffset]::UtcNow.AddSeconds(-10).ToUnixTimeMilliseconds()

    Write-Host "Fetching logs for $name..."

    $response = awslocal logs filter-log-events `
        --log-group-name $LogGroup `
        --start-time $StartTime `
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