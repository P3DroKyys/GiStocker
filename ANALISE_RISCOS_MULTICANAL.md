# Análise de riscos — GiStocker Multicanal

Data: 02/10/2026. Esta análise complementa a proposta de arquitetura e não ativa
integrações nem modifica o banco em uso.

## 1. Correções de premissas

### O GTIN não é a chave primária atual

No GiStocker, `Produtos.id` é o identificador interno estável. Ele é um inteiro
sequencial gerado pelo SQLite (`AUTOINCREMENT`), não um número aleatório. O primeiro
produto normalmente recebe 1, o próximo 2 e assim por diante; IDs excluídos não são
reaproveitados normalmente. Esse número já aparece no cadastro, painel de produtos,
Admin, relatórios e tela de operação.

O GTIN está em `Codigos_Barras` e um produto pode possuir mais de um código. Isso é
favorável à integração: GTIN pode ajudar a sugerir um vínculo, mas não deve determinar
sozinho que dois cadastros representam o mesmo item.

Cada vínculo externo deverá guardar, no mínimo:

```text
canal + loja + produto externo + SKU/variação externa + armazém -> Produtos.id
```

O nome do produto não é uma chave. GTIN ausente, repetido, incorreto, embalagem
diferente, variação e kit exigem confirmação humana. Depois de confirmado, o vínculo
usa os identificadores imutáveis da plataforma, mesmo que o título do anúncio mude.

O `Produtos.id` não precisa ser enviado à Shopee ou TikTok nem substituir o SKU do
anúncio. Ele será a chave estrangeira local usada por `Vinculos_SKU`, pedidos,
reservas, eventos e cotas. Restaurar ou mover o mesmo banco preserva esses IDs e os
vínculos. Uma eventual operação com vários bancos independentes poderá acrescentar
um UUID global sem substituir o ID atual.

### A integração não deve pedir a senha da loja

O fluxo esperado é “Conectar Shopee” ou “Conectar TikTok Shop”. O GiStocker abre a
página oficial de autorização, o vendedor concede acesso e a plataforma devolve um
código temporário, trocado por tokens renováveis. Chaves do aplicativo e tokens são
segredos diferentes. Eles ficam no cofre do serviço, nunca no executável, em texto
aberto, em logs ou numa caixa que exiba o valor completo.

A disponibilidade dos escopos, aprovação e ambientes de teste depende do tipo de
aplicativo, conta e país. Isso deve ser validado nas plataformas antes de escrever
os conectores.

## 2. Regra de 50% e o limite real da prioridade física

Para cada produto:

```text
livre = em_mãos - comprometido - quarentena
reserva_física = ceil(livre * 0,50)
ecommerce_total = livre - reserva_física - margem_de_segurança
```

O e-commerce total é dividido pelos pesos dos canais ativos. Com pesos iguais:

| Livre | Física | E-commerce | Exemplo Shopee/TikTok |
| ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 0 / 0 |
| 1 | 1 | 0 | 0 / 0 |
| 2 | 1 | 1 | 1 / 0 |
| 3 | 2 | 1 | 1 / 0 |
| 5 | 3 | 2 | 1 / 1 |
| 10 | 5 | 5 | 3 / 2 |

A unidade ímpar será sorteada entre os canais elegíveis. O resultado do sorteio fica
persistido. Sortear a cada atualização faria a unidade oscilar entre os canais,
criaria chamadas desnecessárias e abriria janelas de dupla exposição. Quando a
unidade for vendida ou uma nova unidade indivisível surgir, ocorre novo sorteio.

Um canal só é elegível quando há loja autorizada, vínculo confirmado de SKU/variação
e armazém, anúncio ativo e nenhuma pausa/incidente. Assim:

- produto existente somente na Shopee: 100% da cota online vai para a Shopee;
- produto existente somente no TikTok: 100% da cota online vai para o TikTok;
- produto existente nos dois: aplica pesos e sorteio persistente da sobra;
- produto inexistente nos dois: não há exposição online.

Uma API temporariamente indisponível não torna o produto inexistente. A última
quantidade confirmada nesse canal continua reservada até ser consultada ou retirada,
impedindo que a mesma unidade seja realocada para outro marketplace.

### Como o vínculo será feito sem GTIN remoto

Shopee e TikTok mantêm identificadores próprios de produto, variação/SKU, loja e, em
alguns casos, armazém. Esses identificadores chegam pela API mesmo que o anúncio não
tenha GTIN nem conheça o ID do GiStocker. O operador não precisa copiá-los.

