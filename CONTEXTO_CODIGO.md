# Estado atual — busca 1.2.0 (01/10/2026)

Admin/Ajustes e códigos usa `ControladorEstoque.pesquisar_produtos` e
`utils/busca.py`, com índice invertido em memória, pesos por campo e fallback
Damerau–Levenshtein (RapidFuzz 3.14.6). Sem migração de esquema ou FTS. Cache
armazenado no BancoDados, invalidado por total_changes/data_version e liberado ao
fechar; consultas durante transações não preenchem cache. Debounce 220 ms,
paginação de 200, seleção antiga invalidada ao digitar, sugestões sem autoseleção.
`#ID` evita confundir identificadores com volumes numéricos. A busca antiga de
relatórios/catálogo permanece independente. Ver auditoria/BUSCA_1_2_0.md.

Atualização 1.1.1: mínimo de senha de 6 caracteres (máximo 128), bloqueio automático
após 90 minutos. Parâmetros centralizados em config.py. Senhas existentes continuam
válidas; a regra de sequências previsíveis permanece. Evidências em
auditoria/testes_1_1_1.txt e auditoria/interface_1_1_1.txt.

Esta seção substitui as descrições de autenticação e arquivos das versões antigas
mantidas abaixo como histórico. Não voltar ao PIN padrão ou abrir o banco antes da senha.

- `main.py` cria `Cofre` e a tela de acesso; os controladores são criados só após
  SQLCipher autenticar o banco. `models/seguranca.py` concentra migração, cópias,
  integridade, troca de chave e trava por instalação. A senha não fica em atributos.
- `models/preferencias.py` é apenas um leitor restrito das preferências legadas.
  `dados/configuracoes.db` antigo é protegido em `.gsa` depois da migração;
  o tema atual fica em `aparencia.json`. Não há senha padrão nem reset sem a chave.
- `BancoDados` exige senha para disco. `permitir_legado=True` é explícito para
  fixtures/compatibilidade; nunca usado para uma sessão no aplicativo.
- SQLCipher 4.18.0 / SQLite 3.53.4 / OpenSSL 3.5.9, wheel local em `vendor` e hashes
  em `requirements.lock`. Rejeitar versões antigas do motor. Fontes, scripts e
  proveniência da compilação em `auditoria/native_build`.
- Exportações e backups novos são `.db` protegidos; CSV em sessão protegida é
  recusado. `.gsa` preserva bytes de arquivos legados, recuperáveis em memória.
- Bloqueio manual/Ctrl+L/90 minutos fecha conexão e destrói telas/diálogos.
  Timers de buscas, autofoco e gráficos são cancelados para impedir callbacks órfãos.
- Não prometer proteção contra administrador, malware no processo desbloqueado,
  exclusão de arquivos, rollback integral ou captura de uma senha futura por build
  adulterada. Hash de distribuição não é assinatura digital.
- Dados reais ainda exigem ativação local com senha escolhida pelo proprietário.
  A documentação operacional e as limitações ficam em `SEGURANCA.md`.

---

# Contexto técnico do Gestor de Estoque

