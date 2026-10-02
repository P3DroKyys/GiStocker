"""Reproduz a wheel local a partir das fontes oficiais e do OpenSSL do Conan.

Pré-requisitos: Python 3.14 x64, MSVC, wheel/setuptools, fontes/amalgamation e
openssl_graph.json gerados conforme README_COMPILACAO.md.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import sys

base = Path(__file__).resolve().parent
projeto = base.parents[1]
fonte = base / 'sqlcipher3-0.6.2'
engine = base / 'sqlcipher-4.18.0'
graph = json.loads((base / 'openssl_graph.json').read_text(encoding='utf-8-sig'))
dep = next(n for n in graph['graph']['nodes'].values() if str(n.get('ref', '')).startswith('openssl/'))
openssl = Path(dep['package_folder'])
assert (openssl / 'lib' / 'libcrypto.lib').is_file()
assert '#define SQLITE_VERSION        "3.53.4"' in (engine / 'sqlite3.c').read_text(encoding='utf-8')
for nome in ('sqlite3.c', 'sqlite3.h', 'sqlite3ext.h'):
 shutil.copy2(engine / nome, fonte / 'vendor' / nome)
with tarfile.open(base / 'sqlcipher3-0.6.2.tar.gz') as archive:
 s = archive.extractfile('sqlcipher3-0.6.2/setup.py').read().decode('utf-8')
a=s.index('    try:\n        import conan'); b=s.index('    extra_compile_args =', a)
s=s[:a] + f'    library_dirs = [{str(openssl / "lib")!r}]\n    include_dirs = [{str(openssl / "include")!r}, "./vendor", "./src"]\n' + s[b:]
for feature in ('SQLITE_ENABLE_FTS3', 'SQLITE_ENABLE_FTS3_PARENTHESIS', 'SQLITE_ENABLE_FTS4', 'SQLITE_ENABLE_FTS5', 'SQLITE_ENABLE_JSON1', 'SQLITE_ENABLE_LOAD_EXTENSION', 'SQLITE_ENABLE_RTREE', 'SQLITE_SOUNDEX'):
 s='\n'.join(line for line in s.split('\n') if f"('{feature}'," not in line)
s=s.replace("('SQLITE_TEMP_STORE', '2')", "('SQLITE_TEMP_STORE', '3')")
s=s.replace("('SQLITE_MAX_VARIABLE_NUMBER', '250000')", "('SQLITE_MAX_VARIABLE_NUMBER', '10000')")
s=s.replace("('SQLITE_THREADSAFE', '1'),", "('SQLITE_THREADSAFE', '1'),\n        ('SQLITE_OMIT_LOAD_EXTENSION', '1'),\n        ('SQLITE_DEFAULT_DEFENSIVE', '1'),\n        ('SQLITE_TRUSTED_SCHEMA', '0'),")
s=s.replace("VERSION = '0.6.2'", "VERSION = '0.6.2+gistocker.sqlcipher418'")
s=s.replace("extra_link_args = []", "extra_link_args = ['/MANIFEST:NO']")
(fonte / 'setup.py').write_text(s,encoding='utf-8')
p=fonte/'pyproject.toml';s=p.read_text();s=s.replace('version = "0.6.2"','version = "0.6.2+gistocker.sqlcipher418"').replace('requires-python = ">=3.9"','requires-python = ">=3.14,<3.15"');p.write_text(s)
destino=projeto/'vendor';destino.mkdir(exist_ok=True)
subprocess.run([sys.executable,'setup.py','bdist_wheel','--dist-dir',str(destino)],cwd=fonte,check=True)
print('Wheel gerada em',destino)
