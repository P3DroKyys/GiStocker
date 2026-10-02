"""Mesmas regressões de estoque usando o driver e formato da build protegida."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import tempfile

import verificar as base
from verificar_seguranca import SENHA
from models.models import BancoDados
from models.seguranca import conectar, conferir_integridade
from controllers.controllers import ControladorEstoque, ControladorRelatorios


class FluxosCriptografados(base.Auditoria):
    def setUp(self):
        temporario = tempfile.TemporaryDirectory()
        self.addCleanup(temporario.cleanup)
        self.pasta = Path(temporario.name)
        self.bd = BancoDados(self.pasta / 'estoque.db', senha=SENHA, criar=True, backup_automatico=False)
        self.addCleanup(self.bd.fechar)
        self.c = ControladorEstoque(self.bd)
        self.r = ControladorRelatorios(self.bd)

    def test_exportacao_vazia_e_preenchida(self):
        for preenchido in (False, True):
            if preenchido:
                self.produto()
            copia = self.r.exportar_protegido(self.pasta / 'exportacoes')
            with closing(conectar(copia, SENHA)) as con:
                conferir_integridade(con)
                self.assertEqual(con.execute('SELECT count(*) FROM Produtos').fetchone()[0], int(preenchido))
                self.assertEqual(con.execute('SELECT count(*) FROM Logs_Movimentacao').fetchone()[0], int(preenchido))

    def test_defeito_exportacoes_no_mesmo_minuto(self):
        self.produto()
        copias = [self.r.exportar_protegido(self.pasta / 'exportacoes') for _ in range(3)]
        self.assertEqual(len(set(copias)), 3)
        self.assertTrue(all(p.is_file() for p in copias))

    def test_defeito_duas_instancias_perdem_movimentacao(self):
        produto = self.produto()
        def gravar(_):
            bd = BancoDados(self.bd.caminho, senha=SENHA, backup_automatico=False)
            try:
                c = ControladorEstoque(bd)
                for _ in range(10):
                    c.registrar_entrada(produto.id, 1, 10)
            finally:
                bd.fechar()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(gravar, range(2)))
        self.assertEqual(self.c.obter_produto(produto.id).estoque_atual, 30)
        self.assertEqual(len(self.c.listar_logs()), 21)
