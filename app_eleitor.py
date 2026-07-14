"""
Radar Eleitoral IA - Painel do Eleitor.

Dashboard separado, feito para o cidadão comum: digite o nome de um
deputado federal ou senador e veja, em linguagem simples, toda a
atividade parlamentar dele **por mandato** (legislatura) — presença,
votações, gastos, emendas e projetos — sempre com a fonte oficial ao
lado de cada número.

Cobre as 5 últimas legislaturas federais:
2023-2026, 2019-2022, 2015-2018, 2011-2014 e 2007-2010.

Princípios:
  - Informar, não recomendar: nenhum ranking, nota ou comparação entre
    candidatos (Resolução TSE 23.755/2026).
  - Todo dado tem fonte oficial com link.
  - Termos técnicos sempre explicados em linguagem do dia a dia.

Uso local:
    streamlit run app_eleitor.py --server.port 8502
"""

from __future__ import annotations

import os
import unicodedata
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

# Em deploy (Streamlit Cloud), a chave do Portal da Transparência vem de
# st.secrets; localmente, de .env ou config/secrets_local.py.
try:
    if "PORTAL_TRANSPARENCIA_API_KEY" in st.secrets:
        os.environ["PORTAL_TRANSPARENCIA_API_KEY"] = st.secrets["PORTAL_TRANSPARENCIA_API_KEY"]
except Exception:
    pass

from collectors.camara_collector import (
    buscar_despesas_ceap,
    buscar_discursos,
    buscar_eventos_participados,
    buscar_proposicoes_autoria,
    contar_sessoes_deliberativas,
    contar_sessoes_deliberativas_total,
    detalhar_deputado,
    listar_deputados,
    montar_como_votou,
)
from collectors.emendas_collector import (
    _carregar_token_portal,
    buscar_emendas_portal_transparencia,
)
from collectors.senado_collector import (
    buscar_autorias_senador,
    buscar_despesas_ceaps,
    buscar_votacoes_senador,
    detalhar_senador,
    listar_senadores,
)
from collectors.sp_transparencia_collector import (
    baixar_emendas_sp_csv,
    buscar_emendas_estaduais_por_autor,
)
from collectors.obras_sp_collector import (
    buscar_obras_por_municipio,
    normalizar_nome_municipio,
)
from collectors.alesp_collector import (
    buscar_despesas_gabinete,
    buscar_presencas_comissoes,
    buscar_votos_comissoes,
    contar_reunioes_comissoes,
    detalhar_deputado_alesp,
    foto_deputado_alesp,
    listar_deputados_alesp,
    nomes_comissoes,
)
from collectors.camara_sp_collector import (
    buscar_gastos_gabinete as buscar_gastos_vereador,
    buscar_projetos_vereador,
    buscar_votacoes_vereador,
    detalhar_vereador,
    foto_vereador,
    listar_vereadores_atuais,
    mapa_fotos_vereadores,
    partido_atual_vereador,
    resumir_gastos_gabinete as resumir_gastos_vereador,
    resumir_presenca_vereador,
)

UFS = ["Todos", "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
       "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO",
       "RR", "RS", "SC", "SE", "SP", "TO"]

# 5 últimas legislaturas federais (eleição -> mandato de 4 anos)
MANDATOS = {
    "2023–2026 (mandato atual, eleição de 2022)": (2023, 2026),
    "2019–2022 (eleição de 2018)": (2019, 2022),
    "2015–2018 (eleição de 2014)": (2015, 2018),
    "2011–2014 (eleição de 2010)": (2011, 2014),
    "2007–2010 (eleição de 2006)": (2007, 2010),
}

ANO_ATUAL = date.today().year

# Legislaturas MUNICIPAIS (Câmara de vereadores) — ciclo eleitoral próprio,
# diferente do federal/estadual. Eleições em 2016, 2020, 2024...; posse em
# janeiro do ano seguinte. A atual é a 19ª legislatura (2025–2028).
MANDATOS_MUNICIPAIS = {
    "2025–2028 (mandato atual, eleição de 2024)": (2025, 2028),
    "2021–2024 (eleição de 2020)": (2021, 2024),
    "2017–2020 (eleição de 2016)": (2017, 2020),
}

# O que significa cada sigla de proposição (Câmara e Senado), para o eleitor
# não precisar decifrar códigos. Fonte: glossários oficiais das casas.
TIPOS_PROPOSICAO = {
    "PL": "Projeto de Lei",
    "PLP": "Projeto de Lei Complementar",
    "PEC": "Proposta de Emenda à Constituição",
    "PDL": "Projeto de Decreto Legislativo",
    "PRC": "Projeto de Resolução",
    "PRS": "Projeto de Resolução do Senado",
    "MPV": "Medida Provisória",
    "REQ": "Requerimento (pedido formal: audiência, urgência, homenagem etc.)",
    "RIC": "Pedido de informação a ministros e órgãos do governo",
    "RCP": "Requerimento de criação de CPI",
    "INC": "Indicação (sugestão de providência a outro Poder)",
    "EMP": "Emenda de Plenário (mudança em projeto em votação)",
    "EMC": "Emenda apresentada em Comissão",
    "EMR": "Emenda de Relator",
    "ESB": "Emenda ao Substitutivo",
    "SBT": "Substitutivo (nova versão de um projeto)",
    "PRL": "Parecer do Relator",
    "PAR": "Parecer de Comissão",
    "VTS": "Voto em Separado (posição divergente do relator)",
    "DTQ": "Destaque (votação separada de um trecho)",
    "REC": "Recurso contra decisão",
    "PFC": "Proposta de Fiscalização e Controle",
    "SIT": "Sugestão de Iniciativa Popular",
    "TVR": "Ato de concessão de rádio/TV para análise",
    "MSC": "Mensagem do Poder Executivo",
    "OF": "Ofício (comunicação formal)",
}


def _descrever_sigla(sigla: str) -> str:
    return TIPOS_PROPOSICAO.get(str(sigla).strip().upper(), "Outros documentos do processo legislativo")

st.set_page_config(page_title="Radar do Eleitor", page_icon="🔎", layout="wide")


