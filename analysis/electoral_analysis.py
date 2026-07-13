"""
Radar Eleitoral IA - Análise eleitoral.

Gera análises por candidato, município, ano e partido a partir dos
dados de votação já salvos no banco. Separa cálculo (DataFrames) de
texto estratégico (strings), para facilitar testes e reuso por outros
módulos (ex: PDF, plano de comunicação).
"""

import pandas as pd

from database.db_utils import buscar_candidato, buscar_votacao_por_candidato


def gerar_linha_do_tempo(candidato_id: int) -> pd.DataFrame:
    """Retorna a evolução do candidato ano a ano: votos totais, situação e crescimento."""
    votacoes = buscar_votacao_por_candidato(candidato_id)
    if not votacoes:
        return pd.DataFrame(columns=["ano", "cargo", "partido", "votos_totais", "situacao", "crescimento_pct"])

    df = pd.DataFrame(votacoes)
    candidato = buscar_candidato(candidato_id) or {}

    resumo = (
        df.groupby("ano")
        .agg(votos_totais=("votos", "sum"), cargo=("cargo", "first"), partido=("partido", "first"))
        .reset_index()
        .sort_values("ano")
    )
    resumo["situacao"] = candidato.get("situacao", "")
    resumo["crescimento_pct"] = resumo["votos_totais"].pct_change().round(4) * 100
    resumo["crescimento_pct"] = resumo["crescimento_pct"].fillna(0.0)
    return resumo


def calcular_evolucao_municipal(candidato_id: int, ano_inicial: int, ano_final: int) -> pd.DataFrame:
    """Compara votos por município entre dois anos e classifica a tendência."""
    votacoes = buscar_votacao_por_candidato(candidato_id, ano_inicial=ano_inicial, ano_final=ano_final)
    if not votacoes:
        return pd.DataFrame(columns=[
            "municipio", "votos_ano_inicial", "votos_ano_final",
            "variacao_absoluta", "variacao_percentual", "classificacao",
        ])

    df = pd.DataFrame(votacoes)

    df_inicio = df[df["ano"] == ano_inicial].groupby("municipio")["votos"].sum().rename("votos_ano_inicial")
    df_fim = df[df["ano"] == ano_final].groupby("municipio")["votos"].sum().rename("votos_ano_final")

    comparacao = pd.concat([df_inicio, df_fim], axis=1).fillna(0).reset_index()
    comparacao["variacao_absoluta"] = comparacao["votos_ano_final"] - comparacao["votos_ano_inicial"]
    comparacao["variacao_percentual"] = comparacao.apply(
        lambda r: round((r["variacao_absoluta"] / r["votos_ano_inicial"]) * 100, 2)
        if r["votos_ano_inicial"] > 0 else (100.0 if r["votos_ano_final"] > 0 else 0.0),
        axis=1,
    )
    comparacao["classificacao"] = comparacao["variacao_percentual"].apply(_classificar_variacao)
    return comparacao.sort_values("variacao_percentual", ascending=False)


def _classificar_variacao(pct: float) -> str:
    if pct >= 30:
        return "crescimento forte"
    elif pct >= 5:
        return "crescimento moderado"
    elif pct > -5:
        return "estabilidade"
    elif pct > -30:
        return "queda moderada"
    return "queda forte"


def ranking_municipios_fortes(candidato_id: int, ano: int) -> pd.DataFrame:
    """Retorna os municípios com mais votos para o candidato em um determinado ano."""
    votacoes = buscar_votacao_por_candidato(candidato_id, ano_inicial=ano, ano_final=ano)
    if not votacoes:
        return pd.DataFrame(columns=["municipio", "votos"])
    df = pd.DataFrame(votacoes)
    return df.groupby("municipio")["votos"].sum().sort_values(ascending=False).reset_index()


def ranking_municipios_queda(candidato_id: int, ano_inicial: int, ano_final: int) -> pd.DataFrame:
    """Retorna os municípios com maior perda de votos entre dois anos."""
    evolucao = calcular_evolucao_municipal(candidato_id, ano_inicial, ano_final)
    return evolucao[evolucao["variacao_absoluta"] < 0].sort_values("variacao_absoluta")


