# Validação da gestão de dados — 2026-10-06

201 testes distintos aprovados nas execuções finais de cada grupo, com bases
temporárias. Nenhum banco da loja foi usado, restaurado ou importado pelos testes.

| Grupo | Testes | Resultado |
| --- | ---: | --- |
| Banco, GTIN, busca, correções, upgrade, multicanal, IPC, segurança e fluxos criptografados existentes | 176 | OK |
| `verificar_gestao_dados` | 15 | OK |
| `verificar_gestao_ipc` | 4 | OK |
| `smoke_gestao_dados` | 1 | OK |
| `smoke_interface_multicanal` | 1 | OK |
| `smoke_interface_upgrade` | 4 | OK |

Os testes de IPC rodam o agente em outro processo e usam o Named Pipe real do
Windows. Os testes visuais instanciam widgets reais em ambos os temas e exercitam
o worker, a trava modal, a reautenticação e a recarga das telas. Os ensaios de
interrupção encerram abruptamente somente o agente criado pelo teste, tanto durante
uma importação quanto durante uma restauração; após reabrir, a base anterior e
as operações de estoque permanecem disponíveis.

Também foram verificados: senha errada, exclusão entre sessões, timeout com
rollback, integridade SQLCipher, preservação de senha/chave ao importar backup de
outra instalação, chaves estrangeiras inválidas, tipos e colunas inválidos, JSON
truncado/duplicado, falha ao criar snapshot, falha antes do commit, preservação de
IDs/histórico, custo médio, GTINs com zeros, linhas inválidas/duplicadas, arquivo
de saída atômico e repetição segura após perda da resposta de commit.

Durante o desenvolvimento foram corrigidos um import de helper de interface e
um callback de redimensionamento reentrante. Alguns testes antigos dependem de
`auditoria` no PYTHONPATH; as execuções finais usaram esse caminho. O teste de
encerramento abrupto recria seu Event de controle ao reiniciar, pois finalizar
um processo durante Event.wait pode deixar o lock do Event antigo indisponível.

Comando para reproduzir todos os grupos (na raiz do projeto):

```powershell
$env:PYTHONPATH = "$PWD\auditoria;$PWD"
.\.venv\Scripts\python.exe -m unittest auditoria.verificar_banco auditoria.verificar_gtin auditoria.verificar_busca auditoria.verificar_correcoes auditoria.verificar_upgrade auditoria.verificar_multicanal auditoria.verificar_ipc auditoria.verificar_seguranca auditoria.verificar_fluxos_criptografados auditoria.verificar_gestao_dados auditoria.verificar_gestao_ipc auditoria.smoke_gestao_dados auditoria.smoke_interface_multicanal auditoria.smoke_interface_upgrade -v
```

Limites: não foi simulada queda elétrica real nem defeito físico do armazenamento.
Nenhum instalador/build foi gerado nesta alteração. Os arquivos novos são imports
estáticos e o guia de gestão de dados passou a acompanhar as próximas builds.
