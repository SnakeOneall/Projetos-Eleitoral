"""
Radar Eleitoral IA - Coletor de atividade parlamentar (Senado Federal).

Fontes oficiais (públicas, sem chave):
  - API Legis do Senado: https://legis.senado.leg.br/dadosabertos
      GET /senador/lista/atual          -> senadores em exercício
      GET /senador/{codigo}             -> detalhes do senador
      GET /senador/{codigo}/autorias    -> matérias de autoria (?ano=)
      GET /senador/{codigo}/votacoes    -> votações nominais COM o voto (?ano=)
  - CEAPS (Cota para Exercício da Atividade Parlamentar dos Senadores):
      CSV anual em https://www.senado.leg.br/transparencia/LAI/verba/
      (despesa_ceaps_{ano}.csv, separador ';', encoding latin-1)

Verificado em jul/2026.

COMPLIANCE (Resolução TSE 23.755/2026): dados exibidos de forma factual,
sem ranking, nota ou recomendação de candidatos.
"""

import logging
import sys
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

API_BASE = "https://legis.senado.leg.br/dadosabertos"
CEAPS_URL = "https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv"
TIMEOUT = 60

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "senado_raw"


def _criar_logger() -> logging.Logger:
    logger_senado = logging.getLogger("radar_eleitoral.senado")
    if not logger_senado.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[SENADO] %(message)s"))
        logger_senado.addHandler(handler)
    logger_senado.setLevel(logging.INFO)
    logger_senado.propagate = False
    return logger_senado


logger = _criar_logger()


def _get_json(endpoint: str, params: dict = None) -> dict:
    resposta = requests.get(
        f"{API_BASE}{endpoint}",
        params=params or {},
        headers={"Accept": "application/json"},
        timeout=TIMEOUT,
    )
    resposta.raise_for_status()
    return resposta.json()


def _como_lista(valor) -> list:
    """A API do Senado retorna item único como dict; normaliza para lista."""
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


# ----------------------------------------------------------------------
# Senadores
# ----------------------------------------------------------------------

def listar_senadores() -> pd.DataFrame:
    """Senadores em exercício, com código, nome, partido e UF."""
    dados = _get_json("/senador/lista/atual")
    parlamentares = _como_lista(
        dados.get("ListaParlamentarEmExercicio", {})
        .get("Parlamentares", {})
        .get("Parlamentar", [])
    )
    registros = []
    for p in parlamentares:
        ident = p.get("IdentificacaoParlamentar", {})
        registros.append({
            "codigo": ident.get("CodigoParlamentar"),
            "nome": ident.get("NomeParlamentar"),
            "nome_completo": ident.get("NomeCompletoParlamentar"),
            "partido": ident.get("SiglaPartidoParlamentar"),
            "uf": ident.get("UfParlamentar"),
            "url_foto": ident.get("UrlFotoParlamentar"),
            "url_pagina": ident.get("UrlPaginaParlamentar"),
            "email": ident.get("EmailParlamentar"),
        })
    df = pd.DataFrame(registros)
    logger.info(f"{len(df)} senador(es) em exercício retornado(s) pela API.")
    return df


def detalhar_senador(codigo: int) -> dict:
    """Detalhes do senador (mandato, filiação, página oficial)."""
    dados = _get_json(f"/senador/{int(codigo)}")
    parlamentar = dados.get("DetalheParlamentar", {}).get("Parlamentar", {})
    ident = parlamentar.get("IdentificacaoParlamentar", {})
    return {
        "codigo": ident.get("CodigoParlamentar"),
        "nome_parlamentar": ident.get("NomeParlamentar"),
        "nome_civil": ident.get("NomeCompletoParlamentar"),
        "partido": ident.get("SiglaPartidoParlamentar"),
        "uf": ident.get("UfParlamentar"),
        "url_foto": ident.get("UrlFotoParlamentar"),
        "fonte": "API Dados Abertos Senado Federal",
        "link_fonte": ident.get("UrlPaginaParlamentar")
        or f"https://www25.senado.leg.br/web/senadores/senador/-/perfil/{ident.get('CodigoParlamentar')}",
    }


# ----------------------------------------------------------------------
# Votações nominais (já vêm com o voto do senador)
# ----------------------------------------------------------------------

def buscar_votacoes_senador(codigo: int, ano: int, ano_fim: int = None) -> pd.DataFrame:
    """Votações nominais do senador, com o voto dele em cada uma.

    Se `ano_fim` for informado, retorna o intervalo [ano, ano_fim]
    (útil para a visão por mandato/legislatura).
    """
    dados = _get_json(f"/senador/{int(codigo)}/votacoes", {"ano": int(ano)})
    votacoes = _como_lista(
        dados.get("VotacaoParlamentar", {})
        .get("Parlamentar", {})
        .get("Votacoes", {})
        .get("Votacao", [])
    )
    registros = []
    for v in votacoes:
        materia = v.get("Materia", {}) or {}
        sessao = v.get("SessaoPlenaria", {}) or {}
        registros.append({
            "data": sessao.get("DataSessao"),
            "materia": materia.get("DescricaoIdentificacaoMateria") or "",
            "descricao": (v.get("DescricaoVotacao") or "").strip(),
            "voto": (v.get("DescricaoVoto") or v.get("SiglaDescricaoVoto") or "").strip(),
        })
    df = pd.DataFrame(registros)
    if not df.empty:
        # A API nem sempre respeita o parâmetro ?ano= — garante o recorte aqui.
        anos_validos = df["data"].astype(str).str.slice(0, 4)
        anos_validos = pd.to_numeric(anos_validos, errors="coerce")
        fim = int(ano_fim) if ano_fim else int(ano)
        df = df[(anos_validos >= int(ano)) & (anos_validos <= fim)]
        df = df.sort_values("data", ascending=False).reset_index(drop=True)
    logger.info(f"{len(df)} votação(ões) nominais do senador {codigo} ({ano}-{ano_fim or ano}).")
    return df


