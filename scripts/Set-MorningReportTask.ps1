[CmdletBinding()]
param(
    [ValidateSet('RegisterDisabled', 'Enable', 'Disable', 'Status', 'Unregister')]
    [string]$Mode = 'RegisterDisabled',
    [string]$Checkout,
    [string]$Python,
    [string]$EnvironmentFile
)

$ErrorActionPreference = 'Stop'
$repo = 'nornen0202/k-daytrade-morning-agent'
$taskName = 'K-Daytrade Morning 08-45 (1221924070)'
$taskPath = '\'
$account = [Security.Principal.WindowsIdentity]::GetCurrent()
$task = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction SilentlyContinue
if ($task -and $task.Principal.UserId -ne $account.User.Value) {
    $principalAccount = [Security.Principal.NTAccount]::new($task.Principal.UserId)
    if ($principalAccount.Translate([Security.Principal.SecurityIdentifier]) -ne $account.User) {
        throw "Daytrade task is owned by another account"
    }
}
if ($Mode -eq 'Unregister') {
    if ($task -and $task.State -ne 'Disabled') { throw 'Disable the Daytrade task first' }
    if ($task) { Unregister-ScheduledTask -InputObject $task -Confirm:$false }
    return
}
if ($Mode -eq 'Disable') {
    if ($task) { Disable-ScheduledTask -InputObject $task | Out-Null }
} elseif ($Mode -in @('RegisterDisabled', 'Enable')) {
    if ((Get-TimeZone).Id -ne 'Korea Standard Time') {
        throw "Windows time zone must be Korea Standard Time"
    }
    if ($Mode -eq 'RegisterDisabled') {
        if (!$Checkout -or !$Python -or !$EnvironmentFile) {
            throw 'Supply the independent checkout, Python executable and private environment file'
        }
        if ($task -and $task.State -ne 'Disabled') {
            throw 'Disable the existing Daytrade task before reconfiguring it'
        }
        $Checkout = (Resolve-Path -LiteralPath $Checkout).Path
        $Python = (Resolve-Path -LiteralPath $Python).Path
        $EnvironmentFile = (Resolve-Path -LiteralPath $EnvironmentFile).Path
        $remote = git -C $Checkout remote get-url origin
        if ($LASTEXITCODE -or $remote -ne "https://github.com/$repo.git") {
            throw 'Unexpected Daytrade checkout origin'
        }
        $launcher = (Resolve-Path -LiteralPath (Join-Path $Checkout 'scripts/Start-MorningReport.ps1')).Path
        $pwsh = (Get-Process -Id $PID).Path
        if ((Split-Path -Leaf $pwsh) -ne 'pwsh.exe') { throw 'Run this script with PowerShell 7' }
        $arguments = '-NoProfile -NonInteractive -File "{0}" -Checkout "{1}" -Python "{2}" -EnvironmentFile "{3}"' -f
            $launcher, $Checkout, $Python, $EnvironmentFile
        $action = New-ScheduledTaskAction -Execute $pwsh -Argument $arguments -WorkingDirectory $Checkout
        $triggers = foreach ($stamp in @('08:45', '09:00', '09:05')) {
            $at = [datetime]::Today.Add([TimeSpan]::Parse($stamp))
            $trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -At $at -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday
            $trigger.StartBoundary = $at.ToString('yyyy-MM-ddTHH:mm:ss') + '+09:00'
            $trigger
        }
        $settingsArgs = @{
            Disable = $true
            StartWhenAvailable = $true
            WakeToRun = $true
            AllowStartIfOnBatteries = $true
            DontStopIfGoingOnBatteries = $true
            MultipleInstances = 'IgnoreNew'
            ExecutionTimeLimit = New-TimeSpan -Minutes 20
        }
        $settings = New-ScheduledTaskSettingsSet @settingsArgs
        $principal = New-ScheduledTaskPrincipal -UserId $account.Name -LogonType Interactive -RunLevel Limited
        $taskArgs = @{
            TaskName = $taskName
            TaskPath = $taskPath
            Action = $action
            Trigger = $triggers
            Settings = $settings
            Principal = $principal
            Force = $true
        }
        Register-ScheduledTask @taskArgs | Out-Null
    } else {
        if (!$task) { throw 'Register the disabled task first' }
        $checkoutPath = $task.Actions[0].WorkingDirectory
        $workflows = gh api "repos/$repo/actions/workflows?per_page=100" | ConvertFrom-Json
        if ($LASTEXITCODE) { throw 'Could not verify the GitHub workflow cutover' }
        $legacy = $workflows.workflows | Where-Object { $_.id -eq 266757394 }
        $active = $workflows.workflows | Where-Object { $_.path -eq '.github/workflows/morning-report.yml' }
        if (($legacy -and $legacy.state -notin @('disabled_manually', 'deleted')) -or
            !$active -or $active.state -ne 'active') {
            throw 'Cutover requires a disabled legacy workflow and the active replacement on main'
        }
        if ($legacy -and $legacy.state -ne 'deleted') {
            $runs = gh api "repos/$repo/actions/workflows/$($legacy.id)/runs?per_page=100" | ConvertFrom-Json
            if ($LASTEXITCODE -or ($runs.workflow_runs | Where-Object { $_.status -ne 'completed' })) {
                throw 'Wait for all legacy workflow runs to finish before enabling Windows collection'
            }
        }
        git -C $checkoutPath fetch --no-tags origin main
        if ($LASTEXITCODE) { throw 'Could not verify the Daytrade main branch' }
        git -C $checkoutPath diff --quiet FETCH_HEAD -- daytrade_agent config prompts scripts
        if ($LASTEXITCODE) { throw 'Update the independent checkout from the gated main branch first' }
        $marker = git -C $checkoutPath show 'FETCH_HEAD:.github/daytrade-publication-v1'
        if ($LASTEXITCODE -or $marker -ne 'morning-publication-v1') {
            throw 'Daytrade publication protocol has not reached main'
        }
        Enable-ScheduledTask -InputObject $task | Out-Null
    }
}
$task = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction SilentlyContinue
if ($task) {
    $info = Get-ScheduledTaskInfo -InputObject $task
    [pscustomobject]@{
        Task = $task.TaskName
        State = [string]$task.State
        Account = $task.Principal.UserId
        Logon = [string]$task.Principal.LogonType
        TimeZone = (Get-TimeZone).Id
        Boundaries = @($task.Triggers.StartBoundary)
        NextRunTime = $info.NextRunTime
        LastRunTime = $info.LastRunTime
        LastTaskResult = $info.LastTaskResult
    }
}
