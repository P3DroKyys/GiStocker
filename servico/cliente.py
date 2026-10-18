"""Fachada MVC. A interface não recebe chave, conexão nem caminho de escrita."""
from functools import partial
from pathlib import Path
import json
from types import SimpleNamespace
from uuid import uuid4

from controllers.controllers import ControladorEstoque, ErroNegocio
from models.seguranca import ErroSeguranca, ErroSessao
from servico.nucleo import LEITURAS, ESCRITAS, PROTEGIDAS, RELATORIOS
from servico.pipe import chamar, nome_pipe, ERROS_TRANSPORTE
from servico.protocolo import VERSAO, decodificar
from servico.pendencias import Pendencias


class Proxy:
    def __init__(self, cliente, grupo):
        self.cliente, self.grupo = cliente, grupo

    def __getattr__(self, nome):
        if self.grupo=='estoque' and nome=='calcular_custo_medio_ponderado':
            return ControladorEstoque.calcular_custo_medio_ponderado
        if self.grupo=='relatorios' and nome=='exportar_protegido':
            return lambda: self.cliente.chamar('backup')
        permitidos = LEITURAS|ESCRITAS if self.grupo=='estoque' else RELATORIOS
        if nome not in permitidos:
            raise AttributeError(nome)
        if self.grupo == 'estoque' and nome in ('listar_produtos', 'buscar_produtos', 'pesquisar_produtos'):
            return partial(self._listar, nome)
        return partial(self.cliente.chamar,self.grupo+'.'+nome)

    def _listar(self, nome, *args, **kwargs):
        # Filtros locais do catálogo recebem a lista completa em mensagens limitadas.
        if 'limite' in kwargs or 'offset' in kwargs:
            return self.cliente.chamar(self.grupo+'.'+nome, *args, **kwargs)
        resultado = None
        offset = 0
        while True:
            pagina = self.cliente.chamar(self.grupo+'.'+nome, *args, limite=200, offset=offset, **kwargs)
            itens = pagina.produtos if nome == 'pesquisar_produtos' else pagina
            tamanho = len(itens)
            if resultado is None:
                resultado = pagina
            else:
                (resultado.produtos if nome == 'pesquisar_produtos' else resultado).extend(itens)
            if tamanho < 200:
                return resultado
            offset += tamanho


class Cliente:
    def __init__(self, raiz, producao=False):
        self.raiz = Path(raiz)
        self.nome = nome_pipe(raiz,producao)
        self.producao = producao
        self.sessao = None
        self.banco = None  # apenas sentinela de sessão para compatibilidade visual
        self.ao_indisponivel = None
        self.journal = Pendencias(raiz,producao)
        self.ultimo_status = {'modo':'protegido','tema':'dark'}

    def chamar(self, comando, *args, **kwargs):
        assinatura = json.dumps([comando,args,kwargs],sort_keys=True,ensure_ascii=True)
        # Escritas protegidas levam a senha: nunca entram no journal nem são reenviadas.
        mutacao = (comando.startswith('estoque.') and comando.split('.',1)[1] in ESCRITAS - PROTEGIDAS or
                   comando in ('integracoes.vincular','integracoes.cobertura','integracoes.politica','integracoes.receber','integracoes.pedido_operar','integracoes.catalogo_exemplo'))
        try:
            chave = self.journal.iniciar(assinatura) if mutacao else str(uuid4())
            resultado=self._enviar(comando,args,kwargs,chave,mutacao)
            if mutacao:
                self.journal.confirmar()
            return resultado
        except (ErroNegocio,ValueError):
            if mutacao and self.journal.trava:
                self.journal.confirmar()  # erro de negócio é rollback confirmado
            raise
        finally:
            if mutacao:
                self.journal.fechar()

    def _enviar(self, comando, args, kwargs, chave, repetir=False):
        pedido = dict(v=VERSAO,id=chave,sessao=self.sessao,comando=comando,args=list(args),kwargs=kwargs)
        for tentativa in range(2 if repetir else 1):
            try:
                resposta = chamar(self.nome,pedido,self.producao)
                break
            except ERROS_TRANSPORTE:
                if repetir and tentativa == 0:
                    continue
                raise ErroSeguranca('O serviço local não respondeu. Confira o histórico antes de iniciar outra operação: a gravação pode ter sido concluída.') from None
        if resposta.get('id')!=chave or resposta.get('v')!=VERSAO:
            raise ErroSeguranca('Resposta incompatível do serviço.')
        if not resposta.get('ok'):
            sessao_invalida = resposta.get('codigo')=='SESSAO'
            if sessao_invalida and self.sessao and self.ao_indisponivel:
                self.ao_indisponivel()
            classe = (ErroSessao if sessao_invalida else ErroNegocio if resposta.get('erro')=='ErroNegocio'
                      else ValueError if resposta.get('erro') in ('ValueError','TypeError') else ErroSeguranca)
            raise classe(resposta.get('mensagem','Operação não concluída.'))
        resultado=decodificar(resposta['resultado'])
        if comando=='status':
            self.ultimo_status=resultado
        elif comando=='login':
            self.ultimo_status['aviso']=resposta.get('aviso')
        return resultado

    @property
    def modo(self):
        try: return self.chamar('status')['modo']
        except ErroSeguranca: return self.ultimo_status['modo']

    def obter_tema(self):
        try: return self.chamar('status')['tema']
        except ErroSeguranca: return self.ultimo_status['tema']

    def abrir(self, senha, nova=None, confirmacao=None):
        if not self.producao:
            from servico.executar import garantir_agente
            try:
                garantir_agente(self.raiz, False)
            except RuntimeError as erro:
                raise ErroSeguranca(str(erro)) from None
        self.sessao = self.chamar('login',senha,nova,confirmacao)
        self.banco = SimpleNamespace(_fechado=False,criptografado=True)

    def criar_controladores(self):
        return Proxy(self,'estoque'),Proxy(self,'relatorios')

    def definir_tema(self, tema):
        return self.chamar('tema',tema)

    def alterar_senha(self, antiga, nova, confirmacao):
        return self.chamar('senha',antiga,nova,confirmacao)

    def atividade(self):
        if self.sessao:
            self.chamar('atividade')

    def fechar(self):
        try:
            if self.sessao:
                self.chamar('logout')
        except ErroSeguranca:
            pass  # bloqueio visual nunca depende de o serviço estar acessível
        finally:
            self.sessao = self.banco = None
