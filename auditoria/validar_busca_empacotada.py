"""Execute em processo novo: python -I -B este_script.py PASTA_DA_BUILD.

Carrega a biblioteca distribuída e o bytecode da busca do executável, usando
somente produtos fictícios. Não abre banco ou tela de autenticação.
"""
from pathlib import Path
import json
import os
import sys
import types

from PyInstaller.archive.readers import CArchiveReader


def validar(pasta):
    base = Path(pasta).resolve(strict=True)
    sys.path.insert(0, str(base / '_internal'))
    dll_handle = os.add_dll_directory(str(base / '_internal')) if os.name == 'nt' else None
    try:
        import rapidfuzz
        from rapidfuzz.distance import DamerauLevenshtein
        assert Path(rapidfuzz.__file__).is_relative_to(base)
        implementacao = sys.modules[DamerauLevenshtein.distance.__module__]
        assert Path(implementacao.__file__).is_relative_to(base)
        assert 'metrics_cpp' in implementacao.__name__, 'Fallback Python: confira as DLLs auxiliares'
        arquivo = CArchiveReader(str(base / 'GestorEstoque.exe'))
        pyz = arquivo.open_embedded_archive(next(n for n in arquivo.toc if n.endswith('.pyz')))
        utils = types.ModuleType('utils')
        utils.__path__ = []
        sys.modules['utils'] = utils
        for nome in ('config', 'utils.texto', 'utils.busca'):
            modulo = types.ModuleType(nome)
            modulo.__file__ = str(base / '_internal' / (nome.replace('.', '/') + '.py'))
            sys.modules[nome] = modulo
            exec(pyz.extract(nome), modulo.__dict__)
        from utils.busca import IndiceProdutos
        produto = types.SimpleNamespace(id=1, nome='Colônia Malbec 200ml', marca='Boticário',
                                        categoria='Perfume', codigos=['96385074'])
        indice = IndiceProdutos([produto])
        assert indice.pesquisar('malbce').aproximada
        assert indice.pesquisar('malbce').produtos[0].id == 1
        assert indice.pesquisar('96385074').produtos[0].id == 1
        assert not indice.pesquisar('96385075').produtos
        return dict(resultado='OK', versao=sys.modules['config'].VERSAO_APP,
                    modulos_aplicacao='Bytecode extraído do PYZ da build',
                    rapidfuzz=str(rapidfuzz.__file__), implementacao=str(implementacao.__file__),
                    dados_reais_acessados=False)
    finally:
        if dll_handle:
            dll_handle.close()


if __name__ == '__main__':
    print(json.dumps(validar(sys.argv[1]), ensure_ascii=False, indent=2))
