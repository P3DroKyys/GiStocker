# Proposta futura: estoque multicanal

Registro da conversa em 30/09/2026. São ideias para avaliação futura, não uma
autorização para implementar integrações ou alterar as regras atuais.

## Objetivo discutido

Manter o GiStocker como aplicativo local e avaliar integração com Shopee e TikTok
Shop, coordenando vendas online com as baixas das vendas físicas.

## Preferência de distribuição

- Prioridade para a loja física.
- Exemplo proposto pelo usuário: 60% das unidades livres para a loja e 40% para
  o comércio eletrônico; divisão inicial sugerida de 20% para cada marketplace.
- Cotas exclusivas por canal para evitar oferecer a mesma unidade simultaneamente.
- Arredondamento favorecendo a loja física; considerar reserva mínima física,
  percentuais por produto e preferência/alternância para sobras entre marketplaces.
- Os percentuais são metas sobre unidades livres, depois de descontar reservas.
  Pedidos comprometidos não podem ser retirados para recompor a cota física.
- Reequilíbrio confirmado: reduzir disponibilidade no canal de origem, conciliar
  pedidos concorrentes e somente então liberar unidades no destino. Transferências
  ficam pendentes quando não houver confirmação suficiente.

## Operação e arquitetura em avaliação

- Registrar/reservar a venda física antes da conclusão, especialmente em saldo baixo.
- Separar estoque físico, reservado, disponível e cotas por canal.
- Vincular produto/variação local a loja, anúncio e SKU externo; GTIN não substitui
  esse vínculo. Kits compostos exigem reserva/baixa dos componentes.
- Serviço separado da interface, iniciado com o Windows, com fila persistente,
  tentativas de reenvio e reconciliação periódica.
- Processar pedidos/eventos de forma idempotente para não descontar duas vezes.
- Tratar cancelamentos e devoluções conforme o estado; devolver ao estoque vendável
  somente quando couber, com conferência física de mercadoria retornada.
- APIs oficiais, autorização das lojas e permissões disponíveis no Brasil precisam
  ser verificadas quando o projeto começar.
- Modelo totalmente local: sem internet, congelar transferências e permitir venda
  física apenas na cota local; reconciliar pedidos antes de redistribuir na volta.
- Modelo híbrido futuro: serviço online coordenando integrações, mantendo o desktop.
  Não presumir dois bancos independentes como autoridades do mesmo estoque.
- Avaliar um canal e poucos produtos antes de ampliar.

## SQLite: orientação inicial, ainda sem decisão de migração

SQLite continua candidato para uma instalação pequena em uma única máquina, com
transações curtas e escritas coordenadas. Separar camada de dados permite avaliar
PostgreSQL futuramente se crescerem concorrência, múltiplas máquinas ou disponibilidade.
Não compartilhar o arquivo SQLite por pasta de rede, OneDrive ou Dropbox como banco
ativo. Uma futura interface em vários computadores deve acessar um serviço, não abrir
o arquivo remotamente. WAL não permite múltiplos escritores simultâneos.

Antes da integração: corrigir leitura/cálculo fora da transação nas movimentações,
implementar migrações, backup consistente/restauração, reservas e processamento único
de eventos. Não manter transações abertas durante chamadas de API. Mudança local de
estoque e inclusão na fila de envio precisam ser atômicas; a comunicação externa
acontece depois e precisa lidar com confirmação incerta e reenvio.

Referências técnicas: https://www.sqlite.org/whentouse.html e
https://www.sqlite.org/wal.html. Reavaliar conforme volume real e arquitetura escolhida.
