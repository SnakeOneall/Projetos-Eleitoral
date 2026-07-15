"""
Radar Eleitoral IA - ETL da gestão pública da Prefeitura de São Paulo.

A base de Execução Orçamentária é grande (todas as dotações do município).
Este script baixa uma vez e gera agregados compactos que o app lê instantâneo:

    data/processed/pmsp_execucao_funcao.csv.gz   (por área: Saúde, Educação...)
    data/processed/pmsp_execucao_orgao.csv.gz    (por órgão/secretaria)
    data/processed/pmsp_execucao_emendas.csv.gz  (dotações vinculadas a emenda)

Uso (rode periodicamente; commite os arquivos gerados):

    .\\.venv\\Scripts\\python.exe scripts\\etl_prefeitura.py
    .\\.venv\\Scripts\\python.exe scripts\\etl_prefeitura.py --anos 2025 2026
"""

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from collectors.prefeitura_sp_collector import (
    baixar_execucao,
    dotacoes_por_emenda,
    resumo_por_funcao,
    resumo_por_orgao,
)

OUT_DIR = BASE_DIR / "data" / "processed"
SAIDA_FUNCAO = OUT_DIR / "pmsp_execucao_funcao.csv.gz"
SAIDA_ORGAO = OUT_DIR / "pmsp_execucao_orgao.csv.gz"
SAIDA_EMENDAS = OUT_DIR / "pmsp_execucao_emendas.csv.gz"

# Esquema moderno (função/órgão/valores) existe a partir de 2020 (XLSX/CSV).
# Anos anteriores usam layout antigo (mensal) e são ignorados pelo coletor.
ANOS_PADRAO = list(range(2020, date.today().year + 1))


def executar(anos: list) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p_funcao, p_orgao, p_emendas = [], [], []

    for ano in anos:
        df = baixar_execucao(ano)
        if df.empty:
            continue
        for saida, func in ((p_funcao, resumo_por_funcao),
                            (p_orgao, resumo_por_orgao),
                            (p_emendas, dotacoes_por_emenda)):
            agg = func(df)
            if not agg.empty:
                agg["ano"] = ano
                saida.append(agg)
        print(f"[PMSP] {ano}: orçado atualizado R$ {df['orcado_atualizado'].sum():,.0f} | "
              f"pago R$ {df['pago'].sum():,.0f}")

    def _salvar(partes, caminho, rotulo):
        if partes:
            pd.concat(partes, ignore_index=True).to_csv(caminho, index=False, compression="gzip")
            print(f"[PMSP] OK: {rotulo} -> {caminho} ({caminho.stat().st_size/1024:.0f} KB)")

    _salvar(p_funcao, SAIDA_FUNCAO, "por função")
    _salvar(p_orgao, SAIDA_ORGAO, "por órgão")
    _salvar(p_emendas, SAIDA_EMENDAS, "por emenda")
    print("[PMSP] Lembre-se de commitar data/processed (git add data/processed).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ETL da execução orçamentária da PMSP.")
    parser.add_argument("--anos", nargs="+", type=int, default=ANOS_PADRAO)
    args = parser.parse_args()
    executar(args.anos)
