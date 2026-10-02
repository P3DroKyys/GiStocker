# Pesquisa automática no Admin — 1.2.0

Escopo: Admin → Ajustes e códigos. Dados da loja não foram usados nos testes.
O esquema do banco e a criptografia não foram alterados.

## Método implementado

Índice invertido por palavras, com pesos por campo: nome 100, marca 70,
categoria 45. Correspondência exata de palavra recebe peso 100; prefixo, 85;
trecho interno com ao menos três letras, 65. Nome completo exato recebe bônus
maior; início da expressão no nome recebe bônus menor. Empates usam nome e ID.
Maiúsculas, acentos e espaços são normalizados. Hífens/apóstrofos separam termos;
`200ml` e `200 ml` resultam nos mesmos termos. Palavras de ligação são ignoradas
quando acompanhadas de palavras relevantes. Todas as palavras restantes são
exigidas, mesmo quando se encontram em campos diferentes.

Se não houver resultados diretos, usa-se **Damerau–Levenshtein**, implementado
pelo RapidFuzz 3.14.6: inserção, remoção, substituição e transposição de letras.
Admite-se um erro para termos de 4–7 letras e dois para termos de 8–64 letras.
Termos menores e identificadores numéricos não recebem correção. Aproximação
recebe peso inferior aos acertos diretos. Não há remoção silenciosa de palavras
desconhecidas para produzir sugestões que contradigam a consulta.

Código exato tem prioridade. Códigos completos desconhecidos (8/12/13/14 dígitos)
não geram sugestões aproximadas; trechos numéricos com três ou mais dígitos podem
encontrar códigos parciais. `#123` consulta ID, evitando confundir `200` com o
produto ID 200 quando o usuário procura um frasco de 200 ml. `%`/`_` são literais,
sem passagem por LIKE. Há mensagens para consultas acima de 256 caracteres ou
16 termos distintos, sem truncamento silencioso.

O índice existe somente em memória, compartilhado pela conexão do banco. É
reconstruído após mudança em `total_changes` ou `PRAGMA data_version`. Leituras
dentro de transações não alimentam cache; rollback não conserva dados não
confirmados. Fechar/bloquear o banco descarta a referência ao índice e consultas
posteriores falham, mesmo se alguém conservar uma referência ao controlador.
Nenhum índice em texto puro é gravado em disco.

Referências do método:
[RapidFuzz/Damerau–Levenshtein](https://rapidfuzz.github.io/RapidFuzz/Usage/distance/DamerauLevenshtein.html)
e [projeto RapidFuzz](https://github.com/rapidfuzz/RapidFuzz).
FTS5 foi considerado, mas não usado: o motor SQLCipher desta instalação foi
compilado sem FTS. A solução preserva essa configuração e evita migrar o banco.

## Comportamento da interface

- Sem botão Buscar; alterações no texto, inclusive colagem/remoção, agendam uma
  única pesquisa após 220 ms. Enter executa imediatamente, útil para scanners.
- A edição limpa imediatamente seleção, campos e códigos do produto anterior.
  Os botões de ajuste/vínculo ficam desabilitados até haver seleção válida.
- Resultado direto único é selecionado; sugestões aproximadas exigem clique.
  A tela identifica as opções próximas e informa ausência de resultados.
- Campo vazio lista o catálogo. Exibe 200 linhas por vez e contagem explícita;
  Mostrar mais permite acessar todas, sem limite silencioso de resultados.
- Abrir um produto pelo catálogo preenche `#ID` e mantém o fluxo de ajuste.
  Sair da tela, trocar de aba ou bloquear cancela pesquisas pendentes.

## Evidências

`verificar_busca.py` acrescenta 24 testes: relevância, acentos, palavras fora de
ordem, erros de escrita, códigos/zeros à esquerda, volumes, ID, literais, limites,
todos os resultados, alterações/rollback, outra conexão e encerramento de sessão.
`smoke_busca.py` acrescenta cinco integrações com widgets reais ocultos: digitação,
colagem, debounce, seleção obsoleta, sugestões, scanner, paginação, navegação,
catálogo e bloqueio com busca pendente. Bases sempre descartáveis.

Resultado final: **209 testes de regressão aprovados** em 36,359 s e **9 testes
de interface aprovados** em 15,214 s, sem erros Tcl. Registros da suíte completa:
`testes_1_2_0.txt` e `interfaces_1_2_0.txt`.
O teste sintético em `desempenho_busca_1_2_0.json` usou 10.001 produtos:
preparação do índice em 192,40 ms e consultas de 4,87 a 61,87 ms nessa máquina.
Esses tempos não incluem leitura inicial do banco ou desenho da tabela e não
são uma promessa para qualquer equipamento/tamanho de catálogo.

Dependência fixada com hash em `requirements.lock`; licença MIT incluída na build.
`rapidfuzz_audit.json` registra a consulta de vulnerabilidades da nova dependência
sem alertas conhecidos em 01/10/2026. Isso não certifica ausência de falhas futuras.
`pip check` passou. Build coleta os módulos nativos e Python do RapidFuzz; veja
`build_1_2_0.log` e `distribuicao_1_2_0.json` para o pacote gerado.

A verificação do pacote identificou ausência da DLL auxiliar que acompanha a
wheel Windows, fazendo a biblioteca usar o fallback Python. `gerar_build.py`
foi ajustado para incluir `rapidfuzz.libs/*.dll`. Os 19 testes de upgrade e
empacotamento passaram novamente. `validar_distribuicao.py` confere os hashes
das oito extensões de busca e da DLL auxiliar. `validar_busca_empacotada.py`
verifica a busca extraída do executável com a implementação C++ distribuída;
evidência em `busca_empacotada_1_2_0.json`. Isso não automatiza o login no `.exe`.

Build final validada:
`dist/GiStocker_20261001_230801_33c09fc2dcb3/GestorEstoque/GestorEstoque.exe`.
Foram conferidos 2.136 arquivos; a busca carregou `metrics_cpp_avx2` diretamente
da distribuição e passou nos casos de transposição e códigos exatos/incorretos.
SHA-256 do executável:
`4478fd0816b3e4cdd831e46a17538291ba0e0c417e67cf1afcbcaf5d80f25354`.
Esta é a distribuição recomendada; a geração anterior das 23:03 foi substituída
por esta entrega após a correção da DLL auxiliar.

Limites deliberados: não há busca semântica/sinônimos, correção ilimitada de erros
ou aproximação de códigos. Catálogo e Relatórios conservam seus filtros atuais.
As aproximações são sugestões, nunca autorização para alterar estoque.
