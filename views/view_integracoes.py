"""Painel de ensaio isolado, com ações explícitas e sem credenciais de produção."""
import customtkinter as ctk
from uuid import uuid4

from controllers.controllers import ErroNegocio
from models.seguranca import ErroSeguranca
from views.componentes import COR_TEXTO_SUAVE, criar_tabela, limpar_tabela, confirmar


class ViewIntegracoes(ctk.CTkFrame):
    def __init__(self, master, janela):
        super().__init__(master,fg_color='transparent')
        self.janela = janela
        self.dados = None
        self.tarefa = None
        ctk.CTkLabel(self,text='Integrações',font=ctk.CTkFont(size=24,weight='bold')).pack(anchor='w')
        ctk.CTkLabel(self,text='Ambiente de simulação · estoque real preservado · nenhuma loja conectada',text_color=COR_TEXTO_SUAVE).pack(anchor='w',pady=(4,12))
        barra=ctk.CTkFrame(self,fg_color='transparent'); barra.pack(fill='x')
        for texto,acao in [('Preparar simulação','ativar_simulacao'),('Iniciar / retomar ensaio','iniciar_ensaio'),('Pausar','pausar'),('Encerrar','encerrar')]:
            ctk.CTkButton(barra,text=texto,command=lambda a=acao:self.acao(a)).pack(side='left',padx=(0,8))
        self.status=ctk.CTkLabel(self,text='',anchor='w',wraplength=900,justify='left'); self.status.pack(fill='x',pady=8)
        self.tabs=ctk.CTkTabview(self); self.tabs.pack(fill='both',expand=True)
        for nome in ('Cotas','Vínculos','Pedidos','Monitor'): self.tabs.add(nome)
        self._cotas(); self._vinculos(); self._pedidos(); self._monitor()

    def tabela(self, master, titulos):
        quadro,tabela=criar_tabela(master,[(str(i),v,140,'w',True) for i,v in enumerate(titulos)],altura=8,rolagem_horizontal=True)
        quadro.pack(fill='both',expand=True,pady=8)
        return tabela

    def _cotas(self):
        aba=self.tabs.tab('Cotas')
        ctk.CTkLabel(aba,text='Por produto: metade do saldo livre fica reservada para a loja física. Sobras são sorteadas e preservadas.',text_color=COR_TEXTO_SUAVE).pack(anchor='w')
        self.cotas=self.tabela(aba,['Produto','Em mãos','Reservado','Físico','Online','Exposto','Quarentena'])
        campos=ctk.CTkFrame(aba,fg_color='transparent'); campos.pack(fill='x')
        ctk.CTkLabel(campos,text='Reserva física (%)').pack(side='left')
        self.percentual=ctk.CTkEntry(campos,width=70); self.percentual.insert(0,'50'); self.percentual.pack(side='left',padx=8)
        ctk.CTkLabel(campos,text='Margem (un.)').pack(side='left')
        self.margem=ctk.CTkEntry(campos,width=70); self.margem.insert(0,'0'); self.margem.pack(side='left',padx=8)
        ctk.CTkButton(campos,text='Aplicar ao selecionado',command=self.salvar_politica).pack(side='left')

    def _vinculos(self):
        aba=self.tabs.tab('Vínculos')
        ctk.CTkButton(aba,text='Criar catálogo fictício a partir da cópia local',command=lambda:self.acao('catalogo_exemplo')).pack(anchor='w')
        self.catalogo=self.tabela(aba,['Canal','Anúncio / variação','GTIN','Produto associado'])
        self.catalogo.bind('<<TreeviewSelect>>',self.sugerir)
        self.produto=ctk.CTkComboBox(aba,values=['Selecione um anúncio'],width=500,state='readonly'); self.produto.pack(anchor='w',pady=6)
        self.sugestao=ctk.CTkLabel(aba,text='',text_color=COR_TEXTO_SUAVE); self.sugestao.pack(anchor='w')
        ctk.CTkButton(aba,text='Confirmar vínculo selecionado',command=self.vincular).pack(anchor='w',pady=6)
        linha=ctk.CTkFrame(aba,fg_color='transparent'); linha.pack(fill='x')
        self.canal=ctk.CTkComboBox(linha,values=['SHOPEE','TIKTOK'],state='readonly',width=140); self.canal.pack(side='left')
        ctk.CTkButton(linha,text='Produto selecionado não publicado neste canal',command=self.nao_publicado).pack(side='left',padx=8)

    def _pedidos(self):
        aba=self.tabs.tab('Pedidos')
        ctk.CTkLabel(aba,text='Crie um pedido de teste para o anúncio selecionado em Vínculos.',text_color=COR_TEXTO_SUAVE).pack(anchor='w')
        linha=ctk.CTkFrame(aba,fg_color='transparent'); linha.pack(fill='x')
        self.quantidade=ctk.CTkEntry(linha,width=70); self.quantidade.insert(0,'1'); self.quantidade.pack(side='left',padx=6)
        ctk.CTkButton(linha,text='Simular pedido',command=self.novo_pedido).pack(side='left')
        self.pedidos=self.tabela(aba,['Produto','Quantidade','Cancelada','Situação'])
        acoes=ctk.CTkFrame(aba,fg_color='transparent'); acoes.pack(fill='x')
        self.operacao=ctk.CTkComboBox(acoes,width=260,state='readonly',values=['Separar','Embalar','Enviar','Cancelar quantidade informada','Conferir retorno à prateleira','Receber devolução','Aprovar devolução','Reprovar devolução']); self.operacao.pack(side='left')
        ctk.CTkButton(acoes,text='Aplicar ao pedido',command=self.operar_pedido).pack(side='left',padx=8)

    def _monitor(self):
        aba=self.tabs.tab('Monitor')
        linha=ctk.CTkFrame(aba,fg_color='transparent'); linha.pack(fill='x')
        self.falha=ctk.CTkComboBox(linha,width=250,state='readonly',values=['NORMAL','SEM_INTERNET','TOKEN_VENCIDO','RATE_LIMIT','TIMEOUT_APOS_ENVIO']); self.falha.pack(side='left')
        ctk.CTkButton(linha,text='Aplicar cenário',command=lambda:self.acao('falha',None if self.falha.get()=='NORMAL' else self.falha.get())).pack(side='left',padx=8)
        ctk.CTkButton(aba,text='Retomar política local após divergência',command=self.reconciliar).pack(anchor='w',pady=8)
        self.monitor=ctk.CTkTextbox(aba,wrap='word'); self.monitor.pack(fill='both',expand=True,pady=10)

    def chamar(self, acao, *args):
        return self.janela.preferencias.chamar('integracoes.'+acao,*args)

    def reconciliar(self):
        if confirmar('Conciliação da simulação','Confirma retomar as cotas calculadas pelo GiStocker para anúncios com alteração externa detectada?'):
            self.acao('reconciliar')

    def acao(self, acao, *args):
        try:
            self.chamar(acao,*args)
            self.atualizar()
        except (ErroNegocio,ErroSeguranca,ValueError) as erro:
            self.status.configure(text=str(erro))

    def ao_mostrar(self, **_):
        self.atualizar()
        self._agendar()

    def _agendar(self):
        self.ao_ocultar()
        self.tarefa=self.after(5000,self._periodico)

    def _periodico(self):
        self.tarefa=None
        self.atualizar()
        self._agendar()

    def ao_ocultar(self):
        if self.tarefa:
            self.after_cancel(self.tarefa); self.tarefa=None

    def atualizar(self):
        try:
            self.dados=self.chamar('painel')
        except (ErroNegocio,ErroSeguranca,ValueError) as erro:
            self.status.configure(text=str(erro)); return
        sim=self.dados['simulacao']
        self.status.configure(text='Modo físico, sem tarefas de rede. Ative a simulação para ensaiar as integrações.' if not sim else f"Simulação {self.dados['estado'].lower()} · a cópia de teste permanece independente do estoque real.")
        for tabela in (self.cotas,self.catalogo,self.pedidos):
            selecionados=tabela.selection()
            tabela._selecionados=selecionados
            limpar_tabela(tabela)
        for p in (sim or {}).get('produtos',self.dados['local']):
            self.cotas.insert('', 'end',iid=str(p['produto_id']),values=(p['nome'],p['em_maos'],p['comprometido'],p['reserva_fisica'],p['ecommerce'],p['exposta'],p['quarentena']))
        self.remotos={c['id']:c for c in (sim or {}).get('catalogo',[])}
        for c in self.remotos.values():
            self.catalogo.insert('','end',iid=c['id'],values=(c['canal'],c['titulo']+' '+c['variacao'],c['gtin'] or 'Não informado',c['produto_id'] or 'Pendente'))
        # O id do item identifica a linha entre atualizações; a posição muda com novos pedidos.
        self.itens={p['id']:p for p in (sim or {}).get('pedidos',[])}
        for i,p in self.itens.items():
            self.pedidos.insert('','end',iid=i,values=(p['produto_id'],p['quantidade'],p['cancelada'],p['estado']))
        for tabela in (self.cotas,self.catalogo,self.pedidos):
            for i in tabela._selecionados:
                if tabela.exists(i): tabela.selection_add(i)
        texto=['Nenhuma loja real conectada. Autorizações oficiais serão configuradas na fase de piloto.','']
        if sim:
            texto += [f"Comandos pendentes: {len(sim['fila'])}",f"Incidentes: {len(sim['incidentes'])}",'']
            texto += [f"{i['tipo']} · produto {i['produto_id'] or 'pendente de vínculo'}" for i in sim['incidentes']]
            texto += ['','Últimos eventos (UTC):']+[f"{e['criado']} | {e['origem']} | {e['natureza']} | {e['delta']:+d}" for e in sim['eventos'][:30]]
        self.monitor.configure(state='normal'); self.monitor.delete('1.0','end'); self.monitor.insert('end','\n'.join(texto)); self.monitor.configure(state='disabled')

    def selecionado(self,tabela):
        s=tabela.selection()
        if not s: raise ValueError('Selecione uma linha primeiro.')
        return s[0]

    def sugerir(self,_=None):
        try:
            r=self.chamar('sugerir',self.selecionado(self.catalogo))
            produtos=r['produtos'] or self.janela.controlador_estoque.listar_produtos()
            self.opcoes={f'{p.nome} · {p.marca} · #{p.id}':p.id for p in produtos}
            valores=list(self.opcoes)
            self.produto.configure(values=valores or ['Nenhum produto disponível'])
            self.produto.set(valores[0] if valores else 'Nenhum produto disponível')
            self.sugestao.configure(text=r['criterio']+'. Confira nome, volume e variação antes de confirmar.')
        except (ErroNegocio,ErroSeguranca,ValueError): pass

    def vincular(self):
        try: self.acao('vincular',self.selecionado(self.catalogo),self.opcoes[self.produto.get()])
        except (ValueError,KeyError,AttributeError): self.status.configure(text='Selecione o anúncio e o produto correspondente.')

    def nao_publicado(self):
        try: self.acao('cobertura',int(self.selecionado(self.cotas)),self.canal.get(),'NAO_PUBLICADO')
        except ValueError as e: self.status.configure(text=str(e))

    def salvar_politica(self):
        try: self.acao('politica',int(self.selecionado(self.cotas)),int(self.percentual.get()),int(self.margem.get()))
        except ValueError: self.status.configure(text='Selecione um produto e informe números inteiros.')

    def novo_pedido(self):
        try:
            c=self.remotos[self.selecionado(self.catalogo)]
            e=dict(loja=c['loja'],pedido=uuid4().hex,linha='1',remoto=c['id'],quantidade=int(self.quantidade.get()),cancelada=0,versao=1,estado='RESERVADO')
            self.acao('receber',e)
        except (KeyError,ValueError): self.status.configure(text='Selecione um anúncio vinculado e uma quantidade válida.')

    def operar_pedido(self):
        try:
            p=self.itens[self.selecionado(self.pedidos)]
            operacao=self.operacao.get()
            if operacao=='Cancelar quantidade informada':
                import json
                loja,pedido=json.loads(p['pedido_id'])
                cancelada=p['cancelada']+int(self.quantidade.get())
                self.acao('receber',dict(loja=loja,pedido=pedido,linha=p['linha'],remoto=p['remoto'],quantidade=p['quantidade'],cancelada=cancelada,versao=p['versao']+1,estado='CANCELADO' if cancelada==p['quantidade'] else 'RESERVADO'))
            else:
                acoes={'Separar':'SEPARAR','Embalar':'EMBALAR','Enviar':'ENVIAR','Conferir retorno à prateleira':'CONFERIR_RETORNO','Receber devolução':'RECEBER_DEVOLUCAO','Aprovar devolução':'APROVAR_DEVOLUCAO','Reprovar devolução':'REPROVAR_DEVOLUCAO'}
                self.acao('pedido_operar',p['id'],acoes[operacao])
        except (KeyError,ValueError): self.status.configure(text='Selecione um pedido e confira a quantidade.')

    def destroy(self):
        self.ao_ocultar()
        super().destroy()
