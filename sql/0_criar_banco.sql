-- =============================================================================
-- FASE 0 - CRIAÇÃO DO BANCO E TABELAS
-- Pipeline de Dados: Viagens a Serviço (Portal da Transparência)
-- Arquitetura Medallion (Raw -> Silver -> Gold)
-- SGBD: PostgreSQL
-- =============================================================================

-- Rode este bloco separadamente (fora de uma transação) na conexão "postgres"
-- para criar o database. Depois conecte-se a ele (\c transparencia) e rode o restante do script.

CREATE DATABASE transparencia;
-- \c transparencia

-- =============================================================================
-- CAMADA RAW
-- Cópia fiel dos CSVs: todas as colunas em VARCHAR, sem constraints.
-- Replica o CSV inteiro, inclusive colunas que a Silver não usa.
-- =============================================================================

DROP TABLE IF EXISTS raw_pagamento;
DROP TABLE IF EXISTS raw_passagem;
DROP TABLE IF EXISTS raw_trecho;
DROP TABLE IF EXISTS raw_viagem;

-- Colunas e nomes conferidos diretamente nos CSVs reais (viagens_2025_6meses.zip)

CREATE TABLE raw_viagem (
    id_viagem               VARCHAR(20),
    num_proposta            VARCHAR(30),
    situacao                VARCHAR(50),
    viagem_urgente          VARCHAR(5),
    justificativa_urgencia  VARCHAR(4000),
    cod_orgao_superior      VARCHAR(20),
    nome_orgao_superior     VARCHAR(255),
    cod_orgao_solicitante   VARCHAR(20),
    nome_orgao_solicitante  VARCHAR(255),
    cpf_viajante            VARCHAR(20),
    nome_viajante           VARCHAR(255),
    cargo                   VARCHAR(255),
    funcao                  VARCHAR(255),
    descricao_funcao        VARCHAR(255),
    data_inicio             VARCHAR(20),
    data_fim                VARCHAR(20),
    destinos                VARCHAR(4000),
    motivo                  VARCHAR(4000),
    valor_diarias           VARCHAR(30),
    valor_passagens         VARCHAR(30),
    valor_devolucao         VARCHAR(30),
    valor_outros_gastos     VARCHAR(30)
);

CREATE TABLE raw_passagem (
    id_viagem            VARCHAR(20),
    num_proposta         VARCHAR(30),
    meio_transporte      VARCHAR(50),
    pais_origem_ida      VARCHAR(60),
    uf_origem_ida        VARCHAR(40),
    cidade_origem_ida    VARCHAR(80),
    pais_destino_ida     VARCHAR(60),
    uf_destino_ida       VARCHAR(40),
    cidade_destino_ida   VARCHAR(80),
    pais_origem_volta    VARCHAR(60),
    uf_origem_volta      VARCHAR(40),
    cidade_origem_volta  VARCHAR(80),
    pais_destino_volta   VARCHAR(60),
    uf_destino_volta     VARCHAR(40),
    cidade_destino_volta VARCHAR(80),
    valor_passagem       VARCHAR(30),
    taxa_servico         VARCHAR(30),
    data_emissao         VARCHAR(20),
    hora_emissao         VARCHAR(10)
);

CREATE TABLE raw_pagamento (
    id_viagem           VARCHAR(20),
    num_proposta        VARCHAR(30),
    cod_orgao_superior  VARCHAR(20),
    nome_orgao_superior VARCHAR(255),
    cod_orgao_pagador   VARCHAR(20),
    nome_orgao_pagador  VARCHAR(255),
    cod_ug_pagadora     VARCHAR(20),
    nome_ug_pagadora    VARCHAR(255),
    tipo_pagamento      VARCHAR(50),
    valor               VARCHAR(30)
);

CREATE TABLE raw_trecho (
    id_viagem        VARCHAR(20),
    num_proposta     VARCHAR(30),
    sequencia_trecho VARCHAR(10),
    origem_data      VARCHAR(20),
    origem_pais      VARCHAR(60),
    origem_uf        VARCHAR(40),
    origem_cidade    VARCHAR(80),
    destino_data     VARCHAR(20),
    destino_pais     VARCHAR(60),
    destino_uf       VARCHAR(40),
    destino_cidade   VARCHAR(80),
    meio_transporte  VARCHAR(50),
    numero_diarias   VARCHAR(30),
    missao           VARCHAR(5)
);

