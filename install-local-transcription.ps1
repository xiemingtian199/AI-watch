$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$deps = Join-Path $root ".local-deps"
New-Item -ItemType Directory -Force -Path $deps | Out-Null
python -m pip install --target $deps faster-whisper
Write-Host "本地转写组件已安装到 $deps"
