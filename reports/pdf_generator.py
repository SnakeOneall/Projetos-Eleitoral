"""Gerador de relatório comercial em PDF do Radar Eleitoral IA."""

from __future__ import annotations

import html
import logging
import os
from datetime import datetime

import pandas as pd

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    REPORTLAB_AVAILABLE = True
except ModuleNotFoundError:
    colors = None
    TA_CENTER = 1
    A4 = None
    getSampleStyleSheet = None
    ParagraphStyle = None
    cm = 1
    PageBreak = Paragraph = SimpleDocTemplate = Spacer = Table = TableStyle = None
    REPORTLAB_AVAILABLE = False

from analysis.electoral_analysis import (
    gerar_linha_do_tempo,
    gerar_resumo_estrategico,
    ranking_municipios_fortes,
    ranking_municipios_oportunidade,
    ranking_municipios_queda,
)
from analysis.effort_result_analysis import calcular_esforco_resultado, gerar_alertas
from analysis.territorial_analysis import analisar_distribuicao_territorial
from analysis.territorial_rules import detectar_escopo_cargo
from ai.communication_planner import gerar_plano_30_60_90
from collectors.emendas_collector import gerar_resumo_emendas
from compliance.electoral_compliance import AVISO_JURIDICO, gerar_checklist_compliance
from database.db_utils import (
    buscar_candidato,
    buscar_votacao_por_candidato,
    buscar_votacao_secao_por_candidato,
    buscar_votacao_zona_por_candidato,
)


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

NAVY = "#0f2742"
BLUE = "#1f78ff"
GREEN = "#17a673"
RED = "#d64545"
ORANGE = "#f59e0b"
LIGHT = "#f5f7fb"
BORDER = "#d8e0ea"
TEXT = "#172033"

PROXIMO_PASSO_COMERCIAL = (
    "Transformar este diagnóstico em calendário editorial, peças criativas, "
    "gestão de redes sociais e acompanhamento mensal."
)


def _criar_logger_pdf() -> logging.Logger:
    logger_pdf = logging.getLogger("radar_eleitoral.pdf")
    if not logger_pdf.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[PDF] %(message)s"))
        logger_pdf.addHandler(handler)
    logger_pdf.setLevel(logging.INFO)
    logger_pdf.propagate = False
    return logger_pdf


logger = _criar_logger_pdf()


def _escape(texto) -> str:
    return html.escape(str(texto if texto is not None else ""))


def _fmt_int(valor) -> str:
    return f"{int(valor or 0):,}".replace(",", ".")


def _fmt_pct(valor) -> str:
    return f"{float(valor or 0):.1f}%".replace(".", ",")


def _fmt_brl(valor) -> str:
    return f"R$ {float(valor or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _estilos():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CoverTitle", fontSize=26, leading=32, textColor=colors.white, alignment=TA_CENTER, spaceAfter=10))
    styles.add(ParagraphStyle(name="CoverSubtitle", fontSize=14, leading=18, textColor=colors.white, alignment=TA_CENTER, spaceAfter=6))
    styles.add(ParagraphStyle(name="SectionTitle", fontSize=15, leading=19, textColor=colors.HexColor(NAVY), spaceBefore=8, spaceAfter=8))
    styles.add(ParagraphStyle(name="BodySmall", fontSize=8.5, leading=11, textColor=colors.HexColor(TEXT)))
    styles.add(ParagraphStyle(name="Badge", fontSize=9, leading=12, textColor=colors.white, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="KpiLabel", fontSize=7.5, leading=10, textColor=colors.HexColor("#5b6b7c"), alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="KpiValue", fontSize=12, leading=16, textColor=colors.HexColor(NAVY), alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="Warning", fontSize=9, leading=12, textColor=colors.HexColor(RED)))
    return styles


def _p(texto, style):
    return Paragraph(_escape(texto), style)


