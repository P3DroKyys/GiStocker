"""Backup JSON versionado do banco principal; restauração com SQL constante."""
import math
from datetime import datetime, timezone

from gestao.arquivos import LIMITE_ARQUIVO, json_bytes, ler_json
from models.models import BancoDados
from multicanal.esquema import TABELAS, TRIGGERS

TABELAS_BACKUP = tuple(sorted(TABELAS | {'Produtos', 'Codigos_Barras', 'Logs_Movimentacao', 'Logs_Alteracao'})) + ('sqlite_sequence',)
# Backups anteriores ao esquema 4 não têm a auditoria de alterações: restauram com ela vazia.
TABELAS_ESQUEMA_4 = {'Logs_Alteracao'}


def colunas(con, tabela):
    if tabela not in TABELAS_BACKUP:
        raise ValueError('Tabela não permitida.')
    return [tuple(r) for r in con.execute(f'PRAGMA table_info("{tabela}")')]


def exportar(banco):
    """Gerador de progresso por registros; leitura no mesmo snapshot."""
    pacote = {'formato': 'GiStocker-dados', 'versao': 1,
              'esquema': BancoDados.VERSAO_ESQUEMA,
              'criado_utc': datetime.now(timezone.utc).isoformat(), 'tabelas': {}}
    tamanho = 0
    with banco.leitura_consistente():
        totais = {t: banco.conexao.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in TABELAS_BACKUP}
        total, feitos = sum(totais.values()), 0
        for tabela in TABELAS_BACKUP:
            info = colunas(banco.conexao, tabela)
            registros = []
            pacote['tabelas'][tabela] = {'colunas': [r[1] for r in info], 'linhas': registros}
            for linha in banco.conexao.execute(f'SELECT * FROM "{tabela}"'):
                valores = list(linha)
                tamanho += len(json_bytes(valores)) + 1
                if tamanho > LIMITE_ARQUIVO:
                    raise ValueError('Backup maior que 64 MB. Use o backup criptografado em Relatórios.')
                registros.append(valores)
                feitos += 1
                if feitos % 100 == 0:
                    yield ('Exportação de registros', feitos, total)
        yield ('Exportação de registros', feitos, total)
    conteudo = json_bytes(pacote)
    if len(conteudo) > LIMITE_ARQUIVO:
        raise ValueError('Backup maior que 64 MB.')
    return conteudo


