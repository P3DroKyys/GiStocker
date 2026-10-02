"""Widgets reais + agente real em banco temporário; nenhum dado da loja é aberto."""
import multiprocessing
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import customtkinter as ctk
import config
from servico.cliente import Cliente
from servico.executar import executar
from views.main_view import JanelaPrincipal


class InterfaceMulticanal(unittest.TestCase):
    def test_fluxo_completo_via_ipc(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz=Path(tmp)/'dados'; parar=multiprocessing.Event()
            processo=multiprocessing.Process(target=executar,args=(raiz,parar)); processo.start()
            cliente=Cliente(raiz)
            janela=None
            try:
                for _ in range(50):
                    try: cliente.chamar('status'); break
                    except Exception: time.sleep(.1)
                ctk.set_default_color_theme(config.TEMA_COR)
                janela=JanelaPrincipal(cliente); janela.withdraw()
                falhas=[]
                janela.report_callback_exception=lambda tipo,valor,tb:falhas.append(valor)
                acesso=janela.tela_acesso
                acesso.nova_senha.entrada.insert(0,'senha-tela-739')
                acesso.confirmacao.entrada.insert(0,'senha-tela-739')
                acesso._entrar()
                self.assertTrue(janela._desbloqueado)
                estoque=janela.controlador_estoque
                estoque.cadastrar_produto('Refil Lily','O Boticário','Perfumaria',quantidade_inicial=10,codigos=['7891000100103'])
                for tema in ('light','dark'):
                    janela.alternar_tema(tema)
                    for tela in ('operacao','cadastro','dashboard','relatorios','admin','configuracoes','integracoes'):
                        janela.mostrar_view(tela); janela.update_idletasks(); janela.update()
                integracoes=janela.views['integracoes']
                integracoes.acao('ativar_simulacao'); integracoes.acao('catalogo_exemplo')
                self.assertEqual(len(integracoes.catalogo.get_children()),2)
                for remoto in ('SHOPEE:1','TIKTOK:1'):
                    integracoes.catalogo.selection_set(remoto)
                    integracoes.sugerir(); integracoes.vincular()
                integracoes.acao('iniciar_ensaio')
                integracoes.acao('passo')
                integracoes.atualizar()
                self.assertEqual(integracoes.dados['simulacao']['produtos'][0]['exposta'],5)
                self.assertEqual(estoque.obter_produto(1).estoque_atual,10)
                integracoes.acao('encerrar')
                janela.bloquear(); janela.update()
                self.assertFalse(janela._desbloqueado)
                self.assertEqual(falhas,[])
            finally:
                if janela: janela._fechar()
                parar.set(); processo.join(10)
                if processo.is_alive(): processo.terminate(); processo.join()


if __name__=='__main__': unittest.main()
