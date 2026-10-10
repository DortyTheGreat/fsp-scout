# FSP Scout - compare rule-based text parsing with a local LLM on the held-out text set.
# Easiest: double-click compare-llm.bat in the project root.
# Before that start a local OpenAI-compatible server, e.g. llama.cpp:  llama-server -m model.gguf --port 8080
# Extra arguments are passed to validation\llm_compare.py, e.g.:  compare-llm.bat --quick
#   --base-url http://127.0.0.1:11434 --model qwen2.5:3b   (Ollama)
#   --rules-only                                           (no model)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
. (Join-Path $PSScriptRoot "python-env.ps1")

$venvPy = Initialize-Venv $Root
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
Step "Comparing rules and the local LLM"
& $venvPy (Join-Path $Root "validation\llm_compare.py") @args
