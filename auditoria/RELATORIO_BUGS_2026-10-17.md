# Relatório de bugs — GiStocker 2.0.0-preview.1

- **Data:** 2026-10-17
- **Escopo:** todo o código-fonte da árvore de trabalho atual (incluindo as alterações não commitadas de "Gestão de dados": `gestao/`, `servico/gestao.py`, `servico/transferencia.py`, `views/gestao_dados.py`), instalador (`instalador/`) e scripts de build.
- **Método:** leitura integral do código + execução da suíte existente + testes exploratórios próprios executados numa **cópia isolada** do projeto (nenhum arquivo do projeto, banco real ou pasta `dados/` foi alterado).
- **Suíte existente:** `python -m unittest discover -s auditoria -p "verificar*.py"` → **257 testes, todos OK**. Os bugs abaixo não são cobertos por ela.
- **Ambiente de teste:** Windows 11, Python 3.14.3 (`.venv` do projeto), PowerShell 5.1.26100.

---

## 0. Instruções para a IA que vai corrigir

1. Cada bug tem um **ID estável** (`BUG-NN`), severidade, status de verificação, arquivos/linhas, reprodução, causa raiz, direção de correção e critério de aceite.
2. **Status de verificação:**
   - `CONFIRMADO-TESTE`: reproduzido por execução real (saída registrada aqui).
   - `CONFIRMADO-LEITURA`: comportamento determinístico, verificado no código.
   - `PROVÁVEL`: depende de ambiente/hardware; requer confirmação manual antes de corrigir.
3. **Restrições do projeto que a correção NÃO pode quebrar:**
   - O banco é SQLCipher; nunca gravar dados em texto puro em disco (exceto a exportação JSON explícita).
   - `models/seguranca.validar_esquema_legado()` e `multicanal/esquema.conferir_objeto()` funcionam como **lista branca do esquema**: qualquer índice/tabela/trigger novo **precisa ser adicionado a essa lista branca**, senão bancos existentes deixam de abrir ("estrutura inesperada"). Isso é crítico para BUG-03 e BUG-04.
   - O protocolo IPC (`servico/protocolo.py`) é JSON fechado; não introduzir pickle/eval.
   - Não registrar senhas, tokens ou payloads em logs.
4. Os números de linha referem-se aos arquivos no estado de 2026-10-17. Confirme com uma busca antes de editar.
5. O Apêndice A traz um "harness" para reproduzir os bugs de serviço sem interface gráfica e sem tocar em `dados/`.

---

## 1. Resumo

| ID | Severidade | Status | Título curto | Arquivo principal |
|---|---|---|---|---|
| BUG-01 | CRÍTICA | CONFIRMADO-TESTE | Reinstalar/atualizar corrompe `operadores.json` e derruba o serviço | `instalador/servico.ps1` |
| BUG-02 | CRÍTICA | CONFIRMADO-TESTE | Movimentação idêntica posterior é "engolida" por id pendente antigo | `servico/cliente.py`, `servico/pendencias.py` |
| BUG-03 | CRÍTICA | CONFIRMADO-TESTE | Cada gravação custa O(produtos × eventos): 0,9 s a 2,5 s por venda | `multicanal/motor.py` |
| BUG-04 | CRÍTICA | CONFIRMADO-TESTE | Histórico completo (Relatórios) quebra com ~20 mil movimentações e bloqueia a sessão | `servico/nucleo.py`, `servico/pipe.py` |
| BUG-05 | CRÍTICA | CONFIRMADO-TESTE | "1.500" é gravado como R$ 1,50 (separador de milhar pt-BR) | `utils/texto.py` |
| BUG-06 | ALTA | CONFIRMADO-TESTE | Simulação ativa trava o agente (6 s com 200 produtos, 105 s com 800 por ciclo) | `multicanal/sincronizacao.py`, `multicanal/motor.py` |
| BUG-07 | ALTA | CONFIRMADO-TESTE | Senha atual errada em "Alterar senha" encerra a sessão | `servico/cofre.py`, `servico/cliente.py` |
| BUG-08 | ALTA | CONFIRMADO-TESTE | Falha no backup diário impede login com senha correta ("Senha incorreta") | `servico/cofre.py`, `servico/nucleo.py` |
| BUG-09 | ALTA | CONFIRMADO-TESTE | Primeiro acesso: validação da nova senha aparece como "Senha incorreta" + espera + pastas órfãs | `servico/cofre.py`, `servico/nucleo.py` |
| BUG-10 | ALTA | CONFIRMADO-TESTE | Qualquer exceção em `manutencao()` mata o agente/serviço | `servico/pipe.py` |
| BUG-11 | ALTA | CONFIRMADO-TESTE | Agente em segundo plano nunca encerra (modo portátil/fonte) | `servico/executar.py`, `main.py` |
| BUG-12 | ALTA | PROVÁVEL | Atalhos F1–F5 não funcionam com NumLock ligado | `views/main_view.py` |
| BUG-13 | ALTA | CONFIRMADO-LEITURA | `erros.log` não é gravado na versão instalada e não permite diagnóstico | `utils/erros.py`, `main.py` |
| BUG-14 | MÉDIA | CONFIRMADO-TESTE | Laboratório reabre `simulacao.db` antigo (dados desatualizados) | `servico/nucleo.py` |
| BUG-15 | MÉDIA | CONFIRMADO-TESTE | Estados do multicanal sem validação de transição | `servico/nucleo.py` |
| BUG-16 | MÉDIA | CONFIRMADO-LEITURA | Instrução errada após "Exportar cópia protegida" | `views/view_relatorios.py` |
| BUG-17 | MÉDIA | CONFIRMADO-LEITURA | Erros `ValueError`/`ErroSeguranca` do serviço tratados de forma errada nas telas | `views/*.py`, `utils/erros.py` |
| BUG-18 | MÉDIA | CONFIRMADO-LEITURA | Pedidos do laboratório selecionados por posição; refresh pode trocar o alvo | `views/view_integracoes.py` |
| BUG-19 | MÉDIA | CONFIRMADO-LEITURA | Operação de gestão abandonada bloqueia login por até 5 min | `servico/gestao.py`, `servico/nucleo.py` |
| BUG-20 | BAIXA | CONFIRMADO-TESTE | "Estoque parado há (dias)" com valor grande gera erro genérico | `controllers/controllers.py` |
| BUG-21 | BAIXA | CONFIRMADO-TESTE | Importação CSV: log "Ajuste 0" vazio; "1.000" rejeitado; marca/categoria sensível a caixa | `gestao/planilha.py` |
| BUG-22 | BAIXA | CONFIRMADO-TESTE | Busca Admin: prefixo com 8/12/13/14 dígitos dá "não encontrado" | `utils/busca.py` |
| BUG-23 | BAIXA | CONFIRMADO-TESTE | Busca de Relatórios trata `%` e `_` como curingas | `models/models.py` |
| BUG-24 | BAIXA | CONFIRMADO-LEITURA | Tela de primeiro acesso: Enter no campo "Nova frase de senha" não faz nada | `views/acesso.py` |
| BUG-25 | BAIXA | PROVÁVEL | Ctrl+L não bloqueia com Caps Lock ligado | `views/main_view.py` |
| BUG-26 | BAIXA | CONFIRMADO-LEITURA | Bloqueio por inatividade suspenso enquanto o seletor de arquivos está aberto | `views/gestao_dados.py` |
| BUG-27 | BAIXA | CONFIRMADO-LEITURA | Backups `.gsbackup` diários e de restauração acumulam sem limite | `servico/cofre.py` |
| BUG-28 | BAIXA | CONFIRMADO-LEITURA | Caminhos legados errados (exportações do legado e tema na importação portátil) | `servico/cofre.py`, `servico/importacao.py` |
| BUG-29 | BAIXA | CONFIRMADO-LEITURA | Limitador de login global e troca de senha sem limitador | `servico/nucleo.py` |

