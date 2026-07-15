"""
Radar Eleitoral IA - ETL offline da Câmara Municipal de São Paulo (CMSP).

As votações e a presença da CMSP vivem em centenas de arquivos XML (um por
data de sessão). Baixar tudo ao vivo, a cada consulta, é o que trava o app.
Este script baixa esses XMLs UMA vez e gera arquivos compactos que o app lê
instantaneamente:

    data/processed/cmsp_votacoes.csv.gz    (voto a voto, por ano)
    data/processed/cmsp_presencas.csv.gz   (pré-agregado: por ano × vereador)

Uso (rode periodicamente; commite os arquivos gerados para o app publicado):

    .\\.venv\\Scripts\\python.exe scripts\\etl_cmsp.py                 # anos padrão
    .\\.venv\\Scripts\\python.exe scripts\\etl_cmsp.py --anos 2025 2026

O app funciona mesmo sem o ETL (cai no modo ao vivo), mas fica lento. Com os
compactos, cada consulta de vereador abre em milissegundos.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from collectors.camara_sp_collector import (
    baixar_gastos_ano,
    baixar_votacoes_ano,
    buscar_presencas_ano,
)

OUT_DIR = BASE_DIR / "data" / "processed"
SAIDA_VOTACOES = OUT_DIR / "cmsp_votacoes.csv.gz"
SAIDA_PRESENCAS = OUT_DIR / "cmsp_presencas.csv.gz"
SAIDA_GASTOS = OUT_DIR / "cmsp_gastos.csv.gz"

# Legislatura atual da CMSP começou em 2025; incluímos 2024 por segurança.
ANOS_PADRAO = list(range(2024, date.today().year + 1))


def _etl_votacoes(anos: list) -> pd.DataFrame:
    partes = []
    for ano in anos:
        print(f"[CMSP] Baixando votações de {ano}...")
        df = baixar_votacoes_ano(ano)
        if not df.empty:
            df["ano"] = ano
            partes.append(df)
            print(f"[CMSP]   {len(df)} votos, {df['data'].nunique()} sessões.")
    if not partes:
        return pd.DataFrame()
    return pd.concat(partes, ignore_index=True)


def _etl_presencas(anos: list) -> pd.DataFrame:
    """Pré-agrega a presença: uma linha por (ano, vereador) com presenças e
    o total de sessões do ano (denormalizado para leitura simples)."""
    linhas = []
    for ano in anos:
        print(f"[CMSP] Baixando presença de {ano}...")
        df = buscar_presencas_ano(ano)
        if df.empty:
            continue
        total_sessoes = df.drop_duplicates(["data", "sessao"]).shape[0]
        por_vereador = (
            df.assign(presente=df["presenca"].str.strip().str.lower().eq("presente"))
            .groupby("vereador")
            .agg(presencas=("presente", "sum"), partido=("partido", "last"))
            .reset_index()
        )
        por_vereador["ano"] = ano
        por_vereador["total_sessoes"] = total_sessoes
        linhas.append(por_vereador)
        print(f"[CMSP]   {len(por_vereador)} vereadores, {total_sessoes} sessões.")
    if not linhas:
        return pd.DataFrame()
    return pd.concat(linhas, ignore_index=True)


def _etl_gastos(anos: list) -> pd.DataFrame:
    partes = []
    for ano in anos:
        print(f"[CMSP] Baixando gastos de gabinete de {ano}...")
        df = baixar_gastos_ano(ano)
        if not df.empty:
            df["ANO"] = ano
            # mantém só as colunas úteis para reduzir o arquivo
            cols = [c for c in ["ANO", "MES", "VEREADOR", "DESPESA", "FORNECEDOR",
                                "CNPJ", "VALOR"] if c in df.columns]
            partes.append(df[cols])
            print(f"[CMSP]   {len(df)} despesas.")
    if not partes:
        return pd.DataFrame()
    return pd.concat(partes, ignore_index=True)


def executar(anos: list) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    df_vot = _etl_votacoes(anos)
    if not df_vot.empty:
        df_vot.to_csv(SAIDA_VOTACOES, index=False, compression="gzip")
        print(f"[CMSP] OK: {len(df_vot)} votos -> {SAIDA_VOTACOES} "
              f"({SAIDA_VOTACOES.stat().st_size/1024:.0f} KB)")

    df_pres = _etl_presencas(anos)
    if not df_pres.empty:
        df_pres.to_csv(SAIDA_PRESENCAS, index=False, compression="gzip")
        print(f"[CMSP] OK: {len(df_pres)} linhas de presença -> {SAIDA_PRESENCAS} "
              f"({SAIDA_PRESENCAS.stat().st_size/1024:.0f} KB)")

    df_gastos = _etl_gastos(anos)
    if not df_gastos.empty:
        df_gastos.to_csv(SAIDA_GASTOS, index=False, compression="gzip")
        print(f"[CMSP] OK: {len(df_gastos)} despesas -> {SAIDA_GASTOS} "
              f"({SAIDA_GASTOS.stat().st_size/1024:.0f} KB)")

    print("[CMSP] Lembre-se de commitar data/processed (git add data/processed).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ETL de votações e presença da CMSP.")
    parser.add_argument("--anos", nargs="+", type=int, default=ANOS_PADRAO,
                        help="Anos a processar (padrão: 2024 até o ano atual).")
    args = parser.parse_args()
    executar(args.anos)