def _sem_acento(texto: str) -> str:
    texto = str(texto or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _moeda(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _inteiro_br(valor) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _formatar_moeda_df(df: pd.DataFrame, colunas: list) -> pd.DataFrame:
    """Converte colunas numéricas para texto em moeda (R$ 200.000,00)."""
    df = df.copy()
    for c in colunas:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).map(_moeda)
    return df


def _fig_barras(df, x, y, titulo, moeda=False, horizontal=False, altura=320):
    """Gráfico de barras acessível: valor escrito em cada barra (sem depender
    de passar o cursor) e eixo monetário em R$. Pensado para todos os públicos."""
    fig = px.bar(df, x=x, y=y, orientation="h" if horizontal else "v", title=titulo)
    col_valor = x if horizontal else y
    if moeda:
        textos = df[col_valor].map(_moeda)
    else:
        textos = df[col_valor].map(_inteiro_br)
    # "auto" = escreve o valor DENTRO da barra quando cabe; se a barra for
    # pequena demais, escreve logo ao lado/acima — nunca cortado.
    fig.update_traces(
        text=textos,
        textposition="auto",
        cliponaxis=False,
        insidetextanchor="middle",
        textfont=dict(size=13),
        insidetextfont=dict(color="white", size=13),
    )
    fig.update_layout(height=altura, margin=dict(l=10, r=110 if horizontal else 10, t=40, b=10),
                      separators=",.", uniformtext_minsize=11, uniformtext_mode="show")
    # Folga no eixo para o rótulo caber ACIMA/AO LADO da barra sem ser cortado
    col_num = pd.to_numeric(df[col_valor], errors="coerce").fillna(0)
    maximo = float(col_num.max()) if len(col_num) else 0.0
    if maximo > 0:
        folga = maximo * (1.35 if horizontal else 1.22)
        if horizontal:
            fig.update_xaxes(range=[0, folga])
        else:
            fig.update_yaxes(range=[0, folga])
    if moeda:
        if horizontal:
            fig.update_xaxes(tickprefix="R$ ")
        else:
            fig.update_yaxes(tickprefix="R$ ")
    if not horizontal:
        fig.update_xaxes(dtick=1)
    return fig


def _anos_do_mandato(inicio: int, fim: int) -> list:
    """Anos do mandato que já começaram (não consulta anos futuros)."""
    return [a for a in range(inicio, fim + 1) if a <= ANO_ATUAL]


# ----------------------------------------------------------------------
# Cache das consultas às APIs oficiais (agregação por mandato)
# ----------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def _todos_deputados() -> pd.DataFrame:
    return listar_deputados()


@st.cache_data(ttl=3600, show_spinner=False)
def _todos_senadores() -> pd.DataFrame:
    return listar_senadores()


@st.cache_data(ttl=3600, show_spinner=False)
def _todos_dep_alesp() -> pd.DataFrame:
    df = listar_deputados_alesp()
    if df.empty:
        return df
    df = df.rename(columns={"NomeParlamentar": "nome", "Partido": "partido"})
    df["uf"] = "SP"
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def _todos_vereadores_sp() -> pd.DataFrame:
    df = listar_vereadores_atuais()
    if df.empty:
        return df
    df["uf"] = "SP"
    df["partido"] = ""
    return df


@st.cache_data(ttl=86400, show_spinner=False)
def _projetos_vereador(nome: str) -> dict:
    return buscar_projetos_vereador(nome)


@st.cache_data(ttl=86400, show_spinner=False)
def _gastos_vereador_ano(nome: str, ano: int) -> pd.DataFrame:
    return buscar_gastos_vereador(nome, ano)


@st.cache_data(ttl=86400, show_spinner=False)
def _votacoes_vereador_ano(nome: str, ano: int) -> pd.DataFrame:
    return buscar_votacoes_vereador(nome, ano)


@st.cache_data(ttl=86400, show_spinner=False)
def _gastos_vereador_mandato(nome: str, inicio: int, fim: int) -> pd.DataFrame:
    partes = []
    for ano in _anos_do_mandato(inicio, fim):
        df = buscar_gastos_vereador(nome, ano)
        if not df.empty:
            df["ANO"] = ano
            partes.append(df)
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


@st.cache_data(ttl=86400, show_spinner=False)
def _presenca_vereador_mandato(nome: str, inicio: int, fim: int) -> dict:
    total, pres = 0, 0
    for ano in _anos_do_mandato(inicio, fim):
        r = resumir_presenca_vereador(nome, ano)
        total += r.get("total_sessoes", 0)
        pres += r.get("presencas", 0)
    pct = round(pres / total * 100, 1) if total else None
    return {"total_sessoes": total, "presencas": pres, "percentual": pct}


@st.cache_data(ttl=86400, show_spinner=False)
def _votacoes_vereador_mandato(nome: str, inicio: int, fim: int) -> pd.DataFrame:
    partes = []
    for ano in _anos_do_mandato(inicio, fim):
        df = buscar_votacoes_vereador(nome, ano)
        if not df.empty:
            df["ano"] = ano
            partes.append(df)
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


@st.cache_data(ttl=86400, show_spinner=False)
def _partido_vereador(nome: str, ano: int) -> str:
    return partido_atual_vereador(nome, ano)


@st.cache_data(ttl=86400, show_spinner=False)
def _foto_alesp(matricula: str) -> str:
    return foto_deputado_alesp(matricula)


@st.cache_data(ttl=86400, show_spinner=False)
def _mapa_fotos_vereadores() -> dict:
    return mapa_fotos_vereadores()


@st.cache_data(ttl=86400, show_spinner=False)
def _despesas_alesp_mandato(matricula: str, inicio: int, fim: int) -> pd.DataFrame:
    return buscar_despesas_gabinete(matricula, _anos_do_mandato(inicio, fim))


@st.cache_data(ttl=86400, show_spinner=False)
def _presencas_alesp_mandato(id_deputado: str, inicio: int, fim: int,
                             id_spl: str = None, nome: str = None) -> pd.DataFrame:
    return buscar_presencas_comissoes(
        id_deputado, inicio, min(fim, ANO_ATUAL), id_spl=id_spl, nome=nome
    )


@st.cache_data(ttl=3600, show_spinner=False)
def _detalhes_dep(id_camara: int) -> dict:
    return detalhar_deputado(id_camara)


@st.cache_data(ttl=3600, show_spinner=False)
def _detalhes_sen(codigo: int) -> dict:
    return detalhar_senador(codigo)


@st.cache_data(ttl=86400, show_spinner=False)
def _ceap_mandato(id_camara: int, inicio: int, fim: int) -> pd.DataFrame:
    partes = []
    for ano in _anos_do_mandato(inicio, fim):
        try:
            df = buscar_despesas_ceap(id_camara, ano)
            if not df.empty:
                partes.append(df)
        except Exception:
            continue
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


@st.cache_data(ttl=86400, show_spinner=False)
def _eventos_mandato(id_camara: int, inicio: int, fim: int) -> pd.DataFrame:
    partes = []
    for ano in _anos_do_mandato(inicio, fim):
        try:
            df = buscar_eventos_participados(id_camara, f"{ano}-01-01", f"{ano}-12-31")
            if not df.empty:
                partes.append(df)
        except Exception:
            continue
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


@st.cache_data(ttl=86400, show_spinner=False)
def _discursos_mandato(id_camara: int, inicio: int, fim: int) -> pd.DataFrame:
    partes = []
    for ano in _anos_do_mandato(inicio, fim):
        try:
            df = buscar_discursos(id_camara, f"{ano}-01-01", f"{ano}-12-31")
            if not df.empty:
                partes.append(df)
        except Exception:
            continue
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


@st.cache_data(ttl=86400, show_spinner=False)
def _proposicoes_mandato(id_camara: int, inicio: int, fim: int) -> pd.DataFrame:
    partes = []
    for ano in _anos_do_mandato(inicio, fim):
        try:
            df = buscar_proposicoes_autoria(id_camara, ano)
            if not df.empty:
                df["ano_consulta"] = ano
                partes.append(df)
        except Exception:
            continue
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


# Dados históricos (votações, gastos e emendas de anos passados não mudam):
# cache de 24h, compartilhado entre todos os visitantes do app.
@st.cache_data(ttl=86400, show_spinner=False)
def _como_votou_camara(id_camara: int, ano: int) -> pd.DataFrame:
    return montar_como_votou(id_camara, ano, limite=10)


@st.cache_data(ttl=86400, show_spinner=False)
def _total_sessoes_camara(inicio: int, fim: int) -> int:
    return contar_sessoes_deliberativas_total(inicio, min(fim, ANO_ATUAL))


@st.cache_data(ttl=86400, show_spinner=False)
def _total_reunioes_alesp(siglas: tuple, inicio: int, fim: int) -> int:
    return contar_reunioes_comissoes(list(siglas), inicio, min(fim, ANO_ATUAL))


@st.cache_data(ttl=86400, show_spinner=False)
def _votacoes_senado_mandato(codigo: int, inicio: int, fim: int) -> pd.DataFrame:
    return buscar_votacoes_senador(codigo, inicio, ano_fim=fim)


@st.cache_data(ttl=86400, show_spinner=False)
def _autorias_senado_mandato(codigo: int, inicio: int, fim: int) -> pd.DataFrame:
    partes = []
    for ano in _anos_do_mandato(inicio, fim):
        try:
            df = buscar_autorias_senador(codigo, ano)
            if not df.empty:
                df["ano_consulta"] = ano
                partes.append(df)
        except Exception:
            continue
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


@st.cache_data(ttl=86400, show_spinner=False)
def _ceaps_senado_mandato(nome: str, inicio: int, fim: int) -> pd.DataFrame:
    partes = []
    for ano in _anos_do_mandato(inicio, fim):
        try:
            df = buscar_despesas_ceaps(nome, ano)
            if not df.empty:
                partes.append(df)
        except Exception:
            continue
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


@st.cache_data(ttl=86400, show_spinner=False)
def _emendas_sp_mandato(nome_autor: str, inicio: int, fim: int) -> pd.DataFrame:
    return buscar_emendas_estaduais_por_autor(nome_autor, _anos_do_mandato(inicio, fim))


@st.cache_data(ttl=86400, show_spinner=False)
def _emendas_mandato(nome_parlamentar: str, inicio: int, fim: int) -> pd.DataFrame:
    partes = []
    for ano in _anos_do_mandato(inicio, fim):
        try:
            df = buscar_emendas_portal_transparencia(autor=nome_parlamentar.upper(), ano=ano)
            if df is not None and not df.empty:
                partes.append(df)
        except Exception:
            continue
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


@st.cache_data(ttl=86400, show_spinner=False)
def _obras_do_municipio(municipio: str) -> pd.DataFrame:
    return buscar_obras_por_municipio(municipio)


@st.cache_data(ttl=86400, show_spinner=False)
def _emendas_sp_do_municipio(municipio: str, ano: int) -> pd.DataFrame:
    # O filtro do Portal SP exige o nome EXATO em maiúsculas com acento.
    nome_oficial = normalizar_nome_municipio(municipio)
    try:
        return baixar_emendas_sp_csv(localizacao_gasto=nome_oficial, ano_referencia=str(ano))
    except Exception:
        return pd.DataFrame()


# ----------------------------------------------------------------------
# Cabeçalho e seletor de modo
# ----------------------------------------------------------------------

# Evita que o tradutor automático do navegador reescreva os textos do painel
# (ele transforma "mandato a mandato" em "manda a manda", "Cargo" em "Carga" etc.)
st.markdown('<meta name="google" content="notranslate">', unsafe_allow_html=True)

st.title("🔎 Radar do Eleitor")
st.markdown(
    "**Conheça o trabalho de quem você elegeu e o que acontece na sua cidade.** "
    "Todos os dados vêm de fontes oficiais do governo, com link para conferência. "
    "Este painel informa; a escolha é sua."
)

modo = st.radio(
    "O que você quer ver?",
    ["👤 O trabalho de um parlamentar", "🏗️ Obras no seu município (SP)"],
    horizontal=True,
)

# ======================================================================
# MODO OBRAS — seção independente de parlamentar (Estado de São Paulo)
# ======================================================================
if modo.startswith("🏗️"):
    st.divider()
    st.header("🏗️ Obras no seu município")
    st.markdown(
        "Veja as obras do Governo do Estado de São Paulo (rodovias, pontes e "
        "infraestrutura do DER) que passam pela sua cidade, e as emendas "
        "estaduais destinadas ao mesmo município. **São coisas diferentes:** a "
        "obra é executada pelo Estado; a emenda é uma verba que um deputado "
        "direciona. Aqui você vê os dois lado a lado, para tirar suas conclusões."
    )

    with st.form("form_obras"):
        col_m, col_a = st.columns([3, 1])
        with col_m:
            municipio_obras = st.text_input(
                "Digite o nome do município",
                placeholder="Ex.: Marília, Bauru, São José do Rio Preto...",
            )
        with col_a:
            anos_emenda = [a for a in range(ANO_ATUAL, 2021, -1)]
            ano_obras = st.selectbox("Ano das emendas", anos_emenda)
        buscar_obras = st.form_submit_button("🔍 Consultar")

    if not buscar_obras or not (municipio_obras and municipio_obras.strip()):
        st.info("👆 Digite o nome da sua cidade e clique em **Consultar**.")
        st.stop()

    with st.spinner(f"Buscando obras estaduais em {municipio_obras}..."):
        df_obras = _obras_do_municipio(municipio_obras)

    st.subheader(f"🚧 Obras do Estado em {municipio_obras.title()}")
    if df_obras is None or df_obras.empty:
        st.info(
            f"Nenhuma obra do DER encontrada com o município **{municipio_obras}**. "
            "A base atual cobre obras rodoviárias e de infraestrutura do "
            "Departamento de Estradas de Rodagem (DER/SP)."
        )
    else:
        o1, o2, o3 = st.columns(3)
        o1.metric("Obras encontradas", len(df_obras))
        o2.metric("Investimento total", _moeda(float(df_obras.get("valor", pd.Series(dtype=float)).sum())))
        concluidas = int(df_obras["status"].astype(str).str.contains("conclu|entreg", case=False, na=False).sum()) if "status" in df_obras.columns else 0
        o3.metric("Já concluídas", concluidas)

        if "categoria" in df_obras.columns and "valor" in df_obras.columns:
            df_cat = df_obras.groupby("categoria")["valor"].sum().sort_values(ascending=True).reset_index()
            df_cat.columns = ["Categoria", "Investimento (R$)"]
            st.plotly_chart(_fig_barras(df_cat.tail(10), "Investimento (R$)", "Categoria",
                                        "Investimento por tipo de obra", moeda=True, horizontal=True),
                            use_container_width=True)

        with st.expander("📋 Ver todas as obras (descrição, status e valor)"):
            cols_obra = {
                "obra": "Obra", "categoria": "Categoria", "status": "Status",
                "valor": "Valor (R$)", "regiao": "Região", "data_entrega": "Entrega",
            }
            df_ob = df_obras[[c for c in cols_obra if c in df_obras.columns]].rename(columns=cols_obra)
            df_ob = _formatar_moeda_df(df_ob, ["Valor (R$)"])
            st.dataframe(df_ob, hide_index=True, use_container_width=True)

    st.caption(
        "Fonte: [Dados Abertos do Estado de SP — Obras DER/SP]"
        "(https://dadosabertos.sp.gov.br/dataset/obras-der-sp)."
    )

    # Emendas estaduais destinadas ao mesmo município (contexto, não vínculo)
    st.divider()
    st.subheader(f"💰 Emendas estaduais para {municipio_obras.title()} em {ano_obras}")
    with st.spinner("Consultando emendas estaduais do município..."):
        df_em_muni = _emendas_sp_do_municipio(municipio_obras, ano_obras)

    if df_em_muni is None or df_em_muni.empty:
        st.info(
            f"Nenhuma emenda estadual encontrada para {municipio_obras} em {ano_obras}."
        )
    else:
        em1, em2 = st.columns(2)
        em1.metric("Emendas para o município", len(df_em_muni))
        em2.metric("Valor destinado", _moeda(float(df_em_muni.get("VALOR EMPENHADO", pd.Series(dtype=float)).sum())))
        with st.expander("📋 Ver as emendas do município (autor, área e beneficiário)"):
            cols_em = {
                "AUTORIA": "Autor(a)", "PARTIDO POLITICO": "Partido",
                "BENEFICIARIO": "Beneficiário", "OBJETO": "Objeto",
                "VALOR EMPENHADO": "Destinado (R$)", "VALOR PAGO": "Pago (R$)",
            }
            df_em_ex = df_em_muni[[c for c in cols_em if c in df_em_muni.columns]].rename(columns=cols_em)
            df_em_ex = _formatar_moeda_df(df_em_ex, ["Destinado (R$)", "Pago (R$)"])
            st.dataframe(df_em_ex, hide_index=True, use_container_width=True)

    st.info(
        "ℹ️ **Como ler isto:** obras e emendas aparecem juntas por serem do mesmo "
        "município, mas não são necessariamente ligadas — uma emenda pode financiar "
        "uma obra que não é do DER, e uma obra do DER pode não vir de emenda. "
        "Este painel mostra o contexto; o vínculo direto exige conferir os documentos "
        "oficiais de cada uma."
    )
    st.caption(
        "Fonte das emendas: [Portal da Transparência do Estado de SP]"
        "(https://www.transparencia.sp.gov.br/EmendasParlamentares/Realizadas)."
    )
    st.stop()

# ======================================================================
# MODO PARLAMENTAR (fluxo original)
# ======================================================================

# O rádio de TIPO fica FORA do formulário: ao trocar o tipo, a página recarrega
# e o seletor de mandato passa a mostrar as legislaturas certas (a Câmara
# Municipal tem ciclo próprio, diferente do federal/estadual).
casa = st.radio(
    "Quem você quer conhecer?",
    ["Deputado(a) federal", "Senador(a)", "Deputado(a) estadual (SP)",
     "Vereador(a) — São Paulo"],
    horizontal=True,
)
# Cada tipo tem seu próprio conjunto de legislaturas.
mandatos_do_tipo = MANDATOS_MUNICIPAIS if casa == "Vereador(a) — São Paulo" else MANDATOS

# O resto da busca fica em FORMULÁRIO: nada recarrega enquanto a pessoa digita
# ou troca de mandato — só ao clicar em Consultar.
with st.form("form_busca"):
    col_busca, col_uf, col_mandato = st.columns([2.2, 0.7, 1.8])
    with col_busca:
        termo = st.text_input(
            "Digite o nome (ou parte dele)",
            placeholder="Ex.: Maria, Tiririca, Silva...",
            help="Busca sem diferença de acento ou maiúscula.",
        )
    with col_uf:
        uf_filtro = st.selectbox("Estado", UFS, disabled=(casa == "Vereador(a) — São Paulo"))
    with col_mandato:
        mandato_rotulo = st.selectbox("Mandato (legislatura)", list(mandatos_do_tipo.keys()))
    consultar = st.form_submit_button("🔍 Consultar")

if consultar:
    st.session_state["filtros_busca"] = {
        "casa": casa, "termo": termo, "uf": uf_filtro, "mandato": mandato_rotulo,
    }

filtros_busca = st.session_state.get("filtros_busca")
if not filtros_busca:
    st.info("👆 Escolha quem você quer conhecer, digite um nome se quiser, e clique em **Consultar**.")
    st.stop()

casa = filtros_busca["casa"]
termo = filtros_busca["termo"]
uf_filtro = filtros_busca["uf"]
mandato_rotulo = filtros_busca["mandato"]

eh_camara = casa == "Deputado(a) federal"
eh_senado = casa == "Senador(a)"
eh_alesp = casa == "Deputado(a) estadual (SP)"
eh_vereador = casa == "Vereador(a) — São Paulo"

# O mandato pertence ao conjunto do tipo escolhido (municipal para vereador).
_dict_mandato = MANDATOS_MUNICIPAIS if eh_vereador else MANDATOS
ano_ini, ano_fim = _dict_mandato.get(mandato_rotulo, next(iter(_dict_mandato.values())))
periodo_curto = f"{ano_ini}–{ano_fim}"

st.caption(
    "ℹ️ A lista abaixo traz quem está **em exercício hoje**. Ao escolher um mandato "
    "anterior, você vê o que esse mesmo parlamentar fez naquele período (se já era "
    "parlamentar na época). Senadores têm mandato de 8 anos. Para vereadores, os "
    "dados são da Câmara Municipal de São Paulo."
)

with st.spinner("Carregando parlamentares em exercício..."):
    if eh_camara:
        df_parls = _todos_deputados()
    elif eh_senado:
        df_parls = _todos_senadores()
    elif eh_alesp:
        df_parls = _todos_dep_alesp()
    else:
        df_parls = _todos_vereadores_sp()

if df_parls.empty:
    st.error("Não foi possível carregar a lista na API oficial. Tente novamente em instantes.")
    st.stop()

col_nome = "nome"
df_filtro = df_parls.copy()
if uf_filtro != "Todos" and "siglaUf" in df_filtro.columns:
    df_filtro = df_filtro[df_filtro["siglaUf"] == uf_filtro]
if uf_filtro != "Todos" and "uf" in df_filtro.columns:
    df_filtro = df_filtro[df_filtro["uf"] == uf_filtro]

if termo and termo.strip():
    alvo = _sem_acento(termo)
    df_filtro = df_filtro[df_filtro[col_nome].map(_sem_acento).str.contains(alvo, na=False)]

if df_filtro.empty:
    st.warning(
        "Nenhum parlamentar em exercício encontrado com esse nome. "
        "Dica: tente só o primeiro nome, ou mude o estado para 'Todos'."
    )
    st.stop()

partido_col = "siglaPartido" if "siglaPartido" in df_filtro.columns else "partido"
uf_col = "siglaUf" if "siglaUf" in df_filtro.columns else "uf"
df_filtro = df_filtro.sort_values(col_nome)
rotulos = [
    f"{linha[col_nome]} ({linha.get(partido_col) or '—'}/{linha.get(uf_col) or '—'})"
    for _, linha in df_filtro.iterrows()
]
# Chave estável por casa legislativa + saneamento do estado: sem isso, o
# Streamlit pode reaproveitar a seleção antiga quando a lista de opções muda
# (sintoma: dados novos com nome/foto do parlamentar anterior).
chave_seletor = f"sel_parlamentar_{'camara' if eh_camara else 'senado' if eh_senado else 'alesp' if eh_alesp else 'vereador'}"
if st.session_state.get(chave_seletor) not in rotulos:
    st.session_state.pop(chave_seletor, None)

st.caption(f"{len(rotulos)} resultado(s) em exercício")
escolhido = st.selectbox("Escolha o(a) parlamentar:", rotulos, key=chave_seletor)
linha_parl = df_filtro.iloc[rotulos.index(escolhido)]

# ----------------------------------------------------------------------
# Perfil
# ----------------------------------------------------------------------

if eh_camara:
    id_parl = int(linha_parl["id"])
    with st.spinner("Buscando dados oficiais..."):
        detalhes = _detalhes_dep(id_parl)
elif eh_senado:
    id_parl = int(linha_parl["codigo"])
    with st.spinner("Buscando dados oficiais..."):
        detalhes = _detalhes_sen(id_parl)
elif eh_alesp:
    detalhes = detalhar_deputado_alesp(linha_parl.to_dict())
    if not detalhes.get("url_foto"):
        with st.spinner("Carregando a foto..."):
            detalhes["url_foto"] = _foto_alesp(detalhes.get("matricula"))
    id_parl = detalhes["id_alesp"]
else:
    detalhes = detalhar_vereador(linha_parl[col_nome], linha_parl.get("chave"))
    with st.spinner("Identificando o partido e a foto..."):
        detalhes["partido"] = _partido_vereador(linha_parl[col_nome], min(ano_fim, ANO_ATUAL)) or "—"
        detalhes["url_foto"] = foto_vereador(linha_parl[col_nome], _mapa_fotos_vereadores())
    id_parl = linha_parl.get("chave")

# Avatar neutro (SVG embutido) para quando a fonte não fornece foto,
# evitando espaço vazio no perfil.
_AVATAR_NEUTRO = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'>"
    "<rect width='120' height='120' rx='8' fill='%23e9edf3'/>"
    "<circle cx='60' cy='46' r='24' fill='%23b6c2d1'/>"
    "<path d='M20 108c0-22 18-34 40-34s40 12 40 34z' fill='%23b6c2d1'/></svg>"
)

