# Implementação multicanal — registro técnico da prévia

## Escopo e estado

Fundação local implementada incrementalmente, com integrações externas bloqueadas.
Esta é uma **prévia para validação**, não aprovação dos critérios de produção A–G.
Não foram usadas credenciais reais nem publicados estoques em lojas.

Snapshot anterior: `auditoria/multicanal_20261002_013328/fonte_antes.zip`, com manifesto
de hashes no mesmo diretório. Não contém bancos reais. Linha de base:
`auditoria/baseline_multicanal.txt`, **209 testes aprovados**.

## Alterações

- `multicanal/esquema.py`: migração aditiva 1→2; cobertura, políticas, vínculos,
  pedidos/itens, reservas, eventos imutáveis, inbox/outbox, estados, incidentes,
  cursores e componentes de kits. As duas últimas estruturas são preparatórias.
- `multicanal/motor.py`: regras de alocação por produto, cobertura explícita,
  sorteio persistente, proteção física, pedidos e compensações transacionais.
- `multicanal/sincronizacao.py`: adaptador exclusivamente fictício, recuperação de
  envio incerto, observação antes de repetição, backoff e exposição conservadora.
- `servico/nucleo.py`: autenticação, sessões vinculadas à identidade Windows,
  comandos permitidos, deduplicação transacional e isolamento do laboratório.
- `servico/pipe.py`: canal Windows local, DACL explícita, tamanho/tempo limitados,
  rejeição de clientes remotos e verificação do PID do serviço na instalação.
- `servico/cofre.py`: chave aleatória, envelope AES-GCM/scrypt, DPAPI opcional,
  migração, backup portátil e restauração em diretório novo.
- `servico/cliente.py`: proxy dos controladores existentes sem conexão de banco.
- `servico/executar.py`: agente de desenvolvimento e host do serviço Windows.
- `servico/importacao.py`: cópia portátil preservada, bloqueio de escritores,
  hashes e publicação atômica do conjunto importado.
- `views`: Configurações > Integrações, cotas/vínculos/pedidos/monitor, origem no
  histórico e renovação de sessão apenas por atividade, sem polling prorrogar login.
- `instalador`: Inno Setup + configuração auditável de serviço/ACL/recuperação.
- `gerar_build.py`: build única, inventário de dependências, exclusão de artefatos
  de dados/credenciais, hashes e compilação opcional do Setup.

O histórico antigo continua legível e os IDs sequenciais não mudam. A única
expectativa antiga atualizada nos testes é a versão de esquema, agora 2.

## Decisões e desvios explícitos

Inno Setup foi escolhido por empacotar dependências e atalhos com UAC/desinstalação,
com script pequeno e revisável para serviço e rollback. O compilador 6.7.3 foi obtido
da distribuição oficial e sua assinatura Pyrsys B.V. foi verificada como válida.
Isso **não significa** que o executável/instalador do GiStocker esteja assinado.

A mudança para compilação nativa integral foi adiada: trocar simultaneamente o
empacotador, o driver SQLCipher e a arquitetura dificultaria isolar regressões.
PyInstaller permanece nesta prévia. Não é uma proteção contra engenharia reversa.
Perfis comerciais assinados por cliente ainda não foram implementados; não foram
criados forks nem inseridos segredos compartilhados.

Produção e simulação usam arquivos SQLCipher diferentes. O laboratório não é uma
API real nem uma réplica contínua dos dados físicos. A ativação real fica bloqueada
por construção: o schema de lojas desta prévia aceita somente `SIMULADO`.

Importação sem senha pode conferir estabilidade e hashes, mas não integridade
criptográfica. Essa verificação ocorre obrigatoriamente antes de liberar o primeiro
login. Essa limitação evita pedir senha no instalador ou armazená-la para o helper.

## Evidências e roteiro

Testes novos em `auditoria/verificar_multicanal.py`, `verificar_ipc.py` e
`verificar_recuperacao.py`. Cobrem invariantes de 501 saldos, repetição de pedido
100 vezes, cancelamentos, quarentena, exposição, dois anúncios por canal, falhas
de conexão, DPAPI, restauração, schema, IPC real, token Windows restrito, concorrência
e morte abrupta do processo nos dois lados do commit.

O teste `smoke_interface_multicanal.py` usa widgets reais em janela oculta e agente
separado, com banco temporário. Exercita as telas existentes nos dois temas, vínculos,
publicação fictícia, encerramento e bloqueio. Não controla a janela da loja.

Logs intermediários permanecem na auditoria, incluindo falhas corrigidas. O relatório
de execução final e os caminhos dos artefatos são registrados separadamente para não
confundir tentativas intermediárias com validação concluída.

Ainda não comprovados neste ambiente: reboot do Windows, conta virtual sob SCM em
máquina limpa, instalação/upgrade/rollback/uninstall completos e perda física de
energia/disco. Falha de escrita foi injetada, não provocada enchendo o disco real.
Não se deve transformar essas limitações em uma alegação de homologação.

## Documentação externa verificada

- [Named Pipe Security and Access Rights](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights):
  DACL explícita e acesso do cliente sem direito de criar outra instância do pipe.
- [CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata):
  DPAPI por identidade, sem flag de proteção compartilhada pela máquina inteira.
- [Service User Accounts](https://learn.microsoft.com/en-us/windows/win32/services/service-user-accounts):
  contexto próprio do serviço e perfil gerido pelo SCM.
- [Inno Setup](https://jrsoftware.org/isdl.php): compilador oficial; avaliar a licença
  aplicável antes de uso comercial do instalador.
- [Shopee — autorização](https://open.shopee.com/developer-guide/20): o acesso à
  documentação retornou 403 no ambiente de consulta. Endpoints/escopos não foram
  inventados ou homologados a partir de fontes de terceiros.
- [TikTok Shop — Update Inventory](https://partner.tiktokshop.com/docv2/page/update-inventory):
  portal oficial identificado; leitura completa depende da aplicação/documentação
  autenticada. O conteúdo acessível não basta para implementar um conector real.

Para F/G são necessários aplicativo e permissões oficiais, documentação acessível
para a região/conta, autorização do lojista, provisionamento seguro de credenciais
e aprovação expressa do piloto. Não forneça senhas ou tokens pelo chat.
