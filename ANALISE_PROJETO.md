# Análise do projeto — 30/09/2026

## Parecer

A estrutura é coerente para um gestor local de estoque. Os fluxos comuns do núcleo passaram nos testes, mas existem defeitos reproduzidos e cuidados com os dados que devem ser resolvidos antes de considerar o sistema plenamente validado. Esta auditoria não alterou o código de produção nem os bancos originais.

Foram lidos todos os módulos Python próprios da aplicação, README, configurações do VSCode, dependências, scripts de execução/empacotamento e o spec existente. Bibliotecas de terceiros, arquivos binários e ZIPs de distribuição não foram auditados internamente. Não foi feita pesquisa externa ou auditoria de vulnerabilidades de dependências.

## Estrutura e fluxo

- `main.py`: configura o tema, abre o banco, instancia os controladores e a janela principal.
- `config.py`: caminhos, PIN, marcas, categorias, aparência e parâmetros das regras de estoque.
- `models/models.py`: SQLite; tabelas Produtos, Codigos_Barras e Logs_Movimentacao; repositórios e transações.
- `controllers/controllers.py`: cadastro, vínculo de códigos, entrada, saída, ajuste, desfazer, indicadores e CSV.
- `utils/texto.py`: conversão de números, formatação, normalização e sugestões de marca/categoria.
- `views/main_view.py`: navegação, atalhos F1–F5 e tema.
- `views/view_operacao.py`: leitor de código, quantidade/custo, modo rápido e desfazer.
- `views/view_cadastro.py`: novo produto e múltiplos códigos.
- `views/view_dashboard.py`: indicadores, gráficos, ranking e estoque parado.
- `views/view_relatorios.py`: busca, histórico e exportação.
- `views/view_admin.py`: PIN, ajustes de estoque/custo e gestão de códigos.
- `views/componentes.py`: tabelas, cartões, listas, cores e diálogos compartilhados.

O leitor é tratado como teclado: código seguido de Enter. Vários códigos resolvem para um único produto. Entradas recalculam o custo médio; saídas mantêm o custo e bloqueiam saldo negativo pela configuração atual. O desfazer restaura o estado anterior do último log não cancelado, inclusive ajustes e entradas do cadastro. Produtos não são excluídos pelo desfazer.

## Onde estão os dados e executáveis

| Local | Situação observada |
|---|---|
| `C:\Software Gestor\CODIGO\estoque_cosmeticos` | Fonte que deve receber futuras alterações; `.venv` funcional nesta máquina |
| `C:\Software Gestor\CODIGO\estoque_cosmeticos\dados` | Sem banco na inspeção; a execução pelo fonte criará um banco aqui |
| `C:\Software Gestor\BUILD\GestorEstoque` | Executável e banco com 1 produto, 0 códigos e 1 movimentação |
| `C:\Software Gestor\CODIGO\estoque_cosmeticos\dist\GestorEstoque` | Outro executável; banco sem produtos ou movimentações, com arquivos WAL/SHM |

Os executáveis de BUILD e dist têm hashes SHA-256 diferentes. Não foi comprovado qual corresponde exatamente ao fonte atual. Alterar o fonte não atualiza nenhum executável automaticamente; `3_gerar_exe.bat` gera em dist e não atualiza BUILD.

Os dois bancos foram copiados com seus arquivos auxiliares para diretórios temporários, e apenas as cópias foram abertas para inspeção. Tamanho/data dos arquivos não mudaram durante a cópia. Ambos retornaram `integrity_check = ok`, nenhuma violação de chave estrangeira e nenhuma divergência entre saldo e soma dos logs válidos. Isso verifica o estado observado, não substitui um backup consistente via API SQLite quando há gravações simultâneas.

## Verificações realizadas

- Python 3.14.3 do ambiente virtual; pandas 3.0.6, matplotlib 3.11.2 e customtkinter 6.0.0 importados com sucesso.
- `pip check`: sem dependências quebradas.
- Análise sintática dos módulos próprios e importação de main e de todas as telas: aprovadas.
- 19 testes isolados em `auditoria/verificar.py`: 13 aprovados e 6 falhas esperadas que reproduzem defeitos conhecidos.
- Aprovados: cadastro com vários códigos, bloqueio de código duplicado, custo ponderado, entrada sem custo, saída e bloqueio de saldo negativo, validações comuns, desfazer, rollback ao falhar o log, busca sem acentos, vínculo/desvínculo, KPIs/rankings/cancelamentos, estoque parado e exportações vazias/preenchidas.

Executar novamente, na pasta do fonte, pelo PowerShell:

```powershell
& .venv/Scripts/python.exe -B auditoria/verificar.py
```

`OK (expected failures=6)` NÃO significa ausência de defeitos: os seis testes marcados com `expectedFailure` falham como previsto. Ao corrigir cada defeito, remover essa marca e exigir aprovação normal do teste correspondente.

Não foram executados testes visuais interativos, leitura com equipamento USB real, empacotamento novo ou abertura dos executáveis. Portanto, layout, foco, diálogos, operação completa pela interface e distribuição permanecem sem validação funcional direta. Houve aviso de acesso ao cache padrão do matplotlib na execução restrita; a importação posterior com cache temporário explícito funcionou. O log já existente em dist registra falha ao carregar a fonte gráfica do customtkinter; não foi verificado se o aviso ainda ocorre ao abrir esse executável.

