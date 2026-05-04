@echo off
:: start_operator.bat - Legacy launcher (small mode by default)
:: Use start_small.bat or start_homelab.bat for explicit mode selection

:: Set mode to small
set JARVIS_MODE=small

:: AI Settings - Small machine limits
set OLLAMA_MODEL=llama3.2:3b
set MAX_RAM_FOR_OLLAMA=1500

:: Disable GPU acceleration (not available on most small machines)
set OLLAMA_ACCELERATE=off

:: Use D: drive for Ollama models (where your models are installed)
set OLLAMA_MODELS=D:\OllamaModels\.ollama\models
set OLLAMA_HOST=127.0.0.1:11434

:: Use E: drive for HuggingFace cache (Whisper needs ~500MB)
set HF_HOME=E:\.huggingface
set TRANSFORMERS_CACHE=E:\.cache\transformers

:: Use E: drive for JARVIS Vault (notes, memory, skills)
set OPERATOR_VAULT_EXTERNAL=E:\JarvisVault

:: Disable remote access features
set ENABLE_REMOTE_ACCESS=false

cscript //nologo start_operator_hidden.vbs