Atualização 1.0.3 (01/10/2026): senha na abertura de toda a interface, em vez do PIN
no Admin. `models/preferencias.py` usa SQLite separado em `dados/configuracoes.db`
com PBKDF2-SHA256, sal de 16 bytes e 600.000 iterações. Senha inicial `1234`, tema
persistido, troca transacional com senha antiga e confirmação, conexões curtas.
Arquivo corrompido/incompleto é recusado sem reset automático. Não há criptografia
do estoque nem autenticação remota. Preservar `dados` inteira nas atualizações;
backups automáticos de estoque não incluem o banco separado de configurações.
`views/acesso.py` implementa TelaAcesso e CampoSenha. JanelaPrincipal só constrói
navegação e views após autenticar; atalhos não existem antes do desbloqueio.
`views/view_configuracoes.py` reúne versão, modos e troca de senha atrás da
engrenagem. Campos ocultos, botão Mostrar/Ocultar, limpeza ao sair, mínimo 4
caracteres na nova senha. Admin sem segundo bloqueio e sem campo Motivo; histórico
continua registrando "Ajuste manual (Admin)" e conserva validação concorrente.
Preços omitidos/None/vazios no cadastro viram zero; outros valores e demais campos
mantêm validações. O custo vazio de movimentação/ajuste mantém a semântica anterior.
Dashboard usa total_produtos já fornecido pelos relatórios, KPIs responsivos e
legenda abaixo do eixo para impedir sobreposição com barras.
Validação: 140 testes automatizados + 1 integração com widgets reais e bases
isoladas; logs em `auditoria/testes_upgrade.txt` e `teste_interface_upgrade.txt`.
Prévia conferida nos dois temas e tamanho mínimo. Build 1.0.3 em
`dist/GiStocker_20261001_104320_1beccef686fb/GestorEstoque`. O gerador agora cria
destinos exclusivos com mkdir/UUID, herdando permissões da pasta dist (mkdtemp
no Python 3.13+/Windows criava ACL privada à conta compiladora). Nenhuma base
da loja foi usada.

Atualização visual 1.0.2: `views/dialogos.py` implementa modais CTkToplevel com
ícones próprios em traços (Pillow/CTkImage), cores automáticas claro/escuro, rolagem
em mensagens longas, foco restaurado e confirmação inicialmente em Cancelar.
Os quatro helpers de componentes mantêm a API, agora delegando aos novos diálogos.
Falha de inicialização também usa o diálogo próprio, com messagebox como fallback
se o toolkit estiver indisponível. 108 testes aprovados; prévia real sem banco
conferida nos dois temas, Enter/Escape e mensagem longa. Banco e regras não mudaram.

Atualização 1.0.1: os 14 defeitos da auditoria foram corrigidos. `gerar_build.py`
reserva um novo destino em dist a cada geração. Exportação usa snapshot de leitura
WAL e publica atomicamente uma pasta por par de CSVs, neutralizando fórmulas nos
textos. Busca sem limite implícito; remoção de código no Admin confere dono esperado;
validações int64 e teto monetário, somas arbitrárias nos relatórios, custo vazio
preservado. Sugestões de categoria/marca corrigidas. `utils/erros.py` e fallback de
callbacks registram/avisam falhas. Não houve alteração do esquema nem dos bancos de
uso. Evidências atuais em `auditoria/resultados_correcao_20261001`; diagnóstico
anterior preservado em `auditoria/RELATORIO_2026-10-01.md`.

Upgrade de persistência (posterior às análises abaixo): todas as sete operações de
gravação de ControladorEstoque usam `_operacao_atomica`, adquirindo BEGIN IMMEDIATE
antes de ler/validar. BancoDados usa savepoints aninhados, rollback também em falha
de commit/interrupção, espera configurável de bloqueio e synchronous FULL. Ao abrir
base existente, cria backup consistente verificado em `dados/backups` antes da
migração não destrutiva para user_version 1. Backup não tem rotação automática e
falha impede abertura. Versão futura é recusada. Nenhuma base de uso foi aberta por
esta implementação; verificação ocorreu em memória/temporários. Admin envia estado
esperado, ignora campos inalterados e mantém precisão do custo; desfazer envia o ID
confirmado. NaN/infinito são rejeitados. Reservas, fila de integração e cotas continuam
somente propostas futuras. Executáveis antigos precisam ser substituídos por builds
atualizados antes de operar conjuntamente. Suíte: 57 testes, 55 aprovados, duas
falhas esperadas restantes (CSV no mesmo minuto e classificação de tônico capilar).

