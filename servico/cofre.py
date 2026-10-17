"""Chave aleatória do banco, envelope de senha e DPAPI opcional do serviço.

A migração publica um diretório completo por rename. A cópia portátil anterior
permanece preservada e nunca é utilizada como fallback depois da migração.
"""
import base64
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import shutil
import tempfile
from uuid import uuid4
import zipfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
import config
from models.models import BancoDados
from models.seguranca import (Cofre, ErroSeguranca, ErroAutenticacao, ERROS_BANCO, TravaSessao, conectar,
                              conferir_integridade, copiar_protegido, validar_nova_senha)

AAD = b'GiStocker/envelope/v2'


def b64(dado):
    return base64.b64encode(dado).decode('ascii')


def derivar(senha, sal):
    if not isinstance(senha,str) or not 1<=len(senha)<=128:
        raise ValueError('Informe a senha de acesso.')
    return Scrypt(salt=sal,length=32,n=2**15,r=8,p=1).derive(senha.encode('utf-8'))


def embrulhar(chave, senha):
    sal, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    cifrado = AESGCM(derivar(senha,sal)).encrypt(nonce,chave.encode('ascii'),AAD)
    return dict(versao=2,sal=b64(sal),nonce=b64(nonce),cifrado=b64(cifrado))


def desembrulhar(envelope, senha):
    try:
        if envelope['versao']!=2:
            raise ValueError()
        sal, nonce, cifrado = (base64.b64decode(envelope[k],validate=True) for k in ('sal','nonce','cifrado'))
        if len(sal)!=16 or len(nonce)!=12 or len(cifrado)!=80:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise ErroSeguranca('Envelope inválido. Restaure uma cópia protegida íntegra.') from None
    try:
        return AESGCM(derivar(senha,sal)).decrypt(nonce,cifrado,AAD).decode('ascii')
    except InvalidTag:
        raise ErroAutenticacao('Senha incorreta ou envelope danificado.') from None
    except UnicodeDecodeError:
        raise ErroSeguranca('Conteúdo do envelope inválido.') from None


def gravar_atomico(caminho, dados):
    tmp = caminho.with_name('.envelope_' + uuid4().hex)
    try:
        with tmp.open('x',encoding='utf-8') as f:
            json.dump(dados,f,separators=(',',':'))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,caminho)
    finally:
        tmp.unlink(missing_ok=True)


