param(
  [string]$Date = (Get-Date -Format 'yyyy-MM-dd'),
  [string]$ProjectRoot = $PSScriptRoot,
  [int]$DebugPort = 9222,
  [string]$PluginExtensionId = 'eckpehelplpholpddkpmihfigodplkdp',
  [string]$PluginUrl = '',
  [string]$PluginOptionsUrl = '',
  [int]$ScrapeTimeoutMinutes = 240,
  [int]$PluginCompletionTimeoutMinutes = 0,
  [switch]$SkipScrape,
  [switch]$SkipPlugin,
  [switch]$NoStartPluginTask,
  [switch]$NoExportPluginResult,
  [switch]$RequireInputToday,
  [switch]$SkipBlogAnalysis,
  [string]$CsvPath = '',
  [string]$PluginOutputDir = '',
  [string]$BlogAnalysisInputDir = '',
  [int]$BlogAnalysisMaxPages = 0,
  [string[]]$PluginStartSelector = @()
)

$ErrorActionPreference = 'Stop'

if (-not $PluginUrl) {
  $PluginUrl = "chrome-extension://$PluginExtensionId/batch.html"
}
if (-not $PluginOptionsUrl) {
  $PluginOptionsUrl = "chrome-extension://$PluginExtensionId/options.html"
}

function Write-Step {
  param([string]$Message)
  $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
  Write-Host "[$stamp] $Message"
}

function Wait-DebugPort {
  param(
    [int]$Port,
    [int]$TimeoutSeconds = 60
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/version" -TimeoutSec 3
      if ($response.webSocketDebuggerUrl) {
        return $true
      }
    } catch {
      Start-Sleep -Seconds 1
    }
  }
  return $false
}

function Invoke-CheckedProcess {
  param(
    [string]$FilePath,
    [string[]]$Arguments,
    [int]$TimeoutMinutes = 0
  )

  $displayArgs = ($Arguments -join ' ')
  Write-Step "Running: $FilePath $displayArgs"

  if ($TimeoutMinutes -le 0) {
    & $FilePath @Arguments
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) {
      $exitCode = 0
    }
    if ($exitCode -ne 0) {
      throw "Process failed with exit code ${exitCode}: $FilePath $displayArgs"
    }
    return
  }

  $resolved = Get-Command $FilePath -ErrorAction SilentlyContinue
  $resolvedPath = if ($resolved -and $resolved.Source) { $resolved.Source } else { $FilePath }
  $escapedArgs = $Arguments | ForEach-Object {
    $arg = [string]$_
    if ($arg -match '[\s"]') {
      '"' + ($arg -replace '\\', '\\' -replace '"', '\"') + '"'
    } else {
      $arg
    }
  }

  $startInfo = New-Object System.Diagnostics.ProcessStartInfo
  $startInfo.FileName = $resolvedPath
  $startInfo.Arguments = ($escapedArgs -join ' ')
  $startInfo.WorkingDirectory = $ProjectRoot
  $startInfo.UseShellExecute = $false

  $process = New-Object System.Diagnostics.Process
  $process.StartInfo = $startInfo
  if (-not $process.Start()) {
    throw "Failed to start process: $FilePath $displayArgs"
  }

  $completed = $process.WaitForExit($TimeoutMinutes * 60 * 1000)
  if (-not $completed) {
    try { $process.Kill() } catch {}
    throw "Process timed out after $TimeoutMinutes minutes: $FilePath $displayArgs"
  }

  if ($process.ExitCode -ne 0) {
    throw "Process failed with exit code $($process.ExitCode): $FilePath $displayArgs"
  }
}

