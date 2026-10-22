' NSFW Studio V2 - silent launcher wrapper.
'
' 目的：双击桌面快捷方式时**不出现任何命令行窗口**，也不留下常驻控制台。
' 做法：以隐藏窗口方式运行同目录 launch_studio.ps1，stdout/stderr 写入
'       <project>\runtime\logs\launcher-last.log；失败时弹窗提示日志位置。
'
' 注意：本脚本必须由 wscript.exe 运行（桌面快捷方式的目标），不要直接双击 .ps1/.bat，
'       否则仍可能看到控制台窗口。
Option Explicit

Dim shell, fso
Dim scriptsDir, projectRoot, ps1Path, logDir, logFile
Dim commandLine, exitCode

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptsDir = fso.GetParentFolderName(WScript.ScriptFullName)
projectRoot = fso.GetParentFolderName(scriptsDir)
ps1Path = fso.BuildPath(scriptsDir, "launch_studio.ps1")
logDir = fso.BuildPath(projectRoot, "runtime\logs")

If Not fso.FolderExists(logDir) Then
    fso.CreateFolder logDir
End If
logFile = fso.BuildPath(logDir, "launcher-last.log")

' 0 = SW_HIDE：cmd 与 powershell 都不显示窗口；True = 等待启动器结束再返回。
commandLine = "cmd.exe /c ""powershell.exe -NoProfile -ExecutionPolicy Bypass " & _
              "-WindowStyle Hidden -File """ & ps1Path & """ > """ & logFile & """ 2>&1"""

exitCode = shell.Run(commandLine, 0, True)

If exitCode <> 0 Then
    MsgBox "NSFW Studio 启动失败（exit " & exitCode & "）。" & vbCrLf & vbCrLf & _
           "详细日志：" & logFile, 16, "NSFW Studio"
End If
