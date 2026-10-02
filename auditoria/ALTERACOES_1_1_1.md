# GiStocker 1.1.1 — ajustes solicitados

- Bloqueio por inatividade: 90 minutos (5.400 segundos), tanto no temporizador
  quanto na conferência de atividade depois de a sessão expirar.
- Senhas novas/trocas: mínimo de 6 e máximo de 128 caracteres. Não se exige
  seis caracteres todos diferentes. Continuam rejeitadas repetições e sequências
  previsíveis, caracteres de controle e confirmação diferente.
- Mensagens de criação/troca de senha e configurações atualizadas. Parâmetros
  centralizados em `config.py`. Senhas já existentes não foram alteradas.
- Criptografia e formato do banco permanecem compatíveis com 1.1.0. Nenhum
  banco real foi aberto ou modificado para realizar esta mudança.

Verificação: 185 testes aprovados (`testes_1_1_1.txt`) e 4 testes com widgets reais
aprovados (`interface_1_1_1.txt`). Incluem criação, troca e reabertura com senhas de
seis caracteres, rejeição de cinco caracteres e bloqueio aos 5.400 segundos,
sem bloqueio aos 600 ou 5.399 segundos. O teste da interface também confirma
que ultrapassar dez minutos já não encerra a sessão.

Senhas curtas reduzem a resistência a tentativas offline. A aceitação de seis
caracteres foi feita por solicitação do proprietário; senhas longas continuam
recomendadas. Não há recuperação do banco se a senha for esquecida.

Build: ver `build_1_1_1.log`. Conferência do pacote: `distribuicao_1_1_1.json`.
Para usar no fonte, feche/reabra pelo `2_executar.bat`. Para atualizar uma
instalação compilada, siga `SEGURANCA.md`, preservando os dados da instalação.
