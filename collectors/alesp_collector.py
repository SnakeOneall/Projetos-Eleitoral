"""
Radar Eleitoral IA - Coletor de atividade parlamentar (ALESP - Deputados
Estaduais de São Paulo).

Fonte oficial: Portal de Dados Abertos da ALESP (público, sem chave)
https://www.al.sp.gov.br/dados-abertos/

Arquivos usados (verificados em jul/2026):
  - deputados.xml (legislatura atual, atualização diária):
      https://www.al.sp.gov.br/repositorioDados/deputados/deputados.xml
  - despesas_gabinetes_{ano}.xml (verba de gabinete desde 2002):
      https://www.al.sp.gov.br/repositorioDados/deputados/despesas_gabinetes_{ano}.xml
  - comissoes_permanentes_presencas.xml (presenças desde 2005, ~8 MB):
      https://www.al.sp.gov.br/repositorioDados/processo_legislativo/comissoes_permanentes_presencas.xml

Fase 2 (arquivos grandes, exigem ETL offline):
  - proposituras.zip + documento_autor.zip (autoria de projetos)
  - comissoes_permanentes_votacoes.xml (~64 MB, votos em comissões)
  - Emendas estaduais: não estão nos dados abertos da ALESP (orçamento
    estadual/SIGEO-SP).

COMPLIANCE (Resolução TSE 23.755/2026): dados exibidos de forma factual,
sem ranking, nota ou recomendação de candidatos.
"""

import logging
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE_DEPUTADOS = "https://www.al.sp.gov.br/repositorioDados/deputados"
BASE_PROCESSO = "https://www.al.sp.gov.br/repositorioDados/processo_legislativo"
TIMEOUT = 120

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "alesp_raw"


def _criar_logger() -> logging.Logger:
    logger_alesp = logging.getLogger("radar_eleitoral.alesp")
    if not logger_alesp.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[ALESP] %(message)s"))
        logger_alesp.addHandler(handler)
    logger_alesp.setLevel(logging.INFO)
    logger_alesp.propagate = False
    return logger_alesp


logger = _criar_logger()


