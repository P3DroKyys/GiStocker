# Correções da auditoria de 2026-10-17

Referência: `auditoria/RELATORIO_BUGS_2026-10-17.md` (BUG-01 a BUG-29).
Testes de regressão: `auditoria/verificar_correcoes_bugs_2026.py` (61 testes; cada teste falhou antes da
correção correspondente e passa depois).

BUG-01 a BUG-11 foram corrigidos numa sessão anterior e revalidados aqui (revisão do diff + testes).
BUG-12 a BUG-29 foram corrigidos nesta sessão.

## Resultado da verificação

- Suíte completa: `.venv\Scripts\python.exe -B -m unittest discover -s auditoria -p "verificar*.py"`
  → **318 testes, todos OK** (257 anteriores + 61 de regressão), ~160 s, executada numa cópia isolada
  do projeto (sem tocar em `dados/` nem no `erros.log` real).
- Testes de fumaça da interface (`smoke_gestao_dados`, `smoke_interface_upgrade`,
  `smoke_interface_multicanal`, `smoke_busca`): todos OK.
- Harness do Apêndice A do relatório, com pipe real: BUG-09 mostra a mensagem de validação sem atraso nem
  pastas órfãs; BUG-07 responde "A senha atual está incorreta." e a sessão continua válida; BUG-05
  converte `1.500` em 1500; BUG-14 a simulação reflete o estoque atual; BUG-02 termina com estoque 8.

## Tabela

