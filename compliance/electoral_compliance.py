"""
Radar Eleitoral IA - Compliance eleitoral.

Validador de risco para textos, planos e sugestões de comunicação,
ANTES de qualquer revisão humana/jurídica. Este módulo é uma camada de
alerta, não um parecer jurídico.

IMPORTANTE:
Este módulo não substitui análise jurídica especializada. Toda saída
deve ser revisada por um responsável humano (advogado eleitoral ou
equipe de compliance da campanha) antes de qualquer uso público.
"""

import re
from datetime import datetime, timedelta

AVISO_JURIDICO = "Este relatório não substitui análise jurídica especializada."

# Resolução TSE nº 23.755, de 2 de março de 2026 (altera a Resolução nº
# 23.610/2019) — regras sobre propaganda eleitoral e uso de IA, vigentes
# para as Eleições Gerais de 2026. Pontos centrais usados neste módulo:
#  - rotulagem obrigatória de conteúdo sintético/gerado por IA usado em
#    propaganda eleitoral (texto, áudio, vídeo, imagem);
#  - vedação de publicar/republicar/impulsionar conteúdo sintético com
#    imagem/voz/manifestação de candidato nas 72h antes e 24h depois de
#    cada turno da votação ("janela de restrição");
#  - sistemas de IA não podem ranquear, recomendar candidatos ou indicar
#    preferência/voto, direta ou indiretamente.
# Fonte: https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-755-de-2-de-marco-de-2026
RESOLUCAO_TSE_REFERENCIA = "Resolução TSE nº 23.755/2026 (altera a Resolução nº 23.610/2019)"
JANELA_RESTRICAO_HORAS_ANTES = 72
JANELA_RESTRICAO_HORAS_DEPOIS = 24

# Termos que indicam pedido explícito de voto (Lei 9.504/97 trata o tema;
# o uso/momento permitido varia por contexto e período eleitoral — daí o
# alerta, não um bloqueio automático).
TERMOS_PEDIDO_VOTO = [
    r"\bvote em mim\b", r"\bvote no candidato\b", r"\bvote para mim\b",
    r"\bconfirme nas urnas\b", r"\bescolha nas urnas\b", r"\beleja\b",
    r"\bme eleja\b", r"\bvote\s+\d{2,5}\b", r"\bpe[çc]o seu voto\b",
    r"\bconte com (meu|nosso) (n[uú]mero|voto)\b",
]

# Padrões de linguagem ofensiva/acusatória sem indicação de fonte.
TERMOS_ATAQUE_PESSOAL = [
    r"\bcorrupto\b", r"\bladr[ãa]o\b", r"\bbandido\b", r"\bmentiroso\b",
    r"\bcriminoso\b", r"\bcorrupta\b", r"\bvagabundo\b",
]

# Padrões associados a impulsionamento com foco em prejudicar adversário.
TERMOS_IMPULSIONAMENTO_NEGATIVO = [
    r"\bdesmascarar\b", r"\bexpor\s+o\s+advers[áa]rio\b", r"\bderrubar\s+a\s+imagem\b",
    r"\bataque\s+ao\s+oponente\b", r"\bcampanha\s+negativa\b", r"\bdestruir\s+a\s+reputa[çc][ãa]o\b",
]

# Sinaliza afirmações com números/fatos fortes sem indicação de fonte.
PADRAO_NUMERO_SEM_FONTE = re.compile(r"\b\d{1,3}([.,]\d{3})*\s*(%|por cento|mil|milh[õo]es)\b", re.IGNORECASE)
PADRAO_FONTE_CITADA = re.compile(r"\b(fonte|segundo|conforme|de acordo com)\b", re.IGNORECASE)

TERMOS_PROMESSA_EXAGERADA = [
    r"\bgaranto\b", r"\bprometo\s+resolver\b", r"\bvou\s+acabar\s+com\b",
    r"\b100%\s+de\s+certeza\b", r"\bsem\s+d[uú]vida\s+vou\s+resolver\b",
]


def _contem_padrao(texto: str, padroes: list) -> list:
    """Retorna os padrões (compilados como regex) encontrados no texto."""
    texto_lower = texto.lower()
    encontrados = []
    for padrao in padroes:
        if re.search(padrao, texto_lower):
            encontrados.append(padrao)
    return encontrados


