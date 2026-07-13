"""
Radar Eleitoral IA - Fontes oficiais de dados (referência centralizada).

Este módulo reúne os links oficiais usados (ou a usar) pelo sistema,
organizados por categoria. Ele é uma referência de navegação/documentação
e configuração — os collectors (tse_collector.py, emendas_collector.py)
continuam sendo os responsáveis por de fato baixar e processar os dados.

Verificado em: 22/06/2026 (ver observações de cada categoria).
"""

OFFICIAL_SOURCES = {
    # ------------------------------------------------------------------
    # 1. Dados eleitorais oficiais — TSE
    # ------------------------------------------------------------------
    "tse": {
        "portal_dados_abertos": "https://dadosabertos.tse.jus.br/",
        "datasets": "https://dadosabertos.tse.jus.br/dataset/",
        "grupo_resultados": "https://dadosabertos.tse.jus.br/group/resultados",
        "resultados_eleicoes": "https://www.tse.jus.br/eleicoes/resultados-eleicoes",
        "resultados_2024": "https://dadosabertos.tse.jus.br/dataset/resultados-2024",
        "resultados_2022": "https://dadosabertos.tse.jus.br/dataset/resultados-2022",
        "candidatos_2024": "https://dadosabertos.tse.jus.br/dataset/candidatos-2024",
        "eleitorado_atual": "https://dadosabertos.tse.jus.br/dataset/eleitorado-atual",
        "estatisticas": "https://www.tse.jus.br/eleicoes/estatisticas",
        "divulgacandcontas": "https://divulgacandcontas.tse.jus.br/",
    },

    # ------------------------------------------------------------------
    # 2. Emendas parlamentares e verbas federais — Portal da Transparência
    #
    # IMPORTANTE: a API exige cadastro e chave de autenticação.
    # 1. Cadastre um e-mail em:
    #    https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email
    # 2. Você recebe um token por e-mail.
    # 3. Toda requisição precisa do header HTTP: "chave-api-dados: SEU_TOKEN"
    # Limite documentado: até 700 requisições/min entre 00h-06h (fora desse
    # horário o limite é mais restrito — confirme na documentação oficial).
    # ------------------------------------------------------------------
    "portal_transparencia": {
        "consulta_emendas": "https://portaldatransparencia.gov.br/emendas/consulta",
        "consulta_emendas_por_favorecido": "https://portaldatransparencia.gov.br/emendas/consulta-por-favorecido",
        "download_dados_emendas": "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares",
        "cadastrar_email_api": "https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email",
        "api_docs": "https://portaldatransparencia.gov.br/api-de-dados",
        "swagger": "https://api.portaldatransparencia.gov.br/",
        "endpoint_emendas": "https://api.portaldatransparencia.gov.br/api-de-dados/emendas",
        "endpoint_emendas_documentos": "https://api.portaldatransparencia.gov.br/api-de-dados/emendas/documentos/{codigo}",
        "_auth_necessaria": True,
        "_auth_header": "chave-api-dados",
    },

    # ------------------------------------------------------------------
    # 3. Orçamento público, SIAFI e execução orçamentária
    # ------------------------------------------------------------------
    "orcamento": {
        "siga_brasil_senado": "https://www12.senado.leg.br/orcamento/sigabrasil",
        "camara_execucao_orcamentaria": "https://www2.camara.leg.br/ig-orcamento/",
        "dados_abertos_camara": "https://dadosabertos.camara.leg.br/",
        "swagger_camara": "https://dadosabertos.camara.leg.br/swagger/api.html",
    },

    # ------------------------------------------------------------------
    # 4. Transferências, convênios e obras
    # ------------------------------------------------------------------
    "transferegov": {
        "portal": "https://www.gov.br/transferegov/",
        "transferencias_especiais": "https://especiais.transferegov.sistema.gov.br/",
        "sobre_transferencias_especiais": "https://www.gov.br/transferegov/pt-br/sobre/transferencias-especiais",
    },

    # ------------------------------------------------------------------
    # 5. Municípios, mapas e dados territoriais — IBGE
    # ------------------------------------------------------------------
    "ibge": {
        "api_docs": "https://servicodados.ibge.gov.br/api/docs/",
        "malhas_territoriais": "https://www.ibge.gov.br/geociencias/organizacao-do-territorio/malhas-territoriais.html",
        "localidades": "https://www.ibge.gov.br/geociencias/organizacao-do-territorio/estrutura-territorial/27385-localidades.html",
        "areas_municipios": "https://www.ibge.gov.br/geociencias/organizacao-do-territorio/estrutura-territorial/15761-areas-dos-municipios.html",
        "populacao": "https://www.ibge.gov.br/estatisticas/sociais/populacao.html",
    },

    # ------------------------------------------------------------------
    # 6. Legislação e compliance eleitoral (uso de IA em propaganda)
    #
    # Confirmado: a Resolução TSE nº 23.755/2026 (de 2/3/2026) altera a
    # Resolução nº 23.610/2019 e estabelece, entre outras regras:
    #  - rotulagem obrigatória de conteúdo sintético/gerado por IA usado
    #    em propaganda eleitoral (texto, áudio, vídeo, imagem);
    #  - proibição de publicar/republicar/impulsionar conteúdo sintético
    #    com imagem/voz/manifestação de candidato nas 72h antes e 24h
    #    depois de cada turno da votação;
    #  - proibição de sistemas de IA ranquearem, recomendarem candidatos
    #    ou indicarem preferência/voto, direta ou indiretamente;
    #  - multa de R$ 5 mil a R$ 30 mil por peça em caso de descumprimento
    #    (art. 57-D da Lei 9.504/97), além de possível cassação de
    #    registro/mandato em casos de abuso de poder político.
    # ------------------------------------------------------------------
    "compliance_tse": {
        "resolucao_23755_2026": "https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-755-de-2-de-marco-de-2026",
        "resolucao_23760_2026": "https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-760-de-2-de-marco-de-2026",
        "regras_ia_2026_explicacao": "https://www.tse.jus.br/comunicacao/noticias/2026/Abril/por-dentro-das-eleicoes-conheca-as-regras-sobre-uso-de-ia-na-campanha-eleitoral-de-2026",
        "resolucoes_2026_geral": "https://www.tse.jus.br/comunicacao/noticias/2026/Marco/eleicoes-2026-tse-publica-todas-as-resolucoes-que-orientarao-o-pleito",
    },
}


def get(categoria: str, chave: str = None):
    """Acessa uma fonte oficial por categoria (e opcionalmente por chave).

    Exemplos:
        get("tse")                          -> dict completo da categoria
        get("tse", "resultados_2024")        -> URL específica
    """
    bloco = OFFICIAL_SOURCES.get(categoria)
    if bloco is None:
        raise KeyError(f"Categoria '{categoria}' não encontrada em OFFICIAL_SOURCES.")
    if chave is None:
        return bloco
    return bloco.get(chave)


if __name__ == "__main__":
    import json
    print(json.dumps(OFFICIAL_SOURCES, indent=2, ensure_ascii=False))
