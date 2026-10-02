param(
    [ValidateSet('Instalar','Remover')][string]$Acao = 'Instalar',
    [string]$Executavel,
    [string]$Operador,
    [string]$Portatil
)
$ErrorActionPreference = 'Stop'
$nomeServico = 'GiStocker'
$raizDados = Join-Path $env:ProgramData 'GiStocker'
$identidadeServico = 'NT SERVICE\GiStocker'
$nomeGrupo = 'GiStocker Operadores'

function Executar-SC([Parameter(ValueFromRemainingArguments=$true)][string[]]$Argumentos) {
    & "$env:SystemRoot\System32\sc.exe" @Argumentos | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao configurar serviço ($LASTEXITCODE)." }
}

function Parar-Agente {
    $servico = Get-Service -Name $nomeServico -ErrorAction SilentlyContinue
    if ($servico -and $servico.Status -ne 'Stopped') {
        Stop-Service -Name $nomeServico
        $servico.WaitForStatus('Stopped',[TimeSpan]::FromSeconds(45))
    }
}

if ($Acao -eq 'Remover') {
    Parar-Agente
    if (Get-Service -Name $nomeServico -ErrorAction SilentlyContinue) {
        Executar-SC @('delete',$nomeServico)
    }
    # Dados e grupo permanecem: reinstalação recupera a mesma identidade de serviço.
    exit 0
}

$caminhoExe = (Resolve-Path -LiteralPath $Executavel).Path
if ([IO.Path]::GetFileName($caminhoExe) -ne 'GestorEstoque.exe') { throw 'Executável inválido.' }
if (-not $Operador) { throw 'Informe a conta Windows que usará o sistema.' }
$sidOperador = ([Security.Principal.NTAccount]::new($Operador)).Translate([Security.Principal.SecurityIdentifier])
$anterior = Get-CimInstance Win32_Service -Filter "Name='GiStocker'" -ErrorAction SilentlyContinue
$caminhoAnterior = if ($anterior) { $anterior.PathName } else { $null }
$eraAtivo = $anterior -and $anterior.State -eq 'Running'

try {
    if (-not (Get-LocalGroup -Name $nomeGrupo -ErrorAction SilentlyContinue)) {
        New-LocalGroup -Name $nomeGrupo -Description 'Operadores autorizados do GiStocker' | Out-Null
    }
    $membro = Get-LocalGroupMember -Group $nomeGrupo | Where-Object { $_.SID -eq $sidOperador }
    if (-not $membro) { Add-LocalGroupMember -Group $nomeGrupo -Member $sidOperador.Value }
    Parar-Agente
    $binario = '"' + $caminhoExe + '" --servico'
    if ($anterior) {
        Executar-SC @('config',$nomeServico,'binPath=',$binario,'start=','delayed-auto')
    } else {
        Executar-SC @('create',$nomeServico,'binPath=',$binario,'start=','delayed-auto','obj=',$identidadeServico,'DisplayName=','GiStocker — estoque local')
    }
    Executar-SC @('sidtype',$nomeServico,'unrestricted')
    Executar-SC @('failure',$nomeServico,'reset=','86400','actions=','restart/10000/restart/30000/restart/60000')
    Executar-SC @('failureflag',$nomeServico,'1')
    $sidServico = ([Security.Principal.NTAccount]::new($identidadeServico)).Translate([Security.Principal.SecurityIdentifier])
    New-Item -ItemType Directory -Path $raizDados -Force | Out-Null
    if ((Get-Item -LiteralPath $raizDados).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Diretório de dados não pode ser um link.' }
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true,$false)
    foreach ($sid in @('S-1-5-18','S-1-5-32-544',$sidServico.Value)) {
        $regra = New-Object Security.AccessControl.FileSystemAccessRule([Security.Principal.SecurityIdentifier]::new($sid),'FullControl','ContainerInherit,ObjectInherit','None','Allow')
        $acl.AddAccessRule($regra)
    }
    Set-Acl -LiteralPath $raizDados -AclObject $acl
    $operadoresJson = Join-Path $raizDados 'operadores.json'
    $operadores = @($sidOperador.Value)
    if (Test-Path -LiteralPath $operadoresJson) {
        $operadores += @(Get-Content -LiteralPath $operadoresJson -Raw | ConvertFrom-Json)
    }
    ConvertTo-Json -InputObject @($operadores | Select-Object -Unique) | Set-Content -LiteralPath $operadoresJson -Encoding UTF8
    # Exportações são cifradas e podem ser copiadas pelos operadores.
    $exportacoes = Join-Path $raizDados 'exportacoes'
    New-Item -ItemType Directory -Path $exportacoes -Force | Out-Null
    $aclExportacao = Get-Acl -LiteralPath $exportacoes
    $sidGrupo = (Get-LocalGroup -Name $nomeGrupo).SID
    $aclExportacao.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sidGrupo,'ReadAndExecute','ContainerInherit,ObjectInherit','None','Allow')))
    $aclExportacao.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sidOperador,'ReadAndExecute','ContainerInherit,ObjectInherit','None','Allow')))
    Set-Acl -LiteralPath $exportacoes -AclObject $aclExportacao
    if ($Portatil) {
        # A cópia consistente é feita pelo helper empacotado, antes de iniciar SCM.
        # O helper recusa bancos em uso e não descriptografa nenhum conteúdo.
        $processo = Start-Process -FilePath $caminhoExe -ArgumentList @('--importar-portatil',('"'+$Portatil+'"')) -Wait -PassThru -WindowStyle Hidden
        if ($processo.ExitCode -ne 0) { throw 'Importação recusada. Feche a versão antiga e confira o diagnóstico.' }
    }
    Start-Service -Name $nomeServico
    (Get-Service -Name $nomeServico).WaitForStatus('Running',[TimeSpan]::FromSeconds(45))
    $verificacao = Start-Process -FilePath $caminhoExe -ArgumentList '--verificar-servico' -Wait -PassThru -WindowStyle Hidden
    if ($verificacao.ExitCode -ne 0) { throw 'Health check do serviço falhou.' }
    exit 0
} catch {
    # Cada versão fica em seu diretório; basta restaurar o caminho do serviço.
    try {
        Parar-Agente
        if ($caminhoAnterior) {
            Executar-SC @('config',$nomeServico,'binPath=',$caminhoAnterior)
            if ($eraAtivo) { Start-Service -Name $nomeServico }
        } elseif (Get-Service -Name $nomeServico -ErrorAction SilentlyContinue) {
            Executar-SC @('delete',$nomeServico)
        }
    } catch { }
    # Mensagem fixa: nunca registrar senha, token, comandos completos ou dados.
    Write-Error 'Instalação não concluída. Serviço anterior restaurado quando possível; dados preservados. Consulte o guia de recuperação.'
    exit 1
}
