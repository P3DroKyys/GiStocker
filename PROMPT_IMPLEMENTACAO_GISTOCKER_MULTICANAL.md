# Prompt mestre — implementação segura do GiStocker Multicanal

Quero que você trabalhe diretamente no código-fonte do GiStocker e leve esta tarefa
até o limite que for tecnicamente possível sem credenciais reais dos marketplaces.
Não quero apenas uma proposta: quero análise do código atual, plano de migração,
implementação incremental, testes, correção dos problemas encontrados, geração da
build/instalador e relatório final. Não ative integrações em lojas reais e não invente
credenciais, permissões ou respostas de API.

## 1. Repositório e contexto atual

O projeto está em:

```text
C:\Software Gestor\CODIGO\estoque_cosmeticos
```

Antes de alterar qualquer coisa:

1. leia as instruções locais aplicáveis, incluindo `AGENTS.md`, caso exista;
2. leia e confronte com o código atual:
   - `PROJETO_ESTOQUE_MULTICANAL.md`;
   - `ANALISE_RISCOS_MULTICANAL.md`;
   - `CONTEXTO_CODIGO.md`;
   - `SEGURANCA.md`;
   - os scripts BAT e a rotina de build;
3. mapeie o fluxo completo de abertura, autenticação, banco, controladores, telas,
   transações, backups, bloqueio e encerramento;
4. rode a suíte atual antes de editar e registre a linha de base;
5. como este diretório pode não possuir Git, crie um snapshot não destrutivo do
   fonte necessário antes da migração. Não copie bancos reais descriptografados.

O sistema atual é um desktop Windows em Python/CustomTkinter, empacotado por
PyInstaller. Usa SQLCipher/SQLite, senha de acesso, banco criptografado, backups,
pesquisa de produtos, cadastro, entrada, saída, Admin, dashboard e relatórios. A
versão observada é 1.2.0. Atualmente a interface abre o banco e instancia diretamente
os controladores. O banco e os dados ficam ao lado do executável.

Preserve todas as funcionalidades atuais. Não aceite regressões silenciosas para
concluir a arquitetura nova.

## 2. Objetivo do produto

O GiStocker continuará funcionando como sistema local de estoque físico, mas poderá
opcionalmente controlar estoque de Shopee e TikTok Shop. O banco, a autoridade do
saldo e as regras permanecem locais. A primeira implantação é `SINGLE_TENANT`: um
único lojista, uma instalação principal e contas de marketplace pertencentes a esse
lojista.

Futuramente poderão existir edições para outros lojistas. Não crie forks separados.
Use um núcleo único, com perfis assinados, módulos, identidade visual e políticas por
cliente. Nenhum perfil pode conter segredo, token ou chave do banco.

## 3. Decisões já aprovadas

Considere estas decisões como requisitos, não como sugestões:

- uma instalação nova começa em **Somente estoque físico**;
- o modo físico funciona integralmente sem internet e sem chamadas a marketplaces;
- a integração multicanal é opcional e ativada em Configurações;
- ativar o recurso inicia um assistente e não publica estoque imediatamente;
- o GiStocker é a fonte central do saldo físico;
- 50% do saldo livre de cada produto é reservado para a loja física, usando
  `ceil(saldo_livre * 0,50)`;