| ID | Status | Causa raiz corrigida | Arquivos alterados | Teste que prova |
|---|---|---|---|---|
| BUG-01 | corrigido | `servico.ps1` enumera o JSON existente item a item, valida cada SID, grava `string[]` e restaura o arquivo anterior no rollback; `pipe.atributos` recusa estrutura que não seja lista de strings | `instalador/servico.ps1`, `servico/pipe.py` | `test_bug01_reinstalacao_powershell_51`, `test_bug01_consumidor_rejeita_estrutura_invalida` |
| BUG-02 | corrigido | O journal gera UUID novo por ação; o id só é repetido na retentativa imediata da mesma chamada. Idem para lotes de importação | `servico/pendencias.py`, `servico/cliente.py`, `servico/transferencia.py` | `test_bug02_nova_venda_apos_resposta_perdida`, `test_bug02_repeticao_imediata_preserva_id`, `test_bug02_importacao_identica_e_nova_acao` |
| BUG-03 | corrigido | `Motor.fisico`/`preparar` tratam só o produto afetado; índices `idx_eventos_produto`/`idx_eventos_log` com migração para `user_version` 3 e inclusão na lista branca do esquema | `multicanal/motor.py`, `multicanal/esquema.py`, `models/models.py`, `models/seguranca.py`, `gestao/backup.py` | `test_bug03_venda_6000_produtos_50000_eventos`, `test_bug03_v2_migra_reabre_e_restaura_backup`, `test_bug03_metodos_isolam_produto_e_compensam` |
| BUG-04 | corrigido | Histórico paginado por cursor com `LEFT JOIN` indexado (sem N+1); catálogo transferido em páginas; o pipe responde erro em vez de desconectar; falha de transporte em leitura não bloqueia a sessão | `controllers/controllers.py`, `models/models.py`, `servico/nucleo.py`, `servico/pipe.py`, `servico/cliente.py`, `views/view_relatorios.py` | `test_bug04_primeira_pagina_50000_logs`, `test_bug04_catalogo_transfere_paginas_limitadas`, `test_bug04_resposta_extensa_recebe_erro_no_pipe_real`, `test_bug04_leitura_sem_resposta_preserva_sessao` |
| BUG-05 | corrigido | `converter_para_float` com regra pt-BR explícita (ponto de milhar, vírgula decimal; ponto decimal só com 1, 2 ou 4 casas); formatos ambíguos rejeitados; a importação reutiliza o mesmo conversor | `utils/texto.py`, `GESTAO_DADOS.md` | `test_bug05_milhar_ptbr_e_decimais`, `test_bug05_rejeita_formatos_estranhos`, `test_bug05_importacao_reutiliza_conversor` |
| BUG-06 | corrigido | Ciclo do worker vira gerador com orçamento de tempo, executado em thread com conexão própria; `alocar` prepara só o produto | `multicanal/sincronizacao.py`, `multicanal/motor.py`, `servico/nucleo.py` | `test_bug06_manutencao_800_produtos_limitada_e_progride` |
| BUG-07 | corrigido | Falha de autenticação tem tipo próprio (`ErroAutenticacao`); só `ErroSessao` (código `SESSAO`) bloqueia a interface | `models/seguranca.py`, `servico/cofre.py`, `servico/nucleo.py`, `servico/cliente.py` | `test_bug07_senha_atual_errada_preserva_sessao`, `test_bug07_somente_sessao_invalida_bloqueia` |
| BUG-08 | corrigido | Backup diário passa a ser *best-effort*, com aviso na interface e registro em log; só falha de autenticação conta para o atraso | `servico/cofre.py`, `servico/nucleo.py`, `views/main_view.py` | `test_bug08_backup_indisponivel_nao_impede_login`, `test_bug08_falha_operacional_nao_conta_como_senha` |
| BUG-09 | corrigido | Valida a nova senha antes de criar o staging e remove o staging em falha; `ValueError` de validação chega à tela sem atraso; a tela valida antes de enviar | `servico/cofre.py`, `servico/nucleo.py`, `views/acesso.py` | `test_bug09_validacao_sem_staging_nem_atraso`, `test_bug09_falha_de_publicacao_remove_staging`, `test_bug09_tela_valida_antes_do_envio` |
| BUG-10 | corrigido | `manutencao()` protegida no laço do pipe: registra em `<raiz>/logs`, publica aviso e reagenda com backoff | `servico/pipe.py`, `servico/nucleo.py` | `test_bug10_falha_manutencao_nao_derruba_agente` |
| BUG-11 | corrigido | Agente portátil encerra após 60 s sem sessão/simulação/job; `status` publica versão e revisão do código; interface substitui agente de outra versão (`encerrar_agente`) | `servico/executar.py`, `servico/nucleo.py`, `servico/pipe.py`, `servico/cliente.py`, `main.py`, `config.py` | `test_bug11_agente_portatil_ocioso_encerra`, `test_bug11_versao_diferente_substitui_so_portatil`, `test_bug11_status_publica_versao_do_agente` |
| BUG-12 | corrigido | A máscara de Alt depende da plataforma (Windows `0x20000`; X11 `0x8`); NumLock, CapsLock e ScrollLock não filtram mais F1–F5; Alt+F4 não navega | `views/main_view.py` | `test_bug12_atalhos_ignoram_travas_do_teclado` |
| BUG-13 | corrigido | `config.DIRETORIO_LOGS` (instalado: `%LOCALAPPDATA%\GiStocker`; portátil: pasta do programa) para a interface; o agente/serviço grava em `<raiz>/logs`; recusas esperadas (`ValueError`) não são registradas como falha | `config.py`, `utils/erros.py`, `main.py`, `servico/cofre.py`, `servico/gestao.py`, `views/gestao_dados.py` | `test_bug13_instalado_registra_em_localappdata`, `test_bug13_registro_padrao_usa_pasta_de_logs`, `test_bug13_falha_de_inicio_da_interface_usa_pasta_de_logs`, `test_bug13_servico_registra_na_raiz_e_ignora_validacao`, `test_bug13_interface_nao_registra_erro_esperado` |
| BUG-14 | corrigido | Ativar a simulação a partir do estado `FISICO` descarta a cópia anterior (`simulacao.db` e arquivos auxiliares) e copia o estoque atual; a retomada de um ensaio em andamento preserva a cópia | `servico/nucleo.py` | `test_bug14_reativar_simulacao_usa_estoque_atual`, `test_bug14_retomada_preserva_simulacao_em_andamento` |
| BUG-15 | corrigido | Tabela `TRANSICOES` (destino e origens permitidas); `ENCERRANDO_MULTICANAL` só termina em `FISICO`; transição inválida retorna `ErroNegocio` sem alterar o estado | `servico/nucleo.py` | `test_bug15_transicoes_invalidas_sao_recusadas` |
| BUG-16 | corrigido | O diálogo descreve o `.gsbackup`, desaconselha substituir `dados/estoque.db` e aponta para "Recuperação portátil" no `GUIA_MULTICANAL.md` (distribuído com a build) | `views/view_relatorios.py` | `test_bug16_exportacao_protegida_orienta_recuperacao_real` |
| BUG-17 | corrigido | O cliente converte o código `SESSAO` em `ErroSessao`; `mensagem_falha` mostra "Sessão expirada..." para sessão, o texto do serviço para `ErroSeguranca`/`ValueError` e a mensagem de disco só para erro de I/O ou banco; as telas capturam `ERROS_EXIBIVEIS` (inclui `ValueError`); a leitura de código na Operação é protegida | `utils/erros.py`, `servico/cliente.py`, `views/view_operacao.py`, `views/view_cadastro.py`, `views/view_admin.py` | `test_bug17_mensagem_conforme_a_causa`, `test_bug17_operacao_exibe_recusa_do_servico`, `test_bug17_telas_capturam_erros_exibiveis` |
| BUG-18 | corrigido | Linha de pedido identificada pelo `id` do item (não pela posição); painel ordena pedidos e catálogo | `views/view_integracoes.py`, `multicanal/motor.py` | `test_bug18_selecao_de_pedido_sobrevive_ao_refresh`, `test_bug18_painel_ordena_pedidos_e_catalogo` |
| BUG-19 | corrigido | `GestaoDados.abandonado` (60 s sem contato, contado a partir do fim de cada passo); um login autenticado reverte o job órfão; job ativo continua bloqueando | `servico/gestao.py`, `servico/nucleo.py`, `servico/transferencia.py`, `GESTAO_DADOS.md` | `test_bug19_job_ativo_ainda_bloqueia_login`, `test_bug19_job_abandonado_e_revertido_no_login`, `test_bug19_passo_longo_nao_conta_como_abandono` |
| BUG-20 | corrigido | `_validar_dias` (1 a `MAXIMO_DIAS_RELATORIO` = 3650) nos dois relatórios por período; o Dashboard restaura o padrão fora da faixa | `config.py`, `controllers/controllers.py`, `views/view_dashboard.py` | `test_bug20_periodo_fora_do_limite_e_recusado`, `test_bug20_dashboard_restaura_periodo_padrao` |
| BUG-21 | corrigido | Quantidade zero sem custo não grava log; quantidade usa `converter_para_int` (como as telas); marca e categoria comparadas por `normalizar_texto`, gravando a grafia canônica | `gestao/planilha.py`, `GESTAO_DADOS.md` | `test_bug21_quantidade_zero_sem_custo_nao_gera_log`, `test_bug21_quantidade_com_milhar_igual_as_telas`, `test_bug21_marca_e_categoria_sem_diferenciar_caixa_e_acento` |
| BUG-22 | corrigido | O aviso "código não encontrado" só aparece depois da busca por trecho falhar; um prefixo de 12 dígitos encontra o EAN-13 | `utils/busca.py` | `test_bug22_prefixo_com_tamanho_de_gtin_encontra_parcial` |
| BUG-23 | corrigido | `%`, `_` e `\` escapados com `LIKE ? ESCAPE '\'` | `models/models.py` | `test_bug23_curingas_like_sao_literais` |
| BUG-24 | corrigido | Enter/Enter numérico na nova senha avança para a confirmação; na confirmação, envia | `views/acesso.py` | `test_bug24_enter_nos_campos_do_primeiro_acesso` |
| BUG-25 | corrigido | `<Control-L>` ligado junto com `<Control-l>` | `views/main_view.py` | `test_bug25_ctrl_l_bloqueia_com_caps_lock` |
| BUG-26 | corrigido | Com o seletor nativo aberto, a inatividade marca bloqueio pendente; ao fechar o seletor, a janela bloqueia e descarta o caminho escolhido | `views/main_view.py`, `views/gestao_dados.py` | `test_bug26_inatividade_com_seletor_aberto_bloqueia_ao_fechar` |
| BUG-27 | corrigido | Retenção dos `BACKUPS_MANTIDOS` (30) `.gsbackup` automáticos mais recentes, aplicada após cada backup diário; `.gsa` legados não são tocados | `config.py`, `servico/cofre.py`, `README.md` | `test_bug27_mantem_somente_os_backups_mais_recentes` |
| BUG-28 | corrigido | Instalado, as exportações legadas ficam dentro da cópia importada (nunca no pai de `ProgramData\GiStocker`); a importação portátil copia `aparencia.json` (o `tema.json` é o tema de cores em `assets`) | `servico/cofre.py`, `servico/importacao.py` | `test_bug28_exportacoes_legadas_ficam_na_instalacao`, `test_bug28_importacao_portatil_preserva_tema` |
| BUG-29 | corrigido | Limitador por identidade Windows (`tentativas[identidade]`), aplicado ao login e à troca de senha; a falha de autenticação é traduzida no `Nucleo`; a tela de Configurações exibe o motivo da recusa | `servico/nucleo.py`, `servico/cofre.py`, `views/view_configuracoes.py` | `test_bug29_limitador_de_login_por_identidade`, `test_bug29_troca_de_senha_tem_limitador`, `test_bug29_tela_exibe_motivo_da_recusa` |

