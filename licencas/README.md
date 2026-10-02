# Componentes criptográficos desta distribuição

A partir da versão 1.2.0, a pesquisa também utiliza RapidFuzz 3.14.6 (MIT).
Seu aviso está em `RapidFuzz-LICENSE.txt`; esse componente não realiza criptografia.

Esta distribuição utiliza SQLCipher Community 4.18.0 (inclui SQLite 3.53.4),
OpenSSL 3.5.9 LTS e o binding sqlcipher3 0.6.2.

O binding foi recompilado para GiStocker com versão local
`0.6.2+gistocker.sqlcipher418`: amalgamation SQLCipher atualizada, OpenSSL estático
e opções de compilação defensivas. Trata-se de uma versão modificada da
distribuição do binding, não de uma release publicada pelo seu autor.
Os algoritmos criptográficos são os dos projetos originais.

Os avisos e termos originais estão nos arquivos desta pasta. Fontes, hashes e
instruções de recompilação acompanham o código-fonte do GiStocker em
`auditoria/native_build/README_COMPILACAO.md`.
