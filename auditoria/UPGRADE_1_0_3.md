# Upgrade 1.0.3 — 01/10/2026

## Entrega

- Senha única na abertura do aplicativo; Admin sem bloqueio adicional.
- Engrenagem com versão, escolha persistente de tema e troca de senha exigindo
  senha atual, nova senha e confirmação. Campos ocultos com Mostrar/Ocultar;
  limpeza e retorno à máscara ao sair do painel.
- Preferências em `dados/configuracoes.db`, separadas do estoque. PBKDF2-SHA256
  com sal aleatório, comparação constante e atualização em transação. Senha inicial
  igual ao PIN anterior: `1234`. Configurações inválidas não liberam acesso.
- Admin sem campo Motivo. Ajustes continuam auditados com observação automática
  e com proteção contra alteração baseada em saldo/custo desatualizados.
- Dashboard com contagem de produtos, independente da quantidade de itens e do
  número de códigos de barras. Quatro cartões se reorganizam em janelas menores.
  Legenda fora da área das barras, com margem no eixo vertical.
- Cadastro aceita preços omitidos ou vazios, gravando zero. Mantém validações
  quando valores são informados e preserva as regras dos demais campos.

## Verificação

- **140 testes automatizados aprovados**, incluindo os 108 anteriores.
- **1 teste de integração com componentes reais Tk aprovado**, em janela oculta:
  bloqueio inicial e atalhos, senha errada/correta, cadastro sem preços, ajuste sem
  motivo, troca de senha, máscara, limpeza ao navegar, tema, dashboard e relatórios.
- Testes de senha com reabertura, duas instâncias concorrentes, confirmação errada,
  dados inválidos, corrupção e falha simulada de escrita. Senha anterior preservada
  quando a alteração falha.
- Gráfico verificado nos dois temas, em três larguras, com período vazio, pico na
  última data e quantidade de 64 bits; legenda dentro da figura e sem sobrepor barras.
- Prévia nativa inspecionada nos temas claro/escuro, inclusive 1024 × 680.
- Build compilada abriu em cópia isolada pela conta do Windows, com janela ativa
  e sem erros no log de inicialização. A captura dessa janela específica não foi
  concluída porque a autorização do Computer Use expirou; os fluxos completos
  foram verificados na integração com widgets reais descrita acima.
- Evidências: `testes_upgrade.txt`, `teste_interface_upgrade.txt`, `build_upgrade.log`.
- Abertura do executável: `teste_build_upgrade.txt`.
- Testes somente com bancos em memória/temporários e produtos fictícios.

Durante os testes foi corrigida uma conexão não fechada quando o SQLite rejeitava
um arquivo de configurações corrompido. O teste da distribuição também identificou
a ACL privada de pastas criadas por `tempfile.mkdtemp` no Python 3.13+/Windows:
o gerador passou a reservar pastas exclusivas com UUID/mkdir, herdando as permissões
normais de `dist`. Versões anteriores não foram sobrescritas.

Avisos de cache de fontes do matplotlib no sandbox não impediram os testes.
Na montagem inicial de gráficos houve aviso transitório de constrained_layout;
o layout final do gráfico solicitado foi conferido visualmente e por geometria.
Não foram realizados testes de scanner físico, falha elétrica real ou instalação
em outro computador. O bloqueio de acesso não criptografa o banco de estoque.

## Distribuição

Build: `dist/GiStocker_20261001_104320_1beccef686fb/GestorEstoque`.
Atualizar com o software fechado, preservando a instalação anterior; substituir
o executável e `_internal`, mantendo as pastas `dados` e `exportacoes` da loja.
Ao abrir a build numa pasta nova, os dados não são transferidos automaticamente.
Depois do primeiro acesso com `1234`, a senha pode ser trocada pela engrenagem.