## Testes antigos alterados (comportamento errado que o teste validava)

- `verificar_ipc.test_resposta_perdida_e_nova_acao_tem_outro_identificador` e
  `verificar_gestao_ipc.test_resposta_perdida_depois_commit_e_nova_importacao`: afirmavam que uma nova
  ação idêntica após resposta perdida era deduplicada. Esse é exatamente o BUG-02 (venda "engolida").
- `verificar_multicanal.test_migracao_e_immutabilidade` e o teste de migração do serviço: `user_version`
  passa a ser `BancoDados.VERSAO_ESQUEMA` (3) por causa dos índices do BUG-03.
- `verificar_multicanal.test_senha_bloqueio_e_expiracao`: afirmava que, depois de errar a senha atual, a
  troca imediata passava. Com o BUG-29 a repetição imediata recebe "Aguarde"; o teste agora afirma isso e
  simula o fim do intervalo antes da troca correta.
- Testes do BUG-07, 08 e 09 em `verificar_correcoes_bugs_2026.py`: as asserções passaram a usar
  `ErroSessao`, `<raiz>/logs/erros.log` e o limitador por identidade (consequência dos BUG-17, 13 e 29).

## Pontos de atenção

- BUG-12: o mapeamento de bits (`0x8` = NumLock e `0x20000` = Alt no Tk para Windows) vem da
  implementação do Tk e é coberto por teste com estados sintéticos. Ainda vale conferir uma vez na
  máquina da loja: com o NumLock ligado, F1–F5 devem trocar de tela.
- BUG-19: o prazo de abandono do job de gestão caiu de 5 min para 60 s (documentado em `GESTAO_DADOS.md`).
- BUG-27: o descarte automático apaga `.gsbackup` antigos de `dados/backups` além dos 30 mais recentes.
  Exportações manuais e `.gsa` legados não são afetados.
