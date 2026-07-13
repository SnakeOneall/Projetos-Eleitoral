"""Componentes visuais do dashboard Radar Eleitoral IA."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analysis.territorial_analysis import (
    agregar_votos_por_municipio,
    agregar_votos_por_zona,
    analisar_distribuicao_territorial,
    preparar_mapa_vereador_sp,
)


COLORS = {
    "navy": "#0f2742",
    "navy_2": "#163a5f",
    "blue": "#1f78ff",
    "green": "#17a673",
    "red": "#d64545",
    "orange": "#f59e0b",
    "gray_bg": "#f5f7fb",
    "gray_border": "#d8e0ea",
    "text": "#172033",
}


def inject_dashboard_css() -> None:
    """Aplica a camada visual do produto SaaS/BI no Streamlit."""
    st.markdown(
        f"""
        <style>
        .stApp {{
            background: {COLORS["gray_bg"]};
            color: {COLORS["text"]};
        }}
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {COLORS["navy"]} 0%, #091827 100%);
            border-right: 1px solid rgba(255,255,255,.08);
        }}
        section[data-testid="stSidebar"] {{
            color: #f8fbff;
        }}
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] .radar-brand,
        section[data-testid="stSidebar"] .radar-brand * {{
            color: #f8fbff !important;
        }}
        section[data-testid="stSidebar"] input,
        section[data-testid="stSidebar"] textarea,
        section[data-testid="stSidebar"] select {{
            color: #172033 !important;
        }}
        section[data-testid="stSidebar"] div[data-baseweb="select"],
        section[data-testid="stSidebar"] div[data-baseweb="select"] *,
        section[data-testid="stSidebar"] div[data-baseweb="input"],
        section[data-testid="stSidebar"] div[data-baseweb="input"] *,
        section[data-testid="stSidebar"] div[data-baseweb="textarea"],
        section[data-testid="stSidebar"] div[data-baseweb="textarea"] * {{
            color: #172033 !important;
            -webkit-text-fill-color: #172033 !important;
        }}
        section[data-testid="stSidebar"] div[data-baseweb="select"],
        section[data-testid="stSidebar"] div[data-baseweb="input"],
        section[data-testid="stSidebar"] div[data-baseweb="textarea"] {{
            background: #ffffff !important;
            border-radius: 8px !important;
        }}
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] label *,
        section[data-testid="stSidebar"] .stRadio > label,
        section[data-testid="stSidebar"] .stCheckbox > label {{
            color: #f8fbff !important;
        }}
        section[data-testid="stSidebar"] div[data-baseweb="radio"] label span,
        section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label span {{
            color: #f8fbff !important;
        }}
        div[data-baseweb="popover"],
        div[data-baseweb="popover"] *,
        ul[role="listbox"],
        ul[role="listbox"] *,
        div[role="listbox"],
        div[role="listbox"] *,
        li[role="option"],
        li[role="option"] * {{
            color: #172033 !important;
            -webkit-text-fill-color: #172033 !important;
            background-color: #ffffff;
        }}
        li[role="option"]:hover,
        div[role="option"]:hover {{
            background-color: #eaf2ff !important;
        }}
        div[data-baseweb="select"] svg {{
            color: #172033 !important;
            fill: #172033 !important;
        }}
        div[data-testid="stNumberInput"] input,
        div[data-testid="stTextInput"] input,
        div[data-testid="stSelectbox"] div[data-baseweb="select"] *,
        div[data-testid="stMultiSelect"] div[data-baseweb="select"] * {{
            color: #172033 !important;
            -webkit-text-fill-color: #172033 !important;
        }}
        html body .stApp section[data-testid="stSidebar"] div[data-testid="stSelectbox"] div[data-baseweb="select"] div,
        html body .stApp section[data-testid="stSidebar"] div[data-testid="stSelectbox"] div[data-baseweb="select"] span,
        html body .stApp section[data-testid="stSidebar"] div[data-testid="stSelectbox"] div[data-baseweb="select"] [value],
        html body .stApp section[data-testid="stSidebar"] div[data-testid="stMultiSelect"] div[data-baseweb="select"] div,
        html body .stApp section[data-testid="stSidebar"] div[data-testid="stMultiSelect"] div[data-baseweb="select"] span,
        html body .stApp section[data-testid="stSidebar"] div[data-testid="stNumberInput"] input,
        html body .stApp section[data-testid="stSidebar"] div[data-testid="stTextInput"] input {{
            color: #172033 !important;
            -webkit-text-fill-color: #172033 !important;
        }}
        .radar-brand {{
            padding: 1rem 0 .75rem 0;
            border-bottom: 1px solid rgba(255,255,255,.16);
            margin-bottom: 1rem;
        }}
        .radar-brand-title {{
            font-size: 1.35rem;
            font-weight: 800;
            letter-spacing: .02em;
        }}
        .radar-brand-sub {{
            font-size: .78rem;
            opacity: .75;
            margin-top: .2rem;
        }}
        .dashboard-header {{
            background: linear-gradient(135deg, {COLORS["navy"]} 0%, {COLORS["navy_2"]} 65%, {COLORS["blue"]} 100%);
            color: white;
            padding: 1.25rem 1.4rem;
            border-radius: 12px;
            box-shadow: 0 12px 30px rgba(15, 39, 66, .18);
            margin-bottom: 1rem;
        }}
        .dashboard-header h1 {{
            margin: 0;
            font-size: 1.55rem;
            font-weight: 800;
        }}
        .dashboard-header p {{
            margin: .35rem 0 0 0;
            opacity: .88;
        }}
        .card {{
            background: white;
            border: 1px solid {COLORS["gray_border"]};
            border-radius: 12px;
            box-shadow: 0 8px 24px rgba(23, 32, 51, .06);
            padding: 1rem 1.1rem;
            margin-bottom: .85rem;
        }}
        .kpi-card {{
            background: white;
            border: 1px solid {COLORS["gray_border"]};
            border-radius: 12px;
            box-shadow: 0 8px 24px rgba(23, 32, 51, .06);
            padding: .95rem 1rem;
            min-height: 108px;
        }}
        .kpi-label {{
            color: #5b6b7c;
            font-size: .78rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .04em;
        }}
        .kpi-value {{
            color: {COLORS["navy"]};
            font-size: 1.45rem;
            font-weight: 850;
            margin-top: .35rem;
        }}
        .kpi-help {{
            color: #728295;
            font-size: .78rem;
            margin-top: .15rem;
        }}
        .badge-row {{
            display: flex;
            flex-wrap: wrap;
            gap: .45rem;
            margin: .4rem 0 1rem 0;
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: .28rem .68rem;
            font-size: .76rem;
            font-weight: 800;
            border: 1px solid transparent;
        }}
        .badge-ok {{
            background: #e8f8f1;
            color: #0b7a51;
            border-color: #bdebd7;
        }}
        .badge-warn {{
            background: #fff7e6;
            color: #9a5d00;
            border-color: #f8ddb0;
        }}
        .badge-muted {{
            background: #eef2f7;
            color: #5b6b7c;
            border-color: #d8e0ea;
        }}
        .section-title {{
            font-size: 1.05rem;
            font-weight: 850;
            color: {COLORS["navy"]};
            margin-bottom: .5rem;
        }}
        .empty-state {{
            border: 1px dashed #b9c6d6;
            background: #f8fbff;
            border-radius: 12px;
            padding: 1rem;
            color: #526274;
        }}
        div.stButton > button:first-child {{
            border-radius: 10px;
            border: 1px solid {COLORS["blue"]};
            background: {COLORS["blue"]};
            color: white;
            font-weight: 800;
        }}
        div.stDownloadButton > button:first-child {{
            border-radius: 10px;
            background: {COLORS["green"]};
            color: white;
            font-weight: 800;
            border: 0;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(candidato: dict | None) -> str:
    nome = (candidato or {}).get("nome_urna") or "Nenhum candidato selecionado"
    cargo = (candidato or {}).get("cargo") or "-"
    uf = (candidato or {}).get("uf") or "-"
    partido = (candidato or {}).get("partido") or (candidato or {}).get("sigla_partido") or "-"
    atualizado = datetime.now().strftime("%d/%m/%Y %H:%M")
    titulo = f"Candidato selecionado: {nome} | {cargo} | {uf} | {partido}"
    st.markdown(
        f"""
        <div class="dashboard-header">
          <h1>Radar Eleitoral IA</h1>
          <p>{titulo}</p>
          <p>Atualizado em: {atualizado}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return titulo


def render_status_badges(status: dict, origem_dados: str | None = None) -> list[str]:
    labels = {
        "tse_carregado": "TSE carregado",
        "candidato_salvo": "Candidato salvo",
        "emendas_carregadas": "Emendas carregadas",
        "analise_calculada": "Análise gerada",
        "plano_gerado": "Plano gerado",
        "pdf_gerado": "PDF gerado",
    }
    badges = []
    for key, label in labels.items():
        classe = "badge-ok" if status.get(key) else "badge-muted"
        texto = f"{'OK' if status.get(key) else '--'} {label}"
        badges.append(f'<span class="badge {classe}">{texto}</span>')

    if origem_dados == "real":
        badges.append('<span class="badge badge-ok">Fonte oficial TSE</span>')
    elif origem_dados == "demo":
        badges.append('<span class="badge badge-warn">Dados de demonstração</span>')

    st.markdown(f'<div class="badge-row">{"".join(badges)}</div>', unsafe_allow_html=True)
    return badges


def _metricas_padrao(metricas: dict | None) -> dict:
    metricas = metricas or {}
    return {
        "votos_totais": metricas.get("votos_totais", "0"),
        "crescimento": metricas.get("crescimento", "0%"),
        "municipios_fortes": metricas.get("municipios_fortes", "0"),
        "emendas_pagas": metricas.get("emendas_pagas", "R$ 0,00"),
        "indice_retorno": metricas.get("indice_retorno", "N/D"),
    }


def render_kpi_cards(metricas: dict | None) -> dict:
    dados = _metricas_padrao(metricas)
    cards = [
        ("Votos Totais", dados["votos_totais"], "Base eleitoral consolidada"),
        ("Crescimento", dados["crescimento"], "Evolução no período"),
        ("Municípios Fortes", dados["municipios_fortes"], "Territórios de maior tração"),
        ("Emendas Pagas", dados["emendas_pagas"], "Execução territorial identificada"),
        ("Índice de Retorno", dados["indice_retorno"], "Retorno territorial estimado"),
    ]
    cols = st.columns(len(cards))
    for col, (label, value, help_text) in zip(cols, cards):
        col.markdown(
            f"""
            <div class="kpi-card">
              <div class="kpi-label">{label}</div>
              <div class="kpi-value">{value}</div>
              <div class="kpi-help">{help_text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    return dados


def render_filter_panel() -> None:
    st.markdown('<div class="section-title">Filtros de análise</div>', unsafe_allow_html=True)


def render_empty_state(titulo: str, mensagem: str) -> None:
    st.markdown(
        f"""
        <div class="empty-state">
          <strong>{titulo}</strong><br/>
          {mensagem}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_timeline_chart(df: pd.DataFrame | None) -> go.Figure:
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(template="plotly_white", height=320, annotations=[{
            "text": "Nenhum dado encontrado para a linha do tempo.",
            "showarrow": False,
            "xref": "paper",
            "yref": "paper",
            "x": 0.5,
            "y": 0.5,
        }])
        return fig
    fig = px.line(df, x="ano", y="votos_totais", markers=True, text="votos_totais")
    fig.update_traces(line_color=COLORS["blue"], marker=dict(size=9))
    fig.update_layout(template="plotly_white", height=320, margin=dict(l=20, r=20, t=30, b=20))
    return fig


def render_municipios_chart(df: pd.DataFrame | None, titulo: str = "Ranking municipal", color: str | None = None) -> go.Figure:
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(template="plotly_white", height=320, title=titulo, annotations=[{
            "text": "Nenhum dado encontrado para este ranking.",
            "showarrow": False,
            "xref": "paper",
            "yref": "paper",
            "x": 0.5,
            "y": 0.5,
        }])
        return fig
    y_col = "municipio"
    x_col = "votos" if "votos" in df.columns else "variacao_absoluta"
    fig = px.bar(df.head(10).sort_values(x_col), x=x_col, y=y_col, orientation="h", title=titulo)
    fig.update_traces(marker_color=color or COLORS["blue"])
    fig.update_layout(template="plotly_white", height=360, margin=dict(l=20, r=20, t=45, b=20))
    return fig


def render_performance_map(df: pd.DataFrame | None) -> go.Figure:
    """Renderiza um mapa visual em blocos por município enquanto não há GeoJSON."""
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(template="plotly_white", height=420, annotations=[{
            "text": "Nenhum dado municipal disponível para montar o mapa visual.",
            "showarrow": False,
            "xref": "paper",
            "yref": "paper",
            "x": 0.5,
            "y": 0.5,
        }])
        return fig

    base = df.copy()
    if "municipio" not in base.columns:
        return render_performance_map(pd.DataFrame())
    if "votos" not in base.columns:
        base["votos"] = 1
    base["votos"] = pd.to_numeric(base["votos"], errors="coerce").fillna(0)
    base = base[base["votos"] >= 0].head(20)
    if base.empty:
        return render_performance_map(pd.DataFrame())

    fig = px.treemap(
        base,
        path=["municipio"],
        values="votos",
        color="votos",
        color_continuous_scale=[[0, "#dbeafe"], [0.5, COLORS["blue"]], [1, COLORS["navy"]]],
        title="Mapa visual de desempenho municipal",
    )
    fig.update_layout(template="plotly_white", height=430, margin=dict(l=10, r=10, t=45, b=10))
    return fig


def _layout_zonas_sao_paulo(zonas: list[str]) -> pd.DataFrame:
    """Monta um tile map estável para zonas eleitorais da cidade de São Paulo.

    O arquivo atual do TSE traz zona eleitoral, mas não traz polígono/bairro.
    Este layout usa blocos territoriais para evitar o mapa em um único bloco
    quando a eleição é municipal.
    """
    zonas_ordenadas = sorted(zonas, key=lambda z: int(str(z)) if str(z).isdigit() else 9999)
    linhas = [
        ("Norte / Noroeste", 7),
        ("Norte / Nordeste", 9),
        ("Oeste / Centro / Leste", 11),
        ("Centro expandido", 12),
        ("Sul / Sudeste", 10),
        ("Extremo Sul", 8),
    ]
    registros = []
    idx = 0
    for linha_idx, (regiao, largura) in enumerate(linhas):
        y = len(linhas) - linha_idx
        offset = (max(l[1] for l in linhas) - largura) / 2
        for pos in range(largura):
            if idx >= len(zonas_ordenadas):
                break
            registros.append({
                "zona": zonas_ordenadas[idx],
                "x": pos + offset,
                "y": y,
                "regiao_mapa": regiao,
            })
            idx += 1
    while idx < len(zonas_ordenadas):
        registros.append({
            "zona": zonas_ordenadas[idx],
            "x": (idx % 12),
            "y": 0,
            "regiao_mapa": "Outras zonas",
        })
        idx += 1
    return pd.DataFrame(registros)


def render_zone_heatmap(df: pd.DataFrame | None, titulo: str = "Mapa por zonas eleitorais") -> go.Figure:
    """Renderiza distribuição de votos por zona eleitoral.

    Para São Paulo, o TSE entrega a votação por zona, mas não a malha
    geográfica dos bairros. O gráfico usa um tile map com regiões da cidade,
    evitando a perda de detalhe que acontece no mapa por município.
    """
    if df is None or df.empty or "zona" not in df.columns:
        fig = go.Figure()
        fig.update_layout(template="plotly_white", height=440, annotations=[{
            "text": "Nenhum dado por zona eleitoral disponível para montar o mapa.",
            "showarrow": False,
            "xref": "paper",
            "yref": "paper",
            "x": 0.5,
            "y": 0.5,
        }])
        return fig

    base = df.copy()
    base["zona"] = base["zona"].astype(str).str.replace(".0", "", regex=False).str.strip()
    base["votos"] = pd.to_numeric(base.get("votos", 0), errors="coerce").fillna(0)
    base = (
        base.groupby(["zona"], dropna=False)
        .agg(votos=("votos", "sum"), municipio=("municipio", "first"), ano=("ano", "first"))
        .reset_index()
    )
    base = base[base["zona"].notna() & (base["zona"] != "")]
    if base.empty:
        return render_zone_heatmap(pd.DataFrame())

    layout = _layout_zonas_sao_paulo(base["zona"].tolist())
    mapa = base.merge(layout, on="zona", how="left")
    mapa["x"] = pd.to_numeric(mapa["x"], errors="coerce").fillna(0)
    mapa["y"] = pd.to_numeric(mapa["y"], errors="coerce").fillna(0)
    max_votos = float(mapa["votos"].max() or 1)
    mapa["tamanho"] = 22 + (mapa["votos"] / max_votos).pow(0.5) * 42
    mapa["label"] = "Z" + mapa["zona"].astype(str)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=mapa["x"],
        y=mapa["y"],
        mode="markers+text",
        text=mapa["label"],
        textposition="middle center",
        textfont=dict(color="white", size=10),
        marker=dict(
            symbol="hexagon",
            size=mapa["tamanho"],
            color=mapa["votos"],
            colorscale=[[0, "#dbeafe"], [0.35, "#60a5fa"], [0.7, "#2563eb"], [1, "#0f2742"]],
            showscale=True,
            colorbar=dict(title="Votos"),
            line=dict(color="white", width=2),
        ),
        customdata=mapa[["zona", "municipio", "regiao_mapa", "votos"]].values,
        hovertemplate=(
            "<b>Zona eleitoral %{customdata[0]}</b><br>"
            "Município: %{customdata[1]}<br>"
            "Região visual: %{customdata[2]}<br>"
            "Votos: %{customdata[3]:,.0f}<extra></extra>"
        ),
    ))

    contorno_x = [-0.8, 2.0, 5.8, 10.8, 12.8, 10.8, 8.6, 5.2, 1.0, -0.8]
    contorno_y = [3.1, 6.6, 7.2, 6.2, 4.2, 2.0, 0.8, 0.2, 1.4, 3.1]
    fig.add_trace(go.Scatter(
        x=contorno_x,
        y=contorno_y,
        mode="lines",
        line=dict(color="#94a3b8", width=2, dash="dot"),
        hoverinfo="skip",
        showlegend=False,
    ))

    for regiao, largura in [
        ("Norte", 6),
        ("Oeste", 3),
        ("Centro", 6),
        ("Leste", 10),
        ("Sul", 6),
    ]:
        coords = {
            "Norte": (5.7, 6.85),
            "Oeste": (1.2, 3.8),
            "Centro": (5.7, 3.8),
            "Leste": (10.5, 3.8),
            "Sul": (5.7, 0.65),
        }[regiao]
        fig.add_annotation(
            x=coords[0],
            y=coords[1],
            text=regiao,
            showarrow=False,
            font=dict(color="#475569", size=11),
        )

    fig.update_layout(
        template="plotly_white",
        title=titulo,
        height=470,
        margin=dict(l=10, r=10, t=45, b=10),
        xaxis=dict(visible=False, range=[-1.2, 13.2]),
        yaxis=dict(visible=False, range=[0, 7.5], scaleanchor="x", scaleratio=1),
        showlegend=False,
        paper_bgcolor="white",
        plot_bgcolor="#f8fbff",
    )
    return fig


def _normalizar_texto(valor) -> str:
    if valor is None or pd.isna(valor):
        return ""
    texto = str(valor).strip().lower()
    return texto.translate(str.maketrans("áàâãéêíóôõúç", "aaaaeeiooouc"))


def _preparar_distribuicao_territorial(
    df: pd.DataFrame | None,
    cargo: str | None = None,
    municipio: str | None = None,
    uf: str | None = None,
) -> dict:
    if df is None or df.empty:
        return {
            "granularidade": "vazio",
            "dados": pd.DataFrame(columns=["territorio", "votos", "percentual"]),
            "total_votos": 0,
            "titulo": "Distribuição territorial de votos",
            "mensagem": "Nenhum dado territorial encontrado para os filtros atuais.",
        }

    base = df.copy()
    if "votos" not in base.columns:
        base["votos"] = 0
    base["votos"] = pd.to_numeric(base["votos"], errors="coerce").fillna(0)

    cargo_ref = cargo or (base["cargo"].dropna().iloc[0] if "cargo" in base.columns and base["cargo"].notna().any() else "")
    municipio_ref = municipio or (
        base["municipio"].dropna().iloc[0] if "municipio" in base.columns and base["municipio"].notna().any() else ""
    )
    uf_ref = (uf or (base["uf"].dropna().iloc[0] if "uf" in base.columns and base["uf"].notna().any() else "")).upper()

    tem_zona = "zona" in base.columns and base["zona"].notna().any() and base["zona"].astype(str).str.strip().ne("").any()
    vereador_sp = "vereador" in _normalizar_texto(cargo_ref) and _normalizar_texto(municipio_ref) == "sao paulo" and uf_ref == "SP"

    if vereador_sp and tem_zona:
        base["zona"] = base["zona"].astype(str).str.replace(".0", "", regex=False).str.strip()
        dados = (
            base.groupby(["zona"], dropna=False)
            .agg(votos=("votos", "sum"), municipio=("municipio", "first"))
            .reset_index()
        )
        dados["territorio"] = "Zona " + dados["zona"].astype(str)
        granularidade = "zona"
        titulo = "Distribuição de votos em São Paulo por zona eleitoral"
        mensagem = "Dados territoriais encontrados por zona eleitoral."
    elif "municipio" in base.columns and base["municipio"].notna().any():
        dados = base.groupby(["municipio"], dropna=False).agg(votos=("votos", "sum")).reset_index()
        dados["territorio"] = dados["municipio"].astype(str)
        granularidade = "municipio"
        titulo = "Distribuição territorial de votos por município"
        mensagem = (
            "Os dados disponíveis não possuem zona eleitoral para esta consulta."
            if vereador_sp and not tem_zona
            else "Distribuição territorial calculada por município."
        )
    elif tem_zona:
        base["zona"] = base["zona"].astype(str).str.replace(".0", "", regex=False).str.strip()
        dados = base.groupby(["zona"], dropna=False).agg(votos=("votos", "sum")).reset_index()
        dados["territorio"] = "Zona " + dados["zona"].astype(str)
        granularidade = "zona"
        titulo = "Distribuição territorial de votos por zona eleitoral"
        mensagem = "Dados territoriais encontrados por zona eleitoral."
    else:
        return {
            "granularidade": "vazio",
            "dados": pd.DataFrame(columns=["territorio", "votos", "percentual"]),
            "total_votos": int(base["votos"].sum()),
            "titulo": "Distribuição territorial de votos",
            "mensagem": "Nenhum dado territorial encontrado para os filtros atuais.",
        }

    total = float(dados["votos"].sum() or 0)
    dados["percentual"] = (dados["votos"] / total * 100).round(2) if total else 0.0
    dados = dados.sort_values("votos", ascending=False).reset_index(drop=True)
    return {
        "granularidade": granularidade,
        "dados": dados,
        "total_votos": int(total),
        "titulo": titulo,
        "mensagem": mensagem,
    }


def _fig_distribuicao_territorial(dados: pd.DataFrame, titulo: str) -> go.Figure:
    if dados is None or dados.empty:
        fig = go.Figure()
        fig.update_layout(template="plotly_white", height=360, title=titulo, annotations=[{
            "text": "Nenhum dado territorial encontrado.",
            "showarrow": False,
            "xref": "paper",
            "yref": "paper",
            "x": 0.5,
            "y": 0.5,
        }])
        return fig

    top = dados.head(15).sort_values("votos")
    fig = px.bar(
        top,
        x="votos",
        y="territorio",
        orientation="h",
        text="votos",
        title=titulo,
        labels={"votos": "Votos", "territorio": "Território"},
    )
    fig.update_traces(marker_color=COLORS["blue"], texttemplate="%{text:,.0f}", textposition="outside")
    fig.update_layout(template="plotly_white", height=430, margin=dict(l=10, r=30, t=55, b=20))
    return fig


def render_territorial_distribution(
    df: pd.DataFrame | None,
    cargo: str | None = None,
    municipio: str | None = None,
    uf: str | None = None,
    key_prefix: str = "territorial",
) -> dict:
    """Renderiza distribuição territorial por zona eleitoral ou município."""
    resultado = _preparar_distribuicao_territorial(df, cargo=cargo, municipio=municipio, uf=uf)
    st.markdown('<div class="section-title">Distribuição territorial de votos</div>', unsafe_allow_html=True)

    if resultado["granularidade"] == "vazio":
        render_empty_state("Nenhum dado territorial encontrado", resultado["mensagem"])
        return resultado

    total_formatado = f"{resultado['total_votos']:,}".replace(",", ".")
    st.metric("Total de votos no recorte", total_formatado)
    if resultado["granularidade"] == "zona":
        st.success(resultado["mensagem"])
    else:
        st.info(resultado["mensagem"])
    st.info(
        "O mapa geográfico será ativado quando a base territorial for importada. "
        "Abaixo está a distribuição oficial por zona/município."
    )

    fig = _fig_distribuicao_territorial(resultado["dados"], resultado["titulo"])
    st.plotly_chart(fig, width="stretch", key=f"{key_prefix}_barras")

    colunas = [c for c in ["municipio", "zona", "territorio", "votos", "percentual"] if c in resultado["dados"].columns]
    st.dataframe(resultado["dados"][colunas], width="stretch", hide_index=True)
    resultado["fig"] = fig
    return resultado


def _tem_lat_lon(df: pd.DataFrame | None) -> bool:
    if df is None or df.empty or "latitude" not in df.columns or "longitude" not in df.columns:
        return False
    coords = df[["latitude", "longitude"]].apply(pd.to_numeric, errors="coerce")
    return bool(coords.notna().all(axis=1).any())


def _agregar_municipios_com_geodata(df: pd.DataFrame | None) -> pd.DataFrame:
    dados = agregar_votos_por_municipio(df)
    if dados.empty or df is None or df.empty or not _tem_lat_lon(df):
        return dados

    base = df.copy()
    if "uf" not in base.columns:
        base["uf"] = ""
    base["latitude"] = pd.to_numeric(base["latitude"], errors="coerce")
    base["longitude"] = pd.to_numeric(base["longitude"], errors="coerce")
    coords = (
        base.dropna(subset=["latitude", "longitude"])
        .groupby(["uf", "municipio"], dropna=False)
        .agg(latitude=("latitude", "first"), longitude=("longitude", "first"))
        .reset_index()
    )
    return dados.merge(coords, on=["uf", "municipio"], how="left")


def _fig_ranking_territorial(dados: pd.DataFrame, titulo: str, granularidade: str) -> go.Figure:
    if dados is None or dados.empty:
        return _fig_distribuicao_territorial(pd.DataFrame(), titulo)

    base = dados.copy()
    if "chave_territorial" in base.columns:
        base["territorio"] = base["chave_territorial"].astype(str)
        if granularidade == "zona":
            base["territorio"] = "Zona " + base["territorio"]
        elif granularidade == "secao":
            base["territorio"] = "Seção " + base["territorio"]
    elif granularidade == "zona":
        base["territorio"] = "Zona " + base["zona"].astype(str)
    else:
        base["territorio"] = base["municipio"].astype(str)
    return _fig_distribuicao_territorial(base, titulo)


def _fig_mapa_pontos(dados: pd.DataFrame, titulo: str, granularidade: str) -> go.Figure:
    base = dados.copy()
    base["latitude"] = pd.to_numeric(base["latitude"], errors="coerce")
    base["longitude"] = pd.to_numeric(base["longitude"], errors="coerce")
    base = base.dropna(subset=["latitude", "longitude"])
    label_col = "chave_territorial" if "chave_territorial" in base.columns else ("zona" if granularidade == "zona" else "municipio")
    hover_cols = [
        c for c in [
            "municipio", "zona", "secao", "local_votacao", "bairro", "votos",
            "percentual", "nome_zona", "endereco", "endereco_local", "fonte",
        ] if c in base.columns
    ]
    centro = {
        "lat": float(base["latitude"].mean()) if not base.empty else -14.2,
        "lon": float(base["longitude"].mean()) if not base.empty else -51.9,
    }
    fig = px.scatter_mapbox(
        base,
        lat="latitude",
        lon="longitude",
        size="votos",
        color="votos",
        hover_name=label_col,
        hover_data=hover_cols,
        color_continuous_scale=[[0, "#dbeafe"], [0.6, COLORS["blue"]], [1, COLORS["navy"]]],
        title=titulo,
        zoom=9 if granularidade == "zona" else 5,
        center=centro,
        height=460,
    )
    fig.update_layout(
        mapbox_style="carto-positron",
        template="plotly_white",
        margin=dict(l=10, r=10, t=45, b=10),
    )
    return fig


def render_territorial_map_or_ranking(
    df_votos: pd.DataFrame | None,
    cargo: str | None = None,
    municipio: str | None = None,
    uf: str | None = None,
    key_prefix: str = "territorial",
) -> dict:
    """Renderiza mapa geografico quando ha coordenadas; caso contrario, ranking."""
    cargo_ref = cargo or (
        df_votos["cargo"].dropna().iloc[0]
        if df_votos is not None and not df_votos.empty and "cargo" in df_votos.columns and df_votos["cargo"].notna().any()
        else ""
    )
    municipio_ref = municipio or (
        df_votos["municipio"].dropna().iloc[0]
        if df_votos is not None and not df_votos.empty and "municipio" in df_votos.columns and df_votos["municipio"].notna().any()
        else ""
    )
    uf_ref = (uf or (
        df_votos["uf"].dropna().iloc[0]
        if df_votos is not None and not df_votos.empty and "uf" in df_votos.columns and df_votos["uf"].notna().any()
        else ""
    )).upper()

    resultado = analisar_distribuicao_territorial(df_votos, cargo=cargo_ref, municipio=municipio_ref, uf=uf_ref)
    dados = resultado["dados"]
    titulo = resultado["titulo"]
    granularidade = resultado["granularidade"]
    escopo = resultado["regra"]["nivel_principal"]

    if escopo == "municipal":
        st.markdown('<div class="section-title">Análise municipal detalhada</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="section-title">{titulo}</div>', unsafe_allow_html=True)
    if resultado.get("subtitulo"):
        st.caption(resultado["subtitulo"])

    if dados is None or dados.empty:
        render_empty_state(
            "Nenhum dado territorial encontrado",
            "Selecione uma candidatura ou importe dados do TSE para visualizar a distribuição territorial.",
        )
        return {
            "tipo_visualizacao": "vazio",
            "tem_mapa": False,
            "granularidade": granularidade,
            "dados": pd.DataFrame(),
            "fig": None,
        }

    total_formatado = f"{int(dados['votos'].sum()):,}".replace(",", ".")
    st.metric("Total de votos no recorte", total_formatado)

    tem_mapa = _tem_lat_lon(dados)
    if tem_mapa:
        fig = _fig_mapa_pontos(dados, titulo, granularidade)
        st.plotly_chart(fig, width="stretch", key=f"{key_prefix}_mapa")
        tipo_visualizacao = "mapa"
    else:
        if escopo == "municipal" and granularidade == "municipio":
            st.warning(resultado["mensagem"])
        elif granularidade in {"zona", "secao", "bairro", "local_votacao"}:
            st.success(resultado["mensagem"])
        else:
            st.info(resultado["mensagem"])
        st.warning(
            "Mapa geográfico ainda não disponível para esta base. "
            "Exibindo distribuição territorial com dados oficiais do TSE."
        )
        if resultado.get("aviso_importacao"):
            st.info(resultado["aviso_importacao"])
        fig = _fig_ranking_territorial(dados, titulo, granularidade)
        st.plotly_chart(fig, width="stretch", key=f"{key_prefix}_ranking")
        tipo_visualizacao = "ranking"

    colunas = [
        c for c in [
            "ranking", "nivel", "chave_territorial", "municipio", "zona", "secao",
            "local_votacao", "bairro", "votos", "percentual", "latitude", "longitude",
            "nome_zona", "endereco", "endereco_local", "fonte",
        ] if c in dados.columns
    ]
    st.dataframe(dados[colunas], width="stretch", hide_index=True)
    return {
        "tipo_visualizacao": tipo_visualizacao,
        "tem_mapa": tem_mapa,
        "granularidade": granularidade,
        "mensagem": resultado["mensagem"],
        "aviso_importacao": resultado.get("aviso_importacao", ""),
        "dados": dados,
        "fig": fig,
    }


def render_performance_map(
    df: pd.DataFrame | None,
    cargo: str | None = None,
    municipio: str | None = None,
    uf: str | None = None,
    key_prefix: str = "performance",
) -> dict:
    """Usa mapa real apenas quando houver geodata; senão mostra ranking territorial."""
    return render_territorial_map_or_ranking(df, cargo=cargo, municipio=municipio, uf=uf, key_prefix=key_prefix)


def _render_legacy_performance_map(df: pd.DataFrame | None) -> go.Figure:
    """Compatibilidade para chamadas antigas que esperavam uma figura."""
    return render_municipios_chart(df, "Top municípios por votos", COLORS["blue"])


def render_quadrant_chart(df: pd.DataFrame | None) -> go.Figure:
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(template="plotly_white", height=380, annotations=[{
            "text": "Nenhum dado encontrado para a matriz esforço x resultado.",
            "showarrow": False,
            "xref": "paper",
            "yref": "paper",
            "x": 0.5,
            "y": 0.5,
        }])
        return fig
    fig = px.scatter(
        df,
        x="valor_total_pago",
        y="variacao_percentual",
        text="municipio",
        color="classificacao",
        title="Matriz Esforço x Resultado",
    )
    fig.add_hline(y=float(df["variacao_percentual"].median()), line_dash="dash", line_color="#9aa8b5")
    fig.add_vline(x=float(df["valor_total_pago"].median()), line_dash="dash", line_color="#9aa8b5")
    fig.update_layout(template="plotly_white", height=420, margin=dict(l=20, r=20, t=45, b=20))
    return fig


def render_compliance_card(checklist: dict | None) -> dict:
    checklist = checklist or {}
    risco = checklist.get("classificacao_geral", "não avaliado")
    classe = "badge-ok" if "baixo" in risco else ("badge-warn" if "médio" in risco else "badge-muted")
    st.markdown('<div class="section-title">Checklist de Compliance</div>', unsafe_allow_html=True)
    st.markdown(f'<span class="badge {classe}">Risco: {risco}</span>', unsafe_allow_html=True)
    itens = {
        "Pedido explícito de voto": checklist.get("existe_pedido_explicito_de_voto", False),
        "Ataque pessoal": checklist.get("existe_ataque_pessoal", False),
        "Dados sem fonte": checklist.get("existem_dados_sem_fonte", False),
        "Impulsionamento irregular": checklist.get("existe_risco_de_impulsionamento_irregular", False),
        "Uso de IA a identificar": checklist.get("existe_uso_de_ia_que_precisa_ser_identificado", True),
    }
    st.dataframe(pd.DataFrame([{"item": k, "alerta": "Sim" if v else "Não"} for k, v in itens.items()]), width="stretch", hide_index=True)
    st.caption(checklist.get("aviso", "Este relatório não substitui análise jurídica especializada."))
    return checklist


def render_communication_plan(plano: dict | None) -> dict:
    plano = plano or {}
    st.markdown('<div class="section-title">Plano de Comunicação 30/60/90</div>', unsafe_allow_html=True)
    if not plano:
        render_empty_state("Plano ainda não gerado", "Gere o plano após selecionar o candidato e revisar os dados.")
        return plano
    st.write(plano.get("objetivo_geral", ""))
    c30, c60, c90 = st.columns(3)
    c30.info(plano.get("plano_30_dias", ""))
    c60.warning(plano.get("plano_60_dias", ""))
    c90.success(plano.get("plano_90_dias", ""))
    st.caption("Canais recomendados: " + ", ".join(plano.get("canais_recomendados", [])))
    st.caption("Temas prioritários: " + ", ".join(plano.get("temas_prioritarios", [])))
    return plano


def render_audit_panel(auditoria: dict | None) -> dict:
    auditoria = auditoria or {}
    st.markdown('<div class="section-title">Auditoria dos Dados</div>', unsafe_allow_html=True)
    st.json(auditoria)
    if auditoria:
        st.dataframe(pd.DataFrame([auditoria]), width="stretch", hide_index=True)
    return auditoria
