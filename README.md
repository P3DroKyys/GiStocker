# Gestor de Estoque – Cosméticos

### Gestão de dados nas Configurações

Backup completo em JSON, restauração com a senha da instalação atual e importação
aditiva de produtos por CSV UTF-8 estão disponíveis na engrenagem de Configurações.
A exportação JSON exige confirmação da senha e gera um arquivo **sem criptografia**;
o banco local permanece criptografado. Consulte [o guia de gestão de dados](GESTAO_DADOS.md)
para o modelo, regras de importação, cópia de segurança e limites.

### Busca automática no Admin — 1.2.0

Em **Admin → Ajustes e códigos**, digite na barra para filtrar automaticamente.
O botão Buscar foi removido. A pesquisa aguarda 220 ms após a última alteração;
Enter continua disponível para leitores de código de barras.

Resultados exatos e pelo nome aparecem primeiro. A busca ignora acentos/caixa,
aceita palavras em outra ordem, início e trechos de palavras e termos combinados
de nome, marca e categoria. Se nada corresponder diretamente, usa a distância
Damerau–Levenshtein do RapidFuzz para sugerir pequenos erros de escrita, como
`malbce` → `Malbec`. Aproximações são identificadas e exigem seleção manual.

Use `#123` para localizar o ID 123; números sem `#` continuam úteis para volumes
e códigos. Código de barras completo precisa corresponder exatamente, mantendo
zeros à esquerda. Prefixos/trechos numéricos de ao menos três dígitos também
localizam códigos parciais. `%` e `_` são pesquisados literalmente.
Todas as palavras relevantes precisam corresponder; não são sugeridos produtos
apenas porque contêm uma das palavras de uma consulta sem relação.

Mudar a pesquisa limpa imediatamente o produto selecionado. Campo vazio lista
todos; **Mostrar mais** carrega os próximos 200 resultados quando necessário.
O índice fica somente na memória da sessão e é atualizado após mudanças no banco.
A melhoria desta versão é da aba **Ajustes e códigos**; os filtros existentes do
catálogo e de relatórios continuam com seus comportamentos anteriores.

Pelo fonte, atualize as dependências com `1_preparar_ambiente.bat` antes de abrir.
Detalhes e evidências: `auditoria/BUSCA_1_2_0.md`.

### Segurança e acesso — 1.1.1

O banco é aberto somente depois de ser descriptografado pela senha. Não há senha
inicial nesta versão. Na primeira abertura de uma instalação antiga, informe a
senha atual e crie uma senha com 6 a 128 caracteres. Guarde-a: sem ela
não é possível recuperar os dados. A migração deve acontecer com versões antigas
fechadas; os testes e a geração da build não convertem o estoque real.

Banco, backups e novas exportações usam SQLCipher. Cópias antigas da instalação
são preservadas em contêineres criptografados `.gsa`, com verificação antes da
remoção dos originais. A exportação CSV sem senha fica desabilitada nas sessões
protegidas. Apagar configurações não redefine a chave do banco.

**Configurações** mantém versão, tema e troca de senha mediante senha atual.
**Bloquear agora / Ctrl+L** encerra a sessão; 90 minutos sem uso também bloqueiam.
Senhas existentes continuam válidas. Senhas mais longas são recomendadas para
resistir a tentativas de adivinhação em cópias do banco; sequências óbvias são rejeitadas.
A escolha claro/escuro fica em `dados/aparencia.json`, sem credenciais.
Backups antigos continuam usando a senha que tinham quando foram gerados.

Leia [SEGURANCA.md](SEGURANCA.md) para ativação, atualização de build, recuperação,
cópias antigas e limites contra malware/administradores do computador. A build
é para Windows x64; para desenvolvimento use **Python 3.14 x64**. As dependências
exatas e seus hashes estão em `requirements.lock`, incluindo a wheel local em
`vendor`. Execute novamente `1_preparar_ambiente.bat` para atualizar o ambiente.

