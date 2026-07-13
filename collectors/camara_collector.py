"""
Radar Eleitoral IA - Coletor de atividade parlamentar (Câmara dos Deputados).

Fonte oficial: API de Dados Abertos da Câmara dos Deputados
(https://dadosabertos.camara.leg.br/api/v2) — pública, sem chave.

Endpoints usados (verificados em jul/2026):
  - GET /deputados?siglaUf=...            -> lista de deputados em exercício
  - GET /deputados/{id}                    -> situação (Exercício/Licença), gabinete
  - GET /deputados/{id}/despesas           -> CEAP (cota parlamentar), item a item
  - GET /deputados/{id}/eventos            -> eventos com participação (sessões etc.)
  - GET /deputados/{id}/discursos          -> discursos em plenário
  - GET /proposicoes?idDeputadoAutor=...   -> proposições de autoria
  - GET /votacoes/{id}/votos               -> votos nominais

NOTA METODOLÓGICA (importante para a interface):
  A API v2 não expõe o registro oficial de presença/falta justificada por
  sessão. A "participação em sessões deliberativas" aqui é derivada dos
  eventos em que o deputado consta como participante — é um indicador de
  atividade, não o boletim oficial de frequência. Exibir sempre com essa
  ressalva e com link para a fonte.

COMPLIANCE (Resolução TSE 23.755/2026): os dados devem ser exibidos de
forma factual e comparável (valor + média dos pares + fonte). O sistema
não deve gerar rankings, notas ou recomendações de candidatos.
"""

import logging
import sys
import time
from pathlib import Path

import pandas as pd
import requests

# Permite executar tanto via "python -m collectors.camara_collector"
# quanto diretamente via "python collectors\camara_collector.py".
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.init_db import get_connection

API_BASE = "https://dadosabertos.camara.leg.br/api/v2"
TIMEOUT = 30
PAUSA_ENTRE_PAGINAS = 0.3  # cortesia com a API pública
MAX_PAGINAS = 50


def _criar_logger() -> logging.Logger:
    logger_camara = logging.getLogger("radar_eleitoral.camara")
    if not logger_camara.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[CAMARA] %(message)s"))
        logger_camara.addHandler(handler)
    logger_camara.setLevel(logging.INFO)
    logger_camara.propagate = False
    return logger_camara


logger = _criar_logger()


def _get(endpoint: str, params: dict = None) -> dict:
    """GET simples com Accept JSON; levanta exceção para erros HTTP."""
    resposta = requests.get(
        f"{API_BASE}{endpoint}",
        params=params or {},
        headers={"Accept": "application/json"},
        timeout=TIMEOUT,
    )
    resposta.raise_for_status()
    return resposta.json()


def _get_paginado(endpoint: str, params: dict = None) -> list:
    """Percorre todas as páginas de um endpoint que aceita 'pagina'/'itens'."""
    params = dict(params or {})
    params.setdefault("itens", 100)
    registros = []
    for pagina in range(1, MAX_PAGINAS + 1):
        params["pagina"] = pagina
        dados = _get(endpoint, params).get("dados", [])
        if not dados:
            break
        registros.extend(dados)
        if len(dados) < params["itens"]:
            break
        time.sleep(PAUSA_ENTRE_PAGINAS)
    return registros


# ----------------------------------------------------------------------
# Deputados
# ----------------------------------------------------------------------

def listar_deputados(uf: str = None, partido: str = None, legislatura: int = None) -> pd.DataFrame:
    """Lista deputados (em exercício por padrão) com filtros opcionais."""
    params = {}
    if uf:
        params["siglaUf"] = str(uf).upper().strip()
    if partido:
        params["siglaPartido"] = partido
    if legislatura:
        params["idLegislatura"] = int(legislatura)

    dados = _get_paginado("/deputados", {**params, "ordem": "ASC", "ordenarPor": "nome"})
    df = pd.DataFrame(dados)
    logger.info(f"{len(df)} deputado(s) retornado(s) pela API.")
    return df