Upgrade visual GiStocker: tema JSON compartilhado e logo original transparente em
`assets/`; configuração separa recursos empacotados dos dados locais. O BAT de build
inclui esses recursos. Sidebar substitui o texto antigo pela logo, mostra atalhos e
seleção suave; fonte Windows Segoe UI, superfícies neutras, campos com bordas leves,
cartões arredondados e tabelas mais espaçadas. Histórico recente passou a exibir
blocos textuais, e Desfazer usa estilo discreto com borda. Relatórios têm rolagem
horizontal com larguras mínimas preservadas. Nenhuma regra de estoque ou esquema
mudou. `auditoria/preview_visual.py` oferece inspeção isolada em memória. Foram
inspecionados Operação, Cadastro, Dashboard, Relatórios e bloqueio do Admin, incluindo
alternância claro/escuro; o acesso por PIN não foi automatizado. Executáveis antigos
não são atualizados automaticamente.

Upgrade GTIN: `utils/gtin.py:validar_gtin` valida tipo string, trim, dígitos ASCII,
comprimentos 8/12/13/14, repetição de um único dígito e DV Módulo 10 GS1. O controlador
expõe `validar_codigo_barras`, convertendo ValueError em ErroNegocio, e valida todos
os códigos antes de cadastrar/vincular. Cadastro e Admin também validam na interface;
ao salvar, um código ainda digitado não é ignorado. Códigos recebidos da Operação
também são validados antes de entrar na lista do Cadastro. Campos continuam textuais;
não há normalização destrutiva de caracteres ou de zeros à esquerda. Cadastro sem
códigos e leitura/remoção de códigos legados permanecem disponíveis. Banco e esquema
não foram alterados. `auditoria/verificar_gtin.py` contém 17 testes aprovados; as suítes
anteriores mantêm 19 aprovações e seis falhas esperadas somadas (auditoria + painel).
As menções à ausência de validação GTIN no mapa inicial abaixo são históricas.

Atualização posterior ao mapa inicial: o Admin ganhou as abas **Produtos cadastrados**
e **Ajustes e códigos**. `views/painel_produtos.py` consulta todos os produtos pelo
controlador existente, filtra localmente com debounce, ordena colunas e encaminha a
seleção aos ajustes. `criar_tabela` agora aceita rolagem horizontal opcional, ativada
nesse painel. O painel recarrega ao entrar na aba/Admin desbloqueado e pelo botão
Atualizar. Nenhum esquema ou regra de movimentação mudou. As contagens, hashes e
descrições abaixo e em `INDICE_CODIGO.md` referem-se à leitura anterior a esse upgrade.

Leitura integral do código próprio em 30/09/2026. Este documento descreve a implementação encontrada; não representa funcionalidades planejadas. Para retomar o trabalho, ler este mapa e depois os módulos envolvidos na alteração. O índice complementar `INDICE_CODIGO.md` registra classes, funções, métodos, linhas e hashes da versão analisada.

## 1. Escopo e localização

- Fonte principal: `C:\Software Gestor\CODIGO\estoque_cosmeticos`.
- Backup: `C:\Software Gestor\BACKUPCODIGOFONTE\estoque_cosmeticos`. Os 26 arquivos próprios de fonte, documentação e configuração comparados eram idênticos antes da criação deste mapa. Ambientes, bancos e artefatos gerados não participaram dessa comparação.
- Distribuições: `C:\Software Gestor\BUILD\GestorEstoque` e `CODIGO\estoque_cosmeticos\dist\GestorEstoque`. Os executáveis têm hashes distintos; não foi estabelecida correspondência entre cada executável e o fonte atual.
- Foram lidos 17 arquivos Python, incluindo quatro `__init__.py` somente documentais e o script de auditoria, além de README, análise anterior, BATs, requisitos, configurações do VSCode, `.gitignore` e spec do PyInstaller.
- Não foi encontrado `AGENTS.md` na pesquisa do workspace nem diretório `.git` na raiz do fonte. Bibliotecas de terceiros, ambiente virtual e binários não foram auditados internamente.
- Há agora `dados/estoque.db`, `estoque.db-wal` e `estoque.db-shm` no fonte. A observação de ausência desse banco em `ANALISE_PROJETO.md` está desatualizada. Nesta leitura não foram abertos os bancos de uso nem repetidas as contagens de registros da auditoria anterior.