---

## 2. Bugs detalhados

### BUG-01 — Reinstalar/atualizar corrompe `operadores.json` e derruba o serviço
- **Severidade:** CRÍTICA · **Status:** CONFIRMADO-TESTE · **Categoria:** instalador / disponibilidade
- **Arquivos:** `instalador/servico.ps1:69-74`; consumidor `servico/pipe.py:41-47`
- **Descrição:** na 2ª execução do instalador (atualização, reparo ou reinstalação), o script lê o `operadores.json` existente com `ConvertFrom-Json` no Windows PowerShell 5.1. Nessa versão, `ConvertFrom-Json` devolve o array JSON como **um único objeto**; `@(...)` o aninha, e `ConvertTo-Json` grava o array interno como objeto `{"value": [...], "Count": n}`.
- **Reprodução (executada; só manipula um arquivo temporário):**
  ```powershell
  $f = "$env:TEMP\operadores.json"; Remove-Item $f -ErrorAction SilentlyContinue
  foreach ($sidOperador in 'S-1-5-21-1-2-3-1001','S-1-5-21-1-2-3-1002') {
    $operadores = @($sidOperador)
    if (Test-Path -LiteralPath $f) { $operadores += @(Get-Content -LiteralPath $f -Raw | ConvertFrom-Json) }
    ConvertTo-Json -InputObject @($operadores | Select-Object -Unique) | Set-Content -LiteralPath $f -Encoding UTF8
  }
  Get-Content $f -Raw
  ```
  Saída obtida após a 2ª execução:
  ```json
  [ "S-1-5-21-1-2-3-1002", { "value": [ "S-1-5-21-1-2-3-1001" ], "Count": 1 } ]
  ```
  Em Python, `win32security.ConvertStringSidToSid({...})` → `TypeError: Objects of type 'dict' can not be converted to Unicode.`
- **Impacto:** `pipe.atributos()` lança `TypeError` → `servir()` não cria o pipe → o serviço para → o health check do instalador falha → o rollback do instalador restaura o `binPath`, **mas não restaura o `operadores.json`**, então a versão anterior também não sobe. A instalação fica inoperante até edição manual do arquivo em `C:\ProgramData\GiStocker`.
- **Causa raiz:** semântica do `ConvertFrom-Json` no PowerShell 5.1 (o instalador chama explicitamente `{sys}\WindowsPowerShell\v1.0\powershell.exe`).
- **Direção de correção:**
  - No `servico.ps1`, enumerar explicitamente: `$existentes = Get-Content ... -Raw | ConvertFrom-Json; foreach ($s in $existentes) { $operadores += [string]$s }` e validar que cada item é uma string SID (`[Security.Principal.SecurityIdentifier]::new($s)`).
  - Gravar com `ConvertTo-Json -InputObject ([string[]]$lista)` e validar o arquivo resultante antes de iniciar o serviço; fazer backup do arquivo antes e restaurá-lo no `catch`.
  - No `pipe.atributos()`, rejeitar com mensagem clara qualquer item que não seja `str` (e, opcionalmente, achatar listas legadas).
- **Critério de aceite:** executar a lógica do script 3 vezes com SIDs diferentes/repetidos produz um array plano de strings únicas; `pipe.atributos(producao=True, raiz=...)` aceita o arquivo; um arquivo já corrompido (com `{"value":...}`) é recuperado ou rejeitado com mensagem explícita.

---

### BUG-02 — Movimentação idêntica posterior é "engolida" por identificador pendente antigo
- **Severidade:** CRÍTICA · **Status:** CONFIRMADO-TESTE · **Categoria:** integridade de dados (estoque)
- **Arquivos:** `servico/cliente.py:41-58` e `60-79`; `servico/pendencias.py:19-40`; `servico/nucleo.py:182-194` (`_idempotente`)
- **Descrição:** cada mutação recebe um UUID guardado no journal `comandos_pendentes.json`, indexado **somente pela assinatura** `[comando, args, kwargs]`. Se a resposta se perder depois de o serviço ter confirmado (timeout de 120 s, queda do pipe, UI fechada/travada), a entrada fica no journal **sem prazo**. Qualquer operação futura com a mesma assinatura (ex.: `registrar_saida(produto 5, "1")`, extremamente comum) reutiliza o UUID antigo; o serviço encontra o registro em `Comandos_IPC` e devolve o resultado antigo **sem executar a nova operação**. A UI mostra "Saída registrada" com números antigos.
- **Reprodução (executada; ver Apêndice A, cenário B):**
  1. Cadastrar produto com estoque 10.
  2. Fazer `registrar_saida(p, '1')` onde o servidor confirma, mas a resposta é perdida (simulado com `servico.cliente.chamar` executando a chamada real e lançando `TimeoutError` em seguida).
  3. Depois, fazer outra `registrar_saida(p, '1')` legítima.
  - **Obtido:** estoque após a 2ª venda = **9** (a UI informou sucesso com estoque 9). **Esperado:** 8.
  - O journal continha: `{"5b83...798d":"72721edb-..."}`.