def detalhar_deputado(id_camara: int) -> dict:
    """Detalhes do deputado, incluindo situação atual (Exercício, Licença...)."""
    dados = _get(f"/deputados/{int(id_camara)}").get("dados", {})
    ultimo = dados.get("ultimoStatus", {}) or {}
    return {
        "id_camara": dados.get("id"),
        "nome_civil": dados.get("nomeCivil"),
        "nome_parlamentar": ultimo.get("nomeEleitoral") or ultimo.get("nome"),
        "partido": ultimo.get("siglaPartido"),
        "uf": ultimo.get("siglaUf"),
        "situacao": ultimo.get("situacao"),
        "condicao_eleitoral": ultimo.get("condicaoEleitoral"),
        "gabinete": (ultimo.get("gabinete") or {}).get("nome"),
        "url_foto": ultimo.get("urlFoto"),
        "fonte": "API Dados Abertos Câmara",
        "link_fonte": f"https://www.camara.leg.br/deputados/{dados.get('id')}",
    }


# ----------------------------------------------------------------------
# CEAP - Cota para Exercício da Atividade Parlamentar
# ----------------------------------------------------------------------

def buscar_despesas_ceap(id_camara: int, ano: int, mes: int = None) -> pd.DataFrame:
    """Despesas da cota parlamentar, item a item, com link do documento fiscal."""
    params = {"ano": int(ano)}
    if mes:
        params["mes"] = int(mes)
    dados = _get_paginado(f"/deputados/{int(id_camara)}/despesas", params)
    df = pd.DataFrame(dados)
    logger.info(f"{len(df)} despesa(s) CEAP para deputado {id_camara} em {ano}.")
    return df


def resumir_despesas_ceap(df_despesas: pd.DataFrame) -> dict:
    """Agrega o CEAP por tipo de despesa e por mês (valores líquidos)."""
    if df_despesas is None or df_despesas.empty:
        return {"total_liquido": 0.0, "por_tipo": {}, "por_mes": {}}
    df = df_despesas.copy()
    df["valorLiquido"] = pd.to_numeric(df["valorLiquido"], errors="coerce").fillna(0.0)
    return {
        "total_liquido": float(df["valorLiquido"].sum()),
        "por_tipo": df.groupby("tipoDespesa")["valorLiquido"].sum().sort_values(ascending=False).round(2).to_dict(),
        "por_mes": df.groupby("mes")["valorLiquido"].sum().round(2).to_dict(),
    }


# ----------------------------------------------------------------------
# Atividade: sessões, discursos, proposições
# ----------------------------------------------------------------------

def buscar_eventos_participados(id_camara: int, data_inicio: str, data_fim: str) -> pd.DataFrame:
    """Eventos com participação do deputado no período (AAAA-MM-DD).

    Indicador derivado — ver NOTA METODOLÓGICA no topo do módulo.
    """
    dados = _get_paginado(
        f"/deputados/{int(id_camara)}/eventos",
        {"dataInicio": data_inicio, "dataFim": data_fim},
    )
    df = pd.DataFrame(dados)
    logger.info(f"{len(df)} evento(s) com participação do deputado {id_camara} no período.")
    return df


def contar_sessoes_deliberativas(df_eventos: pd.DataFrame) -> int:
    """Conta sessões deliberativas do plenário dentre os eventos participados."""
    if df_eventos is None or df_eventos.empty or "descricaoTipo" not in df_eventos.columns:
        return 0
    return int((df_eventos["descricaoTipo"].astype(str).str.contains("Deliberativa", case=False)).sum())


def buscar_discursos(id_camara: int, data_inicio: str, data_fim: str) -> pd.DataFrame:
    """Discursos do deputado em plenário no período."""
    dados = _get_paginado(
        f"/deputados/{int(id_camara)}/discursos",
        {"dataInicio": data_inicio, "dataFim": data_fim, "ordenarPor": "dataHoraInicio"},
    )
    df = pd.DataFrame(dados)
    logger.info(f"{len(df)} discurso(s) do deputado {id_camara} no período.")
    return df


def buscar_proposicoes_autoria(id_camara: int, ano: int = None) -> pd.DataFrame:
    """Proposições de autoria do deputado (PL, PEC, requerimentos etc.)."""
    params = {"idDeputadoAutor": int(id_camara)}
    if ano:
        params["ano"] = int(ano)
    dados = _get_paginado("/proposicoes", params)
    df = pd.DataFrame(dados)
    logger.info(f"{len(df)} proposição(ões) de autoria do deputado {id_camara}.")
    return df