## 2. Arquitetura e ciclo de vida

Aplicação desktop local em Python, com CustomTkinter/Tkinter, SQLite, matplotlib e pandas. Não há servidor, API HTTP, integração remota, autenticação de usuários ou sincronização implementados no código próprio.

```text
main.py
  ├─ config.py: caminhos, regras e aparência
  ├─ BancoDados: uma conexão SQLite compartilhada
  ├─ ControladorEstoque ── repositórios de produtos, códigos e logs
  ├─ ControladorRelatorios ── repositórios e consultas agregadas
  └─ JanelaPrincipal
       ├─ Operação / Cadastro / Admin → ControladorEstoque
       ├─ Dashboard → ControladorRelatorios
       └─ Relatórios → ambos os controladores

views/componentes.py → componentes e estilos comuns
utils/texto.py → normalização, sugestões e conversões
```

1. `config.py` resolve a base pelo diretório do fonte; no executável, pelo diretório de `sys.executable`.
2. `main.py` redireciona stdout/stderr ausentes no executável sem console; avisos vão para `avisos.log`, quando possível.
3. `main()` configura aparência e tema, cria banco, controladores e janela, e entra no `mainloop()`.
4. O banco ativa chaves estrangeiras, WAL para arquivos, registra a função SQL `normalizar` e cria tabelas/índices ausentes.
5. A janela começa em Operação. Cria cada tela sob demanda e mantém suas instâncias em `views`; trocar de tela esconde a anterior com `grid_forget`, sem destruí-la.
6. `ao_mostrar(**dados)` atualiza ou focaliza cada tela. Não existe barramento global de eventos nem atualização contínua dos dados entre telas.
7. F1–F5 navegam pelas cinco telas. A troca de tema repinta Treeviews e, após 80 ms, notifica telas que implementam `ao_mudar_tema`.
8. Fechar a janela chama `BancoDados.fechar()` e depois destrói a janela.

As consultas, exportações e desenhos são disparados na thread da interface. Não há processamento em background no código próprio; operações grandes podem ocupar o loop gráfico.

## 3. Modelo de dados e persistência

| Entidade | Conteúdo e relações |
|---|---|
| `Produtos` | ID autoincremental, nome, marca, categoria, estoque inteiro, preço base, custo médio e data de cadastro local |
| `Codigos_Barras` | Código textual como chave primária global; FK para produto; vários códigos podem apontar para um mesmo produto |
| `Logs_Movimentacao` | Produto, tipo, quantidade, custo no momento, data/hora, estoque/custo anteriores, cancelamento e observação |

`Produto` inclui a lista de códigos, preenchida por consultas que usam `GROUP_CONCAT(..., ';')`. Suas propriedades calculam investimento e receita potencial. `CodigoBarras` existe como dataclass, mas os repositórios de códigos trabalham diretamente com strings/IDs. `LogMovimentacao.estoque_posterior` subtrai a quantidade nas saídas e soma nos demais tipos.

O banco limita o tipo de log a Entrada, Saída e Ajuste. As validações de domínio ficam principalmente no controlador, não em constraints para saldo, preço e custo. Os valores monetários são `float`/SQLite `REAL`; não há Decimal ou armazenamento em centavos.

`BancoDados.transacao()` usa `BEGIN IMMEDIATE`, COMMIT e ROLLBACK. Chamadas aninhadas reutilizam a transação externa; não criam savepoints. Se uma exceção interna for absorvida antes de alcançar o contexto externo, esse mecanismo não faz rollback independente.

| Repositório | Responsabilidade |
|---|---|
| `RepositorioProdutos` | Inserir, obter por ID, atualizar saldo/custo, listar, buscar e preparar exportação; `atualizar_dados` existe sem fluxo de edição conectado |
| `RepositorioCodigosBarras` | Vincular, desvincular, resolver código para ID e listar códigos por produto |
| `RepositorioLogs` | Inserir, obter por ID, localizar último válido, cancelar e listar histórico com dados atuais do produto |
| `RepositorioRelatorios` | Totais, volume diário, saídas por marca/categoria, ranking e produtos parados |

