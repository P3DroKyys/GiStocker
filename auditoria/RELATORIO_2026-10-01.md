# Auditoria do GiStocker — 01/10/2026

Status histórico: diagnóstico anterior às correções. Os 14 defeitos foram
corrigidos posteriormente na versão 1.0.1; veja [correções e validação](CORRECOES_2026-10-01.md).
Os resultados abaixo preservam as evidências de como o sistema estava na auditoria.

## Resultado

86 testes automatizados: **72 aprovados e 14 defeitos reproduzidos**. Não houve erros
inesperados nem testes ignorados. As 14 ocorrências estão marcadas como
`expectedFailure`: o texto `OK (expected failures=14)` do unittest NÃO significa que
esses comportamentos estejam corretos. São verificações do comportamento desejado
que falham no código atual, preservadas para acompanhar futuras correções.

Foram acrescentados 29 testes aos 57 existentes. Evidências completas, incluindo
tracebacks de cada defeito: [resultados.json](resultados_20261001/resultados.json).
Lista de todos os testes: [testes.txt](resultados_20261001/testes.txt).

Os testes usam bancos em memória ou diretórios temporários com dados fictícios.
Não abriram bancos de produção, não iniciaram o aplicativo de uso e não executaram
uma nova build. Só foram criados arquivos de auditoria. Os hashes dos fontes,
scripts BAT e recursos do aplicativo permaneceram iguais durante a execução final.

## Problemas para resolver depois

### A01 — Alta: gerar novamente a build pode apagar dados usados dentro de dist

- **Condição:** executar o programa em `dist/GestorEstoque` e guardar ali o banco;
  depois rodar novamente `3_gerar_exe.bat`.
- **Causa:** o BAT usa `--noconfirm`, e a etapa COLLECT do PyInstaller limpa a pasta
  de destino inteira. `config.py` coloca `dados` ao lado do executável; os backups
  automáticos ficam abaixo dessa mesma pasta.
- **Reprodução:** a rotina de limpeza da versão instalada do PyInstaller foi
  executada exclusivamente em um diretório temporário com um arquivo sentinela
  fictício em `dist/GestorEstoque/dados/estoque.db`. O sentinela foi removido.
- **Impacto:** perda do banco e dos backups que estiverem dentro do destino de
  geração. Não afeta automaticamente um banco instalado em outra pasta.
- **Local:** `3_gerar_exe.bat:28`, `config.py:23`; PyInstaller
  `building/api.py` COLLECT e `building/utils.py` `_make_clean_directory`.
- **Futura correção:** impedir reconstrução sobre dados de uso ou separar o destino
  da build da pasta permanente de dados. Validar atualização com dados existentes.
- **Teste:** `test_defeito_rebuild_apaga_dados_dentro_dist`.

### A02 — Média: duas exportações no mesmo minuto sobrescrevem arquivos

- **Reprodução:** exportar duas vezes na mesma pasta com o relógio fixado no mesmo
  minuto. Os dois caminhos retornados são idênticos, e `to_csv` grava por cima.
- **Impacto:** perde-se a exportação anterior sem confirmação, mesmo se houver
  movimentações entre as exportações. O banco não é apagado.
- **Local:** `controllers/controllers.py:473`.
- **Futura correção:** nomes únicos e criação sem sobrescrita.
- **Teste:** `test_defeito_exportacoes_no_mesmo_minuto`.

### A03 — Média: CSV de estoque e CSV de histórico podem retratar instantes diferentes

- **Reprodução:** intercalar uma saída entre as duas leituras usadas pela exportação.
  O CSV de estoque contém 10 unidades; o último log exportado já termina em 9.
- **Impacto:** arquivos de uma mesma exportação divergem se outra instância movimentar
  o banco nesse intervalo. Não indica corrupção do banco.
- **Local:** `controllers/controllers.py:477` — consultas sem snapshot conjunto.
- **Futura correção:** ler estoque e histórico em uma transação de leitura consistente.
- **Teste:** `test_defeito_csv_estoque_e_logs_sem_snapshot_unico`.

### A04 — Média: falha na segunda gravação deixa exportação incompleta