def _tabela_padrao(dados: list, cabecalho: list, col_widths: list | None = None) -> Table:
    styles = _estilos()
    linhas = [[_p(c, styles["BodySmall"]) for c in cabecalho]]
    for linha in dados:
        linhas.append([_p(c, styles["BodySmall"]) for c in linha])
    tabela = Table(linhas, repeatRows=1, colWidths=col_widths)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor(BORDER)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(LIGHT)]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return tabela


def _kpi_table(kpis: dict) -> Table:
    styles = _estilos()
    cells = []
    for label, value in [
        ("Votos totais", kpis["votos_totais"]),
        ("Crescimento", kpis["crescimento"]),
        ("Municípios fortes", kpis["municipios_fortes"]),
        ("Municípios em queda", kpis["municipios_queda"]),
        ("Emendas pagas", kpis["emendas_pagas"]),
        ("Retorno territorial", kpis["indice_retorno"]),
    ]:
        cells.append([
            _p(label, styles["KpiLabel"]),
            _p(value, styles["KpiValue"]),
        ])
    tabela = Table([cells[:3], cells[3:]], colWidths=[5.7 * cm, 5.7 * cm, 5.7 * cm])
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(BORDER)),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.HexColor(BORDER)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return tabela


def _pdf_literal(texto: str) -> bytes:
    raw = str(texto).encode("latin-1", errors="replace")
    raw = raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    return b"(" + raw + b")"


