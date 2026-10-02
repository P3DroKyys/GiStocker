"""
Dashboard analítico (View_Dashboard).

  * Cartões KPI: total de itens, valor investido (estoque x custo médio) e
    receita bruta potencial (estoque x preço base);
  * gráfico de barras Entradas x Saídas (últimos N dias);
  * duas rosquinhas (pizza): marcas e categorias mais vendidas;
  * rankings textuais: Curva A (mais vendidos) e Estoque Parado (sem saída há X dias).

Os gráficos são matplotlib embutidos (FigureCanvasTkAgg) e são redesenhados
com as cores do tema ativo sempre que a tela é exibida ou o tema muda.
"""
from __future__ import annotations

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

import config
from utils.texto import converter_para_int, formatar_data_hora, formatar_inteiro, formatar_moeda
from views.componentes import COR_TEXTO_SUAVE, CartaoKPI, cor_fundo_efetiva, erro, paleta_atual


class ViewDashboard(ctk.CTkFrame):
    def __init__(self, master, janela):
        super().__init__(master, fg_color="transparent")
        self.janela = janela
        self.relatorios = janela.controlador_relatorios
        self.graficos: dict[str, tuple[ctk.CTkFrame, Figure, FigureCanvasTkAgg]] = {}
        self._construir()

    # ------------------------------------------------------------------ #
    # Construção
    # ------------------------------------------------------------------ #
    def _construir(self) -> None:
        cabecalho = ctk.CTkFrame(self, fg_color="transparent")
        cabecalho.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(cabecalho, text="Dashboard", font=ctk.CTkFont(size=24, weight="bold")
                     ).pack(side="left")
        ctk.CTkButton(cabecalho, text="Atualizar", width=110, command=self.atualizar).pack(side="right")
        self.entrada_dias = ctk.CTkEntry(cabecalho, width=60, justify="center")
        self.entrada_dias.insert(0, str(config.DIAS_ESTOQUE_PARADO_PADRAO))
        self.entrada_dias.pack(side="right", padx=(6, 12))
        self.entrada_dias.bind("<Return>", lambda _e: self.atualizar())
        ctk.CTkLabel(cabecalho, text="Estoque parado há (dias):", text_color=COR_TEXTO_SUAVE
                     ).pack(side="right")

        self.area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.area.pack(fill="both", expand=True)
        self.area.grid_columnconfigure((0, 1), weight=1, uniform="col")

        # KPIs
        linha_kpi = ctk.CTkFrame(self.area, fg_color="transparent")
        linha_kpi.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.linha_kpi = linha_kpi
        linha_kpi.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="kpi")
        self.kpi_itens = CartaoKPI(linha_kpi, "Quantidade total de itens")
        self.kpi_produtos = CartaoKPI(linha_kpi, "Produtos cadastrados")
        self.kpi_investido = CartaoKPI(linha_kpi, "Valor total investido")
        self.kpi_receita = CartaoKPI(linha_kpi, "Receita bruta potencial")
        self._colunas_kpi = None
        linha_kpi.bind("<Configure>", self._organizar_kpis)
        self._organizar_kpis()

        # Gráficos
        self._criar_grafico("barras", linha=1, coluna=0, colspan=2, altura=320)
        self._criar_grafico("marcas", linha=2, coluna=0, altura=330)
        self._criar_grafico("categorias", linha=2, coluna=1, altura=330)

        # Rankings
        self.caixa_curva_a = self._criar_caixa_texto("Curva A – mais vendidos", linha=3, coluna=0)
        self.caixa_parado = self._criar_caixa_texto("Estoque parado", linha=3, coluna=1)

    def _organizar_kpis(self, _evento=None) -> None:
        # Duas linhas em janelas menores; uma linha quando há espaço para os títulos.
        largura = self.linha_kpi.winfo_width() / self._get_widget_scaling()
        colunas = 4 if largura >= 1000 else 2
        if colunas == self._colunas_kpi:
            return
        self._colunas_kpi = colunas
        for indice in range(4):
            self.linha_kpi.grid_columnconfigure(indice, weight=1 if indice < colunas else 0,
                                                 uniform="kpi" if indice < colunas else "")
        for indice, cartao in enumerate((self.kpi_itens, self.kpi_produtos, self.kpi_investido, self.kpi_receita)):
            cartao.grid(row=indice // colunas, column=indice % colunas, sticky="ew", padx=6, pady=4)

    def _criar_grafico(self, nome: str, linha: int, coluna: int, altura: int, colspan: int = 1) -> None:
        quadro = ctk.CTkFrame(self.area, corner_radius=14, height=altura)
        quadro.grid(row=linha, column=coluna, columnspan=colspan, sticky="nsew", padx=6, pady=6)
        quadro.pack_propagate(False)
        figura = Figure(dpi=100, constrained_layout=True)
        canvas = FigureCanvasTkAgg(figura, master=quadro)
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
        self.graficos[nome] = (quadro, figura, canvas)

    def _criar_caixa_texto(self, titulo: str, linha: int, coluna: int) -> ctk.CTkTextbox:
        quadro = ctk.CTkFrame(self.area, corner_radius=14)
        quadro.grid(row=linha, column=coluna, sticky="nsew", padx=6, pady=6)
        ctk.CTkLabel(quadro, text=titulo, anchor="w", font=ctk.CTkFont(size=15, weight="bold")
                     ).pack(fill="x", padx=14, pady=(12, 4))
        caixa = ctk.CTkTextbox(quadro, height=170, state="disabled", wrap="word",
                               fg_color="transparent", font=ctk.CTkFont(size=13))
        caixa.pack(fill="both", expand=True, padx=8, pady=(0, 10))
        return caixa

    # ------------------------------------------------------------------ #
    # Protocolo da janela principal
    # ------------------------------------------------------------------ #
    def ao_mostrar(self, **_dados) -> None:
        self.atualizar()

    def ao_mudar_tema(self) -> None:
        self.atualizar()

    # ------------------------------------------------------------------ #
    # Atualização
    # ------------------------------------------------------------------ #
    def atualizar(self) -> None:
        try:
            dias_parado = max(1, converter_para_int(self.entrada_dias.get()))
        except ValueError:
            dias_parado = config.DIAS_ESTOQUE_PARADO_PADRAO
            self.entrada_dias.delete(0, "end")
            self.entrada_dias.insert(0, str(dias_parado))
        try:
            kpis = self.relatorios.obter_kpis()
            self.kpi_itens.definir(f"{formatar_inteiro(kpis['total_itens'])} un.")
            self.kpi_produtos.definir(formatar_inteiro(kpis["total_produtos"]))
            self.kpi_investido.definir(formatar_moeda(kpis["valor_investido"]))
            self.kpi_receita.definir(formatar_moeda(kpis["receita_potencial"]))

            self._desenhar_barras()
            self._desenhar_rosquinha("marcas", "Marcas mais vendidas", self.relatorios.ranking_marcas())
            self._desenhar_rosquinha("categorias", "Categorias mais vendidas",
                                     self.relatorios.ranking_categorias())
            self._preencher_curva_a()
            self._preencher_estoque_parado(dias_parado)
        except Exception as falha:  # noqa: BLE001 - qualquer falha vira mensagem ao usuário
            erro("Dashboard", f"Não foi possível atualizar o dashboard:\n{falha}")

    # ------------------------------------------------------------------ #
    # Gráficos
    # ------------------------------------------------------------------ #
    def _preparar_eixo(self, nome: str, titulo: str):
        """Limpa a figura, aplica o fundo do tema e devolve (eixo, paleta, canvas)."""
        quadro, figura, canvas = self.graficos[nome]
        paleta = paleta_atual()
        fundo = cor_fundo_efetiva(quadro)
        figura.clear()
        figura.set_facecolor(fundo)
        eixo = figura.add_subplot(111)
        eixo.set_facecolor(fundo)
        eixo.set_title(titulo, color=paleta["texto"], fontsize=11, loc="left", pad=10)
        return eixo, paleta, canvas, fundo

    def _desenhar_barras(self) -> None:
        dias = config.DIAS_GRAFICO_MOVIMENTACAO
        eixo, p, canvas, _ = self._preparar_eixo("barras", f"Entradas x Saídas – últimos {dias} dias")
        datas, entradas, saidas = self.relatorios.movimentacao_ultimos_dias(dias)
        posicoes = range(len(datas))
        eixo.bar([i - 0.2 for i in posicoes], entradas, width=0.4, color=p["series"][0],
                 label="Entradas", linewidth=0)
        eixo.bar([i + 0.2 for i in posicoes], saidas, width=0.4, color=p["series"][1],
                 label="Saídas", linewidth=0)
        passo = max(1, len(datas) // 6)
        eixo.set_xticks(list(posicoes)[::passo])
        eixo.set_xticklabels([d.strftime("%d/%m") for d in datas][::passo])
        eixo.yaxis.set_major_locator(MaxNLocator(integer=True))
        for lado in ("top", "right", "left"):
            eixo.spines[lado].set_visible(False)
        eixo.spines["bottom"].set_color(p["eixo"])
        eixo.tick_params(colors=p["texto_suave"], labelsize=9, length=0)
        eixo.yaxis.grid(True, color=p["grade"], linewidth=0.8)
        eixo.set_axisbelow(True)
        # A legenda ocupa uma faixa própria abaixo do eixo, fora da área das barras.
        # constrained_layout reserva esse espaço também ao redimensionar a janela.
        eixo.margins(y=0.15)
        legenda = eixo.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.13),
                               ncol=2, fontsize=9)
        for texto in legenda.get_texts():
            texto.set_color(p["texto_secundario"])
        if not any(entradas) and not any(saidas):
            eixo.text(0.5, 0.5, "Sem movimentações no período", transform=eixo.transAxes,
                      ha="center", va="center", color=p["texto_suave"])
        canvas.draw_idle()

    def _desenhar_rosquinha(self, nome: str, titulo: str, dados: list[tuple[str, int]]) -> None:
        eixo, p, canvas, fundo = self._preparar_eixo(nome, titulo)
        if not dados:
            eixo.text(0.5, 0.5, "Sem saídas registradas", transform=eixo.transAxes,
                      ha="center", va="center", color=p["texto_suave"])
            eixo.axis("off")
            canvas.draw_idle()
            return
        rotulos = [d[0] for d in dados]
        valores = [d[1] for d in dados]
        total = sum(valores) or 1
        cores = [p["texto_suave"] if r == "Outras" else p["series"][i % len(p["series"])]
                 for i, r in enumerate(rotulos)]
        fatias, _ = eixo.pie(valores, colors=cores, startangle=90, counterclock=False,
                             wedgeprops=dict(width=0.42, edgecolor=fundo, linewidth=2))
        legendas = [f"{r} – {v / total:.0%} ({formatar_inteiro(v)} un.)" for r, v in zip(rotulos, valores)]
        legenda = eixo.legend(fatias, legendas, loc="center left", bbox_to_anchor=(1.0, 0.5),
                              frameon=False, fontsize=9)
        for texto in legenda.get_texts():
            texto.set_color(p["texto_secundario"])
        eixo.set_aspect("equal")
        canvas.draw_idle()

    # ------------------------------------------------------------------ #
    # Rankings
    # ------------------------------------------------------------------ #
    @staticmethod
    def _preencher_caixa(caixa: ctk.CTkTextbox, linhas: list[str], vazio: str) -> None:
        caixa.configure(state="normal")
        caixa.delete("1.0", "end")
        caixa.insert("end", "\n".join(linhas) if linhas else vazio)
        caixa.configure(state="disabled")

    def _preencher_curva_a(self) -> None:
        itens = self.relatorios.curva_a(config.TAMANHO_CURVA_A)
        linhas = [f"{i}º  {item['nome']} ({item['marca']})  —  "
                  f"{formatar_inteiro(item['total_saidas'])} un. vendidas em "
                  f"{item['qtd_movimentacoes']} saídas  •  estoque atual {item['estoque_atual']}"
                  for i, item in enumerate(itens, start=1)]
        self._preencher_caixa(self.caixa_curva_a, linhas, "Ainda não há saídas registradas.")

    def _preencher_estoque_parado(self, dias: int) -> None:
        itens = self.relatorios.estoque_parado(dias)
        linhas = []
        for item in itens:
            if item["ultima_saida"]:
                referencia = f"última saída em {formatar_data_hora(item['ultima_saida'], com_hora=False)}"
            else:
                referencia = f"nunca vendido (desde {formatar_data_hora(item['referencia'], com_hora=False)})"
            linhas.append(f"•  {item['nome']} ({item['marca']})  —  estoque {item['estoque_atual']} un.  —  {referencia}")
        self._preencher_caixa(self.caixa_parado, linhas, f"Nenhum produto parado há mais de {dias} dias.")

    def destroy(self):
        for _, figura, canvas in self.graficos.values():
            for nome in ('_idle_draw_id', '_event_loop_id'):
                tarefa = getattr(canvas, nome, None)
                if tarefa:
                    canvas.get_tk_widget().after_cancel(tarefa)
                    setattr(canvas, nome, None)
            figura.clear()
        self.graficos.clear()
        super().destroy()
