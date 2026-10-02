"""Auditoria adicional de 01/10/2026. Não abre bancos de uso nem corrige o app.

Regressões da auditoria: devem passar após as correções.
Bases em memória/TemporaryDirectory; processos filhos usam somente essas bases.
"""
import csv
import hashlib
import math
from pathlib import Path
import random
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config
from controllers.controllers import ControladorEstoque, ControladorRelatorios, ErroNegocio
from models.models import BancoDados
from utils.gtin import validar_gtin
from views.view_cadastro import ViewCadastro
from views.view_operacao import ViewOperacao, OPCAO_ENTRADA, OPCAO_SAIDA


class AuditoriaAmpliada(unittest.TestCase):
    def setUp(self):
        self.bd = BancoDados(':memory:', permitir_legado=True)
        self.addCleanup(self.bd.fechar)
        self.c = ControladorEstoque(self.bd)
        self.r = ControladorRelatorios(self.bd)

    def produto(self, **kw):
        dados = dict(nome='Teste fictício', marca=config.MARCAS[0],
                     categoria=config.CATEGORIAS[0], preco_venda_base=30,
                     custo_inicial=10, quantidade_inicial=10, codigos=[])
        dados.update(kw)
        return self.c.cadastrar_produto(**dados)

    def test_1000_operacoes_com_modelo_independente(self):
        rng = random.Random(20261001)
        p = self.produto(quantidade_inicial=0)
        saldo, custo, pilha = 0, 10.0, []
        for _ in range(1000):
            acao = rng.choice(['entrada', 'saida', 'ajuste', 'desfazer'])
            anterior = (saldo, custo)
            if acao == 'entrada':
                qtd, valor = rng.randint(1, 20), rng.randint(0, 500) / 10
                novo_custo = round((saldo * custo + qtd * valor) / (saldo + qtd), 4)
                resultado = self.c.registrar_entrada(p.id, qtd, valor)
                saldo, custo = saldo + qtd, novo_custo
                pilha.append(anterior)
            elif acao == 'saida':
                qtd = rng.randint(1, 20)
                if qtd > saldo:
                    with self.assertRaises(ErroNegocio):
                        self.c.registrar_saida(p.id, qtd)
                else:
                    self.c.registrar_saida(p.id, qtd)
                    saldo -= qtd
                    pilha.append(anterior)
            elif acao == 'ajuste':
                novo_saldo, novo_custo = rng.randint(0, 100), rng.randint(0, 500) / 10
                if (novo_saldo, novo_custo) != anterior:
                    self.c.ajustar_produto(p.id, novo_saldo, novo_custo)
                    saldo, custo = novo_saldo, novo_custo
                    pilha.append(anterior)
            elif pilha:
                self.c.desfazer_ultima_acao()
                saldo, custo = pilha.pop()
            else:
                with self.assertRaises(ErroNegocio):
                    self.c.desfazer_ultima_acao()
            atual = self.c.obter_produto(p.id)
            self.assertEqual(atual.estoque_atual, saldo)
            self.assertAlmostEqual(atual.custo_medio, custo, places=8)
            self.assertEqual(self.r.obter_kpis()['total_itens'], saldo)
        self.assertEqual(self.bd.buscar_um('PRAGMA integrity_check')[0], 'ok')

    def test_400_gtins_e_3600_dvs_incorretos(self):
        rng = random.Random(42)
        for tamanho in (8, 12, 13, 14):
            for _ in range(100):
                corpo = ''.join(str(rng.randrange(10)) for _ in range(tamanho - 1))
                soma = sum(int(n) * (3 if i % 2 == 0 else 1)
                           for i, n in enumerate(reversed(corpo)))
                dv = str((-soma) % 10)
                codigo = corpo + dv
                self.assertEqual(validar_gtin(codigo), codigo)
                for outro in '0123456789':
                    if outro != dv:
                        with self.assertRaises(ValueError):
                            validar_gtin(corpo + outro)

    def test_rejeicao_atomica_de_lote_codigos(self):
        for codigos in (['96385074', 'invalido'], ['96385074', None]):
            with self.assertRaises(ErroNegocio):
                self.produto(codigos=codigos)
        self.assertEqual(self.c.listar_produtos(), [])
        self.assertEqual(self.c.listar_logs(), [])
        self.assertIsNone(self.c.resolver_codigo_barras('96385074'))

    def test_injecao_sql_nome_e_busca_tratada_como_texto(self):
        nome = "Produto'); DROP TABLE Produtos; --"
        p = self.produto(nome=nome)
        self.assertEqual(self.c.obter_produto(p.id).nome, nome)
        self.c.buscar_produtos("' OR 1=1 --")
        self.assertEqual(len(self.c.listar_produtos()), 1)
        with self.assertRaises(ValueError):
            self.r.relatorios.saidas_por_campo('marca; DROP TABLE Produtos')

    def test_relatorios_vazios(self):
        self.assertEqual(self.r.obter_kpis()['total_itens'], 0)
        self.assertEqual(self.r.curva_a(), [])
        self.assertEqual(self.r.estoque_parado(), [])
        self.assertEqual(self.r.ranking_marcas(), [])
        datas, entradas, saidas = self.r.movimentacao_ultimos_dias()
        self.assertEqual(len(datas), 30)
        self.assertEqual(sum(entradas) + sum(saidas), 0)

    def test_csv_preserva_texto_acentos_delimitadores_e_gtin(self):
        nome = 'Loção; "Especial"\nTeste'
        self.produto(nome=nome, codigos=['00123457'])
        with tempfile.TemporaryDirectory() as tmp:
            estoque, logs = self.r.exportar_csv(tmp)
            with estoque.open(encoding='utf-8-sig', newline='') as f:
                dados = list(csv.DictReader(f, delimiter=';'))
            self.assertEqual(dados[0]['nome'], nome)
            self.assertEqual(dados[0]['codigos_barras'], '00123457')
            self.assertTrue(logs.exists())

    def test_operacao_modo_rapido_registra_uma_unidade(self):
        p = self.produto(codigos=['96385074'])
        view = Mock(controlador=self.c)
        view.entrada_codigo.get.return_value = '96385074'
        view.var_modo_rapido.get.return_value = True
        view.entrada_quantidade.get.return_value = '1'
        view.entrada_custo.get.return_value = ''
        view.seletor_tipo.get.return_value = OPCAO_SAIDA
        view._confirmar.side_effect = lambda: ViewOperacao._confirmar(view)
        ViewOperacao._ao_ler_codigo(view)
        self.assertEqual(self.c.obter_produto(p.id).estoque_atual, 9)
        view.entrada_quantidade.insert.assert_called_with(0, '1')

    def test_interface_saida_insuficiente_exibe_erro_sem_gravar(self):
        p = self.produto()
        view = Mock(controlador=self.c, produto_atual=p)
        view.seletor_tipo.get.return_value = OPCAO_SAIDA
        view.entrada_quantidade.get.return_value = '11'
        ViewOperacao._confirmar(view)
        self.assertEqual(self.c.obter_produto(p.id).estoque_atual, 10)
        self.assertEqual(view._definir_status.call_args.args[1], 'erro')

    def test_defeito_falha_disco_na_operacao_nao_exibe_mensagem(self):
        view = Mock(produto_atual=self.produto())
        view.seletor_tipo.get.return_value = OPCAO_ENTRADA
        view.controlador.registrar_entrada.side_effect = sqlite3.OperationalError('database or disk is full')
        with patch('utils.erros.registrar_falha') as registro:
            ViewOperacao._confirmar(view)
        self.assertEqual(view._definir_status.call_args.args[1], 'erro')
        registro.assert_called_once()

    def test_falha_disco_durante_log_reverte_movimentacao(self):
        p = self.produto()
        with patch.object(self.c.logs, 'inserir', side_effect=sqlite3.OperationalError('disk I/O error')):
            with self.assertRaises(sqlite3.OperationalError):
                self.c.registrar_saida(p.id, 1)
        self.assertEqual(self.c.obter_produto(p.id).estoque_atual, 10)
        self.assertEqual(len(self.c.listar_logs()), 1)

    def test_operacoes_em_produto_inexistente_nao_gravam(self):
        for acao in (lambda: self.c.registrar_entrada(999, 1),
                     lambda: self.c.registrar_saida(999, 1),
                     lambda: self.c.ajustar_produto(999, 1),
                     lambda: self.c.vincular_codigo_barras('96385074', 999)):
            with self.assertRaises(ErroNegocio):
                acao()
        self.assertEqual(self.c.listar_logs(), [])

    def test_fk_impede_codigo_e_log_orfaos(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.codigos.vincular('96385074', 999)
        self.assertEqual(self.bd.buscar_todos('PRAGMA foreign_key_check'), [])

    def test_defeito_quantidade_fora_int64_deveria_gerar_erro_negocio(self):
        with self.assertRaises(ErroNegocio):
            self.produto(quantidade_inicial=str(2**63))

    def test_overflow_quantidade_nao_deixa_cadastro_parcial(self):
        with self.assertRaises(ErroNegocio):
            self.produto(quantidade_inicial=str(2**63), codigos=['96385074'])
        self.assertEqual(self.c.listar_produtos(), [])
        self.assertEqual(self.c.listar_logs(), [])

    def test_defeito_soma_saldos_permitidos_quebra_kpis(self):
        self.produto(quantidade_inicial=2**62, custo_inicial=0)
        self.produto(quantidade_inicial=2**62, custo_inicial=0)
        self.assertEqual(self.r.obter_kpis()['total_itens'], 2**63)

    def test_defeito_valor_finito_produz_total_infinito(self):
        with self.assertRaises(ErroNegocio):
            self.produto(custo_inicial='1e308', quantidade_inicial=2)
        self.assertTrue(math.isfinite(self.r.obter_kpis()['valor_investido']))
        self.assertEqual(self.c.listar_produtos(), [])

    def test_defeito_entrada_sem_custo_altera_custo_preciso(self):
        p = self.produto(custo_inicial='10,123456')
        self.assertEqual(self.c.registrar_entrada(p.id, 1, '').custo_novo, p.custo_medio)

    def test_defeito_sugestao_categoria_permanece_apos_apagar_nome(self):
        view = Mock(_categoria_manual=False, _marca_manual=False)
        categoria = {'valor': ''}
        view.combo_categoria.set.side_effect = lambda v: categoria.update(valor=v)
        view.var_nome.get.return_value = 'Shampoo'
        ViewCadastro._ao_digitar_nome(view)
        self.assertEqual(categoria['valor'], 'Cabelos')
        view.var_nome.get.return_value = ''
        ViewCadastro._ao_digitar_nome(view)
        self.assertEqual(categoria['valor'], '')

    def test_defeito_relatorios_e_busca_admin_limitados_sem_aviso(self):
        with self.bd.transacao():
            for i in range(501):
                self.produto(nome=f'Produto {i:04}', quantidade_inicial=0)
        self.assertEqual(len(self.c.listar_produtos()), 501)
        self.assertEqual(len(self.c.buscar_produtos('')), 501)

    def test_defeito_csv_estoque_e_logs_sem_snapshot_unico(self):
        # A escrita concorrente deve usar OUTRA conexão, como uma segunda instância.
        # Escrever na mesma conexão deliberadamente alteraria seu próprio snapshot.
        with tempfile.TemporaryDirectory() as tmp:
            bd1 = BancoDados(Path(tmp) / 'teste.db', backup_automatico=False, permitir_legado=True)
            bd2 = BancoDados(Path(tmp) / 'teste.db', backup_automatico=False, permitir_legado=True)
            try:
                c1, c2 = ControladorEstoque(bd1), ControladorEstoque(bd2)
                p = c1.cadastrar_produto('Fictício', config.MARCAS[0], config.CATEGORIAS[0], 30, 10, 10)
                r = ControladorRelatorios(bd1)
                original = r.produtos.listar_para_exportacao
                def ler_e_movimentar():
                    linhas = original()
                    c2.registrar_saida(p.id, 1)
                    return linhas
                with patch.object(r.produtos, 'listar_para_exportacao', side_effect=ler_e_movimentar):
                    estoque, logs = r.exportar_csv(Path(tmp) / 'csv')
                self.assertEqual(c2.obter_produto(p.id).estoque_atual, 9)
            finally:
                bd2.fechar()
                bd1.fechar()
            with estoque.open(encoding='utf-8-sig', newline='') as f:
                saldo = int(next(csv.DictReader(f, delimiter=';'))['estoque_atual'])
            with logs.open(encoding='utf-8-sig', newline='') as f:
                ultimo = int(next(csv.DictReader(f, delimiter=';'))['estoque_posterior'])
            self.assertEqual(saldo, ultimo)

    def test_defeito_csv_texto_pode_ser_interpretado_como_formula(self):
        self.produto(nome='=1+1')
        with tempfile.TemporaryDirectory() as tmp:
            estoque, _ = self.r.exportar_csv(tmp)
            with estoque.open(encoding='utf-8-sig', newline='') as f:
                nome = next(csv.DictReader(f, delimiter=';'))['nome']
            self.assertFalse(nome.startswith(('=', '+', '-', '@')))

    def test_defeito_csv_falha_segundo_arquivo_deixa_par_incompleto(self):
        import pandas as pd
        original = pd.DataFrame.to_csv
        def gravar(df, destino, **opcoes):
            if Path(destino).name.startswith('backup_logs'):
                raise OSError('Falha de escrita simulada')
            return original(df, destino, **opcoes)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(pd.DataFrame, 'to_csv', new=gravar):
                with self.assertRaises(OSError):
                    self.r.exportar_csv(tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [])


class AuditoriaPersistencia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.path = self.base / 'somente_teste.db'
        with closing(BancoDados(self.path, backup_automatico=False, permitir_legado=True).conexao) as con:
            con.execute('INSERT INTO Produtos(nome,marca,categoria,estoque_atual,custo_medio) VALUES (?,?,?,?,?)',
                        ('Fictício', config.MARCAS[0], config.CATEGORIAS[0], 10, 10))

    def abrir(self):
        bd = BancoDados(self.path, backup_automatico=False, permitir_legado=True)
        self.addCleanup(bd.fechar)
        return bd

    def filho_interrompido(self, confirmado):
        # os._exit evita finally/fechamento normal; não simula defeito físico do disco.
        codigo = '''
import os, sys
from models.models import BancoDados
from controllers.controllers import ControladorEstoque
bd = BancoDados(sys.argv[1], backup_automatico=False, permitir_legado=True)
c = ControladorEstoque(bd)
if sys.argv[2] == 'sim':
    c.registrar_entrada(1, 3, 20)
else:
    with bd.transacao():
        c.registrar_entrada(1, 3, 20)
        os._exit(71)
os._exit(72)
'''
        r = subprocess.run([sys.executable, '-B', '-c', codigo, str(self.path),
                            'sim' if confirmado else 'nao'], cwd=ROOT,
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 72 if confirmado else 71, r.stderr)

    def test_encerramento_abrupto_antes_commit_reverte(self):
        self.filho_interrompido(False)
        bd = self.abrir()
        c = ControladorEstoque(bd)
        self.assertEqual(c.obter_produto(1).estoque_atual, 10)
        self.assertEqual(c.listar_logs(), [])
        self.assertEqual(bd.buscar_um('PRAGMA integrity_check')[0], 'ok')

    def test_encerramento_abrupto_apos_commit_preserva(self):
        self.filho_interrompido(True)
        bd = self.abrir()
        c = ControladorEstoque(bd)
        self.assertEqual(c.obter_produto(1).estoque_atual, 13)
        self.assertEqual(len(c.listar_logs()), 1)
        self.assertEqual(bd.buscar_um('PRAGMA integrity_check')[0], 'ok')

    def test_backup_restaurado_permite_continuar_operando(self):
        bd = self.abrir()
        c = ControladorEstoque(bd)
        c.registrar_entrada(1, 4, 20)
        backup = bd.criar_backup(self.base / 'backups')
        restaurado = BancoDados(backup, backup_automatico=False, permitir_legado=True)
        try:
            novo = ControladorEstoque(restaurado)
            self.assertEqual(novo.registrar_saida(1, 2).estoque_novo, 12)
            self.assertEqual(c.obter_produto(1).estoque_atual, 14)
            self.assertEqual(restaurado.buscar_todos('PRAGMA foreign_key_check'), [])
        finally:
            restaurado.fechar()

    def test_arquivo_corrompido_recusado_sem_sobrescrever(self):
        alvo = self.base / 'corrompido.db'
        alvo.write_bytes(b'arquivo ficticio invalido')
        antes = hashlib.sha256(alvo.read_bytes()).hexdigest()
        with self.assertRaises(sqlite3.DatabaseError):
            BancoDados(alvo, permitir_legado=True)
        self.assertEqual(hashlib.sha256(alvo.read_bytes()).hexdigest(), antes)

    def test_falha_backup_impede_abertura_preservando_dados(self):
        with patch.object(BancoDados, 'criar_backup', side_effect=OSError('disco cheio simulado')):
            with self.assertRaises(OSError):
                BancoDados(self.path, permitir_legado=True)
        self.assertEqual(ControladorEstoque(self.abrir()).obter_produto(1).estoque_atual, 10)

    def test_defeito_remocao_codigo_com_tela_antiga_remove_novo_dono(self):
        c1 = ControladorEstoque(self.abrir())
        c2 = ControladorEstoque(self.abrir())
        c1.vincular_codigo_barras('96385074', 1)
        # A primeira tela guarda a lista antiga enquanto a segunda transfere o código.
        lista_antiga = c1.listar_codigos(1)
        p2 = c2.cadastrar_produto('Outro', config.MARCAS[0], config.CATEGORIAS[0], 20, 10)
        c2.desvincular_codigo_barras('96385074')
        c2.vincular_codigo_barras('96385074', p2.id)
        with self.assertRaises(ErroNegocio):
            c1.desvincular_codigo_barras(lista_antiga[0], produto_id_esperado=1)
        atual = c2.resolver_codigo_barras('96385074')
        self.assertIsNotNone(atual)
        self.assertEqual(atual.id, p2.id)

    def test_defeito_rebuild_apaga_dados_dentro_dist(self):
        from gerar_build import gerar_build
        alvo = (self.base / 'dist' / 'GestorEstoque').resolve()
        self.assertTrue(alvo.is_relative_to(self.base))
        dados = alvo / 'dados'
        dados.mkdir(parents=True)
        banco = dados / 'estoque.db'
        banco.write_bytes(b'SENTINELA FICTICIA, NAO E BANCO DE USO')
        def empacotar(comando, **kwargs):
            destino = Path(comando[comando.index('--distpath') + 1]).resolve()
            self.assertTrue(destino.is_relative_to(self.base))
            self.assertNotEqual(destino, alvo.parent)
            self.assertFalse((destino / 'GestorEstoque').exists())
            novo = destino / 'GestorEstoque' / 'GestorEstoque.exe'
            novo.parent.mkdir()
            novo.write_bytes(b'EXE FICTICIO')
        primeiro = gerar_build(self.base, executar=empacotar)
        segundo = gerar_build(self.base, executar=empacotar)
        self.assertNotEqual(primeiro, segundo)
        self.assertTrue(primeiro.exists())
        self.assertTrue(banco.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
