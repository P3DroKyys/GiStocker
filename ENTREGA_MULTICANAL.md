# Entrega da prévia GiStocker Multicanal

Data: 02/10/2026. Versão: **2.0.0-preview.1**.

## Resultado

O desktop passou a operar por um agente escritor via Named Pipe. Há migração
aditiva, cofre com chave aleatória, proteção de senha/DPAPI, backup portátil,
eventos imutáveis e laboratório multicanal em banco separado. Configurar a
simulação não publica cotas; iniciar, pausar e encerrar são ações distintas.

**Esta entrega é uma prévia validada localmente, não uma versão homologada para
clientes ou lojas online reais.** Não considero todos os critérios A–G concluídos.

## Evidências finais

| Verificação executada | Resultado | Registro |
|---|---|---|
| Linha de base anterior às alterações | 209 aprovados | `auditoria/baseline_multicanal.txt` |
| Suíte completa final | **237 aprovados**, 62,933 s | `auditoria/regressao_multicanal_entrega.txt` |
| Interface existente, widgets reais | 4 aprovados | `auditoria/interface_legada_multicanal.txt` |
| Interface multicanal + agente real, dois temas | 1 aprovado | `auditoria/interface_multicanal_final.txt` |
| Executável compilado, cópia descartável | Aprovado | `auditoria/build_smoke_final.txt` |
| Manifesto da build | **2.163 arquivos conferidos** | `GestorEstoque/SHA256.json` |
| Compilação PyInstaller + Inno Setup | Concluída | `auditoria/build_multicanal_02.txt` |
| Sintaxe PowerShell do instalador | Sem erros de análise | `instalador/servico.ps1` |

Os testes incluem morte abrupta do processo antes/depois do commit, perda de resposta
seguida de nova interface, concorrência, rejeição de token Windows restrito no pipe,
DPAPI, senha, migração v1 preservando o arquivo protegido original, backup/restauração,
cancelamento parcial, devolução/quarentena, alocação para 501 saldos e falhas remotas
simuladas. O journal da interface preserva apenas hashes e UUIDs de comandos pendentes;
não grava senha nem os parâmetros de estoque em texto puro.

Falhas intermediárias foram mantidas na auditoria e corrigidas. A primeira compilação
foi barrada por um falso positivo do scanner: o certificado público `cacert.pem` foi
classificado como segredo. A validação agora distingue certificados de chaves privadas.
Essa primeira pasta não é a build de entrega.

## Arquivos de distribuição

Instalador de testes:

`C:\Software Gestor\CODIGO\estoque_cosmeticos\dist\GiStocker_20261002_093020_276cb38297c1\Instalador\GiStocker-Setup-2.0.0-preview.1_20261002_093020_276cb38297c1.exe`

Executável portátil de testes:

`C:\Software Gestor\CODIGO\estoque_cosmeticos\dist\GiStocker_20261002_093020_276cb38297c1\GestorEstoque\GestorEstoque.exe`

Para o portátil, é necessária a pasta **GestorEstoque inteira**. Para o fluxo instalado,
o Setup inclui as dependências. O teste do executável usou uma cópia temporária; o
serviço de produção não foi instalado nem ativado nesta máquina durante a auditoria.

O Setup tem arquivo `.sha256` ao lado. Os binários do GiStocker não têm assinatura
Authenticode. A assinatura validada foi a do compilador Inno Setup, não a do produto.

## Estado por marco

| Marco | Estado nesta entrega |
|---|---|
| A — auditoria e migração | Snapshot, linha de base, migração aditiva e testes concluídos. |
| B — agente/IPC/cofre | Implementado e testado em processos locais. Conta virtual e SCM ainda exigem homologação instalada. |
| C — núcleo multicanal | Alocação, vínculos, pedidos, compensações, filas e falhas exercitados no laboratório. Integração real bloqueada. |
| D — distribuição | Build e Setup gerados. Instalação/upgrade/rollback/uninstall e reboot em Windows limpo **não comprovados**. |
| E — telas | Configurações, laboratório de cotas/vínculos/pedidos/monitor e origem no histórico implementados; testes reais de widgets aprovados. |
| F/G — plataformas e kits | Somente preparação e mocks. Sem OAuth real, piloto, sombra de sete dias ou execução de kits. |

## Limites que permanecem

- Não há Windows Sandbox disponível no ambiente; não houve teste em outra máquina
  ou de perda física de energia. Não confundir teste de processo com teste de reboot.
- A ferramenta de restauração é técnica, por função Python com senha lida em memória;
  ainda não existe assistente gráfico de restauração.
- Perfis comerciais assinados por cliente e compilação nativa integral ficaram
  pendentes; não foram criados forks nem embutidos segredos compartilhados.
- Uma nova devolução parcial após a inspeção de outra devolução da mesma linha gera
  pendência de conciliação; não é automatizada nesta prévia.
- O catálogo é fictício e deriva da cópia local. Importação real de imagens,
  características e SKU do vendedor depende dos conectores oficiais.
- Shopee bloqueou a leitura da documentação com 403. O portal TikTok exigiu conteúdo
  dinâmico/autenticado. Não implementei endpoints com base em suposições.
- Nenhum sistema local é invulnerável a um administrador ou malware executando na
  conta do serviço. A senha curta, embora permitida, limita resistência offline.

Antes do piloto real: homologar instalação e recuperação em Windows limpo; obter
documentação e permissões oficiais; provisionar credenciais fora da build; executar
sombra por sete dias e só então um piloto autorizado em 5–10 SKUs de **um** canal.

## Como continuar e recuperar

Desenvolvimento: `1_preparar_ambiente.bat`, depois `2_executar.bat`.
Distribuição: `3_gerar_exe.bat`, que cria pastas exclusivas.

Instalação, atualização, importação, backup, restauração e remoção estão detalhados em
`GUIA_MULTICANAL.md`. Arquitetura, arquivos alterados e fontes oficiais estão em
`RELATORIO_MULTICANAL.md`. O snapshot anterior está em
`auditoria/multicanal_20261002_013328/fonte_antes.zip`.

Não use simultaneamente o estoque antigo e o novo após migrar: a cópia antiga é
histórica. Não tente reverter um esquema novo com um executável antigo. Recupere uma
cópia protegida em diretório novo, confira saldos/IDs e escolha uma única autoridade.