Não há migração/versionamento de esquema, restauração, exclusão de produto ou backup SQLite implementados. `CREATE TABLE IF NOT EXISTS` não atualiza estruturas existentes. CSV é exportação de dados, sem rotina inversa de importação/restauração.

## 4. Regras de negócio e contratos

`ErroNegocio` transporta mensagens prontas para a interface. As validações convertem os campos PT-BR, exigem quantidade positiva nas movimentações, estoque inicial não negativo e valores monetários não negativos. Marca e categoria devem pertencer às listas fixas.

### Cadastro

`cadastrar_produto` limpa nome e códigos, elimina códigos vazios/duplicados preservando ordem e verifica se os códigos já pertencem a outro produto. Produto, vínculos e eventual log inicial são gravados na mesma transação. Quantidade inicial positiva gera Entrada com observação `Cadastro inicial`, estoque anterior 0 e custo anterior 0. Cadastro sem estoque não gera log.

É permitido cadastrar produto sem código. Não há validação de dígitos, comprimento ou dígito verificador GTIN: os códigos são strings. Um código alternativo identifica o mesmo saldo, sem fator de conversão. Embora a interface mencione kits, não existe composição de kit nem baixa automática de múltiplos componentes.

### Entrada

`registrar_entrada` consulta o produto, soma a quantidade e calcula:

```text
novo custo = (saldo anterior × custo anterior + quantidade × custo unitário)
             / (saldo anterior + quantidade)
```

Arredonda para quatro casas. Saldo anterior zero ou negativo faz o custo assumir o custo da entrada. Campo de custo vazio usa o custo médio atual; o cálculo ainda passa pelo arredondamento. Cadastro inicial não aplica o mesmo arredondamento obrigatório. O log de Entrada registra o custo unitário recebido, e não o custo médio resultante.

### Saída

`registrar_saida` reduz o saldo e mantém o custo médio. Pela configuração atual, rejeita saldo negativo. A quantidade do log é positiva; o tipo Saída determina a subtração. Não registra preço efetivamente praticado, pagamento, cliente, desconto, lucro ou documento fiscal. Portanto, os rankings de “vendidos” medem saídas, incluindo baixas que possam não ser vendas.

### Ajuste

`ajustar_produto` aceita saldo absoluto e/ou novo custo; campos ausentes preservam o valor consultado. Rejeita ausência de valores e ajuste sem mudança. Registra quantidade como delta, inclusive zero para ajuste só de custo; `custo_no_momento` é o novo custo. Motivo vazio recebe `Ajuste manual (Admin)`.

### Desfazer

`obter_ultima_acao` apresenta a última movimentação válida; `desfazer_ultima_acao` consulta novamente o último log válido, restaura estoque/custo anteriores e marca `cancelado=1`. É uma pilha global por ID, não uma pilha por produto, usuário ou sessão. Pode desfazer ações de execuções anteriores, ajustes administrativos e entradas do cadastro. Não remove o produto nem os códigos cadastrados. Não há refazer.

`ResultadoMovimentacao` devolve log ID, tipo, produto atualizado, quantidade e estado anterior; propriedades expõem saldo/custo novos. `ResultadoDesfazer` devolve log e produto restaurado. Nome/marca/categoria mostrados no histórico vêm do produto atual via JOIN, não de snapshots desses textos.

### Códigos adicionais

Vincular verifica produto e disponibilidade do código; desvincular verifica existência. Essas ações não criam logs de movimentação e não entram no desfazer. Remover o último código é permitido.

## 5. Telas, estados e eventos

