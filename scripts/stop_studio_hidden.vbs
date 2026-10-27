' NSFW Studio V2 - silent stopper wrapper.
'
' 目的：双击桌面「NSFW Studio · 停止」时**不出现命令行窗口**，以隐藏窗口方式运行
'       同目录 stop_studio.ps1，stdout/stderr 写入 <project>\runtime\logs\stop-last.log。
'
' 行为：成功（exit 0）不打扰；失败弹窗给出退出码与日志位置。
'       退出码含义见 stop_studio.ps1 头部（10/11/12/13/14/15）。
Option Explicit

Dim shell, fso
Dim scriptsDir, projectRoot, ps1Path, logDir, logFile
Dim commandLine, exitCode, message

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptsDir = fso.GetParentFolderName(WScript.ScriptFullName)
projectRoot = fso.GetParentFolderName(scriptsDir)
ps1Path = fso.BuildPath(scriptsDir, "stop_studio.ps1")
logDir = fso.BuildPath(projectRoot, "runtime\logs")

If Not fso.FolderExists(fso.BuildPath(projectRoot, "runtime")) Then
    fso.CreateFolder fso.BuildPath(projectRoot, "runtime")
End If
If Not fso.FolderExists(logDir) Then
    fso.CreateFolder logDir
End If
logFile = fso.BuildPath(logDir, "stop-last.log")

' 0 = SW_HIDE：不显示窗口；True = 等待停止流程结束再返回。
commandLine = "cmd.exe /c ""powershell.exe -NoProfile -ExecutionPolicy Bypass " & _
              "-WindowStyle Hidden -File """ & ps1Path & """ > """ & logFile & """ 2>&1"""

exitCode = shell.Run(commandLine, 0, True)

If exitCode <> 0 Then
    message = "NSFW Studio 停止未完全成功（exit " & exitCode & "）。" & vbCrLf & vbCrLf
    If exitCode = 15 Then
        message = message & "检测到外部（非 ControlHub 托管）ComfyUI，已停止其余组件，未强杀该进程。"
    ElseIf exitCode = 14 Then
        message = message & "ControlHub 调用失败，请检查 control-hub 是否可用。"
    ElseIf exitCode = 13 Then
        message = message & "停止后仍有托管端口被占用，请查看日志确认残留进程。"
    Else
        message = message & "请查看日志确认是哪一步失败。"
    End If
    message = message & vbCrLf & vbCrLf & "详细日志：" & logFile
    MsgBox message, 48, "NSFW Studio"
End If