# ----------------------------------------------------------------------
# Autorias
# ----------------------------------------------------------------------

def buscar_autorias_senador(codigo: int, ano: int = None) -> pd.DataFrame:
    """Matérias de autoria do senador (PLs, PECs, requerimentos, emendas)."""
    params = {"ano": int(ano)} if ano else {}
    dados = _get_json(f"/senador/{int(codigo)}/autorias", params)
    raiz = next(iter(dados.values()), {}) if isinstance(dados, dict) else {}
    autorias = _como_lista(
        (raiz.get("Parlamentar", {}) or {}).get("Autorias", {}).get("Autoria", [])
    )
    registros = []
    for a in autorias:
        materia = a.get("Materia", {}) or {}
        registros.append({
            "materia": materia.get("DescricaoIdentificacaoMateria"),
            "sigla": materia.get("SiglaSubtipoMateria"),
            "ano": materia.get("AnoMateria"),
            "ementa": materia.get("EmentaMateria") or "",
        })
    df = pd.DataFrame(registros)
    # Nota: o ano da matéria (AnoMateria) pode diferir do ano da autoria;
    # confiamos no parâmetro ?ano= da API para o recorte temporal.
    logger.info(f"{len(df)} autoria(s) do senador {codigo}.")
    return df


# ----------------------------------------------------------------------
# CEAPS - despesas dos senadores
# ----------------------------------------------------------------------

def _baixar_ceaps_ano(ano: int) -> pd.DataFrame:
    """Baixa (com cache local em data/senado_raw) o CSV anual do CEAPS."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    arquivo = CACHE_DIR / f"despesa_ceaps_{ano}.csv"

    if not arquivo.exists():
        url = CEAPS_URL.format(ano=int(ano))
        logger.info(f"Baixando CEAPS {ano} de {url}...")
        resposta = requests.get(url, timeout=TIMEOUT)
        resposta.raise_for_status()
        arquivo.write_bytes(resposta.content)

    texto = arquivo.read_text(encoding="latin-1", errors="replace")
    # A primeira linha é um título ("ULTIMA ATUALIZACAO..."); o cabeçalho vem depois.
    linhas = texto.splitlines()
    inicio = next((i for i, l in enumerate(linhas) if "SENADOR" in l.upper()), 0)
    df = pd.read_csv(StringIO("\n".join(linhas[inicio:])), sep=";", quotechar='"')
    df.columns = [c.strip().upper() for c in df.columns]
    if "VALOR_REEMBOLSADO" in df.columns:
        df["VALOR_REEMBOLSADO"] = (
            df["VALOR_REEMBOLSADO"].astype(str).str.replace(",", ".", regex=False)
        )
        df["VALOR_REEMBOLSADO"] = pd.to_numeric(df["VALOR_REEMBOLSADO"], errors="coerce").fillna(0.0)
    return df


def buscar_despesas_ceaps(nome_senador: str, ano: int) -> pd.DataFrame:
    """Despesas CEAPS do senador no ano (filtro por nome parlamentar)."""
    df = _baixar_ceaps_ano(ano)
    if df.empty or "SENADOR" not in df.columns:
        return pd.DataFrame()
    alvo = str(nome_senador).strip().upper()
    recorte = df[df["SENADOR"].astype(str).str.upper().str.strip() == alvo].copy()
    if recorte.empty:
        # tentativa por conteúdo parcial (nomes compostos)
        recorte = df[df["SENADOR"].astype(str).str.upper().str.contains(alvo, na=False, regex=False)].copy()
    logger.info(f"{len(recorte)} despesa(s) CEAPS de {nome_senador} em {ano}.")
    return recorte


def resumir_despesas_ceaps(df_despesas: pd.DataFrame) -> dict:
    """Agrega o CEAPS do senador por tipo de despesa e por mês."""
    if df_despesas is None or df_despesas.empty:
        return {"total_liquido": 0.0, "por_tipo": {}, "por_mes": {}}
    df = df_despesas.copy()
    col_valor = "VALOR_REEMBOLSADO"
    col_tipo = "TIPO_DESPESA"
    col_mes = "MES"
    return {
        "total_liquido": float(df[col_valor].sum()),
        "por_tipo": df.groupby(col_tipo)[col_valor].sum().sort_values(ascending=False).round(2).to_dict()
        if col_tipo in df.columns else {},
        "por_mes": df.groupby(col_mes)[col_valor].sum().round(2).to_dict()
        if col_mes in df.columns else {},
    }


if __name__ == "__main__":
    # Teste manual rápido
    senadores = listar_senadores()
    print(senadores.head())
    if not senadores.empty:
        cod = int(senadores.iloc[0]["codigo"])
        nome = senadores.iloc[0]["nome"]
        print(f"\n[TESTE] Votações 2025 de {nome}:")
        print(buscar_votacoes_senador(cod, 2025).head())
        print(f"\n[TESTE] CEAPS 2025 de {nome}:")
        despesas = buscar_despesas_ceaps(nome, 2025)
        print(resumir_despesas_ceaps(despesas))
