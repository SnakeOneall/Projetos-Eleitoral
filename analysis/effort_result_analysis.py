"""
Radar Eleitoral IA - Análise de esforço versus resultado.

Cruza a evolução de votos do candidato por município com o volume de
emendas/verbas públicas destinado a esses municípios, para identificar
onde houve retorno territorial e onde houve investimento sem retorno
eleitoral aparente.

Linguagem institucional obrigatória (evitar termos sensíveis como
"compra de voto"): usar "retorno territorial", "reconhecimento
regional", "percepção pública", "eficiência de comunicação",
"atuação parlamentar".
"""

import pandas as pd

from analysis.electoral_analysis import calcular_evolucao_municipal
from collectors.emendas_collector import buscar_emendas_por_parlamentar
from database.db_utils import buscar_candidato


def calcular_esforco_resultado(candidato_id: int, ano_inicial: int, ano_final: int) -> pd.DataFrame:
    """Para cada município, cruza variação de votos com valor público destinado
    e classifica em uma das 4 categorias da matriz esforço x resultado.
    """
    candidato = buscar_candidato(candidato_id)
    if not candidato:
        return pd.DataFrame()

    evolucao = calcular_evolucao_municipal(candidato_id, ano_inicial, ano_final)
    if evolucao.empty:
        return pd.DataFrame()

    emendas = buscar_emendas_por_parlamentar(
        candidato.get("nome_urna") or candidato.get("nome_civil"),
        uf=candidato.get("uf"),
        ano_inicial=ano_inicial,
        ano_final=ano_final,
    )
    df_emendas = pd.DataFrame(emendas)

    if df_emendas.empty:
        valor_por_municipio = pd.DataFrame(columns=["municipio", "valor_total_destinado", "valor_total_pago"])
    else:
        valor_por_municipio = (
            df_emendas.groupby("municipio_beneficiado")
            .agg(valor_total_destinado=("valor_empenhado", "sum"), valor_total_pago=("valor_pago", "sum"))
            .reset_index()
            .rename(columns={"municipio_beneficiado": "municipio"})
        )

    matriz = evolucao.merge(valor_por_municipio, on="municipio", how="left")
    matriz["valor_total_destinado"] = matriz["valor_total_destinado"].fillna(0.0)
    matriz["valor_total_pago"] = matriz["valor_total_pago"].fillna(0.0)

    mediana_esforco = matriz["valor_total_destinado"].median()
    mediana_resultado = matriz["variacao_percentual"].median()

    matriz["indice_retorno_territorial"] = matriz.apply(
        lambda r: round(r["variacao_percentual"] / r["valor_total_destinado"] * 1_000_000, 4)
        if r["valor_total_destinado"] > 0 else None,
        axis=1,
    )

    matriz["classificacao"] = matriz.apply(
        lambda r: _classificar_esforco_resultado(r, mediana_esforco, mediana_resultado), axis=1
    )
    matriz["leitura_ia"] = matriz.apply(gerar_leitura_municipio, axis=1)

    colunas_finais = [
        "municipio", "votos_ano_inicial", "votos_ano_final", "variacao_absoluta",
        "variacao_percentual", "valor_total_destinado", "valor_total_pago",
        "indice_retorno_territorial", "classificacao", "leitura_ia",
    ]
    return matriz[colunas_finais].sort_values("variacao_percentual", ascending=False)


def _classificar_esforco_resultado(row, mediana_esforco: float, mediana_resultado: float) -> str:
    alto_esforco = row["valor_total_destinado"] >= mediana_esforco and row["valor_total_destinado"] > 0
    alto_resultado = row["variacao_percentual"] >= mediana_resultado

    if alto_esforco and alto_resultado:
        return "Alto esforço / Alto resultado"
    elif alto_esforco and not alto_resultado:
        return "Alto esforço / Baixo resultado"
    elif not alto_esforco and alto_resultado:
        return "Baixo esforço / Alto resultado"
    return "Baixo esforço / Baixo resultado"