| Arquivo / classe | Construção, eventos e estado |
|---|---|
| `views/main_view.py` / `JanelaPrincipal` | Sidebar, atalhos, cache das cinco telas, navegação, alternância de tema e fechamento |
| `views/view_operacao.py` / `ViewOperacao` | Seletor Entrada/Saída, código, produto atual, quantidade/custo, modo rápido, mensagens e oito logs recentes |
| `views/view_cadastro.py` / `ViewCadastro` | Formulário de novo produto, sugestões e lista temporária de códigos |
| `views/view_admin.py` / `ViewAdmin` | PIN, busca/seleção de produto, ajuste absoluto, vínculo/desvínculo e bloqueio manual |
| `views/view_dashboard.py` / `ViewDashboard` | Três KPIs, barras, duas rosquinhas e listas de mais vendidos/parados |
| `views/view_relatorios.py` / `ViewRelatorios` | Busca de produtos, histórico filtrável e exportação geral |

**Operação:** o leitor USB é tratado como teclado que envia código + Enter. `_ao_ler_codigo` resolve o produto; desconhecido oferece abrir Cadastro passando `codigo`. Normalmente o foco vai para quantidade; Enter em quantidade/custo confirma. No modo rápido, define quantidade 1 e confirma imediatamente usando o tipo selecionado e o custo que estiver no campo. `_confirmar` chama o controlador, mostra resultado, limpa produto/quantidade/custo e atualiza recentes. Escape limpa nos campos vinculados. Um callback a cada 400 ms tenta restaurar foco no código quando a tela está visível, respeitando seus campos e diálogos. `_desfazer` solicita confirmação e atualiza histórico. Voltar à tela atualiza recentes, mas não recarrega automaticamente um produto já selecionado.

**Cadastro:** o trace de `var_nome` procura categoria/marca em listas ordenadas de palavras-chave. Seleção manual ativa flags que impedem novas sugestões até limpar o formulário. Sem nova correspondência, uma sugestão anterior pode permanecer. `_adicionar_codigo` verifica vínculo existente e adiciona à lista local; salvar envia somente códigos já adicionados à lista. `ao_mostrar(codigo)` acrescenta esse código ao formulário existente, sem limpá-lo. Salvar limpa após sucesso e permanece no Cadastro; não retoma automaticamente a movimentação que levou ao cadastro.

**Admin:** compara o PIN diretamente com `config.PIN_ADMIN`. O desbloqueio fica na instância da tela e persiste ao navegar; não há prazo de sessão. `_buscar` tenta código exato primeiro, depois busca textual; resultado único é selecionado. `_carregar_produto` preenche os campos de saldo/custo e códigos. Ajustar confirma, grava, recarrega produto e busca. Remover um chip chama o controlador antes da remoção visual. `ao_mostrar` apenas escolhe o quadro bloqueado/desbloqueado; não recarrega o produto existente. O PIN protege o acesso visual, sem autorização no controlador.

**Dashboard:** atualiza ao aparecer, ao clicar Atualizar e ao mudar tema. O campo de dias altera somente estoque parado; as barras continuam usando `DIAS_GRAFICO_MOVIMENTACAO`. Entrada inválida de dias volta ao padrão; valor menor que 1 é usado como 1. Gráficos recriam eixos e usam `draw_idle`, cores do tema e fundo efetivo do widget. Sem dados, mostram mensagens. Falhas na atualização são apresentadas em diálogo.

**Relatórios:** a busca usa debounce de 250 ms. Selecionar produto filtra o histórico por ID; “Mostrar todos” limpa esse filtro. O filtro não é automaticamente limpo ao alterar a busca. `ao_mostrar` recarrega busca e logs. Cancelados permanecem visíveis em cor suave. `_exportar` exporta todo estoque/histórico, independentemente dos filtros da tela, e oferece abrir a pasta no Explorer.

## 6. Consultas, indicadores e exportações