Depois de conectar a loja, o GiStocker importa o catálogo em modo somente leitura e
apresenta uma tela de associação. Para cada anúncio ou variação, o sistema sugere
produtos locais usando GTIN exato, SKU do vendedor, marca, nome, volume e variação.
Sem identificador comum confiável, a confirmação inicial é manual. Isso é necessário
porque uma associação errada alteraria o estoque do produto errado.

Ao confirmar, `Vinculos_SKU` guarda algo equivalente a:

```text
produto_id_local = 42
canal = SHOPEE
loja_externa = ...
produto_externo = ...
sku_ou_variacao_externa = ...
armazem_externo = ...
estado = CONFIRMADO
```

O mesmo produto 42 pode ter um vínculo Shopee e outro TikTok. Se não houver anúncio
TikTok, a cobertura é marcada explicitamente como `NAO_PUBLICADO`; isso torna apenas
a Shopee elegível. Ausência de vínculo sem revisão fica `PENDENTE_VINCULO` e bloqueia
a ativação, evitando interpretar uma configuração incompleta como ausência real.

Cada SKU externo possui restrição de unicidade e só pode controlar um produto local.
Se um produto local tiver dois anúncios no mesmo marketplace, o sistema divide a cota
do canal entre eles e valida a soma, em vez de publicar a cota completa nos dois.

Depois do primeiro vínculo, alterações de título não o desfazem. Se o anúncio/SKU for
apagado, recriado ou substituído pela plataforma, ele volta para revisão. No futuro,
quando a API permitir e o usuário optar, o GiStocker poderá preencher um SKU do
vendedor como `GIS-000042`; isso facilita novos vínculos, mas não é requisito.

Percentual não elimina sozinho a quebra de estoque. Existe uma janela entre vender
fisicamente e os marketplaces confirmarem que reduziram o anúncio. A regra segura é:

```text
venda física permitida somente se
saldo após a venda >= exposição online ainda confirmada + margem
```

Dentro da reserva física, a venda é imediata. Para usar uma unidade ainda anunciada
online, o GiStocker reduz primeiro a quantidade remota, espera a confirmação e só
então libera a venda. Durante uma queda de internet, essa unidade adicional fica
bloqueada. Permitir a venda sem essa confirmação é uma decisão comercial que aceita
risco residual de venda simultânea.

## 3. Falhas prováveis e resposta proposta

| Situação | Consequência possível | Proteção necessária |
| --- | --- | --- |
| Mesmo pedido chega por webhook e consulta | Baixa duplicada | Inbox com chave idempotente única por loja, pedido, linha e transição. |
| Eventos chegam fora de ordem | Pedido cancelado ou enviado regressa de estado | Máquina de estados monotônica e versão/horário remoto. |
| Webhook não chega | Pedido demora a ser reservado | Consulta periódica com janela sobreposta e conciliação completa. |
| Timeout após a plataforma aplicar o estoque | Repetição incerta | Enviar quantidades absolutas e consultar o valor remoto antes de repetir. |
| Shopee e TikTok vendem ao mesmo tempo | Saldo fica negativo | Reserva transacional local, cotas rígidas e escritor único. |
| Marketplace já reduz o estoque ao vender | GiStocker subtrai novamente ao publicar | Separar evento de pedido de quantidade desejada/enviada/confirmada/observada. |
| Sobra é sorteada a cada sincronização | Unidade oscila entre marketplaces | Persistir o vencedor e sortear somente quando a geração da alocação mudar. |
| Produto só existe em uma plataforma | Sistema tenta atualizar SKU inexistente | Calcular apenas sobre vínculos confirmados e elegíveis. |
| Produto sem vínculo é tratado como ausente | Cota vai toda ao canal errado | Estado explícito `PENDENTE_VINCULO` ou `NAO_PUBLICADO`; pendência bloqueia ativação. |
| Dois anúncios representam o mesmo item | Cota completa é duplicada nos dois | Somar a exposição por produto/canal e dividir a cota entre os vínculos. |
| Venda física durante queda de internet | Unidade ainda anunciada é vendida duas vezes | Modo estrito usando a última exposição confirmada. |
| Alteração manual no Seller Center | GiStocker e plataforma discordam | Detectar deriva e aplicar política explícita: pausar ou republicar a fonte central. |
| Cancelamento parcial/tardio | Reserva liberada indevidamente | Regras por estado e linha; evento compensatório, sem apagar o histórico. |
| Devolução chega danificada | Unidade imprópria volta ao anúncio | Quarentena até conferência física. |
| Token vence ou é revogado | Canal para de sincronizar | Renovação antecipada, pausa segura, alerta e reautorização. |
| Limite ou indisponibilidade da API | Fila cresce ou chamadas são bloqueadas | Backoff exponencial com jitter, circuit breaker e respeito a `Retry-After`. |
| API muda de versão | Conector passa a interpretar dados errado | Adaptador por versão, testes de contrato e acompanhamento do changelog. |
| SKU é vinculado ao produto errado | Estoque de outro item é alterado | Confirmação humana, unicidade no banco e piloto com poucos SKUs. |
| Produto possui variações/armazéns | Atualização atinge lugar incorreto | Vínculo inclui SKU/variação e armazém, não apenas o anúncio. |
| Kit e unidade usam o mesmo componente | Ambos anunciam a mesma última unidade | Lista de componentes e reserva atômica; disponibilidade calculada pelo componente limitante. |
| PC perde energia no meio do envio | Comando fica com resultado desconhecido | Outbox persistente; no reinício consultar a plataforma antes de concluir ou repetir. |
| Banco fica sem espaço ou corrompe | Escritas e sincronização falham | Monitor de disco, parada segura, backup cifrado externo e teste periódico de restauração. |
| Relógio do PC está errado | Assinatura/autorização é recusada | Horário UTC interno, sincronização do Windows e alerta de desvio. |
| Duas instâncias gravam o banco | Corrida, bloqueio ou saldo divergente | Serviço Windows como único escritor; interface usa Named Pipe. |
| Serviço cai e a interface grava diretamente | Regras são contornadas | Interface entra em modo degradado e bloqueia mutações até o serviço voltar. |
| Malware/administrador obtém a conta do serviço | Segredos e banco podem ser usados | Conta dedicada, ACL, DPAPI, BitLocker, antimalware e logs sem segredos. |
| Restauração de backup antigo | Estado local volta no tempo | Conciliação obrigatória antes de publicar qualquer quantidade. |

