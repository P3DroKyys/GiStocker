"""Queda real de processo antes/depois do commit usando apenas dados temporários."""
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from servico.nucleo import Nucleo


def chamar(n,token,comando,args=None,kwargs=None,chave=None):
    return n.executar(dict(v=1,id=chave or str(uuid4()),sessao=token,comando=comando,args=args or [],kwargs=kwargs or {}),'teste')


def interromper(raiz,chave,antes):
    n=Nucleo(raiz)
    token=chamar(n,None,'login',['senha-crash-83',None,None])['resultado']
    if antes:
        original=n.motor.fisico
        def cair(*args,**kwargs):
            original(*args,**kwargs)
            os._exit(77)
        n.motor.fisico=cair
    resposta=chamar(n,token,'estoque.registrar_saida',[1,2],chave=chave)
    os._exit(78 if resposta['ok'] else 79)


class Recuperacao(unittest.TestCase):
    def test_queda_em_ambos_lados_do_commit(self):
        for antes in (True,False):
            with self.subTest(antes=antes), tempfile.TemporaryDirectory() as tmp:
                raiz=Path(tmp)/'dados'; n=Nucleo(raiz)
                token=chamar(n,None,'login',['','senha-crash-83','senha-crash-83'])['resultado']
                r=chamar(n,token,'estoque.cadastrar_produto',kwargs=dict(nome='Crash',marca='O Boticário',categoria='Perfumaria',quantidade_inicial=10,codigos=['7891000100103']))
                self.assertTrue(r['ok'],r)
                n.fechar()
                chave=str(uuid4())
                filho=multiprocessing.Process(target=interromper,args=(raiz,chave,antes)); filho.start(); filho.join(20)
                if filho.is_alive(): filho.terminate(); filho.join(); self.fail('Processo não terminou.')
                self.assertEqual(filho.exitcode,77 if antes else 78)
                n=Nucleo(raiz)
                try:
                    token=chamar(n,None,'login',['senha-crash-83',None,None])['resultado']
                    self.assertEqual(n.motor.saldo(1)['em_maos'],10 if antes else 8)
                    for _ in range(3): self.assertTrue(chamar(n,token,'estoque.registrar_saida',[1,2],chave=chave)['ok'])
                    self.assertEqual(n.motor.saldo(1)['em_maos'],8)
                finally: n.fechar()


if __name__=='__main__': unittest.main()