def substituir(con, tabelas, etapa):
    """Executada dentro de transação. Nenhum nome/DDL é obtido do JSON."""
    con.execute('PRAGMA defer_foreign_keys=ON')
    for nome in TRIGGERS:
        con.execute(f'DROP TRIGGER "{nome}"')
    # Filhos primeiro: evita cascatas sobre registros recém-inseridos.
    for tabela in reversed(TABELAS_BACKUP):
        con.execute(f'DELETE FROM "{tabela}"')
    total = sum(len(tabelas[t]['linhas']) for t in TABELAS_BACKUP)
    feitos = 0
    for tabela in TABELAS_BACKUP:
        if tabela == 'sqlite_sequence':
            con.execute('DELETE FROM sqlite_sequence')
        info = colunas(con, tabela)
        marcadores = ','.join('?' for _ in info)
        for linha in tabelas[tabela]['linhas']:
            if type(linha) is not list or len(linha) != len(info):
                raise ValueError(f'Registro inválido na tabela {tabela}.')
            for valor, (_, nome, tipo, obrigatorio, _, pk) in zip(linha, info):
                if valor is None:
                    if obrigatorio or pk:
                        raise ValueError(f'Campo obrigatório ausente: {tabela}.{nome}.')
                elif (tipo == 'INTEGER' and (type(valor) is not int or not -(2**63) <= valor < 2**63)
                      or tipo == 'REAL' and (type(valor) not in (int, float) or not math.isfinite(valor))
                      or tipo == 'TEXT' and type(valor) is not str
                      or tipo == '' and type(valor) not in (int, str)):
                    raise ValueError(f'Tipo inválido em {tabela}.{nome}.')
            con.execute(f'INSERT INTO "{tabela}" VALUES({marcadores})', linha)
            feitos += 1
            if feitos % 100 == 0:
                yield (etapa, feitos, total)
    for sql in TRIGGERS.values():
        con.execute(sql)
    if con.execute('PRAGMA foreign_key_check').fetchone():
        raise ValueError('O backup contém vínculos com registros inexistentes.')
    if [tuple(r) for r in con.execute('PRAGMA integrity_check')] != [('ok',)]:
        raise ValueError('O backup não passou na verificação de integridade.')
    # Sequências preservam IDs mesmo quando registros antigos foram removidos.
    sequencias = list(con.execute('SELECT name,seq FROM sqlite_sequence'))
    nomes = set()
    for nome, seq in sequencias:
        if nome not in ('Produtos', 'Logs_Movimentacao', 'Logs_Alteracao', 'Eventos_Estoque', 'Outbox_Comandos', 'Incidentes_Sync') or nome in nomes or type(seq) is not int or not 0 <= seq < 2**63:
            raise ValueError('Sequência de identificadores inválida.')
        nomes.add(nome)
        if seq < con.execute(f'SELECT coalesce(max(id),0) FROM "{nome}"').fetchone()[0]:
            raise ValueError('Sequência de identificadores inconsistente.')
    if [tuple(r) for r in con.execute('SELECT id,estado FROM Config_Multicanal')] != [(1, 'FISICO')]:
        raise ValueError('O backup deve estar no modo físico. Encerre a simulação antes de exportar.')
    if con.execute("SELECT 1 FROM Produtos WHERE estoque_atual<0 OR custo_medio<0 OR preco_venda_base<0 OR trim(nome)='' LIMIT 1").fetchone():
        raise ValueError('O backup contém produtos com dados inválidos.')
    if {r[0] for r in con.execute('SELECT id FROM Canais')} != {'SHOPEE', 'TIKTOK'}:
        raise ValueError('O backup não contém os canais obrigatórios.')
    if con.execute('SELECT 1 FROM Produtos p LEFT JOIN '
                   '(SELECT produto_id,sum(delta) saldo FROM Eventos_Estoque GROUP BY produto_id) e '
                   'ON e.produto_id=p.id WHERE e.saldo IS NULL OR e.saldo<>p.estoque_atual LIMIT 1').fetchone():
        raise ValueError('O saldo dos produtos diverge do histórico de eventos.')
    yield (etapa, feitos, total)


def restaurar(cofre, conteudo, recibo):
    pacote = ler_json(conteudo)
    if (type(pacote) is not dict or set(pacote) != {'formato', 'versao', 'esquema', 'criado_utc', 'tabelas'}
            or pacote['formato'] != 'GiStocker-dados' or type(pacote['versao']) is not int or pacote['versao'] != 1
            or type(pacote['esquema']) is not int or pacote['esquema'] not in (2, 3, 4)
            or type(pacote['tabelas']) is not dict
            or set(pacote['tabelas']) != set(TABELAS_BACKUP) - (TABELAS_ESQUEMA_4 if pacote['esquema'] < 4 else set())):
        raise ValueError('Formato ou versão de backup incompatível.')
    tabelas = pacote['tabelas']
    destino = cofre.banco
    for tabela in TABELAS_ESQUEMA_4 - set(tabelas):
        tabelas[tabela] = {'colunas': [r[1] for r in colunas(destino.conexao, tabela)], 'linhas': []}
    for tabela in TABELAS_BACKUP:
        dados = tabelas[tabela]
        if (type(dados) is not dict or set(dados) != {'colunas', 'linhas'}
                or dados['colunas'] != [r[1] for r in colunas(destino.conexao, tabela)]
                or type(dados['linhas']) is not list):
            raise ValueError(f'Estrutura inválida na tabela {tabela}.')
    # Validação completa em memória antes de tocar o banco da instalação.
    temporario = BancoDados(':memory:')
    try:
        with temporario.transacao():
            yield from substituir(temporario.conexao, tabelas, 'Validação do backup')
    finally:
        temporario.fechar()
    yield ('Cópia de segurança criptografada', 0, 1)
    snapshot = cofre.exportar(cofre.raiz / 'backups')
    yield ('Cópia de segurança criptografada', 1, 1)
    resultado = {'restaurado': True, 'snapshot': str(snapshot),
                 'produtos': len(tabelas['Produtos']['linhas']),
                 'historico': len(tabelas['Logs_Movimentacao']['linhas'])}
    with destino.transacao():
        yield from substituir(destino.conexao, tabelas, 'Restauração de registros')
        recibo(resultado)
    destino._indice_pesquisa = destino._versao_pesquisa = None
    return resultado