st.divider()
col_foto, col_info = st.columns([1, 5])
with col_foto:
    st.image(detalhes.get("url_foto") or _AVATAR_NEUTRO, width=120)
with col_info:
    st.subheader(detalhes.get("nome_parlamentar") or linha_parl[col_nome])
    situacao = detalhes.get("situacao") or ("Em exercício" if not eh_camara else "—")
    st.markdown(
        f"**Partido:** {detalhes.get('partido')} • **Estado:** {detalhes.get('uf')} • "
        f"**Situação do mandato:** {situacao}"
    )
    if (eh_camara or eh_alesp) and str(situacao).lower() not in ("exercício", "em exercício"):
        st.info(
            f"ℹ️ Situação **{situacao}**: o parlamentar não está atuando normalmente "
            "no momento (pode estar de licença ou ter assumido outro cargo)."
        )
    if eh_alesp and detalhes.get("base_eleitoral"):
        st.markdown(f"**Base eleitoral declarada:** {detalhes['base_eleitoral'][:300]}")
    if eh_alesp and detalhes.get("areas_atuacao"):
        st.markdown(f"**Áreas de atuação declaradas:** {detalhes['areas_atuacao'][:300]}")
    st.markdown(f"[📄 Página oficial]({detalhes.get('link_fonte')})")