- **Reprodução:** simular erro de escrita no arquivo de logs depois que o CSV de
  estoque foi salvo. A exportação lança erro, mas deixa o primeiro arquivo no destino.
- **Impacto:** pode restar um par incompleto ou, havendo arquivos anteriores com o
  mesmo nome, uma mistura de versões. A tela comunica erro de exportação.
- **Local:** `controllers/controllers.py:483`.
- **Futura correção:** preparar arquivos temporários e publicar o conjunto concluído.
- **Teste:** `test_defeito_csv_falha_segundo_arquivo_deixa_par_incompleto`.

### A05 — Média, condicional: conteúdo textual do CSV pode virar fórmula em planilhas

- **Reprodução:** cadastrar nome `=1+1` e exportar. O campo sai exatamente como
  `=1+1`, sem proteção para abertura em programas que interpretam fórmulas.
- **Impacto:** depende do programa e do modo de importação; não foi aberta uma
  planilha nem executada fórmula. O teste confirma a ausência de neutralização.
- **Local:** `controllers/controllers.py:466`, campos textuais da exportação.
- **Futura correção:** oferecer exportação segura para planilhas preservando a
  finalidade do CSV. Não confundir esse risco com injeção de SQL: a busca testada
  usa parâmetros e passou.
- **Teste:** `test_defeito_csv_texto_pode_ser_interpretado_como_formula`.

### A06 — Média: tela antiga pode remover um código transferido para outro produto

- **Reprodução:** instância A guarda os códigos do produto 1. Instância B remove um
  código e vincula ao produto 2. A confirma a remoção usando sua lista antiga: o
  código é removido do produto 2, sem conferir o dono esperado.
- **Impacto:** o novo produto perde o vínculo do código. As quantidades não mudam.
- **Local:** `controllers/controllers.py:266`, `views/view_admin.py:294`.
- **Futura correção:** validar o produto esperado dentro da mesma transação da
  remoção e recarregar a interface quando houver divergência.
- **Teste:** `test_defeito_remocao_codigo_com_tela_antiga_remove_novo_dono`.

### A07 — Média: falhas de disco não recebem mensagem adequada na operação

- **Reprodução:** simular `sqlite3.OperationalError('database or disk is full')`
  no controlador chamado pela confirmação de entrada. A exceção escapa do callback,
  que trata somente `ErroNegocio`; a mensagem de status esperada não é exibida.
- **Impacto:** o usuário pode não entender por que a movimentação falhou. Isso não
  demonstra fechamento de todo o programa: callbacks Tk normalmente registram a
  exceção. Cadastro e Admin também têm captura restrita, constatada por revisão.
- **Proteção aprovada:** outro teste simula erro de I/O ao inserir o log; a transação
  reverte o saldo corretamente.
- **Local:** `views/view_operacao.py:232`, `controllers/controllers.py:41`.
- **Futura correção:** mensagens para falhas de persistência e registro técnico,
  preservando o rollback e sem informar sucesso antes da confirmação.
- **Teste:** `test_defeito_falha_disco_na_operacao_nao_exibe_mensagem`.

### A08 — Média: busca em Relatórios e Ajustes limita a lista a 500 sem indicar corte

- **Reprodução:** cadastrar 501 produtos fictícios. A listagem completa retorna
  501; `buscar_produtos('')`, usada nessas telas, retorna 500.
- **Impacto:** a contagem pode parecer o total e produtos podem ficar fora de uma
  busca ampla. Uma busca mais específica ainda pode encontrá-los.
- **Escopo:** o painel Admin > Produtos cadastrados usa listagem completa e passou
  nos testes; a exportação também não tem esse limite.
- **Local:** `models/models.py:338`, `views/view_relatorios.py` `_buscar`,
  `views/view_admin.py` `_buscar`.
- **Futura correção:** paginação ou indicação explícita de truncamento e total.
- **Teste:** `test_defeito_relatorios_e_busca_admin_limitados_sem_aviso`.

### A09 — Baixa, entrada extrema: quantidade maior que o limite do SQLite gera erro técnico

- **Reprodução:** quantidade inicial textual `9223372036854775808` (2^63).
  Recebe `OverflowError`, em vez de erro de validação para o usuário.
