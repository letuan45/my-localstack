$LogGroups = @{
    "lambda_a" = "/aws/lambda/lambda_a"
    "lambda_b" = "/aws/lambda/lambda_b"
}

$LogDir = "./logs"
if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

Write-Host "Invoking lambda_a..."
awslocal lambda invoke --function-name lambda_a out.json | Out-Null

Start-Sleep -Seconds 2

foreach ($name in $LogGroups.Keys) {

    $LogGroup = $LogGroups[$name]
    $OutputFile = "$LogDir/$name.log"

    # 🔥 FIX: lấy log trong 10s gần nhất
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