No Cadastro, preço de venda base e custo inicial são opcionais: campos em branco
são gravados como R$ 0,00. Valores informados continuam sujeitos às validações.
As demais regras do cadastro permanecem iguais. O Admin não tem mais o campo
Motivo; o ajuste continua registrado no histórico como "Ajuste manual (Admin)".
O Dashboard mostra **Produtos cadastrados**, incluindo produtos sem estoque e
contando cada cadastro uma vez, mesmo com vários códigos. A legenda de entradas
e saídas fica abaixo do gráfico, fora da área das barras; os quatro indicadores
se reorganizam em duas linhas quando a janela é menor.

Testes: suíte `verificar*.py` e integração com widgets reais, bancos descartáveis
e janela oculta em `auditoria/smoke_interface_upgrade.py`. A prévia visual aceita
`--tela acesso`, `--tela configuracoes` e `--tamanho 1024x680`.

### Identidade visual GiStocker

Na versão 1.0.2, mensagens de erro, aviso, sucesso e confirmação usam diálogos
próprios em `views/dialogos.py`, com as cores claras/escuras do aplicativo, ícones
desenhados para o GiStocker, texto com quebra de linha e rolagem para mensagens
extensas. A barra de título também acompanha o tema no Windows. Escape ou fechar
cancela; Tab alterna entre botões e Enter aciona o botão focado. Confirmações abrem
com Cancelar como opção inicial, evitando confirmar uma ação por engano.

Prévia sem banco: `.venv\Scripts\python.exe -B auditoria/preview_dialogos.py`.
O diálogo nativo do Windows fica apenas como último recurso se a própria interface
gráfica falhar durante a inicialização.

A interface usa a logo original em `assets/gistocker.png` e o tema compartilhado
`assets/tema.json`: tons neutros, destaque azul, fonte Segoe UI no Windows e
componentes arredondados nos modos claro/escuro. A navegação e os atalhos permanecem
os mesmos. As tabelas de relatórios permitem rolagem horizontal.

`config.DIRETORIO_RECURSOS` resolve imagens/tema tanto pelo fonte quanto dentro do
pacote PyInstaller. O script `3_gerar_exe.bat` inclui a pasta `assets` no executável.
Mantenha essa pasta ao distribuir o código. Os caminhos dos bancos não mudaram.

O ícone próprio está em `assets/icone_gistocker.ico`, com transparência e nove
resoluções de 16 a 256 pixels. A imagem fornecida está preservada em
`assets/icone_gistocker.png`. O ícone é aplicado à janela no Windows e ao próximo
executável gerado pelo BAT; executáveis já existentes não são modificados.

Prévia com produtos fictícios e banco criptografado descartável:
`.venv\Scripts\python.exe -B auditoria/preview_visual.py`.
Aceita `--tema light` e `--tela dashboard`, por exemplo. Não usa os dados da loja.

Aplicação desktop local (Python 3.14 x64, customtkinter, SQLCipher/SQLite, matplotlib, pandas)
para controle de estoque de loja de cosméticos com leitor de código de barras USB.

## Como editar no VSCode

1. Abra esta pasta no VSCode (**Arquivo > Abrir Pasta**, selecione `estoque_cosmeticos`).
2. Dê dois cliques em **`1_preparar_ambiente.bat`** (só na primeira vez).
   Ele cria a pasta `.venv` e instala tudo o que o programa precisa.
3. Edite os arquivos `.py` normalmente.
4. Para testar, use **`2_executar.bat`** ou tecle **F5** dentro do VSCode.
5. Para gerar o programa final, use **`3_gerar_exe.bat`**.
   O resultado aparece em `dist\GiStocker_DATA_HORA_ID\GestorEstoque\GestorEstoque.exe`.
   O BAT mostra o caminho completo. Cada geração reserva uma pasta nova e preserva
   as anteriores, inclusive dados e backups. Distribua a pasta `GestorEstoque` inteira.
   Os destinos exclusivos herdam as permissões de `dist`, permitindo abrir a build
   pela conta do Windows mesmo quando a compilação usa uma conta de automação.

