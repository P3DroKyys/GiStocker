#ifndef BuildDir
  #error BuildDir obrigatório
#endif
#ifndef Release
  #define Release "2.0.0-preview.1"
#endif
[Setup]
AppId={{F4C5C155-C020-456D-AF4D-102339AD09B7}
AppName=GiStocker
AppVersion={#Release}
DefaultDirName={autopf}\GiStocker
DefaultGroupName=GiStocker
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#BuildDir}\..\Instalador
OutputBaseFilename=GiStocker-Setup-{#Release}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\versoes\{#Release}\GestorEstoque.exe
CloseApplications=no
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}\versoes\{#Release}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "servico.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\GiStocker"; Filename: "{app}\versoes\{#Release}\GestorEstoque.exe"
Name: "{autodesktop}\GiStocker"; Filename: "{app}\versoes\{#Release}\GestorEstoque.exe"

[Run]
Filename: "{app}\versoes\{#Release}\GestorEstoque.exe"; Description: "Abrir GiStocker"; Flags: nowait postinstall skipifsilent runasoriginaluser

[Code]
var
  Conta: TInputQueryWizardPage;
  Portatil: TInputDirWizardPage;

procedure InitializeWizard;
begin
  Conta := CreateInputQueryPage(wpSelectDir, 'Acesso ao GiStocker', 'Conta Windows autorizada',
    'Informe a conta que usará o programa. A senha do GiStocker será criada no primeiro acesso. Se esta conta receber acesso agora, pode ser necessário sair e entrar no Windows.');
  Conta.Add('Conta Windows (computador\usuário):', False);
  Conta.Values[0] := GetEnv('USERDOMAIN') + '\' + GetEnv('USERNAME');
  Portatil := CreateInputDirPage(Conta.ID, 'Dados de uma versão portátil', 'Importação opcional',
    'Deixe vazio para uma instalação nova. Para importar, selecione a pasta dados antiga e feche todas as versões do GiStocker. A origem será preservada; use somente a instalação nova após importar.', False, '');
  Portatil.Add('Pasta dados antiga (opcional):');
end;

function Aspas(const Valor: String): String;
begin
  if Pos('"', Valor) > 0 then RaiseException('Caractere inválido no parâmetro.');
  Result := '"' + Valor + '"';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var Codigo: Integer; Parametros: String;
begin
  if CurStep = ssPostInstall then begin
    SaveStringToFile(ExpandConstant('{app}\versoes\{#Release}\instalado.flag'), 'GiStocker', False);
    Parametros := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + Aspas(ExpandConstant('{app}\servico.ps1')) +
      ' -Acao Instalar -Executavel ' + Aspas(ExpandConstant('{app}\versoes\{#Release}\GestorEstoque.exe')) +
      ' -Operador ' + Aspas(Conta.Values[0]);
    if Portatil.Values[0] <> '' then Parametros := Parametros + ' -Portatil ' + Aspas(Portatil.Values[0]);
    if (not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Parametros, '', SW_HIDE, ewWaitUntilTerminated, Codigo)) or (Codigo <> 0) then
      RaiseException('Não foi possível configurar ou verificar o serviço. Os dados foram preservados. Consulte o guia de recuperação.');
  end;
end;

function InitializeUninstall: Boolean;
var Codigo: Integer;
begin
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + Aspas(ExpandConstant('{app}\servico.ps1')) + ' -Acao Remover',
    '', SW_HIDE, ewWaitUntilTerminated, Codigo) and (Codigo = 0);
  if not Result then MsgBox('O serviço não pôde ser parado. A desinstalação foi interrompida para preservar os dados.', mbError, MB_OK);
end;
