# Gestão de dados — Configurações

Abra a engrenagem **Configurações → Gestão de dados**. As operações atuam no
banco principal da instalação aberta. Encerre o laboratório de integrações antes
de executá-las; o banco separado da simulação não faz parte deste backup.

## Backup completo em JSON

**Exportar backup do sistema** solicita a senha atual e confirmação do aviso:

> Atenção: O arquivo exportado conterá todos os seus dados sem criptografia. Guarde-o em local seguro.

O arquivo `.gsdados.json` contém todas as tabelas do banco principal, incluindo
produtos, códigos, movimentações, eventos, vínculos e contadores de IDs. Não contém
a senha, a chave SQLCipher, o envelope de acesso nem a preferência de tema. Não é
um arquivo SQL executável. A exportação lê um único snapshot consistente do banco
e publica o arquivo apenas depois de concluir a gravação.

**Restaurar backup do sistema** substitui integralmente esses dados. Confirme a
senha da instalação de destino, mesmo se o backup veio de outro computador. A
senha e a chave atuais são mantidas: os registros são gravados através da conexão
SQLCipher já autenticada. O arquivo JSON precisa ser da versão de formato/esquema
compatível; `.db`, `.gsbackup` e `.gsa` não são aceitos por este botão.

Antes de substituir, o agente valida o arquivo em um banco temporário em memória
(colunas, tipos, restrições, chaves estrangeiras, integridade e saldos do livro de
eventos). Depois, cria um snapshot **criptografado** `.gsbackup` em
`dados/backups` — ou na pasta de dados de ProgramData quando instalado. O caminho
é informado ao concluir. Falha na validação ou no snapshot impede a substituição.
Todos os deletes/inserts e a recriação dos gatilhos ocorrem em uma transação.

Os snapshots `.gsbackup` continuam usando o mecanismo de restauração protegida
de `servico.cofre.restaurar`, em diretório novo, e a senha da época da cópia. Este
painel restaura somente os arquivos JSON que ele exporta.

## Planilha de produtos (Excel)

**Baixar planilha modelo** gera `modelo_produtos.xlsx` com três abas:

- **Produtos**: linha de títulos fixa e colorida (obrigatórias com `*` em cor forte,
  opcionais em cor clara), uma linha por produto a partir da linha 2. Cada célula
  mostra uma orientação ao ser selecionada. A coluna de código já está formatada
  como Texto, o que preserva zeros à esquerda. **Marca** e **Categoria** são listas
  suspensas com os valores cadastrados no programa. Quantidade aceita só inteiro
  ≥ 0, e preço/custo só valores ≥ 0. Valores colados de outra planilha passam por
  cima da validação do Excel, mas são validados de novo na importação.
- **Instruções**: passo a passo, regras por coluna e uma linha de exemplo (esta
  aba não é importada).
- **Listas**: oculta; origem das listas suspensas.

| Coluna (título no Excel / cabeçalho CSV) | Regra |
| --- | --- |
| Código de barras (GTIN) / `codigo` | Obrigatório. GTIN textual válido de 8, 12, 13 ou 14 dígitos, incluindo DV GS1. Célula numérica é recusada, porque zeros à esquerda já perdidos não podem ser recuperados. |
| Nome do produto / `nome` | Obrigatório, até 500 caracteres. |
| Marca / `marca` | Obrigatório. Uma das marcas do cadastro (maiúsculas e acentos são indiferentes). |
| Categoria / `categoria` | Obrigatório. Uma das categorias do cadastro (maiúsculas e acentos são indiferentes). |
| Quantidade a adicionar / `quantidade` | Inteiro não negativo. **Vazio vale 0.** É a quantidade **a adicionar**, não o saldo final. |
| Preço de venda (R$) / `preco_venda_base` | Opcional. Preenchido, substitui o preço de venda. Vazio: produto novo fica com 0, existente mantém o preço atual. |
| Custo unitário (R$) / `custo_unitario` | Opcional. Com entrada de estoque, compõe o custo médio ponderado. Com quantidade zero, substitui o custo atual e gera um Ajuste no histórico. Vazio: produto novo fica com 0, existente mantém o custo e nenhum registro de histórico é criado. |

