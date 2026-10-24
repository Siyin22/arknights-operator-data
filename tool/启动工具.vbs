Option Explicit
Dim fs, shell, folder, python, script
Set fs = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
python = fs.BuildPath(folder, ".venv\Scripts\pythonw.exe")
script = fs.BuildPath(folder, "src\launch.py")
If Not fs.FileExists(python) Then
    MsgBox "Python environment is missing. Please ask your AI assistant to repair this tool.", 16, "Arknights Data"
    WScript.Quit 1
End If
shell.CurrentDirectory = folder
shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & script & Chr(34), 0, False
