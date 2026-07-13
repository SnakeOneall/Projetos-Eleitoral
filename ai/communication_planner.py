"""
Radar Eleitoral IA - Gerador de plano de comunicação.

Gera planejamento estratégico de comunicação (30/60/90 dias) com base
nas análises eleitoral e de esforço x resultado, para REVISÃO HUMANA
pela equipe de marketing/comunicação da campanha.

Regras de segurança/compliance aplicadas neste módulo:
- Não sugere fake news.
- Não sugere ataque pessoal.
- Não sugere disparo em massa irregular.
- Não sugere pedido explícito de voto antes do período permitido.
- Não sugere impulsionamento negativo.
- Não usa dados pessoais sensíveis.
- Usa linguagem de prestação de contas, escuta pública e divulgação
  institucional.

Este módulo NÃO automatiza disparos nem publicações. Ele apenas gera
texto de planejamento para a equipe humana revisar e executar.
"""

from compliance.electoral_compliance import AVISO_JURIDICO, gerar_checklist_compliance

TEMAS_PADRAO = [
    "prestação de contas", "saúde", "educação", "infraestrutura", "segurança",
    "geração de emprego", "escuta da população", "agenda regional", "propostas futuras",
]

FORMATOS_CONTEUDO = [
    "reels", "carrossel", "vídeo curto", "live", "artigo", "card", "stories",
    "imprensa local", "reunião presencial", "newsletter", "WhatsApp informativo com consentimento",
]

CANAIS_PADRAO = [
    "Instagram", "Facebook", "TikTok", "YouTube", "WhatsApp informativo com opt-in",
    "agenda presencial", "imprensa local",
]


def sugerir_temas_por_municipio(municipio: str, dados: dict) -> list:
    """Sugere temas prioritários de comunicação para um município, com base na
    classificação de esforço x resultado e nas áreas de emenda já identificadas.
    """
    classificacao = (dados or {}).get("classificacao", "")
    areas_emenda = (dados or {}).get("areas_atendidas", {}) or {}

    temas = []

    if "Alto esforço / Baixo resultado" in classificacao:
        temas.append("prestação de contas")
        temas.append("escuta da população")
    elif "Baixo esforço / Alto resultado" in classificacao:
        temas.append("agenda regional")
        temas.append("propostas futuras")
    elif "Alto esforço / Alto resultado" in classificacao:
        temas.append("prestação de contas")
    else:
        temas.append("escuta da população")
        temas.append("propostas futuras")

    for area in areas_emenda.keys():
        area_lower = str(area).lower()
        if "sa" in area_lower:  # saúde
            temas.append("saúde")
        elif "educ" in area_lower:
            temas.append("educação")
        elif "infra" in area_lower:
            temas.append("infraestrutura")
        elif "seguran" in area_lower:
            temas.append("segurança")

    # Remove duplicados preservando ordem, limita a temas conhecidos
    vistos = set()
    resultado = []
    for tema in temas:
        if tema not in vistos and tema in TEMAS_PADRAO:
            vistos.add(tema)
            resultado.append(tema)

    return resultado or ["escuta da população"]


def sugerir_formatos_conteudo() -> list:
    """Retorna a lista de formatos de conteúdo disponíveis para o plano editorial."""
    return list(FORMATOS_CONTEUDO)


