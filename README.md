# Projeto Transparência - Viagens a Serviço

Pipeline de dados sobre viagens a serviço de órgãos públicos federais, com base
nos dados abertos do [Portal da Transparência](https://portaldatransparencia.gov.br/).
O projeto segue a arquitetura Medallion (**Raw → Silver → Gold**), com carga em
PostgreSQL e análise final em notebook Jupyter.

## Arquitetura

```
CSV (Portal da Transparência)
        │
        ▼
   camada RAW        →  cópia fiel dos CSVs, sem tratamento
        │
        ▼
   camada SILVER      →  dados tipados, limpos e com integridade referencial
        │
        ▼
   camada GOLD        →  agregações prontas para análise de negócio
```

## Estrutura de pastas

```
Projeto_Transparencia/
├── .env                  # credenciais reais (NÃO versionado)
├── .env.example           # modelo de variáveis de ambiente
├── .gitignore
├── config.py               # configurações e leitura do .env
├── banco.py                 # funções de acesso ao PostgreSQL
├── requirements.txt
├── README.md
├── data/                    # CSVs e .zip baixados (NÃO versionado)
├── sql/
│   └── 0_criar_banco.sql     # cria o database e as tabelas raw_*/silver_*
└── scripts/
    ├── 1_extrair.py            # Fase 1: baixa e carrega a camada Raw
    ├── 2_transformar.py         # Fase 2: transforma Raw -> Silver
    └── 3_analise.ipynb           # Fase 3: camada Gold + perguntas de negócio
```

## Pré-requisitos

- Python 3.10+
- PostgreSQL instalado e rodando localmente
- Uma conta com acesso ao arquivo `.zip` de dados no Google Drive

## Setup

**1. Clone o repositório e instale as dependências**
```bash
git clone https://github.com/Willkahl/Projeto-Transparencia-Viagens.git
cd Projeto-Transparencia-Viagens
pip install -r requirements.txt
```

**2. Configure o `.env`**

Copie o modelo e preencha com seus dados reais:
```bash
cp .env.example .env
```
Edite o `.env` com as credenciais do seu PostgreSQL local e o ID do arquivo no
Google Drive (a parte final do link de compartilhamento, em
`.../file/d/ESTE_TRECHO_E_O_ID/view`):
```dotenv
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=sua_senha
POSTGRES_DATABASE=transparencia
```
O `DRIVE_FILE_ID` e o restante das configurações (nomes de arquivo, separador
do CSV, tamanho do bloco de leitura) ficam centralizados em `config.py`.

**3. Crie o banco e as tabelas**

Rode o script `sql/0_criar_banco.sql` no seu cliente PostgreSQL preferido
(psql, DBeaver, pgAdmin etc.), conectado inicialmente no banco padrão
`postgres`. O script cria o database `transparencia` e todas as tabelas das
camadas Raw e Silver.

## Como rodar o pipeline

Execute os scripts a partir da **raiz do projeto**, na ordem:

```bash
python scripts/1_extrair.py
python scripts/2_transformar.py
```

- **`1_extrair.py`** baixa o `.zip` do Google Drive (se ainda não estiver em
  `data/`), extrai os 4 CSVs e carrega o conteúdo, sem transformação, nas
  tabelas `raw_*`.
- **`2_transformar.py`** lê as tabelas `raw_*`, converte os tipos (texto →
  `DECIMAL`/`DATE`), calcula colunas derivadas (`valor_total`,
  `duracao_dias`) e carrega as tabelas `silver_*`, respeitando a integridade
  referencial.

Ambos os scripts são **idempotentes**: podem ser executados novamente sem
duplicar dados (fazem `TRUNCATE` das tabelas de destino antes de carregar).

**Camada Gold e perguntas de negócio**

Abra `scripts/3_analise.ipynb` no Jupyter (a partir da pasta `scripts/`, para
que os imports funcionem corretamente) e execute as células em ordem. O
notebook:
- responde 6 perguntas de negócio com SQL + tabela + gráfico;
- cria a tabela agregada `gold_gastos_orgao` e a view `vw_gold_gastos_orgao`
  (gastos por órgão pagador).

## Dados

Os CSVs de origem (`2025_Viagem.csv`, `2025_Passagem.csv`,
`2025_Pagamento.csv`, `2025_Trecho.csv`) usam separador `;` e encoding
`latin-1`, seguindo o padrão do Portal da Transparência. Eles ficam em
`data/`, pasta ignorada pelo Git por conter arquivos grandes e por poderem
ser regerados a qualquer momento a partir do `1_extrair.py`.

## Fluxo de desenvolvimento

O projeto foi desenvolvido em sprints, cada uma em sua própria branch,
integrada à `main` via Pull Request:

| Sprint | Entrega |
|---|---|
| Sprint 0 | Setup do projeto (`.gitignore`, `.env.example`, `config.py`, `banco.py`) |
| Sprint 1 | Camada Bronze/Raw (`0_criar_banco.sql`, `1_extrair.py`) |
| Sprint 2 | Camada Silver (`2_transformar.py`) |
| Sprint 3 | Camada Gold e análise de negócio (`3_analise.ipynb`) |
