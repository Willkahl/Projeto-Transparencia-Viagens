# =========================================================================
# SPRINT 2 - TRANSFORMAÇÃO DOS DADOS
# Transformação da base de dados analisada para preparação da camada Silver.
# =========================================================================


"""
2_transformar.py
FASE 2 - TRANSFORMAÇÃO E CAMADA SILVER

Copia Raw -> Silver convertendo os tipos (texto -> DECIMAL e DATE),
respeitando a integridade referencial (viagem antes de passagem/pagamento/
trecho) e calculando as colunas derivadas valor_total e duracao_dias.

Idempotente: faz TRUNCATE das tabelas Silver (na ordem que respeita as FKs)
antes de recarregar. Resiliente: try/except em cada etapa.

ESTRUTURA DE PASTAS: este script mora em scripts/, enquanto config.py e
banco.py ficam na raiz do projeto. As duas linhas abaixo adicionam a raiz
ao sys.path para que os imports funcionem independente de onde o script
for executado.

IMPORTANTE: depende da função consultar() em banco.py. Se ainda não existir
no seu banco.py, adicione:

    def consultar(conexao, sql, parametros=None):
        cursor = conexao.cursor()
        cursor.execute(sql, parametros or ())
        linhas = cursor.fetchall()
        cursor.close()
        return linhas
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import logging
from datetime import datetime

from banco import conectar, executar, inserir_em_lote, consultar

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def para_decimal(valor_txt):
    """Converte texto no padrão brasileiro ('1272,97') para float. None se vazio/invalido."""
    if valor_txt is None:
        return None
    txt = str(valor_txt).strip()
    if txt == "" or txt.lower() in ("nan", "none"):
        return None
    txt = txt.replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return None


def para_data(data_txt):
    """Converte texto 'DD/MM/AAAA' para date. None se vazio/inválido."""
    if data_txt is None:
        return None
    txt = str(data_txt).strip()
    if txt == "" or txt.lower() in ("nan", "none"):
        return None
    try:
        return datetime.strptime(txt, "%d/%m/%Y").date()
    except ValueError:
        return None


def para_int(valor_txt):
    if valor_txt is None:
        return None
    txt = str(valor_txt).strip()
    if txt == "" or txt.lower() in ("nan", "none"):
        return None
    try:
        return int(float(txt.replace(",", ".")))
    except ValueError:
        return None


def inserir_tabela(conn, tabela, colunas, registros):
    """
    Monta o INSERT (com %s por coluna) e delega para inserir_em_lote do banco.py,
    que espera (conexao, sql_insert, linhas). Retorna a quantidade inserida.
    """
    if not registros:
        return 0
    placeholders = ", ".join(["%s"] * len(colunas))
    sql_insert = f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({placeholders})"
    inserir_em_lote(conn, sql_insert, registros)
    return len(registros)


def truncar_silver(conn):
    """
    Trunca as 4 tabelas Silver em um único comando. O PostgreSQL exige que
    tabelas com FK entre si sejam truncadas juntas (ou com CASCADE).
    """
    executar(conn, "TRUNCATE TABLE silver_passagem, silver_pagamento, silver_trecho, silver_viagem;")


def transformar_viagem(conn):
    linhas = consultar(
        conn,
        """
        SELECT id_viagem, num_proposta, situacao, viagem_urgente,
               cod_orgao_superior, nome_orgao_superior, nome_viajante, cargo,
               data_inicio, data_fim, destinos, motivo,
               valor_diarias, valor_passagens, valor_devolucao, valor_outros_gastos
        FROM raw_viagem
        WHERE id_viagem IS NOT NULL
        """,
    )

    registros = []
    for row in linhas:
        (id_viagem, num_proposta, situacao, viagem_urgente, cod_orgao_superior,
         nome_orgao_superior, nome_viajante, cargo, data_inicio_txt, data_fim_txt,
         destinos, motivo, valor_diarias_txt, valor_passagens_txt,
         valor_devolucao_txt, valor_outros_gastos_txt) = row

        if not nome_orgao_superior:
            # respeita a constraint NOT NULL da Silver: descarta registro inválido
            log.warning("Descartando viagem %s: nome_orgao_superior nulo.", id_viagem)
            continue

        data_inicio = para_data(data_inicio_txt)
        data_fim = para_data(data_fim_txt)

        valor_diarias = para_decimal(valor_diarias_txt) or 0
        valor_passagens = para_decimal(valor_passagens_txt) or 0
        valor_devolucao = para_decimal(valor_devolucao_txt) or 0
        valor_outros_gastos = para_decimal(valor_outros_gastos_txt) or 0

        valor_total = valor_diarias + valor_passagens + valor_outros_gastos - valor_devolucao
        duracao_dias = (data_fim - data_inicio).days if data_inicio and data_fim else None

        registros.append((
            id_viagem, num_proposta, situacao, viagem_urgente, cod_orgao_superior,
            nome_orgao_superior, nome_viajante, cargo, data_inicio, data_fim,
            destinos, motivo, valor_diarias, valor_passagens, valor_devolucao,
            valor_outros_gastos, valor_total, duracao_dias,
        ))

    colunas = [
        "id_viagem", "num_proposta", "situacao", "viagem_urgente", "cod_orgao_superior",
        "nome_orgao_superior", "nome_viajante", "cargo", "data_inicio", "data_fim",
        "destinos", "motivo", "valor_diarias", "valor_passagens", "valor_devolucao",
        "valor_outros_gastos", "valor_total", "duracao_dias",
    ]
    total = inserir_tabela(conn, "silver_viagem", colunas, registros)
    log.info("silver_viagem: %d registros.", total)
    return {r[0] for r in registros}  # ids válidos, para checar integridade referencial


def transformar_passagem(conn, ids_viagem_validos):
    linhas = consultar(
        conn,
        """
        SELECT id_viagem, meio_transporte, pais_origem_ida, uf_origem_ida,
               cidade_origem_ida, pais_destino_ida, uf_destino_ida, cidade_destino_ida,
               valor_passagem, taxa_servico, data_emissao
        FROM raw_passagem
        """,
    )
    registros = []
    for row in linhas:
        (id_viagem, meio_transporte, pais_o, uf_o, cid_o, pais_d, uf_d, cid_d,
         valor_passagem_txt, taxa_servico_txt, data_emissao_txt) = row
        if id_viagem not in ids_viagem_validos:
            continue
        valor_passagem = para_decimal(valor_passagem_txt) or 0
        taxa_servico = para_decimal(taxa_servico_txt) or 0
        registros.append((
            id_viagem, meio_transporte, pais_o, uf_o, cid_o, pais_d, uf_d, cid_d,
            valor_passagem, taxa_servico, para_data(data_emissao_txt),
        ))
    colunas = [
        "id_viagem", "meio_transporte", "pais_origem_ida", "uf_origem_ida",
        "cidade_origem_ida", "pais_destino_ida", "uf_destino_ida", "cidade_destino_ida",
        "valor_passagem", "taxa_servico", "data_emissao",
    ]
    total = inserir_tabela(conn, "silver_passagem", colunas, registros)
    log.info("silver_passagem: %d registros.", total)


def transformar_pagamento(conn, ids_viagem_validos):
    linhas = consultar(
        conn,
        """
        SELECT id_viagem, num_proposta, nome_orgao_pagador, nome_ug_pagadora,
               tipo_pagamento, valor
        FROM raw_pagamento
        """,
    )
    registros = []
    for row in linhas:
        id_viagem, num_proposta, nome_orgao_pagador, nome_ug_pagadora, tipo_pagamento, valor_txt = row
        if id_viagem not in ids_viagem_validos or not tipo_pagamento:
            continue
        valor = para_decimal(valor_txt) or 0
        registros.append((id_viagem, num_proposta, nome_orgao_pagador, nome_ug_pagadora, tipo_pagamento, valor))
    colunas = ["id_viagem", "num_proposta", "nome_orgao_pagador", "nome_ug_pagadora", "tipo_pagamento", "valor"]
    total = inserir_tabela(conn, "silver_pagamento", colunas, registros)
    log.info("silver_pagamento: %d registros.", total)


def transformar_trecho(conn, ids_viagem_validos):
    linhas = consultar(
        conn,
        """
        SELECT id_viagem, sequencia_trecho, origem_data, origem_uf, origem_cidade,
               destino_data, destino_uf, destino_cidade, meio_transporte, numero_diarias
        FROM raw_trecho
        """,
    )
    registros = []
    vistos = set()
    for row in linhas:
        (id_viagem, seq_txt, origem_data_txt, origem_uf, origem_cidade,
         destino_data_txt, destino_uf, destino_cidade, meio_transporte, num_diarias_txt) = row
        if id_viagem not in ids_viagem_validos:
            continue
        sequencia = para_int(seq_txt)
        chave = (id_viagem, sequencia)
        if chave in vistos:
            continue  # respeita a UNIQUE (id_viagem, sequencia_trecho)
        vistos.add(chave)

        registros.append((
            id_viagem, sequencia, para_data(origem_data_txt), origem_uf, origem_cidade,
            para_data(destino_data_txt), destino_uf, destino_cidade, meio_transporte,
            para_decimal(num_diarias_txt) or 0,
        ))
    colunas = [
        "id_viagem", "sequencia_trecho", "origem_data", "origem_uf", "origem_cidade",
        "destino_data", "destino_uf", "destino_cidade", "meio_transporte", "numero_diarias",
    ]
    total = inserir_tabela(conn, "silver_trecho", colunas, registros)
    log.info("silver_trecho: %d registros.", total)


def main():
    conn = None
    try:
        conn = conectar()
        truncar_silver(conn)
        ids_viagem_validos = transformar_viagem(conn)
        transformar_passagem(conn, ids_viagem_validos)
        transformar_pagamento(conn, ids_viagem_validos)
        transformar_trecho(conn, ids_viagem_validos)
        log.info("Fase 2 concluída com sucesso.")
    except Exception as e:
        log.error("Erro na transformação Raw -> Silver: %s", e)
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
