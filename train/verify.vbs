' Runs the sandbox check (scripts\verify_host.py) hidden: no console window
' that closing would kill. Double-click it, or: explorer.exe verify.vbs
Set sh = CreateObject("WScript.Shell")
here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
py = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Shishya\runtime\pythonw.exe")
sh.Run """" & py & """ """ & here & "\scripts\verify_host.py""", 0, False