- **Impacto:** falha do callback; cadastro parcial não fica gravado, confirmado por
  teste separado. A quantidade é muito superior a um estoque realista.
- **Local:** validadores de quantidade em `controllers/controllers.py:91` e `:101`.
- **Futura correção:** limites de negócio e de armazenamento, inclusive saldo após entrada.
- **Teste:** `test_defeito_quantidade_fora_int64_deveria_gerar_erro_negocio`.

### A10 — Baixa, entrada extrema: saldos individuais aceitos podem estourar a soma dos KPIs

- **Reprodução:** dois produtos com 2^62 unidades cada. Os registros são aceitos,
  mas a consulta de KPIs falha com `sqlite3.OperationalError: integer overflow`.
- **Impacto:** dashboard indisponível para esse conjunto artificial de dados.
- **Local:** `models/models.py:481`.
- **Futura correção:** limites plausíveis de quantidade e proteção dos agregados.
- **Teste:** `test_defeito_soma_saldos_permitidos_quebra_kpis`.

### A11 — Baixa, entrada extrema: custo finito aceito pode gerar total infinito

- **Reprodução:** custo inicial `1e308`, quantidade 2. O cadastro aceita; o valor
  investido agregado resulta em infinito.
- **Impacto:** indicadores financeiros inválidos com valores extremos. A validação
  existente de NaN/infinito na entrada continua funcionando; falta proteger produtos
  e somas de valores individualmente finitos.
- **Local:** `controllers/controllers.py:111`, cadastro; `models/models.py:481`.
- **Futura correção:** limites monetários de negócio e checagem dos totais.
- **Teste:** `test_defeito_valor_finito_produz_total_infinito`.

### A12 — Baixa: entrada sem informar custo altera custo com mais de quatro casas

- **Reprodução:** cadastrar custo `10,123456`; registrar entrada com custo vazio.
  O custo passa a `10,1235`, apesar de o comportamento documentado ser mantê-lo.
- **Impacto:** pequena diferença de precisão; cadastro aceita mais casas que as
  mantidas pelo cálculo de entrada.
- **Local:** `controllers/controllers.py` `cadastrar_produto`, `registrar_entrada`
  e `calcular_custo_medio_ponderado`.
- **Futura correção:** definir precisão uniforme e preservar o custo ao deixá-lo vazio.
- **Teste:** `test_defeito_entrada_sem_custo_altera_custo_preciso`.

### A13 — Baixa: sugestão incorreta para tônico capilar

- **Reprodução:** `sugerir_categoria('Tônico capilar')` retorna Skincare.
- **Causa:** o termo genérico “tônico” é avaliado antes de “tônico capilar”.
- **Impacto:** categoria errada se o usuário aceitar a sugestão sem revisar.
- **Local:** `config.py:117` e `:139`.
- **Futura correção:** priorizar termos específicos.
- **Teste:** `test_defeito_tonico_capilar`.

### A14 — Baixa: sugestão automática anterior permanece depois de apagar o nome

- **Reprodução:** digitar “Shampoo” e apagar o nome. A categoria automática continua
  Cabelos; o teste do callback confirma isso sem criar janela.
- **Impacto:** ao substituir por um nome sem palavra reconhecida, pode ficar uma
  classificação do produto anterior. Por revisão, marca segue o mesmo padrão.
- **Local:** `views/view_cadastro.py:146`.
- **Futura correção:** limpar sugestões automáticas sem desfazer escolhas manuais.
- **Teste:** `test_defeito_sugestao_categoria_permanece_apos_apagar_nome`.

## Pontos de projeto observados, separados dos 14 defeitos

- Backup local automático é feito ao abrir um banco existente, não continuamente;
  não há retenção, rotação nem cópia externa. Uma longa sessão não produz novos
  snapshots automaticamente. Falha de backup impede abrir o aplicativo; essa
  proteção foi testada e preserva os dados, mas necessita orientação de recuperação.
- PIN administrativo está fixo no código, sem gestão de usuários, tentativas ou
  identidade do operador no histórico. É uma barreira simples de interface, não
  controle de acesso completo. Não foi tentado acesso à sessão real do usuário.