function Wait-StableFiles {
  param(
    [string]$Directory,
    [string]$Pattern,
    [int]$TimeoutSeconds = 300,
    [int]$StableSeconds = 10
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  $lastSignature = ''
  $stableSince = $null

  while ((Get-Date) -lt $deadline) {
    $partialDownloads = Get-ChildItem -Path $Directory -Filter '*.crdownload' -ErrorAction SilentlyContinue
    $files = Get-ChildItem -Path $Directory -Filter $Pattern -ErrorAction SilentlyContinue | Sort-Object Name

    if ($files.Count -gt 0 -and $partialDownloads.Count -eq 0) {
      $signature = ($files | ForEach-Object { "$($_.Name):$($_.Length):$($_.LastWriteTimeUtc.Ticks)" }) -join '|'
      if ($signature -eq $lastSignature) {
        if ($null -eq $stableSince) {
          $stableSince = Get-Date
        }
        if (((Get-Date) - $stableSince).TotalSeconds -ge $StableSeconds) {
          return $files
        }
      } else {
        $lastSignature = $signature
        $stableSince = $null
      }
    }

    Start-Sleep -Seconds 2
  }

  throw "Timed out waiting for stable files: $Directory\$Pattern"
}

$ProjectRoot = (Resolve-Path $ProjectRoot).Path
Set-Location $ProjectRoot

$logsDir = Join-Path $ProjectRoot 'logs'
$null = New-Item -ItemType Directory -Force -Path $logsDir
$logFile = Join-Path $logsDir "daily_workflow_$Date.log"

Start-Transcript -Path $logFile -Append | Out-Null

try {
  Write-Step "Workflow started for $Date"

  $inputFile = Join-Path $ProjectRoot 'data\input.xlsx'
  if (-not (Test-Path $inputFile)) {
    throw "Missing input file: $inputFile"
  }

  $inputInfo = Get-Item $inputFile
  Write-Step "Input file: $inputFile (LastWriteTime: $($inputInfo.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')))"
  if ($RequireInputToday -and $inputInfo.LastWriteTime.Date -ne (Get-Date).Date) {
    throw "input.xlsx was not updated today. Use without -RequireInputToday to allow stale input."
  }

  $startChromeBat = Join-Path $ProjectRoot 'start_chrome_debug.bat'
  if (-not (Test-Path $startChromeBat)) {
    throw "Missing Chrome debug script: $startChromeBat"
  }

  Write-Step "Starting Chrome debug session"
  Invoke-CheckedProcess -FilePath 'cmd.exe' -Arguments @('/c', "`"$startChromeBat`"")

  if (-not (Wait-DebugPort -Port $DebugPort -TimeoutSeconds 90)) {
    throw "Chrome debug port $DebugPort did not become ready."
  }
  Write-Step "Chrome debug port $DebugPort is ready"

  if (-not $SkipScrape) {
    Invoke-CheckedProcess -FilePath 'python' -Arguments @('main.py', '--mode', 'full', '--date', $Date) -TimeoutMinutes $ScrapeTimeoutMinutes

    $downloadDir = Join-Path $ProjectRoot 'data\downloads'
    Write-Step "Waiting for exported CSV downloads to settle"
    $downloaded = Wait-StableFiles -Directory $downloadDir -Pattern "backlinks_export_$Date*.csv" -TimeoutSeconds 600 -StableSeconds 10
    Write-Step "Detected $($downloaded.Count) stable exported CSV files"
  } else {
    Write-Step "Skipping scrape step"
  }

  Write-Step "Running final merge for $Date"
  Invoke-CheckedProcess -FilePath 'python' -Arguments @('merge_only.py', '--date', $Date)

  if ([string]::IsNullOrWhiteSpace($CsvPath)) {
    $CsvPath = Join-Path $ProjectRoot "data\backlinks_merged_$Date.csv"
  } elseif (-not [System.IO.Path]::IsPathRooted($CsvPath)) {
    $CsvPath = Join-Path $ProjectRoot $CsvPath
  }

  if (-not (Test-Path $CsvPath)) {
    throw "Merged CSV was not created: $CsvPath"
  }
  Write-Step "Merged CSV ready: $CsvPath"

  if ([string]::IsNullOrWhiteSpace($PluginOutputDir)) {
    $PluginOutputDir = Join-Path $ProjectRoot 'data\output'
  } elseif (-not [System.IO.Path]::IsPathRooted($PluginOutputDir)) {
    $PluginOutputDir = Join-Path $ProjectRoot $PluginOutputDir
  }
  $null = New-Item -ItemType Directory -Force -Path $PluginOutputDir

  if ([string]::IsNullOrWhiteSpace($BlogAnalysisInputDir)) {
    $BlogAnalysisInputDir = Join-Path $ProjectRoot 'data\input'
  } elseif (-not [System.IO.Path]::IsPathRooted($BlogAnalysisInputDir)) {
    $BlogAnalysisInputDir = Join-Path $ProjectRoot $BlogAnalysisInputDir
  }
  $null = New-Item -ItemType Directory -Force -Path $BlogAnalysisInputDir

  if (-not $SkipPlugin) {
    if (-not (Wait-DebugPort -Port $DebugPort -TimeoutSeconds 30)) {
      Write-Step "Chrome debug port is not ready after merge; starting Chrome again"
      Invoke-CheckedProcess -FilePath 'cmd.exe' -Arguments @('/c', "`"$startChromeBat`"")
      if (-not (Wait-DebugPort -Port $DebugPort -TimeoutSeconds 90)) {
        throw "Chrome debug port $DebugPort did not become ready before plugin upload."
      }
    }

    $pluginArgs = @(
      'extension_batch_upload.py',
      '--csv', $CsvPath,
      '--url', $PluginUrl,
      '--options-url', $PluginOptionsUrl,
      '--port', "$DebugPort",
      '--output-dir', $PluginOutputDir,
      '--completion-timeout-minutes', "$PluginCompletionTimeoutMinutes"
    )

    if (-not $SkipBlogAnalysis -and -not $NoStartPluginTask) {
      $pluginArgs += @(
        '--analyze-opened-blogs',
        '--blog-analysis-input-dir', $BlogAnalysisInputDir,
        '--blog-analysis-input-xlsx', $inputFile
      )
    }

    foreach ($selector in $PluginStartSelector) {
      if (-not [string]::IsNullOrWhiteSpace($selector)) {
        $pluginArgs += @('--start-selector', $selector)
      }
    }

    if ($BlogAnalysisMaxPages -gt 0) {
      $pluginArgs += @('--blog-analysis-max-pages', "$BlogAnalysisMaxPages")
    }

    if ($NoStartPluginTask) {
      $pluginArgs += '--no-start'
    }

    if ($NoExportPluginResult) {
      $pluginArgs += '--no-export'
    }

    Invoke-CheckedProcess -FilePath 'python' -Arguments $pluginArgs
  } else {
    Write-Step "Skipping plugin step"
  }

  Write-Step "Workflow completed successfully"
}
finally {
  Stop-Transcript | Out-Null
}