Mesmo com essas proteções, nenhuma arquitetura local consegue garantir operação 24/7
enquanto PC, energia e internet estiverem indisponíveis. Ela pode garantir retomada
automática e convergência posterior. Um nobreak reduz interrupções curtas; BIOS com
religamento após energia e serviço com reinício automático reduzem intervenção.

## 4. Funcionamento local, webhooks e recuperação

O sincronizador não pode depender da janela do GiStocker estar aberta. Ele deve ser
um Serviço do Windows iniciado automaticamente. O serviço é o único processo que
abre o banco para escrita, processa pedidos, renova tokens e envia estoque.

Um PC residencial atrás do roteador normalmente não recebe webhooks HTTPS públicos.
Existem três opções:

1. **Somente consultas periódicas:** mantém tudo local, mas detecta vendas com atraso
   e pode não satisfazer todos os requisitos de aprovação das plataformas.
2. **Relay HTTPS mínimo:** recebe somente a notificação validada e deixa o serviço
   local buscar os detalhes oficiais. Banco, regras e estoque continuam locais.
3. **Expor o PC residencial:** não recomendado devido a certificado, IP, firewall,
   segurança e indisponibilidade durante quedas.

Independentemente da opção, a consulta periódica continua obrigatória. Webhook é um
aviso, não uma prova de que todos os eventos chegaram.

### Modo somente físico

Uma instalação nova começa em `FISICO`. Nesse modo:

- nenhuma loja é autorizada;
- nenhum processo acessa APIs de marketplace;
- o sistema funciona sem internet;
- o cofre não mantém tokens externos;
- o banco pode ser fechado quando a interface é bloqueada ou encerrada;
- todos os recursos atuais de estoque físico permanecem disponíveis.

O botão “Usar estoque multicanal” inicia um assistente, mas não publica valores. Só
depois de importar catálogo, confirmar vínculos, simular cotas e concluir o piloto o
estado muda para `MULTICANAL_ATIVO`.

Se a integração já estiver ativa, desligar é uma transação operacional. A opção
segura envia zero aos anúncios controlados, confirma a retirada, processa pedidos
pendentes, remove/revoga tokens e só então retorna a `FISICO`. Uma pausa curta mantém
a última exposição comprometida e não libera essas unidades para a loja física.

Ao iniciar depois de uma queda, o serviço deve:

1. abrir o banco e executar verificação de integridade;
2. recuperar comandos pendentes ou de resultado incerto;
3. renovar tokens quando necessário;
4. buscar pedidos desde um cursor anterior, com sobreposição;
5. deduplicar e aplicar eventos em transações;
6. consultar o estoque observado nos canais;
7. abrir incidentes para divergências;
8. somente depois recalcular e publicar as cotas.

## 5. Banco cifrado e reinício sem senha

Hoje a senha da pessoa participa da abertura do SQLCipher. Para o serviço voltar
sozinho, a chave do banco deverá ser uma chave aleatória de dados com dois invólucros:

- um cifrado pela senha, para login e recuperação portátil;
- outro pelo DPAPI do Windows, restrito à conta dedicada do serviço e à máquina.

O segundo invólucro permite reinício automático na mesma máquina. Ele não deve ser
copiado para outro computador como autorização válida. Uma instalação restaurada em
outro PC exige a senha de recuperação e nova autorização das lojas.

Há um limite inevitável: se malware ou uma pessoa controla o Windows como
administrador, também pode tentar controlar um serviço autorizado a operar sem
senha. A proteção real depende de Windows atualizado, usuário sem privilégio de
administrador no uso diário, BitLocker, antimalware, conta dedicada e backups fora
da máquina.

## 6. Histórico e telas

`Logs_Movimentacao` atual não guarda contexto suficiente para pedidos externos. A
migração deve preservar seus dados e preencher movimentos antigos como origem
`FISICO`. Novos eventos terão pelo menos:

```text
origem: FISICO | SHOPEE | TIKTOK
tipo do evento
produto e quantidade
loja/canal
pedido e linha externos
chave idempotente
evento compensado, quando houver
ocorrido_em_utc e registrado_em_utc
estado da sincronização
```

Na lista “Últimas movimentações” e nos relatórios entram as colunas **Origem**,
**Referência** e **Status**. Exemplos:

- Entrada — Físico / Recebimento;
- Saída — Físico / Venda no balcão;
- Saída — Shopee / Pedido abreviado;
- Saída — TikTok Shop / Pedido abreviado.

Dados pessoais do comprador não precisam aparecer nesse histórico. “Desfazer” passa
a criar um evento compensatório e deve ser bloqueado quando um pedido externo já
possuir consequência irreversível.

### Cancelamento e separação

Uma reserva é criada quando o estado confiável da plataforma indicar que o pedido
deve comprometer estoque. O retorno depende do ponto operacional:

| Situação | Tratamento |
| --- | --- |
| Cancelado antes da separação | Libera automaticamente a reserva e recalcula/publica cotas. |
| Cancelamento parcial | Libera somente as linhas e quantidades canceladas. |
| Em separação ou embalado | Abre pendência; libera após confirmar retorno físico à prateleira. |
| Já enviado | Não aumenta estoque por cancelamento. Aguarda o fluxo de devolução. |
| Devolução recebida | Entra em quarentena até inspeção. |

Para aplicar essa regra, o GiStocker precisa conhecer o estado operacional local do
pedido. A interface deverá permitir marcar “Iniciar separação”, “Embalado” e
“Enviado”, ou importar estados equivalentes quando a plataforma fornecer informação
confiável. Cada transição será idempotente para impedir uma segunda reposição quando
o mesmo cancelamento chegar novamente.

## 7. Sequência segura de implantação

1. Validar acesso de desenvolvedor, escopos, limites e ambiente de teste.
2. Criar serviço, cofre, comunicação local, eventos, inbox/outbox e recuperação,
   ainda sem chamar marketplaces.
3. Implementar alocador de 50% em simulador e testes de propriedade.
4. Criar telas de integrações, vínculo de SKU, política e monitor.
5. Conectar um marketplace em modo somente leitura por sete dias.
6. Habilitar escrita para 5–10 produtos simples e acompanhados.
7. Ampliar o primeiro canal; repetir o piloto para o segundo.
8. Implementar kits somente depois do fluxo unitário estabilizado.

Os dois marketplaces não devem ser ativados juntos no primeiro dia. O piloto precisa
provar reinício após queda, idempotência, eventos fora de ordem, timeout incerto,
token vencido, restauração de backup e retorno temporário ao controle manual.

### Limite de uma build distribuída

Se outras pessoas receberem a build e conectarem as próprias lojas, o GiStocker se
torna uma integração multicliente. Segredos usados para assinar requisições ou trocar
tokens não podem ser protegidos permanentemente dentro de um executável executado na
máquina do cliente. Cifrar o segredo na build apenas muda onde ele pode ser extraído.