- Histórico não registra quem vinculou/desvinculou códigos. Não há tela de edição
  geral de nome/marca/categoria/preço, nem restauração assistida de backup.
- GTIN-14 é validado, mas vincular um código de kit ao mesmo produto não modela
  componentes ou multiplicadores de unidades. Lotes, validade, reservas por canal,
  fila de API e reconciliação continuam sendo funcionalidades futuras.
- As consultas e a inserção das linhas nas telas são síncronas. Carga alta de
  histórico pode afetar a interface; não foi comprovado travamento visual.
- Dados ao lado do executável exigem uma pasta gravável. Instalação em pasta
  protegida e recuperação após falha física de disco não foram testadas.

## O que passou

Cadastro, múltiplos códigos, rejeição de códigos duplicados/inválidos, preservação
de zeros, entradas, saídas, custo médio em valores normais, bloqueio de saldo
insuficiente, ajustes, desfazer, busca sem acentos, filtros/ordenação do catálogo,
relatórios vazios/preenchidos, cancelamentos e exportação textual com acentos,
aspas, delimitadores e quebras de linha.

As verificações de interface são testes de callbacks e componentes substitutos
(mocks), não uma certificação de renderização ou de todos os cliques reais.

Persistência: concorrência entre conexões, disputa pela última unidade, código
único concorrente, proteção contra ajuste desatualizado, confirmação de desfazer,
rollback em erro de log/commit, transações aninhadas, backup com WAL, migração
legada, recusa de versão futura e restauração em base temporária com nova operação.

Dois processos filhos encerrados via `os._exit` confirmaram que operações sem
commit são revertidas e operações com commit persistem; ambas as bases reabriram
com `integrity_check = ok`. Isso simula interrupção de processo, não corte físico
de energia nem defeito de armazenamento. Um arquivo corrompido fictício também foi
recusado sem sobrescrita.

## Carga e cobertura adicional

- 1.000 operações pseudoaleatórias, com semente fixa, comparadas a um modelo de
  saldo/custo e pilha de desfazer independente.
- 400 GTINs gerados nos quatro tamanhos e 3.600 variantes com DV errado, calculados
  por algoritmo independente que percorre o corpo da direita para a esquerda.
- 5.000 produtos e 10.000 movimentações fictícias: saldo agregado de 45.000 conferido;
  integridade SQLite aprovada. Medidas desta execução, **somente banco em memória**:

| Consulta | Tempo aproximado | Resultado |
|---|---:|---:|
| Catálogo completo | 21 ms | 5.000 produtos |
| Busca ampla | 21 ms | 500 produtos (limite A08) |
| Histórico completo | 33 ms | 10.000 movimentações |
| KPIs | 2,5 ms | 4 indicadores |
| Curva A | 3,4 ms | 5 produtos |

Não usar esses tempos como garantia da velocidade das telas, de disco ou de outro
computador. Ambiente: Python 3.14.3, CustomTkinter 6.0.0, pandas 3.0.6,
matplotlib 3.11.2, Pillow 12.3.0, PyInstaller 6.22.3, Windows 11.

## Limites e verificações ainda pendentes

Não existe teste finito de “todas as situações possíveis”. Esta rodada cobre os
cenários descritos e não garante ausência de outros defeitos. Não foram testados
scanner USB real, DPI/resoluções, todos os fluxos visuais, permissões reais do
Windows, instalação em outro PC, disco fisicamente cheio/danificado ou energia.
Não foram inspecionados dados reais da loja nem chamadas a marketplaces.

No momento da auditoria, `dist/GestorEstoque/GestorEstoque.exe` **não estava presente**;
portanto não houve teste de abertura ou inspeção desse executável nesta rodada.
A pasta não foi recriada nem substituída. A01 foi comprovado com a rotina instalada
do empacotador sobre arquivos fictícios, sem precisar da build de uso.

Para reproduzir a suíte e gerar evidências, a partir da pasta do projeto:

```powershell
.\.venv\Scripts\python.exe -B auditoria/executar_auditoria.py
```

Prioridade sugerida para uma futura rodada de correção: A01; depois A02–A08;
em seguida limites numéricos A09–A11 e os ajustes A12–A14. Nenhuma dessas
correções foi aplicada nesta auditoria.