# ======================================================================
# BLOCO VEREADOR (CMSP) — autocontido; encerra antes do fluxo de deputado
# ======================================================================
if eh_vereador:
    nome_ver = linha_parl[col_nome]

    st.divider()
    st.header("📋 Produção legislativa")
    with st.spinner("Consultando o processo legislativo da Câmara Municipal..."):
        proj = _projetos_vereador(nome_ver)
    df_tram = proj.get("em_tramitacao", pd.DataFrame())
    df_leis = proj.get("leis_aprovadas", pd.DataFrame())

    v1, v2 = st.columns(2)
    v1.metric("Projetos e proposituras em tramitação", len(df_tram))
    v2.metric("Leis já aprovadas (de autoria)", len(df_leis))
    st.caption(
        "Em tramitação estão propostas ainda em análise (projetos de lei, "
        "requerimentos, indicações, moções etc.); leis aprovadas já produziram "
        "efeito. Quantidade não é qualidade — vale abrir e ler o conteúdo."
    )

    # Separa a produção por tipo de propositura (PL, requerimento, indicação, moção...)
    if not df_tram.empty and "tipo" in df_tram.columns:
        por_tipo = df_tram["tipo"].value_counts().reset_index()
        por_tipo.columns = ["Sigla", "Quantidade"]
        por_tipo.insert(1, "O que é", por_tipo["Sigla"].map(_descrever_sigla))
        with st.expander("📚 Ver a produção por tipo"):
            st.dataframe(por_tipo[["Sigla", "O que é", "Quantidade"]],
                         hide_index=True, use_container_width=True)

    if not df_tram.empty:
        with st.expander("📄 Ver proposituras em tramitação"):
            cols = {"tipo": "Tipo", "numero": "Número", "ano": "Ano"}
            st.dataframe(df_tram[[c for c in cols if c in df_tram.columns]].rename(columns=cols),
                         hide_index=True, use_container_width=True)
    if not df_leis.empty:
        with st.expander("✅ Ver leis aprovadas de autoria"):
            cols = {"numero": "Lei nº", "publicacao": "Publicação", "projeto": "Projeto de origem"}
            st.dataframe(df_leis[[c for c in cols if c in df_leis.columns]].rename(columns=cols),
                         hide_index=True, use_container_width=True)

    st.caption(
        "Fonte: [SPLEGIS — Câmara Municipal de São Paulo]"
        "(https://www.saopaulo.sp.leg.br/transparencia/dados-abertos/). "
        "Projetos e leis são o acumulado do mandato."
    )

    # Presença nas sessões plenárias (item de assiduidade)
    st.divider()
    st.header(f"🪑 Presença nas sessões no mandato {periodo_curto}")
    with st.spinner(f"Consultando a presença nas sessões ({periodo_curto})..."):
        pres = _presenca_vereador_mandato(nome_ver, ano_ini, ano_fim)
    if pres.get("total_sessoes"):
        p1, p2 = st.columns(2)
        p1.metric(
            "Sessões que participou",
            f"{pres['presencas']} de {pres['total_sessoes']}",
        )
        p2.metric("Frequência", f"{pres['percentual']}%" if pres["percentual"] is not None else "—")
        st.caption(
            "Presença nas sessões plenárias ordinárias e extraordinárias, segundo o "
            "registro oficial da Câmara Municipal. O recesso parlamentar (períodos "
            "sem sessões) não conta como falta."
        )
    else:
        st.info("Ainda não há registro de presença para o período selecionado.")
    st.caption(
        "Fonte: registro de presença em plenário da Câmara Municipal de São Paulo "
        "(dados abertos)."
    )

    # Como votou (votações nominais do plenário, no mandato)
    st.divider()
    st.header(f"🗳️ Como votou no mandato {periodo_curto}")
    st.markdown(
        "As **votações nominais** são aquelas em que fica registrado o voto de cada "
        "vereador, um a um. É o retrato mais direto das posições de quem te representa."
    )
    with st.spinner(f"Consultando as votações do plenário ({periodo_curto})... na primeira vez pode demorar."):
        df_vot = _votacoes_vereador_mandato(nome_ver, ano_ini, ano_fim)
    if df_vot is None or df_vot.empty:
        st.info(
            "Nenhuma votação nominal encontrada para este vereador no período. "
            "Muitas decisões são por votação simbólica, que não registra voto individual."
        )
    else:
        vv1, vv2, vv3 = st.columns(3)
        vv1.metric("Votações nominais registradas", len(df_vot))
        vv2.metric("Votou 'Sim'", int((df_vot["voto"].str.strip().str.lower() == "sim").sum()))
        vv3.metric("Votou 'Não'", int((df_vot["voto"].str.strip().str.lower().isin(["nao", "não"])).sum()))
        with st.expander("📄 Ver cada votação e o voto"):
            cols = {"data": "Data", "materia": "O que foi votado",
                    "voto": "Voto", "resultado": "Resultado"}
            st.dataframe(df_vot[[c for c in cols if c in df_vot.columns]].rename(columns=cols),
                         hide_index=True, use_container_width=True)
        st.caption(
            "Fonte: sistema de votações da Câmara Municipal de São Paulo (dados abertos)."
        )

    st.divider()
    st.header(f"💰 Verba de gabinete no mandato {periodo_curto}")
    st.markdown(
        "Todo vereador tem uma verba pública para custear o mandato (o chamado "
        "'auxílio-encargos gerais de gabinete'). **Não é salário.** Cada despesa "
        "abaixo tem fornecedor e valor registrados no sistema oficial de custos."
    )
    with st.spinner(f"Consultando os gastos de gabinete ({periodo_curto})..."):
        df_gv = _gastos_vereador_mandato(nome_ver, ano_ini, ano_fim)
    resumo_gv = resumir_gastos_vereador(df_gv)

    st.metric("Total gasto no mandato", _moeda(resumo_gv["total"]))
    if df_gv is not None and not df_gv.empty and "ANO" in df_gv.columns:
        df_ano_v = df_gv.groupby("ANO")["VALOR"].sum().reset_index()
        df_ano_v.columns = ["Ano", "Valor (R$)"]
        st.plotly_chart(_fig_barras(df_ano_v, "Ano", "Valor (R$)",
                                    "Gasto ano a ano do mandato", moeda=True),
                        use_container_width=True)
    if resumo_gv["por_tipo"]:
        df_tp = pd.DataFrame(list(resumo_gv["por_tipo"].items()), columns=["Tipo de gasto", "Valor (R$)"])
        df_tp = df_tp.sort_values("Valor (R$)")
        st.plotly_chart(_fig_barras(df_tp.tail(10), "Valor (R$)", "Tipo de gasto",
                                    "Em que o dinheiro foi usado (total do mandato)",
                                    moeda=True, horizontal=True),
                        use_container_width=True)
    if df_gv is not None and not df_gv.empty:
        with st.expander("🧾 Ver cada despesa em detalhe"):
            cols = {"ANO": "Ano", "MES": "Mês", "DESPESA": "Tipo", "FORNECEDOR": "Fornecedor",
                    "CNPJ": "CNPJ", "VALOR": "Valor (R$)"}
            df_d = df_gv[[c for c in cols if c in df_gv.columns]].rename(columns=cols)
            df_d = _formatar_moeda_df(df_d, ["Valor (R$)"])
            st.dataframe(df_d, hide_index=True, use_container_width=True)
    st.caption(
        "Fonte: [SisGV — Sistema de Custos de Mandato da CMSP]"
        "(https://www.saopaulo.sp.leg.br/transparencia/dados-abertos/)."
    )

    st.info(
        "ℹ️ Vereadores **não têm emendas parlamentares** como deputados e senadores — "
        "eles atuam pelo orçamento municipal por outros instrumentos."
    )
    st.divider()
    st.markdown(
        "##### ℹ️ Sobre este painel\n"
        "Dados oficiais da Câmara Municipal de São Paulo (SPLEGIS e SisGV). Este "
        "painel **não faz ranking, nota ou recomendação de voto** (Resolução TSE "
        "nº 23.755/2026). Quantidade não mede qualidade."
    )
    st.stop()