def ranking_municipios_oportunidade(candidato_id: int, ano_final: int) -> pd.DataFrame:
    """Identifica municípios com potencial de comunicação: votação atual baixa
    em relação à média do próprio candidato, sinalizando espaço de crescimento.

    Nota: este é um indicador inicial simplificado para o MVP. A versão
    completa (com eleitorado total e desempenho de concorrentes) depende
    da integração com dados do TSE de eleitorado por município.
    """
    votacoes = buscar_votacao_por_candidato(candidato_id, ano_inicial=ano_final, ano_final=ano_final)
    if not votacoes:
        return pd.DataFrame(columns=["municipio", "votos", "abaixo_da_media"])

    df = pd.DataFrame(votacoes).groupby("municipio")["votos"].sum().reset_index()
    media = df["votos"].mean()
    df["abaixo_da_media"] = df["votos"] < media
    df["potencial_comunicacao"] = df["abaixo_da_media"].map({True: "oportunidade", False: "consolidado"})
    return df.sort_values("votos")


def comparar_com_partido(candidato_id: int, ano: int) -> dict:
    """Compara o desempenho do candidato com a média do partido na UF no mesmo ano.

    Nota: requer dados de outros candidatos do mesmo partido/UF/ano no banco.
    Em ambiente de MVP com poucos candidatos cadastrados, o resultado pode
    ficar limitado — documentado aqui para evolução futura.
    """
    candidato = buscar_candidato(candidato_id)
    if not candidato:
        return {"erro": "Candidato não encontrado."}

    from database.db_utils import listar_candidatos

    pares_partido = listar_candidatos(partido=candidato.get("sigla_partido"), uf=candidato.get("uf"), ano=ano)
    votos_candidato = sum(v["votos"] for v in buscar_votacao_por_candidato(candidato_id, ano, ano))

    votos_outros = []
    for outro in pares_partido:
        if outro["id"] == candidato_id:
            continue
        votos_outros.extend(v["votos"] for v in buscar_votacao_por_candidato(outro["id"], ano, ano))

    media_partido = sum(votos_outros) / len(votos_outros) if votos_outros else None

    return {
        "votos_candidato": votos_candidato,
        "media_outros_candidatos_partido": media_partido,
        "acima_da_media": (votos_candidato > media_partido) if media_partido is not None else None,
        "candidatos_comparados": len(pares_partido) - 1 if pares_partido else 0,
    }


def gerar_resumo_estrategico(candidato_id: int, periodo: tuple) -> str:
    """Gera um resumo textual com onde o candidato cresceu, perdeu, manteve força
    e onde há oportunidade — para uso direto no dashboard e no relatório PDF.
    """
    ano_inicial, ano_final = periodo
    candidato = buscar_candidato(candidato_id)
    if not candidato:
        return "Candidato não encontrado para gerar resumo estratégico."

    evolucao = calcular_evolucao_municipal(candidato_id, ano_inicial, ano_final)
    if evolucao.empty:
        return (
            f"Não há dados de votação suficientes para {candidato.get('nome_urna')} "
            f"no período de {ano_inicial} a {ano_final}."
        )

    crescimento = evolucao[evolucao["classificacao"].isin(["crescimento forte", "crescimento moderado"])]
    queda = evolucao[evolucao["classificacao"].isin(["queda forte", "queda moderada"])]
    estavel = evolucao[evolucao["classificacao"] == "estabilidade"]

    partes = [
        f"Resumo estratégico de {candidato.get('nome_urna')} ({candidato.get('cargo')}/"
        f"{candidato.get('uf')}) no período {ano_inicial}-{ano_final}:"
    ]

    if not crescimento.empty:
        top_crescimento = ", ".join(crescimento["municipio"].head(3))
        partes.append(f"Cresceu em {len(crescimento)} município(s), com destaque para {top_crescimento}.")

    if not queda.empty:
        top_queda = ", ".join(queda["municipio"].head(3))
        partes.append(f"Perdeu força em {len(queda)} município(s), com atenção especial para {top_queda}.")

    if not estavel.empty:
        partes.append(f"Manteve base estável em {len(estavel)} município(s).")

    oportunidade = ranking_municipios_oportunidade(candidato_id, ano_final)
    municipios_oportunidade = oportunidade[oportunidade["potencial_comunicacao"] == "oportunidade"]
    if not municipios_oportunidade.empty:
        top_oportunidade = ", ".join(municipios_oportunidade["municipio"].head(3))
        partes.append(f"Municípios com potencial de comunicação a priorizar: {top_oportunidade}.")

    return " ".join(partes)


if __name__ == "__main__":
    print("[TESTE] Linha do tempo:")
    print(gerar_linha_do_tempo(1))
    print("\n[TESTE] Evolução municipal 2016-2020:")
    print(calcular_evolucao_municipal(1, 2016, 2020))
    print("\n[TESTE] Resumo estratégico:")
    print(gerar_resumo_estrategico(1, (2016, 2020)))
