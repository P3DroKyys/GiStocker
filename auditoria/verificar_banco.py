"""Regressões de persistência; usa apenas bancos temporários e em memória."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from controllers.controllers import ControladorEstoque, ErroNegocio
from models.models import BancoDados


class BancoSeguro(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "estoque.db"
        self.bd = BancoDados(self.path, backup_automatico=False, permitir_legado=True)
        self.addCleanup(self.bd.fechar)
        self.c = ControladorEstoque(self.bd)

    def produto(self, quantidade=10):
        return self.c.cadastrar_produto("Teste", config.MARCAS[0], config.CATEGORIAS[0],
                                        30, 10, quantidade)

    def test_entradas_realmente_concorrentes(self):
        produto = self.produto()
        barreira = threading.Barrier(2)

        def entradas(custo):
            bd = BancoDados(self.path, backup_automatico=False, permitir_legado=True)
            try:
                c = ControladorEstoque(bd)
                barreira.wait(timeout=10)
                for _ in range(20):
                    c.registrar_entrada(produto.id, 1, custo)
            finally:
                bd.fechar()

        with ThreadPoolExecutor(max_workers=2) as pool:
            tarefas = [pool.submit(entradas, custo) for custo in (10, 20)]
            for tarefa in tarefas:
                tarefa.result(timeout=20)
        final = self.c.obter_produto(produto.id)
        self.assertEqual(final.estoque_atual, 50)
        self.assertAlmostEqual(final.custo_medio, 14, places=2)
        self.assertEqual(len(self.c.listar_logs()), 41)
        saldo = 0
        for log in reversed(self.c.listar_logs()):
            self.assertEqual(log["estoque_anterior"], saldo)
            saldo += log["quantidade"]

    def test_ultima_unidade_nao_vendida_duas_vezes(self):
        produto = self.produto(1)
        barreira = threading.Barrier(2)

        def vender():
            bd = BancoDados(self.path, backup_automatico=False, permitir_legado=True)
            try:
                c = ControladorEstoque(bd)
                barreira.wait(timeout=10)
                try:
                    c.registrar_saida(produto.id, 1)
                    return "vendeu"
                except ErroNegocio:
                    return "sem estoque"
            finally:
                bd.fechar()

        with ThreadPoolExecutor(max_workers=2) as pool:
            tarefas = [pool.submit(vender) for _ in range(2)]
            self.assertCountEqual([t.result(timeout=20) for t in tarefas], ["vendeu", "sem estoque"])
        self.assertEqual(self.c.obter_produto(produto.id).estoque_atual, 0)
        self.assertEqual(len(self.c.listar_logs()), 2)

    def test_codigo_concorrente_preserva_unicidade(self):
        produtos = [self.produto(), self.produto()]
        barreira = threading.Barrier(2)

        def vincular(produto):
            bd = BancoDados(self.path, backup_automatico=False, permitir_legado=True)
            try:
                c = ControladorEstoque(bd)
                barreira.wait(timeout=10)
                try:
                    c.vincular_codigo_barras("96385074", produto.id)
                    return True
                except ErroNegocio:
                    return False
            finally:
                bd.fechar()

        with ThreadPoolExecutor(max_workers=2) as pool:
            tarefas = [pool.submit(vincular, p) for p in produtos]
            self.assertCountEqual([t.result(timeout=20) for t in tarefas], [True, False])

    def test_desfazer_nao_reverte_acao_diferente_da_confirmada(self):
        p = self.produto()
        anterior = self.c.obter_ultima_acao().log.id
        self.c.registrar_saida(p.id, 1)
        with self.assertRaisesRegex(ErroNegocio, "histórico mudou"):
            self.c.desfazer_ultima_acao(log_id_esperado=anterior)
        self.assertEqual(self.c.obter_produto(p.id).estoque_atual, 9)

    def test_ajuste_nao_sobrescreve_tela_desatualizada(self):
        p = self.produto()
        self.c.registrar_saida(p.id, 1)
        with self.assertRaisesRegex(ErroNegocio, "após a seleção"):
            self.c.ajustar_produto(p.id, 20, estoque_esperado=10, custo_esperado=10)
        self.assertEqual(self.c.obter_produto(p.id).estoque_atual, 9)

    def test_falha_no_log_reverte_todos_os_tipos(self):
        p = self.produto()
        for acao in (lambda: self.c.registrar_entrada(p.id, 1, 20),
                     lambda: self.c.registrar_saida(p.id, 1),
                     lambda: self.c.ajustar_produto(p.id, 20, 30)):
            with patch.object(self.c.logs, "inserir", side_effect=RuntimeError("simulada")):
                with self.assertRaises(RuntimeError):
                    acao()
            atual = self.c.obter_produto(p.id)
            self.assertEqual((atual.estoque_atual, atual.custo_medio), (10, 10))
        self.assertEqual(len(self.c.listar_logs()), 1)

    def test_savepoint_reverte_apenas_operacao_interna(self):
        with self.bd.transacao():
            a = self.produto()
            try:
                with self.bd.transacao():
                    self.produto()
                    raise ValueError("simulada")
            except ValueError:
                pass
            b = self.produto()
        self.assertEqual([p.id for p in self.c.listar_produtos()], [a.id, b.id])
        self.assertEqual(len(self.c.listar_logs()), 2)

    def test_rollback_externo_reverte_operacoes_internas(self):
        with self.assertRaises(KeyboardInterrupt):
            with self.bd.transacao():
                self.produto()
                raise KeyboardInterrupt()
        self.assertEqual(self.c.listar_produtos(), [])
        self.assertFalse(self.bd.conexao.in_transaction)
        self.produto()

    def test_falha_commit_reverte_e_libera_conexao(self):
        original = self.bd.conexao

        class FalhaCommit:
            def __getattr__(self, name):
                return getattr(original, name)

            def execute(self, sql, *args):
                if sql == "COMMIT":
                    raise sqlite3.OperationalError("Falha de commit simulada")
                return original.execute(sql, *args)

        with patch.object(self.bd, "conexao", FalhaCommit()):
            with self.assertRaises(sqlite3.OperationalError):
                self.produto()
        self.assertFalse(original.in_transaction)
        self.assertEqual(self.c.listar_produtos(), [])
        self.produto()

    def test_banco_ocupado_gera_mensagem_e_nao_grava(self):
        p = self.produto()
        outro = BancoDados(self.path, backup_automatico=False, timeout=0.02, permitir_legado=True)
        try:
            with self.bd.transacao():
                with self.assertRaisesRegex(ErroNegocio, "banco está ocupado"):
                    ControladorEstoque(outro).registrar_saida(p.id, 1)
            self.assertEqual(self.c.obter_produto(p.id).estoque_atual, 10)
            ControladorEstoque(outro).registrar_saida(p.id, 1)
        finally:
            outro.fechar()

    def test_backup_inclui_wal_e_pode_ser_aberto_para_recuperacao(self):
        p = self.produto()
        self.c.vincular_codigo_barras("96385074", p.id)
        self.c.registrar_saida(p.id, 2)
        self.assertTrue(Path(str(self.path) + "-wal").is_file())
        backup = self.bd.criar_backup()
        self.c.registrar_entrada(p.id, 10)
        copia = BancoDados(backup, backup_automatico=False, permitir_legado=True)
        try:
            c = ControladorEstoque(copia)
            self.assertEqual(c.obter_produto(p.id).estoque_atual, 8)
            self.assertEqual(c.listar_codigos(p.id), ["96385074"])
            self.assertEqual(len(c.listar_logs()), 2)
            self.assertEqual(copia.buscar_todos("PRAGMA foreign_key_check"), [])
        finally:
            copia.fechar()

    def test_backups_unicos_e_automatico_na_reabertura(self):
        self.produto()
        a, b = self.bd.criar_backup(), self.bd.criar_backup()
        self.assertNotEqual(a, b)
        outro = BancoDados(self.path, permitir_legado=True)
        try:
            self.assertTrue(outro.ultimo_backup.is_file())
            self.assertNotIn(outro.ultimo_backup, (a, b))
        finally:
            outro.fechar()

    def test_backup_durante_transacao_rejeitado_sem_travar(self):
        with self.bd.transacao():
            with self.assertRaises(RuntimeError):
                self.bd.criar_backup()

    def test_migracao_legada_preserva_dados_e_cria_backup(self):
        p = self.produto()
        self.bd.executar("INSERT INTO Codigos_Barras VALUES ('legado', ?)", (p.id,))
        self.bd.executar("PRAGMA user_version = 0")
        outro = BancoDados(self.path, permitir_legado=True)
        try:
            self.assertEqual(outro.buscar_um("PRAGMA user_version")[0], BancoDados.VERSAO_ESQUEMA)
            self.assertEqual(ControladorEstoque(outro).listar_codigos(p.id), ["legado"])
            with closing(sqlite3.connect(outro.ultimo_backup)) as copia:
                self.assertEqual(copia.execute("PRAGMA user_version").fetchone()[0], 0)
                self.assertEqual(copia.execute("SELECT COUNT(*) FROM Produtos").fetchone()[0], 1)
        finally:
            outro.fechar()

    def test_versao_futura_recusada_sem_modificar_banco(self):
        self.produto()
        self.bd.executar("PRAGMA user_version = 99")
        with self.assertRaisesRegex(RuntimeError, "mais recente"):
            BancoDados(self.path, permitir_legado=True)
        self.assertEqual(self.bd.buscar_um("PRAGMA user_version")[0], 99)
        self.assertEqual(len(self.c.listar_produtos()), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
