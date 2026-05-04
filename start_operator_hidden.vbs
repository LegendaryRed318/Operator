' start_operator_hidden.vbs - Launch Operator with no visible windows
' Uses pythonw.exe to run launcher.py which manages all services silently

Set WshShell = CreateObject("WScript.Shell")

' Change to Operator directory
WshShell.CurrentDirectory = "C:\Projects\Operator"

' Environment Configuration for Ollama
Set colEnv = WshShell.Environment("PROCESS")
colEnv("OLLAMA_MODELS") = "D:\OllamaModels\.ollama\models"
colEnv("OLLAMA_URL") = "http://localhost:11434"
colEnv("OLLAMA_HOST") = "127.0.0.1:11434"

' Use E: drive for HuggingFace cache (Whisper models ~500MB)
colEnv("HF_HOME") = "E:\.huggingface"
colEnv("TRANSFORMERS_CACHE") = "E:\.cache\transformers"

' Use E: drive for JARVIS Vault (notes, memory, skills)
colEnv("OPERATOR_VAULT_EXTERNAL") = "E:\JarvisVault"

' Create required directories
CreateDir("database")
CreateDir("logs")
CreateDir("test_logs")
CreateDir("models")
CreateDir("skills")

Sub CreateDir(dirName)
    Dim fso
    Set fso = CreateObject("Scripting.FileSystemObject")
    If Not fso.FolderExists(dirName) Then
        fso.CreateFolder(dirName)
    End If
End Sub

' Start the main launcher silently using pythonw
On Error Resume Next
WshShell.Run "backend\venv\Scripts\pythonw.exe launcher.py", 0, False
If Err.Number <> 0 Then
    ' Fallback to pythonw in PATH if venv isn't used
    WshShell.Run "pythonw.exe launcher.py", 0, False
End If
On Error Goto 0

Set WshShell = Nothing
