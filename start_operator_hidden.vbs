' start_operator_hidden.vbs - Launch Operator with no visible windows
' Uses pythonw.exe and hidden CMD windows

Set WshShell = CreateObject("WScript.Shell")

' Change to Operator directory
WshShell.CurrentDirectory = "C:\Projects\Operator"

' Environment Configuration for Ollama
Set colEnv = WshShell.Environment("PROCESS")
colEnv("OLLAMA_MODELS") = "D:\OllamaModels\.ollama\models"
colEnv("OLLAMA_URL") = "http://localhost:11434"

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

' Start HTTP API Server (hidden, using pythonw)
WshShell.Run "backend\venv\Scripts\pythonw.exe backend\server.py", 0, False
WScript.Sleep 2000

' Start WebSocket Server (hidden, using pythonw)
WshShell.Run "backend\venv\Scripts\pythonw.exe backend\ws_server.py", 0, False
WScript.Sleep 2000

' Start File Watcher (hidden, using pythonw)
WshShell.Run "backend\venv\Scripts\pythonw.exe backend\watcher.py", 0, False
WScript.Sleep 2000

' Start Project Launcher (hidden, using pythonw)
WshShell.Run "backend\venv\Scripts\pythonw.exe backend\project_launcher.py", 0, False
WScript.Sleep 3000

' Start Frontend (hidden window)
WshShell.Run "cmd /c cd frontend && npm run dev", 0, False
WScript.Sleep 3000

' Start Tray Icon (this one shows if needed, but try pythonw first)
On Error Resume Next
WshShell.Run "backend\venv\Scripts\pythonw.exe backend\tray.py", 0, False
If Err.Number <> 0 Then
    ' Fallback to python if pythonw fails for tray
    WshShell.Run "backend\venv\Scripts\python.exe backend\tray.py", 0, False
End If
On Error Goto 0

' Show notification (optional)
' MsgBox "Jarvis Operator is running!" & vbCrLf & _
'        "Dashboard: http://localhost:5173" & vbCrLf & _
'        "Right-click system tray icon for options.", _
'        vbInformation, "Operator Started"

Set WshShell = Nothing
