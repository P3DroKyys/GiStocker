"""Casos que o smoke com janela oculta não cobria."""
import time
import traceback
import unittest

import customtkinter as ctk
from views.gestao_dados import rotulo


class Layout(unittest.TestCase):
    def test_rotulos_usam_largura_disponivel_sem_ciclo(self):
        root = ctk.CTk()
        root.geometry('760x600+10000+10000')
        falhas = []
        root.report_callback_exception = lambda t, v, tb: falhas.append(''.join(traceback.format_exception(t, v, tb)))
        try:
            frame = ctk.CTkFrame(root)
            frame.pack(fill='both', expand=True)
            label = rotulo(frame, 'Texto de explicação que deve ocupar a largura do painel. ' * 5)
            for escala in (1, 1.25, 1.5):
                ctk.set_widget_scaling(escala)
                for largura in (760, 600, 900):
                    root.geometry(f'{largura}x600+10000+10000')
                    for _ in range(3):
                        root.update()
                        time.sleep(.01)
                    disponivel = label.winfo_width() / label._get_widget_scaling()
                    self.assertAlmostEqual(label.cget('wraplength'), disponivel - 8, delta=3)
            self.assertFalse(falhas, falhas[0] if falhas else '')
        finally:
            ctk.set_widget_scaling(1)
            root.destroy()


if __name__ == '__main__':
    unittest.main()
