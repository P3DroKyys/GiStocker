"""Regressões dos contratos modais, sem abrir janelas nem banco de uso."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from views import componentes
from views.dialogos import DialogoGiStocker


class Dialogos(unittest.TestCase):
    def test_helpers_encaminham_tipo_e_texto(self):
        with patch('views.componentes.mostrar_dialogo') as abrir:
            for funcao, tipo in ((componentes.erro, 'erro'), (componentes.alertar, 'aviso'),
                                 (componentes.informar, 'sucesso')):
                funcao('Título', 'Texto\ncom detalhes')
                abrir.assert_called_with('Título', 'Texto\ncom detalhes', tipo)

    def test_confirmacao_preserva_sim_e_nao(self):
        for resposta in (True, False):
            with patch('views.componentes.mostrar_dialogo', return_value=resposta):
                self.assertIs(componentes.confirmar('Confirmar', 'Continuar?'), resposta)

    def test_enter_sem_foco_nao_confirma_acao(self):
        tela = Mock()
        tela._botao_focado.return_value = None
        self.assertEqual(DialogoGiStocker._enter(tela), 'break')
        tela.cancelar.invoke.assert_called_once()
        tela.aceitar.invoke.assert_not_called()

    def test_enter_respeita_botao_focado(self):
        tela = Mock()
        tela._botao_focado.return_value = tela.aceitar
        DialogoGiStocker._enter(tela)
        tela.aceitar.invoke.assert_called_once()
        tela.cancelar.invoke.assert_not_called()

    def test_tab_e_shift_tab_alternam_botoes(self):
        tela = Mock()
        tela._botoes = [tela.cancelar, tela.aceitar]
        tela._botao_focado.return_value = tela.cancelar
        self.assertEqual(DialogoGiStocker._mudar_foco(tela, 1), 'break')
        tela.aceitar.focus_set.assert_called_once()
        tela._botao_focado.return_value = tela.aceitar
        DialogoGiStocker._mudar_foco(tela, -1)
        tela.cancelar.focus_set.assert_called_once()

    def test_fechar_sem_confirmar_retorna_falso(self):
        tela = Mock()
        DialogoGiStocker._fechar(tela, False)
        self.assertIs(tela.resultado, False)
        tela.destroy.assert_called_once()


if __name__ == '__main__':
    unittest.main()
