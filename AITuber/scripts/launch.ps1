<#
.SYNOPSIS
    AITuber 配信ランチャー — 全コンポーネントを一括起動

.DESCRIPTION
    1. VOICEVOX エンジンを起動（未起動の場合）
    2. Orchestrator を起動（テスト or 本番）
    3. ビルド済み .exe があればそちらを起動 / なければ Unity エディタ Play を案内

.PARAMETER Mode
    "test"  : ローカルテスト配信（YouTube 不要、コンソールでチャット入力）
    "live"  : 本番配信（YouTube LiveChat 接続）
    デフォルト: test

.PARAMETER UseEditor
    ビルド済み .exe があっても Unity エディタを使う場合に指定。

.EXAMPLE
    .\scripts\launch.ps1              # テスト配信（.exe優先）
    .\scripts\launch.ps1 -Mode live   # 本番配信
    .\scripts\launch.ps1 -UseEditor   # エディタモード強制
#>

param(
    [ValidateSet("test", "live")]
    [string]$Mode = "test",
    [switch]$UseEditor
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AITuber 配信ランチャー ($Mode モード)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. VOICEVOX 起動確認 ────────────────────────────────────────────

Write-Host "[1/3] VOICEVOX エンジン確認中..." -ForegroundColor Yellow

$voicevoxReady = $false
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:50021/version" -TimeoutSec 2 -ErrorAction Stop
    Write-Host "  [OK] VOICEVOX 起動済み (version: $($response.Content.Trim()))" -ForegroundColor Green
    $voicevoxReady = $true
} catch {
    Write-Host "  [...] VOICEVOX を起動します..." -ForegroundColor Yellow

    # VOICEVOX のよくあるインストール先を探す
    $voicevoxPaths = @(
        "$env:LOCALAPPDATA\Programs\VOICEVOX\VOICEVOX.exe",
        "$env:ProgramFiles\VOICEVOX\VOICEVOX.exe",
        "${env:ProgramFiles(x86)}\VOICEVOX\VOICEVOX.exe",
        "$env:USERPROFILE\Desktop\VOICEVOX\VOICEVOX.exe",
        "C:\VOICEVOX\VOICEVOX.exe"
    )

    $voicevoxExe = $null
    foreach ($p in $voicevoxPaths) {
        if (Test-Path $p) {
            $voicevoxExe = $p
            break
        }
    }

    if (-not $voicevoxExe) {
        # プロセスから探す
        $vvProc = Get-Process -Name "VOICEVOX*" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($vvProc) {
            Write-Host "  [OK] VOICEVOX プロセス検出 (PID: $($vvProc.Id))" -ForegroundColor Green
            $voicevoxReady = $true
        } else {
            Write-Host "  [NG] VOICEVOX が見つかりません。手動で起動してください。" -ForegroundColor Red
            Write-Host "       https://voicevox.hiroshiba.jp/" -ForegroundColor Gray
            Write-Host ""
            Read-Host "VOICEVOX を起動したら Enter を押してください"
        }
    }

    if ($voicevoxExe -and -not $voicevoxReady) {
        Start-Process $voicevoxExe
        Write-Host "  [...] VOICEVOX 起動待機中..." -ForegroundColor Yellow

        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Seconds 2
            try {
                $null = Invoke-WebRequest -Uri "http://127.0.0.1:50021/version" -TimeoutSec 2 -ErrorAction Stop
                $voicevoxReady = $true
                Write-Host "  [OK] VOICEVOX エンジン準備完了" -ForegroundColor Green
                break
            } catch {
                Write-Host "  [...]  待機中... ($($i * 2)s)" -ForegroundColor Gray
            }
        }
    }

    if (-not $voicevoxReady) {
        # 最終確認
        try {
            $null = Invoke-WebRequest -Uri "http://127.0.0.1:50021/version" -TimeoutSec 5 -ErrorAction Stop
            $voicevoxReady = $true
            Write-Host "  [OK] VOICEVOX 接続成功" -ForegroundColor Green
        } catch {
            Write-Host "  [NG] VOICEVOX に接続できません。中断します。" -ForegroundColor Red
            exit 1
        }
    }
}

# ── 2. .env 確認 ────────────────────────────────────────────────────

$envFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Host ""
    Write-Host "  [NG] .env ファイルが見つかりません。" -ForegroundColor Red
    Write-Host "       cp .env.example .env して API キーを設定してください。" -ForegroundColor Gray
    exit 1
}

