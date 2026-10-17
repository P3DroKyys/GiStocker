"""Importação offline conservadora. Nunca move nem apaga os dados de origem."""
import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4

from models.seguranca import ErroSeguranca, TravaSessao, CABECALHO_SQLITE
from servico.cofre import gravar_atomico


def importar_portatil(origem, destino):
    origem,destino=Path(origem).resolve(),Path(destino).resolve()
    if origem==destino or origem.is_relative_to(destino) or destino.is_relative_to(origem):
        raise ErroSeguranca('Origem e destino devem ser independentes.')
    if any((destino/nome).exists() for nome in ('estoque.db','cofre_v2','portatil_importado')):
        raise ErroSeguranca('Já existem dados na instalação. Não serão sobrescritos.')
    if origem.is_symlink() or not origem.is_dir():
        raise ErroSeguranca('Pasta de origem inválida.')
    v2=(origem/'cofre_v2').is_dir()
    pasta=origem/'cofre_v2' if v2 else origem
    if not (pasta/'estoque.db').is_file():
        raise ErroSeguranca('Banco portátil não encontrado.')
    with (pasta/'estoque.db').open('rb') as f:
        if f.read(16)==CABECALHO_SQLITE:
            raise ErroSeguranca('Proteja o banco pela versão portátil antes de importá-lo.')
    travas=[]
    try:
        for lock in {origem/'.agente.lock',origem/'.sessao.lock',pasta/'.sessao.lock'}:
            travas.append(TravaSessao(lock))
        staging=destino/('.importacao_'+uuid4().hex)
        staging.mkdir(parents=True)
        arquivos=['estoque.db','estoque.db-wal','estoque.db-shm','acesso.json'] if v2 else ['estoque.db','estoque.db-wal','estoque.db-shm','configuracoes.db','aparencia.json']
        hashes={}
        for nome in arquivos:
            src=pasta/nome
            if not src.exists(): continue
            if src.is_symlink() or not src.is_file(): raise ErroSeguranca('Arquivo de origem inválido.')
            if nome=='estoque.db-shm': continue  # índice transitório; SQLite reconstrói a partir do WAL
            antes=src.stat()
            shutil.copyfile(src,staging/nome)
            with src.open('rb') as f: original=hashlib.file_digest(f,'sha256').hexdigest()
            with (staging/nome).open('rb') as f: copia=hashlib.file_digest(f,'sha256').hexdigest()
            if original!=copia or src.stat().st_mtime_ns!=antes.st_mtime_ns:
                raise ErroSeguranca('Arquivo mudou durante a cópia. Feche o programa antigo.')
            hashes[nome]=copia
        if v2:
            e=json.loads((staging/'acesso.json').read_text(encoding='utf-8'))
            e['servico']=None
            gravar_atomico(staging/'acesso.json',e)
            staging.rename(destino/'cofre_v2')
        else:
            # Publica todo o conjunto atomicamente; senha/integridade serão
            # verificadas pelo SQLCipher antes de liberar a primeira sessão.
            staging.rename(destino/'portatil_importado')
        gravar_atomico(destino/'importacao.json',{'origem_preservada':True,'validacao_criptografica':'PENDENTE_LOGIN','sha256_origem':hashes})
    finally:
        for trava in travas: trava.fechar()
