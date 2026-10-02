"""Exercita um processo escritor separado e o Named Pipe real do Windows."""
import multiprocessing
from pathlib import Path
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from servico.cliente import Cliente
from servico.executar import executar


def agente(raiz, parar):
    executar(raiz,parar)


class PipeWindows(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.raiz=Path(self.tmp.name)/'dados'
        self.parar=multiprocessing.Event()
        self.processo=multiprocessing.Process(target=agente,args=(self.raiz,self.parar))
        self.processo.start()
        self.cliente=Cliente(self.raiz)
        erro=None
        for _ in range(60):
            try:
                self.cliente.chamar('status'); break
            except Exception as e:
                erro=e; time.sleep(.1)
        else:
            self.tearDown(); raise erro

    def tearDown(self):
        self.cliente.fechar()
        self.parar.set(); self.processo.join(8)
        if self.processo.is_alive():
            self.processo.terminate(); self.processo.join()
        self.tmp.cleanup()

    def test_login_controle_e_concorrencia(self):
        self.cliente.abrir('','teste-ipc-739','teste-ipc-739')
        estoque,relatorios=self.cliente.criar_controladores()
        p=estoque.cadastrar_produto('Lily','O Boticário','Perfumaria',quantidade_inicial=1,codigos=['7891000100103'])
        self.assertEqual(p.id,1)
        self.assertEqual(estoque.pesquisar_produtos('lily').produtos[0].id,p.id)
        def vender(indice):
            from servico.pendencias import Pendencias
            c=Cliente(self.raiz); c.sessao=self.cliente.sessao
            c.journal=Pendencias(self.raiz/str(indice),False)
            try:
                c.chamar('estoque.registrar_saida',p.id,1)
                return True
            except Exception: return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(vender,range(2))),1)
        self.assertEqual(estoque.obter_produto(p.id).estoque_atual,0)
        self.assertTrue(relatorios.obter_kpis())
        self.assertEqual(estoque.listar_logs()[0]['origem'],'FISICO')
        self.cliente.fechar()
        with self.assertRaises(Exception): estoque.listar_produtos()

    def test_resposta_perdida_e_nova_interface_nao_repetem_baixa(self):
        from servico.pipe import chamar
        from models.seguranca import ErroSeguranca
        self.cliente.abrir('','teste-ipc-739','teste-ipc-739')
        estoque,_=self.cliente.criar_controladores()
        estoque.cadastrar_produto('Lily','O Boticário','Perfumaria',quantidade_inicial=10,codigos=['7891000100103'])
        def perder(*args,**kwargs):
            chamar(*args,**kwargs)
            raise OSError('Resposta perdida após commit')
        with patch('servico.cliente.chamar',side_effect=perder):
            with self.assertRaises(ErroSeguranca): estoque.registrar_saida(1,2)
        nova=Cliente(self.raiz); nova.sessao=self.cliente.sessao
        resultado=nova.chamar('estoque.registrar_saida',1,2)
        self.assertEqual(resultado.estoque_novo,8)
        self.assertEqual(estoque.obter_produto(1).estoque_atual,8)
        self.assertEqual((self.raiz/'comandos_pendentes.json').read_text(encoding='utf-8'),'{}')

    def test_dacl_rejeita_token_restrito(self):
        import win32api,win32con,win32security,win32file,pywintypes
        from servico.pipe import nome_pipe
        original=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_ALL_ACCESS)
        restrito=None
        try:
            anonimo=win32security.ConvertStringSidToSid('S-1-5-7')
            restrito=win32security.CreateRestrictedToken(original,0,[],[],[(anonimo,0)])
            win32security.ImpersonateLoggedOnUser(restrito)
            try:
                with self.assertRaises(pywintypes.error) as contexto:
                    win32file.CreateFile(nome_pipe(self.raiz),win32con.GENERIC_READ|0x0002,0,None,win32con.OPEN_EXISTING,0,None)
                self.assertEqual(contexto.exception.winerror,5)
            finally: win32security.RevertToSelf()
        finally:
            if restrito: restrito.Close()
            original.Close()


if __name__=='__main__': unittest.main()
