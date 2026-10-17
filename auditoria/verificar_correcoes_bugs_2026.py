"""Regressões da auditoria de 17/10/2026, exclusivamente em raízes descartáveis."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import threading
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from servico.cliente import Cliente
from servico.nucleo import Nucleo
from servico.protocolo import VERSAO, decodificar

RAIZ = Path(__file__).resolve().parents[1]


class Instalador(unittest.TestCase):
    def test_bug01_reinstalacao_powershell_51(self):
        # Executa somente o trecho de operadores do instalador, nunca serviços/ACLs.
        fonte = (RAIZ / 'instalador/servico.ps1').read_text(encoding='utf-8-sig')
        trecho = fonte[fonte.index("    $operadoresJson ="):fonte.index('    # Exportações')]
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            script = raiz / 'verificar.ps1'
            script.write_text("$ErrorActionPreference = 'Stop'\n"
                              "if ($PSVersionTable.PSVersion.Major -ne 5) { throw 'Exige Windows PowerShell 5.1' }\n"
                              "$raizDados = $PSScriptRoot\n"
                              "foreach ($s in 'S-1-5-21-1-2-3-1001','S-1-5-21-1-2-3-1002','S-1-5-21-1-2-3-1001') {\n"
                              "$sidOperador = [Security.Principal.SecurityIdentifier]::new($s)\n" + trecho + "\n}\n",
                              encoding='utf-8-sig')
            subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'),
                            '-NoProfile', '-NonInteractive', '-File', str(script)],
                           check=True, capture_output=True, timeout=30)
            operadores = json.loads((raiz / 'operadores.json').read_text(encoding='utf-8-sig'))
            self.assertTrue(all(isinstance(s, str) for s in operadores), operadores)
            self.assertCountEqual(operadores, ['S-1-5-21-1-2-3-1001', 'S-1-5-21-1-2-3-1002'])

    def test_bug01_consumidor_rejeita_estrutura_invalida(self):
        from servico.pipe import atributos, sid_atual
        import win32security
        sid = win32security.ConvertStringSidToSid(sid_atual())
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / 'operadores.json'
            for valor in ([{'value': ['S-1-5-18'], 'Count': 1}], {'sid': 'S-1-5-18'}, [8]):
                with self.subTest(valor=valor):
                    arquivo.write_text(json.dumps(valor), encoding='utf-8')
                    with patch('servico.pipe.win32security.LookupAccountName', return_value=(sid, '', 1)):
                        with self.assertRaisesRegex(ValueError, 'operadores'):
                            atributos(True, pasta)


class ServicoLocal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.n = Nucleo(self.raiz)
        self.addCleanup(self.n.fechar)
        self.cliente = Cliente(self.raiz)
        self.transporte = patch('servico.cliente.chamar', side_effect=self.entregar)
        self.transporte.start()
        self.addCleanup(self.transporte.stop)
        self.cliente.abrir('', 'senha-teste-2026', 'senha-teste-2026')

    def entregar(self, nome, pedido, producao):
        return self.n.executar(pedido, 'S-1-5-21-1-2-3-1001')

    def produto(self, **kwargs):
        return self.cliente.chamar('estoque.cadastrar_produto', 'Produto', 'Natura', 'Perfumaria', **kwargs)

    def popular(self, produtos, eventos):
        with self.n.cofre.banco.transacao() as con:
            con.executemany('INSERT INTO Produtos(id,nome,marca,categoria,estoque_atual) VALUES(?,?,?,?,10)',
                            ((i, f'Produto {i}', 'Natura', 'Perfumaria') for i in range(1, produtos + 1)))
            con.executemany('INSERT INTO Eventos_Estoque(chave,produto_id,delta,origem,natureza) VALUES(?,?,?,?,?)',
                            ((f'fixture:{i}', i % produtos + 1, 10 if i < produtos else 0, 'FISICO', 'ABERTURA')
                             for i in range(eventos)))
        self.n.motor.preparar()

    def test_bug02_nova_venda_apos_resposta_perdida(self):
        from models.seguranca import ErroSeguranca
        p = self.produto(quantidade_inicial=10)
        def perder(*args):
            self.entregar(*args)
            raise OSError('Resposta perdida após commit')
        with patch('servico.cliente.chamar', side_effect=perder):
            with self.assertRaises(ErroSeguranca):
                self.cliente.chamar('estoque.registrar_saida', p.id, 1)
        self.cliente.chamar('estoque.registrar_saida', p.id, 1)
        self.assertEqual(self.cliente.chamar('estoque.obter_produto', p.id).estoque_atual, 8)

    def test_bug02_repeticao_imediata_preserva_id(self):
        p = self.produto(quantidade_inicial=10)
        ids = []
        def perder_uma(nome, pedido, producao):
            ids.append(pedido['id'])
            resposta = self.entregar(nome, pedido, producao)
            if len(ids) == 1:
                raise OSError('Resposta perdida após commit')
            return resposta
        with patch('servico.cliente.chamar', side_effect=perder_uma):
            resultado = self.cliente.chamar('estoque.registrar_saida', p.id, 1)
        self.assertEqual(len(ids), 2)
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(resultado.estoque_novo, 9)

    def test_bug02_importacao_identica_e_nova_acao(self):
        from auditoria.verificar_gestao_dados import csv_bytes, linha
        from servico.transferencia import Transferencia
        arquivo = self.raiz / 'entrada.csv'
        arquivo.write_bytes(csv_bytes([linha()]))
        def perder(nome, pedido, producao):
            resposta = self.entregar(nome, pedido, producao)
            if pedido['comando'] == 'dados.passo' and resposta.get('resultado', {}).get('concluido'):
                raise OSError('Resposta perdida após commit')
            return resposta
        with patch('servico.transferencia.chamar', side_effect=perder):
            with self.assertRaises(OSError):
                Transferencia(self.cliente).executar('importar', arquivo, 'senha-teste-2026', lambda *p: None)
        with patch('servico.transferencia.chamar', side_effect=self.entregar):
            Transferencia(self.cliente).executar('importar', arquivo, 'senha-teste-2026', lambda *p: None)
        self.assertEqual(self.cliente.chamar('estoque.obter_produto', 1).estoque_atual, 6)

    def test_bug03_venda_6000_produtos_50000_eventos(self):
        self.popular(6000, 50000)
        tempos = []
        for _ in range(3):
            inicio = time.perf_counter()
            self.cliente.chamar('estoque.registrar_saida', 6000, 1)
            tempos.append(time.perf_counter() - inicio)
        self.assertLess(max(tempos), .050, f'Tempos em segundos: {tempos}')
        self.assertEqual(self.n.motor.linha('SELECT sum(delta) saldo FROM Eventos_Estoque WHERE produto_id=6000')['saldo'], 7)

    def test_bug03_v2_migra_reabre_e_restaura_backup(self):
        from auditoria.verificar_gestao_dados import consumir
        from gestao import backup
        from models.models import BancoDados
        from models.seguranca import validar_esquema_legado
        p = self.produto(quantidade_inicial=10)
        con = self.n.cofre.banco.conexao
        for nome in ('idx_eventos_produto', 'idx_eventos_log'):
            con.execute(f'DROP INDEX IF EXISTS {nome}')
        con.execute('PRAGMA user_version=2')
        validar_esquema_legado(con)
        conteudo, _ = consumir(backup.exportar(self.n.cofre.banco))
        pacote = json.loads(conteudo)
        pacote['esquema'] = 2
        self.n.fechar()
        self.cliente.abrir('senha-teste-2026')
        con = self.n.cofre.banco.conexao
        self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0], 3)
        validar_esquema_legado(con)
        for coluna in ('produto_id', 'log_id'):
            plano = str([tuple(r) for r in con.execute(f'EXPLAIN QUERY PLAN SELECT id FROM Eventos_Estoque WHERE {coluna}=?', (1,))])
            self.assertIn('USING COVERING INDEX', plano)
        consumir(backup.restaurar(self.n.cofre, json.dumps(pacote).encode(), lambda r: None))
        self.assertEqual(self.n.motor.estoque.obter_produto(p.id).estoque_atual, 10)
        validar_esquema_legado(con)

    def test_bug03_metodos_isolam_produto_e_compensam(self):
        p = self.produto(quantidade_inicial=10, codigos=['7891000100103'])
        with patch.object(self.n.motor.estoque, 'listar_produtos', side_effect=AssertionError('Varredura global')):
            self.cliente.chamar('estoque.registrar_entrada', produto_id=p.id, quantidade=2)
            self.cliente.chamar('estoque.desfazer_ultima_acao')
            self.cliente.chamar('estoque.desvincular_codigo_barras', '7891000100103')
            self.cliente.chamar('estoque.vincular_codigo_barras', '7891000100103', p.id)
            novo = self.produto(quantidade_inicial=2)
        self.assertEqual(self.n.motor.saldo(p.id)['em_maos'], 10)
        self.assertEqual(self.n.motor.linha('SELECT sum(delta) saldo FROM Eventos_Estoque WHERE produto_id=?', (novo.id,))['saldo'], 2)

    def test_bug04_primeira_pagina_50000_logs(self):
        self.popular(1, 1)
        con = self.n.cofre.banco.conexao
        with self.n.cofre.banco.transacao():
            con.executemany("INSERT INTO Logs_Movimentacao(id,produto_id,tipo,quantidade,data_hora) VALUES(?,1,'Ajuste',0,'2026-10-17 12:00:00')",
                            ((i,) for i in range(1, 50001)))
            con.executemany("INSERT INTO Eventos_Estoque(chave,produto_id,delta,origem,natureza,log_id) VALUES(?,1,0,'FISICO','AJUSTE',?)",
                            ((f'log:{i}', i) for i in range(1, 50001)))
        consultas = []
        con.set_trace_callback(consultas.append)
        self.addCleanup(con.set_trace_callback, None)
        inicio = time.perf_counter()
        pagina = self.cliente.chamar('estoque.listar_logs')
        duracao = time.perf_counter() - inicio
        self.assertEqual(len(pagina), 200)
        self.assertLess(duracao, 1)
        self.assertLessEqual(sum(q.lstrip().upper().startswith('SELECT') for q in consultas), 1)
        proxima = self.cliente.chamar('estoque.listar_logs', antes_id=pagina[-1]['id'])
        self.assertEqual(proxima[0]['id'], 49800)
        self.assertEqual(pagina[0]['origem'], 'FISICO')

    def test_bug04_leitura_sem_resposta_preserva_sessao(self):
        from models.seguranca import ErroSeguranca
        self.cliente.ao_indisponivel = Mock()
        sessao = self.cliente.sessao
        with patch('servico.cliente.chamar', side_effect=OSError('Transporte interrompido')):
            with self.assertRaises(ErroSeguranca):
                self.cliente.chamar('estoque.listar_logs')
        self.cliente.ao_indisponivel.assert_not_called()
        self.assertEqual(self.cliente.sessao, sessao)

    def test_bug04_catalogo_transfere_paginas_limitadas(self):
        self.popular(1201, 1201)
        tamanhos = []
        def medir(nome, pedido, producao):
            resposta = self.entregar(nome, pedido, producao)
            resultado = decodificar(resposta['resultado'])
            tamanhos.append(len(resultado.produtos if hasattr(resultado, 'produtos') else resultado))
            return resposta
        estoque, _ = self.cliente.criar_controladores()
        with patch('servico.cliente.chamar', side_effect=medir):
            for metodo, args in ((estoque.listar_produtos, ()), (estoque.buscar_produtos, ('',)),
                                 (estoque.pesquisar_produtos, ('',))):
                resultado = metodo(*args)
                self.assertEqual(len(resultado.produtos if hasattr(resultado, 'produtos') else resultado), 1201)
        self.assertLessEqual(max(tamanhos), 200)

    def test_bug06_manutencao_800_produtos_limitada_e_progride(self):
        self.popular(800, 800)
        self.cliente.chamar('integracoes.ativar_simulacao')
        self.cliente.chamar('integracoes.catalogo_exemplo')
        with self.n.simulacao.bd.transacao():
            for pid in range(1, 801):
                self.n.simulacao.vincular(f'SHOPEE:{pid}', pid)
                self.n.simulacao.vincular(f'TIKTOK:{pid}', pid)
        self.cliente.chamar('integracoes.iniciar_ensaio')
        tempos = []
        for _ in range(250):
            inicio = time.perf_counter()
            self.n.manutencao()
            tempos.append(time.perf_counter() - inicio)
            self.assertLess(tempos[-1], .200, f'Manutenção levou {tempos[-1]:.4f}s')
            self.assertEqual(self.cliente.chamar('status')['servico'], 'online')
            if self.n.simulacao.con.execute('SELECT sum(confirmada) FROM Estado_SKU_Canal').fetchone()[0] == 4000:
                break
        else:
            self.fail('O trabalho limitado não avançou até todos os 800 produtos')
        self.assertFalse(self.n.simulacao.bd.conexao.in_transaction)

    def encerrar_simulacao(self):
        from controllers.controllers import ErroNegocio
        try:
            self.cliente.chamar('integracoes.encerrar')
        except ErroNegocio:
            pass   # o worker conclui o encerramento nos próximos ciclos
        for _ in range(100):
            if self.n.simulacao is None:
                return
            self.n.manutencao()
            time.sleep(.02)
        self.fail('Simulação não encerrou')

    def estado_multicanal(self):
        return self.n.cofre.banco.conexao.execute('SELECT estado FROM Config_Multicanal').fetchone()[0]

    def test_bug14_reativar_simulacao_usa_estoque_atual(self):
        self.produto(quantidade_inicial=1)
        self.cliente.chamar('integracoes.ativar_simulacao')
        self.encerrar_simulacao()
        self.cliente.chamar('estoque.cadastrar_produto', 'Produto pós-laboratório', 'Avon', 'Maquiagem')
        painel = self.cliente.chamar('integracoes.ativar_simulacao')
        nomes = [p['nome'] for p in painel['simulacao']['produtos']]
        self.assertIn('Produto pós-laboratório', nomes)
        self.encerrar_simulacao()

    def test_bug14_retomada_preserva_simulacao_em_andamento(self):
        self.cliente.chamar('integracoes.ativar_simulacao')
        self.cliente.chamar('integracoes.catalogo_exemplo')
        self.cliente.chamar('estoque.cadastrar_produto', 'Produto fora do ensaio', 'Avon', 'Maquiagem')
        painel = self.cliente.chamar('integracoes.ativar_simulacao')   # já configurando: não recria
        self.assertNotIn('Produto fora do ensaio', [p['nome'] for p in painel['simulacao']['produtos']])
        self.encerrar_simulacao()

    def test_bug15_transicoes_invalidas_sao_recusadas(self):
        from controllers.controllers import ErroNegocio
        self.cliente.chamar('integracoes.ativar_simulacao')
        with self.assertRaises(ErroNegocio):
            self.cliente.chamar('integracoes.pausar')
        self.assertEqual(self.estado_multicanal(), 'MULTICANAL_CONFIGURANDO')
        self.cliente.chamar('integracoes.iniciar_ensaio')
        with self.assertRaises(ErroNegocio):
            self.cliente.chamar('integracoes.ativar_simulacao')
        self.assertEqual(self.estado_multicanal(), 'MULTICANAL_ATIVO')
        self.cliente.chamar('integracoes.pausar')
        self.cliente.chamar('integracoes.iniciar_ensaio')
        with self.n.cofre.banco.transacao() as con:
            con.execute("UPDATE Config_Multicanal SET estado='ENCERRANDO_MULTICANAL'")
        for acao in ('iniciar_ensaio', 'pausar', 'ativar_simulacao'):
            with self.subTest(acao=acao):
                with self.assertRaises(ErroNegocio):
                    self.cliente.chamar('integracoes.' + acao)
                self.assertEqual(self.estado_multicanal(), 'ENCERRANDO_MULTICANAL')
        self.encerrar_simulacao()
        self.assertEqual(self.estado_multicanal(), 'FISICO')

    def iniciar_job_orfao(self):
        operacao = str(uuid4())
        resposta = self.n.executar(dict(v=VERSAO, id=str(uuid4()), sessao=self.cliente.sessao, comando='dados.iniciar',
                                        args=[operacao, 'importar', 'senha-teste-2026', 10, 'a' * 64], kwargs={}),
                                   'S-1-5-21-1-2-3-1001')
        self.assertTrue(resposta['ok'], resposta)
        self.cliente.sessao = None   # a interface morreu sem liberar o job

    def test_bug19_job_ativo_ainda_bloqueia_login(self):
        self.iniciar_job_orfao()
        with self.assertRaisesRegex(ValueError, 'Gestão de dados em andamento'):
            self.cliente.abrir('senha-teste-2026')

    def test_bug19_job_abandonado_e_revertido_no_login(self):
        self.iniciar_job_orfao()
        self.n.gestao.job['uso'] -= 61
        self.cliente.abrir('senha-teste-2026')
        self.assertFalse(self.n.gestao.ocupado)
        self.assertEqual(self.cliente.chamar('estoque.listar_produtos'), [])

    def test_bug19_passo_longo_nao_conta_como_abandono(self):
        def exportacao_lenta(_banco):
            time.sleep(.2)
            yield ('Exportação de registros', 1, 1)
            return b'{}'
        self.n.gestao.job = None
        resposta = self.n.executar(dict(v=VERSAO, id=str(uuid4()), sessao=self.cliente.sessao, comando='dados.iniciar',
                                        args=[str(uuid4()), 'exportar', 'senha-teste-2026'], kwargs={}),
                                   'S-1-5-21-1-2-3-1001')
        operacao = resposta['resultado']['id']
        inicio = time.monotonic()
        with patch('gestao.backup.exportar', exportacao_lenta):
            self.n.gestao.comando(self.cliente.sessao, 'passo', operacao)
        self.assertGreaterEqual(self.n.gestao.job['uso'] - inicio, .2)
        self.n.gestao.fechar()

    def test_bug29_limitador_de_login_por_identidade(self):
        from models.seguranca import ErroSeguranca
        self.cliente.fechar()
        login = lambda senha, identidade: self.n.executar(dict(v=VERSAO, id=str(uuid4()), sessao=None, comando='login',
                                                              args=[senha, None, None], kwargs={}), identidade)
        self.assertFalse(login('errada', 'S-1-5-21-1-2-3-1001')['ok'])
        self.assertIn('Aguarde', login('senha-teste-2026', 'S-1-5-21-1-2-3-1001')['mensagem'])
        self.assertTrue(login('senha-teste-2026', 'S-1-5-21-1-2-3-1002')['ok'])   # outra conta não é afetada

    def test_bug29_troca_de_senha_tem_limitador(self):
        from models.seguranca import ErroSeguranca
        self.cliente.ao_indisponivel = Mock()
        with self.assertRaisesRegex(ValueError, 'senha atual.*incorreta'):
            self.cliente.alterar_senha('errada', 'senha-nova-2026', 'senha-nova-2026')
        with self.assertRaisesRegex(ErroSeguranca, 'Aguarde'):
            self.cliente.alterar_senha('senha-teste-2026', 'senha-nova-2026', 'senha-nova-2026')
        self.assertTrue(self.n.cofre.verificar_senha('senha-teste-2026'))
        self.cliente.ao_indisponivel.assert_not_called()
        self.n.tentativas.clear()
        self.cliente.alterar_senha('senha-teste-2026', 'senha-nova-2026', 'senha-nova-2026')
        self.assertEqual(self.n.tentativas, {})

    def test_bug29_tela_exibe_motivo_da_recusa(self):
        from models.seguranca import ErroSeguranca
        from views.view_configuracoes import ViewConfiguracoes
        tela = Mock(_salvando=False)
        tela.janela.preferencias.alterar_senha.side_effect = ErroSeguranca('Aguarde antes de tentar novamente.')
        ViewConfiguracoes._alterar_senha(tela)
        self.assertEqual(tela.mensagem.configure.call_args.kwargs['text'], 'Aguarde antes de tentar novamente.')

    def test_bug07_senha_atual_errada_preserva_sessao(self):
        self.cliente.ao_indisponivel = Mock()
        with self.assertRaisesRegex(ValueError, 'senha atual.*incorreta'):
            self.cliente.alterar_senha('errada', 'senha-nova-2026', 'senha-nova-2026')
        self.cliente.ao_indisponivel.assert_not_called()
        self.assertEqual(self.cliente.chamar('estoque.listar_produtos'), [])
        self.assertTrue(self.n.cofre.verificar_senha('senha-teste-2026'))

    def test_bug07_somente_sessao_invalida_bloqueia(self):
        from models.seguranca import ErroSeguranca
        self.cliente.ao_indisponivel = Mock()
        with patch.object(self.n.cofre, 'alterar_senha', side_effect=ErroSeguranca('Envelope inválido.')):
            with self.assertRaises(ErroSeguranca):
                self.cliente.alterar_senha('senha-teste-2026', 'senha-nova-2026', 'senha-nova-2026')
        self.cliente.ao_indisponivel.assert_not_called()
        self.n.sessoes.clear()
        from models.seguranca import ErroSessao
        with self.assertRaisesRegex(ErroSessao, 'Sessão bloqueada'):   # BUG-17: tipo próprio na interface
            self.cliente.chamar('estoque.listar_produtos')
        self.cliente.ao_indisponivel.assert_called_once()

    def test_bug08_backup_indisponivel_nao_impede_login(self):
        self.cliente.fechar()
        backups = self.raiz / 'backups'
        backups.rename(self.raiz / 'backups_preservados')
        backups.write_text('obstrução fictícia', encoding='utf-8')
        self.cliente.abrir('senha-teste-2026')
        self.assertEqual(self.n.tentativas, {})
        self.assertIn('Backup diário', self.cliente.ultimo_status['aviso'])
        self.assertIn('Backup diário', self.cliente.chamar('status')['aviso'])
        self.assertIsNotNone(self.n.cofre.banco)
        log = (self.raiz / 'logs/erros.log').read_text(encoding='utf-8')   # BUG-13: log do agente
        self.assertIn('Error', log)
        self.assertNotIn('senha-teste-2026', log)
        self.cliente.fechar()
        from models.seguranca import ErroSeguranca
        with self.assertRaises(ErroSeguranca):
            self.cliente.abrir('errada')
        falhas, liberado = self.n.tentativas['S-1-5-21-1-2-3-1001']   # BUG-29: limitador por identidade
        self.assertEqual(falhas, 1)
        self.assertGreater(liberado, time.monotonic())

    def test_bug08_falha_operacional_nao_conta_como_senha(self):
        from models.seguranca import ErroSeguranca
        self.cliente.fechar()
        with patch.object(self.n.cofre, '_abrir_chave', side_effect=OSError('Disco indisponível')):
            with self.assertRaises(ErroSeguranca):
                self.cliente.abrir('senha-teste-2026')
        self.assertEqual(self.n.tentativas, {})


class Retencao(unittest.TestCase):
    def test_bug27_mantem_somente_os_backups_mais_recentes(self):
        import config
        from servico.cofre import CofreServico
        with tempfile.TemporaryDirectory() as pasta:
            cofre = CofreServico(pasta)
            cofre.abrir('', 'senha-teste-2026', 'senha-teste-2026')
            cofre.fechar()
            backups = Path(pasta) / 'backups'
            for dia in range(config.BACKUPS_MANTIDOS + 5):
                antiga = backups / f'GiStocker_2020{dia // 28 + 1:02}{dia % 28 + 1:02}_{dia:032x}.gsbackup'
                antiga.write_bytes(b'copia antiga')
                os.utime(antiga, (1_600_000_000 + dia, 1_600_000_000 + dia))
            preservado = backups / 'estoque_20200101.db.abc.gsa'
            preservado.write_bytes(b'legado')
            for hoje in backups.glob(f'GiStocker_{time.strftime("%Y%m%d", time.gmtime())}_*.gsbackup'):
                hoje.unlink()   # força o backup diário da próxima abertura
            cofre.abrir('senha-teste-2026')
            cofre.fechar()
            copias = sorted(backups.glob('GiStocker_*.gsbackup'), key=lambda p: p.stat().st_mtime_ns)
            self.assertEqual(len(copias), config.BACKUPS_MANTIDOS)
            self.assertIn(time.strftime('%Y%m%d', time.gmtime()), copias[-1].name)   # o de hoje fica
            self.assertNotIn(f'{0:032x}', ' '.join(p.name for p in copias))         # o mais antigo sai
            self.assertTrue(preservado.exists())


class Legado(unittest.TestCase):
    def test_bug28_exportacoes_legadas_ficam_na_instalacao(self):
        from servico.cofre import CofreServico
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta) / 'GiStocker'
            with patch('config.INSTALADO', True):
                self.assertTrue(CofreServico(raiz).legado.exportacoes.is_relative_to(raiz.resolve()))
            with patch('config.INSTALADO', False):   # portátil: <pasta>/dados + <pasta>/exportacoes
                self.assertEqual(CofreServico(raiz).legado.exportacoes, raiz.resolve().parent / 'exportacoes')

    def test_bug28_importacao_portatil_preserva_tema(self):
        from servico.importacao import importar_portatil
        with tempfile.TemporaryDirectory() as pasta:
            origem, destino = Path(pasta) / 'dados', Path(pasta) / 'ProgramData'
            origem.mkdir()
            (origem / 'estoque.db').write_bytes(os.urandom(64))   # SQLCipher não tem cabeçalho legível
            (origem / 'configuracoes.db').write_bytes(os.urandom(64))
            (origem / 'aparencia.json').write_text('{"tema": "light"}', encoding='utf-8')
            importar_portatil(origem, destino)
            copia = destino / 'portatil_importado' / 'aparencia.json'
            self.assertEqual(copia.read_text(encoding='utf-8'), '{"tema": "light"}')
            self.assertIn('aparencia.json', json.loads((destino / 'importacao.json').read_text())['sha256_origem'])


class Transporte(unittest.TestCase):
    def test_bug11_agente_portatil_ocioso_encerra(self):
        from servico.executar import executar
        with tempfile.TemporaryDirectory() as pasta:
            parar = threading.Event()
            with patch('config.SEGUNDOS_OCIOSIDADE_AGENTE', .15, create=True):
                thread = threading.Thread(target=executar, args=(pasta, parar), daemon=True)
                thread.start()
                try:
                    thread.join(2)
                    self.assertFalse(thread.is_alive(), 'Agente portátil permaneceu vivo sem sessões')
                finally:
                    parar.set()
                    thread.join(5)

    def test_bug11_versao_diferente_substitui_so_portatil(self):
        import config
        from servico.executar import garantir_agente
        with tempfile.TemporaryDirectory() as pasta:
            for instalado in (False, True):
                with self.subTest(instalado=instalado):
                    cliente = Mock()
                    status = iter([{'versao': 'antiga', 'revisao': 'antiga'},
                                   {'versao': config.VERSAO_APP, 'revisao': 'atual'}])
                    cliente.chamar.side_effect = lambda comando: next(status) if comando == 'status' else True
                    with patch('servico.cliente.Cliente', return_value=cliente), \
                         patch('servico.executar.revisao_codigo', return_value='atual', create=True), \
                         patch('servico.executar.subprocess.Popen') as iniciar, \
                         patch('config.DIRETORIO_DADOS', Path(pasta)), patch('config.INSTALADO', instalado):
                        if instalado:
                            with self.assertRaisesRegex(RuntimeError, 'Reparar'):
                                garantir_agente()
                            iniciar.assert_not_called()
                            self.assertEqual(cliente.chamar.call_count, 1)
                        else:
                            self.assertIs(garantir_agente(), cliente)
                            iniciar.assert_called_once()
                            self.assertIn(unittest.mock.call('encerrar_agente'), cliente.chamar.call_args_list)

    def test_bug11_status_publica_versao_do_agente(self):
        import config
        with tempfile.TemporaryDirectory() as pasta:
            n = Nucleo(pasta)
            try:
                resposta = n.executar(dict(v=VERSAO, id=str(uuid4()), sessao=None, comando='status', args=[], kwargs={}), 'teste')
                self.assertEqual(resposta['resultado'].get('versao'), config.VERSAO_APP)
                self.assertTrue(resposta['resultado'].get('revisao'))
            finally:
                n.fechar()

    def test_bug10_falha_manutencao_nao_derruba_agente(self):
        from servico.executar import executar
        original = Nucleo.manutencao
        houve_falha, recuperado = threading.Event(), threading.Event()
        chamadas, falhas = [], []
        def manutencao(n):
            chamadas.append(time.monotonic())
            if len(chamadas) == 3:
                houve_falha.set()
                raise OSError('segredo-ficticio-nao-registrar')
            original(n)
            if len(chamadas) > 3:
                recuperado.set()
        with tempfile.TemporaryDirectory() as pasta:
            parar = threading.Event()
            def agente():
                try:
                    executar(pasta, parar)
                except OSError as erro:
                    falhas.append(type(erro).__name__)
            with patch.object(Nucleo, 'manutencao', manutencao):
                thread = threading.Thread(target=agente, daemon=True)
                thread.start()
                try:
                    self.assertTrue(houve_falha.wait(5))
                    time.sleep(.1)
                    self.assertTrue(thread.is_alive(), falhas)
                    self.assertEqual(Cliente(pasta).chamar('status')['servico'], 'online')
                    self.assertTrue(recuperado.wait(4))
                    self.assertGreaterEqual(chamadas[3] - chamadas[2], 1)
                    log = (Path(pasta) / 'logs/erros.log').read_text(encoding='utf-8')
                    self.assertIn('OSError', log)
                    self.assertNotIn('segredo-ficticio', log)
                finally:
                    parar.set()
                    thread.join(5)
                    self.assertFalse(thread.is_alive())

    def test_bug04_resposta_extensa_recebe_erro_no_pipe_real(self):
        from servico.pipe import servir, ERROS_TRANSPORTE
        from servico.protocolo import LIMITE
        with tempfile.TemporaryDirectory() as pasta:
            parar = threading.Event()
            nucleo = Mock()
            nucleo.deve_encerrar.return_value = False
            nucleo.executar.side_effect = lambda p, i: dict(v=VERSAO, id=p['id'], ok=True,
                                                          resultado={} if p['comando'] == 'status' else 'x' * LIMITE)
            thread = threading.Thread(target=servir, args=(nucleo, pasta, parar), daemon=True)
            thread.start()
            cliente = Cliente(pasta)
            try:
                from models.seguranca import ErroSeguranca
                for _ in range(50):
                    try:
                        cliente.chamar('status')
                        break
                    except ErroSeguranca:
                        time.sleep(.02)
                else:
                    self.fail('Pipe não iniciou')
                with self.assertRaisesRegex(ValueError, 'extensa'):
                    cliente.chamar('estoque.listar_produtos')
                self.assertEqual(cliente.chamar('status'), {})
            finally:
                parar.set()
                thread.join(5)
                self.assertFalse(thread.is_alive())


class Valores(unittest.TestCase):
    def test_bug05_milhar_ptbr_e_decimais(self):
        from utils.texto import converter_para_float
        for texto, esperado in (('1.500', 1500), ('1.234', 1234), ('2.000.000', 2000000),
                                ('1.500,00', 1500), ('12,50', 12.5), ('0,99', .99),
                                ('10.5', 10.5), ('R$ 1.234,56', 1234.56), ('10.1234', 10.1234)):
            with self.subTest(texto=texto):
                self.assertEqual(converter_para_float(texto), esperado)

    def test_bug05_rejeita_formatos_estranhos(self):
        from utils.texto import converter_para_float
        for texto in ('1,234.56', '1_000', '1e3', 'inf', 'nan', 'R$R$1', '1.23.456', '1,,2'):
            with self.subTest(texto=texto):
                with self.assertRaises(ValueError):
                    converter_para_float(texto)

    def test_bug05_importacao_reutiliza_conversor(self):
        from auditoria.verificar_gestao_dados import consumir, csv_bytes, linha
        from gestao.planilha import importar
        from models.models import BancoDados
        from controllers.controllers import ControladorEstoque
        banco = BancoDados(':memory:')
        self.addCleanup(banco.fechar)
        resultado, _ = consumir(importar(banco, csv_bytes([linha(preco='1.500', custo='1.200')]), 'teste', lambda r: None))
        self.assertEqual(resultado['erros'], [])
        produto = ControladorEstoque(banco).obter_produto(1)
        self.assertEqual((produto.preco_venda_base, produto.custo_medio), (1500, 1200))


class Planilha(unittest.TestCase):
    def importar(self, *linhas):
        from auditoria.verificar_gestao_dados import consumir, csv_bytes
        from gestao.planilha import importar
        resultado, _ = consumir(importar(self.banco, csv_bytes(list(linhas)), str(uuid4()), lambda r: None))
        return resultado

    def setUp(self):
        from models.models import BancoDados
        from controllers.controllers import ControladorEstoque
        self.banco = BancoDados(':memory:')
        self.addCleanup(self.banco.fechar)
        self.estoque = ControladorEstoque(self.banco)

    def test_bug21_quantidade_zero_sem_custo_nao_gera_log(self):
        from auditoria.verificar_gestao_dados import linha
        self.importar(linha(qtd='2'))
        logs = len(self.estoque.listar_logs())
        resultado = self.importar(linha(qtd='0', preco='', custo=''))
        self.assertEqual(resultado['atualizados'], 1)
        self.assertEqual(len(self.estoque.listar_logs()), logs)
        self.importar(linha(qtd='0', preco='', custo='7'))   # correção de custo continua registrada
        ultimo = self.estoque.listar_logs()[0]
        self.assertEqual((ultimo['tipo'], ultimo['quantidade'], ultimo['custo_no_momento']), ('Ajuste', 0, 7))
        self.assertEqual(self.estoque.obter_produto(1).custo_medio, 7)

    def test_bug21_quantidade_com_milhar_igual_as_telas(self):
        from auditoria.verificar_gestao_dados import linha
        resultado = self.importar(linha(qtd='1.000'), linha(n=2, qtd='-1'), linha(n=3, qtd='1,5'))
        self.assertEqual(self.estoque.obter_produto(1).estoque_atual, 1000)
        self.assertEqual([e['linha'] for e in resultado['erros']], [3, 4])

    def test_bug21_marca_e_categoria_sem_diferenciar_caixa_e_acento(self):
        from auditoria.verificar_gestao_dados import csv_bytes
        from gestao.planilha import ler, validar
        valores = ler(csv_bytes([['7891000100103', 'Perfume', 'o boticario', 'PERFUMARIA', '1', '', '']]))[0][1]
        self.assertEqual(validar(valores)[2:4], ('O Boticário', 'Perfumaria'))
        with self.assertRaisesRegex(ValueError, 'Marca ou categoria'):
            validar(['7891000100103', 'Perfume', 'Marca Inexistente', 'Perfumaria', '1', '', ''])


class PrimeiroAcesso(unittest.TestCase):
    def test_bug09_validacao_sem_staging_nem_atraso(self):
        with tempfile.TemporaryDirectory() as pasta:
            n = Nucleo(pasta)
            try:
                for nova, confirmacao, mensagem in (('abc', 'abc', 'caracteres'),
                                                   ('senha-nova-2026', 'outra-senha-2026', 'confirmação')):
                    resposta = n.executar(dict(v=VERSAO, id=str(uuid4()), sessao=None, comando='login',
                                               args=['', nova, confirmacao], kwargs={}), 'teste')
                    self.assertEqual(resposta['erro'], 'ValueError')
                    self.assertIn(mensagem, resposta['mensagem'].lower())
                    self.assertEqual(n.tentativas, {})
                    self.assertEqual(list(Path(pasta).glob('.cofre_*')), [])
            finally:
                n.fechar()

    def test_bug09_falha_de_publicacao_remove_staging(self):
        from servico.cofre import CofreServico
        with tempfile.TemporaryDirectory() as pasta:
            cofre = CofreServico(pasta)
            try:
                with patch('servico.cofre.gravar_atomico', side_effect=OSError('Falha de publicação')):
                    with self.assertRaises(OSError):
                        cofre.abrir('', 'senha-nova-2026', 'senha-nova-2026')
                self.assertEqual(list(Path(pasta).glob('.cofre_*')), [])
                self.assertFalse(cofre.pasta.exists())
                cofre.abrir('', 'senha-nova-2026', 'senha-nova-2026')
                self.assertIsNotNone(cofre.banco)
            finally:
                cofre.fechar()

    def test_bug09_tela_valida_antes_do_envio(self):
        from views.acesso import TelaAcesso
        tela = Mock(_ocupado=False, modo='novo')
        tela.nova_senha.get.return_value = 'abc'
        tela.confirmacao.get.return_value = 'abc'
        TelaAcesso._entrar(tela)
        tela.preferencias.abrir.assert_not_called()
        tela.after.assert_not_called()
        self.assertFalse(tela._ocupado)
        self.assertIn('caracteres', tela.mensagem.configure.call_args.kwargs['text'])


class Registro(unittest.TestCase):
    def test_bug13_instalado_registra_em_localappdata(self):
        # Processo separado: simula a build instalada sem recarregar config nesta suíte.
        with tempfile.TemporaryDirectory() as pasta:
            programa, local = Path(pasta) / 'versoes/2.0', Path(pasta) / 'Local'
            programa.mkdir(parents=True)
            (programa / 'instalado.flag').write_text('GiStocker', encoding='utf-8')
            codigo = ('import sys; sys.frozen = True; sys.executable = sys.argv[1]; import config; '
                      'print(config.DIRETORIO_LOGS)')
            saida = subprocess.run([os.sys.executable, '-B', '-c', codigo, str(programa / 'GestorEstoque.exe')],
                                   cwd=RAIZ, env=dict(os.environ, LOCALAPPDATA=str(local)),
                                   capture_output=True, text=True, check=True).stdout.strip()
            self.assertEqual(Path(saida), local / 'GiStocker')

    def test_bug13_registro_padrao_usa_pasta_de_logs(self):
        from utils.erros import registrar_falha
        with tempfile.TemporaryDirectory() as pasta:
            with patch('config.DIRETORIO_LOGS', Path(pasta) / 'logs', create=True):
                registrar_falha(OSError('detalhe-nao-registrar'))
            log = (Path(pasta) / 'logs/erros.log').read_text(encoding='utf-8')
            self.assertIn('OSError', log)
            self.assertNotIn('detalhe-nao-registrar', log)

    def test_bug13_falha_de_inicio_da_interface_usa_pasta_de_logs(self):
        import main
        with tempfile.TemporaryDirectory() as pasta:
            with patch('config.DIRETORIO_LOGS', Path(pasta), create=True), \
                 patch('sys.argv', ['main.py']), patch('views.dialogos.mostrar_dialogo') as dialogo:
                main._registrar_falha(RuntimeError('falha'))
            self.assertIn('RuntimeError', (Path(pasta) / 'erros.log').read_text(encoding='utf-8'))
            self.assertIn(str(Path(pasta) / 'erros.log'), dialogo.call_args.args[1])

    def test_bug13_servico_registra_na_raiz_e_ignora_validacao(self):
        from servico.gestao import GestaoDados
        with tempfile.TemporaryDirectory() as pasta:
            for falha, registra in ((ValueError('Backup com tipo inválido.'), False), (OSError('disco'), True)):
                with self.subTest(falha=type(falha).__name__):
                    cofre = Mock(raiz=Path(pasta))
                    gestao = GestaoDados(cofre)
                    gestao.job = dict(dono='s', id='op', tipo='exportar', concluido=False, erro=None,
                                      gerador=None, uso=0, saida=b'', recebido=0, etapa='', feitos=0, total=1)
                    with patch('gestao.backup.exportar', side_effect=falha), \
                         patch('config.DIRETORIO_LOGS', Path(pasta) / 'interface', create=True):
                        gestao.comando('s', 'passo', 'op')
                    self.assertEqual((Path(pasta) / 'logs/erros.log').exists(), registra)
                    self.assertFalse((Path(pasta) / 'interface').exists())


class Relatorios(unittest.TestCase):
    def test_bug20_periodo_fora_do_limite_e_recusado(self):
        from controllers.controllers import ControladorRelatorios, ErroNegocio
        from models.models import BancoDados
        banco = BancoDados(':memory:')
        self.addCleanup(banco.fechar)
        relatorios = ControladorRelatorios(banco)
        for dias in (0, -3, 10**12, '30'):
            with self.subTest(dias=dias):
                with self.assertRaisesRegex(ErroNegocio, '1 a 3650'):
                    relatorios.estoque_parado(dias)
                with self.assertRaisesRegex(ErroNegocio, '1 a 3650'):
                    relatorios.movimentacao_ultimos_dias(dias)
        self.assertEqual(relatorios.estoque_parado(3650), [])
        self.assertEqual(len(relatorios.movimentacao_ultimos_dias(3650)[0]), 3650)

    def test_bug20_dashboard_restaura_periodo_padrao(self):
        import config
        from views.view_dashboard import ViewDashboard
        tela = Mock()
        tela.entrada_dias.get.return_value = '999999999999'
        tela.relatorios.obter_kpis.return_value = dict(total_itens=0, total_produtos=0, valor_investido=0, receita_potencial=0)
        ViewDashboard.atualizar(tela)
        tela._preencher_estoque_parado.assert_called_once_with(config.DIAS_ESTOQUE_PARADO_PADRAO)
        tela.entrada_dias.insert.assert_called_once_with(0, str(config.DIAS_ESTOQUE_PARADO_PADRAO))


class Busca(unittest.TestCase):
    def test_bug22_prefixo_com_tamanho_de_gtin_encontra_parcial(self):
        from models.models import Produto
        from utils.busca import IndiceProdutos
        indice = IndiceProdutos([Produto(1, 'Perfume Lily', 'O Boticário', 'Perfumaria', codigos=['7891033000017']),
                                 Produto(2, 'Batom', 'Avon', 'Maquiagem', codigos=['78910330'])])
        self.assertEqual([p.id for p in indice.pesquisar('789103300001').produtos], [1])
        self.assertEqual([p.id for p in indice.pesquisar('78910330').produtos], [2])   # exato continua primeiro
        inexistente = indice.pesquisar('7891033000024')
        self.assertEqual(inexistente.produtos, [])
        self.assertIn('Código de barras não encontrado', inexistente.aviso)

    def test_bug23_curingas_like_sao_literais(self):
        from controllers.controllers import ControladorEstoque
        from models.models import BancoDados
        banco = BancoDados(':memory:')
        self.addCleanup(banco.fechar)
        estoque = ControladorEstoque(banco)
        for nome in ('Batom 100% matte', 'Batom vermelho', 'Sombra_azul', 'Base 10\\20'):
            estoque.cadastrar_produto(nome, 'Avon', 'Maquiagem')
        nomes = lambda termo: [p.nome for p in estoque.buscar_produtos(termo)]
        self.assertEqual(nomes('100%'), ['Batom 100% matte'])
        self.assertEqual(nomes('%'), ['Batom 100% matte'])
        self.assertEqual(nomes('a_u'), [])
        self.assertEqual(nomes('_azul'), ['Sombra_azul'])
        self.assertEqual(nomes('10\\2'), ['Base 10\\20'])


class Mensagens(unittest.TestCase):
    def test_bug17_mensagem_conforme_a_causa(self):
        from models.seguranca import ErroSeguranca, ErroSessao
        from utils.erros import mensagem_falha
        servico = 'O serviço local não respondeu. Confira o histórico antes de iniciar outra operação.'
        with patch('utils.erros.registrar_falha') as registrar:
            self.assertIn('Sessão', mensagem_falha(ErroSessao('Sessão bloqueada.')))
            self.assertEqual(mensagem_falha(ErroSeguranca(servico)), servico)
            self.assertEqual(mensagem_falha(ValueError('Gestão de dados em andamento.')), 'Gestão de dados em andamento.')
            registrar.assert_not_called()
            self.assertIn('espaço em disco', mensagem_falha(OSError('disco')))
            registrar.assert_called_once()

    def test_bug17_operacao_exibe_recusa_do_servico(self):
        from views.view_operacao import ViewOperacao
        from models.seguranca import ErroSessao
        tela = Mock(produto_atual=Mock(id=1))
        tela.seletor_tipo.get.return_value = 'SAÍDA'
        tela.controlador.registrar_saida.side_effect = ValueError('Gestão de dados em andamento. Aguarde a conclusão.')
        ViewOperacao._confirmar(tela)
        tela._definir_status.assert_called_with('Gestão de dados em andamento. Aguarde a conclusão.', 'erro')
        tela.entrada_codigo.get.return_value = '7891000100103'
        tela.controlador.resolver_codigo_barras.side_effect = ErroSessao('Sessão bloqueada.')
        ViewOperacao._ao_ler_codigo(tela)
        self.assertIn('Sessão', tela._definir_status.call_args.args[0])

    def test_bug17_telas_capturam_erros_exibiveis(self):
        from views.view_admin import ViewAdmin
        from views.view_cadastro import ViewCadastro
        tela = Mock(produto_atual=Mock(id=1, estoque_atual=1, custo_medio=1.0))
        tela.controlador.ajustar_produto.side_effect = ValueError('Parâmetros incompatíveis com esta operação.')
        tela.entrada_estoque.get.return_value = '2'
        tela.entrada_custo.get.return_value = '1'
        with patch('views.view_admin.confirmar', return_value=True), patch('views.view_admin.erro') as erro:
            ViewAdmin._aplicar_ajuste(tela)
        erro.assert_called_once_with('Ajuste', 'Parâmetros incompatíveis com esta operação.')
        cadastro = Mock()
        cadastro.entrada_codigo.get.return_value = ''
        cadastro.controlador.cadastrar_produto.side_effect = ValueError('Gestão de dados em andamento.')
        with patch('views.view_cadastro.erro') as erro:
            ViewCadastro._salvar(cadastro)
        erro.assert_called_once_with('Não foi possível salvar', 'Gestão de dados em andamento.')


class Interface(unittest.TestCase):
    def raiz(self):
        import customtkinter as ctk
        from views.tarefas import cancelar_tarefas
        raiz = ctk.CTk()
        raiz.withdraw()
        self.addCleanup(lambda: (cancelar_tarefas(raiz, todas=True), raiz.destroy()))
        return raiz

    def janela(self):
        from views.main_view import JanelaPrincipal
        preferencias = Mock(modo='protegido', banco=None)
        janela = JanelaPrincipal(preferencias)
        janela.withdraw()
        self.addCleanup(janela._fechar)
        return janela

    def test_bug12_atalhos_ignoram_travas_do_teclado(self):
        import sys
        from views.main_view import JanelaPrincipal
        janela = Mock()
        travas = (0x2, 0x8, 0x20) if sys.platform == 'win32' else (0x2,)   # CapsLock, NumLock, ScrollLock
        for estado in (0, *travas):
            with self.subTest(estado=hex(estado)):
                janela.mostrar_view.reset_mock()
                JanelaPrincipal._atalho_tela(janela, Mock(state=estado), 'cadastro')
                janela.mostrar_view.assert_called_once_with('cadastro')
        janela.mostrar_view.reset_mock()
        alt = 0x20000 if sys.platform == 'win32' else 0x8
        JanelaPrincipal._atalho_tela(janela, Mock(state=alt | 0x8), 'relatorios')
        janela.mostrar_view.assert_not_called()

    def test_bug13_interface_nao_registra_erro_esperado(self):
        from views.gestao_dados import DialogoGestao
        for falha, registra in ((ValueError('Senha atual incorreta. Nenhum dado foi alterado.'), False),
                                (OSError('O agente não respondeu.'), True)):
            with self.subTest(falha=type(falha).__name__):
                dialogo = Mock(tipo='importar', caminho='x.csv')
                transferencia = Mock()
                transferencia.executar.side_effect = falha
                with patch('utils.erros.registrar_falha') as registrar:
                    DialogoGestao._trabalhar(dialogo, transferencia, 'senha')
                self.assertEqual(registrar.called, registra)
                self.assertEqual(dialogo.fila.put.call_args.args[0], ('erro', str(falha)))

    def test_bug16_exportacao_protegida_orienta_recuperacao_real(self):
        from views.view_relatorios import ViewRelatorios
        tela = Mock()
        tela.relatorios.exportar_protegido.return_value = Path('backups/GiStocker_20261017_ab.gsbackup')
        with patch('views.view_relatorios.confirmar', return_value=False) as confirmar:
            ViewRelatorios._exportar(tela)
        texto = confirmar.call_args.args[1]
        self.assertIn('.gsbackup', texto)
        self.assertIn('Recuperação portátil', texto)
        self.assertNotIn('dados/estoque.db', texto.replace('não substitua dados/estoque.db', ''))
        guia = (RAIZ / 'GUIA_MULTICANAL.md').read_text(encoding='utf-8')
        self.assertIn('## Recuperação portátil', guia)

    def test_bug18_selecao_de_pedido_sobrevive_ao_refresh(self):
        from views.view_integracoes import ViewIntegracoes
        raiz = self.raiz()
        def pedido(loja, numero):
            return dict(id=json.dumps([loja, numero, '1']), pedido_id=json.dumps([loja, numero]), linha='1',
                        remoto=f'{loja}:1', produto_id=1, quantidade=1, cancelada=0, versao=1, estado='RESERVADO')
        a, b = pedido('SHOPEE', 'a'), pedido('TIKTOK', 'b')
        painel = lambda pedidos: dict(estado='MULTICANAL_ATIVO', local=[], simulacao=dict(
            produtos=[], catalogo=[], pedidos=pedidos, fila=[], incidentes=[], eventos=[]))
        janela = Mock()
        janela.preferencias.chamar.return_value = painel([a])
        tela = ViewIntegracoes(raiz, janela)
        tela.atualizar()
        tela.pedidos.selection_set(tela.pedidos.get_children()[0])
        janela.preferencias.chamar.return_value = painel([b, a])   # novo pedido antes do selecionado
        tela.atualizar()
        tela.operacao.set('Separar')
        tela.operar_pedido()
        janela.preferencias.chamar.assert_any_call('integracoes.pedido_operar', a['id'], 'SEPARAR')

    def test_bug18_painel_ordena_pedidos_e_catalogo(self):
        from multicanal.motor import Motor
        from models.models import BancoDados
        banco = BancoDados(':memory:')
        self.addCleanup(banco.fechar)
        consultas = []
        banco.conexao.set_trace_callback(consultas.append)
        Motor(banco).painel()
        for tabela in ('Itens_Pedido_Externo', 'Catalogo_Remoto c'):
            with self.subTest(tabela=tabela):
                sql = next(q for q in consultas if f'FROM {tabela}' in q)
                self.assertIn('ORDER BY', sql)

    def test_bug24_enter_nos_campos_do_primeiro_acesso(self):
        from views.acesso import TelaAcesso
        raiz = self.raiz()
        tela = TelaAcesso(raiz, Mock(modo='novo'), Mock())
        for campo in (tela.nova_senha, tela.confirmacao):
            for tecla in ('<Key-Return>', '<Key-KP_Enter>'):
                with self.subTest(tecla=tecla):
                    self.assertIn(tecla, campo.entrada._entry.bind())
        falsa = Mock()
        self.assertEqual(TelaAcesso._avancar(falsa), 'break')
        falsa.confirmacao.entrada.focus_set.assert_called_once()

    def test_bug26_inatividade_com_seletor_aberto_bloqueia_ao_fechar(self):
        from types import SimpleNamespace
        from views.gestao_dados import PainelGestao
        from views.main_view import JanelaPrincipal
        janela = SimpleNamespace(_gestao_em_andamento=False, _dialogo_gestao=None, _ultimo_uso=0,
                                 _desbloqueado=True, after=Mock(), bloquear=Mock(), _conferir_inatividade=Mock())
        def seletor(**_opcoes):
            JanelaPrincipal._conferir_inatividade(janela)   # o prazo vence com o diálogo nativo aberto
            janela.bloquear.assert_not_called()             # destruir agora quebraria a chamada em curso
            return 'C:/Users/loja/planilha.csv'
        painel = Mock(janela=janela)
        self.assertEqual(PainelGestao._selecionar(painel, seletor), '')
        janela.bloquear.assert_called_once()
        self.assertFalse(janela._gestao_em_andamento)
        janela.bloquear.reset_mock()
        janela._ultimo_uso = time.monotonic()
        self.assertEqual(PainelGestao._selecionar(painel, lambda **_: 'C:/x.csv'), 'C:/x.csv')
        janela.bloquear.assert_not_called()

    def test_bug25_ctrl_l_bloqueia_com_caps_lock(self):
        janela = self.janela()
        for sequencia in ('<Control-Key-l>', '<Control-Key-L>'):
            with self.subTest(sequencia=sequencia):
                self.assertIn(sequencia, janela.bind())
