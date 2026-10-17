# 注册每个交易日 16:10 JST 运行的计划任务（PowerShell 管理员运行一次即可）
# 16:10 而不是 15:30：東証 15:30 收盘后，yfinance 的日线通常还要 15~30 分钟才更新。
$proj = "D:\trading\quant_breakout"
$bat  = Join-Path $proj "scripts\run_daily.bat"

$action  = New-ScheduledTaskAction -Execute $bat
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 16:10
$set     = New-ScheduledTaskSettingsSet -StartWhenAvailable `
           -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
           -MultipleInstances IgnoreNew     # 重叠触发时忽略新实例，配合程序内幂等双保险

Register-ScheduledTask -TaskName "QuantBreakout-Daily" -Action $action `
    -Trigger $trigger -Settings $set -Description "横盘突破策略每日运行" -Force

Write-Host "已注册。先用以下命令手工跑一次确认："
Write-Host "  Start-ScheduledTask -TaskName QuantBreakout-Daily"
Write-Host "注意：日本の祝日（休市日）也会触发，程序会因为『数据过期』自动跳过，属正常。"
