# Compilação do motor nativo Windows x64

Artefato da entrega: `vendor/sqlcipher3-0.6.2+gistocker.sqlcipher418-cp314-cp314-win_amd64.whl`
(caminho relativo à raiz do projeto).

SHA-256: `11265efdae34bc912a55fffa546bc23dd94485ade8a9f618f50e595f79fbb50d`.

Composição: binding sqlcipher3 0.6.2, SQLCipher Community 4.18.0 / SQLite 3.53.4,
OpenSSL 3.5.9 LTS estático. A versão local identifica as modificações de compilação;
não é uma release oficial do binding. Não houve alteração intencional dos
algoritmos criptográficos desses fornecedores.

## Fontes e ferramentas

- Python 3.14.3 x64; MSVC 18 Build Tools, ferramenta 14.50.35717;
  Windows SDK 10.0.26100.0. `compilar_wheel.cmd` contém os caminhos usados.
- Conan 2.33.0, setuptools/wheel da venv. Conan obteve NASM 2.16.01 e
  Strawberry Perl 5.32.1.1 para compilar OpenSSL; não acompanham o runtime.
- `provenance.json` contém URLs oficiais e hashes dos arquivos SQLCipher e
  sqlcipher3. O hash do sdist do binding foi confrontado com os metadados do PyPI.
- `openssl_graph.json` registra receita, revisões, opções e dependências
  efetivamente resolvidas pelo Conan. Os logs de cada etapa foram conservados.

## Repetir as etapas

Os comandos são de desenvolvimento; não são necessários para instalar ou rodar
a build pronta. A partir da raiz do projeto, baixe as duas fontes das URLs de
`provenance.json`, confira os hashes e extraia nas pastas de nome correspondente
sob `auditoria/native_build`. Faça isso somente com esses arquivos conhecidos.

No Developer Command Prompt x64 do Visual Studio, entre na pasta SQLCipher e rode:

```bat
cd /d "C:\Software Gestor\CODIGO\estoque_cosmeticos\auditoria\native_build\sqlcipher-4.18.0"
for %I in (.) do cd /d "%~sI"
nmake /f Makefile.msc sqlite3.c
```

Use caminho sem espaços ou nome curto 8.3: o gerador Jim e algumas ferramentas
falharam com caminhos contendo espaços. O Makefile gera a amalgamation e headers;
não se usa a amalgamation SQLite antiga que acompanhava o sdist do binding.
Confira `SQLITE_VERSION` em `sqlite3.c`: deve ser `3.53.4`.

No PowerShell da raiz do projeto, prepare o Conan em uma pasta dedicada e gere
OpenSSL. Em outra máquina, ajuste os caminhos e regenere o grafo; ele contém
caminhos locais e não deve ser reutilizado cegamente.

```powershell
$env:CONAN_HOME = (cmd /c 'for %I in ("auditoria\native_build\conan_cache") do @echo %~sI').Trim()
.\.venv\Scripts\conan.exe profile detect --force
.\.venv\Scripts\conan.exe remote update conancenter --url=https://center2.conan.io
.\.venv\Scripts\conan.exe install --requires=openssl/3.5.9 -s build_type=Release `
  -o 'openssl/*:shared=False' -o 'openssl/*:no_zlib=True' `
  -o 'openssl/*:no_fips=True' -o 'openssl/*:no_autoload_config=True' `
  -o 'openssl/*:no_apps=True' --build=missing `
  --output-folder=auditoria/native_build/openssl --format=json > auditoria/native_build/openssl_graph.json
```

A pasta de cache precisa existir antes de resolver seu nome curto. Caso nomes
curtos não estejam disponíveis, escolha outro caminho dedicado sem espaços.
Para reproduzir exatamente as receitas, confira as revisões do grafo preservado;
Conan remoto pode oferecer revisões diferentes no futuro. Não se afirma reprodução
bit a bit: timestamps, compiladores e empacotamento podem mudar o hash da wheel.

Execute `auditoria\native_build\compilar_wheel.cmd`. Ele configura o MSVC e chama
`compilar_sqlcipher.py`, que lê o setup original do sdist, aplica as opções
descritas abaixo e gera a wheel em `vendor`. O script não lê bancos da loja.

Opções específicas: `SQLITE_TEMP_STORE=3`, `SQLITE_OMIT_LOAD_EXTENSION=1`,
`SQLITE_DEFAULT_DEFENSIVE=1`, `SQLITE_TRUSTED_SCHEMA=0`,
`SQLITE_MAX_VARIABLE_NUMBER=10000`, `SQLITE_THREADSAFE=1` e os hooks/codec SQLCipher.
Foram retiradas as opções de FTS3/4/5, RTree, Soundex e carregamento de extensões.
Remover a flag legada JSON1 não remove necessariamente JSON do SQLite moderno.
`/MANIFEST:NO` é usado apenas no link da extensão Python `.pyd`; o executável
PyInstaller segue seu próprio empacotamento/manifesto.

Após recompilar, confira versões/opções, execute todos os testes de segurança e
atualize o SHA-256 em `requirements.lock` **somente após revisar o novo artefato**.
Não substitua esta wheel pela versão pública antiga sem essa avaliação.
As consultas em `../motor_criptografico.json` documentam o motor validado.

Logs: `amalgamation.log`, `openssl_build.log`, `wheel_build.log`.
Licenças redistribuídas em `../../licencas`.
