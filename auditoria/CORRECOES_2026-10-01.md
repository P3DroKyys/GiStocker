# Correções de estabilidade — GiStocker 1.0.1

Os 14 problemas reproduzidos na auditoria foram corrigidos. O relatório anterior
permanece como diagnóstico histórico. Não foram modificados bancos de uso, nem
alterado o esquema SQLite. Foi preservado um ZIP dos fontes anteriores em
`auditoria/fonte_antes_correcoes_*.zip`.

| ID | Correção entregue |
|---|---|
| A01 | BAT chama `gerar_build.py`: cada build reserva uma pasta exclusiva dentro de dist; não limpa versões anteriores. |
| A02 | Cada exportação recebe pasta e nomes exclusivos, inclusive quando feitas no mesmo instante. |
| A03 | Estoque e histórico são consultados no mesmo snapshot de leitura SQLite. |
| A04 | Os dois CSVs são preparados em pasta temporária e publicados por renomeação da pasta; falha de escrita/publicação limpa somente a pasta temporária criada pela operação. |
| A05 | Textos que começam com indicadores de fórmula ou controles recebem apóstrofo no CSV; valores numéricos e cadastros originais são preservados. |
| A06 | Admin envia o produto esperado ao remover um código; controlador valida o dono dentro da transação. |
| A07 | Falhas de persistência têm mensagem nas telas de operação/cadastro/Admin e registro em erros.log; há proteção geral de callbacks para falhas inesperadas, inclusive consultas. |
| A08 | Removido o limite implícito de 500 na busca; catálogo, Relatórios e Ajustes acessam todos os resultados. |
| A09 | Quantidades, saldo resultante e diferença de ajuste são verificados contra o limite do INTEGER antes da gravação. |
| A10 | KPIs usam inteiros Python; gráficos e rankings usam agregação sem overflow de 64 bits. Valores financeiros legados não finitos geram erro explicativo. |
| A11 | Validação monetária rejeita valores extremos: teto configurável de R$ 1 trilhão por valor unitário, além de NaN/infinito/negativos. |
| A12 | Custo inicial novo usa quatro casas; entrada sem custo preserva exatamente o custo anterior, inclusive valores legados com mais casas. |
| A13 | “Tônico capilar” é avaliado antes de “tônico”. |
| A14 | Sugestões automáticas de marca/categoria são limpas quando deixam de corresponder ao nome; escolhas manuais são mantidas. |

## Validação

102 testes aprovados, sem `expectedFailure`, testes ignorados ou falhas inesperadas.
Evidências em `resultados_correcao_20261001/testes.txt` e `resultados.json`.

Foram mantidos os testes de transações, concorrência, migração, backup/restauração,
encerramento abrupto, GTIN, estoque e relatórios. Casos adicionais verificam quatro
exportações simultâneas, falha de publicação preservando exportação anterior, limpeza
de transação após falha de leitura, campos de fórmula sem converter deltas negativos
em texto, proteção dos limites, preservação de custo legado e builds repetidas/falhas.

A reprodução antiga da divergência de CSV foi ajustada para escrever por uma segunda
conexão: uma escrita deliberada na mesma conexão alteraria o próprio snapshot,
sem representar outra instância do aplicativo. A reprodução da build passou a
exercitar o novo gerador, verificando os caminhos enviados ao empacotador e a
preservação de arquivos sentinela. Testes de valores proibidos verificam rejeição
amigável e ausência de gravação, em vez de esperar que o cadastro inválido prossiga.

A carga continua incluindo 1.000 operações pseudoaleatórias, 400 GTINs corretos e
3.600 variantes incorretas, além de 5.000 produtos e 10.000 movimentos fictícios.
Tempos medidos usam banco em memória e não representam a renderização de telas.

Uma build nova foi gerada pelo próprio BAT. A inspeção de empacotamento confere
presença dos módulos e igualdade dos recursos visuais com os fontes. Isso não
equivale a testar instalação e execução em outro computador.

## Mudanças visíveis e atualização

- Build: `dist/GiStocker_DATA_HORA_ID/GestorEstoque/GestorEstoque.exe`.
- Exportação: `exportacoes/exportacao_DATA_HORA_ID/`, contendo o par de CSVs.
- Erros técnicos: mensagem e `erros.log`, quando o disco permite escrever o log.
- O arquivo de estoque continua em `dados/estoque.db`, ao lado da instalação.

Para atualizar a instalação em uso: feche todas as instâncias; preserve uma cópia
da pasta atual completa; substitua apenas o executável e `_internal` pelos arquivos
da nova build. Mantenha as pastas `dados` e `exportacoes`. Não substitua o banco
com o aplicativo aberto. Uma build aberta em pasta nova não importa automaticamente
os dados da loja e pode iniciar com uma base vazia.

## Limites

Nenhum conjunto de testes garante ausência de todos os bugs. Nesta rodada não foi
realizado teste físico de queda de energia, scanner USB, instalação em outro PC ou
revisão visual completa. A interrupção de processo foi simulada em bases temporárias.

As observações de projeto do relatório anterior (gestão de usuários/PIN, retenção
e cópia externa de backups, restauração assistida, lotes e integrações) continuam
sendo melhorias distintas dos 14 defeitos corrigidos. Não foram implementadas APIs
ou regras de reserva de estoque nesta atualização.