- **Causa raiz:** a deduplicação foi pensada para "repetir imediatamente a mesma operação", mas a chave não expira, não está ligada à sessão nem à intenção do usuário e não é limpa quando a resposta chega por outra via.
- **Direção de correção (escolher uma, documentar):**
  - Guardar no journal também `criado_em` e a sessão; considerar a entrada válida só para uma **repetição explícita** (ex.: botão "Repetir operação pendente" ou retentativa automática imediata) e expirar em poucos minutos.
  - Ao iniciar uma nova sessão (login), consultar no serviço o status de cada id pendente (`Comandos_IPC`): se já executado, mostrar o resultado ao usuário e remover do journal; nunca reaproveitar em silêncio para uma nova ação.
  - Alternativamente, gerar sempre um UUID novo por ação do usuário e só reaproveitar no laço de retentativa da mesma ação.
- **Critério de aceite:** o cenário acima termina com estoque 8; uma retentativa imediata da mesma ação, após falha de resposta, continua não duplicando a baixa.
- **Mesmo padrão em:** `servico/transferencia.py:39-41` (journal `gestao_pendentes.json` com chave `tipo:tamanho:sha256`): reimportar intencionalmente o mesmo CSV depois de uma falha pós-commit devolve o recibo antigo e **não soma as quantidades de novo**.

---

### BUG-03 — Cada gravação custa O(produtos × eventos)
- **Severidade:** CRÍTICA · **Status:** CONFIRMADO-TESTE · **Categoria:** desempenho / escalabilidade
- **Arquivos:** `multicanal/motor.py:118-126` (`preparar`), `145-164` (`fisico`); `multicanal/esquema.py:18-21` (tabela `Eventos_Estoque` sem índice em `produto_id`/`log_id`)
- **Descrição:** toda escrita física (entrada, saída, ajuste, cadastro, vincular código, desfazer) passa por `Motor.fisico`, que:
  1. lista todos os produtos duas vezes;
  2. executa um `SELECT ... FROM Logs_Movimentacao WHERE id>? AND produto_id=?` por produto;
  3. chama `self.preparar()`, que para **cada produto** faz `SELECT id FROM Eventos_Estoque WHERE produto_id=?` (varredura completa, não há índice) e 3 `INSERT OR IGNORE`.
- **Medições (via `Nucleo.executar`, sem pipe):**
  | Produtos | Eventos | `registrar_saida` |
  |---|---|---|
  | 3.000 | 25.000 | **0,86 s** |
  | 6.000 | 50.000 | **2,50 s** |
  Crescimento ~quadrático. Toda chamada IPC é síncrona na thread da interface, então a tela congela durante cada leitura do leitor de código de barras (modo rápido incluído).
- **Direção de correção:**
  - Em `fisico`, considerar apenas os produtos afetados pelo método (o `produto_id` do argumento, ou o produto do log desfeito); para `cadastrar_produto`, o novo id.
  - `preparar(produto_id=None)` deve preparar só o produto alterado; manter a preparação completa apenas no login/migração.
  - Criar índices `Eventos_Estoque(produto_id)` e `Eventos_Estoque(log_id)`. **Obrigatório:** incluir os novos índices na lista branca (`models/seguranca.validar_esquema_legado` e/ou `multicanal/esquema.conferir_objeto`), com migração de `user_version` e atualização de `gestao/backup.py`, se necessário. Sem isso, bancos com o índice serão recusados na abertura.
- **Critério de aceite:** com 6.000 produtos e 50.000 eventos, `registrar_saida` < 50 ms; a suíte existente continua passando; banco antigo (sem índice) abre e é migrado.

---

### BUG-04 — Histórico completo quebra com ~20 mil movimentações e bloqueia a sessão
- **Severidade:** CRÍTICA · **Status:** CONFIRMADO-TESTE · **Categoria:** escalabilidade / disponibilidade
- **Arquivos:** `views/view_relatorios.py:403-404` (sempre `listar_logs()` sem limite); `servico/nucleo.py:174-179` (consulta N+1 em `Eventos_Estoque` sem índice); `servico/protocolo.py:45-49` (limite de 8 MB); `servico/pipe.py:129-147` (exceção de serialização engolida, nenhuma resposta enviada); `servico/cliente.py:63-71` (qualquer falha → `ao_indisponivel()` → bloqueio da UI)
- **Descrição:** ao abrir **Relatórios**, a tela pede o histórico inteiro. O serviço faz 1 consulta sem índice por log (N+1) e serializa tudo. Cada log ocupa ~421 bytes de JSON, então com **~19.900 logs** a resposta passa de 8 MB; `serializar()` lança `ValueError`, o `servir()` engole a exceção (`except ...: pass`) e desconecta sem responder. O cliente interpreta como "serviço não respondeu" e **bloqueia a sessão**.
- **Medições:**
  | Logs | `listar_logs()` no Nucleo | Via pipe real |
  |---|---|---|
  | 25.003 | 10,35 s | falha após 10,3 s: `ErroSeguranca: O serviço local não respondeu...` + `ao_indisponivel` chamado |
  | 50.003 | 40,50 s | falha após 41,0 s, idem |
  O mesmo limite atinge `listar_produtos()` / `pesquisar_produtos('')` com ~31.700 produtos (~264 bytes/produto), usados no Admin.
- **Direção de correção:**
  - Paginar o histórico (`limite`/`offset` ou cursor por `id`) e carregar sob demanda na Treeview.
  - Trocar o N+1 por um único `LEFT JOIN` com índice em `Eventos_Estoque(log_id)` (mesma ressalva de lista branca do BUG-03).
  - Em `servir()`, quando a serialização falhar, **responder** `{'ok': False, 'erro': 'ValueError', 'mensagem': 'Resposta extensa demais...'}` em vez de desconectar em silêncio.
  - No cliente, não bloquear a sessão por erro de transporte em **leituras**; bloquear só quando o serviço indicar sessão inválida.
- **Critério de aceite:** com 50.000 logs, abrir Relatórios leva < 1 s para a primeira página e a sessão não é bloqueada; resposta acima do limite gera mensagem clara.

---

