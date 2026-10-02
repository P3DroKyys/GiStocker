# Auditoria de segurança — GiStocker 1.1.0

Data: 01/10/2026. Escopo: aplicação local Windows, autenticação, arquivos de dados,
migração, dependências, sessão, backups e regressões funcionais. Testes realizados
com bancos fictícios isolados. O estoque real não foi convertido ou modificado.

## Resultado e correções

| Problema identificado | Correção implementada |
| --- | --- |
| A senha protegia a interface, enquanto o estoque SQLite permanecia legível e editável por outros programas. | SQLCipher: a chave fornecida pelo usuário é necessária para consultar as páginas do banco. Os controladores são criados somente após a abertura autenticada. |
| Configuração local de senha e senha inicial podiam ser confundidas com uma barreira de proteção do arquivo. | Sem senha padrão, chave embutida ou redefinição pela exclusão de preferências. A configuração antiga serve somente para autorizar a conversão do banco que já estava em texto puro. |
| Backups, CSVs e registros antigos poderiam revelar informações mesmo após proteger o banco principal. | Backups e exportações novos criptografados. Arquivos antigos da instalação são preservados em `.gsa`, com leitura de verificação antes de remover o original. Logs novos não registram mensagens de exceção, SQL, senhas ou valores dos produtos. |
| Uma sessão deixada aberta continuava oferecendo acesso ao estoque. | Bloqueio manual/Ctrl+L e após dez minutos de inatividade, fechamento da conexão e destruição das telas e diálogos. |
| Conversão, troca de senha e encerramento abrupto poderiam introduzir perda de dados ou sessão em estado incerto. | Migração com verificação e backup antes da substituição; reabertura de validação; recuperação de conversão parcial; fechamento da sessão em falha de recriptografia; testes por encerramento de subprocessos. |
| A wheel pública avaliada usava um motor anterior e apresentou encerramento nativo com falhas de autenticação, logging e proteção de memória. | Wheel específica a partir das fontes oficiais: SQLCipher 4.18.0, SQLite 3.53.4 e OpenSSL 3.5.9 LTS. Teste isolado com quarenta senhas incorretas, logging ativo e proteção de memória passa sem encerrar o processo. |
| Callbacks de widgets e gráficos podiam continuar depois do bloqueio, inclusive durante um diálogo. | Cancelamento de tarefas da árvore de widgets e proteção dos callbacks que retornam de mensagens; integração com widgets reais sem erros Tcl. |

Criptografia usa os mecanismos do SQLCipher, sem cifra caseira: AES-256,
PBKDF2-HMAC-SHA512 com 256.000 iterações e autenticação de páginas HMAC-SHA512.
Temporários de consultas ficam em memória. Extensões nativas dinâmicas, FTS e
RTree não estão habilitados na compilação. Modo defensivo é o padrão.
A senha exige de 15 a 128 caracteres e rejeita algumas sequências previsíveis;
essa validação não é uma garantia de entropia de qualquer frase escolhida.

## Evidência de testes

| Verificação | Resultado | Registro |
| --- | --- | --- |
| Suíte completa de segurança e regressão | **183 testes aprovados**, 32,827 s | `testes_seguranca_regressao.txt` |
| Integração Tk/CustomTkinter com widgets reais | **4 testes aprovados**, 6,574 s; sem erros Tcl | `interface_seguranca.txt` |
| Dependências Python instaladas | Nenhuma vulnerabilidade conhecida reportada nas **59 dependências consultadas**; uma versão local não consultável | `dependencias_seguranca_final.json` / `.txt` |
| Resolução do runtime fixado e hashes | Simulação de instalação aprovada, incluindo wheel local | `reprodutibilidade_runtime.txt` |
| Motor nativo e parâmetros criptográficos | Versões, opções e SHA-256 registrados | `motor_criptografico.json` |
| Build Windows 1.1.0 | Gerada; 2.051 arquivos conferidos pelo manifesto; motor nativo idêntico ao testado; sem dados reais ou ferramentas de auditoria | `build_seguranca.log`, `distribuicao_seguranca.json` |
| Inicialização do executável | Processo abriu a janela GiStocker e carregou SQLCipher; sem erro ou banco criado antes da senha; cópia isolada encerrada e removida | `startup_build_seguranca.json` |

Os 183 testes incluem fluxos de estoque, GTIN, concorrência, transações, custo
médio, desfazer, consultas, gráficos, construção do pacote e segurança. Dezenove
regressões funcionais rodam novamente sobre arquivos SQLCipher reais, além dos
testes legados em bases descartáveis. Os quatro testes de interface exercitam
criação de senha, login correto/incorreto, cadastro, Admin, indicadores, tema,
troca de senha, bloqueio e retomada de migração parcial.

As tentativas de acesso verificadas incluem SQLite comum lendo banco protegido,
senha incorreta, preferências apagadas/forjadas, chamada direta para liberar a
interface sem banco autenticado, alteração de página cifrada, injeção na senha,
esquema legado com trigger inesperado e segunda instância. Também foram
verificados os arquivos de banco, WAL, backup e exportação para ausência de um
marcador de dados fictícios em texto puro. Essa busca é uma verificação adicional,
não uma prova matemática da criptografia.

Falhas simuladas: gravação/backup/substituição de arquivo, proteção incompleta de
cópias antigas, troca de chave, encerramento antes/depois de commit e interrupção
durante recriptografia de um banco com 1.200 produtos. Após interrupção de rekey,
aceita-se a chave antiga ou nova, mas são exigidos todos os dados e integridade.
Isso simula encerramento de processo, não perda física real de energia do disco.