# ----------------------------------------------------------------------
# Trabalho no plenário (mandato)
# ----------------------------------------------------------------------

st.divider()
st.header(f"📋 O trabalho no plenário no mandato {periodo_curto}")

if eh_camara:
    with st.spinner(f"Consultando a Câmara ano a ano ({periodo_curto})... na primeira vez pode demorar."):
        df_eventos = _eventos_mandato(id_parl, ano_ini, ano_fim)
        df_discursos = _discursos_mandato(id_parl, ano_ini, ano_fim)
        df_props = _proposicoes_mandato(id_parl, ano_ini, ano_fim)

    sessoes = contar_sessoes_deliberativas(df_eventos)
    with st.spinner("Contando o total de sessões do plenário no período..."):
        total_sessoes = _total_sessoes_camara(ano_ini, ano_fim)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Sessões de votação que participou",
        f"{sessoes} de {total_sessoes}" if total_sessoes else sessoes,
        help="Total de sessões deliberativas realizadas pelo plenário no período, "
             "segundo a API oficial da Câmara.",
    )
    c2.metric("Eventos e reuniões no total", len(df_eventos))
    c3.metric("Discursos no plenário", len(df_discursos))
    c4.metric("Projetos e propostas apresentados", len(df_props))

    st.caption(
        "⚠️ A participação em sessões vem dos registros de eventos da API oficial da Câmara. "
        "O boletim oficial de frequência (com faltas justificadas) é publicado separadamente. "
        "Importante: o recesso parlamentar (períodos sem sessões, previstos na Constituição) "
        "não é férias individuais do deputado. Se o parlamentar não era deputado neste "
        "período, os números aparecem zerados."
    )

    if not df_props.empty and "ano_consulta" in df_props.columns:
        por_ano = df_props.groupby("ano_consulta").size().reset_index()
        por_ano.columns = ["Ano", "Projetos apresentados"]
        st.plotly_chart(_fig_barras(por_ano, "Ano", "Projetos apresentados",
                                    "Projetos e propostas, ano a ano do mandato", altura=280),
                        use_container_width=True)

    if not df_props.empty and "siglaTipo" in df_props.columns:
        tipos = df_props["siglaTipo"].value_counts().reset_index()
        tipos.columns = ["Sigla", "Quantidade"]
        tipos.insert(1, "O que é", tipos["Sigla"].map(_descrever_sigla))
        with st.expander("📚 Ver os projetos apresentados por tipo"):
            st.dataframe(tipos[["Sigla", "O que é", "Quantidade"]],
                         hide_index=True, use_container_width=True)
