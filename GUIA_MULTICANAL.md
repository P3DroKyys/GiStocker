# GiStocker 2.0 — prévia local e simulação multicanal

Esta edição implementa a base local e um laboratório isolado. **Não conecta lojas
reais. Não está homologada para distribuição comercial.** O instalador precisa
passar pelo roteiro de Windows limpo abaixo antes do uso por clientes.

## Executar e compilar

1. Use `1_preparar_ambiente.bat` para instalar as dependências fixadas por hash.
2. Use `2_executar.bat`. A interface inicia um agente local sem janela quando ele
   ainda não está disponível. O agente é o dono da conexão SQLCipher.
3. Use `3_gerar_exe.bat` para criar uma distribuição exclusiva em `dist`.
   Havendo `ferramentas/inno/ISCC.exe` ou `ISCC.exe` no PATH, também gera o Setup.
   Nenhuma distribuição anterior é substituída.

O agente de desenvolvimento permanece em segundo plano. No modo físico, fechar ou
bloquear a interface fecha o banco quando não houver outra sessão autorizada.
O agente não deve ser encerrado pelo Gerenciador de Tarefas durante migração/backup.
Uma falha de comunicação nunca faz a interface abrir o banco diretamente.

## Primeiro acesso e preservação dos dados

Uma instalação vazia pede criação de senha e começa no modo físico. O mínimo
continua sendo seis caracteres, com bloqueio de sequências previsíveis; isso não
torna uma senha curta resistente a ataques offline. O bloqueio por inatividade
continua em 90 minutos, validado também pelo agente.

Ao autenticar um banco protegido da versão 1, o serviço cria `dados/cofre_v2` por
publicação de um diretório completo. A cópia nova usa chave aleatória de 256 bits,
protegida por um envelope AES-GCM derivado da senha com scrypt. Produtos.id, códigos,
saldo e histórico são preservados. O arquivo protegido original da versão 1 não
tem seu esquema modificado nessa conversão. Não continue usando simultaneamente
a versão antiga: ela terá uma cópia histórica, não o estoque atualizado.

Um legado ainda sem criptografia usa a conversão anterior auditada, que também
protege arquivos antigos. O instalador recusa importar um banco portátil em texto
puro; primeiro proteja-o na versão portátil.

Há backup automático protegido na primeira abertura de cada dia UTC, em
`dados/backups`, além da exportação manual na aba Relatórios. A extensão é
`.gsbackup`: banco cifrado + envelope de senha, sem a autorização DPAPI da máquina.
Uma senha nova não altera cópias antigas nem revoga envelopes antigos já copiados.

## Laboratório de integrações

Em Configurações > Integrações:

1. **Preparar simulação** cria uma cópia cifrada separada em `cofre_v2/simulacao.db`.
   Alterações posteriores no estoque real não são replicadas nessa cópia.
2. Em Vínculos, crie o catálogo fictício. Ele não foi obtido da Shopee/TikTok.
3. Selecione anúncio e produto e confirme o vínculo. GTIN exato tem precedência
   nas sugestões; nome/marca são apenas ajuda, nunca autorização automática.
4. Se um produto realmente não existir em um canal, selecione-o em Cotas e use
   “não publicado neste canal”. Pendente de vínculo bloqueia a alocação do produto.
5. Confira a política de cada produto. Padrão: 50%, arredondado para cima no físico,
   margem zero. Uma unidade excedente é sorteada entre os canais e o resultado fica
   persistido. Dois anúncios no mesmo canal compartilham a cota, não a duplicam.
6. **Iniciar / retomar ensaio** permite que o worker publique no marketplace
   fictício. Isso não faz chamadas de internet.
7. Em Pedidos, simule pedidos e cancelamentos; indique separação, embalagem, envio,
   retorno à prateleira ou recebimento/inspeção de devolução.
8. Em Monitor, ensaie internet ausente, token vencido, rate limit e timeout após
   envio. Voltar a NORMAL permite recuperação. Nenhum token real é solicitado.

Pausar conserva a exposição conhecida. Encerrar primeiro zera os anúncios fictícios,
confirma e exige resolução de pedidos, reservas e conferências. Encerramento pendente
fica gravado e é retomado após reinício. Preparar vínculos sozinho não publica.

Em integração ativa, o serviço mantém a chave de dados protegida também pela DPAPI
da sua conta Windows. Assim a simulação continua com a interface fechada e pode
retomar depois de reiniciar o agente. Acesso às telas continua exigindo senha.
O processo de desenvolvimento usa a conta do desenvolvedor: não oferece o isolamento
entre contas que a instalação com serviço dedicado pretende fornecer.