# ----------------------------------------------------------------------
# Votações nominais do plenário ("como ele votou")
# ----------------------------------------------------------------------

import re as _re

_PADRAO_NOMINAL = _re.compile(r"Sim:\s*\d+", _re.IGNORECASE)


def listar_votacoes_nominais_plenario(ano: int, limite: int = 12) -> pd.DataFrame:
    """Votações nominais do plenário no ano (mais recentes primeiro).

    A API limita o intervalo de datas por requisição (ano inteiro retorna
    HTTP 400), então a busca é feita mês a mês, do fim do ano para trás,
    parando ao atingir o limite pedido.

    A API não marca explicitamente quais votações são nominais; usamos a
    descrição oficial (que traz o placar 'Sim: X; Não: Y') como critério,
    evitando baixar votos de votações simbólicas (que não têm voto
    individual registrado).
    """
    import calendar

    ano = int(ano)
    partes = []
    encontradas = 0
    for mes in range(12, 0, -1):
        ultimo_dia = calendar.monthrange(ano, mes)[1]
        try:
            dados = _get_paginado(
                "/votacoes",
                {
                    "dataInicio": f"{ano}-{mes:02d}-01",
                    "dataFim": f"{ano}-{mes:02d}-{ultimo_dia}",
                    "ordem": "DESC",
                    "ordenarPor": "dataHoraRegistro",
                },
            )
        except requests.HTTPError:
            continue  # mês futuro ou sem dados
        df_mes = pd.DataFrame(dados)
        if df_mes.empty:
            continue
        df_mes = df_mes[df_mes["siglaOrgao"] == "PLEN"]
        df_mes = df_mes[df_mes["descricao"].astype(str).str.contains(_PADRAO_NOMINAL, na=False)]
        if not df_mes.empty:
            partes.append(df_mes)
            encontradas += len(df_mes)
        if encontradas >= limite:
            break

    if not partes:
        return pd.DataFrame()
    df = pd.concat(partes, ignore_index=True)
    df = df.sort_values("dataHoraRegistro", ascending=False)
    # Diversifica as datas (máx. 2 votações por dia) para dar um retrato
    # mais representativo do que concentrar tudo em uma única sessão.
    df = df.groupby("data", group_keys=False).head(2)
    df = df.sort_values("dataHoraRegistro", ascending=False).head(int(limite)).reset_index(drop=True)
    logger.info(f"{len(df)} votação(ões) nominais do plenário em {ano}.")
    return df


def buscar_voto_do_deputado(votacao_id: str, id_camara: int) -> str:
    """Como o deputado votou em uma votação nominal específica.

    Retorna 'Sim', 'Não', 'Abstenção', 'Obstrução', 'Artigo 17' (presidente
    não vota) ou 'Não registrado' quando não há voto dele na lista (ausência,
    licença ou não participação).
    """
    dados = _get(f"/votacoes/{votacao_id}/votos").get("dados", [])
    for voto in dados:
        deputado = voto.get("deputado_") or {}
        if int(deputado.get("id") or 0) == int(id_camara):
            return voto.get("tipoVoto") or "Não registrado"
    return "Não registrado"


def montar_como_votou(id_camara: int, ano: int, limite: int = 10) -> pd.DataFrame:
    """Tabela: data, matéria/descrição e o voto do deputado nas últimas
    votações nominais do plenário no ano."""
    votacoes = listar_votacoes_nominais_plenario(ano, limite=limite)
    if votacoes.empty:
        return pd.DataFrame(columns=["data", "descricao", "voto", "link_fonte"])

    registros = []
    for _, v in votacoes.iterrows():
        voto = buscar_voto_do_deputado(v["id"], id_camara)
        registros.append({
            "data": v.get("data"),
            "descricao": v.get("descricao"),
            "voto": voto,
            "link_fonte": v.get("uri") or "https://dadosabertos.camara.leg.br/",
        })
        time.sleep(PAUSA_ENTRE_PAGINAS)
    return pd.DataFrame(registros)


# ----------------------------------------------------------------------
# Resumo consolidado (para dashboard)
# ----------------------------------------------------------------------

