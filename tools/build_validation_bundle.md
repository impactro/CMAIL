# Bundle de homologação

Executar build_validation_bundle.py --output <temp-autorizado> a partir de
qualquer diretório na máquina DEV. Usa somente uma lista fechada de fixtures/
probes/roteiro do repositório; não percorre instâncias nem importa runtime.
ZIP novo usa criação exclusiva para não substituir evidência anterior.
Manifesto registra SHA256 de cada arquivo; hash final sai no stdout.
Não executa testes ou conexão real. Contrato: docs/validation/README.md.