def detectar_pedido_explicito_voto(texto: str) -> bool:
    """Identifica se o texto contém pedido explícito de voto."""
    return len(_contem_padrao(texto, TERMOS_PEDIDO_VOTO)) > 0


def detectar_ataque_pessoal(texto: str) -> bool:
    """Identifica linguagem ofensiva ou acusatória sem indicação de fonte."""
    tem_ataque = len(_contem_padrao(texto, TERMOS_ATAQUE_PESSOAL)) > 0
    tem_fonte = bool(PADRAO_FONTE_CITADA.search(texto.lower()))
    # Se há linguagem ofensiva E nenhuma fonte citada, o risco é maior.
    return tem_ataque and not tem_fonte


def detectar_impulsionamento_negativo(texto: str) -> bool:
    """Identifica conteúdo com foco aparente em prejudicar adversário."""
    return len(_contem_padrao(texto, TERMOS_IMPULSIONAMENTO_NEGATIVO)) > 0


def detectar_desinformacao_potencial(texto: str) -> bool:
    """Marca risco quando há números/fatos fortes citados sem indicação de fonte."""
    tem_numero_forte = bool(PADRAO_NUMERO_SEM_FONTE.search(texto))
    tem_fonte = bool(PADRAO_FONTE_CITADA.search(texto.lower()))
    tem_promessa = len(_contem_padrao(texto, TERMOS_PROMESSA_EXAGERADA)) > 0
    return (tem_numero_forte and not tem_fonte) or tem_promessa


def detectar_uso_ia(texto: str) -> bool:
    """Sinaliza quando o texto foi (ou pode ter sido) gerado/alterado por IA,
    para que a equipe avalie a necessidade de rotulagem explícita, conforme
    a Resolução TSE nº 23.755/2026 — toda peça de propaganda eleitoral criada
    ou significativamente alterada por IA deve informar isso de modo claro
    e acessível.

    Nota: este módulo gera planejamento (sempre identificável como gerado
    com apoio de IA), então esta função tipicamente retorna True para
    qualquer conteúdo produzido pelo Radar Eleitoral IA.
    """
    marcadores = [r"\bgerado por ia\b", r"\bassistente de ia\b", r"\bintelig[êe]ncia artificial\b"]
    return True if _contem_padrao(texto, marcadores) else True  # conteúdo do sistema é sempre IA-assistido


def detectar_janela_restricao_ia(data_publicacao: datetime, data_eleicao: datetime) -> bool:
    """Verifica se uma publicação de conteúdo sintético/gerado por IA contendo
    imagem, voz ou manifestação de candidato cairia na janela de restrição da
    Resolução TSE nº 23.755/2026: vedada nas 72h antes e 24h depois de cada
    turno da votação.

    Retorna True se a data de publicação estiver dentro da janela vedada
    (ou seja, se HOUVER risco de violar a regra).
    """
    inicio_janela = data_eleicao - timedelta(hours=JANELA_RESTRICAO_HORAS_ANTES)
    fim_janela = data_eleicao + timedelta(hours=JANELA_RESTRICAO_HORAS_DEPOIS)
    return inicio_janela <= data_publicacao <= fim_janela


def avaliar_risco_texto(texto: str) -> str:
    """Classifica o risco eleitoral geral de um texto: baixo, médio ou alto."""
    if not texto or not texto.strip():
        return "baixo risco"

    sinalizadores = [
        detectar_pedido_explicito_voto(texto),
        detectar_ataque_pessoal(texto),
        detectar_impulsionamento_negativo(texto),
        detectar_desinformacao_potencial(texto),
    ]
    total = sum(sinalizadores)

    if total == 0:
        return "baixo risco"
    elif total == 1:
        return "médio risco"
    return "alto risco"