def gerar_resumo_atividade(id_camara: int, ano: int) -> dict:
    """Resumo factual da atividade parlamentar de um deputado em um ano.

    Retorna dados brutos e agregados, sem nota ou ranking (compliance TSE).
    """
    data_inicio, data_fim = f"{ano}-01-01", f"{ano}-12-31"

    detalhes = detalhar_deputado(id_camara)
    despesas = buscar_despesas_ceap(id_camara, ano)
    eventos = buscar_eventos_participados(id_camara, data_inicio, data_fim)
    discursos = buscar_discursos(id_camara, data_inicio, data_fim)
    proposicoes = buscar_proposicoes_autoria(id_camara, ano)

    tipos_proposicao = {}
    if not proposicoes.empty and "siglaTipo" in proposicoes.columns:
        tipos_proposicao = proposicoes["siglaTipo"].value_counts().to_dict()

    return {
        "deputado": detalhes,
        "ano": ano,
        "ceap": resumir_despesas_ceap(despesas),
        "sessoes_deliberativas_participadas": contar_sessoes_deliberativas(eventos),
        "eventos_participados_total": int(len(eventos)),
        "discursos": int(len(discursos)),
        "proposicoes_apresentadas": int(len(proposicoes)),
        "proposicoes_por_tipo": tipos_proposicao,
        "observacao_metodologica": (
            "Participação em sessões derivada dos eventos da API de Dados Abertos; "
            "não substitui o boletim oficial de frequência da Câmara."
        ),
        "fonte": "API Dados Abertos da Câmara dos Deputados",
    }


# ----------------------------------------------------------------------
# Persistência
# ----------------------------------------------------------------------

def salvar_atividade_no_banco(id_camara: int, ano: int) -> dict:
    """Coleta e persiste a atividade do ano no banco local. Retorna contagens."""
    resumo = gerar_resumo_atividade(id_camara, ano)
    despesas = buscar_despesas_ceap(id_camara, ano)

    conn = get_connection()
    cur = conn.cursor()
    try:
        dep = resumo["deputado"]
        cur.execute(
            """INSERT OR REPLACE INTO deputados_camara
               (id_camara, nome_civil, nome_parlamentar, partido, uf, situacao,
                condicao_eleitoral, url_foto, link_fonte)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                dep["id_camara"], dep["nome_civil"], dep["nome_parlamentar"],
                dep["partido"], dep["uf"], dep["situacao"],
                dep["condicao_eleitoral"], dep["url_foto"], dep["link_fonte"],
            ),
        )

        cur.execute(
            "DELETE FROM atividade_ceap WHERE id_camara = ? AND ano = ?",
            (int(id_camara), int(ano)),
        )
        inseridas = 0
        for _, linha in despesas.iterrows():
            cur.execute(
                """INSERT INTO atividade_ceap
                   (id_camara, ano, mes, tipo_despesa, fornecedor, cnpj_cpf_fornecedor,
                    valor_documento, valor_glosa, valor_liquido, url_documento)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(id_camara), int(linha.get("ano") or ano), int(linha.get("mes") or 0),
                    linha.get("tipoDespesa"), linha.get("nomeFornecedor"),
                    linha.get("cnpjCpfFornecedor"),
                    float(linha.get("valorDocumento") or 0),
                    float(linha.get("valorGlosa") or 0),
                    float(linha.get("valorLiquido") or 0),
                    linha.get("urlDocumento"),
                ),
            )
            inseridas += 1

        cur.execute(
            """INSERT OR REPLACE INTO atividade_resumo_anual
               (id_camara, ano, sessoes_participadas, eventos_participados,
                discursos, proposicoes, total_ceap_liquido, observacao)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                int(id_camara), int(ano),
                resumo["sessoes_deliberativas_participadas"],
                resumo["eventos_participados_total"],
                resumo["discursos"],
                resumo["proposicoes_apresentadas"],
                resumo["ceap"]["total_liquido"],
                resumo["observacao_metodologica"],
            ),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"Atividade {ano} do deputado {id_camara} salva ({inseridas} despesas CEAP).")
    return {"despesas_ceap": inseridas, "resumo": resumo}


if __name__ == "__main__":
    # Teste manual rápido (Adriana Ventura - SP, id 204528)
    resumo = gerar_resumo_atividade(204528, 2025)
    import json
    print(json.dumps(resumo, indent=2, ensure_ascii=False, default=str))