def _gerar_pdf_simples(caminho: str, linhas: list[str]) -> str:
    """Modo mínimo e válido quando ReportLab não está instalado."""
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    linhas_seguras = [str(linha)[:110] for linha in linhas if str(linha).strip()]
    stream = [b"BT", b"/F1 10 Tf", b"72 790 Td", b"13 TL"]
    for linha in linhas_seguras[:52]:
        stream.append(_pdf_literal(linha) + b" Tj")
        stream.append(b"T*")
    stream.append(b"ET")
    conteudo = b"\n".join(stream)

    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(conteudo)).encode("ascii") + b" >>\nstream\n" + conteudo + b"\nendstream",
    ]

    saida = [b"%PDF-1.4\n"]
    offsets = [0]
    for idx, obj in enumerate(objetos, start=1):
        offsets.append(sum(len(parte) for parte in saida))
        saida.append(f"{idx} 0 obj\n".encode("ascii"))
        saida.append(obj)
        saida.append(b"\nendobj\n")

    xref_offset = sum(len(parte) for parte in saida)
    saida.append(f"xref\n0 {len(objetos) + 1}\n".encode("ascii"))
    saida.append(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        saida.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    saida.append(
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )

    with open(caminho, "wb") as arquivo:
        arquivo.write(b"".join(saida))
    logger.info(f"PDF em modo mínimo gerado em: {caminho}")
    return caminho


def _calcular_kpis(candidato_id: int, periodo_inicio: int, periodo_fim: int, resumo_emendas: dict, matriz) -> dict:
    linha_tempo = gerar_linha_do_tempo(candidato_id)
    votos_totais = 0
    crescimento = 0.0
    if not linha_tempo.empty:
        votos_totais = linha_tempo["votos_totais"].iloc[-1]
        crescimento = linha_tempo["crescimento_pct"].iloc[-1] if "crescimento_pct" in linha_tempo.columns else 0.0

    fortes = ranking_municipios_fortes(candidato_id, periodo_fim)
    queda = ranking_municipios_queda(candidato_id, periodo_inicio, periodo_fim)
    indice = "N/D"
    if matriz is not None and not matriz.empty and "indice_retorno_territorial" in matriz.columns:
        serie = matriz["indice_retorno_territorial"].dropna()
        if not serie.empty:
            indice = f"{serie.median():.2f}"

    return {
        "votos_totais": _fmt_int(votos_totais),
        "crescimento": _fmt_pct(crescimento),
        "municipios_fortes": _fmt_int(len(fortes) if not fortes.empty else 0),
        "municipios_queda": _fmt_int(len(queda) if not queda.empty else 0),
        "emendas_pagas": _fmt_brl((resumo_emendas or {}).get("total_pago", 0)),
        "indice_retorno": indice,
    }


def _descobertas(resumo: str, alertas: dict, kpis: dict) -> list[str]:
    return [
        f"Votos totais consolidados no período: {kpis['votos_totais']}.",
        f"Crescimento eleitoral estimado: {kpis['crescimento']}.",
        f"Municípios fortes identificados: {kpis['municipios_fortes']}.",
        f"Municípios em queda ou atenção: {kpis['municipios_queda']}.",
        "Prioridades de comunicação: "
        + (", ".join((alertas or {}).get("prioridade_comunicacao", [])[:5]) or "nenhuma prioridade crítica identificada."),
        resumo,
    ]


def _preparar_distribuicao_territorial_pdf(candidato: dict, periodo_fim: int) -> dict:
    """Prepara a melhor distribuicao territorial para o PDF."""
    candidato_id = candidato["id"]
    secoes = pd.DataFrame(buscar_votacao_secao_por_candidato(candidato_id, int(periodo_fim)))
    if not secoes.empty:
        dados = secoes
    else:
        zonas = pd.DataFrame(buscar_votacao_zona_por_candidato(candidato_id, int(periodo_fim)))
        if not zonas.empty:
            dados = zonas
        else:
            dados = pd.DataFrame(buscar_votacao_por_candidato(candidato_id, ano_inicial=int(periodo_fim), ano_final=int(periodo_fim)))
    return analisar_distribuicao_territorial(
        dados,
        cargo=candidato.get("cargo"),
        municipio=(dados["municipio"].dropna().iloc[0] if not dados.empty and "municipio" in dados.columns and dados["municipio"].notna().any() else None),
        uf=candidato.get("uf"),
    )


def _linhas_tabela_territorial(resultado: dict, limite: int = 12) -> list[list[str]]:
    dados = resultado.get("dados")
    if dados is None or dados.empty:
        return []
    linhas = []
    for _, row in dados.head(limite).iterrows():
        linhas.append([
            row.get("ranking", ""),
            row.get("nivel", resultado.get("nivel", "")),
            row.get("chave_territorial", ""),
            row.get("municipio", ""),
            row.get("zona", ""),
            row.get("secao", ""),
            row.get("bairro", ""),
            _fmt_int(row.get("votos", 0)),
            _fmt_pct(row.get("percentual", 0)),
        ])
    return linhas


def gerar_pdf_relatorio(candidato_id: int, periodo_inicio: int, periodo_fim: int) -> str:
    """Gera o relatório estratégico em PDF e retorna o caminho do arquivo."""
    candidato = buscar_candidato(candidato_id)
    if not candidato:
        raise ValueError(f"Candidato {candidato_id} não encontrado.")

    fonte_eleitoral = candidato.get("fonte_dados") or "Dados de demonstração do MVP"
    origem_eleitoral = candidato.get("origem_dados") or "demo"
    badge_dados = "Dados reais" if origem_eleitoral == "real" else "Dados de demonstração"

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    nome_arquivo = f"relatorio_{candidato['nome_urna'].replace(' ', '_')}_{periodo_inicio}_{periodo_fim}.pdf"
    caminho = os.path.join(OUTPUT_DIR, nome_arquivo)

    resumo_estrategico = gerar_resumo_estrategico(candidato_id, (periodo_inicio, periodo_fim))
    alertas = gerar_alertas(candidato_id) or {}
    resumo_emendas = gerar_resumo_emendas(candidato_id) or {}
    matriz = calcular_esforco_resultado(candidato_id, periodo_inicio, periodo_fim)
    oportunidade = ranking_municipios_oportunidade(candidato_id, periodo_fim)
    municipios_oport_lista = (
        oportunidade[oportunidade["potencial_comunicacao"] == "oportunidade"]["municipio"].tolist()
        if not oportunidade.empty and "potencial_comunicacao" in oportunidade.columns else []
    )
    plano = gerar_plano_30_60_90(
        candidato,
        {"municipios_oportunidade": municipios_oport_lista},
        {"municipios_atencao": alertas.get("prioridade_comunicacao", [])},
    )
    checklist = plano.get("compliance_checklist") or gerar_checklist_compliance(plano)
    kpis = _calcular_kpis(candidato_id, periodo_inicio, periodo_fim, resumo_emendas, matriz)
    regra_territorial = detectar_escopo_cargo(candidato.get("cargo"))
    distribuicao_territorial = _preparar_distribuicao_territorial_pdf(candidato, periodo_fim)
    linhas_territoriais = _linhas_tabela_territorial(distribuicao_territorial)

    if not REPORTLAB_AVAILABLE:
        return _gerar_pdf_simples(caminho, [
            "Radar Eleitoral IA",
            "Relatório Estratégico Eleitoral",
            f"Candidato: {candidato['nome_urna']} - {candidato.get('cargo', '')}/{candidato.get('uf', '')}",
            f"Período analisado: {periodo_inicio} a {periodo_fim}",
            badge_dados,
            f"Fonte eleitoral: {fonte_eleitoral}",
            "Sumário executivo",
            *(_descobertas(resumo_estrategico, alertas, kpis)[:5]),
            "Distribuição municipal detalhada",
            distribuicao_territorial.get("mensagem", ""),
            distribuicao_territorial.get("aviso_importacao", ""),
            *(f"{linha[1]} {linha[2]} - {linha[7]} votos" for linha in linhas_territoriais[:8]),
            "Plano de comunicação 30/60/90",
            plano.get("plano_30_dias", ""),
            plano.get("plano_60_dias", ""),
            plano.get("plano_90_dias", ""),
            f"Compliance: {checklist.get('classificacao_geral')}",
            AVISO_JURIDICO,
        ])

    styles = _estilos()
    doc = SimpleDocTemplate(
        caminho,
        pagesize=A4,
        leftMargin=1.45 * cm,
        rightMargin=1.45 * cm,
        topMargin=1.35 * cm,
        bottomMargin=1.35 * cm,
        title="Radar Eleitoral IA - Relatório Estratégico",
    )
    story = []

    capa = Table([
        [_p("Radar Eleitoral IA", styles["CoverTitle"])],
        [_p("Relatório Estratégico Eleitoral", styles["CoverSubtitle"])],
        [_p(f"{candidato['nome_urna']} | {candidato.get('cargo', '')} | {candidato.get('uf', '')}", styles["CoverSubtitle"])],
        [_p(f"Partido: {candidato.get('partido') or candidato.get('sigla_partido') or '-'}", styles["CoverSubtitle"])],
        [_p(f"Período analisado: {periodo_inicio} a {periodo_fim}", styles["CoverSubtitle"])],
        [_p(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')} | {badge_dados}", styles["CoverSubtitle"])],
    ], colWidths=[18 * cm])
    capa.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(NAVY)),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(NAVY)),
        ("TOPPADDING", (0, 0), (-1, -1), 16),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(Spacer(1, 5.8 * cm))
    story.append(capa)
    story.append(Spacer(1, 1 * cm))
    story.append(_p("Diagnóstico territorial, análise de esforço x resultado, plano de comunicação e compliance.", styles["BodySmall"]))
    story.append(PageBreak())

    story.append(_p("Sumário Executivo", styles["SectionTitle"]))
    descobertas = _descobertas(resumo_estrategico, alertas, kpis)[:6]
    story.append(_tabela_padrao([[f"{idx}.", item] for idx, item in enumerate(descobertas, start=1)], ["#", "Principais descobertas"], [1.0 * cm, 16.7 * cm]))
    story.append(Spacer(1, .35 * cm))
    story.append(_p("KPIs em destaque", styles["SectionTitle"]))
    story.append(_kpi_table(kpis))
    story.append(PageBreak())

    story.append(_p("Linha do Tempo Eleitoral", styles["SectionTitle"]))
    linha_tempo = gerar_linha_do_tempo(candidato_id)
    if not linha_tempo.empty:
        dados_linha = [
            [r["ano"], r["cargo"], r["partido"], _fmt_int(r["votos_totais"]), r["situacao"], _fmt_pct(r.get("crescimento_pct", 0))]
            for _, r in linha_tempo.iterrows()
        ]
        story.append(_tabela_padrao(dados_linha, ["Ano", "Cargo", "Partido", "Votos", "Situação", "Crescimento"]))
    else:
        story.append(_p("Nenhum dado encontrado para a linha do tempo eleitoral.", styles["BodySmall"]))
    story.append(Spacer(1, .3 * cm))

    story.append(_p("Municípios", styles["SectionTitle"]))
    fortes = ranking_municipios_fortes(candidato_id, periodo_fim)
    queda = ranking_municipios_queda(candidato_id, periodo_inicio, periodo_fim)
    if not fortes.empty:
        story.append(_p("Top municípios por votos", styles["BodySmall"]))
        story.append(_tabela_padrao([[r["municipio"], _fmt_int(r["votos"])] for _, r in fortes.head(8).iterrows()], ["Município", "Votos"]))
        story.append(Spacer(1, .25 * cm))
    if not queda.empty:
        story.append(_p("Municípios em queda", styles["BodySmall"]))
        story.append(_tabela_padrao(
            [[r["municipio"], _fmt_int(r["variacao_absoluta"]), _fmt_pct(r["variacao_percentual"])] for _, r in queda.head(8).iterrows()],
            ["Município", "Variação absoluta", "Variação %"],
        ))
    if not oportunidade.empty:
        story.append(Spacer(1, .25 * cm))
        story.append(_p("Oportunidades", styles["BodySmall"]))
        story.append(_tabela_padrao(
            [[r["municipio"], _fmt_int(r.get("votos", 0)), r.get("potencial_comunicacao", "")] for _, r in oportunidade.head(8).iterrows()],
            ["Município", "Votos", "Leitura"],
        ))
    if regra_territorial["nivel_principal"] == "municipal":
        story.append(Spacer(1, .35 * cm))
        story.append(_p("Distribuição municipal detalhada", styles["SectionTitle"]))
        story.append(_p(distribuicao_territorial.get("mensagem", ""), styles["BodySmall"]))
        if distribuicao_territorial.get("aviso_importacao"):
            story.append(_p(distribuicao_territorial["aviso_importacao"], styles["BodySmall"]))
        story.append(_p(
            "A análise por bairro depende da importação da base de seção/local de votação "
            "e geocodificação territorial.",
            styles["BodySmall"],
        ))
        if linhas_territoriais:
            story.append(_tabela_padrao(
                linhas_territoriais,
                ["Rank", "Nível", "Território", "Município", "Zona", "Seção", "Bairro", "Votos", "%"],
                [1.0 * cm, 2.0 * cm, 3.0 * cm, 3.0 * cm, 1.4 * cm, 1.4 * cm, 2.4 * cm, 1.5 * cm, 1.3 * cm],
            ))
        else:
            story.append(_p("Nenhum dado territorial detalhado encontrado para o cargo municipal.", styles["BodySmall"]))
    story.append(PageBreak())

    story.append(_p("Esforço x Resultado", styles["SectionTitle"]))
    if resumo_emendas and resumo_emendas.get("total_pago", 0) > 0:
        story.append(_p(
            f"Total empenhado: {_fmt_brl(resumo_emendas.get('total_empenhado', 0))} | "
            f"Total pago: {_fmt_brl(resumo_emendas.get('total_pago', 0))} | "
            f"Municípios beneficiados: {len(resumo_emendas.get('municipios_beneficiados', []))}",
            styles["BodySmall"],
        ))
    else:
        story.append(_p("Nenhum dado de emendas encontrado para este candidato.", styles["BodySmall"]))
    story.append(Spacer(1, .25 * cm))
    if matriz is not None and not matriz.empty:
        dados_matriz = [
            [
                r["municipio"],
                _fmt_brl(r["valor_total_pago"]),
                _fmt_pct(r["variacao_percentual"]),
                r["classificacao"],
                r.get("leitura_ia", "Leitura institucional não disponível para este município."),
            ]
            for _, r in matriz.head(12).iterrows()
        ]
        story.append(_tabela_padrao(dados_matriz, ["Município", "Valor pago", "Variação votos", "Classificação", "Leitura institucional"], [3.2 * cm, 2.6 * cm, 2.4 * cm, 3.5 * cm, 6.0 * cm]))
    else:
        story.append(_p("Nenhum dado encontrado para calcular a matriz esforço x resultado.", styles["BodySmall"]))
    story.append(PageBreak())

    story.append(_p("Plano de Comunicação 30/60/90", styles["SectionTitle"]))
    story.append(_p(f"Objetivo: {plano.get('objetivo_geral', '')}", styles["BodySmall"]))
    story.append(Spacer(1, .25 * cm))
    story.append(_tabela_padrao([
        ["30 dias", plano.get("plano_30_dias", "")],
        ["60 dias", plano.get("plano_60_dias", "")],
        ["90 dias", plano.get("plano_90_dias", "")],
        ["Canais", ", ".join(plano.get("canais_recomendados", []))],
        ["Temas", ", ".join(plano.get("temas_prioritarios", []))],
    ], ["Horizonte", "Recomendação"], [2.6 * cm, 15.0 * cm]))
    story.append(PageBreak())

    story.append(_p("Compliance", styles["SectionTitle"]))
    dados_checklist = [
        ["Pedido explícito de voto", "Sim" if checklist.get("existe_pedido_explicito_de_voto") else "Não"],
        ["Ataque pessoal", "Sim" if checklist.get("existe_ataque_pessoal") else "Não"],
        ["Promessa exagerada", "Sim" if checklist.get("existe_promessa_exagerada") else "Não"],
        ["Dados sem fonte", "Sim" if checklist.get("existem_dados_sem_fonte") else "Não"],
        ["Impulsionamento irregular", "Sim" if checklist.get("existe_risco_de_impulsionamento_irregular") else "Não"],
        ["Uso de IA a identificar", "Sim" if checklist.get("existe_uso_de_ia_que_precisa_ser_identificado") else "Não"],
        ["Risco geral", checklist.get("classificacao_geral", "não avaliado")],
        ["Revisão jurídica", "Sim" if checklist.get("recomenda_revisao_juridica") else "Não"],
    ]
    story.append(_tabela_padrao(dados_checklist, ["Item", "Resultado"], [8 * cm, 9.6 * cm]))
    story.append(Spacer(1, .35 * cm))
    story.append(Paragraph(_escape(AVISO_JURIDICO), styles["Warning"]))
    story.append(PageBreak())

    story.append(_p("Fontes dos Dados", styles["SectionTitle"]))
    story.append(_tabela_padrao([
        ["Dados eleitorais", origem_eleitoral, fonte_eleitoral],
        ["Emendas/verbas", "CSV/API/Banco local", "Portal da Transparência ou arquivo manual importado"],
        ["Dados de demonstração", "Aplicável quando indicado", "Usados apenas para validar o MVP"],
    ], ["Categoria", "Origem", "Fonte"]))
    story.append(Spacer(1, .5 * cm))
    story.append(_p("Próximos passos comerciais", styles["SectionTitle"]))
    story.append(_p(PROXIMO_PASSO_COMERCIAL, styles["BodySmall"]))

    doc.build(story)
    logger.info(f"Relatório PDF gerado em: {caminho}")
    return caminho


if __name__ == "__main__":
    caminho_gerado = gerar_pdf_relatorio(1, 2016, 2020)
    print(f"[PDF] PDF gerado em: {caminho_gerado}")
    print(f"[PDF] Tamanho do arquivo: {os.path.getsize(caminho_gerado)} bytes")
