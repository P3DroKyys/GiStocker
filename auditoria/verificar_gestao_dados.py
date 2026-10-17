"""Regressão em bancos temporários: nunca abre dados da instalação."""
import base64
from contextlib import closing
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

import config
from gestao import backup, planilha
from gestao.arquivos import SaidaAtomica, json_bytes
from models.models import BancoDados
from multicanal.motor import Motor
from servico.cofre import CofreServico
from servico.gestao import GestaoDados
from servico.nucleo import Nucleo
from servico.protocolo import VERSAO


def consumir(gerador):
    progresso = []
    while True:
        try:
            progresso.append(next(gerador))
        except StopIteration as fim:
            return fim.value, progresso


def gtin(numero):
    corpo = str(numero).zfill(12)
    soma = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(corpo))
    return corpo + str((-soma) % 10)


def csv_bytes(linhas):
    f = io.StringIO(newline='')
    w = csv.writer(f, delimiter=';')
    w.writerow(planilha.CABECALHOS)
    w.writerows(linhas)
    return f.getvalue().encode('utf-8-sig')


def linha(n=1, qtd='3', preco='20,00', custo='10,00'):
    return [gtin(n), f'Produto {n}', config.MARCAS[0], config.CATEGORIAS[0], qtd, preco, custo]


class Planilhas(unittest.TestCase):
    def setUp(self):
        self.bd = BancoDados(':memory:')
        self.motor = Motor(self.bd)

    def tearDown(self):
        self.bd.fechar()

    def importar(self, linhas):
        return consumir(planilha.importar(self.bd, csv_bytes(linhas), str(uuid4()), lambda _: None))[0]

    def test_modelo_somente_cabecalhos(self):
        self.assertEqual(planilha.modelo().decode('utf-8-sig').splitlines(), [';'.join(planilha.CABECALHOS)])

    def test_adicionar_atualizar_custo_ponderado_precos_vazios_e_historico(self):
        self.assertEqual(self.importar([linha()])['novos'], 1)
        dados = linha(qtd='2', preco='', custo='20')
        dados[1] = 'Nome atualizado'
        r = self.importar([dados, linha(2, '0', '', '')])
        self.assertEqual((r['novos'], r['atualizados']), (1, 1))
        p = self.motor.estoque.obter_produto(1)
        self.assertEqual((p.nome, p.estoque_atual, p.custo_medio, p.preco_venda_base), ('Nome atualizado', 5, 14, 20))
        self.assertEqual(p.codigos, [gtin(1)])
        self.assertEqual(self.bd.conexao.execute('SELECT sum(delta) FROM Eventos_Estoque WHERE produto_id=1').fetchone()[0], 5)
        logs = self.motor.estoque.listar_logs()
        self.assertEqual(len(logs), 2)
        self.assertTrue(all('Importação CSV' in l['observacao'] for l in logs))
        self.importar([linha(qtd='0', preco='30', custo='7')])
        p = self.motor.estoque.obter_produto(1)
        self.assertEqual((p.estoque_atual, p.custo_medio, p.preco_venda_base), (5, 7, 30))
        self.motor.fisico('desfazer_ultima_acao', [], {}, str(uuid4()))
        self.assertEqual(self.motor.estoque.obter_produto(1).custo_medio, 14)

    def test_erros_por_linha_e_duplicatas_incluindo_alias(self):
        self.importar([linha()])
        self.motor.estoque.vincular_codigo_barras(gtin(9), 1)
        invalidas = []
        for indice, valor in ((0, 'abc'), (0, '0000000000000'), (0, '123'),
                              (2, 'marca inexistente'), (3, ''), (4, '-1'),
                              (4, '1.5'), (4, str(2**63)), (5, 'NaN'), (6, '-5')):
            v = linha(2)
            v[indice] = valor
            invalidas.append(v)
        r = self.importar([linha(), linha(9), linha()] + invalidas + [linha(2), linha(3)[:-1]])
        self.assertEqual((r['novos'], r['atualizados'], len(r['erros'])), (1, 1, 13))
        self.assertEqual(r['erros'][0]['linha'], 3)
        self.assertEqual(self.motor.estoque.obter_produto(1).estoque_atual, 6)

    def test_lote_critico_e_interrupcao_nao_deixam_parcial(self):
        with patch.object(self.motor.__class__, 'preparar', side_effect=OSError('disco')):
            with self.assertRaises(OSError):
                self.importar([linha(), linha(2)])
        self.assertEqual(self.motor.estoque.listar_produtos(), [])
        g = planilha.importar(self.bd, csv_bytes([linha(n) for n in range(1, 202)]), str(uuid4()), lambda _: None)
        self.assertEqual(next(g)[1:], (100, 201))
        self.assertTrue(self.bd.conexao.in_transaction)
        g.close()
        self.assertFalse(self.bd.conexao.in_transaction)
        self.assertEqual(self.motor.estoque.listar_produtos(), [])

    def test_csv_estrutural_invalido_e_gtin_notacao_cientifica(self):
        for arquivo in (b'errado\n1', planilha.modelo(), planilha.modelo() + b'"aspas', b'\xff\xff'):
            with self.assertRaises(ValueError):
                consumir(planilha.importar(self.bd, arquivo, str(uuid4()), lambda _: None))
        v = linha()
        v[0] = '1.234E+12'
        self.assertEqual(len(self.importar([v])['erros']), 1)

    def test_progresso_real(self):
        r, p = consumir(planilha.importar(self.bd, csv_bytes([linha(n) for n in range(1, 252)]), str(uuid4()), lambda _: None))
        self.assertEqual(r['novos'], 251)
        self.assertEqual([v[1:] for v in p], [(100, 251), (200, 251), (251, 251)])