elif eh_alesp:
    with st.spinner(f"Consultando os dados abertos da ALESP ({periodo_curto})... a primeira consulta baixa os arquivos oficiais."):
        df_presencas = _presencas_alesp_mandato(
            id_parl, ano_ini, ano_fim,
            id_spl=detalhes.get("id_spl"),
            nome=detalhes.get("nome_parlamentar"),
        )

    siglas_atuacao = (
        tuple(sorted(df_presencas["SiglaComissao"].dropna().unique()))
        if not df_presencas.empty and "SiglaComissao" in df_presencas.columns else tuple()
    )
    total_reunioes = _total_reunioes_alesp(siglas_atuacao, ano_ini, ano_fim) if siglas_atuacao else 0

    c1, c2 = st.columns(2)
    c1.metric(
        "Presenças em reuniões de comissões",
        f"{len(df_presencas)} de {total_reunioes}" if total_reunioes else len(df_presencas),
        help="O total considera apenas as reuniões encerradas das comissões em que "
             "o deputado atuou no período — ninguém participa de todas as comissões da casa.",
    )
    c2.metric("Comissões diferentes em que atuou", len(siglas_atuacao))

    st.caption(
        "⚠️ A ALESP publica em dados abertos a presença nas **comissões permanentes** "
        "(onde os projetos são analisados antes do plenário). A presença nas sessões "
        "do plenário não está disponível em formato aberto. Projetos de autoria e "
        "votos em comissões serão adicionados em uma próxima fase."
    )

    if not df_presencas.empty and "ano" in df_presencas.columns:
        por_ano = df_presencas.groupby("ano").size().reset_index()
        por_ano.columns = ["Ano", "Presenças"]
        st.plotly_chart(_fig_barras(por_ano, "Ano", "Presenças",
                                    "Presenças em comissões, ano a ano do mandato", altura=280),
                        use_container_width=True)

    if not df_presencas.empty and "SiglaComissao" in df_presencas.columns:
        mapa_nomes = nomes_comissoes()
        por_com = df_presencas["SiglaComissao"].value_counts().reset_index()
        por_com.columns = ["Sigla", "Presenças"]
        por_com.insert(1, "Comissão", por_com["Sigla"].map(
            lambda s: mapa_nomes.get(s, "Comissão não identificada")
        ))
        with st.expander("📚 Ver presenças por comissão"):
            st.dataframe(por_com, hide_index=True, use_container_width=True)
else:
    with st.spinner(f"Consultando o Senado ({periodo_curto})..."):
        df_votacoes_sen = _votacoes_senado_mandato(id_parl, ano_ini, ano_fim)
        df_autorias = _autorias_senado_mandato(id_parl, ano_ini, ano_fim)

    c1, c2 = st.columns(2)
    c1.metric("Votações nominais em que votou", len(df_votacoes_sen))
    c2.metric("Matérias de autoria no mandato", len(df_autorias))

    if not df_autorias.empty and "ano_consulta" in df_autorias.columns:
        por_ano = df_autorias.groupby("ano_consulta").size().reset_index()
        por_ano.columns = ["Ano", "Matérias"]
        st.plotly_chart(_fig_barras(por_ano, "Ano", "Matérias",
                                    "Matérias de autoria, ano a ano do mandato", altura=280),
                        use_container_width=True)

    if not df_autorias.empty and "sigla" in df_autorias.columns:
        tipos = df_autorias["sigla"].value_counts().reset_index()
        tipos.columns = ["Sigla", "Quantidade"]
        tipos.insert(1, "O que é", tipos["Sigla"].map(_descrever_sigla))
        with st.expander("📚 Ver as matérias apresentadas por tipo"):
            st.dataframe(tipos[["Sigla", "O que é", "Quantidade"]],
                         hide_index=True, use_container_width=True)

with st.expander("❓ O que significa cada número?"):
    st.markdown(
        "- **Sessões / votações nominais**: reuniões do plenário em que se discute e "
        "vota. É onde o mandato 'acontece'.\n"
        "- **Projetos, propostas e matérias**: tudo que o parlamentar apresentou — "
        "projetos de lei, emendas, requerimentos. Quantidade não é qualidade: "
        "vale abrir e ler o conteúdo.\n"
        "- **Discursos**: falas registradas em plenário."
    )

# ----------------------------------------------------------------------
# Como ele votou
# ----------------------------------------------------------------------

st.divider()
st.header(f"🗳️ Como votou (mandato {periodo_curto})")
st.markdown(
    "As **votações nominais** são aquelas em que fica registrado o voto de cada "
    "parlamentar, um a um. É o retrato mais direto das posições de quem te representa."
)

if eh_alesp:
    df_votos_alesp = buscar_votos_comissoes(
        id_parl, ano_ini, ano_fim,
        id_spl=detalhes.get("id_spl"),
        nome=detalhes.get("nome_parlamentar"),
    )
    if df_votos_alesp is None:
        st.info(
            "🔜 Os votos nas comissões ainda não foram processados neste servidor. "
            "Rode `python scripts/etl_alesp_votacoes.py` e publique o arquivo gerado "
            "em data/processed para habilitar esta seção."
        )
    elif df_votos_alesp.empty:
        st.info("Nenhum voto em comissões encontrado para este deputado no período.")
    else:
        st.metric("Votos registrados em comissões no mandato", len(df_votos_alesp))
        df_exibir = df_votos_alesp.head(20).copy()
        df_exibir["link"] = df_exibir["id_documento"].map(
            lambda i: f"https://www.al.sp.gov.br/propositura/?id={i}" if str(i).strip() else ""
        )
        # Nome completo da comissão (o eleitor não conhece as siglas)
        if "comissao" in df_exibir.columns and df_exibir["comissao"].astype(str).str.strip().ne("").any():
            df_exibir["nome_comissao"] = df_exibir["comissao"]
        else:
            mapa_nomes_votos = nomes_comissoes()
            df_exibir["nome_comissao"] = df_exibir["sigla_comissao"].map(
                lambda s: mapa_nomes_votos.get(str(s).strip(), str(s))
            )
        df_exibir = df_exibir.rename(columns={
            "data_reuniao": "Data", "nome_comissao": "Comissão",
            "voto": "Voto", "link": "Matéria (fonte)",
        })[["Data", "Comissão", "Voto", "Matéria (fonte)"]]
        st.dataframe(
            df_exibir, hide_index=True, use_container_width=True,
            column_config={"Matéria (fonte)": st.column_config.LinkColumn("Matéria (fonte)", display_text="abrir 🔗")},
        )
        st.caption(
            f"Mostrando os 20 mais recentes de {len(df_votos_alesp)} votos em "
            "comissões permanentes no mandato. São os votos dados na análise das "
            "matérias ANTES do plenário — as votações do plenário da ALESP não "
            "estão disponíveis em dados abertos. Fonte: Dados Abertos ALESP."
        )