## Defeitos reproduzidos e prioridades

### Alta: perda de movimentação com duas instâncias

Em `controllers/controllers.py:235` e `:264`, o produto é lido e o saldo é calculado antes de `with self.bd.transacao()`. Duas instâncias podem ler o mesmo saldo e a última gravação sobrescrever o resultado da anterior, embora ambos os logs sejam salvos. O teste intercala duas conexões: saldo 10, entradas +2 e +3, resultado 13 em vez de 15. A mesma estrutura de leitura anterior à transação aparece em ajuste e desfazer. Leitura, validação e gravação devem ocorrer sob a mesma transação; alternativamente, impedir mais de uma instância, conforme a necessidade do produto.

### Alta: alteração involuntária do custo no Admin

`views/view_admin.py:204` preenche o campo de custo com apenas duas casas decimais, mas o cálculo usa quatro. `_aplicar_ajuste` envia esse campo mesmo quando só a quantidade mudou. Custo 10,1234 passa para 10,12 ao ajustar o estoque. Preservar a precisão no campo ou enviar somente valores efetivamente editados.

### Média: valores monetários não finitos

`utils/texto.py:97` aceita `inf`, `nan` e entradas como `1e309`; `controllers/controllers.py:92` verifica somente se o valor é negativo. `inf` é gravado como custo; `nan` chega ao SQLite e provoca IntegrityError, que os formulários não tratam como ErroNegocio. Validar finitude e limites antes de gravar. Há dois testes separados para infinito e NaN.

### Média: exportação sobrescrita

`controllers/controllers.py:428` usa carimbo de data com precisão de minuto. Duas exportações no mesmo minuto escrevem nos mesmos arquivos e substituem a anterior. Usar nomes únicos e evitar sobrescrita silenciosa.

### Baixa: sugestão de categoria incorreta

Em `config.py:113`, o termo genérico “tônico” vem antes de “tônico capilar” (`:135`). Como a primeira correspondência vence, “Tônico capilar” é classificado como Skincare. Priorizar termos específicos.

## Pontos de manutenção e proteção dos dados

1. **Backup e migração:** o README orienta apagar o banco após mudar o modelo. Isso não é uma estratégia adequada para dados reais. Não há rotina de restauração dos CSVs nem versionamento/migração do esquema. Antes de mudanças estruturais, implementar backup SQLite consistente e migrações que preservem registros.
2. **Banco dentro da distribuição:** dist contém dados reais de execução e o script de build usa `--noconfirm` no mesmo destino. Esse destino deve ser tratado como substituível pelo empacotador. Não gerar novamente ali sem preservar o banco, incluindo o estado WAL; preferir separar o diretório de dados do diretório de distribuição.
3. **Ausência de Git:** a pasta entregue não é um repositório Git. Existe `.gitignore`, mas não há histórico de versões disponível. Inicializar versionamento antes das próximas mudanças, sem incluir bancos, ambientes virtuais ou builds.
4. **Dependências abertas:** requirements define somente versões mínimas e o PyInstaller é instalado sem versão fixa. Registrar versões homologadas para reproduzir o ambiente e o executável.
5. **PIN simples:** está fixo em config, o Admin permanece desbloqueado até bloqueio manual/encerramento, e o desfazer da Operação pode reverter ajustes administrativos sem PIN. Se houver separação real de funções entre usuários, definir autorização também nas ações e no desfazer.
6. **Busca limitada:** retorna no máximo 500 produtos sem paginação ou indicação de truncamento. O histórico carrega todos os logs; testar desempenho antes de bases grandes.
7. **Edição de produto:** o repositório tem `atualizar_dados`, mas não há fluxo completo de edição de nome, marca, categoria ou preço de venda. Será necessário implementar controlador e interface para essa mudança.
8. **Falhas de inicialização/callback:** imports de bibliotecas e telas ocorrem antes do try de main; falhas de importação não passam por `_registrar_falha`. Exceções de callbacks Tk também precisam de tratamento próprio para registro e aviso consistentes.
9. **Tabelas largas:** o componente comum cria rolagem vertical, sem horizontal. Revisar visualmente as colunas de relatórios em resolução mínima e escalas de tela maiores.
10. **Build antigo:** o spec salvo contém caminho absoluto de outra pasta. O BAT gera um novo spec; não tratar o spec atual como portável. O ambiente virtual copiado funciona aqui, mas deve ser recriado em outra máquina.

## Orientação para próximas alterações

Usar o fonte de CODIGO como base única. Primeiro, definir qual banco é o utilizado no dia a dia e estabelecer backup/restauração, separação dos dados e Git. Depois corrigir custo no Admin e transações, validar entradas numéricas e exportações e executar os testes isolados. Para cada mudança de tela, validar o fluxo pela interface; para mudanças no banco, criar migração. Por último gerar e testar uma nova distribuição em local isolado antes de substituir a usada na loja.

Esta análise e o script de auditoria são os únicos arquivos adicionados por esta revisão.
