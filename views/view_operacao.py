"""
Tela principal de operação (View_Operacao).

Fluxo otimizado para leitor de código de barras USB:
  1. O campo de código está sempre em foco (autofoco constante).
  2. O leitor envia o código + Enter -> o produto é identificado e exibido.
  3. O foco pula para "Quantidade" (padrão 1). Digite a quantidade e Enter.
  4. A movimentação é registrada e o foco volta ao campo de código.
Com o "Modo rápido" ligado, cada leitura registra 1 unidade imediatamente.
"""
from __future__ import annotations

import tkinter as tk

import sqlite3
from models.seguranca import ERROS_BANCO, ERROS_OPERACIONAIS, ErroSeguranca
from utils.erros import mensagem_falha

import customtkinter as ctk

import config
from controllers.controllers import ErroNegocio
from utils.texto import formatar_data_hora, formatar_inteiro, formatar_moeda
from views.componentes import (
    COR_PERIGO, COR_TEXTO_ERRO, COR_TEXTO_INFO, COR_TEXTO_SUAVE, COR_TEXTO_SUCESSO,
    alertar, confirmar, erro,
)

OPCAO_ENTRADA = "ENTRADA"
OPCAO_SAIDA = "SAÍDA"
INTERVALO_AUTOFOCO_MS = 400
CORES_STATUS = {"info": COR_TEXTO_INFO, "sucesso": COR_TEXTO_SUCESSO, "erro": COR_TEXTO_ERRO}


def descrever_log(log, nome_produto: str) -> str:
    """Texto curto de um log para confirmações e mensagens."""
    if log.tipo == config.TIPO_AJUSTE:
        return (f"Ajuste em '{nome_produto}' (estoque {log.estoque_anterior} → "
                f"{log.estoque_posterior}, custo {formatar_moeda(log.custo_anterior)} → "
                f"{formatar_moeda(log.custo_no_momento)})")
    return f"{log.tipo} de {log.quantidade} un. — '{nome_produto}'"


