"""Radar Eleitoral IA - dashboard comercial em Streamlit."""

from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import streamlit as st

from analysis.electoral_analysis import (
    calcular_evolucao_municipal,
    gerar_linha_do_tempo,
    gerar_resumo_estrategico,
    ranking_municipios_fortes,
    ranking_municipios_oportunidade,
    ranking_municipios_queda,
)
from analysis.effort_result_analysis import calcular_esforco_resultado, gerar_alertas
from analysis.tse_aggregations import agregar_votacao_por_candidato
from ai.communication_planner import gerar_calendario_editorial_30_dias, gerar_plano_30_60_90
from collectors.emendas_collector import (
    buscar_emendas_filtradas,
    buscar_emendas_portal_transparencia,
    gerar_resumo_emendas,
    importar_emendas_csv,
    salvar_emendas_no_banco,
)
from collectors.tse_collector import salvar_resultados_no_banco
from commercial_flow import criar_status_fluxo, montar_auditoria_dados
from compliance.electoral_compliance import gerar_checklist_compliance
from config.tse_sources import anos_disponiveis
from database.db_utils import (
    buscar_candidato,
    buscar_candidaturas_tse,
    buscar_votacao_secao_por_candidato,
    buscar_votacao_zona_por_candidato,
    buscar_votacao_por_candidato,
    listar_candidatos,
    listar_importacoes_tse,
    verificar_importacao_tse,
)
from database.init_db import _popular_dados_fake, init_database
from reports.pdf_generator import gerar_pdf_relatorio
from scripts.import_tse_history import importar_tse_ano_uf
from ui_components import (
    COLORS,
    inject_dashboard_css,
    render_audit_panel,
    render_compliance_card,
    render_communication_plan,
    render_empty_state,
    render_filter_panel,
    render_header,
    render_kpi_cards,
    render_municipios_chart,
    render_quadrant_chart,
    render_status_badges,
    render_territorial_map_or_ranking,
    render_timeline_chart,
)


st.set_page_config(page_title="Radar Eleitoral IA", layout="wide")
inject_dashboard_css()


@st.cache_resource(show_spinner=False)
def _garantir_banco() -> bool:
    db_path = os.path.join("database", "radar_eleitoral.db")
    if not os.path.exists(db_path):
        init_database()
        _popular_dados_fake()
    else:
        init_database()
    return True


@st.cache_data(ttl=30)
def _buscar_candidatos_cache(filtros: dict) -> list:
    return listar_candidatos(**filtros)


@st.cache_data(ttl=30)
def _buscar_candidaturas_tse_cache(filtros: dict) -> list:
    return buscar_candidaturas_tse(**filtros)