def gerar_plano_30_60_90(candidato: dict, analise_eleitoral: dict, analise_esforco_resultado: dict) -> dict:
    """Gera o plano de comunicação estruturado em 30/60/90 dias.

    `analise_eleitoral` e `analise_esforco_resultado` são dicts simplificados
    (ex: {"municipios_oportunidade": [...], "municipios_atencao": [...]})
    produzidos a partir dos módulos de análise.
    """
    municipios_atencao = (analise_esforco_resultado or {}).get("municipios_atencao", [])
    municipios_oportunidade = (analise_eleitoral or {}).get("municipios_oportunidade", [])

    publicos_regionais = list(dict.fromkeys(municipios_atencao + municipios_oportunidade)) or ["base geral"]

    plano = {
        "objetivo_geral": (
            f"Fortalecer a presença institucional de {candidato.get('nome_urna', 'candidato')} "
            f"por meio de prestação de contas, escuta pública e divulgação de propostas, "
            f"priorizando os municípios com maior necessidade de reforço de comunicação."
        ),
        "publicos_regionais": publicos_regionais,
        "temas_prioritarios": TEMAS_PADRAO[:5],
        "canais_recomendados": CANAIS_PADRAO,
        "plano_30_dias": (
            "Semanas 1-4: publicar conteúdo de prestação de contas sobre ações já realizadas "
            "nos municípios prioritários; iniciar agenda de escuta pública presencial; "
            "produzir cards e reels com linguagem institucional, sem disparos em massa."
        ),
        "plano_60_dias": (
            "Semanas 5-8: ampliar divulgação de propostas futuras com base nos temas levantados "
            "na escuta pública; reforçar presença em imprensa local; iniciar newsletter "
            "informativa institucional para contatos com consentimento."
        ),
        "plano_90_dias": (
            "Semanas 9-12: consolidar agenda regional com lives e reuniões presenciais; "
            "publicar relatório de prestação de contas consolidado do período; avaliar "
            "indicadores de engajamento e ajustar prioridades para o próximo ciclo."
        ),
    }

    checklist = gerar_checklist_compliance(plano)
    plano["compliance_checklist"] = checklist
    plano["risco_eleitoral"] = checklist["classificacao_geral"]
    plano["aviso_juridico"] = AVISO_JURIDICO

    return plano


def gerar_calendario_editorial_30_dias(temas: list = None) -> list:
    """Gera um calendário editorial semanal para os primeiros 30 dias."""
    temas = temas or TEMAS_PADRAO[:4]
    formatos = sugerir_formatos_conteudo()
    calendario = []

    for semana in range(1, 5):
        tema = temas[(semana - 1) % len(temas)]
        formato = formatos[(semana - 1) % len(formatos)]
        canal = CANAIS_PADRAO[(semana - 1) % len(CANAIS_PADRAO)]
        calendario.append({
            "semana": semana,
            "tema": tema,
            "formato": formato,
            "canal": canal,
            "objetivo": f"Reforçar percepção institucional sobre o tema '{tema}'.",
            "observacao_compliance": (
                "Conteúdo institucional/informativo. Evitar pedido explícito de voto "
                "fora do período permitido e verificar fonte de qualquer dado citado."
            ),
        })

    return calendario


def gerar_resumo_para_agencia(candidato: dict, plano: dict) -> str:
    """Gera um texto executivo resumido para a equipe/agência de marketing entender
    rapidamente onde atuar.
    """
    publicos = ", ".join(plano.get("publicos_regionais", [])[:5]) or "a definir"
    temas = ", ".join(plano.get("temas_prioritarios", [])[:5])
    risco = plano.get("risco_eleitoral", "não avaliado")

    return (
        f"Resumo executivo — {candidato.get('nome_urna', 'Candidato')} ({candidato.get('cargo', '')}/"
        f"{candidato.get('uf', '')}):\n"
        f"Públicos regionais prioritários: {publicos}.\n"
        f"Temas de comunicação recomendados: {temas}.\n"
        f"Classificação de risco de compliance do plano: {risco}.\n"
        f"Recomenda-se revisão jurídica antes de qualquer publicação, especialmente em "
        f"períodos próximos à eleição. {plano.get('compliance_checklist', {}).get('aviso', '')}"
    )


if __name__ == "__main__":
    candidato_teste = {"nome_urna": "Zé Pereira", "cargo": "Vereador", "uf": "SP"}
    analise_eleitoral_teste = {"municipios_oportunidade": ["Diadema", "Santo André"]}
    analise_esforco_teste = {"municipios_atencao": ["Guarulhos"]}

    plano = gerar_plano_30_60_90(candidato_teste, analise_eleitoral_teste, analise_esforco_teste)
    print("[TESTE] Plano de comunicação:")
    for k, v in plano.items():
        print(f"  {k}: {v}")

    print("\n[TESTE] Calendário editorial:")
    for item in gerar_calendario_editorial_30_dias():
        print(f"  {item}")

    print("\n[TESTE] Resumo para agência:")
    print(gerar_resumo_para_agencia(candidato_teste, plano))
