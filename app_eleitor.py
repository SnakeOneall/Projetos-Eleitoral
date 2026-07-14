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
from collectors.sp_transparencia_collector import buscar_emendas_estaduais_por_autor
from collectors.alesp_collector import (
    buscar_despesas_gabinete,
    buscar_presencas_comissoes,
    buscar_votos_comissoes,
    contar_reunioes_comissoes,
    detalhar_deputado_alesp,
    listar_deputados_alesp,
    nomes_comissoes,
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


# ----------------------------------------------------------------------
# Cabeçalho e busca por nome
# ----------------------------------------------------------------------

# Evita que o tradutor automático do navegador reescreva os textos do painel
# (ele transforma "mandato a mandato" em "manda a manda", "Cargo" em "Carga" etc.)
st.markdown('<meta name="google" content="notranslate">', unsafe_allow_html=True)

st.title("🔎 Radar do Eleitor")
st.markdown(
    "**Conheça o trabalho de quem você elegeu — ou pretende eleger, mandato a mandato.** "
    "Todos os dados vêm de fontes oficiais do governo, com link para conferência. "
    "Este painel informa; a escolha é sua."
)

# A busca fica dentro de um FORMULÁRIO: nada recarrega enquanto a pessoa digita
# ou troca opções — só ao clicar em Consultar. Isso elimina as execuções
# interrompidas que misturavam dados de parlamentares diferentes na tela.
with st.form("form_busca"):
    col_casa, col_busca, col_uf, col_mandato = st.columns([1.2, 2.2, 0.7, 1.6])
    with col_casa:
        casa = st.radio(
            "Quem você quer conhecer?",
            ["Deputado(a) federal", "Senador(a)", "Deputado(a) estadual (SP)"],
            horizontal=False,
        )
    with col_busca:
        termo = st.text_input(
            "Digite o nome (ou parte dele)",
            placeholder="Ex.: Maria, Tiririca, Silva...",
            help="Busca sem diferença de acento ou maiúscula, em todos os estados.",
        )
    with col_uf:
        uf_filtro = st.selectbox("Estado", UFS)
    with col_mandato:
        mandato_rotulo = st.selectbox("Mandato (legislatura)", list(MANDATOS.keys()))
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

ano_ini, ano_fim = MANDATOS[mandato_rotulo]
periodo_curto = f"{ano_ini}–{ano_fim}"
eh_camara = casa == "Deputado(a) federal"
eh_senado = casa == "Senador(a)"
eh_alesp = casa == "Deputado(a) estadual (SP)"

st.caption(
    "ℹ️ A lista abaixo traz quem está **em exercício hoje**. Ao escolher um mandato "
    "anterior, você vê o que esse mesmo parlamentar fez naquele período (se já era "
    "parlamentar na época). Senadores têm mandato de 8 anos — o período selecionado "
    "mostra a metade correspondente."
)

with st.spinner("Carregando parlamentares em exercício..."):
    if eh_camara:
        df_parls = _todos_deputados()
    elif eh_senado:
        df_parls = _todos_senadores()
    else:
        df_parls = _todos_dep_alesp()

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
chave_seletor = f"sel_parlamentar_{'camara' if eh_camara else 'senado' if eh_senado else 'alesp'}"
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
else:
    detalhes = detalhar_deputado_alesp(linha_parl.to_dict())
    id_parl = detalhes["id_alesp"]

st.divider()
col_foto, col_info = st.columns([1, 5])
with col_foto:
    if detalhes.get("url_foto"):
        st.image(detalhes["url_foto"], width=120)
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
