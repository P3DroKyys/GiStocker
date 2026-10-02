"""Prévia visual isolada: banco em memória e produtos fictícios.

Uso: python auditoria/preview_visual.py --tema dark --tela operacao
"""
import argparse
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import customtkinter as ctk
import config
from controllers.controllers import ControladorEstoque, ControladorRelatorios
from models.models import BancoDados
from models.seguranca import Cofre
from verificar_seguranca import SENHA
from views.main_view import JanelaPrincipal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tema", choices=("light", "dark"), default="dark")
    parser.add_argument("--tela", choices=("acesso", "configuracoes", "operacao", "cadastro", "dashboard", "relatorios", "admin"), default="operacao")
    parser.add_argument("--tamanho", default="1280x800")
    args = parser.parse_args()
    ctk.set_appearance_mode(args.tema)
    ctk.set_default_color_theme(config.TEMA_COR)
    with tempfile.TemporaryDirectory(prefix="gistocker_preview_") as pasta:
        preferencias = Cofre(Path(pasta) / "dados" / "estoque.db")
        banco = preferencias.abrir("", SENHA, SENHA)
        preferencias.definir_tema(args.tema)
        estoque = ControladorEstoque(banco)
        for nome, marca, categoria, preco, custo, quantidade in (
            ("Lily · Hidratante corporal 250 g", "O Boticário", "Corpo e Banho", 129.90, 68.50, 18),
            ("Siàge · Shampoo 250 ml", "Eudora", "Cabelos", 59.90, 29.90, 24),
            ("Ekos · Colônia fresca 150 ml", "Natura", "Perfumaria", 119.90, 64.00, 12),
        ):
            p = estoque.cadastrar_produto(nome, marca, categoria, preco, custo, quantidade)
            estoque.registrar_saida(p.id, 2)
        if args.tela == "acesso":
            preferencias.fechar()
        janela = JanelaPrincipal(preferencias)
        janela.geometry(args.tamanho)
        janela.title(f"GiStocker · PRÉVIA {args.tela} {args.tema} · dados fictícios")
        if args.tela != "acesso":
            janela._liberar_acesso()
            janela.mostrar_view(args.tela)
        try:
            janela.mainloop()
        finally:
            preferencias.fechar()


if __name__ == "__main__":
    main()