### BUG-05 — Valores monetários com separador de milhar pt-BR são gravados 1000× menores
- **Severidade:** CRÍTICA · **Status:** CONFIRMADO-TESTE · **Categoria:** integridade de dados financeiros
- **Arquivos:** `utils/texto.py:265-279` (`converter_para_float`); usado por `controllers/controllers.py:115-126` (`_validar_valor_monetario`) e `gestao/planilha.py:59-60`
- **Descrição:** a regra só remove `.` de milhar quando também existe `,`. Saídas obtidas:
  | Entrada | Resultado | Esperado (pt-BR) |
  |---|---|---|
  | `1.500` | **1.5** | 1500 |
  | `1.234` | **1.234** | 1234 |
  | `1,234.56` | **1.23456** | 1234.56 ou erro |
  | `2.000.000` | erro | 2000000 |
  | `1.500,00` | 1500.0 | OK |
- **Impacto:** preço/custo digitado como "1.500" (Cadastro, campo custo da Operação, Admin) ou importado por CSV vira R$ 1,50, sem aviso. Na importação testada, `preco_venda_base=1.500` e `custo_unitario=1.200` foram gravados como **1.5** e **1.2**. O custo médio ponderado, os KPIs e as receitas ficam incorretos.
- **Direção de correção:** definir formato pt-BR explícito. Ex.: se o texto casa com `^\d{1,3}(\.\d{3})+(,\d+)?$`, tratar `.` como milhar; se tem um único `.` seguido de exatamente 3 dígitos e nenhuma `,`, **rejeitar como ambíguo** (pedir "1500" ou "1.500,00"); aceitar `.` decimal só com 1, 2 ou 4 casas. Rejeitar `1_000`, `1e3`, `inf`, `nan`. Alinhar a mesma regra na importação CSV e documentar no modelo.
- **Critério de aceite:** a tabela acima produz 1500, 1234, erro/1234.56, 2000000 e 1500; testes de regressão para `12,50`, `0,99`, `10.5`, `R$ 1.234,56`.

---

### BUG-06 — Simulação ativa trava o agente
- **Severidade:** ALTA · **Status:** CONFIRMADO-TESTE · **Categoria:** desempenho / disponibilidade (laboratório de integrações)
- **Arquivos:** `servico/nucleo.py:57-71` (`manutencao` chama o worker a cada ~1 s); `multicanal/sincronizacao.py:419-466` (`Worker.passo`); `multicanal/motor.py:199-244` (`planejar` → `alocar` → `preparar` para cada produto)
- **Descrição:** com o estado `MULTICANAL_ATIVO`, cada ciclo chama `planejar()` para cada produto; cada `planejar` chama `alocar`, que chama `preparar()` sobre **todos** os produtos (O(P²·E)), e cada publicação abre transações com `synchronous=FULL`. O servidor do pipe é de thread única, então nenhuma requisição da UI é atendida durante o ciclo; o `WaitNamedPipe(5000)` do cliente expira e a sessão é bloqueada.
- **Medições (`Nucleo.manutencao()` com catálogo fictício e ensaio iniciado):**
  | Produtos | Tempo por ciclo |
  |---|---|
  | 200 | **~6,0 s** |
  | 800 | **~105 s** |
- **Direção de correção:** remover `self.preparar()` de `alocar`/`planejar` (preparar uma vez por ciclo ou só o produto); agrupar o ciclo numa única transação; limitar o trabalho por chamada de `manutencao` (orçamento de tempo) ou rodar o worker numa thread com conexão própria; não chamar o worker enquanto houver requisição pendente.
- **Critério de aceite:** com 800 produtos, cada chamada de `manutencao()` < 200 ms e a UI continua respondendo durante o ensaio.

---

### BUG-07 — Senha atual errada em "Alterar senha" encerra a sessão
- **Severidade:** ALTA · **Status:** CONFIRMADO-TESTE · **Categoria:** UX / fluxo de segurança
- **Arquivos:** `servico/cofre.py:159-168` (`desembrulhar` lança `ErroSeguranca`); `servico/cliente.py:75-76`; `views/view_configuracoes.py:423-434`; `views/main_view.py:85-87`
- **Descrição:** a senha atual errada gera `ErroSeguranca('Senha incorreta ou envelope danificado.')`. O cliente trata **qualquer** `ErroSeguranca` com sessão aberta como serviço indisponível e chama `ao_indisponivel()` → `bloquear()`. A tela mostra antes "Não foi possível salvar a senha. Confira o espaço livre e as permissões da pasta dados." (mensagem errada) e em seguida volta para a tela de acesso.
- **Reprodução (executada via pipe real):** `cliente.alterar_senha('errada#123', 'novaSenha#2026', 'novaSenha#2026')` → `ErroSeguranca` e callback `ao_indisponivel` chamado.
- **Direção de correção:** em `CofreServico.alterar_senha`, converter a falha de `desembrulhar` em `ValueError('A senha atual está incorreta.')` (a tela já exibe `ValueError` corretamente). No cliente, só chamar `ao_indisponivel()` para o erro específico de sessão bloqueada (ex.: um código de erro dedicado), não para qualquer `ErroSeguranca`. Considerar limitar tentativas (ver BUG-29).
- **Critério de aceite:** senha atual errada mostra "A senha atual está incorreta." e a sessão permanece aberta.

---

### BUG-08 — Falha ao criar o backup diário impede o login com a senha correta
- **Severidade:** ALTA · **Status:** CONFIRMADO-TESTE · **Categoria:** disponibilidade / mensagem enganosa
- **Arquivos:** `servico/cofre.py:93-107` (`_abrir_chave` cria o `.gsbackup` diário dentro do `try`, e qualquer falha fecha o banco); `servico/nucleo.py:113-118` (qualquer exceção vira "Senha incorreta" e incrementa o atraso)
- **Reprodução (executada):** após o primeiro login, substituir a pasta `<raiz>/backups` por um arquivo (simula disco cheio, permissão negada ou antivírus) → login com a senha **correta** retorna `Senha incorreta ou dados indisponíveis. Nenhum acesso foi liberado.` e aplica atraso progressivo (2 s, 4 s, ... até 300 s).
- **Impacto:** com o disco cheio, a loja não consegue abrir o sistema e é levada a pensar que errou a senha.
- **Direção de correção:** o backup diário deve ser *best-effort*: capturar a exceção, registrar no log, liberar a sessão e avisar na UI ("Backup diário não pôde ser criado: espaço/permissões"). Em `Nucleo` login, só incrementar `tentativas` quando a falha for de autenticação (`desembrulhar`), e devolver mensagens distintas para falha de senha e de I/O.
- **Critério de aceite:** com `backups` indisponível, o login com a senha correta funciona e exibe um aviso; a senha errada continua com atraso.

---