### Correções de estabilidade — 1.0.1

Os 14 problemas daquela auditoria foram corrigidos. Na versão 1.0.1, as exportações ficavam
em `exportacoes/exportacao_DATA_HORA_ID/`, com estoque e histórico do mesmo snapshot.
A pasta final só era publicada após gravar os dois CSVs; exportações anteriores não
eram sobrescritas. Textos que poderiam virar fórmulas recebiam um apóstrofo inicial
na exportação. Na versão 1.1.0, esse formato foi substituído por cópias protegidas
`.db`, para não deixar dados legíveis sem senha na pasta.

As buscas mostram todos os resultados. A remoção de código no Admin verifica o
produto esperado. Sugestões automáticas são limpas quando deixam de corresponder
ao nome, preservando escolhas manuais. Erros de persistência recebem mensagem
e registro técnico em `erros.log` quando o disco permite gravar.

Quantidades e saldos respeitam INTEGER de 64 bits; totais de relatórios usam somas
sem overflow inteiro. Novos preços/custos têm teto de R$ 1 trilhão, configurável em
`LIMITE_VALOR_UNITARIO`. Custos novos usam quatro casas decimais; entradas sem custo
preservam exatamente o valor anterior, inclusive em cadastros legados.

Para atualizar uma instalação com dados: feche todas as instâncias, preserve a
pasta atual completa e copie apenas `GestorEstoque.exe` e `_internal` da nova build
para a pasta da instalação. Mantenha `dados` e `exportacoes` existentes. Abrir a
nova build em outra pasta inicia uma base própria, não transfere a base da loja.

> Pré-requisito: Python 3.14 de 64 bits instalado, marcando
> "Add Python to PATH" durante a instalação.

Em uma instalação nova, `dados/estoque.db` é criado somente depois de definir
uma senha válida na tela de acesso. Não há senha inicial nem senha de recuperação.

### Onde mexer para cada tipo de mudança

| Quero mudar… | Arquivo |
|---|---|
| Marcas, categorias, cores do tema, dias do "estoque parado" | `config.py` |
| Criptografia, acesso e aparência | `models/seguranca.py` |
| Leitura de configurações antigas para migração | `models/preferencias.py` |
| Tela de acesso e painel de configurações | `views/acesso.py`, `views/view_configuracoes.py` |
| Palavras-chave do preenchimento automático | `config.py` (no fim) |
| Layout da tela de leitura de código de barras | `views/view_operacao.py` |
| Campos da tela de cadastro | `views/view_cadastro.py` |
| Gráficos e indicadores | `views/view_dashboard.py` |
| Colunas das tabelas e exportação | `views/view_relatorios.py` |
| Cálculo de custo, regras de entrada/saída | `controllers/controllers.py` |
| Estrutura das tabelas do banco | `models/models.py` |

> Não apague o banco para atualizar o sistema. A versão do esquema é controlada
> por `PRAGMA user_version`; alterações futuras devem ser implementadas como
> migrações transacionais que preservem os registros.

### Segurança do banco SQLite

As gravações de cadastro, códigos, entrada, saída, ajuste e desfazer usam transação
desde a leitura/validação até a gravação do saldo e histórico. Há espera de até
cinco segundos por outro escritor; se continuar ocupado, a interface mostra uma
mensagem para tentar novamente. Transações aninhadas usam savepoints. WAL e
`synchronous=FULL` permanecem ativos nos bancos em disco.

Após autenticar um banco existente, o sistema cria um backup SQLCipher consistente na pasta
`backups` dentro da pasta do banco (normalmente `dados/backups`). Inclui o estado do
WAL, tem nome único e passa por `integrity_check`. A migração de segurança cria uma cópia criptografada e validada antes de
substituir o arquivo antigo, mantendo as tabelas e os registros atuais. Bancos de uma
versão futura são recusados. Se o backup falhar, a abertura é interrompida e o erro
é informado pelo tratamento de inicialização; não se prossegue silenciosamente.