## Estoque e pedidos

O saldo em mãos só diminui no envio do pedido; antes disso, a unidade fica reservada
e indisponível para novas vendas. Cancelamento anterior à separação libera a parte
cancelada. Após separar, exige confirmação de retorno. Após enviar, exige recebimento
e inspeção; a devolução recebida permanece em quarentena até aprovação.

Eventos de estoque são imutáveis no banco; desfazer uma operação física gera um
evento compensatório e mantém a marcação histórica usada pelas telas antigas.
Entradas têm origem física; saídas de pedidos fictícios indicam o canal no laboratório.
O histórico do estoque real ganha origem física e está preparado para a origem online
quando um conector real for homologado. Datas históricas locais são preservadas;
os eventos novos registram UTC, sem inventar um horário UTC para registros antigos.

O laboratório contém proteção de exposição e comandos absolutos. Nenhuma arquitetura
local garante ausência total de ruptura durante indisponibilidade prolongada ou
alterações externas. A futura ativação real exige limites de exposição, conciliação
de pedidos e política operacional para o computador desligado.

## Instalar, atualizar e remover

O Setup pede UAC, a conta Windows autorizada e, opcionalmente, uma pasta de dados
portátil. Cria o serviço `GiStocker` com conta virtual `NT SERVICE\GiStocker`, início
automático atrasado e recuperação por reinício. Interface e serviço ficam em uma
pasta versionada dentro de Program Files; dados ficam em ProgramData/GiStocker.
Operadores acessam o Named Pipe e podem ler exportações cifradas, mas não recebem
permissão de escrita no banco. O instalador não pede a senha do estoque.

Na importação portátil, feche interface e agente anteriores. A cópia recusa escritores
em uso, confere hashes e preserva a origem. A integridade criptográfica só pode ser
verificada no primeiro login com a senha correta; não é possível verificá-la antes
sem obter a chave. Importação incompleta não é publicada como um banco válido.

Atualizações usam outro diretório de binários. Se configurar/iniciar/verificar o
serviço falhar, o script tenta restaurar seu caminho anterior. Dados nunca são
removidos. Rollback de binários não reverte um esquema de banco já migrado; uma
versão antiga deve recusar esquema mais novo. Restaure um backup em diretório novo
e confira os saldos antes de qualquer troca de autoridade.

A desinstalação para/remove o serviço e os binários registrados pelo instalador,
preservando ProgramData, backups, exportações e o grupo local de operadores.

## Recuperação portátil

A função `servico.cofre.restaurar(copia, destino, senha)` restaura uma `.gsbackup`
em diretório novo, verifica SQLCipher/esquema e começa com integração desativada.
Não sobrescreve um banco existente. A restauração ainda é uma ferramenta técnica;
um assistente gráfico de recuperação não está entregue nesta prévia.

Nunca envie a senha pelo chat ou por argumentos de terminal. Na recuperação técnica,
leia a senha com `getpass.getpass()` e passe-a diretamente à função em memória.
Não copie somente `estoque.db` de um banco em uso: o WAL pode conter dados confirmados.

## Homologação pendente em máquina limpa

O ambiente atual não possui Windows Sandbox disponível. Antes de distribuir:

- instalar em Windows 10/11 x64 limpo, com usuário comum e UAC por outra conta;
- verificar conta virtual, ACL, DPAPI e início após reiniciar o Windows;
- confirmar que o usuário autorizado acessa imediatamente o pipe e que outro não;
- importar uma cópia protegida portátil com WAL, conferir senha, saldos e IDs;
- interromper instalação/upgrade e verificar rollback, atalhos e dados;
- confirmar que desinstalar/reinstalar preserva o acesso aos dados;
- validar exportação/recuperação em outro computador e dependências nativas;
- assinar executável/Setup com certificado do responsável antes de distribuir.

## Limites conhecidos e próximos marcos

Shopee/TikTok reais, OAuth/autorização, cursores reais, sete dias de sombra, piloto de
5–10 SKUs e kits não estão ativados. O schema reserva estruturas para esses marcos,
mas tabelas reservadas não equivalem a funcionalidades já concluídas.
Devolução adicional após concluir a inspeção de uma mesma linha abre pendência de
conciliação; esta prévia não automatiza múltiplos ciclos de devolução parcial.

Não há assinatura Authenticode nem compilação nativa completa. PyInstaller empacota,
mas não impede engenharia reversa. A segurança depende de não embutir segredos, de
criptografia e de controles do Windows. Malware com acesso administrativo ou à conta
do serviço pode comprometer o processo: esta edição não promete “blindagem total”.

As referências oficiais e os limites de verificação estão no relatório técnico.