### BUG-09 — Primeiro acesso: erros de validação aparecem como "Senha incorreta", com atraso e pastas órfãs
- **Severidade:** ALTA · **Status:** CONFIRMADO-TESTE · **Categoria:** UX / onboarding / lixo em disco
- **Arquivos:** `servico/cofre.py:116-150` (`_migrar` cria `.cofre_<uuid>` antes de validar e não remove em falha); `servico/nucleo.py:113-118`; `views/acesso.py:438-447` (a tela não valida localmente)
- **Reprodução (executada, instalação nova):**
  - `login('', 'abc', 'abc')` → `ErroSeguranca: Senha incorreta ou dados indisponíveis...` (esperado: "Use uma senha com 6 a 128 caracteres").
  - `login('', 'senhaForte#2026', 'senhaDiferente#2026')` → mesma mensagem (esperado: "A confirmação não corresponde...").
  - Atraso aplicado: 4 s após 2 tentativas (cresce até 300 s).
  - Restam pastas `.cofre_9ec1...` e `.cofre_cffc...` na raiz de dados (no modo legado/protegido, cada uma pode conter uma cópia inteira do banco).
- **Direção de correção:** validar `validar_nova_senha()` **antes** de criar o diretório de staging; remover o staging no `finally` em caso de falha (ele já é criptografado, mas acumula). No `Nucleo`, deixar `ValueError` de validação passar com a mensagem original e **sem** incrementar o atraso. Opcional: validar também na `TelaAcesso` antes de enviar.
- **Critério de aceite:** as duas tentativas acima mostram a mensagem específica, sem atraso e sem pastas `.cofre_*` remanescentes.

---

### BUG-10 — Qualquer exceção em `manutencao()` derruba o agente/serviço
- **Severidade:** ALTA · **Status:** CONFIRMADO-TESTE (com injeção de falha) · **Categoria:** robustez
- **Arquivos:** `servico/pipe.py:113-117` (`nucleo.manutencao()` fora do `try`); `servico/nucleo.py:57-71`
- **Descrição:** `manutencao()` executa o worker de simulação, fecha jobs de gestão e lê o envelope. Um erro transitório (I/O, SQLite "disk full", `KeyError`/`TypeError` no worker) sai do laço `while`, executa o `finally` (fecha pipe e banco) e encerra o agente. No modo portátil, a UI só reinicia o agente na próxima abertura; no serviço, depende das ações de recuperação do SCM.
- **Reprodução (executada):** monkeypatch de `Nucleo.manutencao` lançando `OSError` na 3ª chamada → thread do agente termina (`agente vivo? False ['OSError']`).
- **Direção de correção:** envolver `nucleo.manutencao()` em `try/except Exception`, registrar com `registrar_falha` (sem payload) e continuar o laço, com backoff para não entrar em loop quente de erro.
- **Critério de aceite:** com a injeção acima, o agente continua atendendo `status` e o erro aparece no log.

---

### BUG-11 — Agente em segundo plano nunca encerra (modo portátil/fonte)
- **Severidade:** ALTA · **Status:** CONFIRMADO-TESTE · **Categoria:** ciclo de vida / atualização
- **Arquivos:** `servico/executar.py:14-48` (`executar()` roda até `parar`, que nunca é sinalizado no modo `--agente`); `main.py:296-309` (fechar a janela só faz `logout`)
- **Evidência:** nesta máquina, com **nenhuma interface aberta**, há um processo `python.exe main.py --agente` vivo desde 17/10/2026 16:13 (PIDs 32856/21384).
- **Impacto:**
  1. **Atualização portátil:** o README manda "feche todas as instâncias e copie `GestorEstoque.exe` e `_internal`", mas o agente é invisível e mantém o `.exe` em uso, então a cópia falha.
  2. **Código antigo em execução:** ao atualizar o fonte, o agente continua com o código anterior até reiniciar o Windows; recursos novos (ex.: `dados.*`) respondem "Comando não permitido". Não há verificação de versão entre UI e agente (`VERSAO = 1` fixo).
  3. **Instalador:** `importar_portatil` exige `.agente.lock` livre, então a importação é recusada ("Feche a versão antiga") e o usuário não tem como fechar o agente.
  4. Consumo contínuo de CPU: laço de polling de 20 ms + `manutencao()` a cada segundo.
- **Direção de correção:** encerrar o agente portátil quando não houver sessões nem simulação ativa por N minutos (ou quando a última UI sair, via comando `encerrar`); incluir a versão do app no `status` e reiniciar o agente se divergir; instruir/oferecer "Encerrar serviço local" na UI.
- **Critério de aceite:** após fechar a UI (sem simulação ativa), o processo `--agente` termina em até N minutos; abrir uma UI de versão diferente substitui o agente.

---

### BUG-12 — Atalhos F1–F5 não funcionam com NumLock ligado
- **Severidade:** ALTA (afeta a operação diária com teclado numérico) · **Status:** PROVÁVEL (confirmar manualmente) · **Categoria:** UI / teclado
- **Arquivo:** `views/main_view.py:135-136`
  ```python
  self.bind(f"<{atalho}>", lambda e, c=chave: self.mostrar_view(c) if not e.state & 0x2000 and not e.state & 0x8 else None)
  ```
- **Descrição:** no Tk para Windows, o bit `0x0008` (Mod1) de `event.state` indica **NumLock ligado**, e Alt é `0x20000`. O filtro (que parece ter sido escrito para X11, onde Mod1 é Alt) descarta o atalho sempre que o NumLock está ligado, o que é comum em teclados com teclado numérico. Já `0x2000` não corresponde a Alt no Windows, então Alt+F4 (fechar) também dispara a navegação para Relatórios.
- **Como confirmar:** ligar o NumLock, abrir o app e pressionar F2: a tela não muda. Ou adicionar temporariamente `print(hex(e.state))` no handler.
- **Direção de correção:** no Windows, ignorar apenas `0x20000` (Alt) e `0x4` (Ctrl), se desejado; nunca filtrar `0x8`/`0x2`/`0x20` (NumLock, CapsLock, ScrollLock). Fazer a máscara depender de `sys.platform`.
- **Critério de aceite:** F1–F5 navegam com NumLock/CapsLock ligados; Alt+F4 não navega.

---