Os snapshots `.gsbackup` automáticos de `dados/backups` (diários e anteriores a uma
restauração) mantêm as `BACKUPS_MANTIDOS` cópias mais recentes (30, em `config.py`);
cópias `.gsa` legadas e exportações manuais não são descartadas. Não há botão de
restauração de `.gsbackup` nesta etapa.
São snapshots na abertura, não proteção contínua das movimentações feitas depois.
Guarde cópias também fora desse disco. A API `BancoDados.criar_backup(pasta)` permite
gerar snapshots adicionais fora de uma transação.

Para recuperação assistida: feche **todas** as instâncias e preserve a pasta de
dados atual completa, incluindo WAL/SHM. Valide o backup escolhido em pasta
separada. Prepare uma pasta de dados limpa com a cópia validada renomeada para
`estoque.db`, sem misturar WAL/SHM da base anterior, e só então coloque-a no lugar
da pasta ativa. Mantenha a pasta antiga preservada até conferir os dados restaurados.
Não troque arquivos enquanto houver aplicação usando o banco.

O Admin preserva a precisão do custo e rejeita ajuste baseado em saldo/custo
desatualizado. Desfazer exige que o último log ainda seja o apresentado na confirmação.
Valores monetários NaN/infinito são rejeitados antes de gravar.

Feche versões antigas antes de usar esta atualização: executáveis anteriores não
possuem essas proteções. Para testar todas as regressões isoladas:
`.venv\Scripts\python.exe -B -m unittest discover -s auditoria -p "verificar*.py"`.

## Estrutura (MVC)

```
estoque_cosmeticos/
├── 1_preparar_ambiente.bat # cria o .venv e instala as bibliotecas (uma vez só)
├── 2_executar.bat          # abre o programa a partir do código-fonte
├── 3_gerar_exe.bat         # chama gerar_build.py, sempre em uma nova pasta de dist
├── main.py                 # tela de acesso; controladores somente após autenticação
├── config.py               # caminhos, regras, marcas, categorias, palavras-chave
├── requirements.txt
├── models/
│   ├── models.py           # BancoDados (SQLite, transações), dataclasses e repositórios
│   ├── seguranca.py        # autenticação criptográfica, migração, chave e sessão
│   └── preferencias.py     # leitura das configurações antigas, somente para migração
├── controllers/
│   └── controllers.py      # ControladorEstoque (1:N, custo médio, desfazer, ajuste)
│                           # ControladorRelatorios (KPIs, gráficos, rankings, cópias protegidas)
├── views/
│   ├── main_view.py        # JanelaPrincipal: barra lateral, troca de telas, tema
│   ├── acesso.py           # desbloqueio inicial e campos de senha
│   ├── view_configuracoes.py # versão, aparência, troca de senha
│   ├── componentes.py      # paleta, Treeview estilizada, CartaoKPI, ListaCodigos, diálogos
│   ├── view_operacao.py    # leitura de código, ENTRADA/SAÍDA, quantidade, desfazer
│   ├── view_cadastro.py    # cadastro com gatilho inteligente e múltiplos códigos
│   ├── view_dashboard.py   # KPIs + gráficos matplotlib + Curva A / Estoque parado
│   ├── view_relatorios.py  # busca inteligente, histórico, exportação protegida
│   └── view_admin.py       # ajuste manual (log "Ajuste"), gestão de códigos
├── utils/
│   └── texto.py            # normalização, sugestão de categoria/marca, formatação
├── dados/                  # estoque.db criptografado e aparência (criados em tempo de execução)
└── exportacoes/            # cópias criptografadas do estoque e do histórico
```

## Regras de negócio principais

* **Códigos 1:N** – `Codigos_Barras.codigo` é chave primária e aponta para
  `Produtos.id`; qualquer código vinculado resolve para o mesmo estoque.