elif eh_camara:
    ano_recente = min(ano_fim, ANO_ATUAL)
    with st.spinner("Buscando as votações nominais mais recentes do plenário (pode levar até 1 minuto)..."):
        df_votou = _como_votou_camara(id_parl, ano_recente)
        if df_votou.empty and ano_recente - 1 >= ano_ini:
            df_votou = _como_votou_camara(id_parl, ano_recente - 1)
    if df_votou.empty:
        st.info("Nenhuma votação nominal do plenário encontrada no período.")
    else:
        df_exibir = df_votou.rename(columns={
            "data": "Data", "descricao": "O que foi votado", "voto": "Voto",
            "link_fonte": "Fonte",
        })
        st.dataframe(
            df_exibir, hide_index=True, use_container_width=True,
            column_config={"Fonte": st.column_config.LinkColumn("Fonte", display_text="conferir 🔗")},
        )
        st.caption(
            f"Mostrando as votações nominais mais recentes do plenário ({ano_recente}), "
            "para não deixar a consulta lenta. 'Não registrado' = o voto do deputado "
            "não consta na lista oficial (ausência, licença, obstrução da bancada ou "
            "não participação)."
        )
else:
    if df_votacoes_sen.empty:
        st.info("Nenhuma votação nominal encontrada no período.")
    else:
        df_exibir = df_votacoes_sen.head(20).rename(columns={
            "data": "Data", "materia": "Matéria", "descricao": "O que foi votado", "voto": "Voto",
        })
        st.dataframe(df_exibir, hide_index=True, use_container_width=True)
        st.caption(
            f"Mostrando as 20 mais recentes de {len(df_votacoes_sen)} votações nominais "
            f"do mandato {periodo_curto}. Fonte: API de Dados Abertos do Senado Federal."
        )

# ----------------------------------------------------------------------
# Gastos do mandato
# ----------------------------------------------------------------------

st.divider()
st.header(f"💰 Gastos do mandato {periodo_curto}")
st.markdown(
    "Todo parlamentar tem direito a uma **cota** (CEAP na Câmara, CEAPS no Senado): "
    "um valor mensal público para custear o trabalho — escritório, divulgação, "
    "passagens, combustível. **Não é salário.** Cada gasto tem documento público."
)

if eh_camara:
    with st.spinner(f"Consultando gastos oficiais de {periodo_curto}..."):
        df_gastos = _ceap_mandato(id_parl, ano_ini, ano_fim)
    col_valor, col_tipo, col_ano_g = "valorLiquido", "tipoDespesa", "ano"
elif eh_alesp:
    with st.spinner(f"Consultando a verba de gabinete na ALESP ({periodo_curto})..."):
        df_gastos = _despesas_alesp_mandato(detalhes["matricula"], ano_ini, ano_fim)
    col_valor, col_tipo, col_ano_g = "Valor", "Tipo", "Ano"
else:
    with st.spinner(f"Consultando gastos oficiais de {periodo_curto} (CSVs oficiais do Senado)..."):
        nome_busca = detalhes.get("nome_parlamentar") or linha_parl[col_nome]
        df_gastos = _ceaps_senado_mandato(nome_busca, ano_ini, ano_fim)
    col_valor, col_tipo, col_ano_g = "VALOR_REEMBOLSADO", "TIPO_DESPESA", "ANO"

if df_gastos is None or df_gastos.empty:
    st.metric("Total gasto da cota no mandato", _moeda(0.0))
    st.info(
        "Nenhum gasto de cota encontrado neste período — o parlamentar pode não ter "
        "exercido mandato nessa legislatura, ou os dados do período não estão disponíveis."
    )
else:
    df_gastos[col_valor] = pd.to_numeric(df_gastos[col_valor], errors="coerce").fillna(0.0)
    st.metric("Total gasto da cota no mandato", _moeda(float(df_gastos[col_valor].sum())))

    g1, g2 = st.columns(2)
    with g1:
        if col_ano_g in df_gastos.columns:
            df_ano = df_gastos.groupby(col_ano_g)[col_valor].sum().reset_index()
            df_ano.columns = ["Ano", "Valor (R$)"]
            st.plotly_chart(_fig_barras(df_ano, "Ano", "Valor (R$)",
                                        "Gasto ano a ano do mandato", moeda=True),
                            use_container_width=True)
    with g2:
        if col_tipo in df_gastos.columns:
            df_tipo = df_gastos.groupby(col_tipo)[col_valor].sum().sort_values(ascending=True).reset_index()
            df_tipo.columns = ["Tipo de gasto", "Valor (R$)"]
            st.plotly_chart(_fig_barras(df_tipo.tail(10), "Valor (R$)", "Tipo de gasto",
                                        "Em que o dinheiro foi usado (total do mandato)",
                                        moeda=True, horizontal=True),
                            use_container_width=True)

    with st.expander("🧾 Ver cada gasto em detalhe"):
        if eh_camara:
            colunas_exibir = {
                "ano": "Ano", "mes": "Mês", "tipoDespesa": "Tipo", "nomeFornecedor": "Fornecedor",
                "valorLiquido": "Valor (R$)", "urlDocumento": "Nota fiscal",
            }
            df_notas = df_gastos[[c for c in colunas_exibir if c in df_gastos.columns]].rename(columns=colunas_exibir)
            df_notas = _formatar_moeda_df(df_notas, ["Valor (R$)"])
            st.dataframe(
                df_notas, hide_index=True, use_container_width=True,
                column_config={"Nota fiscal": st.column_config.LinkColumn("Nota fiscal", display_text="abrir 📄")},
            )
        elif eh_alesp:
            colunas_exibir = {
                "Ano": "Ano", "Mes": "Mês", "Tipo": "Tipo", "Fornecedor": "Fornecedor",
                "CNPJ": "CNPJ", "Valor": "Valor (R$)",
            }
            df_notas = df_gastos[[c for c in colunas_exibir if c in df_gastos.columns]].rename(columns=colunas_exibir)
            df_notas = _formatar_moeda_df(df_notas, ["Valor (R$)"])
            st.dataframe(df_notas, hide_index=True, use_container_width=True)
        else:
            colunas_exibir = {
                "ANO": "Ano", "MES": "Mês", "TIPO_DESPESA": "Tipo", "FORNECEDOR": "Fornecedor",
                "DETALHAMENTO": "Detalhe", "VALOR_REEMBOLSADO": "Valor (R$)",
            }
            df_notas = df_gastos[[c for c in colunas_exibir if c in df_gastos.columns]].rename(columns=colunas_exibir)
            df_notas = _formatar_moeda_df(df_notas, ["Valor (R$)"])
            st.dataframe(df_notas, hide_index=True, use_container_width=True)

if eh_camara:
    fonte_gastos = "[API de Dados Abertos da Câmara dos Deputados](https://dadosabertos.camara.leg.br/)"
elif eh_alesp:
    fonte_gastos = "[Dados Abertos da ALESP](https://www.al.sp.gov.br/dados-abertos/) (verba de gabinete, desde 2002)"
else:
    fonte_gastos = "[Transparência do Senado Federal](https://www12.senado.leg.br/transparencia) (CEAPS)"
st.caption(f"Fonte: {fonte_gastos}.")

# ----------------------------------------------------------------------
# Emendas parlamentares (mandato)
# ----------------------------------------------------------------------

st.divider()
st.header(f"🏥 Emendas parlamentares no mandato {periodo_curto}")
st.markdown(
    "**Emendas** são a forma como o parlamentar direciona parte do orçamento da União "
    "para obras e serviços — um hospital, uma escola, uma estrada. "
    "Aqui você vê para onde foi o dinheiro, ano a ano do mandato."
)

nome_para_emendas = detalhes.get("nome_parlamentar") or linha_parl[col_nome]

