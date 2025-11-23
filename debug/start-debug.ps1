# PenDonn Debug Mode Launcher for Windows
# Easy way to start PenDonn in debug mode

Write-Host "`n" -NoNewline
Write-Host "="*60 -ForegroundColor Cyan
Write-Host "  PenDonn - Debug Mode Launcher" -ForegroundColor Cyan
Write-Host "="*60 -ForegroundColor Cyan
Write-Host ""

# Check if Python is available
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python not found. Please install Python 3.9+" -ForegroundColor Red
    exit 1
}

# Check if requirements are installed
Write-Host "`nChecking dependencies..." -ForegroundColor Yellow
$modulesNeeded = @("flask", "scapy", "nmap")
$missingModules = @()

foreach ($module in $modulesNeeded) {
    $result = python -c "import $module" 2>&1
    if ($LASTEXITCODE -ne 0) {
        $missingModules += $module
    }
}

if ($missingModules.Count -gt 0) {
    Write-Host "⚠ Missing dependencies detected" -ForegroundColor Yellow
    Write-Host "  Installing requirements..." -ForegroundColor Yellow
    python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Failed to install dependencies" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "✓ All dependencies installed" -ForegroundColor Green
}

# Create necessary directories
Write-Host "`nPreparing directories..." -ForegroundColor Yellow
$dirs = @("./data", "./logs", "./handshakes", "./test_data")
foreach ($dir in $dirs) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Host "  Created: $dir" -ForegroundColor Gray
    }
}
Write-Host "✓ Directories ready" -ForegroundColor Green

# Check if debug config exists
if (!(Test-Path "./config/config.debug.json")) {
    Write-Host "✗ Debug configuration not found: ./config/config.debug.json" -ForegroundColor Red
    exit 1
}

# Ask about test data
Write-Host ""
$stats = python -c "from core.database import Database; db = Database('./data/pendonn_debug.db'); s = db.get_statistics(); print(f'{s[\"networks_discovered\"]}'); db.close()" 2>$null
if ($stats -and $stats -gt 0) {
    Write-Host "📊 Database contains existing data" -ForegroundColor Cyan
    $response = Read-Host "   Generate fresh test data? (y/n)"
    if ($response -eq 'y') {
        Write-Host "`n🔧 Generating test data..." -ForegroundColor Yellow
        python test_debug_mode.py
    }
} else {
    Write-Host "📦 No test data found" -ForegroundColor Cyan
    $response = Read-Host "   Generate test data for better testing? (y/n)"
    if ($response -eq 'y') {
        Write-Host "`n🔧 Generating test data..." -ForegroundColor Yellow
        python test_debug_mode.py
    }
}

# Show instructions
Write-Host ""
Write-Host "="*60 -ForegroundColor Cyan
Write-Host "  Starting PenDonn in Debug Mode" -ForegroundColor Cyan
Write-Host "="*60 -ForegroundColor Cyan
Write-Host ""
Write-Host "🌐 Web Interface will be available at:" -ForegroundColor Green
Write-Host "   http://localhost:8080" -ForegroundColor White
Write-Host ""
Write-Host "📝 Logs are saved to:" -ForegroundColor Green
Write-Host "   ./logs/pendonn.log" -ForegroundColor White
Write-Host ""
Write-Host "⌨  Press Ctrl+C to stop PenDonn" -ForegroundColor Yellow
Write-Host ""
Write-Host "="*60 -ForegroundColor Cyan
Write-Host ""

# Start PenDonn
try {
    python main.py --debug
} catch {
    Write-Host "`n✗ PenDonn stopped" -ForegroundColor Red
} finally {
    Write-Host "`n" -NoNewline
    Write-Host "="*60 -ForegroundColor Cyan
    Write-Host "  PenDonn Debug Session Ended" -ForegroundColor Cyan
    Write-Host "="*60 -ForegroundColor Cyan
    Write-Host ""
}