class ViewOperacao(ctk.CTkFrame):
    def __init__(self, master, janela):
        super().__init__(master, fg_color="transparent")
        self.janela = janela
        self.controlador = janela.controlador_estoque
        self.produto_atual = None
        self._construir()
        self._atualizar_recentes()
        self._autofoco_agendado = self.after(INTERVALO_AUTOFOCO_MS, self._verificar_autofoco)

    # ------------------------------------------------------------------ #
    # Construção
    # ------------------------------------------------------------------ #
    def _construir(self) -> None:
        self.grid_columnconfigure(0, weight=3, uniform="col")
        self.grid_columnconfigure(1, weight=2, uniform="col")
        self.grid_rowconfigure(0, weight=1)

        esquerda = ctk.CTkFrame(self, fg_color="transparent")
        esquerda.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        direita = ctk.CTkFrame(self, corner_radius=14)
        direita.grid(row=0, column=1, sticky="nsew")

        ctk.CTkLabel(esquerda, text="Operação de Estoque", anchor="w",
                     font=ctk.CTkFont(size=26, weight="bold")).pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(esquerda, text="Entradas e saídas, com tudo sob controle.", anchor="w",
                     text_color=COR_TEXTO_SUAVE).pack(fill="x", pady=(0, 18))

        # [ ENTRADA ] [ SAÍDA ]
        self.seletor_tipo = ctk.CTkSegmentedButton(
            esquerda, values=[OPCAO_ENTRADA, OPCAO_SAIDA], command=self._ao_mudar_tipo,
            font=ctk.CTkFont(size=14, weight="bold"), height=44)
        self.seletor_tipo.set(OPCAO_ENTRADA)
        self.seletor_tipo.pack(fill="x", pady=(0, 14))

        # Campo do leitor
        ctk.CTkLabel(esquerda, text="Código de barras", anchor="w",
                     text_color=COR_TEXTO_SUAVE).pack(fill="x")
        self.entrada_codigo = ctk.CTkEntry(
            esquerda, height=54, font=ctk.CTkFont(size=22),
            placeholder_text="Escaneie ou digite o código e pressione Enter")
        self.entrada_codigo.pack(fill="x", pady=(2, 12))
        for tecla in ("<Return>", "<KP_Enter>"):
            self.entrada_codigo.bind(tecla, self._ao_ler_codigo)

        # Cartão do produto identificado
        self.cartao = ctk.CTkFrame(esquerda, corner_radius=14)
        self.cartao.pack(fill="x", pady=(0, 12))
        self.rotulo_nome = ctk.CTkLabel(self.cartao, text="Aguardando leitura…", anchor="w",
                                        justify="left", wraplength=560,
                                        font=ctk.CTkFont(size=20, weight="bold"))
        self.rotulo_nome.pack(fill="x", padx=14, pady=(12, 2))
        self.rotulo_detalhes = ctk.CTkLabel(self.cartao, text="", anchor="w",
                                            text_color=COR_TEXTO_SUAVE)
        self.rotulo_detalhes.pack(fill="x", padx=14)
        linha_numeros = ctk.CTkFrame(self.cartao, fg_color="transparent")
        linha_numeros.pack(fill="x", padx=14, pady=(6, 12))
        self.rotulo_estoque = ctk.CTkLabel(linha_numeros, text="", anchor="w",
                                           font=ctk.CTkFont(size=15, weight="bold"))
        self.rotulo_estoque.pack(side="left")
        self.rotulo_custo = ctk.CTkLabel(linha_numeros, text="", text_color=COR_TEXTO_SUAVE)
        self.rotulo_custo.pack(side="left", padx=(18, 0))
        self.rotulo_preco = ctk.CTkLabel(linha_numeros, text="", text_color=COR_TEXTO_SUAVE)
        self.rotulo_preco.pack(side="left", padx=(18, 0))

        # Quantidade / custo unitário
        campos = ctk.CTkFrame(esquerda, fg_color="transparent")
        campos.pack(fill="x", pady=(0, 10))
        quadro_qtd = ctk.CTkFrame(campos, fg_color="transparent")
        quadro_qtd.grid(row=0, column=0, sticky="w", padx=(0, 20))
        ctk.CTkLabel(quadro_qtd, text="Quantidade", anchor="w",
                     text_color=COR_TEXTO_SUAVE).pack(fill="x")
        self.entrada_quantidade = ctk.CTkEntry(quadro_qtd, width=150, height=46,
                                               font=ctk.CTkFont(size=20), justify="center")
        self.entrada_quantidade.insert(0, "1")
        self.entrada_quantidade.pack()
        self.quadro_custo = ctk.CTkFrame(campos, fg_color="transparent")
        self.quadro_custo.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(self.quadro_custo, text="Custo unitário (R$) – opcional", anchor="w",
                     text_color=COR_TEXTO_SUAVE).pack(fill="x")
        self.entrada_custo = ctk.CTkEntry(self.quadro_custo, width=200, height=46,
                                          font=ctk.CTkFont(size=18),
                                          placeholder_text="vazio = custo atual")
        self.entrada_custo.pack()
        for campo in (self.entrada_quantidade, self.entrada_custo):
            for tecla in ("<Return>", "<KP_Enter>"):
                campo.bind(tecla, self._confirmar)
        for campo in (self.entrada_codigo, self.entrada_quantidade, self.entrada_custo):
            campo.bind("<Escape>", self._limpar)

        # Botões
        botoes = ctk.CTkFrame(esquerda, fg_color="transparent")
        botoes.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(botoes, text="Confirmar   (Enter)", height=46,
                      font=ctk.CTkFont(size=16, weight="bold"), command=self._confirmar
                      ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(botoes, text="Limpar   (Esc)", height=46, width=150, fg_color="transparent",
                      border_width=1, text_color=("gray10", "#DCE4EE"), command=self._limpar
                      ).pack(side="left")

        self.var_modo_rapido = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(esquerda, text="Modo rápido: registrar 1 unidade a cada leitura",
                      variable=self.var_modo_rapido, onvalue=True, offvalue=False
                      ).pack(anchor="w", pady=(0, 10))

        self.rotulo_status = ctk.CTkLabel(esquerda, text="Pronto para leitura.", anchor="w",
                                          justify="left", wraplength=600, text_color=COR_TEXTO_INFO)
        self.rotulo_status.pack(fill="x")

        # Coluna direita: últimas movimentações + desfazer
        ctk.CTkLabel(direita, text="Últimas movimentações", anchor="w",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(fill="x", padx=14, pady=(12, 6))
        self.caixa_recentes = ctk.CTkTextbox(direita, font=ctk.CTkFont(size=13),
                                             state="disabled", wrap="word", fg_color="transparent",
                                             spacing1=4, spacing3=5)
        self.caixa_recentes.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        ctk.CTkButton(direita, text="Desfazer última ação", height=42,
                      font=ctk.CTkFont(size=13), border_width=1,
                      fg_color="transparent", border_color=("#E3BFC5", "#644049"),
                      text_color=COR_TEXTO_ERRO, hover_color=("#FBECEF", "#392831"), command=self._desfazer
                      ).pack(fill="x", padx=14, pady=(0, 14))

    # ------------------------------------------------------------------ #
    # Protocolo da janela principal
    # ------------------------------------------------------------------ #
    def ao_mostrar(self, **_dados) -> None:
        self._atualizar_recentes()
        self._focar_codigo(limpar=False)

    # ------------------------------------------------------------------ #
    # Autofoco constante
    # ------------------------------------------------------------------ #
    def _foco_em_campo_da_tela(self, widget) -> bool:
        caminho = str(widget)
        return any(caminho.startswith(str(campo)) for campo in
                   (self.entrada_codigo, self.entrada_quantidade, self.entrada_custo))

    def _verificar_autofoco(self) -> None:
        """A cada 400 ms devolve o foco ao campo de código, exceto quando o
        usuário está digitando em Quantidade/Custo ou em outra janela (diálogo)."""
        try:
            if self.winfo_ismapped():
                foco = self.focus_get()
                if foco is None or (foco.winfo_toplevel() is self.winfo_toplevel()
                                    and not self._foco_em_campo_da_tela(foco)):
                    self.entrada_codigo.focus_set()
        except (tk.TclError, KeyError):
            pass
        self._autofoco_agendado = self.after(INTERVALO_AUTOFOCO_MS, self._verificar_autofoco)

    def _focar_codigo(self, limpar: bool = True) -> None:
        if not self.winfo_exists():
            return
        if limpar:
            self.entrada_codigo.delete(0, "end")
        self.entrada_codigo.focus_set()

    # ------------------------------------------------------------------ #
    # Ações
    # ------------------------------------------------------------------ #
    def _ao_mudar_tipo(self, valor: str) -> None:
        if valor == OPCAO_ENTRADA:
            self.quadro_custo.grid()
        else:
            self.quadro_custo.grid_remove()
        self._focar_codigo(limpar=False)

    def _ao_ler_codigo(self, _evento=None) -> None:
        codigo = self.entrada_codigo.get().strip()
        if not codigo:
            return
        produto = self.controlador.resolver_codigo_barras(codigo)
        if produto is None:
            self._limpar_produto()
            self._definir_status(f"Código {codigo} não cadastrado.", "erro")
            if confirmar("Código não encontrado",
                         f"O código {codigo} não está vinculado a nenhum produto.\n\n"
                         "Deseja cadastrar o produto agora?"):
                self.janela.mostrar_view("cadastro", codigo=codigo)
            else:
                self._focar_codigo()
            return

        self.produto_atual = produto
        self._exibir_produto(produto)
        if self.var_modo_rapido.get():
            self.entrada_quantidade.delete(0, "end")
            self.entrada_quantidade.insert(0, "1")
            self._confirmar()
        else:
            self._definir_status("Produto identificado. Informe a quantidade e pressione Enter.", "info")
            self.entrada_quantidade.focus_set()
            self.entrada_quantidade.select_range(0, "end")

    def _confirmar(self, _evento=None) -> None:
        if self.produto_atual is None:
            self._definir_status("Leia um código de barras antes de confirmar.", "erro")
            self._focar_codigo()
            return
        tipo = self.seletor_tipo.get()
        try:
            if tipo == OPCAO_ENTRADA:
                resultado = self.controlador.registrar_entrada(
                    self.produto_atual.id, self.entrada_quantidade.get(), self.entrada_custo.get())
            else:
                resultado = self.controlador.registrar_saida(
                    self.produto_atual.id, self.entrada_quantidade.get())
        except (ErroNegocio, ErroSeguranca, *ERROS_BANCO, OSError) as falha:
            self._definir_status(mensagem_falha(falha), "erro")
            self.entrada_quantidade.focus_set()
            self.entrada_quantidade.select_range(0, "end")
            return

        mensagem = (f"{resultado.tipo} registrada: {resultado.quantidade} un. de "
                    f"'{resultado.produto.nome}'. Estoque: {resultado.estoque_anterior} → "
                    f"{resultado.estoque_novo}.")
        if resultado.tipo == config.TIPO_ENTRADA and abs(resultado.custo_novo - resultado.custo_anterior) > 1e-9:
            mensagem += (f" Custo médio: {formatar_moeda(resultado.custo_anterior)} → "
                         f"{formatar_moeda(resultado.custo_novo)}.")
        self._definir_status(mensagem, "sucesso")
        self._limpar_produto()
        self._atualizar_recentes()
        self._focar_codigo()

    def _desfazer(self) -> None:
        ultima = self.controlador.obter_ultima_acao()
        if ultima is None:
            alertar("Desfazer", "Não há nenhuma ação para desfazer.")
            self._focar_codigo(limpar=False)
            return
        log = ultima.log
        texto = (f"{descrever_log(log, ultima.produto.nome)}\n"
                 f"Registrada em {formatar_data_hora(log.data_hora)}.\n\n"
                 f"O estoque voltará para {log.estoque_anterior} un. Confirmar?")
        if not confirmar("Desfazer última ação", texto):
            self._focar_codigo(limpar=False)
            return
        try:
            resultado = self.controlador.desfazer_ultima_acao(log_id_esperado=log.id)
        except (ErroNegocio, ErroSeguranca, *ERROS_BANCO, OSError) as falha:
            erro("Desfazer", mensagem_falha(falha))
            return
        self._definir_status(
            f"Ação desfeita: {descrever_log(resultado.log, resultado.produto.nome)}. "
            f"Estoque atual: {resultado.produto.estoque_atual} un.", "sucesso")
        if self.produto_atual and self.produto_atual.id == resultado.produto.id:
            self._exibir_produto(resultado.produto)
        self._atualizar_recentes()
        self._focar_codigo(limpar=False)

    def _limpar(self, _evento=None) -> None:
        self._limpar_produto()
        self._definir_status("Pronto para leitura.", "info")
        self._focar_codigo()

    # ------------------------------------------------------------------ #
    # Atualização visual
    # ------------------------------------------------------------------ #
    def _exibir_produto(self, produto) -> None:
        self.rotulo_nome.configure(text=produto.nome)
        self.rotulo_detalhes.configure(text=f"{produto.marca}  •  {produto.categoria}  •  ID {produto.id}")
        self.rotulo_estoque.configure(text=f"Estoque: {formatar_inteiro(produto.estoque_atual)} un.")
        self.rotulo_custo.configure(text=f"Custo médio: {formatar_moeda(produto.custo_medio)}")
        self.rotulo_preco.configure(text=f"Preço base: {formatar_moeda(produto.preco_venda_base)}")

    def _limpar_produto(self) -> None:
        self.produto_atual = None
        self.rotulo_nome.configure(text="Aguardando leitura…")
        for rotulo in (self.rotulo_detalhes, self.rotulo_estoque, self.rotulo_custo, self.rotulo_preco):
            rotulo.configure(text="")
        self.entrada_quantidade.delete(0, "end")
        self.entrada_quantidade.insert(0, "1")
        self.entrada_custo.delete(0, "end")

    def _definir_status(self, texto: str, tipo: str = "info") -> None:
        self.rotulo_status.configure(text=texto, text_color=CORES_STATUS[tipo])

    def _atualizar_recentes(self) -> None:
        logs = self.controlador.listar_logs(limite=config.QTD_MOVIMENTACOES_RECENTES)
        linhas = []
        for log in logs:
            if log["tipo"] == config.TIPO_SAIDA:
                quantidade = f"-{log['quantidade']}"
            else:
                quantidade = f"{log['quantidade']:+d}"
            situacao = "  ·  Cancelado" if log["cancelado"] else ""
            origem = {'FISICO':'Físico','SHOPEE':'Shopee','TIKTOK':'TikTok Shop'}.get(log.get('origem','FISICO'),'Físico')
            linhas.append(f"{log['tipo']}  ·  {origem}  ·  {quantidade} un.{situacao}\n"
                          f"{log['produto_nome']}\n{formatar_data_hora(log['data_hora'])}\n")
        self.caixa_recentes.configure(state="normal")
        self.caixa_recentes.delete("1.0", "end")
        self.caixa_recentes.insert("end", "\n".join(linhas) if linhas else "Nenhuma movimentação ainda.")
        self.caixa_recentes.configure(state="disabled")

    def destroy(self):
        if getattr(self, '_autofoco_agendado', None):
            self.after_cancel(self._autofoco_agendado)
            self._autofoco_agendado = None
        super().destroy()