O `pip-audit` não consegue consultar `sqlcipher3==0.6.2+gistocker.sqlcipher418`,
pois a versão local não existe no PyPI. Ele também não constitui auditoria de
todas as bibliotecas nativas. A procedência, versões e opções do motor foram
conferidas separadamente; os arquivos estão em `native_build`. Ferramentas de
auditoria/compilação presentes na venv não são dependências do aplicativo final.
Ausência de alertas publicados não demonstra ausência de vulnerabilidades.

Comandos para repetir a verificação, a partir da raiz do projeto:

```powershell
$env:MPLCONFIGDIR = (Join-Path (Get-Location) 'auditoria\.mplconfig')
.\.venv\Scripts\python.exe -B -m unittest discover -s auditoria -p 'verificar*.py'
.\.venv\Scripts\python.exe -B auditoria/smoke_interface_upgrade.py
.\.venv\Scripts\python.exe -m pip check
```

## Estado dos dados reais e ativação

**A instalação real ainda precisa passar pela conversão na tela de acesso.**
Feche todas as versões antigas. Abra o fonte atualizado ou atualize a instalação
correta com executável e `_internal` da nova build. Informe a senha atual e defina
a nova frase de senha localmente. Não há recuperação sem essa senha.

A inspeção de caminhos encontrou cópias em:

- `C:\Software Gestor\CODIGO\estoque_cosmeticos\dados` e `exportacoes`;
- `C:\Software Gestor\BUILD\GestorEstoque\dados`;
- `C:\Software Gestor\CODIGO\estoque_cosmeticos\dist\GiStocker_20261001_112256_272436de1e74\GestorEstoque\dados`.

Uma distribuição anterior `GiStocker_20261001_003947_twmiqkkq` não permitiu listar
sua pasta de dados nesta sessão. Essas outras instalações não foram alteradas.
Converter uma delas não protege automaticamente as demais. Preserve/confronte
as cópias corretas antes de decidir sobre sua descontinuação; não misture arquivos
WAL/SHM ou dados de instalações distintas. Não se leu o conteúdo comercial para
realizar os testes.

O fonte anterior à alteração foi preservado no arquivo
`fonte_antes_seguranca_20261001_121418.zip` (sem dados de estoque).
Arquivos de testes anteriores com falhas são registros históricos; os resultados
válidos desta entrega são os explicitamente indicados na tabela acima.

Build entregue:
`dist/GiStocker_20261001_131641_09507d5c1eac/GestorEstoque/GestorEstoque.exe`.
Distribua a pasta `GestorEstoque` inteira, incluindo `_internal` e licenças.
SHA-256 do executável:
`e8d723d5db4b0edd38628246d37cca0e37edc5a285b7162a1129cfb911eebd92`.
O pacote contém aproximadamente 124 MB. A verificação do executável compilado
cobriu composição e inicialização; os fluxos completos de autenticação/estoque
foram exercitados pelos testes no fonte com o mesmo motor nativo. Não se afirma
que toda operação foi automatizada dentro do `.exe` ou testada em outro computador.
O script `validar_distribuicao.py` repete a conferência de arquivos/módulos/hashes.

## Limites e operação

- Quem possui a senha pode abrir o banco com outro programa compatível com
  SQLCipher. Criptografia por senha não consegue exigir exclusivamente esta UI.
- Um administrador do Windows ou malware na sessão pode capturar teclas/telas,
  ler memória, substituir o programa para capturar a próxima senha ou apagar
  arquivos. Empacotar Python não impede inspeção ou modificação do executável.
- Não há autoridade externa para detectar substituição integral por um backup
  antigo válido. Exclusão, rollback e sabotagem de disponibilidade não são
  resolvidos somente pela criptografia local.
- Trocar a senha protege o banco principal com a nova chave. Cópias anteriores
  continuam abrindo com a senha da época. Isso inclui os contêineres `.gsa`.
- O atraso de login é uma limitação da interface, não um bloqueio irrevogável
  contra força bruta offline. Frase de senha forte e KDF são indispensáveis.
- Remover um original convertido não garante apagar vestígios em SSDs, snapshots,
  backups do Windows ou cópias externas. Proteção do sistema/disco complementa a
  aplicação. Não foram alteradas permissões globais, antivírus ou BitLocker.
- CSV em texto puro está desabilitado. A exportação agora é `.db` criptografada.
  `.gsa` preserva arquivos antigos e não é um backup de estoque diretamente
  restaurável; não existe UI de restauração desse contêiner nesta versão.
- Os backups são snapshots, sem replicação contínua externa. Mantenha cópias
  protegidas fora da máquina. A build não possui assinatura Authenticode;
  `SHA256.json` verifica cópia/transferência, não autenticidade contra um invasor.

Instruções de uso e recuperação: [SEGURANCA.md](../SEGURANCA.md).
Recompilação do motor: [README_COMPILACAO.md](native_build/README_COMPILACAO.md).

Fontes técnicas: [SQLCipher design](https://www.zetetic.net/sqlcipher/design/),
[API SQLCipher](https://www.zetetic.net/sqlcipher/sqlcipher-api/),
[releases SQLCipher](https://github.com/sqlcipher/sqlcipher/releases),
[SQLite security](https://www.sqlite.org/cves.html),
[releases OpenSSL](https://openssl-library.org/source/),
[OWASP armazenamento criptográfico](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html).