if ($Mode -eq "live") {
    $envContent = Get-Content $envFile -Raw
    if ($envContent -match "YOUTUBE_LIVE_CHAT_ID=\s*$" -or $envContent -notmatch "YOUTUBE_LIVE_CHAT_ID=\S+") {
        Write-Host ""
        Write-Host "  [NG] YOUTUBE_LIVE_CHAT_ID が未設定です。" -ForegroundColor Red
        Write-Host "       YouTube 配信を開始して liveChatId を .env に設定してください。" -ForegroundColor Gray
        Write-Host "       詳細: README.md の「liveChatId の取得方法」を参照" -ForegroundColor Gray
        exit 1
    }
}

# ── 3. ビルド済み .exe 検出 ──────────────────────────────────────────

$buildExe = Join-Path $ProjectRoot "AITuber\Build\AITuber.exe"
$hasBuild = (Test-Path $buildExe) -and (-not $UseEditor)

if ($hasBuild) {
    Write-Host "[INFO] ビルド済み .exe を検出: $buildExe" -ForegroundColor Green
} else {
    if ($UseEditor) {
        Write-Host "[INFO] -UseEditor 指定のため Unity エディタを使用します" -ForegroundColor Gray
    } else {
        Write-Host "[INFO] ビルド済み .exe なし → Unity エディタで Play してください" -ForegroundColor Gray
        Write-Host "       初回ビルド: Unity メニュー → AITuber > Build Windows Standalone" -ForegroundColor Gray
    }
}

# ── 4. Orchestrator 起動 ────────────────────────────────────────────

Write-Host ""
if ($Mode -eq "test") {
    Write-Host "[2/3] テスト配信モードで Orchestrator を起動..." -ForegroundColor Yellow
    Write-Host "  コンソールにコメントを入力してテストできます。" -ForegroundColor Gray
    $orchCmd = "python -m orchestrator.local_test"
} else {
    Write-Host "[2/3] 本番モードで Orchestrator を起動..." -ForegroundColor Yellow
    $orchCmd = "python -m orchestrator"
}

# Orchestrator をバックグラウンドで起動（本番のみ）
Push-Location $ProjectRoot

if ($Mode -eq "live") {
    $orchProcess = Start-Process -FilePath "python" -ArgumentList "-m orchestrator" `
        -WorkingDirectory $ProjectRoot -PassThru -NoNewWindow
    Write-Host "  [OK] Orchestrator 起動 (PID: $($orchProcess.Id))" -ForegroundColor Green
    Start-Sleep -Seconds 3

    # ── アバターアプリ起動 ────────────────────────────────────────
    Write-Host ""
    if ($hasBuild) {
        Write-Host "[3/3] AITuber アバターアプリを起動..." -ForegroundColor Yellow
        $avatarProcess = Start-Process -FilePath $buildExe `
            -ArgumentList "-screen-width 1280 -screen-height 720 -screen-fullscreen 0" `
            -PassThru
        Write-Host "  [OK] AITuber.exe 起動 (PID: $($avatarProcess.Id))" -ForegroundColor Green
    } else {
        Write-Host "[3/3] Unity で Play を押してください" -ForegroundColor Yellow
        Write-Host "  Unity エディタの ▶ ボタンを押すと、アバターが WS 接続します。" -ForegroundColor Gray
    }

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  配信中！ Ctrl+C で停止" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green

    try {
        $orchProcess.WaitForExit()
    } catch {
        # Ctrl+C
    } finally {
        if (-not $orchProcess.HasExited) {
            Stop-Process $orchProcess -Force -ErrorAction SilentlyContinue
        }
        # ビルド版もあれば終了
        if ($avatarProcess -and -not $avatarProcess.HasExited) {
            Stop-Process $avatarProcess -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    # テストモード: フォアグラウンドで対話実行
    Write-Host ""
    if ($hasBuild) {
        Write-Host "[3/3] AITuber アバターアプリを起動..." -ForegroundColor Yellow
        $avatarProcess = Start-Process -FilePath $buildExe `
            -ArgumentList "-screen-width 1280 -screen-height 720 -screen-fullscreen 0" `
            -PassThru
        Write-Host "  [OK] AITuber.exe 起動 (PID: $($avatarProcess.Id))" -ForegroundColor Green
    } else {
        Write-Host "[3/3] Unity で Play を押すとアバターが接続します（任意）" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  テスト配信開始！" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""

    & python -m orchestrator.local_test

    # テスト終了時にアバターも終了
    if ($avatarProcess -and -not $avatarProcess.HasExited) {
        Stop-Process $avatarProcess -Force -ErrorAction SilentlyContinue
    }
}

Pop-Location
Write-Host ""
Write-Host "[END] 配信終了" -ForegroundColor Cyan