- o restante é distribuído somente entre canais elegíveis;
- com pesos iguais e uma sobra indivisível, o canal é sorteado;
- o sorteio é persistente: o vencedor fica gravado e não muda a cada sincronização;
- se um produto estiver apenas na Shopee, toda a cota online vai para a Shopee;
- se estiver apenas no TikTok, toda a cota online vai para o TikTok;
- ausência de vínculo não pode ser confundida com produto não publicado;
- GTIN não é a chave primária do produto;
- `Produtos.id` é o identificador local sequencial atual e deve ser preservado;
- o operador não deverá digitar IDs técnicos dos marketplaces;
- cancelamento antes da separação libera a reserva automaticamente;
- cancelamentos parciais liberam somente as linhas canceladas;
- item separado/embalado exige conferência antes de voltar ao vendável;
- item enviado só volta após devolução e inspeção;
- toda entrada de mercadoria tem origem física;
- saídas devem informar origem `FISICO`, `SHOPEE` ou `TIKTOK`;
- a sincronização precisa continuar com a interface fechada;
- após queda de energia, internet ou processo, o sistema deve retomar e reconciliar;
- a primeira ativação real será feita em apenas um marketplace e poucos SKUs;
- kits ficam para uma fase posterior ao fluxo unitário estabilizado;
- nenhum segredo compartilhado pode ser embutido no executável;
- a primeira implantação pode usar credenciais privadas provisionadas após instalar;
- futuras integrações multicliente deverão usar broker seguro ou credenciais próprias
  por cliente.

Adote como padrões iniciais, salvo impedimento técnico comprovado:

- modo estrito contra ruptura;
- margem de segurança zero no simulador;
- alteração manual detectada no Seller Center pausa o SKU e abre incidente;
- uma conta por plataforma na primeira versão;
- sincronização por polling e conciliação mesmo quando existir webhook;
- nenhum envio real de estoque durante o desenvolvimento da fundação.

## 4. Arquitetura obrigatória: serviço como escritor único

Transforme o sistema para este fluxo:

```text
GiStocker Desktop
    -> Named Pipe local autenticado
GiStocker Service
    -> casos de uso/controladores
    -> SQLCipher/SQLite
```

Requisitos:

1. somente o serviço abre o banco de produção para escrita;
2. a interface não executa SQL e não recebe a chave do banco;
3. interface e serviço trocam comandos e respostas estruturadas;
4. use Named Pipe do Windows com ACL restrita;
5. não exponha porta TCP local desnecessária;
6. cada pedido IPC possui versão, request ID, sessão, comando, parâmetros validados
   e resposta/erro tipado;
7. comandos mutáveis relevantes precisam de idempotência;
8. não mantenha transação SQLite aberta durante chamadas de rede;
9. se o serviço não responder, a interface entra em modo degradado e bloqueia
   mutações; ela nunca abre o banco diretamente como fallback;
10. leituras podem usar consultas do serviço e snapshots consistentes;
11. preserve uma camada de casos de uso independente do transporte para permitir
    testes sem iniciar o Windows Service.

No modo físico, o serviço pode iniciar bloqueado e abrir o banco após a senha ser
validada pela interface. Ao encerrar/bloquear a interface, feche o banco se não houver
integração ativa.

No modo multicanal, use uma chave de dados aleatória para o SQLCipher, embrulhada de
duas formas: pela senha humana e pelo DPAPI da conta do serviço. Isso permite reinício
automático na mesma máquina e recuperação portátil pela senha. Nunca deixe senha ou
chave aberta em arquivo, variável de ambiente permanente, linha de comando ou log.

## 5. Serviço do Windows e instalação prática

O cliente final deve receber preferencialmente um único arquivo semelhante a:

```text
GiStocker-Setup-<versao>.exe
```

Ele executa o instalador, aceita uma única elevação UAC e conclui a instalação sem
precisar usar terminal, BAT, `sc.exe` manualmente ou copiar dependências.

Analise as opções adequadas ao projeto — por exemplo Inno Setup, WiX ou equivalente
maduro — e escolha a solução mais simples, auditável e reproduzível. Não escolha uma
tecnologia apenas por familiaridade; documente por que ela atende serviço, upgrade,
ACL, rollback e desinstalação. Se a ferramenta não estiver instalada, prepare a
automação e solicite somente a permissão estritamente necessária para instalá-la.

O instalador deverá:

- instalar interface e serviço em local apropriado;
- criar atalhos e entrada de desinstalação;
- criar `C:\ProgramData\GiStocker` ou local equivalente para dados, backups e logs;
- aplicar ACL mínima para a conta do serviço e administradores autorizados;
- registrar o serviço com início automático atrasado;
- configurar recuperação após falhas;
- iniciar e executar health check do serviço;
- preservar banco, backups e exportações em upgrade;
- nunca apagar dados automaticamente na desinstalação;
- detectar uma instalação anterior;
- migrar de forma segura o banco portátil encontrado ao lado da instalação antiga;
- antes de migrar: parar escritores, criar backup, verificar integridade, copiar para
  temporário, validar, aplicar ACL e só então efetivar;
- fazer rollback de arquivos/serviço se a instalação falhar;
- deixar diagnóstico claro e sanitizado;
- abrir um assistente de primeira execução para criar/usar senha e selecionar modo
  físico ou multicanal.

Não prometa instalação literalmente sem interação: UAC, criação da primeira senha e
autorização oficial da loja são passos que exigem o usuário. Todo o restante deve ser
automatizado.

Mantenha os BATs úteis para desenvolvimento:

- `1_preparar_ambiente.bat` instala dependências homologadas;
- `2_executar.bat` inicia serviço/agente de desenvolvimento e interface sem exigir
  uma instalação de produção;
- `3_gerar_exe.bat` produz artefatos versionados e, quando possível, o instalador.

As builds antigas nunca podem ser apagadas ou sobrescritas silenciosamente.

## 6. Modelo de dados e migrações

Use migrações transacionais, versionadas e repetíveis. Preserve `Produtos`,
`Codigos_Barras` e o histórico existente. Movimentos antigos recebem origem física.

Modele, ajuste os nomes se necessário e justifique:

- `Canais`;
- `Lojas_Externas`;
- `Vinculos_SKU`;
- `Cobertura_Produto_Canal`;
- `Politicas_Alocacao`;
- `Estado_Alocacao`;
- `Eventos_Estoque` imutáveis;
- `Reservas`;
- `Pedidos_Externos`;
- `Itens_Pedido_Externo`;
- `Inbox_Eventos`;
- `Outbox_Comandos`;
- `Estado_SKU_Canal`;
- `Cursores_Sincronizacao`;
- `Incidentes_Sync`;
- `Componentes_Kit` para fase futura.

`Produtos.estoque_atual` pode permanecer como projeção rápida, mas alterações novas
devem gerar evento auditável. Corrigir/desfazer cria evento compensatório. Não apague
efeitos históricos. Use restrições de unicidade e chaves estrangeiras para impedir
vínculos duplicados, eventos repetidos e alocação inconsistente.

## 7. Cálculo de estoque e segurança contra ruptura

Use as definições:

```text
livre = em_maos - comprometido - quarentena
reserva_fisica = ceil(livre * 0,50)
ecommerce_total = max(0, livre - reserva_fisica - margem)
```

Distribua `ecommerce_total` apenas entre canais elegíveis. Um canal só é elegível
quando possui loja autorizada, vínculo confirmado, anúncio/variação/armazém válidos e
nenhum incidente impeditivo.

Estados mínimos de cobertura:

```text
PENDENTE_VINCULO
VINCULADO
NAO_PUBLICADO
IGNORADO
PAUSADO
```

`PENDENTE_VINCULO` não equivale a `NAO_PUBLICADO` e deve bloquear ativação daquele
produto. Falha temporária da API não remove elegibilidade nem libera a última
exposição confirmada.

Para sobra indivisível com pesos iguais, sorteie entre canais elegíveis e persista o
resultado/generation. Não sorteie novamente a cada recálculo. Preserve atribuições
quando possível e sorteie novamente apenas quando a unidade anterior desaparecer,
uma nova sobra surgir ou a elegibilidade mudar.

Modo estrito:

```text
venda física permitida somente se
saldo após a venda >= exposição online ainda confirmada + margem
```

Para invadir uma cota exposta online, primeiro retire/reduza remotamente, confirme e
depois libere a venda física. Sem conexão, bloqueie somente essa transferência; não
bloqueie vendas dentro da reserva física.

Envie quantidades absolutas aos marketplaces, nunca deltas. Separe claramente:

- quantidade desejada;
- enviada;
- confirmada;
- observada remotamente;
- exposição ainda comprometida.

## 8. Vínculo de produtos

O vínculo ocorre no nível correto de loja, produto remoto, SKU/variação e armazém:

```text
canal + loja + produto externo + SKU/variação + armazém -> Produtos.id
```

Depois de autorizar uma loja, importe o catálogo em modo somente leitura. A interface
mostra produto local e anúncio remoto lado a lado, incluindo imagem, título, marca,
variação, SKU do vendedor, GTIN quando existir, estoque e canal.

Sugira vínculos por:

1. GTIN exato e único;
2. SKU do vendedor já conhecido;
3. marca, nome, volume e variação normalizados;
4. similaridade textual apenas como ajuda.

Sem identificador confiável, exija confirmação humana, mas nunca exija que o usuário
copie IDs técnicos. IDs externos vêm da API. Cada SKU remoto aponta para no máximo um
produto local. Um produto local pode estar em múltiplos canais. Se houver dois
anúncios do mesmo produto no mesmo canal, a soma publicada entre eles não ultrapassa
a cota do canal.

## 9. Pedidos, cancelamentos e devoluções

Modele estado remoto e estado operacional local. Considere pelo menos:

```text
NOVO
RESERVADO
EM_SEPARACAO
EMBALADO
ENVIADO
CANCELADO
DEVOLUCAO_EM_CONFERENCIA
```

Regras:

- pedido elegível cria reserva uma única vez;
- mesma notificação via webhook e polling não duplica a baixa;
- chave idempotente inclui plataforma, loja, pedido, linha e transição/versão;
- evento fora de ordem não faz a máquina de estados regredir;
- cancelamento antes da separação libera automaticamente;
- cancelamento parcial libera apenas a parte cancelada;
- durante/depois da separação exige retorno físico à prateleira;
- enviado não retorna por uma simples notificação;
- devolução entra em quarentena até inspeção;
- nenhuma informação pessoal desnecessária do comprador aparece nos logs/telas.

Projete uma tela mínima de pedidos/pendências capaz de informar separação, embalagem,
envio, cancelamento e conferência, sem fingir estados que a API não confirma.

## 10. Origem e histórico das movimentações

Mostre nas movimentações e relatórios:

- origem física, Shopee ou TikTok;
- referência abreviada do pedido;
- data ocorrida e data registrada, em UTC internamente;
- quantidade;
- estado da sincronização;
- evento compensado, quando houver.

Exemplos:

```text
Entrada | Físico      | Recebimento
Saída   | Físico      | Venda no balcão
Saída   | Shopee      | Pedido SHP•••123
Saída   | TikTok Shop | Pedido TTS•••456
```

## 11. Resiliência e recuperação

Implemente inbox/outbox persistentes e uma máquina de estados para comandos:

```text
PENDENTE -> ENVIANDO -> CONFIRMADO
                     -> RETENTAR -> PENDENTE
                     -> INCIDENTE
```

Use backoff exponencial com jitter, circuit breaker, limites e `Retry-After` quando
aplicável. Após reinício:

1. verifique integridade do banco;
2. recupere comandos pendentes ou incertos;
3. renove autorização quando possível;
4. busque pedidos com cursor e janela sobreposta;
5. deduplique/aplique em transação;
6. observe estoque remoto;
7. abra incidentes;
8. só então recalcule e publique cotas.

Um timeout depois do envio é resultado incerto: consulte o valor remoto antes de
repetir. Nunca trate uma resposta HTTP isolada como prova permanente de convergência.

Teste energia/processo interrompido antes e depois de cada commit, internet ausente,
token vencido, relógio incorreto, disco cheio, API limitada, eventos duplicados e
fora de ordem, restauração antiga e serviço reiniciado.

## 12. Ativação e desativação do multicanal

Estados globais:

```text
FISICO
MULTICANAL_CONFIGURANDO
MULTICANAL_ATIVO
MULTICANAL_PAUSADO
ENCERRANDO_MULTICANAL
```