def _init_state() -> None:
    defaults = {
        "candidato_confirmado": None,
        "resultados_busca": [],
        "resultados_cache_tse": [],
        "filtros_busca": {},
        "filtros_emendas": {},
        "tse_registros": 0,
        "emendas_count": 0,
        "analise_count": 0,
        "plano_cache": None,
        "pdf_path": None,
        "auditoria": {},
        "tse_avisos": [],
        "emendas_status": "",
        "busca_banco_executada": False,
        "busca_banco_status": "",
        "busca_banco_count": 0,
        "matriz_cache": None,
        "admin_import_result": None,
        "ultimo_status_operacao": "",
        "ultimo_status_tipo": "info",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _status_atual(candidato=None) -> dict:
    return criar_status_fluxo(
        tse_registros=st.session_state.tse_registros,
        candidato=candidato,
        emendas_count=st.session_state.emendas_count,
        analise_count=st.session_state.analise_count,
        plano=st.session_state.plano_cache,
        pdf_path=st.session_state.pdf_path,
    )


def _atualizar_auditoria(candidato=None, origem_emendas: str = "Banco local/CSV") -> None:
    st.session_state.auditoria = montar_auditoria_dados(
        candidato=candidato,
        tse_registros=st.session_state.tse_registros,
        emendas_count=st.session_state.emendas_count,
        filtros={
            "busca": st.session_state.filtros_busca,
            "emendas": st.session_state.filtros_emendas,
        },
        origem_emendas=origem_emendas,
        pdf_path=st.session_state.pdf_path,
    )


def _mostrar_avisos_tse(df_tse: pd.DataFrame) -> None:
    avisos = list(df_tse.attrs.get("avisos_tse", []))
    st.session_state.tse_avisos = avisos
    for aviso in avisos:
        st.warning(f"[TSE] {aviso}")
    if df_tse.attrs.get("usou_demo"):
        st.info("[TSE] A consulta retornou dados de demonstração explicitamente sinalizados.")


def _definir_status_operacao(mensagem: str, tipo: str = "info") -> None:
    st.session_state.ultimo_status_operacao = mensagem
    st.session_state.ultimo_status_tipo = tipo


def _render_status_operacao(container=st) -> None:
    mensagem = st.session_state.get("ultimo_status_operacao")
    if not mensagem:
        return
    tipo = st.session_state.get("ultimo_status_tipo", "info")
    if tipo == "success":
        container.success(mensagem)
    elif tipo == "warning":
        container.warning(mensagem)
    elif tipo == "error":
        container.error(mensagem)
    else:
        container.info(mensagem)


def _persistir_resultado_tse(df_tse: pd.DataFrame, filtros_busca: dict, candidato=None) -> None:
    _mostrar_avisos_tse(df_tse)
    st.session_state.tse_registros = len(df_tse)
    if df_tse.empty:
        st.warning("Nenhum dado oficial foi encontrado no TSE para os filtros informados.")
        _atualizar_auditoria(candidato)
        return

    resumo_importacao = salvar_resultados_no_banco(df_tse)
    st.success(f"Importação TSE concluída: {resumo_importacao}")
    st.session_state.resultados_busca = listar_candidatos(**filtros_busca)
    st.session_state.busca_banco_executada = True
    st.session_state.busca_banco_count = len(st.session_state.resultados_busca)
    st.session_state.busca_banco_status = (
        f"Busca atualizada: {st.session_state.busca_banco_count} candidatura(s) encontrada(s)."
    )
    _atualizar_auditoria(candidato)


def _linhas_cache_para_candidatura(registro: dict) -> list:
    filtros = {
        "ano": registro.get("ano"),
        "uf": registro.get("uf"),
        "id_tse": registro.get("id_tse"),
    }
    if registro.get("id_tse"):
        return buscar_candidaturas_tse(**filtros)

    return buscar_candidaturas_tse(
        ano=registro.get("ano"),
        uf=registro.get("uf"),
        cargo=registro.get("cargo"),
        nome_civil=registro.get("nome_civil"),
        nome_urna=registro.get("nome_urna"),
        numero=registro.get("numero"),
    )


def _promover_cache_tse_para_analise(registro: dict) -> tuple[int | None, dict, int]:
    linhas = _linhas_cache_para_candidatura(registro)
    if not linhas:
        return None, {}, 0

    df_tse = pd.DataFrame(linhas)
    ano = int(registro.get("ano") or df_tse["ano"].iloc[0])
    df_tse["origem_dados"] = "real"
    df_tse["fonte_dados"] = f"TSE local tratado - votacao por municipio e zona ({ano})"
    resumo = salvar_resultados_no_banco(df_tse)

    candidatos = listar_candidatos(
        nome_civil=registro.get("nome_civil"),
        uf=registro.get("uf"),
    )
    cargo = str(registro.get("cargo") or "").upper().strip()
    candidatos_mesmo_cargo = [
        c for c in candidatos
        if str(c.get("cargo") or "").upper().strip() == cargo
    ]
    candidato_escolhido = (candidatos_mesmo_cargo or candidatos or [None])[0]
    candidato_id = candidato_escolhido["id"] if candidato_escolhido else None
    return candidato_id, resumo, len(linhas)


def _format_int(valor) -> str:
    return f"{int(valor or 0):,}".replace(",", ".")


def _format_pct(valor) -> str:
    return f"{float(valor or 0):.1f}%".replace(".", ",")


def _format_brl(valor) -> str:
    return f"R$ {float(valor or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _calcular_metricas(candidato: dict | None, ano_inicial: int, ano_final: int) -> dict:
    if not candidato:
        return {}

    candidato_id = candidato["id"]
    votacoes = buscar_votacao_por_candidato(candidato_id, ano_inicial=ano_inicial, ano_final=ano_final)
    df_votos = pd.DataFrame(votacoes)
    votos_totais = 0
    if not df_votos.empty:
        df_ano_final = df_votos[df_votos["ano"] == ano_final]
        votos_totais = df_ano_final["votos"].sum() if not df_ano_final.empty else df_votos["votos"].sum()

    linha_tempo = gerar_linha_do_tempo(candidato_id)
    crescimento = 0.0
    if not linha_tempo.empty and "crescimento_pct" in linha_tempo.columns:
        crescimento = float(linha_tempo["crescimento_pct"].iloc[-1])

    fortes = ranking_municipios_fortes(candidato_id, ano_final)
    resumo_emendas = gerar_resumo_emendas(candidato_id) or {}
    matriz = calcular_esforco_resultado(candidato_id, ano_inicial, ano_final)
    indice = "N/D"
    if not matriz.empty and "indice_retorno_territorial" in matriz.columns:
        serie = matriz["indice_retorno_territorial"].dropna()
        if not serie.empty:
            indice = f"{serie.median():.2f}"

    return {
        "votos_totais": _format_int(votos_totais),
        "crescimento": _format_pct(crescimento),
        "municipios_fortes": str(len(fortes)) if not fortes.empty else "0",
        "emendas_pagas": _format_brl(resumo_emendas.get("total_pago", 0)),
        "indice_retorno": indice,
    }


def _buscar_dados_territoriais(candidato: dict | None, ano: int) -> pd.DataFrame:
    """Busca o melhor recorte territorial disponivel para a visualizacao."""
    if not candidato:
        return pd.DataFrame()

    candidato_id = candidato["id"]
    secoes = pd.DataFrame(buscar_votacao_secao_por_candidato(candidato_id, int(ano)))
    if not secoes.empty and "secao" in secoes.columns and secoes["secao"].notna().any():
        dados = secoes
    else:
        zonas = pd.DataFrame(buscar_votacao_zona_por_candidato(candidato_id, int(ano)))
        if not zonas.empty and "zona" in zonas.columns and zonas["zona"].notna().any():
            dados = zonas
        else:
            dados = pd.DataFrame(buscar_votacao_por_candidato(candidato_id, ano_inicial=int(ano), ano_final=int(ano)))

    if dados.empty:
        return dados

    if "cargo" not in dados.columns:
        dados["cargo"] = candidato.get("cargo")
    if "uf" not in dados.columns or not dados["uf"].notna().any():
        dados["uf"] = candidato.get("uf")
    return dados


def _municipio_territorial_ref(df: pd.DataFrame, candidato: dict | None) -> str | None:
    if df is not None and not df.empty and "municipio" in df.columns and df["municipio"].notna().any():
        return str(df["municipio"].dropna().iloc[0])
    return (candidato or {}).get("municipio")


_garantir_banco()
_init_state()

anos_tse_configurados = anos_disponiveis()

st.sidebar.markdown(
    """
    <div class="radar-brand">
      <div class="radar-brand-title">Radar Eleitoral IA</div>
      <div class="radar-brand-sub">Inteligência territorial, estratégia e compliance</div>
    </div>
    """,
    unsafe_allow_html=True,
)
render_filter_panel()

ano_base_tse = st.sidebar.selectbox("Ano base", anos_tse_configurados, index=0)
comparar_com = st.sidebar.selectbox(
    "Comparar com",
    anos_tse_configurados,
    index=min(2, len(anos_tse_configurados) - 1),
)

modo_periodo = st.sidebar.radio("Período", ["Ano base x comparação", "Personalizado"])
if modo_periodo == "Personalizado":
    ano_inicial = st.sidebar.number_input("Ano inicial", min_value=1990, max_value=2030, value=int(comparar_com))
    ano_final = st.sidebar.number_input("Ano final", min_value=1990, max_value=2030, value=int(ano_base_tse))
else:
    ano_inicial = int(comparar_com)
    ano_final = int(ano_base_tse)

st.sidebar.text_input("Nome civil", key="busca_nome_civil")
st.sidebar.text_input("Nome na urna", key="busca_nome_urna")
st.sidebar.text_input("Número do candidato", key="busca_numero")
st.sidebar.text_input("Partido", key="busca_partido")
st.sidebar.text_input("UF", value="SP", key="busca_uf")
st.sidebar.selectbox(
    "Cargo",
    [
        "Todos", "Vereador", "Prefeito", "Vice-prefeito", "Deputado Estadual",
        "Deputado Federal", "Deputado Distrital", "Senador", "Governador", "Presidente",
    ],
    key="busca_cargo",
)
pesquisar = st.sidebar.button("Pesquisar candidato", type="primary", key="btn_pesquisar_candidato")
status_sidebar_placeholder = st.sidebar.empty()

cargo_busca = None if st.session_state.busca_cargo == "Todos" else st.session_state.busca_cargo
filtros_busca = {
    "nome_civil": st.session_state.busca_nome_civil or None,
    "nome_urna": st.session_state.busca_nome_urna or None,
    "numero": st.session_state.busca_numero or None,
    "partido": st.session_state.busca_partido or None,
    "uf": st.session_state.busca_uf or None,
    "cargo": cargo_busca,
}
st.session_state.filtros_busca = filtros_busca

if pesquisar:
    uf_consulta = (filtros_busca["uf"] or "SP").upper().strip()
    filtros_cache_tse = {
        **filtros_busca,
        "ano": int(ano_base_tse),
        "uf": uf_consulta,
    }
    status_sidebar_placeholder.info(f"Pesquisando {uf_consulta}/{int(ano_base_tse)} no banco local tratado...")
    with st.spinner("Pesquisando candidato no banco local tratado..."):
        importacao_tse = verificar_importacao_tse(int(ano_base_tse), uf_consulta)
        if not importacao_tse:
            st.session_state.resultados_cache_tse = []
            st.session_state.busca_banco_status = (
                f"Dados de {uf_consulta}/{int(ano_base_tse)} ainda não importados. "
                "Acesse a área de Administração para importar."
            )
            _definir_status_operacao(st.session_state.busca_banco_status, "warning")
        else:
            st.session_state.resultados_cache_tse = _buscar_candidaturas_tse_cache(filtros_cache_tse)
            total_registros = len(st.session_state.resultados_cache_tse)
            if total_registros:
                st.session_state.busca_banco_status = (
                    "Busca concluída no cache local TSE: "
                    f"{total_registros} registro(s) de zona encontrado(s)."
                )
                _definir_status_operacao(st.session_state.busca_banco_status, "success")
            else:
                st.session_state.busca_banco_status = (
                    f"Busca concluída em {uf_consulta}/{int(ano_base_tse)}, mas nenhum candidato "
                    "bateu com os filtros informados. Tente reduzir nome, número, partido ou cargo."
                )
                _definir_status_operacao(st.session_state.busca_banco_status, "warning")
    st.session_state.resultados_busca = []
    st.session_state.candidato_confirmado = None
    st.session_state.pdf_path = None
    st.session_state.busca_banco_executada = True
    st.session_state.busca_banco_count = len(st.session_state.resultados_cache_tse)
    _atualizar_auditoria(None)

st.sidebar.info("Dados oficiais do TSE agora são importados na aba Administração de Dados.")
_render_status_operacao(st.sidebar)

candidato = buscar_candidato(st.session_state.candidato_confirmado) if st.session_state.candidato_confirmado else None

candidato = buscar_candidato(st.session_state.candidato_confirmado) if st.session_state.candidato_confirmado else None
status = _status_atual(candidato)

render_header(candidato)
render_status_badges(status, (candidato or {}).get("origem_dados"))
render_kpi_cards(_calcular_metricas(candidato, int(ano_inicial), int(ano_final)))
_render_status_operacao(st)

tabs = st.tabs([
    "Resumo",
    "Municípios",
    "Esforço x Resultado",
    "Plano de Comunicação",
    "Compliance",
    "Relatório",
    "Auditoria",
    "Mapa",
    "Administração de Dados",
])

with tabs[0]:
    col_resultados, col_mapa = st.columns([1.35, 1])

    with col_resultados:
        st.markdown('<div class="section-title">Seleção de candidatura</div>', unsafe_allow_html=True)
        if st.session_state.busca_banco_executada:
            if st.session_state.busca_banco_count:
                st.success(st.session_state.busca_banco_status)
            else:
                st.warning(st.session_state.busca_banco_status)

        for aviso in st.session_state.tse_avisos:
            st.caption(f"[TSE] {aviso}")

        if st.session_state.resultados_cache_tse:
            df_resultados = pd.DataFrame(st.session_state.resultados_cache_tse)
            df_candidaturas = agregar_votacao_por_candidato(df_resultados)
            colunas = [
                c for c in [
                    "id_tse", "nome_civil", "nome_urna", "numero", "partido", "cargo",
                    "uf", "ano", "situacao", "votos", "votos_validos",
                ] if c in df_candidaturas.columns
            ]
            st.dataframe(df_candidaturas[colunas], width="stretch", hide_index=True)
            registros_agregados = df_candidaturas.to_dict("records")
            opcoes = {
                (
                    f"{c.get('nome_urna') or c.get('nome_civil')} ({c.get('ano')}) "
                    f"- {c.get('cargo')} - {c.get('partido')} - {_format_int(c.get('votos'))} votos"
                ): idx
                for idx, c in enumerate(registros_agregados)
            }
            escolha = st.selectbox("Confirmar candidato correto", list(opcoes.keys()))
            if st.button("Confirmar candidatura", type="primary"):
                registro = registros_agregados[opcoes[escolha]]
                candidato_id, resumo_promocao, total_linhas = _promover_cache_tse_para_analise(registro)
                if candidato_id:
                    st.session_state.candidato_confirmado = candidato_id
                    candidato = buscar_candidato(st.session_state.candidato_confirmado)
                    st.session_state.tse_registros = max(
                        total_linhas,
                        len(buscar_votacao_por_candidato(candidato["id"])),
                    )
                    st.session_state.resultados_busca = listar_candidatos(
                        nome_civil=registro.get("nome_civil"),
                        uf=registro.get("uf"),
                    )
                    _atualizar_auditoria(candidato)
                    st.success(f"Candidatura confirmada. Dados preparados para análise: {resumo_promocao}")
                    st.rerun()
                else:
                    st.error("Não foi possível preparar essa candidatura para análise.")
        else:
            render_empty_state(
                "Nenhuma candidatura selecionada",
                "Use os filtros à esquerda para pesquisar no cache local ou importe dados na Administração.",
            )

        if candidato:
            st.markdown('<div class="section-title">Resumo estratégico</div>', unsafe_allow_html=True)
            st.write(gerar_resumo_estrategico(candidato["id"], (int(ano_inicial), int(ano_final))))

    with col_mapa:
        st.markdown('<div class="section-title">Mapa de desempenho</div>', unsafe_allow_html=True)
        if candidato:
            dados_territoriais = _buscar_dados_territoriais(candidato, int(ano_final))
            render_territorial_map_or_ranking(
                dados_territoriais,
                cargo=candidato.get("cargo"),
                municipio=_municipio_territorial_ref(dados_territoriais, candidato),
                uf=candidato.get("uf"),
                key_prefix="resumo_territorial",
            )
        else:
            render_empty_state(
                "Mapa visual aguardando candidato",
                "Selecione uma candidatura para visualizar o desempenho por zona eleitoral.",
            )

with tabs[1]:
    if not candidato:
        render_empty_state("Selecione uma candidatura", "Os gráficos municipais aparecem após confirmar um candidato.")
    else:
        linha_tempo = gerar_linha_do_tempo(candidato["id"])
        st.markdown('<div class="section-title">Linha do tempo eleitoral</div>', unsafe_allow_html=True)
        st.plotly_chart(render_timeline_chart(linha_tempo), width="stretch", key="plot_municipios_linha_tempo")

        fortes = ranking_municipios_fortes(candidato["id"], int(ano_final))
        queda = ranking_municipios_queda(candidato["id"], int(ano_inicial), int(ano_final))
        oportunidade = ranking_municipios_oportunidade(candidato["id"], int(ano_final))
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(
                render_municipios_chart(fortes, "Top municípios por votos", COLORS["blue"]),
                width="stretch",
                key="plot_municipios_top_votos",
            )
        with c2:
            st.plotly_chart(
                render_municipios_chart(queda, "Municípios em queda", COLORS["red"]),
                width="stretch",
                key="plot_municipios_queda",
            )
        st.markdown('<div class="section-title">Oportunidades territoriais</div>', unsafe_allow_html=True)
        if oportunidade.empty:
            render_empty_state("Nenhuma oportunidade calculada", "Importe ou selecione dados eleitorais para gerar oportunidades.")
        else:
            st.dataframe(oportunidade, width="stretch", hide_index=True)

with tabs[2]:
    if not candidato:
        render_empty_state("Selecione uma candidatura", "A matriz depende de votação e emendas vinculadas ao candidato.")
    else:
        st.markdown('<div class="section-title">Emendas e verbas públicas</div>', unsafe_allow_html=True)
        col1, col2, col3, col4, col5 = st.columns(5)
        em_ano = col1.number_input("Ano", min_value=0, max_value=2030, value=0, key="em_ano")
        em_codigo = col2.text_input("Código IBGE", key="em_codigo_ibge")
        em_municipio = col3.text_input("Município", key="em_municipio")
        em_uf = col4.text_input("UF", value=candidato.get("uf") or "", key="em_uf")
        em_autor = col5.text_input("Autor/parlamentar", value=candidato.get("nome_urna") or "", key="em_autor")
        niveis = st.multiselect(
            "Nível territorial",
            ["municipal", "estadual", "nacional", "multiplo"],
            default=["multiplo"],
            key="em_niveis",
        )
        origem_emendas = st.radio("Origem da consulta", ["Banco local", "Portal da Transparência"], horizontal=True)
        arquivo_csv = st.file_uploader("Importar CSV de emendas", type=["csv"])
        filtros_emendas = {
            "ano": int(em_ano) if em_ano else None,
            "codigo_ibge": em_codigo or None,
            "municipio": em_municipio or None,
            "uf": em_uf or None,
            "autor": em_autor or None,
            "nivel": ",".join(niveis or ["multiplo"]),
        }
        st.session_state.filtros_emendas = filtros_emendas

        col_a, col_b, col_c = st.columns([1, 1, 1.1])
        if col_a.button("Consultar emendas", type="primary"):
            try:
                if origem_emendas == "Portal da Transparência":
                    df_emendas = buscar_emendas_portal_transparencia(**filtros_emendas)
                    status_portal = df_emendas.attrs.get("status_consulta", "")
                    st.session_state.emendas_status = status_portal
                    if status_portal == "sem_chave_api":
                        st.warning(
                            "Não foi possível consultar a fonte neste momento: chave do Portal da Transparência não configurada."
                        )
                    if not df_emendas.empty:
                        inseridas = salvar_emendas_no_banco(df_emendas)
                        st.success(f"{inseridas} emenda(s) importada(s) do Portal.")
                else:
                    df_emendas = buscar_emendas_filtradas(**filtros_emendas)
                    st.session_state.emendas_status = df_emendas.attrs.get("status_consulta", "banco_local")
                st.session_state.emendas_count = len(df_emendas)
                if df_emendas.empty:
                    st.info("Nenhuma emenda encontrada com os filtros informados.")
                else:
                    st.dataframe(df_emendas, width="stretch", hide_index=True)
                    st.caption(f"[EMENDAS] Origem/status: {st.session_state.emendas_status or origem_emendas}")
                _atualizar_auditoria(candidato, origem_emendas)
            except Exception as exc:
                st.error(f"Não foi possível consultar a fonte neste momento: {exc}")

        if arquivo_csv is not None and col_b.button("Salvar CSV"):
            caminho_temp = os.path.join("data", "temp_upload.csv")
            with open(caminho_temp, "wb") as f:
                f.write(arquivo_csv.getbuffer())
            df_importado = importar_emendas_csv(caminho_temp)
            inseridas = salvar_emendas_no_banco(df_importado)
            st.session_state.emendas_count = inseridas
            _atualizar_auditoria(candidato, "CSV")
            st.success(f"{inseridas} emenda(s) importada(s) do CSV.")

        if col_c.button("Calcular matriz esforço x resultado", type="primary"):
            matriz = calcular_esforco_resultado(candidato["id"], int(ano_inicial), int(ano_final))
            st.session_state.matriz_cache = matriz
            st.session_state.analise_count = len(matriz)
            _atualizar_auditoria(candidato)
            if matriz.empty:
                st.info("Nenhum dado encontrado para calcular a matriz neste período.")

        matriz = st.session_state.matriz_cache
        if matriz is None:
            matriz = calcular_esforco_resultado(candidato["id"], int(ano_inicial), int(ano_final))
        st.plotly_chart(render_quadrant_chart(matriz), width="stretch", key="plot_esforco_resultado_matriz")
        if matriz is not None and not matriz.empty:
            st.dataframe(matriz, width="stretch", hide_index=True)

with tabs[3]:
    if not candidato:
        render_empty_state("Selecione uma candidatura", "O plano 30/60/90 aparece após confirmar o candidato.")
    else:
        if st.button("Gerar plano 30/60/90", type="primary"):
            alertas = gerar_alertas(candidato["id"]) or {}
            oportunidade = ranking_municipios_oportunidade(candidato["id"], int(ano_final))
            municipios_oport = (
                oportunidade[oportunidade["potencial_comunicacao"] == "oportunidade"]["municipio"].tolist()
                if not oportunidade.empty else []
            )
            st.session_state.plano_cache = gerar_plano_30_60_90(
                candidato,
                {"municipios_oportunidade": municipios_oport},
                {"municipios_atencao": alertas.get("prioridade_comunicacao", [])},
            )
            _atualizar_auditoria(candidato)

        render_communication_plan(st.session_state.plano_cache)
        if st.session_state.plano_cache:
            calendario = gerar_calendario_editorial_30_dias(st.session_state.plano_cache.get("temas_prioritarios"))
            st.dataframe(pd.DataFrame(calendario), width="stretch", hide_index=True)

with tabs[4]:
    plano = st.session_state.plano_cache or {}
    checklist = plano.get("compliance_checklist") or gerar_checklist_compliance(plano or {"objetivo": "Plano ainda não gerado"})
    render_compliance_card(checklist)

with tabs[5]:
    if not candidato:
        render_empty_state("Selecione uma candidatura", "O relatório estratégico depende de uma candidatura confirmada.")
    else:
        st.markdown('<div class="section-title">Relatório Estratégico Eleitoral</div>', unsafe_allow_html=True)
        st.write(f"Período analisado: {int(ano_inicial)} a {int(ano_final)}")
        st.write(f"Fonte eleitoral: {candidato.get('fonte_dados') or 'Dados de demonstração do MVP'}")
        if st.button("Gerar PDF Estratégico", type="primary"):
            try:
                caminho_pdf = gerar_pdf_relatorio(candidato["id"], int(ano_inicial), int(ano_final))
                st.session_state.pdf_path = caminho_pdf
                _atualizar_auditoria(candidato)
                with open(caminho_pdf, "rb") as f:
                    st.download_button(
                        "Baixar relatório PDF",
                        data=f.read(),
                        file_name=os.path.basename(caminho_pdf),
                        mime="application/pdf",
                    )
                st.success(f"PDF gerado: {os.path.basename(caminho_pdf)}")
            except Exception as exc:
                st.error(f"Não foi possível gerar o PDF neste momento: {exc}")
        if st.session_state.pdf_path:
            st.caption(f"Último PDF: {st.session_state.pdf_path}")

with tabs[6]:
    candidato = buscar_candidato(st.session_state.candidato_confirmado) if st.session_state.candidato_confirmado else None
    _atualizar_auditoria(candidato)
    render_audit_panel(st.session_state.auditoria)

with tabs[7]:
    st.markdown('<div class="section-title">Mapa de desempenho municipal</div>', unsafe_allow_html=True)
    if candidato:
        dados_territoriais = _buscar_dados_territoriais(candidato, int(ano_final))
        resultado_territorial = render_territorial_map_or_ranking(
            dados_territoriais,
            cargo=candidato.get("cargo"),
            municipio=_municipio_territorial_ref(dados_territoriais, candidato),
            uf=candidato.get("uf"),
            key_prefix="aba_mapa_territorial",
        )
        if resultado_territorial["granularidade"] in {"bairro", "local_votacao", "secao", "zona"}:
            st.caption(
                "Distribuição municipal detalhada a partir da melhor granularidade disponível no banco. "
                "Coordenadas são usadas apenas quando a camada geográfica importada as fornece."
            )
        else:
            st.caption("Sem detalhe por zona para este recorte; exibindo desempenho por município.")
    else:
        render_empty_state(
            "Mapa aguardando candidatura",
            "Confirme uma candidatura para visualizar as zonas eleitorais por desempenho.",
        )

with tabs[8]:
    st.markdown('<div class="section-title">Administração de Dados TSE</div>', unsafe_allow_html=True)
    st.info(
        "Os arquivos do TSE são grandes e históricos. Importe uma vez por ano/UF; "
        "depois o dashboard consulta apenas o banco local tratado."
    )

    col_ano, col_uf, col_forcar, col_local = st.columns([1, 1, 1, 1.25])
    admin_ano = col_ano.selectbox("Ano para importar", anos_tse_configurados, key="admin_tse_ano")
    admin_uf = col_uf.text_input("UF", value=(st.session_state.busca_uf or "SP"), key="admin_tse_uf")
    admin_forcar = col_forcar.checkbox("Forçar reimportação", key="admin_tse_forcar")
    admin_somente_baixados = col_local.checkbox(
        "Usar apenas ZIP local",
        value=False,
        key="admin_tse_somente_baixados",
        help="Não baixa arquivo. Use quando você já colocou o ZIP em data/raw/tse.",
    )
    import_status_placeholder = st.empty()

    if st.button("Importar TSE para o banco local", type="primary", key="btn_admin_importar_tse"):
        mensagem_importando = (
            f"Importando TSE {admin_uf.upper().strip()}/{admin_ano}. "
            "Aguarde: arquivos grandes podem demorar alguns minutos."
        )
        import_status_placeholder.info(mensagem_importando)
        _definir_status_operacao(mensagem_importando, "info")
        with st.spinner(f"Importando TSE {admin_uf.upper().strip()}/{admin_ano}. Isso pode demorar..."):
            resultado = importar_tse_ano_uf(
                ano=int(admin_ano),
                uf=admin_uf,
                forcar=admin_forcar,
                somente_baixados=admin_somente_baixados,
            )
        st.session_state.admin_import_result = resultado
        _buscar_candidaturas_tse_cache.clear()
        if resultado["status"] == "importado":
            _definir_status_operacao(resultado["mensagem"], "success")
        elif resultado["status"] == "pulado":
            _definir_status_operacao(resultado["mensagem"], "info")
        else:
            _definir_status_operacao(resultado["mensagem"], "error")

    if st.session_state.admin_import_result:
        resultado = st.session_state.admin_import_result
        if resultado["status"] == "importado":
            st.success(resultado["mensagem"])
        elif resultado["status"] == "pulado":
            st.info(resultado["mensagem"])
        else:
            st.error(resultado["mensagem"])

    st.markdown('<div class="section-title">Importação territorial</div>', unsafe_allow_html=True)
    st.info(
        "Cargos municipais precisam de granularidade por zona, seção, local de votação ou bairro. "
        "A importação por município/zona já está disponível no fluxo TSE acima; seção e locais "
        "ficam preparados para ETL offline."
    )
    tipo_territorial = st.selectbox(
        "Base territorial",
        [
            "Votação por município/zona",
            "Votação por seção",
            "Locais de votação",
            "Zonas eleitorais/geocodificação",
        ],
        key="admin_tipo_territorial",
    )
    if tipo_territorial == "Votação por município/zona":
        st.success("Disponível: use o botão 'Importar TSE para o banco local' acima.")
    elif tipo_territorial == "Votação por seção":
        st.warning("Em preparação no dashboard. ETL offline disponível por script.")
        st.code(
            f'.\\.venv\\Scripts\\python.exe scripts\\import_tse_sections.py --uf {admin_uf.upper().strip()} '
            f'--ano {int(admin_ano)} --municipio "São Paulo"',
            language="powershell",
        )
    elif tipo_territorial == "Locais de votação":
        st.warning("Em preparação: a tabela local está criada, mas o importador completo de locais ainda não foi ligado à UI.")
    else:
        st.info("Disponível por script para CSV de zonas/geocodificação.")
        st.code(
            f'.\\.venv\\Scripts\\python.exe scripts\\import_geo_data.py --uf {admin_uf.upper().strip()} '
            '--municipio "São Paulo"',
            language="powershell",
        )

    st.markdown('<div class="section-title">Status das importações</div>', unsafe_allow_html=True)
    importacoes = listar_importacoes_tse()
    if importacoes:
        st.dataframe(pd.DataFrame(importacoes), width="stretch", hide_index=True)
    else:
        render_empty_state(
            "Nenhuma importação TSE registrada",
            "Importe um ano/UF para liberar a busca rápida no dashboard.",
        )
