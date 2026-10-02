# GiStocker 1.2.0 — proteção dos dados locais

Esta versão vincula o acesso à descriptografia do banco. A tela de senha não é
mais o único bloqueio: pular uma verificação visual não revela o conteúdo de um
banco protegido. Não há senha padrão, chave embutida, senha mestra ou recuperação
por exclusão de configurações.

Na versão 1.1.1, o mínimo foi ajustado para seis caracteres e a inatividade para
90 minutos. Senhas existentes continuam válidas. Uma senha mais longa continua
recomendada contra tentativas de adivinhação em cópias do banco criptografado.

A versão 1.2.0 acrescenta pesquisa local com RapidFuzz. Seu índice fica na memória
da sessão e é descartado ao fechar o banco; não cria índice de produtos em disco
nem transmite consultas para um serviço externo. As regras de acesso permanecem.

## Ativação na instalação que contém seu estoque

1. Feche todas as versões do GiStocker que estejam usando esses dados.
2. Pelo código-fonte, execute `1_preparar_ambiente.bat` para atualizar as bibliotecas
   e depois `2_executar.bat`. O ambiente desta versão exige Python 3.14 de 64 bits.
   A build pronta para Windows x64 já inclui o ambiente e não exige Python.
3. Em uma instalação antiga, informe a senha atual e uma nova frase de senha de
   6 a 128 caracteres, duas vezes. Em uma instalação nova, crie a senha.
   Escolha algo pessoal e difícil de adivinhar; o comprimento sozinho não garante isso.
4. Guarde a senha em local seguro. **Esquecê-la impede recuperar os dados.**
   Não existe um arquivo que possa ser apagado para redefini-la.
5. Aguarde a conclusão. O aplicativo confere o banco convertido e cria uma cópia
   criptografada antes de substituir o banco antigo. A tela principal só é liberada
   depois que as cópias antigas da instalação também são protegidas.

Para atualizar uma build existente, com o programa fechado, substitua o executável
e a pasta `_internal` pelo conteúdo da nova distribuição, mantendo as pastas
`dados` e `exportacoes` da instalação correta. Não use a pasta de dados de outra
instalação por engano. Copiar apenas o executável não atualiza as bibliotecas.

**Os dados reais não são convertidos pela geração da build ou pelos testes.**
A conversão acontece no primeiro acesso autorizado à instalação, com a senha
escolhida localmente pelo proprietário. Não é necessário enviar a senha a ninguém.

## O que fica protegido

| Item | Comportamento |
| --- | --- |
| `dados/estoque.db` | Banco SQLCipher; a senha é necessária para abrir e consultar. |
| WAL e journal de transações | Páginas protegidas pelo mesmo mecanismo do banco. |
| `dados/backups/*.db` novos | Cópias completas e criptografadas, com verificação de integridade. |
| Exportação de relatórios | Gera uma cópia protegida `.db` com estoque e histórico. |
| Backups `.db` antigos em texto puro | Preservados como contêineres criptografados `.gsa`. |
| CSVs antigos em `exportacoes` | Preservados em `.gsa`, incluindo subpastas da instalação. |
| Configuração de senha e logs antigos | Preservados em `.gsa` após o banco ter sido autenticado. |
| `dados/aparencia.json` | Apenas a preferência claro/escuro; não contém chave nem senha. |
| `dados/.sessao.lock` | Trava de uma instância; não contém dados ou credenciais. |

A exportação em CSV sem proteção fica desabilitada nas sessões criptografadas.
Um CSV comum poderia ser lido sem senha por qualquer programa com acesso à pasta.
Os arquivos `.gsa` conservam os bytes originais; o original só é removido depois
de uma leitura de verificação com SHA-256. Eles não devem ser renomeados para
`estoque.db`. A função `models.seguranca.ler_arquivo_protegido` recupera seu conteúdo
em memória mediante senha, sem criar automaticamente uma cópia em texto puro.
Não há interface de restauração de `.gsa` nesta versão; mantenha os novos backups
`.db` para a recuperação normal do estoque.

