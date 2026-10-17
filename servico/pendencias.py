"""Journal da interface: só hashes de comandos e UUIDs, nunca valores/senhas."""
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from models.seguranca import TravaSessao, ErroSeguranca
from servico.cofre import gravar_atomico


class Pendencias:
    def __init__(self, raiz, producao):
        pasta=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'GiStocker' if producao else Path(raiz)
        self.caminho=pasta/'comandos_pendentes.json'
        self.trava=None
        self.chave=None

    def iniciar(self, assinatura):
        self.trava=TravaSessao(self.caminho.with_suffix('.lock'))
        try:
            if self.caminho.exists():
                if self.caminho.stat().st_size>1024*1024: raise ValueError()
                self.dados=json.loads(self.caminho.read_text(encoding='utf-8'))
                if type(self.dados) is not dict: raise ValueError()
                for k,v in self.dados.items():
                    if type(k) is not str or len(k)!=64: raise ValueError()
                    UUID(v)
            else: self.dados={}
            self.chave=hashlib.sha256(assinatura.encode('utf-8')).hexdigest()
            # Cada ação é nova; apenas o chamador repete o UUID durante esta chamada.
            id_pedido=str(uuid4())
            self.dados={self.chave:id_pedido}
            gravar_atomico(self.caminho,self.dados)
            return id_pedido
        except (OSError, ValueError, TypeError):
            self.fechar()
            raise ErroSeguranca('Não foi possível preservar o identificador da operação. Nenhuma solicitação de gravação foi enviada.') from None

    def confirmar(self):
        self.dados.pop(self.chave,None)
        gravar_atomico(self.caminho,self.dados)

    def fechar(self):
        if self.trava: self.trava.fechar()
        self.trava=None