### BUG-13 — `erros.log` não é gravado na versão instalada e não permite diagnóstico
- **Severidade:** ALTA · **Status:** CONFIRMADO-LEITURA (+ evidência no log real) · **Categoria:** observabilidade
- **Arquivos:** `utils/erros.py:117-127` (sempre `config.DIRETORIO_BASE / 'erros.log'`); `main.py:316`; `views/gestao_dados.py:237-241`; `servico/gestao.py:139-140`
- **Descrição:**
  1. Instalado, `DIRETORIO_BASE` é `C:\Program Files\GiStocker\versoes\<release>`, sem permissão de escrita para o operador. `main._registrar_falha` usa `ProgramData\GiStocker`, cuja ACL só libera SYSTEM, Administradores e o serviço. Os erros da UI são **descartados em silêncio** (`except OSError: pass`), embora a UI diga "Detalhes em erros.log".
  2. Erros **esperados** (senha errada, validação) são registrados como falhas, mas sem a mensagem, então o log não diferencia uma senha errada de um bug real. Evidência: o `erros.log` real tem 6 `ValueError` em 17/10/2026 16:15–16:21 em `transferencia.py:30 pedir ← :41 executar` (falha no `dados.iniciar` da gestão de dados) e não é possível saber a causa.
- **Direção de correção:** gravar o log da UI em `%LOCALAPPDATA%\GiStocker\erros.log` (instalado) e o do serviço em `ProgramData\GiStocker\logs`; não registrar `ValueError`/`ErroNegocio` esperados como falha (ou registrar com um "código de motivo" sem dados sensíveis, ex.: `SENHA_INCORRETA`, `LAB_ATIVO`, `JOB_EM_ANDAMENTO`).
- **Critério de aceite:** na versão instalada, uma exceção na UI gera linha em `%LOCALAPPDATA%\GiStocker\erros.log`; uma senha errada na gestão de dados não gera entrada de falha.

---

### BUG-14 — Laboratório reabre `simulacao.db` antigo
- **Severidade:** MÉDIA · **Status:** CONFIRMADO-TESTE · **Categoria:** lógica
- **Arquivos:** `servico/nucleo.py:48-55` (`_abrir_simulacao` só copia se o arquivo **não** existir); `servico/nucleo.py:268-277` (`_concluir_encerramento` fecha, mas não remove o arquivo)
- **Reprodução (executada):** ativar e encerrar a simulação → cadastrar "Produto novo pós-lab" → ativar de novo: real = 4 produtos, simulação = 3, produto novo **ausente**. Na pasta real `dados/cofre_v2/` já existe um `simulacao.db`.
- **Direção de correção:** ao ativar a partir do estado `FISICO`, recriar a cópia (remover a antiga com segurança, mantendo-a só enquanto o estado não for `FISICO`); ou, ao encerrar com sucesso, apagar `simulacao.db`.
- **Critério de aceite:** a reativação reflete o estoque real atual.

---

### BUG-15 — Estados do multicanal sem validação de transição
- **Severidade:** MÉDIA · **Status:** CONFIRMADO-TESTE · **Categoria:** máquina de estados
- **Arquivo:** `servico/nucleo.py:202-226`
- **Descrição:** `ativar_simulacao`, `iniciar_ensaio`, `pausar` e `encerrar` fazem `UPDATE` direto, sem checar o estado atual. Observado: `MULTICANAL_ATIVO` → "Preparar simulação" → `MULTICANAL_CONFIGURANDO`. Pelo código, "Iniciar/retomar" durante `ENCERRANDO_MULTICANAL` volta para `ATIVO` e cancela um encerramento em andamento, e "Pausar" também.
- **Direção de correção:** tabela explícita de transições permitidas e `ErroNegocio` para as demais (ex.: `ENCERRANDO` só sai para `FISICO`).
- **Critério de aceite:** transições inválidas retornam erro e o estado não muda.

---

### BUG-16 — Instrução errada após "Exportar cópia protegida" (Relatórios)
- **Severidade:** MÉDIA · **Status:** CONFIRMADO-LEITURA · **Categoria:** UX / recuperação de desastre
- **Arquivos:** `views/view_relatorios.py:428-432`; `servico/cofre.py:203-222` (gera `.gsbackup`)
- **Descrição:** o diálogo diz "Esta cópia exige a senha atual... Para restaurar, feche o software e use-a como dados/estoque.db". Na v2, o arquivo é um **ZIP `.gsbackup`** (`estoque.db` + `acesso.json`); o banco usa uma **chave aleatória** envelopada, não a senha, e o banco ativo fica em `dados/cofre_v2/`. Seguir a instrução não restaura nada. A restauração real é `servico.cofre.restaurar()`, uma ferramenta técnica sem interface (`GUIA_MULTICANAL.md:119`).
- **Direção de correção:** corrigir o texto (citar `.gsbackup` e o procedimento documentado) ou oferecer na UI a restauração de `.gsbackup` usando `servico.cofre.restaurar` em uma pasta nova.
- **Critério de aceite:** o texto do diálogo descreve um procedimento que funciona.

---

### BUG-17 — Erros do serviço tratados de forma errada nas telas
- **Severidade:** MÉDIA · **Status:** CONFIRMADO-LEITURA · **Categoria:** tratamento de erros / UX
- **Arquivos:** `views/view_operacao.py:251`, `283`; `views/view_cadastro.py:178`, `210`; `views/view_admin.py:190`, `236`, `297`, `318`, `333`; `utils/erros.py:130-135`; `servico/cliente.py:77`
- **Descrição:**
  1. O cliente converte respostas `ValueError`/`TypeError` do serviço em `ValueError` (ex.: "Gestão de dados em andamento", "Parâmetros incompatíveis"), mas as telas só capturam `ErroNegocio, ErroSeguranca, ERROS_BANCO, OSError`. O `ValueError` cai no `report_callback_exception` com a mensagem genérica "Ocorreu uma falha... Detalhes em erros.log".
  2. `mensagem_falha()` transforma **todo** `ErroSeguranca` em "Não foi possível acessar ou gravar os dados. Verifique o espaço em disco...", inclusive "Sessão bloqueada" e "O serviço local não respondeu", o que leva o usuário a um diagnóstico errado.
  3. Erros internos do serviço (`'Operacional'`) viram `ErroSeguranca` no cliente.
- **Direção de correção:** criar códigos de erro estáveis no protocolo (`SESSAO`, `SERVICO_INDISPONIVEL`, `VALIDACAO`, `NEGOCIO`, `INTERNO`); mapear cada código para mensagem própria nas telas; capturar `ValueError` nas mesmas cláusulas de `ErroNegocio`.
- **Critério de aceite:** com a sessão expirada, a Operação mostra "Sessão expirada, desbloqueie novamente", e não "espaço em disco".

---