São aceitos `.xlsx` (é lida a aba **Produtos** ou, sem ela, a primeira aba) e,
como alternativa, **CSV UTF-8** com separador `;` ou `,`. No `.xlsx`, números
digitados como número são lidos com o valor exato da célula. No CSV, e em células
de texto, valores monetários usam vírgula decimal e ponto de milhar: `1.500` vale
1500 e `1.234,56` vale 1234,56. Também são aceitos ponto decimal com 1, 2 ou 4
casas (`10.5`, `12.50`, `10.1234`) e o prefixo `R$`. Para três casas decimais, use
vírgula (`1,234`). Notação científica, sublinhados, infinitos e o formato
`1,234.56` são rejeitados. As quantidades não aceitam casas decimais; o ponto de
milhar é aceito, como nas telas. A linha de títulos pode usar os títulos do Excel
ou os cabeçalhos do CSV. Um `.xlsx` acima de 256 MiB descompactado é recusado.

O sistema encontra produtos pelo GTIN e atualiza o produto vinculado. Um GTIN novo
cria outro produto; o importador não tenta mesclar produtos por semelhança de nome.
Múltiplos GTINs podem apontar ao mesmo produto já existente, mas apenas uma linha
válida por produto é aplicada em cada arquivo: repetições são relatadas e ignoradas.
Nome, marca e categoria são atualizados nas linhas válidas. Preços vazios preservam
os valores atuais; para novos produtos, ficam em zero. Os demais produtos não são
apagados. Quantidades e custos entram no histórico com origem física e ID do lote.

Cada linha tem um savepoint dentro da transação do lote. Erros de conteúdo ficam
no relatório final com o número da linha; falhas críticas de banco/disco abortam
todo o lote. O relatório pode ser salvo em texto. O comando Desfazer existente
continua tratando a última movimentação de estoque/custo; não reverte em bloco
nomes/preços nem a importação inteira. Use backup antes de uma atualização ampla.

## Execução e limites

- Até 64 MiB por arquivo e 100.000 linhas por planilha. Arquivos maiores são rejeitados
  explicitamente, sem truncamento; o backup protegido existente continua disponível.
- O modal segue o tema claro/escuro. A navegação e o fechamento normal ficam
  bloqueados durante o trabalho; o processamento de arquivos roda fora da thread Tk.
- O progresso é calculado por bytes transferidos ou registros processados. Cada
  etapa informa seu próprio percentual; não é uma estimativa de tempo restante.
- Ao concluir importação/restauração, o acesso é bloqueado para descartar todas as
  telas e consultas antigas. Desbloqueie com a mesma senha para continuar.
- O agente continua sendo o único escritor. Enquanto mantém uma transação entre
  lotes, ele bloqueia outras consultas e alterações do sistema. Um minuto sem
  contato encerra o job e reverte uma transação ainda não confirmada; um novo
  desbloqueio após o fechamento inesperado da interface também reverte o job órfão.
- Uma repetição automática imediata conserva o identificador do lote, e o recibo
  transacional impede duplicação. Cada nova ação do usuário, inclusive selecionar
  novamente o mesmo arquivo após erro, recebe outro identificador e soma estoque.
  Se a comunicação cair nas duas tentativas, confira o histórico antes de iniciar
  outra importação: o lote anterior pode ter sido confirmado.
- O banco permanece criptografado. JSONs exportados, CSVs preenchidos e relatórios
  de importação ficam sob a responsabilidade do usuário e não são criptografados.
  Nada é enviado à internet. Não publique esses arquivos no GitHub.

## Arquitetura e testes

`gestao/arquivos.py`: formatos de arquivo e gravação atômica.
`gestao/backup.py`: exportação e restauração, schema fechado, integração com cofre.
`gestao/planilha.py`: modelo `.xlsx` (openpyxl), leitura de `.xlsx`/CSV, validações e upsert transacional.
`servico/gestao.py`: autenticação, jobs, exclusão mútua, recibos e rollback.
`servico/transferencia.py`: transporte em blocos e journal, sem widgets.
`views/gestao_dados.py`: painel e modal; `view_configuracoes.py` somente injeta o painel.

Testes isolados (executar na raiz do projeto, com ambiente preparado):

```powershell
.\.venv\Scripts\python.exe -m unittest auditoria.verificar_gestao_dados auditoria.verificar_gestao_ipc auditoria.smoke_gestao_dados -v
```

Usam bases temporárias e incluem rollback após falha, encerramento brusco do agente,
resposta perdida após commit, senha errada, corrupção/alteração de arquivos,
importação parcial por linha, integridade SQLCipher, temas e atualização das telas.
Não simulam falha física real de disco ou desligamento elétrico do computador.