* **Custo médio ponderado** – em cada Entrada:
  `novo = (estoque × custo_atual + qtd × custo_entrada) / (estoque + qtd)`.
  Sem estoque anterior, o custo passa a ser o da entrada.
* **Desfazer** – cada log guarda `estoque_anterior` e `custo_anterior`; o
  desfazer restaura esse instantâneo e marca o log como `cancelado = 1`
  (nunca apaga o histórico).
* **Ajuste (Admin)** – sobrescreve estoque/custo e grava log tipo "Ajuste" com
  `quantidade` = delta e `custo_no_momento` = novo custo.
* **Saída maior que o estoque** é bloqueada por padrão
  (`PERMITIR_ESTOQUE_NEGATIVO` em `config.py`).

## Atalhos

### Validação de GTIN / código de barras

O Cadastro e o vínculo de códigos no Admin validam o GTIN antes de aceitá-lo na
interface. Os controladores repetem essa validação antes de gravar, inclusive em
chamadas diretas sem interface. A função central é `utils/gtin.py:validar_gtin`.

A ordem de validação é: exigir string, aparar espaços nas extremidades, aceitar
somente caracteres ASCII `0–9`, exigir 8/12/13/14 dígitos, rejeitar sequências de um
único dígito repetido e conferir o DV pelo Módulo 10 GS1. DV incorreto retorna
exatamente **Código GTIN/EAN inválido**. Soma múltipla de dez resulta em DV zero.

Os campos continuam sendo `CTkEntry` textuais. A validação acontece ao Adicionar,
Vincular ou Salvar, sem apagar letras/caracteres internos para transformar uma
entrada inválida em outro código. Um código digitado e ainda não adicionado à lista
também é validado ao salvar; códigos vindos da Operação passam pela mesma checagem.
Zeros à esquerda são preservados. O preenchimento até 14 dígitos é temporário,
somente para o cálculo; não muda o texto salvo no SQLite.

Essa verificação é local e não confirma que um GTIN foi atribuído a um produto real
pela GS1. Referência: [cálculo do dígito verificador GS1](https://www.gs1.org/services/how-calculate-check-digit-manually).
Produtos sem códigos continuam permitidos. Códigos antigos já gravados não são
reescritos ou removidos automaticamente; a nova validação protege cadastros e vínculos novos.

Teste isolado: `.venv\Scripts\python.exe -B auditoria/verificar_gtin.py`.

### Painel de produtos no Admin

Após desbloquear o software, abra **Admin (F5)**. A aba **Produtos cadastrados** mostra todos os
produtos, incluindo ID, nome, marca, categoria, estoque, custo médio, preço base,
códigos de barras e data de cadastro.

- Digite na busca para localizar por nome, marca, categoria, código ou ID; a busca ignora acentos.
- Combine os filtros de marca e categoria ou use **Limpar filtros**.
- Clique no título de uma coluna para ordenar; clique novamente para inverter a ordem.
- Use a barra horizontal abaixo da tabela para acessar as demais colunas.
- Selecione uma linha para ver os códigos completos e o custo médio com quatro casas.
- Dê dois cliques na linha ou clique em **Abrir ajustes do produto** para acessar
  a aba **Ajustes e códigos**, com as operações administrativas já existentes.
- Ao voltar à aba da tabela, os dados são recarregados. O botão **Atualizar** também
  permite atualizar a listagem mantendo os filtros.

O painel é de consulta; nome, marca, categoria e preço ainda não são editáveis nele.
O painel de produtos mantém as mesmas informações; a versão 1.1.0 protege o arquivo do banco. Para testar esta atualização pelo fonte, use
`2_executar.bat`; executáveis já existentes precisam ser gerados novamente para recebê-la.

F1 Operação · F2 Cadastro · F3 Dashboard · F4 Relatórios · F5 Admin ·
Ctrl+L bloqueia · Enter confirma · Esc limpa a tela de operação.