### BUG-18 — Pedidos do laboratório selecionados por posição
- **Severidade:** MÉDIA · **Status:** CONFIRMADO-LEITURA · **Categoria:** UI / laboratório
- **Arquivos:** `views/view_integracoes.py:120-125` (`iid = str(índice)`), `168-180`; `multicanal/motor.py:374` (`SELECT * FROM Itens_Pedido_Externo` sem `ORDER BY`)
- **Descrição:** a tabela de pedidos usa o índice da lista como `iid` e é recarregada a cada 5 s. A seleção é restaurada por índice, então se a ordem ou a quantidade de linhas mudar, "Aplicar ao pedido" pode agir sobre **outro pedido** (enviar, cancelar, aprovar devolução).
- **Direção de correção:** usar `p['id']` como `iid` (escapando caracteres, se necessário) e `ORDER BY` estável no painel.
- **Critério de aceite:** após um refresh com novo pedido inserido, a seleção continua no mesmo `id`.

---

### BUG-19 — Operação de gestão abandonada bloqueia login por até 5 minutos
- **Severidade:** MÉDIA · **Status:** CONFIRMADO-LEITURA · **Categoria:** disponibilidade
- **Arquivos:** `servico/gestao.py:33-35` (expira após 300 s sem uso); `servico/nucleo.py:106-108` (login recusado com job ativo), `58-60` (sessões não expiram enquanto há job)
- **Descrição:** se a UI morrer durante exportação/importação/restauração (processo encerrado, queda de energia da UI), o job fica ativo; `login` responde "Gestão de dados em andamento. Aguarde a conclusão." por até 5 min, e a tela de acesso não explica o motivo nem o tempo.
- **Direção de correção:** ao receber `login` da mesma identidade Windows com job órfão (dono sem sessão viva), cancelar o job (rollback) e liberar; ou informar o tempo restante.
- **Critério de aceite:** após encerrar a UI no meio de uma importação, um novo login é aceito imediatamente e o lote não é confirmado.

---

### BUG-20 — "Estoque parado há (dias)" com valor grande gera erro genérico
- **Severidade:** BAIXA · **Status:** CONFIRMADO-TESTE · **Categoria:** validação de entrada
- **Arquivos:** `views/view_dashboard.py:121`; `controllers/controllers.py:488-491`
- **Reprodução:** `relatorios.estoque_parado(10**12)` → `OverflowError` em `timedelta` → resposta `Operacional` → "Operação não concluída. Confira o serviço..." e o Dashboard fica parcialmente atualizado.
- **Direção de correção:** limitar `dias` a 1–3650 na tela e no controlador.

---

### BUG-21 — Importação CSV: inconsistências
- **Severidade:** BAIXA · **Status:** CONFIRMADO-TESTE · **Arquivo:** `gestao/planilha.py:55`, `57`, `90-98`
- **Itens:**
  1. Linha de produto existente com quantidade `0` e preço/custo vazios grava um log **"Ajuste" de 0 unidades** sem mudança. Ele vira o alvo do botão "Desfazer" e polui o histórico (observado: `log 5 Ajuste 0 Importação CSV ...`).
  2. Quantidade `1.000` é rejeitada no CSV ("sem separador de milhar"), mas aceita como 1000 nas telas (`converter_para_int`).
  3. Marca e categoria exigem grafia exata (`natura` ≠ `Natura`; `O Boticario` sem acento é rejeitado).
- **Direção de correção:** não gerar log quando nada muda; usar a mesma regra de conversão das telas (após corrigir o BUG-05); comparar marca/categoria com `normalizar_texto` e gravar o nome canônico.

---

### BUG-22 — Busca Admin: prefixo com 8/12/13/14 dígitos dá "não encontrado"
- **Severidade:** BAIXA · **Status:** CONFIRMADO-TESTE · **Arquivo:** `utils/busca.py:83-84`
- **Reprodução:** produto com código `7891033000017`; buscar `789103300001` (12 dígitos, prefixo) → `[]` com "Código de barras não encontrado". Já `789103` encontra. O README diz que prefixos com 3 ou mais dígitos localizam códigos parciais.
- **Direção de correção:** antes de devolver "não encontrado", tentar a busca por trecho numérico; ou mostrar o aviso só quando o comprimento coincide com um GTIN válido (dígito verificador OK).

---

### BUG-23 — Busca de Relatórios trata `%` e `_` como curingas
- **Severidade:** BAIXA · **Status:** CONFIRMADO-TESTE · **Arquivo:** `models/models.py:407-433` (`RepositorioProdutos.buscar`)
- **Reprodução:** `buscar_produtos('%')` retorna todos os produtos; `buscar_produtos('a_u')` casa "maquiagem" (a?u).
- **Direção de correção:** escapar `\`, `%` e `_` e usar `LIKE ? ESCAPE '\'`.

---

### BUG-24 — Tela de primeiro acesso: Enter no campo "Nova frase de senha" não faz nada
- **Severidade:** BAIXA · **Status:** CONFIRMADO-LEITURA · **Arquivo:** `views/acesso.py:410-421`
- **Descrição:** no modo `novo`, o campo "Senha atual" está oculto (é o único com `<Return>` e `<KP_Enter>`); "Nova frase de senha" não tem atalho e a "Confirmação" não tem `<KP_Enter>`.
- **Direção de correção:** ligar `<Return>`/`<KP_Enter>` em todos os campos visíveis (no primeiro campo, Enter pode avançar o foco).

---

### BUG-25 — Ctrl+L não bloqueia com Caps Lock ligado
- **Severidade:** BAIXA · **Status:** PROVÁVEL · **Arquivo:** `views/main_view.py:74`
- **Descrição:** só `<Control-l>` está ligado; com Caps Lock, o Tk entrega o keysym `L`.
- **Direção de correção:** ligar também `<Control-L>`.

---

### BUG-26 — Bloqueio por inatividade suspenso com o seletor de arquivos aberto
- **Severidade:** BAIXA · **Status:** CONFIRMADO-LEITURA · **Arquivos:** `views/gestao_dados.py:134-142`; `views/main_view.py:252-266`
- **Descrição:** `_selecionar` marca `_gestao_em_andamento = True` enquanto o diálogo nativo está aberto; `bloquear()` retorna cedo com essa flag. Se o usuário sair com o seletor aberto, a tela nunca bloqueia, e os dados continuam visíveis atrás do diálogo.
- **Direção de correção:** usar uma flag separada para "seletor aberto"; ao estourar a inatividade, bloquear assim que o seletor fechar e descartar o caminho escolhido.