Para distribuição multicliente, a arquitetura recomendada mantém banco e decisões de
estoque locais, mas usa um broker pequeno e sem catálogo completo para:

- receber o retorno da autorização;
- guardar ou usar o segredo global do aplicativo;
- trocar e renovar tokens conforme a política da plataforma;
- assinar operações quando necessário;
- receber webhooks e disponibilizá-los ao serviço local.

O broker não se torna a autoridade de estoque. Se estiver indisponível, o serviço
local mantém filas e retoma depois; as cotas já publicadas continuam limitando vendas.
Sem broker, cada usuário teria de criar a própria aplicação de desenvolvedor e guardar
as próprias chaves localmente.

### Decisão de implantação atual

A primeira implantação é `SINGLE_TENANT`: um lojista, uma instalação principal e as
contas de marketplace pertencentes a esse lojista. Isso permite começar com aplicação
privada e cofre local, sujeito às regras de aprovação e callback de cada plataforma.
O segredo é provisionado após instalar e protegido em repouso pelo Windows; ele não é
compilado no executável.

Futuras versões adaptadas para outros lojistas usarão o mesmo núcleo. Diferenças serão
perfis assinados, módulos, tema, políticas e conectores. Manter forks independentes
causaria migrações incompatíveis, testes duplicados e correções de segurança que não
chegariam a todos os clientes.

Quando múltiplos lojistas passarem a autorizar lojas online, entra o broker
multicliente descrito acima. O banco de cada lojista continua local e isolado.

### O que engenharia reversa consegue e o que ela não deve encontrar

A build atual é produzida com PyInstaller. É possível extrair seu arquivo interno e
decompilar parte do bytecode Python. O resultado não é necessariamente o fonte exato,
mas costuma revelar regras, nomes, textos, endpoints e qualquer chave gravada como
constante. Renomear ou cifrar uma constante dentro do mesmo executável não resolve:
em algum momento o programa precisaria decifrá-la na máquina do usuário.

Para uma distribuição segura, aplicam-se controles independentes:

| Objetivo | Controle |
| --- | --- |
| Não vazar segredo global | Segredo existe somente no broker/KMS. |
| Impedir uso de uma build copiada | Identidade assimétrica por instalação e revogação por dispositivo. |
| Evitar broker como oráculo de assinatura | Operações tipadas e allowlist; sem assinar URL/payload arbitrário. |
| Reduzir clonagem do código | Compilação nativa de módulos próprios e remoção de metadados. |
| Impedir build adulterada | Assinatura Authenticode e atualização com manifesto assinado. |
| Detectar credencial acidental | Varredura do repositório e do artefato em toda release. |
| Conter instalação comprometida | Escopos mínimos, rate limit, tokens curtos e revogação individual. |

Nenhum aplicativo executado num computador controlado por um atacante consegue ser
completamente imune à engenharia reversa. O objetivo verificável é que desmontar a
build não revele credenciais capazes de controlar as lojas de outros clientes e que
uma instalação comprometida possa ser bloqueada isoladamente.

## 8. Decisões ainda necessárias

Antes da primeira migração, precisam ser fechadas estas regras:

1. se o modo estrito será obrigatório;
2. margem padrão de segurança por produto;
3. uso apenas de consultas locais ou aceitação de relay HTTPS mínimo;
4. o que fazer com alteração manual no Seller Center: republicar automaticamente
   ou pausar e pedir revisão;
5. quantidade de contas/lojas e armazéns por plataforma;
6. existência de kits que compartilham itens com anúncios unitários;
7. qual marketplace e quais 5–10 produtos entram no primeiro piloto;
8. como o operador informa que começou a separar um pedido.

Decisões já incorporadas:

- 50% do saldo livre reservado ao físico, arredondando para cima;
- sobra online sorteada de forma persistente entre canais elegíveis;
- canal sem anúncio/vínculo não recebe cota daquele produto;
- cancelamento anterior à separação devolve o item automaticamente ao saldo livre;
- sincronização continua em Serviço do Windows com a interface fechada;
- autorização por fluxo oficial no navegador e segredos guardados pelo serviço;
- modo físico como padrão, totalmente funcional sem internet;
- ativação multicanal voluntária e desativação com retirada segura da exposição;
- primeira implantação single-tenant para um único lojista;
- futuras edições compartilham o mesmo núcleo e variam por perfil/módulo.

A implementação deve começar em modo simulado. Nenhum token real entra no código,
nos testes automatizados, nos arquivos de log ou na documentação.