-- =============================================================================
-- CAMADA SILVER
-- Dados limpos e tipados, com PK, FK e 2 constraints extras por tabela
-- (NOT NULL, CHECK, UNIQUE), declaradas dentro do CREATE TABLE.
-- =============================================================================

DROP TABLE IF EXISTS silver_pagamento;
DROP TABLE IF EXISTS silver_passagem;
DROP TABLE IF EXISTS silver_trecho;
DROP TABLE IF EXISTS silver_viagem;

-- silver_viagem
-- Constraints extras: NOT NULL em nome_orgao_superior | CHECK em valor_diarias >= 0
CREATE TABLE silver_viagem (
    id_viagem           VARCHAR(20)     PRIMARY KEY,
    num_proposta         VARCHAR(20),
    situacao             VARCHAR(50),
    viagem_urgente       VARCHAR(5),
    cod_orgao_superior    VARCHAR(20),
    nome_orgao_superior   VARCHAR(255)    NOT NULL,
    nome_viajante        VARCHAR(255),
    cargo                VARCHAR(255),
    data_inicio          DATE,
    data_fim             DATE,
    destinos             VARCHAR(4000),
    motivo               VARCHAR(4000),
    valor_diarias        DECIMAL(10,2)   CHECK (valor_diarias >= 0),
    valor_passagens      DECIMAL(10,2),
    valor_devolucao      DECIMAL(10,2),
    valor_outros_gastos  DECIMAL(10,2),
    valor_total          DECIMAL(12,2),   -- calculado na Fase 2
    duracao_dias         INT              -- calculado na Fase 2
);

-- silver_passagem
-- Constraints extras: CHECK em valor_passagem >= 0 | CHECK em taxa_servico >= 0
CREATE TABLE silver_passagem (
    id_passagem        SERIAL          PRIMARY KEY,
    id_viagem           VARCHAR(20)     NOT NULL REFERENCES silver_viagem(id_viagem),
    meio_transporte     VARCHAR(50),
    pais_origem_ida     VARCHAR(60),
    uf_origem_ida       VARCHAR(40),
    cidade_origem_ida   VARCHAR(80),
    pais_destino_ida    VARCHAR(60),
    uf_destino_ida      VARCHAR(40),
    cidade_destino_ida  VARCHAR(80),
    valor_passagem      DECIMAL(10,2)   CHECK (valor_passagem >= 0),
    taxa_servico        DECIMAL(10,2)   CHECK (taxa_servico >= 0),
    data_emissao        DATE
);

-- silver_pagamento
-- Constraints extras: CHECK em valor >= 0 | NOT NULL em tipo_pagamento
CREATE TABLE silver_pagamento (
    id_pagamento       SERIAL          PRIMARY KEY,
    id_viagem           VARCHAR(20)     NOT NULL REFERENCES silver_viagem(id_viagem),
    num_proposta        VARCHAR(20),
    nome_orgao_pagador   VARCHAR(255),
    nome_ug_pagadora     VARCHAR(255),
    tipo_pagamento       VARCHAR(50)     NOT NULL,
    valor                DECIMAL(10,2)   CHECK (valor >= 0)
);

-- silver_trecho
-- Constraints extras: CHECK em numero_diarias >= 0 | UNIQUE (id_viagem, sequencia_trecho)
CREATE TABLE silver_trecho (
    id_trecho          SERIAL          PRIMARY KEY,
    id_viagem           VARCHAR(20)     NOT NULL REFERENCES silver_viagem(id_viagem),
    sequencia_trecho     INT,
    origem_data          DATE,
    origem_uf            VARCHAR(40),
    origem_cidade        VARCHAR(80),
    destino_data         DATE,
    destino_uf           VARCHAR(40),
    destino_cidade       VARCHAR(80),
    meio_transporte      VARCHAR(50),
    numero_diarias       DECIMAL(10,2)   CHECK (numero_diarias >= 0),
    UNIQUE (id_viagem, sequencia_trecho)
);

-- Índices auxiliares para acelerar os JOINs da camada Gold
CREATE INDEX idx_silver_passagem_viagem ON silver_passagem(id_viagem);
CREATE INDEX idx_silver_pagamento_viagem ON silver_pagamento(id_viagem);
CREATE INDEX idx_silver_trecho_viagem ON silver_trecho(id_viagem);
