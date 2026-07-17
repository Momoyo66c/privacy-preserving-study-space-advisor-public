param(
  [int]$Port = 18000,
  [string]$ImageName = "study-space-api:module3-smoke"
)

$ErrorActionPreference = "Stop"
$containerName = "study-space-api-smoke-$PID"

docker version | Out-Null
docker build --tag $ImageName .
$containerId = docker run --detach --name $containerName --publish "${Port}:8000" $ImageName

try {
  $deadline = (Get-Date).AddSeconds(45)
  do {
    try {
      $health = Invoke-RestMethod -Uri "http://127.0.0.1:${Port}/health" -TimeoutSec 2
      if ($health.database -eq "ok") {
        Write-Output "Docker smoke passed: database=$($health.database), adapter=$($health.recommendation_adapter.mode)"
        exit 0
      }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while ((Get-Date) -lt $deadline)

  throw "Container did not become healthy within 45 seconds."
} finally {
  docker logs $containerName
  docker rm --force $containerName | Out-Null
}