Os mecanismos de páginas, autenticação e armazenamento temporário seguem o
[projeto do SQLCipher](https://www.zetetic.net/sqlcipher/design/). A implementação
usa AES-256, HMAC-SHA512, sal aleatório e PBKDF2-HMAC-SHA512 com 256.000 iterações.
Os arquivos temporários de consultas ficam em memória. As chaves não são salvas
em configurações, código-fonte ou no executável.

## Uso diário e troca de senha

- **Ctrl+L** ou **Configurações → Bloquear agora** fecha o banco e remove as telas
  da sessão. Para continuar, é necessário descriptografar o banco novamente.
- Na versão 1.1.1, 90 minutos sem uso também bloqueiam a sessão. Uma ação após esse intervalo
  não deve simplesmente renovar a sessão que já expirou.
- Trocar a senha exige a senha atual. A alteração recriptografa o banco principal,
  e a nova chave é verificada antes de informar sucesso.
- Backups anteriores continuam exigindo a senha que tinham quando foram criados.
  Uma troca de senha não pode revogar cópias que alguém já guardou fora do programa.
- Há atraso progressivo após falhas de acesso. A defesa contra tentativas feitas
  diretamente em uma cópia do arquivo depende da derivação criptográfica e da
  qualidade da senha; um contador de tentativas local não impede ataques offline.

## Recuperação e falhas de energia

As gravações continuam transacionais, com WAL e `synchronous=FULL`. Uma operação
não confirmada deve ser revertida; uma operação confirmada deve permanecer.
Isso não substitui backups: falha física do disco, defeito no armazenamento ou
um sistema operacional comprometido podem destruir arquivos.

Para restaurar um **backup protegido `.db`**:

1. Feche o software e preserve a pasta `dados` atual inteira em outro nome/local,
   incluindo eventuais arquivos WAL/SHM. Não misture arquivos de bases diferentes.
2. Prepare uma pasta `dados` limpa e copie o backup escolhido para `dados/estoque.db`.
3. Abra a versão atualizada e informe a senha usada na criação daquele backup.
4. Confira os produtos e as movimentações antes de descartar qualquer cópia antiga.

Os backups são snapshots na abertura/desbloqueio e na exportação protegida;
não são uma cópia externa contínua de cada movimentação. Mantenha também uma cópia
fora desse computador, preferencialmente desconectada quando não estiver em uso.

Na migração, arquivo em uso, erro de integridade ou falha no backup impedem a
substituição do original. Se o banco for convertido, mas uma falha impedir proteger
um CSV/backup antigo, a sessão permanece bloqueada: a próxima tentativa usa a
**nova senha** e retoma a proteção das cópias pendentes.

## Limites de segurança que precisam ser considerados

A criptografia protege os dados em repouso de quem não possui a senha. Ela não
torna um computador comprometido confiável. Um administrador ou malware no Windows
pode apagar arquivos, substituir o executável para capturar uma senha futura,
registrar teclas, capturar a tela ou ler dados enquanto a sessão está desbloqueada.
Também não há garantia de detectar a substituição integral por um backup antigo
válido; isso exigiria uma referência confiável fora desses arquivos locais.

Use conta Windows sem privilégios administrativos no dia a dia, bloqueio do
Windows, atualizações, proteção antimalware e criptografia do disco (BitLocker
ou equivalente disponível no equipamento). Instalação com permissões restritas
e assinatura digital verificável são as próximas camadas de proteção do programa.
O manifesto `SHA256.json` serve para conferir a transferência da build; não é
assinatura digital e não resiste a um invasor que possa substituí-lo junto com ela.

A exclusão de originais após conversão não garante apagar vestígios em SSDs,
histórico de arquivos, snapshots ou backups externos. A migração trata os arquivos
da **instalação aberta**. Outras pastas, pendrives, builds antigas e cópias anteriores
precisam ser protegidos ou descontinuados separadamente, após conferir os dados.

## Dependências e manutenção

O motor desta entrega é SQLCipher **4.18.0**, SQLite **3.53.4** e OpenSSL **3.5.9 LTS**.
A wheel Windows do `sqlcipher3` foi compilada especificamente para este projeto,
com versão `0.6.2+gistocker.sqlcipher418`. Ela usa armazenamento temporário somente
em memória, modo defensivo por padrão, esquema não confiável e não inclui suporte
a carregar extensões nativas, FTS ou RTree. Os avisos de licença estão em `licencas`.

As versões e hashes do runtime ficam em `requirements.lock`; a wheel validada está
em `vendor`. Não a substitua automaticamente pela wheel genérica antiga do PyPI.
O aplicativo verifica os requisitos do motor antes de abrir uma sessão.

Referências do fornecedor: [releases SQLCipher](https://github.com/sqlcipher/sqlcipher/releases),
[releases OpenSSL](https://openssl-library.org/source/),
[recomendações de armazenamento criptográfico da OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html).
Os resultados, o escopo dos testes e as limitações da auditoria estão em
`auditoria/SEGURANCA_1_1_0.md` no código-fonte. Nenhuma suíte demonstra ausência
absoluta de falhas futuras; as dependências precisam continuar recebendo manutenção.