- Busca normaliza acentos, caixa e espaços, separa palavras e exige TODAS; cada uma pode ocorrer no nome, marca, categoria ou código. Usa LIKE com parâmetros, até 500 resultados, sem paginação. `%` e `_` digitados continuam sendo curingas LIKE.
- KPIs: soma de unidades; investimento = soma de saldo × custo médio; receita potencial = soma de saldo × preço base. A consulta também retorna quantidade de produtos, não exibida entre os três cartões.
- Barras: 30 dias incluindo hoje, com preenchimento de dias vazios por zero. Contam Entradas e Saídas válidas; excluem Ajustes/cancelados e incluem entradas de cadastro.
- Rosquinhas: saídas válidas de todo o histórico por marca/categoria. Quando excede o limite, reserva uma posição para “Outras”. Não usa o intervalo de 30 dias das barras.
- “Curva A”: top 5 por unidades saídas, desempate por quantidade de movimentações. Não calcula classificação ABC por receita ou percentual acumulado.
- Estoque parado: somente saldo positivo; referência é a última saída válida, ou primeira movimentação válida, ou cadastro. Inclui referência estritamente anterior ao limite. Reposição recente não redefine uma última saída antiga.
- Logs: ordem decrescente de ID, cancelados incluídos por padrão, com saldo posterior calculado. O histórico completo não tem paginação.
- Exportação: dois CSVs via pandas, UTF-8 com BOM, `;` como separador e vírgula decimal. Exporta colunas fixas mesmo quando vazio; cancelamento vira Sim/Não. Nomes usam minuto (`AAAAMMDD_HHMM`), podendo sobrescrever exportações do mesmo minuto.
- Os dois arquivos e suas consultas não são uma única operação atômica/snapshot; falha no segundo pode deixar apenas o primeiro atualizado. Não há importador desses arquivos.

## 7. Componentes, utilitários e configuração

`views/componentes.py` centraliza paletas claro/escuro, cores de estado, detecção do modo, conversão de cores Tk para hexadecimal e busca do fundo efetivo subindo pelos pais transparentes. `aplicar_estilo_treeview` configura tema ttk clam, fontes, seleção e cabeçalhos. `criar_tabela` recebe definições de colunas e entrega frame + Treeview com rolagem vertical. `limpar_tabela` apaga linhas. `CartaoKPI` apresenta título/valor. `ListaCodigos` mantém lista local, evita repetição em adicionar e redesenha chips; callback opcional pode vetar remoção. Os quatro helpers de diálogo encapsulam messagebox.

`utils/texto.py` usa Unicode NFKD para remover acentos. `_contem_termo` aplica limites de palavra via lookarounds e escapa a expressão. Sugestões retornam a primeira correspondência em `config`. Formatação de moeda usa duas casas, inteiros usam ponto de milhar, datas ISO viram apresentação brasileira. Conversão decimal aceita formatos brasileiros e ponto decimal; conversão inteira aceita milhar com ponto. São convenções diferentes: `1.000` vira 1000 no conversor inteiro e 1.0 no conversor decimal.

`config.py` contém nome/versão, tamanhos da janela, tema padrão escuro, caminhos locais, PIN padrão, bloqueio de negativo, prazos, limites dos rankings/recentes, precisão do custo, tipos de movimentação, 17 marcas, cinco categorias e palavras-chave ordenadas. Não há tela de preferências, gravação do tema escolhido ou configuração externa persistente.

## 8. Ambiente, execução e distribuição

| Arquivo | Papel |
|---|---|
| `requirements.txt` | Mínimos de CustomTkinter, matplotlib e pandas, sem lockfile |
| `1_preparar_ambiente.bat` | Cria `.venv`, atualiza pip e instala requisitos + PyInstaller |
| `2_executar.bat` | Executa `main.py` pelo Python do `.venv` |
| `3_gerar_exe.bat` | Descobre recursos do CustomTkinter e gera distribuição em pasta, sem console, com PyInstaller |
| `build/GestorEstoque.spec` | Artefato existente com caminho absoluto antigo para CustomTkinter; o BAT gera outro spec |
| `.vscode/settings.json` | Seleção do Python virtual, ativação do terminal e ocultação de caches/build |
| `.vscode/launch.json` | Depuração de `main.py` com debugpy e cwd na raiz do fonte |
| `.gitignore` | Exclui ambiente, caches, build/dist, SQLite/WAL/SHM, CSVs e logs |
| `README.md` | Instruções de uso/desenvolvimento; a orientação de apagar o banco para mudar esquema não preserva dados |
| `ANALISE_PROJETO.md` | Auditoria anterior, defeitos e observações de ambiente; dados temporais precisam de nova verificação |