def gerar_checklist_compliance(plano_comunicacao: dict, data_publicacao: datetime = None, data_eleicao: datetime = None) -> dict:
    """Gera um checklist de compliance para um plano de comunicação (dict com
    chaves como 'objetivo', 'plano_30_dias', 'plano_60_dias', 'plano_90_dias', etc.).

    Se `data_publicacao` e `data_eleicao` forem informadas, também verifica
    se a publicação cairia na janela de restrição de conteúdo sintético/IA
    da Resolução TSE nº 23.755/2026 (72h antes / 24h depois da votação).
    """
    texto_completo = " ".join(
        str(v) for v in plano_comunicacao.values() if isinstance(v, str)
    )

    risco = avaliar_risco_texto(texto_completo)
    checklist = {
        "existe_pedido_explicito_de_voto": detectar_pedido_explicito_voto(texto_completo),
        "existe_ataque_pessoal": detectar_ataque_pessoal(texto_completo),
        "existe_promessa_exagerada": len(_contem_padrao(texto_completo, TERMOS_PROMESSA_EXAGERADA)) > 0,
        "existem_dados_sem_fonte": detectar_desinformacao_potencial(texto_completo),
        "existe_risco_de_impulsionamento_irregular": detectar_impulsionamento_negativo(texto_completo),
        "existe_uso_de_ia_que_precisa_ser_identificado": detectar_uso_ia(texto_completo),
        "classificacao_geral": risco,
        "recomenda_revisao_juridica": risco in ("médio risco", "alto risco"),
        "referencia_normativa": RESOLUCAO_TSE_REFERENCIA,
        "aviso": AVISO_JURIDICO,
    }

    if data_publicacao and data_eleicao:
        dentro_da_janela = detectar_janela_restricao_ia(data_publicacao, data_eleicao)
        checklist["dentro_da_janela_de_restricao_ia"] = dentro_da_janela
        if dentro_da_janela:
            checklist["classificacao_geral"] = "alto risco"
            checklist["recomenda_revisao_juridica"] = True

    return checklist


def gerar_observacoes_seguras(texto: str) -> str:
    """Reescreve recomendações de comunicação em linguagem institucional mais segura.

    Esta função não tenta "burlar" alertas de compliance — ela sugere um
    enquadramento institucional para temas legítimos (prestação de contas,
    transparência, escuta pública), mantendo os alertas de risco intactos
    para revisão humana.
    """
    substituicoes = {
        r"\bvote em mim\b": "conheça nossa atuação e propostas",
        r"\bvote no candidato\b": "conheça o trabalho do candidato",
        r"\bgaranto\b": "trabalho para",
        r"\bvou acabar com\b": "atuo para reduzir",
        r"\bdesmascarar\b": "apresentar dados públicos sobre",
    }

    resultado = texto
    for padrao, substituto in substituicoes.items():
        resultado = re.sub(padrao, substituto, resultado, flags=re.IGNORECASE)

    sugestao_enquadramento = (
        " Recomenda-se enquadrar o conteúdo como prestação de contas, "
        "transparência, escuta pública ou divulgação institucional de propostas."
    )
    return resultado.strip() + sugestao_enquadramento


if __name__ == "__main__":
    exemplos = [
        "Realizamos uma reunião de escuta pública sobre saúde no bairro Jardim Exemplo.",
        "Vote em mim, número 45123! Garanto que vou acabar com todos os problemas da cidade!",
        "O adversário é corrupto e vamos desmascarar ele nas redes sociais.",
    ]
    for texto in exemplos:
        print(f"\nTexto: {texto}")
        print(f"Risco: {avaliar_risco_texto(texto)}")
        print(f"Versão segura: {gerar_observacoes_seguras(texto)}")

    print("\n[TESTE] Janela de restrição de IA (eleição em 04/10/2026):")
    data_eleicao = datetime(2026, 10, 4, 17, 0)
    publicacao_arriscada = datetime(2026, 10, 3, 10, 0)  # ~31h antes -> dentro da janela de 72h
    publicacao_segura = datetime(2026, 9, 1, 10, 0)
    print(f"  Publicação em {publicacao_arriscada}: dentro da janela? {detectar_janela_restricao_ia(publicacao_arriscada, data_eleicao)}")
    print(f"  Publicação em {publicacao_segura}: dentro da janela? {detectar_janela_restricao_ia(publicacao_segura, data_eleicao)}")