def _baixar_xml(url: str, nome_cache: str, usar_cache: bool = True) -> ET.Element:
    """Baixa um XML (com cache local em data/alesp_raw) e retorna a raiz."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    arquivo = CACHE_DIR / nome_cache
    if not (usar_cache and arquivo.exists()):
        logger.info(f"Baixando {url}...")
        resposta = requests.get(url, timeout=TIMEOUT)
        resposta.raise_for_status()
        arquivo.write_bytes(resposta.content)
    return ET.fromstring(arquivo.read_bytes())


def _elemento_para_dict(elemento: ET.Element) -> dict:
    return {filho.tag: (filho.text or "").strip() for filho in elemento}


# ----------------------------------------------------------------------
# Deputados estaduais em exercício
# ----------------------------------------------------------------------

def listar_deputados_alesp() -> pd.DataFrame:
    """Deputados estaduais de SP da legislatura atual (deputados.xml)."""
    raiz = _baixar_xml(f"{BASE_DEPUTADOS}/deputados.xml", "deputados.xml")
    registros = [_elemento_para_dict(dep) for dep in raiz]
    df = pd.DataFrame(registros)
    if not df.empty and "NomeParlamentar" in df.columns:
        df = df.sort_values("NomeParlamentar").reset_index(drop=True)
    logger.info(f"{len(df)} deputado(s) estadual(is) na legislatura atual.")
    return df


def detalhar_deputado_alesp(linha: dict) -> dict:
    """Normaliza os campos do deputados.xml para o formato do painel."""
    id_dep = str(linha.get("IdDeputado") or "").strip()
    situacao_codigo = (linha.get("Situacao") or "").strip().upper()
    situacao = {
        "EXE": "Em exercício",
        "LIC": "Licenciado",
        "AFA": "Afastado",
    }.get(situacao_codigo, situacao_codigo or "—")
    return {
        "id_alesp": id_dep,
        "id_spl": str(linha.get("IdSPL") or "").strip(),
        "matricula": str(linha.get("Matricula") or "").strip(),
        "nome_parlamentar": linha.get("NomeParlamentar") or linha.get("nome"),
        "partido": linha.get("Partido") or linha.get("partido"),
        "uf": "SP",
        "situacao": situacao,
        "email": linha.get("Email"),
        "base_eleitoral": linha.get("txtBaseEleitoral") or "",
        "areas_atuacao": linha.get("txtAreaAtuacao") or "",
        "url_foto": linha.get("PathFoto") or linha.get("Foto") or "",
        "fonte": "Dados Abertos ALESP",
        "link_fonte": f"https://www.al.sp.gov.br/deputado/?matricula={linha.get('Matricula')}"
        if linha.get("Matricula") else "https://www.al.sp.gov.br/",
    }


# ----------------------------------------------------------------------
# Verba de gabinete (despesas desde 2002)
# ----------------------------------------------------------------------

def buscar_despesas_gabinete(matricula: str, anos: list) -> pd.DataFrame:
    """Despesas de gabinete do deputado nos anos pedidos (uma consulta por ano).

    O vínculo é feito pela matrícula (campo Matricula nos dois arquivos).
    """
    matricula = str(matricula).strip()
    partes = []
    for ano in anos:
        try:
            raiz = _baixar_xml(
                f"{BASE_DEPUTADOS}/despesas_gabinetes_{int(ano)}.xml",
                f"despesas_gabinetes_{int(ano)}.xml",
            )
        except Exception as exc:
            logger.info(f"Despesas de {ano} indisponíveis: {exc}")
            continue
        registros = [_elemento_para_dict(d) for d in raiz]
        df_ano = pd.DataFrame(registros)
        if df_ano.empty:
            continue
        if "Matricula" in df_ano.columns:
            df_ano = df_ano[df_ano["Matricula"].astype(str).str.strip() == matricula]
        partes.append(df_ano)

    if not partes:
        return pd.DataFrame()

    df = pd.concat(partes, ignore_index=True)
    if "Valor" in df.columns:
        df["Valor"] = pd.to_numeric(
            df["Valor"].astype(str).str.replace(",", ".", regex=False), errors="coerce"
        ).fillna(0.0)
    for col in ("Ano", "Mes"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    logger.info(f"{len(df)} despesa(s) de gabinete da matrícula {matricula} em {anos}.")
    return df


def resumir_despesas_gabinete(df_despesas: pd.DataFrame) -> dict:
    """Agrega a verba de gabinete por tipo e por ano."""
    if df_despesas is None or df_despesas.empty or "Valor" not in df_despesas.columns:
        return {"total_liquido": 0.0, "por_tipo": {}, "por_ano": {}}
    return {
        "total_liquido": float(df_despesas["Valor"].sum()),
        "por_tipo": df_despesas.groupby("Tipo")["Valor"].sum().sort_values(ascending=False).round(2).to_dict()
        if "Tipo" in df_despesas.columns else {},
        "por_ano": df_despesas.groupby("Ano")["Valor"].sum().round(2).to_dict()
        if "Ano" in df_despesas.columns else {},
    }


# ----------------------------------------------------------------------
# Presença em comissões permanentes (desde 2005)
# ----------------------------------------------------------------------

def buscar_presencas_comissoes(
    id_deputado: str,
    ano_inicio: int,
    ano_fim: int,
    id_spl: str = None,
    nome: str = None,
) -> pd.DataFrame:
    """Presenças do deputado em reuniões de comissões no período.

    O campo IdDeputado do arquivo usa identificadores diferentes conforme a
    época (registros recentes usam o IdSPL do deputados.xml; antigos usam
    outro id). Por isso o vínculo aceita IdDeputado, IdSPL e, como reforço,
    o nome parlamentar.

    Observação: o arquivo cobre COMISSÕES PERMANENTES (não é a presença em
    sessões do plenário, que a ALESP não publica em dados abertos).
    """
    raiz = _baixar_xml(
        f"{BASE_PROCESSO}/comissoes_permanentes_presencas.xml",
        "comissoes_permanentes_presencas.xml",
    )
    registros = [_elemento_para_dict(p) for p in raiz]
    df = pd.DataFrame(registros)
    if df.empty:
        return df

    ids_validos = {str(id_deputado).strip()}
    if id_spl:
        ids_validos.add(str(id_spl).strip())
    mask = df["IdDeputado"].astype(str).str.strip().isin(ids_validos)
    if nome and "Deputado" in df.columns:
        alvo = str(nome).strip().casefold()
        mask = mask | (df["Deputado"].astype(str).str.strip().str.casefold() == alvo)
    df = df[mask]
    if "DataReuniao" in df.columns:
        df["ano"] = pd.to_numeric(df["DataReuniao"].astype(str).str.slice(0, 4), errors="coerce")
        df = df[(df["ano"] >= int(ano_inicio)) & (df["ano"] <= int(ano_fim))]
    df = df.reset_index(drop=True)
    logger.info(
        f"{len(df)} presença(s) em comissões do deputado {id_deputado} "
        f"({ano_inicio}-{ano_fim})."
    )
    return df


def nomes_comissoes() -> dict:
    """Mapa sigla -> nome completo das comissões (ex.: CDH -> Comissão de
    Direitos Humanos), para a interface não exibir apenas siglas."""
    raiz = _baixar_xml(f"{BASE_PROCESSO}/comissoes.xml", "comissoes.xml")
    mapa = {}
    for c in raiz:
        dados = _elemento_para_dict(c)
        sigla = (dados.get("SiglaComissao") or "").strip()
        nome = (dados.get("NomeComissao") or "").strip()
        if sigla and nome:
            mapa[sigla] = nome
    return mapa


# As reuniões concluídas aparecem como "REALIZADA" (registros recentes) ou
# "ENCERRADA" (legislaturas antigas) no arquivo oficial.
_SITUACOES_REUNIAO_CONCLUIDA = {"REALIZADA", "ENCERRADA"}


def contar_reunioes_comissoes(siglas: list, ano_inicio: int, ano_fim: int) -> int:
    """Total de reuniões realizadas das comissões informadas no período.

    Denominador justo para a presença: considera apenas as comissões em que
    o deputado atuou (ninguém participa de todas as comissões da casa).
    """
    if not siglas:
        return 0
    raiz_com = _baixar_xml(f"{BASE_PROCESSO}/comissoes.xml", "comissoes.xml")
    sigla_por_id = {}
    for c in raiz_com:
        dados = _elemento_para_dict(c)
        sigla_por_id[dados.get("IdComissao", "")] = dados.get("SiglaComissao", "")

    raiz_reu = _baixar_xml(
        f"{BASE_PROCESSO}/comissoes_permanentes_reunioes.xml",
        "comissoes_permanentes_reunioes.xml",
    )
    alvo = {str(s).strip().upper() for s in siglas}
    total = 0
    for r in raiz_reu:
        dados = _elemento_para_dict(r)
        if (dados.get("Situacao") or "").upper() not in _SITUACOES_REUNIAO_CONCLUIDA:
            continue
        ano = str(dados.get("Data") or "")[:4]
        if not (ano.isdigit() and int(ano_inicio) <= int(ano) <= int(ano_fim)):
            continue
        sigla = (sigla_por_id.get(dados.get("IdComissao", "")) or "").strip().upper()
        if sigla in alvo:
            total += 1
    logger.info(f"{total} reunião(ões) encerradas das comissões {sorted(alvo)} em {ano_inicio}-{ano_fim}.")
    return total


# ----------------------------------------------------------------------
# Votos nas comissões (lê o compacto gerado pelo ETL offline)
# ----------------------------------------------------------------------

PROCESSED_VOTACOES = Path(__file__).resolve().parent.parent / "data" / "processed" / "alesp_votacoes_comissoes.csv.gz"


def buscar_votos_comissoes(
    id_deputado: str,
    ano_inicio: int,
    ano_fim: int,
    id_spl: str = None,
    nome: str = None,
):
    """Votos do deputado nas comissões, a partir do compacto do ETL.

    Retorna None se o ETL ainda não foi executado (arquivo ausente).
    Gerar/atualizar com: python scripts/etl_alesp_votacoes.py
    """
    if not PROCESSED_VOTACOES.exists():
        return None
    df = pd.read_csv(PROCESSED_VOTACOES, dtype={"id_deputado": str, "id_documento": str})

    ids_validos = {str(id_deputado).strip()}
    if id_spl:
        ids_validos.add(str(id_spl).strip())
    mask = df["id_deputado"].astype(str).str.strip().isin(ids_validos)
    if nome and "deputado" in df.columns:
        alvo = str(nome).strip().casefold()
        mask = mask | (df["deputado"].astype(str).str.strip().str.casefold() == alvo)
    df = df[mask]

    df = df[(df["ano"] >= int(ano_inicio)) & (df["ano"] <= int(ano_fim))]
    df = df.sort_values("data_reuniao", ascending=False).reset_index(drop=True)
    logger.info(f"{len(df)} voto(s) em comissões do deputado {id_deputado} ({ano_inicio}-{ano_fim}).")
    return df


if __name__ == "__main__":
    # Teste manual rápido
    deputados = listar_deputados_alesp()
    print(deputados[["IdDeputado", "Matricula", "NomeParlamentar", "Partido"]].head())
    if not deputados.empty:
        primeiro = deputados.iloc[0].to_dict()
        detalhes = detalhar_deputado_alesp(primeiro)
        print(f"\n[TESTE] {detalhes['nome_parlamentar']} ({detalhes['partido']})")
        despesas = buscar_despesas_gabinete(detalhes["matricula"], [2023, 2024, 2025])
        print(resumir_despesas_gabinete(despesas))
        presencas = buscar_presencas_comissoes(detalhes["id_alesp"], 2023, 2026)
        print(f"[TESTE] {len(presencas)} presenças em comissões no mandato atual.")