Mudar fonte não atualiza BUILD nem dist automaticamente. O BAT escreve em dist, não em BUILD. Banco/exportações/logs ficam junto do fonte ou executável conforme o modo; são bases separadas. Reconstruir a distribuição com `--noconfirm` exige preservar os dados que estejam nela. Arquivos WAL/SHM podem conter estado relevante; copiar apenas o `.db` durante uso não equivale a backup consistente.

## 9. Evidências e limitações desta análise

Executado novamente: `.venv\Scripts\python.exe -B auditoria/verificar.py` na raiz do fonte. Resultado: 19 testes, 13 aprovados e seis `expectedFailure`. A suíte usa SQLite em memória e arquivos temporários; não abre os bancos de uso. O teste do Admin simula a formatação do campo, não automatiza a interface real.

As seis falhas esperadas continuam reproduzidas:

1. Duas instâncias podem perder atualização: leitura/cálculo acontecem antes da transação de escrita. O saldo final pode divergir da soma dos logs.
2. Admin exibe/preenche custo com duas casas e o reenvia ao ajustar saldo, perdendo precisão de quatro casas.
3. Custo infinito não é rejeitado como regra de negócio.
4. NaN chega ao SQLite e gera erro de integridade, em vez de `ErroNegocio`.
5. Exportações no mesmo minuto usam o mesmo destino.
6. “Tônico capilar” encontra “tônico” de Skincare antes do termo específico de Cabelos.

Limitações estruturais observadas na leitura: PIN somente visual; desfazer permite reverter ajuste sem PIN; vínculo/desvínculo não é auditado; buscas/histórico não paginam; tabelas não têm rolagem horizontal; importações gráficas ficam fora do try final de main; exceções Tk não recebem tratamento global próprio. Entradas/saídas/cadastro/Admin geralmente capturam somente `ErroNegocio`, enquanto exportação/dashboard capturam exceções mais amplas.

Esta etapa não executou interface, scanner físico, novo empacotamento ou executáveis, nem verificou integridade/conteúdo dos bancos reais ou vulnerabilidades de dependências. Os comportamentos visuais foram compreendidos por leitura, sem validação interativa. Nenhum módulo de produção foi alterado.

## 10. Mapa de impacto para próximas alterações

| Alteração desejada | Partes que precisam ser consideradas juntas |
|---|---|
| Entrada, saída, custo ou desfazer | ControladorEstoque, transação/repos de produtos e logs, ViewOperacao, auditoria |
| Novo campo de produto | Schema/dataclass/conversor, consultas, cadastro/controlador, telas, CSV e migração de bancos existentes |
| Edição de nome/marca/categoria/preço | Método de repositório já existe; faltam fluxo de controlador/interface e decisão sobre histórico de metadados |
| Código de barras/kit | Repositório de códigos, cadastro/Admin/Operação; kit composto exigiria modelo próprio |
| Indicador ou filtro temporal | Consultas de RepositorioRelatorios, ControladorRelatorios e ViewDashboard |
| Exportação/importação/backup | ControladorRelatorios, contrato de colunas, paths/config e consistência SQLite |
| Visual ou tema | Tela específica, componentes, hooks da JanelaPrincipal e integração matplotlib |
| Usuários/permissões | Modelo e controlador além do PIN visual; considerar desfazer e identificação nos logs |
| Distribuição | BAT/spec, recursos gráficos, dependências e separação/preservação dos dados |

Antes de cada mudança, verificar o fonte atual: este mapa é um snapshot, não substitui reler os trechos envolvidos. Não presumir qual distribuição/banco é usado diariamente sem evidência adicional.