def gerar_leitura_municipio(row) -> str:
    """Gera um texto curto explicando a leitura do município, em linguagem institucional."""
    municipio = row["municipio"]
    classificacao = row.get("classificacao") or _classificar_esforco_resultado(row, row["valor_total_destinado"], row["variacao_percentual"])
    variacao = row["variacao_percentual"]

    if classificacao == "Alto esforço / Alto resultado":
        return (
            f"{municipio}: atuação parlamentar consistente, com retorno territorial "
            f"acompanhando o investimento ({variacao:.1f}% de variação)."
        )
    elif classificacao == "Alto esforço / Baixo resultado":
        return (
            f"{municipio}: investimento público relevante, mas percepção pública ainda não "
            f"reflete proporcionalmente nos votos ({variacao:.1f}%). Pode indicar oportunidade "
            f"de reforço de comunicação institucional sobre as ações já realizadas."
        )
    elif classificacao == "Baixo esforço / Alto resultado":
        return (
            f"{municipio}: bom reconhecimento regional mesmo com baixo investimento direto "
            f"identificado ({variacao:.1f}%). Município de eficiência de comunicação."
        )
    return (
        f"{municipio}: baixo investimento identificado e variação de {variacao:.1f}%. "
        f"Candidato a entrar no planejamento de atuação parlamentar futura."
    )


def gerar_ranking_eficiencia(candidato_id: int) -> pd.DataFrame:
    """Ranqueia municípios pela melhor relação entre esforço público e evolução eleitoral.

    Usa o último período de 2 eleições disponível automaticamente (ver chamadores
    no dashboard, que informam ano_inicial/ano_final explícitos).
    """
    from database.db_utils import buscar_votacao_por_candidato

    votacoes = buscar_votacao_por_candidato(candidato_id)
    if not votacoes:
        return pd.DataFrame()

    anos = sorted({v["ano"] for v in votacoes})
    if len(anos) < 2:
        return pd.DataFrame()

    matriz = calcular_esforco_resultado(candidato_id, anos[0], anos[-1])
    if matriz.empty:
        return matriz

    return matriz[matriz["indice_retorno_territorial"].notna()].sort_values(
        "indice_retorno_territorial", ascending=False
    )


def gerar_alertas(candidato_id: int) -> dict:
    """Aponta municípios que merecem atenção especial no planejamento."""
    from database.db_utils import buscar_votacao_por_candidato

    votacoes = buscar_votacao_por_candidato(candidato_id)
    if not votacoes:
        return {}

    anos = sorted({v["ano"] for v in votacoes})
    if len(anos) < 2:
        return {}

    matriz = calcular_esforco_resultado(candidato_id, anos[0], anos[-1])
    if matriz.empty:
        return {}

    return {
        "alto_esforco_queda": matriz[
            (matriz["classificacao"] == "Alto esforço / Baixo resultado") & (matriz["variacao_absoluta"] < 0)
        ]["municipio"].tolist(),
        "baixo_esforco_crescimento_forte": matriz[
            (matriz["classificacao"] == "Baixo esforço / Alto resultado") & (matriz["variacao_percentual"] >= 30)
        ]["municipio"].tolist(),
        "alto_valor_baixa_percepcao": matriz[
            (matriz["valor_total_pago"] > matriz["valor_total_pago"].median())
            & (matriz["classificacao"] == "Alto esforço / Baixo resultado")
        ]["municipio"].tolist(),
        "prioridade_comunicacao": matriz[
            matriz["classificacao"].isin(["Alto esforço / Baixo resultado", "Baixo esforço / Baixo resultado"])
        ]["municipio"].tolist(),
    }


def salvar_analise_no_banco(candidato_id: int, ano_inicial: int, ano_final: int) -> int:
    """Persiste a matriz de esforço x resultado na tabela analise_esforco_resultado."""
    from database.init_db import get_connection

    matriz = calcular_esforco_resultado(candidato_id, ano_inicial, ano_final)
    if matriz.empty:
        return 0

    candidato = buscar_candidato(candidato_id) or {}
    conn = get_connection()
    cur = conn.cursor()
    inseridos = 0
    for _, row in matriz.iterrows():
        cur.execute(
            """INSERT INTO analise_esforco_resultado
               (candidato_id, municipio, uf, periodo_inicio, periodo_fim, votos_inicio,
                votos_fim, variacao_votos, percentual_variacao, valor_total_destinado,
                valor_total_pago, classificacao, leitura_ia)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                candidato_id, row["municipio"], candidato.get("uf"), ano_inicial, ano_final,
                int(row["votos_ano_inicial"]), int(row["votos_ano_final"]), int(row["variacao_absoluta"]),
                float(row["variacao_percentual"]), float(row["valor_total_destinado"]),
                float(row["valor_total_pago"]), row["classificacao"], row["leitura_ia"],
            ),
        )
        inseridos += 1
    conn.commit()
    conn.close()
    return inseridos


if __name__ == "__main__":
    print("[TESTE] Matriz esforço x resultado (2016-2020):")
    print(calcular_esforco_resultado(1, 2016, 2020))
    print("\n[TESTE] Alertas:")
    print(gerar_alertas(1))
