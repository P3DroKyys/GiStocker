"""Confere o pacote produzido; não abre nem altera dados da loja."""
import hashlib
import json
import marshal
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config

from PyInstaller.archive.readers import CArchiveReader
import sqlcipher3._sqlite3 as motor
import rapidfuzz


def sha256(caminho):
    with caminho.open('rb') as arquivo:
        return hashlib.file_digest(arquivo, 'sha256').hexdigest()


def validar(pasta):
    pasta = Path(pasta).resolve(strict=True)
    manifesto = json.loads((pasta / 'SHA256.json').read_text(encoding='utf-8'))
    arquivos = {p.relative_to(pasta).as_posix(): p for p in pasta.rglob('*') if p.is_file()}
    assert set(arquivos) == set(manifesto) | {'SHA256.json'}, 'Conteúdo diferente do manifesto'
    for nome, resumo in manifesto.items():
        assert sha256(arquivos[nome]) == resumo, f'Hash diferente: {nome}'
    assert not (pasta / 'dados').exists(), 'Dados não devem acompanhar a build'
    assert not (pasta / 'exportacoes').exists()
    assert not any(Path(nome).suffix in {'.db', '.gsa'} for nome in arquivos)
    assert not any(parte in {'auditoria', '.venv', 'conan_cache'} for nome in arquivos for parte in Path(nome).parts)
    nativos = list((pasta / '_internal' / 'sqlcipher3').glob('_sqlite3*.pyd'))
    assert len(nativos) == 1
    assert sha256(nativos[0]) == sha256(Path(motor.__file__)), 'Motor diferente do testado'
    raiz_rapidfuzz = Path(rapidfuzz.__file__).parent
    nativos_busca = list(raiz_rapidfuzz.rglob('*.pyd'))
    assert nativos_busca, 'RapidFuzz nativo ausente no ambiente de validação'
    for biblioteca in nativos_busca:
        empacotada = pasta / '_internal' / 'rapidfuzz' / biblioteca.relative_to(raiz_rapidfuzz)
        assert empacotada.is_file() and sha256(empacotada) == sha256(biblioteca), f'Biblioteca de busca diferente: {biblioteca.name}'
    libs_busca = list((raiz_rapidfuzz.parent / 'rapidfuzz.libs').glob('*.dll'))
    for biblioteca in libs_busca:
        empacotada = pasta / '_internal' / 'rapidfuzz.libs' / biblioteca.name
        assert empacotada.is_file() and sha256(empacotada) == sha256(biblioteca), f'DLL auxiliar de busca ausente/diferente: {biblioteca.name}'
    exe = pasta / 'GestorEstoque.exe'
    arquivo = CArchiveReader(str(exe))
    nome_pyz = next(nome for nome in arquivo.toc if nome.endswith('.pyz'))
    pyz = arquivo.open_embedded_archive(nome_pyz)
    nomes = set(pyz.toc)
    necessarios = {'models.seguranca', 'models.models', 'models.preferencias',
                  'controllers.controllers', 'views.acesso', 'views.main_view',
                  'views.tarefas', 'sqlcipher3', 'sqlcipher3.dbapi2',
                  'utils.busca', 'rapidfuzz', 'rapidfuzz.distance.DamerauLevenshtein'}
    assert necessarios <= nomes, necessarios - nomes
    assert not any(nome.startswith(('auditoria', 'verificar', 'pip_audit', 'conan')) for nome in nomes)
    codigo = pyz.extract('config')
    if isinstance(codigo, bytes):
        codigo = marshal.loads(codigo)
    assert config.VERSAO_APP in codigo.co_consts
    return dict(pasta=str(pasta), arquivos_verificados=len(manifesto),
                bytes=sum(p.stat().st_size for p in arquivos.values()),
                modulos=len(nomes), motor_sha256=sha256(nativos[0]),
                bibliotecas_nativas_busca_verificadas=len(nativos_busca),
                exe_sha256=sha256(exe), versao=config.VERSAO_APP,
                dados_reais_incluidos=False, testes_e_ferramentas_auditoria_incluidos=False,
                resultado='OK')


if __name__ == '__main__':
    resultado = validar(sys.argv[1])
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
