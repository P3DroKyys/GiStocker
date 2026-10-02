"""Contratos multicanal; nunca usa os dados reais da instalação."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from controllers.controllers import ControladorEstoque, ErroNegocio
from models.models import BancoDados
from models.seguranca import ErroSeguranca
from multicanal.motor import Motor
from multicanal.sincronizacao import MarketplaceSimulado, Worker
from servico.cofre import CofreServico, restaurar
from servico.nucleo import Nucleo
from servico.protocolo import codificar, decodificar, ler


class Dominio(unittest.TestCase):
    def setUp(self):
        self.bd = BancoDados(':memory:')
        self.m = Motor(self.bd)
        self.p = self.m.estoque.cadastrar_produto('Lily Refil','O Boticário','Perfumaria',quantidade_inicial=10,codigos=['7891000100103'])
        self.m.preparar()
        self.api = MarketplaceSimulado(self.bd)
        self.w = Worker(self.m,self.api)
        for canal in ('SHOPEE','TIKTOK'):
            self.m.con.execute('INSERT INTO Lojas_Externas VALUES(?,?,?,?,1)',(canal,canal,canal,'SIMULADO'))
            self.m.con.execute('INSERT INTO Catalogo_Remoto(id,loja,produto_externo,sku,armazem,titulo) VALUES(?,?,?,?,?,?)',(canal,canal,'produto','sku','a','Lily'))

    def tearDown(self):
        self.bd.fechar()

    def vincular(self):
        for canal in ('SHOPEE','TIKTOK'):
            self.m.vincular(canal,self.p.id)

    def evento(self, **alteracoes):
        e = dict(loja='SHOPEE',pedido='pedido-1',linha='1',remoto='SHOPEE',quantidade=2,cancelada=0,versao=1,estado='RESERVADO')
        e.update(alteracoes)
        return e

    def pedido(self, **kwargs):
        self.m.receber(self.evento(**kwargs)); self.m.processar_inbox()
        return self.m.linha('SELECT id FROM Itens_Pedido_Externo')['id']

    def test_migracao_e_immutabilidade(self):
        self.assertEqual(self.bd.conexao.execute('PRAGMA user_version').fetchone()[0],2)
        for sql in ('DELETE FROM Eventos_Estoque','UPDATE Eventos_Estoque SET delta=0'):
            with self.assertRaises(sqlite3.IntegrityError): self.m.con.execute(sql)

    def test_faixa_alocador_e_sorteio_estavel(self):
        self.vincular()
        for saldo in range(501):
            self.m.con.execute('UPDATE Produtos SET estoque_atual=?',(saldo,))
            plano = self.m.alocar(self.p.id)
            self.assertEqual(plano['saldo']['reserva_fisica'],(saldo+1)//2)
            self.assertEqual(sum(plano['cotas'].values()),saldo//2)
            self.assertLessEqual(abs(plano['cotas']['SHOPEE']-plano['cotas']['TIKTOK']),1)
            self.assertEqual(plano,self.m.alocar(self.p.id))

    def test_canal_unico_nao_confunde_pendente(self):
        self.m.vincular('SHOPEE',self.p.id)
        self.assertTrue(self.m.alocar(self.p.id)['bloqueado'])
        self.m.cobertura(self.p.id,'TIKTOK','NAO_PUBLICADO')
        self.assertEqual(self.m.alocar(self.p.id)['cotas'],{'SHOPEE':5})

    def test_dois_anuncios_nao_duplicam_cota(self):
        self.vincular()
        self.m.con.execute("INSERT INTO Catalogo_Remoto(id,loja,produto_externo,sku,armazem,titulo) VALUES('outro','SHOPEE','outro','sku','a','Lily')")
        self.m.vincular('outro',self.p.id)
        self.w.passo()
        self.assertEqual(self.m.saldo(self.p.id)['exposta'],5)

    def test_venda_fisica_protege_exposicao_e_rollback(self):
        self.vincular(); self.w.passo()
        with self.assertRaises(ErroNegocio):
            self.m.fisico('registrar_saida',[self.p.id,6],{},str(uuid4()))
        self.assertEqual(self.m.estoque.obter_produto(self.p.id).estoque_atual,10)
        self.m.fisico('registrar_saida',[self.p.id,5],{},str(uuid4()))
        self.assertEqual(self.m.estoque.obter_produto(self.p.id).estoque_atual,5)

    def test_pedido_cem_vezes_e_cancelamento_parcial(self):
        self.vincular()
        for _ in range(100): self.pedido()
        self.assertEqual(self.m.saldo(self.p.id)['comprometido'],2)
        self.pedido(cancelada=1,versao=2)
        self.assertEqual(self.m.saldo(self.p.id)['comprometido'],1)
        self.pedido()  # anterior não reabre
        self.assertEqual(self.m.saldo(self.p.id)['comprometido'],1)

    def test_cancelamento_antes_do_pedido(self):
        self.vincular()
        self.pedido(cancelada=2,versao=3,estado='CANCELADO')
        self.pedido()
        self.assertEqual(self.m.saldo(self.p.id)['comprometido'],0)

    def test_cancelamento_separado_exige_conferencia(self):
        self.vincular()
        item = self.pedido()
        self.m.pedido_operar(item,'SEPARAR')
        self.pedido(cancelada=2,versao=2,estado='CANCELADO')
        self.assertEqual(self.m.saldo(self.p.id)['comprometido'],2)
        self.m.pedido_operar(item,'CONFERIR_RETORNO')
        self.assertEqual(self.m.saldo(self.p.id)['comprometido'],0)

    def test_envio_nao_volta_por_cancelamento(self):
        self.vincular(); item=self.pedido()
        for acao in ('SEPARAR','EMBALAR','ENVIAR'): self.m.pedido_operar(item,acao)
        self.pedido(cancelada=2,versao=2,estado='CANCELADO')
        with self.assertRaises(ErroNegocio): self.m.pedido_operar(item,'CONFERIR_RETORNO')
        self.assertEqual(self.m.saldo(self.p.id)['em_maos'],8)

    def test_devolucao_so_vende_apos_inspecao(self):
        self.vincular(); item=self.pedido()
        for acao in ('SEPARAR','EMBALAR','ENVIAR'): self.m.pedido_operar(item,acao)
        self.pedido(cancelada=2,versao=2,estado='CANCELADO')
        self.m.pedido_operar(item,'RECEBER_DEVOLUCAO')
        self.assertEqual(self.m.saldo(self.p.id)['quarentena'],2)
        self.assertEqual(self.m.saldo(self.p.id)['livre'],8)
        with self.assertRaises(ErroNegocio): self.m.pedido_operar(item,'RECEBER_DEVOLUCAO')
        self.m.pedido_operar(item,'APROVAR_DEVOLUCAO')
        self.assertEqual(self.m.saldo(self.p.id)['livre'],10)
        with self.assertRaises(ErroNegocio): self.m.pedido_operar(item,'APROVAR_DEVOLUCAO')

    def test_timeout_nao_libera_exposicao(self):
        self.vincular(); self.api.falha='TIMEOUT_APOS_ENVIO'; self.w.passo()
        self.assertGreater(self.m.saldo(self.p.id)['exposta'],0)
        self.assertTrue(self.m.linha('SELECT 1 FROM Estado_SKU_Canal WHERE incerta=1'))
        self.api.falha=None
        self.w = Worker(self.m,self.api)
        self.w.passo()
        self.assertFalse(self.m.linha('SELECT 1 FROM Estado_SKU_Canal WHERE incerta=1'))

    def test_falhas_api_preservam_cota(self):
        self.vincular(); self.w.passo()
        for falha in ('SEM_INTERNET','RATE_LIMIT','TOKEN_VENCIDO'):
            self.api.falha=falha; self.w.retomar_em=0; self.w.passo()
            self.assertEqual(self.m.saldo(self.p.id)['exposta'],5)

    def test_sem_vinculo_nao_perde_evento(self):
        self.m.receber(self.evento()); self.m.processar_inbox()
        self.assertEqual(self.m.linha('SELECT estado FROM Inbox_Eventos')['estado'],'PENDENTE')
        self.vincular(); self.m.processar_inbox()
        self.assertEqual(self.m.linha('SELECT estado FROM Inbox_Eventos')['estado'],'APLICADO')

    def test_mesma_versao_divergente_bloqueada(self):
        self.m.receber(self.evento())
        with self.assertRaises(ErroNegocio): self.m.receber(self.evento(quantidade=3))


class Servico(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.n=Nucleo(Path(self.tmp.name)/'dados')
        self.token=None
        r=self.call('login',['','teste-seguro-47','teste-seguro-47'])
        self.assertTrue(r['ok'],r)
        self.token=r['resultado']

    def tearDown(self):
        self.n.fechar(); self.tmp.cleanup()

    def call(self,cmd,args=None,kwargs=None,chave=None,identidade='usuario'):
        return self.n.executar(dict(v=1,id=chave or str(uuid4()),sessao=self.token,comando=cmd,args=args or [],kwargs=kwargs or {}),identidade)

    def cadastrar(self):
        return self.call('estoque.cadastrar_produto',kwargs=dict(nome='Lily',marca='O Boticário',categoria='Perfumaria',quantidade_inicial=10,codigos=['7891000100103']))

    def test_json_sem_tipos_arbitrarios(self):
        with self.assertRaises(ValueError): ler(b'{"a":1,"a":2}')
        with self.assertRaises(ValueError): ler(b'{"a":NaN}')
        with self.assertRaises(ValueError): decodificar({'$tipo':'eval','valor':'1'})

    def test_ipc_sem_sql_ou_sessao_de_outro_usuario(self):
        for cmd in ('estoque.bd','sql','estoque.__getattribute__','relatorios.exportar_csv'):
            self.assertFalse(self.call(cmd)['ok'])
        self.assertFalse(self.call('estoque.listar_produtos',identidade='intruso')['ok'])

    def test_repeticao_apos_commit_e_reinicio(self):
        r=self.cadastrar(); self.assertTrue(r['ok'],r)
        chave=str(uuid4())
        a=self.call('estoque.registrar_saida',[1,2],chave=chave)
        self.assertTrue(a['ok'],a)
        b=self.call('estoque.registrar_saida',[1,2],chave=chave)
        self.assertEqual(a,b)
        self.assertFalse(self.call('estoque.registrar_saida',[1,3],chave=chave)['ok'])
        self.n.fechar(); self.n=Nucleo(Path(self.tmp.name)/'dados')
        self.token=self.call('login',['teste-seguro-47',None,None])['resultado']
        self.assertEqual(self.call('estoque.registrar_saida',[1,2],chave=chave)['resultado'],a['resultado'])
        self.assertEqual(self.n.motor.saldo(1)['em_maos'],8)

    def test_senha_bloqueio_e_expiracao(self):
        self.assertFalse(self.call('senha',['errada','outra-senha-48','outra-senha-48'])['ok'])
        self.assertTrue(self.call('senha',['teste-seguro-47','outra-senha-48','outra-senha-48'])['ok'])
        self.n.sessoes[self.token]['uso']-=5401
        self.assertFalse(self.call('estoque.listar_produtos')['ok'])
        self.n.manutencao(); self.assertIsNone(self.n.cofre.banco)

    def test_backup_restaura_outro_diretorio_sem_dpapi(self):
        self.assertTrue(self.cadastrar()['ok'])
        copia=decodificar(self.call('backup')['resultado'])
        destino=Path(self.tmp.name)/'outro_pc'
        restaurar(copia,destino,'teste-seguro-47')
        novo=CofreServico(destino)
        try:
            novo.abrir('teste-seguro-47')
            self.assertEqual(ControladorEstoque(novo.banco).obter_produto(1).nome,'Lily')
            self.assertIsNone(novo.ler_envelope()['servico'])
        finally: novo.fechar()

    def test_simulacao_isolada_e_dpapi(self):
        self.cadastrar()
        self.assertTrue(self.call('integracoes.ativar_simulacao')['ok'])
        self.assertTrue(self.call('integracoes.catalogo_exemplo')['ok'])
        self.n.simulacao.estoque.registrar_saida(1,2)
        self.assertEqual(self.n.motor.saldo(1)['em_maos'],10)
        self.n.fechar(); self.n=Nucleo(Path(self.tmp.name)/'dados')
        self.assertIsNotNone(self.n.worker)
        self.assertEqual(self.n.simulacao.saldo(1)['em_maos'],8)
        self.assertFalse(self.call('estoque.listar_produtos')['ok'])

    def test_banco_nao_abre_sem_envelope(self):
        with closing(sqlite3.connect(self.n.cofre.caminho)) as con:
            with self.assertRaises(sqlite3.DatabaseError): con.execute('SELECT * FROM Produtos').fetchall()
        outro=CofreServico(Path(self.tmp.name)/'dados')
        with self.assertRaises(ErroSeguranca): outro.abrir('errada')

    def test_falha_escrita_reverte_saldo_evento_e_comando(self):
        self.cadastrar()
        with patch.object(self.n.motor,'evento',side_effect=OSError('disco cheio simulado')):
            resposta=self.call('estoque.registrar_saida',[1,3])
        self.assertFalse(resposta['ok'])
        self.assertEqual(self.n.motor.saldo(1)['em_maos'],10)
        self.assertEqual(len(self.n.motor.estoque.listar_logs()),1)

    def test_configurar_nao_publica_e_encerramento_confirma_zero(self):
        self.cadastrar(); self.call('integracoes.ativar_simulacao'); self.call('integracoes.catalogo_exemplo')
        for remoto in ('SHOPEE:1','TIKTOK:1'): self.call('integracoes.vincular',[remoto,1])
        self.n.manutencao()
        self.assertEqual(self.n.simulacao.saldo(1)['exposta'],0)
        self.call('integracoes.iniciar_ensaio'); self.n.manutencao()
        self.assertEqual(self.n.simulacao.saldo(1)['exposta'],5)
        self.call('integracoes.pausar'); self.n.manutencao()
        self.assertEqual(self.n.simulacao.saldo(1)['exposta'],5)
        self.call('integracoes.falha',['SEM_INTERNET'])
        self.assertFalse(self.call('integracoes.encerrar')['ok'])
        self.assertIsNotNone(self.n.simulacao)
        self.call('integracoes.falha',[None]); self.n.manutencao()
        self.assertIsNone(self.n.simulacao)
        self.assertIsNone(self.n.cofre.ler_envelope()['servico'])

    def test_migracao_v1_preserva_arquivo_original(self):
        import hashlib
        from models.models import SQL_CRIAR_TABELAS
        from models.seguranca import conectar
        raiz=Path(self.tmp.name)/'versao1'; raiz.mkdir()
        caminho=raiz/'estoque.db'
        with closing(conectar(caminho,'senha-antiga-73',criar=True)) as con:
            for sql in SQL_CRIAR_TABELAS.split(';'):
                if sql.strip(): con.execute(sql)
            con.execute('PRAGMA user_version=1')
            con.execute("INSERT INTO Produtos(nome,marca,categoria,estoque_atual) VALUES('Legado','O Boticário','Perfumaria',7)")
        antes=hashlib.sha256(caminho.read_bytes()).digest()
        cofre=CofreServico(raiz)
        try:
            cofre.abrir('senha-antiga-73')
            self.assertEqual(cofre.banco.conexao.execute('PRAGMA user_version').fetchone()[0],2)
            self.assertEqual(cofre.banco.conexao.execute('SELECT estoque_atual FROM Produtos').fetchone()[0],7)
            self.assertEqual(hashlib.sha256(caminho.read_bytes()).digest(),antes)
        finally: cofre.fechar()


if __name__=='__main__': unittest.main()