class Backups(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.cofre = CofreServico(self.raiz / 'dados')
        self.cofre.abrir('', 'senha-atual', 'senha-atual')
        self.bd = self.cofre.banco
        consumir(planilha.importar(self.bd, csv_bytes([linha()]), str(uuid4()), lambda _: None))
        self.original = consumir(backup.exportar(self.bd))[0]
        self.snapshots_antes = set((self.cofre.raiz / 'backups').glob('*.gsbackup'))

    def tearDown(self):
        self.cofre.fechar()
        self.tmp.cleanup()

    def tabelas(self):
        return json.loads(consumir(backup.exportar(self.bd))[0])['tabelas']

    def test_roundtrip_preserva_historico_ids_senha_chave_e_criptografia(self):
        esperado = self.tabelas()
        senha_antes = self.cofre.envelope.read_bytes()
        chave = self.cofre.chave
        consumir(planilha.importar(self.bd, csv_bytes([linha(2)]), str(uuid4()), lambda _: None))
        r, progresso = consumir(backup.restaurar(self.cofre, self.original, lambda _: None))
        self.assertEqual(self.tabelas(), esperado)
        self.assertEqual(self.cofre.envelope.read_bytes(), senha_antes)
        self.assertEqual(self.cofre.chave, chave)
        self.assertTrue(Path(r['snapshot']).is_file())
        self.assertTrue(self.cofre.verificar_senha('senha-atual'))
        self.assertNotEqual(self.cofre.caminho.read_bytes()[:16], b'SQLite format 3\x00')
        with closing(sqlite3.connect(self.cofre.caminho)) as con:
            with self.assertRaises(sqlite3.DatabaseError):
                con.execute('SELECT * FROM Produtos').fetchall()
        consumir(planilha.importar(self.bd, csv_bytes([linha(2)]), str(uuid4()), lambda _: None))
        self.assertEqual(Motor(self.bd).estoque.obter_produto(2).id, 2)
        self.assertTrue(any(p[0] == 'Restauração de registros' for p in progresso))

    def test_importar_backup_de_outra_instalacao_nao_troca_a_senha(self):
        outro = CofreServico(self.raiz / 'outro')
        try:
            outro.abrir('', 'outra-senha', 'outra-senha')
            consumir(backup.restaurar(outro, self.original, lambda _: None))
            self.assertTrue(outro.verificar_senha('outra-senha'))
            self.assertFalse(outro.verificar_senha('senha-atual'))
            self.assertEqual(Motor(outro.banco).estoque.obter_produto(1).estoque_atual, 3)
        finally:
            outro.fechar()

    def test_backup_invalido_nunca_substitui(self):
        esperado = self.tabelas()
        base = json.loads(self.original)
        variantes = []
        p = copy.deepcopy(base); p['tabelas']['Produtos']['linhas'][0][4] = -1; variantes.append(p)
        p = copy.deepcopy(base); p['tabelas']['Produtos']['linhas'][0][4] = '3'; variantes.append(p)
        p = copy.deepcopy(base); p['tabelas']['Codigos_Barras']['linhas'][0][1] = 999; variantes.append(p)
        p = copy.deepcopy(base); p['tabelas']['Produtos']['colunas'][0] = 'id); DROP TABLE Produtos'; variantes.append(p)
        p = copy.deepcopy(base); p['tabelas']['Eventos_Estoque']['linhas'][0][3] = 55; variantes.append(p)
        for pacote in variantes:
            with self.subTest(pacote=pacote['tabelas']['Produtos']):
                with self.assertRaises(Exception):
                    consumir(backup.restaurar(self.cofre, json_bytes(pacote), lambda _: None))
                self.assertEqual(self.tabelas(), esperado)
        for conteudo in (self.original[:-2], b'{"x":1,"x":2}', b'{"x":NaN}'):
            with self.assertRaises(ValueError):
                consumir(backup.restaurar(self.cofre, conteudo, lambda _: None))
        self.assertEqual(set((self.cofre.raiz / 'backups').glob('*.gsbackup')), self.snapshots_antes)

    def test_falha_apos_substituir_reverte_tabelas_e_triggers(self):
        consumir(planilha.importar(self.bd, csv_bytes([linha(2)]), str(uuid4()), lambda _: None))
        esperado = self.tabelas()
        def falhar(_):
            raise OSError('falha antes de commit')
        with self.assertRaises(OSError):
            consumir(backup.restaurar(self.cofre, self.original, falhar))
        self.assertEqual(self.tabelas(), esperado)
        self.assertEqual(len(set((self.cofre.raiz / 'backups').glob('*.gsbackup')) - self.snapshots_antes), 1)
        with self.assertRaises(Exception):
            self.bd.conexao.execute('DELETE FROM Eventos_Estoque')

    def test_falha_snapshot_nao_altera_banco(self):
        esperado = self.tabelas()
        with patch.object(self.cofre, 'exportar', side_effect=OSError('sem espaço')):
            with self.assertRaises(OSError):
                consumir(backup.restaurar(self.cofre, self.original, lambda _: None))
        self.assertEqual(self.tabelas(), esperado)

    def test_arquivo_atomico_preserva_destino_em_falha(self):
        destino = self.raiz / 'backup.json'
        destino.write_text('anterior')
        with self.assertRaises(OSError):
            with SaidaAtomica(destino) as arq:
                arq.write(b'novo')
                raise OSError('falha')
        self.assertEqual(destino.read_text(), 'anterior')
        self.assertFalse(list(self.raiz.glob('*.parcial')))


class Agente(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.n = Nucleo(Path(self.tmp.name) / 'dados')
        self.token = None
        self.token = self.pedir('login', '', 'senha-teste', 'senha-teste')

    def tearDown(self):
        self.n.fechar()
        self.tmp.cleanup()

    def pedir(self, comando, *args, token=None):
        r = self.n.executar(dict(v=VERSAO, id=str(uuid4()), sessao=token or self.token,
                                comando=comando, args=list(args), kwargs={}), 'mesmo-usuario')
        if not r['ok']:
            raise ValueError(r['mensagem'])
        return r['resultado']

    def iniciar(self, conteudo, op=None):
        op = op or str(uuid4())
        estado = self.pedir('dados.iniciar', op, 'importar', 'senha-teste', len(conteudo), hashlib.sha256(conteudo).hexdigest())
        if not estado['concluido']:
            self.pedir('dados.enviar', op, 0, base64.b64encode(conteudo).decode('ascii'))
        return op, estado

    def test_senha_incorreta_sessao_invalida_e_simulacao(self):
        for tipo in ('exportar', 'restaurar', 'importar'):
            self.n.gestao.tentar_apos = 0
            with self.assertRaisesRegex(ValueError, 'Senha atual incorreta'):
                self.pedir('dados.iniciar', str(uuid4()), tipo, 'errada', 1, 'a' * 64)
            self.assertFalse(self.n.gestao.ocupado)
        with self.assertRaisesRegex(ValueError, 'Sessão bloqueada'):
            self.pedir('dados.iniciar', str(uuid4()), 'exportar', 'senha-teste', token='invalido')
        self.n.gestao.tentar_apos = 0
        self.n.cofre.banco.conexao.execute("UPDATE Config_Multicanal SET estado='MULTICANAL_PAUSADO'")
        with self.assertRaisesRegex(ValueError, 'laboratório'):
            self.pedir('dados.iniciar', str(uuid4()), 'exportar', 'senha-teste')

    def test_exclusao_mutua_abort_timeout_e_idempotencia(self):
        conteudo = csv_bytes([linha(n) for n in range(1, 102)])
        op, _ = self.iniciar(conteudo)
        self.pedir('dados.passo', op)
        with self.assertRaisesRegex(ValueError, 'andamento'):
            self.pedir('estoque.listar_produtos')
        with self.assertRaises(ValueError):
            self.pedir('login', 'senha-teste', None, None)
        self.n.gestao.job['uso'] = time.monotonic() - 301
        self.n.manutencao()
        self.assertEqual(self.pedir('estoque.listar_produtos'), [])
        op, estado = self.iniciar(conteudo, op)
        while not estado['concluido']:
            estado = self.pedir('dados.passo', op)
            self.assertIsNone(estado['erro'])
        self.pedir('dados.liberar', op)
        _, estado = self.iniciar(conteudo, op)
        self.assertTrue(estado['concluido'])
        self.pedir('dados.liberar', op)
        self.assertEqual(self.n.motor.estoque.obter_produto(1).estoque_atual, 3)

    def test_outro_token_nao_acessa_job(self):
        outro = self.pedir('login', 'senha-teste', None, None)
        op, _ = self.iniciar(csv_bytes([linha()]))
        with self.assertRaisesRegex(ValueError, 'sessão'):
            self.pedir('dados.baixar', op, 0, token=outro)
        self.pedir('dados.liberar', op)


if __name__ == '__main__':
    unittest.main()