class CofreServico:
    def __init__(self, raiz):
        self.raiz = Path(raiz).resolve()
        self.raiz.mkdir(parents=True,exist_ok=True)
        self.pasta = self.raiz/'cofre_v2'
        self.envelope = self.pasta/'acesso.json'
        self.caminho = self.pasta/'estoque.db'
        self.exportacoes = self.raiz/'exportacoes'
        origem = self.raiz/'portatil_importado' if (self.raiz/'portatil_importado').is_dir() else self.raiz
        # Portátil: <pasta>/dados + <pasta>/exportacoes. Instalado, o legado só existe como cópia
        # importada; o pai de ProgramData\GiStocker não pertence ao aplicativo.
        exportacoes = origem/'exportacoes' if config.INSTALADO else self.raiz.parent/'exportacoes'
        self.legado = Cofre(origem/'estoque.db',origem/'configuracoes.db',exportacoes)
        self.banco = None
        self.chave = None
        self.trava = None
        self.aviso_backup = None

    def ler_envelope(self):
        if self.envelope.stat().st_size>8192:
            raise ErroSeguranca('Envelope inválido.')
        return json.loads(self.envelope.read_text(encoding='utf-8'))

    @property
    def modo(self):
        if self.pasta.exists():
            if not self.envelope.is_file() or not self.caminho.is_file():
                raise ErroSeguranca('Cofre incompleto. Restaure uma cópia protegida; não crie outro banco.')
            return 'protegido'
        return self.legado.modo

    def _abrir_chave(self, chave):
        if self.banco is not None:
            return self.banco
        self.trava = TravaSessao(self.pasta/'.sessao.lock')
        try:
            self.banco = BancoDados(self.caminho,senha=chave,backup_automatico=False)
            self.chave = chave
        except BaseException:
            self.fechar()
            raise
        self.aviso_backup = None
        try:
            backups = self.raiz/'backups'
            hoje = datetime.now(timezone.utc).strftime('%Y%m%d')
            if not any(backups.glob('GiStocker_'+hoje+'_*.gsbackup')):
                self.exportar(backups)
                self._podar_backups(backups)
        except (OSError, *ERROS_BANCO, ErroSeguranca) as falha:
            from utils.erros import registrar_falha
            registrar_falha(falha, pasta=self.raiz/'logs')
            self.aviso_backup = 'Backup diário não pôde ser criado. Confira o espaço e as permissões da pasta de backups.'
        return self.banco

    @staticmethod
    def _podar_backups(pasta):
        """Mantém só os .gsbackup automáticos mais recentes; .gsa legados não são tocados."""
        copias = sorted(pasta.glob('GiStocker_*.gsbackup'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        for antiga in copias[config.BACKUPS_MANTIDOS:]:
            antiga.unlink()

    def abrir(self, senha, nova=None, confirmacao=None):
        if not self.pasta.exists():
            self._migrar(senha,nova,confirmacao)
            senha = nova if nova is not None else senha
        chave = desembrulhar(self.ler_envelope()['senha'],senha)
        return self._abrir_chave(chave)

    def _migrar(self, senha, nova, confirmacao):
        modo = self.legado.modo
        senha_efetiva = nova if modo in ('novo','legado') else senha
        if modo in ('novo', 'legado'):
            validar_nova_senha(nova,confirmacao)
        destino = self.raiz/('.cofre_' + uuid4().hex)
        destino.mkdir()
        trava_antiga = None
        try:
            chave = secrets.token_hex(32)
            if modo=='novo':
                BancoDados(destino/'estoque.db',senha=chave,criar=True,backup_automatico=False).fechar()
            else:
                if modo=='legado':
                    # Conversão legada já auditada protege também CSVs/backups antigos.
                    banco = self.legado.abrir(senha,nova,confirmacao)
                    copiar_protegido(banco.conexao,destino/'estoque.db')
                else:
                    # Não migrar o esquema do original: permite rollback para a versão 1.
                    trava_antiga = TravaSessao(self.legado.caminho.parent/'.sessao.lock')
                    with closing(conectar(self.legado.caminho,senha,somente_leitura=True)) as origem:
                        conferir_integridade(origem)
                        copiar_protegido(origem,destino/'estoque.db')
                with closing(conectar(destino/'estoque.db',senha_efetiva)) as con:
                    con.execute('PRAGMA journal_mode=DELETE')
                    con.reset_key(chave)
                BancoDados(destino/'estoque.db',senha=chave,backup_automatico=False).fechar()
            with closing(conectar(destino/'estoque.db',chave)) as con:
                conferir_integridade(con)
            gravar_atomico(destino/'acesso.json',{'senha':embrulhar(chave,senha_efetiva),'servico':None,'tema':self.legado.obter_tema()})
            destino.rename(self.pasta)
        finally:
            self.legado.fechar()
            if trava_antiga:
                trava_antiga.fechar()
            if destino.exists():
                if destino.resolve().parent != self.raiz:
                    raise ErroSeguranca('O diretório de preparação mudou. Limpeza interrompida.')
                shutil.rmtree(destino)

    def verificar_senha(self, senha):
        try:
            desembrulhar(self.ler_envelope()['senha'],senha)
            return True
        except (ErroSeguranca,ValueError):
            return False

    def alterar_senha(self, antiga, nova, confirmacao):
        if self.banco is None:
            raise ErroSeguranca('Desbloqueie o sistema.')
        validar_nova_senha(nova,confirmacao)
        e = self.ler_envelope()
        chave = desembrulhar(e['senha'],antiga)   # ErroAutenticacao: o Nucleo limita e informa
        if antiga==nova:
            raise ValueError('Escolha uma senha diferente da atual.')
        e['senha'] = embrulhar(chave,nova)
        gravar_atomico(self.envelope,e)

    def permitir_segundo_plano(self, permitir):
        if self.chave is None:
            raise ErroSeguranca('Desbloqueie o sistema.')
        import win32crypt
        e = self.ler_envelope()
        e['servico'] = b64(win32crypt.CryptProtectData(self.chave.encode('ascii'),'GiStocker',AAD,None,None,1)) if permitir else None
        gravar_atomico(self.envelope,e)

    def abrir_segundo_plano(self):
        if not self.pasta.exists():
            return False
        import win32crypt
        blob = self.ler_envelope().get('servico')
        if not blob:
            return False
        try:
            chave = win32crypt.CryptUnprotectData(base64.b64decode(blob),AAD,None,None,1)[1].decode('ascii')
            self._abrir_chave(chave)
            return True
        except Exception:
            self.fechar()
            raise ErroSeguranca('Proteção desta máquina indisponível. Desbloqueie com a senha para reautorizar o serviço.') from None

    def obter_tema(self):
        return self.ler_envelope().get('tema','dark') if self.pasta.exists() else self.legado.obter_tema()

    def definir_tema(self, tema):
        if self.banco is None or tema not in ('dark','light'):
            raise ErroSeguranca('Tema ou sessão inválidos.')
        e = self.ler_envelope()
        e['tema'] = tema
        gravar_atomico(self.envelope,e)

    def exportar(self, pasta=None):
        if self.banco is None:
            raise ErroSeguranca('Desbloqueie o sistema.')
        pasta = Path(pasta) if pasta is not None else self.exportacoes
        pasta.mkdir(parents=True,exist_ok=True)
        destino = pasta/('GiStocker_' + datetime.now(timezone.utc).strftime('%Y%m%d')+'_'+uuid4().hex + '.gsbackup')
        parcial = destino.with_suffix('.parcial')
        # Temporários contêm somente conteúdo SQLCipher e envelope cifrado.
        try:
            with tempfile.TemporaryDirectory(dir=pasta) as tmp:
                db = copiar_protegido(self.banco.conexao,Path(tmp)/'estoque.db')
                with zipfile.ZipFile(parcial,'x',compression=zipfile.ZIP_STORED) as z:
                    z.write(db,'estoque.db')
                    z.writestr('acesso.json',json.dumps({'senha':self.ler_envelope()['senha'],'servico':None,'tema':self.obter_tema()}))
                with parcial.open('r+b') as arquivo:
                    os.fsync(arquivo.fileno())
                parcial.rename(destino)
        finally:
            parcial.unlink(missing_ok=True)
        return destino

    def fechar(self):
        if self.banco is not None:
            self.banco.fechar()
        self.banco = self.chave = None
        if self.trava:
            self.trava.fechar()
        self.trava = None


def restaurar(copia, destino, senha):
    """Restaura em diretório NOVO. Nunca sobrescreve uma instalação existente."""
    destino = Path(destino)
    if destino.exists():
        raise ErroSeguranca('Escolha uma pasta nova para validar a restauração.')
    with zipfile.ZipFile(copia) as z:
        if sorted(z.namelist())!=['acesso.json','estoque.db'] or z.getinfo('acesso.json').file_size>8192:
            raise ErroSeguranca('Cópia protegida inválida.')
        envelope = json.loads(z.read('acesso.json'))
        chave = desembrulhar(envelope['senha'],senha)
        envelope['servico'] = None
        destino.mkdir(parents=True)
        staging = destino/'.restauracao'
        staging.mkdir()
        with z.open('estoque.db') as entrada, (staging/'estoque.db').open('xb') as saida:
            import shutil
            shutil.copyfileobj(entrada,saida)
        bd = BancoDados(staging/'estoque.db',senha=chave,backup_automatico=False)
        try:
            conferir_integridade(bd.conexao)
            # Restaurar nunca retoma publicação automaticamente.
            with bd.transacao():
                bd.conexao.execute("UPDATE Config_Multicanal SET estado='FISICO'")
        finally:
            bd.fechar()
        gravar_atomico(staging/'acesso.json',envelope)
        staging.rename(destino/'cofre_v2')