if eh_alesp:
    df_emendas = pd.DataFrame()
else:
    if not _carregar_token_portal():
        st.warning(
            "⚠️ A chave da API do Portal da Transparência não está configurada neste "
            "servidor, então as emendas não podem ser consultadas. No Streamlit Cloud: "
            "Settings → Secrets → adicionar PORTAL_TRANSPARENCIA_API_KEY."
        )
    with st.spinner(f"Consultando o Portal da Transparência ({periodo_curto})..."):
        df_emendas = _emendas_mandato(nome_para_emendas, ano_ini, ano_fim)

if eh_alesp:
    with st.spinner(f"Consultando emendas estaduais no Portal da Transparência SP ({periodo_curto})..."):
        df_emendas_sp = _emendas_sp_mandato(nome_para_emendas, ano_ini, ano_fim)

    if df_emendas_sp is None or df_emendas_sp.empty:
        st.info(
            f"Nenhuma emenda estadual encontrada para **{nome_para_emendas}** no "
            f"período {periodo_curto}. O portal estadual cobre anos a partir de "
            "2022 (anteriores só em PDF) e considera emendas realizadas/executadas."
        )
    else:
        e1, e2, e3 = st.columns(3)
        e1.metric("Emendas estaduais no mandato", len(df_emendas_sp))
        e2.metric("Valor destinado (empenhado)", _moeda(float(df_emendas_sp.get("VALOR EMPENHADO", pd.Series(dtype=float)).sum())))
        e3.metric("Valor efetivamente pago", _moeda(float(df_emendas_sp.get("VALOR PAGO", pd.Series(dtype=float)).sum())))

        m1, m2 = st.columns(2)
        with m1:
            if "ANO REFERENCIA" in df_emendas_sp.columns:
                df_ano_sp = df_emendas_sp.groupby("ANO REFERENCIA")["VALOR EMPENHADO"].sum().reset_index()
                df_ano_sp.columns = ["Ano", "Valor destinado (R$)"]
                st.plotly_chart(_fig_barras(df_ano_sp, "Ano", "Valor destinado (R$)",
                                            "Emendas estaduais ano a ano", moeda=True),
                                use_container_width=True)
        with m2:
            if "LOCALIZACAO DO GASTO" in df_emendas_sp.columns:
                df_loc = df_emendas_sp.groupby("LOCALIZACAO DO GASTO")["VALOR EMPENHADO"].sum().sort_values(ascending=True).reset_index()
                df_loc.columns = ["Município", "Valor destinado (R$)"]
                st.plotly_chart(_fig_barras(df_loc.tail(10), "Valor destinado (R$)", "Município",
                                            "Municípios que mais receberam",
                                            moeda=True, horizontal=True),
                                use_container_width=True)

        with st.expander("📋 Ver todas as emendas estaduais (beneficiário e objeto)"):
            colunas_sp = {
                "ANO REFERENCIA": "Ano", "BENEFICIARIO": "Beneficiário",
                "OBJETO": "Objeto", "LOCALIZACAO DO GASTO": "Município",
                "TIPO DE EMENDA": "Tipo", "VALOR EMPENHADO": "Destinado (R$)",
                "VALOR PAGO": "Pago (R$)",
            }
            df_exibir_sp = df_emendas_sp[[c for c in colunas_sp if c in df_emendas_sp.columns]].rename(columns=colunas_sp)
            df_exibir_sp = _formatar_moeda_df(df_exibir_sp, ["Destinado (R$)", "Pago (R$)"])
            st.dataframe(df_exibir_sp, hide_index=True, use_container_width=True)

    st.caption(
        "Fonte: [Consulta oficial de Emendas Parlamentares Realizadas — Portal da "
        "Transparência do Estado de SP]"
        "(https://www.transparencia.sp.gov.br/EmendasParlamentares/Realizadas). "
        "Dados estruturados disponíveis a partir de 2022."
    )
elif df_emendas is None or df_emendas.empty:
    st.info(
        f"Nenhuma emenda encontrada no Portal da Transparência para "
        f"**{nome_para_emendas}** no período {periodo_curto}. Isso pode acontecer se o "
        "nome registrado no Portal for diferente, se não houve emendas, ou se o período "
        "é anterior à cobertura do Portal (dados de emendas por autor começam em 2014)."
    )
else:
    for col in ("valor_empenhado", "valor_pago"):
        if col in df_emendas.columns:
            df_emendas[col] = pd.to_numeric(df_emendas[col], errors="coerce").fillna(0.0)

    e1, e2, e3 = st.columns(3)
    e1.metric("Emendas no mandato", len(df_emendas))
    e2.metric("Valor destinado (empenhado)", _moeda(float(df_emendas["valor_empenhado"].sum())))
    e3.metric("Valor efetivamente pago", _moeda(float(df_emendas["valor_pago"].sum())))

    with st.expander("❓ Qual a diferença entre 'destinado' e 'pago'?"):
        st.markdown(
            "- **Empenhado (destinado)**: o governo reservou o dinheiro para aquela finalidade.\n"
            "- **Pago**: o dinheiro de fato saiu do caixa e chegou ao destino.\n"
            "É comum haver diferença — obras demoram, e parte fica para os anos seguintes."
        )

    m1, m2 = st.columns(2)
    with m1:
        if "ano" in df_emendas.columns:
            df_ano_e = df_emendas.copy()
            df_ano_e["ano"] = pd.to_numeric(df_ano_e["ano"], errors="coerce")
            df_ano_e = df_ano_e.groupby("ano")["valor_empenhado"].sum().reset_index()
            df_ano_e.columns = ["Ano", "Valor destinado (R$)"]
            st.plotly_chart(_fig_barras(df_ano_e, "Ano", "Valor destinado (R$)",
                                        "Emendas ano a ano do mandato", moeda=True),
                            use_container_width=True)
    with m2:
        if "area" in df_emendas.columns and df_emendas["area"].astype(str).str.strip().ne("").any():
            df_area = (
                df_emendas.groupby("area")["valor_empenhado"].sum().sort_values(ascending=True).reset_index()
            )
            df_area.columns = ["Área", "Valor destinado (R$)"]
            st.plotly_chart(_fig_barras(df_area.tail(10), "Valor destinado (R$)", "Área",
                                        "Áreas beneficiadas (total do mandato)",
                                        moeda=True, horizontal=True),
                            use_container_width=True)

    with st.expander("📋 Ver todas as emendas com destino e fonte"):
        colunas_emendas = {
            "ano": "Ano", "municipio_beneficiado": "Município", "uf": "UF",
            "area": "Área", "valor_empenhado": "Destinado (R$)",
            "valor_pago": "Pago (R$)", "link_fonte": "Fonte oficial",
        }
        df_exibir = df_emendas[[c for c in colunas_emendas if c in df_emendas.columns]].rename(columns=colunas_emendas)
        df_exibir = _formatar_moeda_df(df_exibir, ["Destinado (R$)", "Pago (R$)"])
        st.dataframe(
            df_exibir, hide_index=True, use_container_width=True,
            column_config={"Fonte oficial": st.column_config.LinkColumn("Fonte oficial", display_text="conferir 🔗")},
        )
    st.caption(
        "Município em branco = emenda de abrangência estadual ou nacional, ou destinada "
        "a vários municípios (aparece como 'MÚLTIPLO' no Portal da Transparência)."
    )

if not eh_alesp:
    st.caption(
        "Fonte: [Portal da Transparência do Governo Federal]"
        "(https://portaldatransparencia.gov.br/emendas/consulta)."
    )

# ----------------------------------------------------------------------
# Rodapé institucional
# ----------------------------------------------------------------------

st.divider()
st.markdown(
    "##### ℹ️ Sobre este painel\n"
    "Os dados são consultados ao vivo em fontes oficiais: Câmara dos Deputados, "
    "Senado Federal, ALESP e Portal da Transparência. Este painel **não faz ranking, nota "
    "ou recomendação de voto** — apresenta fatos públicos para que cada eleitor tire "
    "suas próprias conclusões (em conformidade com a Resolução TSE nº 23.755/2026). "
    "Números de quantidade não medem qualidade: um bom mandato se avalia também "
    "pelo conteúdo dos projetos e pela realidade de cada cidade."
)