---

### BUG-27 — Backups `.gsbackup` acumulam sem limite
- **Severidade:** BAIXA · **Status:** CONFIRMADO-LEITURA (limitação também citada em `README.md:191`) · **Arquivo:** `servico/cofre.py:100-104`, `gestao/backup.py:129`
- **Descrição:** um `.gsbackup` completo por dia de uso, mais um por restauração, sem rotação. Em bancos grandes, o disco enche, e isso dispara o BUG-08.
- **Direção de correção:** política de retenção (ex.: últimos 30 diários + 12 mensais), configurável, sem apagar o snapshot mais recente de restauração.

---

### BUG-28 — Caminhos legados incorretos
- **Severidade:** BAIXA · **Status:** CONFIRMADO-LEITURA
- **Itens:**
  1. `servico/cofre.py:75`: `Cofre(..., self.raiz.parent/'exportacoes')`. Instalado, `raiz` é `C:\ProgramData\GiStocker` e as exportações legadas apontam para `C:\ProgramData\exportacoes` (fora da pasta do app).
  2. `servico/importacao.py:33`: a importação portátil v1 copia `tema.json`, mas a v1 grava o tema em `aparencia.json` (`models/seguranca.py:270`), então o tema é perdido.
- **Direção de correção:** usar `self.raiz/'exportacoes'` (ou o caminho portátil correto) e copiar `aparencia.json`.

---

### BUG-29 — Limitador de login global; troca de senha sem limitador
- **Severidade:** BAIXA (segurança) · **Status:** CONFIRMADO-LEITURA · **Arquivo:** `servico/nucleo.py:109-118`, `151-154`
- **Descrição:** `login_depois`/`tentativas` são globais: qualquer conta autorizada no pipe atrasa o login de todas. Já o comando `senha` (que testa a senha atual) não tem limitador, o que permite tentativas ilimitadas a partir de uma sessão aberta.
- **Direção de correção:** limitador por identidade Windows; aplicar o mesmo limitador ao `senha` e ao `dados.iniciar` (este já tem um próprio).

---

## 3. Itens verificados sem defeito (para não reabrir)
- Ida e volta Exportação JSON → Restauração em cenário com produto sem estoque, desfazer e ajuste: **OK**.
- Detecção de delimitador `;`/`,` com `;` entre aspas no nome: **OK**.
- Diálogos modais destruídos pelo bloqueio por inatividade: as telas verificam `winfo_exists()` depois de `confirmar`/`informar`. **OK**.
- Suíte `auditoria/verificar*.py`: 257/257 **OK**.

---

## Apêndice A — Harness de reprodução (sem UI, sem tocar em `dados/`)

Execute a partir de uma cópia do projeto ou com `sys.path` apontando para ele. Cada cenário cria uma raiz descartável; o nome do pipe de desenvolvimento deriva do caminho da raiz, então não conflita com o agente real.

```python
import sys, os, uuid, time, threading
from pathlib import Path
PROJ = Path(r'CAMINHO\DA\COPIA\DO\PROJETO'); sys.path.insert(0, str(PROJ)); os.chdir(PROJ)
from servico.nucleo import Nucleo
from servico.protocolo import VERSAO
SENHA, ID = 'senhaForte#2026', 'S-1-5-21-TESTE'

def novo_nucleo():
    raiz = Path(os.environ['TEMP']) / ('gistocker_teste_' + uuid.uuid4().hex[:8]); raiz.mkdir()
    n = Nucleo(raiz)
    def req(cmd, *a, sessao=None, **kw):
        return n.executar(dict(v=VERSAO, id=str(uuid.uuid4()), sessao=sessao, comando=cmd, args=list(a), kwargs=kw), ID)
    return raiz, n, req

# BUG-09: primeiro acesso com senha curta
raiz, n, req = novo_nucleo()
print(req('login', '', 'abc', 'abc'))                     # mensagem "Senha incorreta..."
print([p.name for p in raiz.iterdir()])                   # pasta .cofre_* órfã
n.login_depois = 0
S = req('login', '', SENHA, SENHA)['resultado']

# BUG-07: troca com senha atual errada -> erro 'ErroSeguranca'
print(req('senha', 'errada#123', 'novaSenha#2026', 'novaSenha#2026', sessao=S))

# BUG-05: conversão monetária
from utils.texto import converter_para_float
print(converter_para_float('1.500'))                      # 1.5 (errado)

# BUG-14: simulação desatualizada
req('integracoes.ativar_simulacao', sessao=S); req('integracoes.encerrar', sessao=S)
req('estoque.cadastrar_produto', 'Novo', 'Avon', 'Maquiagem', '1', '1', '5', [], sessao=S)
r = req('integracoes.ativar_simulacao', sessao=S)['resultado']
print(len(r['local']), len(r['simulacao']['produtos']))   # 1 vs 0
req('integracoes.encerrar', sessao=S); n.fechar()

# BUG-02: id pendente reaproveitado (pipe real em thread)
raiz = Path(os.environ['TEMP']) / ('gistocker_pipe_' + uuid.uuid4().hex[:8]); raiz.mkdir()
from servico.executar import executar
import servico.cliente as mc
parar = threading.Event(); th = threading.Thread(target=executar, args=(raiz, parar), daemon=True); th.start(); time.sleep(1.5)
c = mc.Cliente(raiz); c.abrir('', SENHA, SENHA); est, _ = c.criar_controladores()
p = est.cadastrar_produto('Batom', 'Avon', 'Maquiagem', '10', '5', '10', [])
orig = mc.chamar
def perde(nome, pedido, producao=False):
    orig(nome, pedido, producao); raise TimeoutError()
mc.chamar = perde
try: est.registrar_saida(p.id, '1')
except Exception: pass
mc.chamar = orig
est.registrar_saida(p.id, '1')
print(est.obter_produto(p.id).estoque_atual)              # 9 (esperado 8)
c.fechar(); parar.set(); th.join(10)
```

Para o BUG-03, BUG-04 e BUG-06, popular a raiz com inserts diretos em `Produtos`, `Logs_Movimentacao` e `Eventos_Estoque` dentro de `n.cofre.banco.transacao()`, chamar `n.motor.preparar()` e cronometrar `req('estoque.registrar_saida', ...)`, `req('estoque.listar_logs')` e, para o laboratório, `integracoes.ativar_simulacao` → `catalogo_exemplo` → `iniciar_ensaio` → `n.manutencao()`.