No modo físico não execute tarefas externas. Ativar abre assistente de autorização,
importação, vínculos, simulação e piloto.

Desativação após publicação deve oferecer:

- pausa temporária, mantendo última exposição comprometida;
- encerramento seguro: bloquear redistribuições, enviar zero, confirmar, importar
  pedidos pendentes, revogar/remover autorização e voltar a `FISICO`;
- transferência explícita para controle manual, com exportação do estado e aviso de
  responsabilidade.

Não permita um botão que simplesmente mate a sincronização deixando anúncios ativos
sem controle.

## 13. APIs, autorização e segredos

Use somente APIs oficiais. Não use scraping, automação de tela nem senha do Seller
Center. Verifique documentação oficial atual de Shopee e TikTok antes de implementar
endpoints. Registre versão, escopos, limites e estados suportados. Não deduza detalhes
ausentes da documentação autenticada.

O fluxo esperado é autorização oficial no navegador e tokens renováveis. Nunca grave
`app_secret`, partner key, token mestre ou segredo compartilhado no fonte, build,
perfil, log ou teste.

Para a primeira implantação single-tenant, crie interfaces de provisionamento seguro
pós-instalação e cofre DPAPI/Windows. Se callback HTTPS ou webhook público for exigido,
projete um relay mínimo. Não exponha o PC residencial diretamente à internet.

Prepare a fronteira para um broker futuro multicliente. Ele deve aceitar operações
tipadas e autorizadas, jamais assinar URL/payload arbitrário. Use identidade por
instalação, nonce, timestamp, idempotência, rate limit, escopo por loja e revogação.

Não bloqueie toda a implementação local por falta de credenciais. Construa adaptadores
com contratos, mocks/fakes e testes. Pare apenas a ativação real no ponto em que
cadastro/aprovação/credenciais oficiais forem indispensáveis.

## 14. Segurança da build

A build atual usa PyInstaller e bytecode Python pode ser extraído/decompilado. Não
prometa impedir totalmente engenharia reversa.

Faça duas coisas separadas:

1. garanta que desmontar a build não revele segredo capaz de controlar lojas;
2. dificulte cópia da lógica por compilação nativa dos módulos próprios, se viável.

Avalie Nuitka/Cython para os módulos do GiStocker, sem comprometer CustomTkinter,
Matplotlib, Pandas e SQLCipher. Compare funcionamento, tamanho, tempo de build e falso
positivo de antivírus. Mantenha PyInstaller como fallback até a alternativa passar em
todos os testes.

Inclua na esteira:

- varredura de segredos no fonte e artefato;
- SBOM/inventário de dependências;
- hashes do pacote;
- suporte a Authenticode quando houver certificado;
- manifesto de atualização assinado;
- logs sanitizados;
- teste que falha se tokens ou padrões de credencial entrarem no artefato.

Assinatura de código prova origem/integridade; ela não impede decompilação. Não trate
ofuscação como fronteira de segurança.

## 15. Estratégia de implementação

Implemente incrementalmente e mantenha o sistema executável em cada marco:

### Marco A — linha de base e abstração

- rodar testes atuais;
- criar snapshot;
- introduzir interfaces de casos de uso/repositórios sem mudar comportamento;
- adicionar testes de contrato para as operações atuais.

### Marco B — esquema e domínio multicanal

- migrações versionadas;
- eventos, reservas, vínculos, cobertura, políticas, inbox/outbox e incidentes;
- alocador puro e simulador;
- nenhum acesso externo.

### Marco C — processo de serviço e IPC

- serviço/agente executável;
- Named Pipe autenticado;
- interface usa cliente IPC;
- serviço é escritor único;
- modo físico continua funcionando;
- crash/restart/concurrency tests.

### Marco D — instalador e migração

- setup de um clique com UAC;
- ProgramData e ACL;
- instalação/upgrade/rollback/uninstall seguro;
- migração do formato portátil;
- teste em ambiente Windows limpo.

