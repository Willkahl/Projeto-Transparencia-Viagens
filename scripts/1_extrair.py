# =========================================================================
# SPRINT 1 - IMPORTAÇÃO DOS DADOS
# Leitura da base de dados analisada com utilização do gdown, zipfile e logging, para verificar a estrutura do arquivo e as colunas disponíveis.
# =========================================================================


"""
1_extrair.py
FASE 1 - EXTRAÇÃO E CAMADA RAW

- Baixa o .zip do Google Drive (DRIVE_FILE_ID no config.py / .env).
- Extrai os 4 CSVs (separador ';', encoding latin-1).
- Lê cada CSV em blocos (chunks) e carrega, sem alterar o conteúdo, nas
  tabelas raw_* (TRUNCATE antes de carregar -> idempotente).
- Resiliente: cada etapa crítica é protegida por try/except e loga o erro
  sem derrubar o processo inteiro.

IMPORTANTE: os nomes das colunas abaixo (RAW_MAPEAMENTO) seguem o dicionário
de dados do Portal da Transparência e já foram conferidos diretamente contra
os 4 CSVs reais (viagens_2025_6meses.zip). Se o cabeçalho real do CSV vier
diferente no futuro, ajuste apenas o dicionário correspondente — o resto do
script não precisa mudar.

ESTRUTURA DE PASTAS: este script mora em scripts/, enquanto config.py e
banco.py ficam na raiz do projeto. As duas linhas abaixo adicionam a raiz
ao sys.path para que os imports funcionem independente de onde o script
for executado.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import zipfile
import logging

import pandas as pd
import gdown

from config import (
    PASTA_DADOS,
    DRIVE_FILE_ID,
    ARQUIVOS,
    CSV_SEPARADOR,
    CSV_ENCODING,
    TAMANHO_BLOCO,
)
from banco import conectar, executar, inserir_em_lote

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# Mapeamento: nome da coluna no CSV de origem -> nome da coluna na tabela Raw.
# Ajuste os nomes à esquerda caso o cabeçalho real do CSV seja diferente.
# Cabeçalhos conferidos diretamente nos 4 CSVs reais (viagens_2025_6meses.zip).
RAW_MAPEAMENTO = {
    "viagem": {
        "Identificador do processo de viagem": "id_viagem",
        "Número da Proposta (PCDP)": "num_proposta",
        "Situação": "situacao",
        "Viagem Urgente": "viagem_urgente",
        "Justificativa Urgência Viagem": "justificativa_urgencia",
        "Código do órgão superior": "cod_orgao_superior",
        "Nome do órgão superior": "nome_orgao_superior",
        "Código órgão solicitante": "cod_orgao_solicitante",
        "Nome órgão solicitante": "nome_orgao_solicitante",
        "CPF viajante": "cpf_viajante",
        "Nome": "nome_viajante",
        "Cargo": "cargo",
        "Função": "funcao",
        "Descrição Função": "descricao_funcao",
        "Período - Data de início": "data_inicio",
        "Período - Data de fim": "data_fim",
        "Destinos": "destinos",
        "Motivo": "motivo",
        "Valor diárias": "valor_diarias",
        "Valor passagens": "valor_passagens",
        "Valor devolução": "valor_devolucao",
        "Valor outros gastos": "valor_outros_gastos",
    },
    "passagem": {
        "Identificador do processo de viagem": "id_viagem",
        "Número da Proposta (PCDP)": "num_proposta",
        "Meio de transporte": "meio_transporte",
        "País - Origem ida": "pais_origem_ida",
        "UF - Origem ida": "uf_origem_ida",
        "Cidade - Origem ida": "cidade_origem_ida",
        "País - Destino ida": "pais_destino_ida",
        "UF - Destino ida": "uf_destino_ida",
        "Cidade - Destino ida": "cidade_destino_ida",
        "País - Origem volta": "pais_origem_volta",
        "UF - Origem volta": "uf_origem_volta",
        "Cidade - Origem volta": "cidade_origem_volta",
        "Pais - Destino volta": "pais_destino_volta",
        "UF - Destino volta": "uf_destino_volta",
        "Cidade - Destino volta": "cidade_destino_volta",
        "Valor da passagem": "valor_passagem",
        "Taxa de serviço": "taxa_servico",
        "Data da emissão/compra": "data_emissao",
        "Hora da emissão/compra": "hora_emissao",
    },
    "pagamento": {
        "Identificador do processo de viagem": "id_viagem",
        "Número da Proposta (PCDP)": "num_proposta",
        "Código do órgão superior": "cod_orgao_superior",
        "Nome do órgão superior": "nome_orgao_superior",
        "Codigo do órgão pagador": "cod_orgao_pagador",
        "Nome do órgao pagador": "nome_orgao_pagador",
        "Código da unidade gestora pagadora": "cod_ug_pagadora",
        "Nome da unidade gestora pagadora": "nome_ug_pagadora",
        "Tipo de pagamento": "tipo_pagamento",
        "Valor": "valor",
    },
    "trecho": {
        # Atenção: no CSV real este cabeçalho vem com um espaço à direita;
        # o script normaliza os nomes de coluna (strip) antes de mapear.
        "Identificador do processo de viagem": "id_viagem",
        "Número da Proposta (PCDP)": "num_proposta",
        "Sequência Trecho": "sequencia_trecho",
        "Origem - Data": "origem_data",
        "Origem - País": "origem_pais",
        "Origem - UF": "origem_uf",
        "Origem - Cidade": "origem_cidade",
        "Destino - Data": "destino_data",
        "Destino - País": "destino_pais",
        "Destino - UF": "destino_uf",
        "Destino - Cidade": "destino_cidade",
        "Meio de transporte": "meio_transporte",
        "Número Diárias": "numero_diarias",
        "Missao?": "missao",
    },
}

# Onde o .zip baixado do Drive vai ficar salvo (dentro de PASTA_DADOS)
ZIP_PATH = PASTA_DADOS / "viagens.zip"


def baixar_zip():
    """Baixa o .zip do Google Drive, se ainda não existir localmente."""
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    if ZIP_PATH.exists():
        log.info("Zip já presente em %s, pulando download.", ZIP_PATH)
        return
    if not DRIVE_FILE_ID:
        raise RuntimeError("DRIVE_FILE_ID não configurado no config.py/.env")
    url = f"https://drive.google.com/uc?id={DRIVE_FILE_ID}"
    log.info("Baixando zip do Google Drive...")
    gdown.download(url, str(ZIP_PATH), quiet=False)


def extrair_csvs():
    """Extrai os CSVs de dentro do zip para PASTA_DADOS."""
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        z.extractall(PASTA_DADOS)
    log.info("CSVs extraídos em %s", PASTA_DADOS)


def carregar_tabela_raw(conn, chave):
    """Lê o CSV correspondente em blocos e insere (sem transformar) na Raw."""
    info = ARQUIVOS[chave]
    caminho = PASTA_DADOS / info["csv"]
    tabela = info["tabela_raw"]
    mapeamento = RAW_MAPEAMENTO[chave]

    executar(conn, f"TRUNCATE TABLE {tabela};")  # idempotência

    total = 0
    try:
        for bloco in pd.read_csv(
            caminho,
            sep=CSV_SEPARADOR,
            encoding=CSV_ENCODING,      # Colunas separadas por ponto e vírgula, encoding latin-1
            dtype=str,                  # garante que todos os campos sejam lidos como string
            keep_default_na=False,      # evita que campos vazios sejam convertidos para NaN
            chunksize=TAMANHO_BLOCO,
        ):
            bloco.columns = bloco.columns.str.strip()  # remove espaços indevidos no cabeçalho
            faltantes = [c for c in mapeamento if c not in bloco.columns]
            if faltantes:
                log.warning(
                    "%s: colunas do CSV não encontradas (preenchidas com NULL): %s",
                    chave, faltantes,
                )
            bloco = bloco.reindex(columns=list(mapeamento.keys()))
            bloco = bloco.rename(columns=mapeamento)
            bloco = bloco.where(pd.notnull(bloco), None)

            colunas_destino = list(mapeamento.values())
            registros = [tuple(r) for r in bloco[colunas_destino].itertuples(index=False, name=None)]

            placeholders = ", ".join(["%s"] * len(colunas_destino))
            sql_insert = f"INSERT INTO {tabela} ({', '.join(colunas_destino)}) VALUES ({placeholders})"
            inserir_em_lote(conn, sql_insert, registros)
            total += len(registros)

        log.info("%s -> %s: %d registros carregados.", chave, tabela, total)
    except FileNotFoundError:
        log.error("Arquivo não encontrado: %s", caminho)
        raise
    except Exception as e:
        log.error("Falha ao carregar %s: %s", tabela, e)
        raise


def main():
    try:
        baixar_zip()
        extrair_csvs()
    except Exception as e:
        log.error("Erro na etapa de download/extração: %s", e)
        sys.exit(1)

    conn = None
    try:
        conn = conectar()
        for chave in ("viagem", "pagamento", "passagem", "trecho"):
            carregar_tabela_raw(conn, chave)
        log.info("Fase 1 concluída com sucesso.")
    except Exception as e:
        log.error("Erro na carga da camada Raw: %s", e)
        sys.exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
