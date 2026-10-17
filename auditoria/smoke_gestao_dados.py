"""Tela de configurações + modal + worker + pipe em instalação descartável."""
from pathlib import Path
import time
import traceback
import unittest

import customtkinter as ctk
import config
from auditoria import verificar_ipc
from auditoria.verificar_gestao_dados import csv_bytes, linha
from views.gestao_dados import DialogoGestao
from views.main_view import JanelaPrincipal


class InterfaceGestao(unittest.TestCase):
    setUp = verificar_ipc.PipeWindows.setUp
    tearDown = verificar_ipc.PipeWindows.tearDown

    def test_fluxo_temas_modal_e_refresh(self):
        ctk.set_default_color_theme(config.TEMA_COR)
        janela = JanelaPrincipal(self.cliente)
        janela.withdraw()
        falhas = []
        janela.report_callback_exception = lambda tipo, valor, tb: falhas.append(''.join(traceback.format_exception(tipo, valor, tb)))
        dlg = None
        try:
            tela = janela.tela_acesso
            tela.nova_senha.entrada.insert(0, 'senha-interface')
            tela.confirmacao.entrada.insert(0, 'senha-interface')
            tela._entrar()
            janela.mostrar_view('configuracoes')
            csv = Path(self.tmp.name) / 'produtos.csv'
            csv.write_bytes(csv_bytes([linha(), linha(2, qtd='invalido')]))
            for tema in ('light', 'dark'):
                janela.alternar_tema(tema)
                dlg = DialogoGestao(janela, 'importar', str(csv))
                dlg.geometry('540x540')
                janela.update_idletasks()
                janela.update()
                janela.mostrar_view('admin')
                self.assertIs(janela.view_atual, janela.views['configuracoes'])
                janela.bloquear()
                self.assertTrue(janela._desbloqueado)
                dlg.iniciar()
                self.assertFalse(dlg.executando)
                dlg.fechar()
                dlg = None
            dlg = DialogoGestao(janela, 'importar', str(csv))
            dlg.senha.entrada.insert(0, 'senha-interface')
            dlg.aceite.select()
            dlg.iniciar()
            janela._fechar()
            self.assertTrue(janela.winfo_exists())
            limite = time.monotonic() + 30
            while dlg.executando and time.monotonic() < limite:
                janela.update()
                time.sleep(.02)
            self.assertFalse(dlg.executando)
            self.assertTrue(dlg.sucesso)
            self.assertIn('Linha 3:', dlg.relatorio)
            self.assertEqual(dlg.senha.get(), '')
            dlg.fechar()
            dlg = None
            self.assertFalse(janela._desbloqueado)
            self.assertEqual(janela.views, {})
            tela = janela.tela_acesso
            tela.campo_senha.entrada.insert(0, 'senha-interface')
            tela._entrar()
            self.assertEqual(janela.controlador_estoque.obter_produto(1).estoque_atual, 3)
            for chave in ('dashboard', 'admin', 'operacao', 'relatorios', 'configuracoes'):
                janela.mostrar_view(chave)
                janela.update()
            self.assertFalse(falhas, falhas[0] if falhas else '')
        finally:
            if dlg:
                dlg.executando = False
                dlg.fechar()
            janela._gestao_em_andamento = False
            janela._fechar()


if __name__ == '__main__':
    unittest.main()