### Marco E — telas e operação local

- Configurações > Integrações;
- ativar/pausar/encerrar;
- vínculos de SKU;
- política/simulador;
- monitor e incidentes;
- origem no histórico;
- pedidos/pendências em modo simulado.

### Marco F — primeiro conector

- somente depois de validar documentação e acesso;
- autorização oficial;
- importação em leitura por pelo menos sete dias;
- 5–10 SKUs simples;
- escrita controlada apenas depois de comparação sem divergências;
- botão de pausa e procedimento de retorno manual.

### Marco G — segundo conector e kits

- repetir sombra/piloto para o segundo canal;
- ativar redistribuição entre canais;
- kits somente depois do fluxo unitário estável.

Não implemente ambos os marketplaces de uma vez. Não ative todos os produtos de uma
vez.

## 16. Testes e critérios de aceite

Além da suíte atual, crie testes significativos para:

- todas as funções atuais no modo físico;
- banco existente migrado sem perda;
- senha correta/incorreta e alteração de senha;
- bloqueio por inatividade atual de 90 minutos;
- serviço como único escritor;
- processo não autorizado tentando acessar o pipe;
- duas saídas simultâneas;
- comandos repetidos;
- crash em cada fronteira de commit;
- alocador para grande faixa de saldos e combinações de canais;
- sorteio persistente sem oscilação;
- produto somente em um canal;
- produto pendente de vínculo;
- dois anúncios no mesmo canal sem duplicar a cota;
- pedido duplicado 100 vezes causando uma única reserva;
- cancelamento parcial e eventos fora de ordem;
- timeout remoto incerto;
- token vencido, rate limit e API indisponível;
- reinício do Windows/serviço;
- disco cheio e relógio incorreto;
- backup/restauração em outra máquina;
- upgrade e rollback do instalador;
- desinstalação preservando dados;
- build sem segredos;
- execução da build em máquina limpa.

Critérios obrigatórios:

- nenhum teste anterior deixa de passar sem justificativa e correção;
- nenhuma operação confirmada é perdida;
- nenhuma repetição duplica uma baixa;
- soma comprometida/exposta não supera o saldo permitido;
- toda divergência é explicável por evento/incidente;
- interface fechada não interrompe multicanal;
- modo físico não acessa a internet;
- nenhuma credencial aparece em logs, traceback, argumentos ou build;
- falha de serviço nunca faz a interface gravar diretamente no banco;
- upgrade não apaga banco, backups ou exportações.

## 17. Regras de trabalho

- Não reescreva tudo de uma vez.
- Faça mudanças pequenas, revisáveis e testadas.
- Preserve compatibilidade e dados existentes.
- Não apague builds, bancos, backups ou auditorias existentes.
- Não use o banco real para testes destrutivos.
- Não solicite minha senha ou tokens pelo chat.
- Não esconda limitações técnicas.
- Não declare sucesso sem executar os testes aplicáveis.
- Se encontrar bug gerado pelas mudanças, corrija e teste novamente.
- Se faltar uma decisão, use o padrão mais conservador que preserve estoque e dados,
  documente a suposição e continue o trabalho independente.
- Se uma etapa depender exclusivamente de aprovação externa/credencial, conclua todo
  o restante e apresente o bloqueio exato.

## 18. Entregáveis finais

Ao concluir cada marco, informe de forma objetiva:

- comportamento implementado;
- arquivos alterados;
- migrações realizadas;
- comandos/testes executados e resultados;
- riscos ou limitações restantes;
- como executar pelo código-fonte;
- como gerar a distribuição;
- caminho exato do instalador/build;
- fluxo de instalação, upgrade, recuperação e desinstalação;
- qualquer ação externa ainda necessária.

Comece auditando o estado real do repositório e confrontando-o com este prompt. Em
seguida, implemente os Marcos A até E com autonomia. Para os Marcos F e G, avance até
o limite permitido pela documentação e por mocks, sem conectar ou alterar lojas reais
sem credenciais oficiais e autorização explícita.
