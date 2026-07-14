"""
Radar Eleitoral IA - Coletor de atividade parlamentar (Câmara Municipal de
São Paulo - CMSP / vereadores).

RESULTADO DA INVESTIGAÇÃO (jul/2026): a CMSP expõe web services oficiais
com saída JSON (★★★★☆), sem chave. Dois serviços:

1. SPLEGIS - Sistema do Processo Legislativo
   Base: https://splegisws.saopaulo.sp.leg.br/ws/ws2.asmx
   Métodos usados (todos GET, sufixo JSON):
     - VereadoresCMSPJSON                      -> lista de vereadores (histórica)
     - PromoventesCMSPJSON                     -> autores (liga nome -> chave de promovente)
     - ProjetosEmTramitacaoPorPromoventeJSON?Codigo=  -> projetos em tramitação
     - LeisAprovadasPorPromoventeJSON?Codigo=  -> leis já aprovadas de autoria
     - ProjetosPorAnoJSON?ano=                 -> todos os projetos do ano

2. SisGV - Sistema de controle de custos de mandato
   Base: https://sisgvconsulta.saopaulo.sp.leg.br/ws/Servicos.asmx
   Método (POST form-urlencoded):
     - ObterDebitoVereadorJSON  (ano, mes)     -> despesas do mandato, item a item
       Campos: VEREADOR, DEPARTAMENTO, DESPESA, CNPJ, FORNECEDOR, VALOR, ANO, MES

IDENTIDADE: o vínculo entre os serviços é feito pelo NOME do vereador
(normalizado sem acento/caixa): nome na lista de vereadores == nome de
promovente (para projetos) == campo VEREADOR no SisGV (para gastos).

As respostas JSON vêm embrulhadas em XML (<string>...</string>); o parser
extrai o array/objeto interno.

Presença e votações de plenário existem, mas só via download XML por sessão
(fase futura). Aqui cobrimos: vereadores atuais, projetos, leis e gastos.

COMPLIANCE (Resolução TSE 23.755/2026): dados factuais, sem ranking.
"""

import json
import logging
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SPLEGIS = "https://splegisws.saopaulo.sp.leg.br/ws/ws2.asmx"
SISGV = "https://sisgvconsulta.saopaulo.sp.leg.br/ws/Servicos.asmx"
TIMEOUT = 60
HEADERS = {"User-Agent": "Mozilla/5.0 RadarEleitoral/1.0"}


def _criar_logger() -> logging.Logger:
    log = logging.getLogger("radar_eleitoral.camara_sp")
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("[CMSP] %(message)s"))
        log.addHandler(h)
    log.setLevel(logging.INFO)
    log.propagate = False
    return log


logger = _criar_logger()


def _sem_acento(texto: str) -> str:
    texto = str(texto or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _extrair_json(texto: str):
    """As respostas *JSON dos web services ora vêm puras, ora dentro de um
    <string> XML. Tenta os dois formatos."""
    texto = (texto or "").strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass
    m = re.search(r">(\[[\s\S]*\]|\{[\s\S]*\})<", texto)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return []

# Sistema de votações da CMSP (arquivos XML por data de sessão)
BLOB_VOTACOES = "https://splegispdarmazenamento.blob.core.windows.net/containersip"


def _get_splegis(metodo: str, params: dict = None) -> list:
    r = requests.get(f"{SPLEGIS}/{metodo}", params=params or {}, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    dados = _extrair_json(r.text)
    return dados if isinstance(dados, list) else [dados]


# ----------------------------------------------------------------------
# Vereadores e promoventes (identidade)
# ----------------------------------------------------------------------

def listar_vereadores() -> pd.DataFrame:
    """Lista os vereadores (base histórica da CMSP) com nome e chave."""
    dados = _get_splegis("VereadoresCMSPJSON")
    registros = [{
        "chave": v.get("chave"),
        "nome": v.get("nome"),
        "mandatos": v.get("mandatos") or [],
    } for v in dados]
    df = pd.DataFrame(registros)
    logger.info(f"{len(df)} vereador(es) na base da CMSP.")
    return df


def listar_vereadores_atuais(desde: str = "2025-01-01") -> pd.DataFrame:
    """Vereadores com mandato ativo na legislatura corrente.

    Considera atual quem tem mandato terminando no futuro ou iniciado a
    partir de `desde` (cobre titulares e suplentes empossados).
    """
    df = listar_vereadores()
    if df.empty:
        return df

    def _ativo(mandatos):
        for m in mandatos or []:
            fim = str(m.get("fim") or "9999")[:10]
            ini = str(m.get("inicio") or "")[:10]
            if fim >= desde or ini >= desde:
                return True
        return False

    atuais = df[df["mandatos"].map(_ativo)].copy()
    atuais = atuais.drop_duplicates("nome").sort_values("nome").reset_index(drop=True)
    logger.info(f"{len(atuais)} vereador(es) em exercício.")
    return atuais[["chave", "nome"]]


def _mapa_promoventes() -> dict:
    """nome normalizado -> chave de promovente (para consultar projetos/leis)."""
    dados = _get_splegis("PromoventesCMSPJSON")
    mapa = {}
    for p in dados:
        if re.search(r"VEREADOR", str((p.get("tipo") or {}).get("nome") or ""), re.I):
            mapa[_sem_acento(p.get("nome"))] = p.get("chave")
    return mapa


def _chave_promovente(nome: str) -> int | None:
    return _mapa_promoventes().get(_sem_acento(nome))


# ----------------------------------------------------------------------
# Produção legislativa
# ----------------------------------------------------------------------

def buscar_projetos_vereador(nome: str) -> dict:
    """Projetos em tramitação e leis aprovadas de autoria do vereador."""
    chave = _chave_promovente(nome)
    if not chave:
        return {"em_tramitacao": pd.DataFrame(), "leis_aprovadas": pd.DataFrame()}
    tram = pd.DataFrame(_get_splegis("ProjetosEmTramitacaoPorPromoventeJSON", {"Codigo": chave}))
    leis = pd.DataFrame(_get_splegis("LeisAprovadasPorPromoventeJSON", {"Codigo": chave}))
    logger.info(f"{nome}: {len(tram)} projeto(s) em tramitação, {len(leis)} lei(s) aprovada(s).")
    return {"em_tramitacao": tram, "leis_aprovadas": leis}


# ----------------------------------------------------------------------
# Verba de gabinete (SisGV)
# ----------------------------------------------------------------------

def _debito_mes(ano: int, mes: int) -> pd.DataFrame:
    r = requests.post(
        f"{SISGV}/ObterDebitoVereadorJSON",
        data={"ano": int(ano), "mes": int(mes)},
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    dados = _extrair_json(r.text)
    return pd.DataFrame(dados if isinstance(dados, list) else [dados])


def buscar_gastos_gabinete(nome: str, ano: int) -> pd.DataFrame:
    """Despesas do mandato do vereador no ano (verba de gabinete, SisGV).

    O SisGV entrega por mês (todos os vereadores); filtramos pelo nome.
    """
    alvo = _sem_acento(nome)
    partes = []
    for mes in range(1, 13):
        try:
            df_mes = _debito_mes(ano, mes)
        except Exception:
            continue
        if df_mes.empty or "VEREADOR" not in df_mes.columns:
            continue
        recorte = df_mes[df_mes["VEREADOR"].map(_sem_acento) == alvo]
        if not recorte.empty:
            partes.append(recorte)
    if not partes:
        return pd.DataFrame()
    df = pd.concat(partes, ignore_index=True)
    if "VALOR" in df.columns:
        df["VALOR"] = pd.to_numeric(df["VALOR"], errors="coerce").fillna(0.0)
    logger.info(f"{nome}: {len(df)} despesa(s) de gabinete em {ano}.")
    return df


def resumir_gastos_gabinete(df: pd.DataFrame) -> dict:
    if df is None or df.empty or "VALOR" not in df.columns:
        return {"total": 0.0, "por_tipo": {}, "por_mes": {}}
    return {
        "total": float(df["VALOR"].sum()),
        "por_tipo": df.groupby("DESPESA")["VALOR"].sum().sort_values(ascending=False).round(2).to_dict()
        if "DESPESA" in df.columns else {},
        "por_mes": df.groupby("MES")["VALOR"].sum().round(2).to_dict()
        if "MES" in df.columns else {},
    }


# ----------------------------------------------------------------------
# Votações nominais no plenário ("como votou")
# ----------------------------------------------------------------------

def listar_sessoes_plenarias(ano: int) -> list:
    """Datas das sessões plenárias do ano (via SPLEGIS)."""
    dados = _get_splegis("PautasSessoesPlenariasJSON", {"ano": int(ano)})
    datas = sorted({(s.get("data") or "")[:10] for s in dados if s.get("data")})
    return [d for d in datas if d]


def baixar_votacoes_ano(ano: int) -> pd.DataFrame:
    """Todas as votações NOMINAIS do plenário no ano, voto a voto.

    Percorre as datas de sessão e baixa o XML VOTACOES_DD_MM_AAAA.xml de cada
    uma. Retorna uma linha por (votação × vereador). É a base do "como votou"
    e também a fonte do partido atual de cada vereador.
    """
    registros = []
    for data in listar_sessoes_plenarias(ano):
        a, m, d = data.split("-")
        url = f"{BLOB_VOTACOES}/VOTACOES_{d}_{m}_{a}.xml"
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if not r.ok or len(r.content) < 300:
                continue
            raiz = ET.fromstring(r.content)
        except Exception:
            continue
        for votacao in raiz.iter("Votacao"):
            base = {
                "data": data,
                "materia": votacao.get("Materia") or "",
                "resultado": votacao.get("Resultado") or "",
                "presentes": votacao.get("Presentes") or "",
                "sim": votacao.get("Sim") or "",
                "nao": votacao.get("Nao") or "",
            }
            for ver in votacao.findall("Vereador"):
                registros.append({
                    **base,
                    "vereador": ver.get("Nome") or "",
                    "partido": ver.get("Partido") or "",
                    "voto": ver.get("Voto") or "",
                })
    df = pd.DataFrame(registros)
    logger.info(f"{df['data'].nunique() if not df.empty else 0} sessão(ões) com votação nominal em {ano}.")
    return df


def buscar_presencas_ano(ano: int) -> pd.DataFrame:
    """Presença de todos os vereadores nas sessões plenárias do ano.

    Cada linha = (vereador × sessão), com Presente/Ausente. Fonte: XML
    PRESENCAS_DD_MM_AAAA.xml por data de sessão.
    """
    registros = []
    for data in listar_sessoes_plenarias(ano):
        a, m, d = data.split("-")
        url = f"{BLOB_VOTACOES}/PRESENCAS_{d}_{m}_{a}.xml"
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if not r.ok or len(r.content) < 300:
                continue
            raiz = ET.fromstring(r.content)
        except Exception:
            continue
        for ver in raiz.iter("Vereador"):
            for sessao in ver.findall("Sessao"):
                registros.append({
                    "data": data,
                    "vereador": ver.get("Nome") or "",
                    "partido": ver.get("Partido") or "",
                    "sessao": sessao.get("Nome") or "",
                    "presenca": sessao.get("Presenca") or "",
                })
    df = pd.DataFrame(registros)
    logger.info(f"{df['data'].nunique() if not df.empty else 0} sessão(ões) com presença em {ano}.")
    return df


def resumir_presenca_vereador(nome: str, ano: int) -> dict:
    """'Participou de X de Y sessões (Z%)' para o vereador no ano."""
    df = buscar_presencas_ano(ano)
    if df.empty:
        return {"total_sessoes": 0, "presencas": 0, "percentual": None}
    total_sessoes = df.drop_duplicates(["data", "sessao"]).shape[0]
    alvo = _sem_acento(nome)
    dele = df[df["vereador"].map(_sem_acento) == alvo]
    presencas = int((dele["presenca"].str.strip().str.lower() == "presente").sum())
    pct = round(presencas / total_sessoes * 100, 1) if total_sessoes else None
    return {"total_sessoes": total_sessoes, "presencas": presencas, "percentual": pct}


def buscar_votacoes_vereador(nome: str, ano: int) -> pd.DataFrame:
    """Como o vereador votou nas votações nominais do ano."""
    df = baixar_votacoes_ano(ano)
    if df.empty:
        return df
    alvo = _sem_acento(nome)
    recorte = df[df["vereador"].map(_sem_acento) == alvo].copy()
    recorte = recorte.sort_values("data", ascending=False).reset_index(drop=True)
    logger.info(f"{nome}: {len(recorte)} voto(s) nominais em {ano}.")
    return recorte


def partido_atual_vereador(nome: str, ano: int = None) -> str:
    """Partido do vereador a partir das votações mais recentes (o SPLEGIS não
    expõe o partido atual de forma direta)."""
    from datetime import date
    ano = ano or date.today().year
    for tentativa in (ano, ano - 1):
        df = baixar_votacoes_ano(tentativa)
        if df.empty:
            continue
        alvo = _sem_acento(nome)
        recorte = df[df["vereador"].map(_sem_acento) == alvo]
        if not recorte.empty:
            partidos = recorte.sort_values("data")["partido"]
            ultimo = partidos[partidos.astype(str).str.strip() != ""]
            if len(ultimo):
                return ultimo.iloc[-1]
    return ""


def mapa_fotos_vereadores() -> dict:
    """nome normalizado -> URL da foto, extraído da página de membros da CMSP.

    Uma única requisição cobre todos os vereadores atuais (as fotos são
    uploads do WordPress com nome livre, sem padrão pela chave)."""
    try:
        r = requests.get(
            "https://www.saopaulo.sp.leg.br/vereadores/membros/",
            headers=HEADERS, timeout=TIMEOUT,
        )
        r.raise_for_status()
    except Exception:
        return {}

    html = r.text
    # cada card-vereador tem a foto (img.thumbnail) e o nome num <h3>:
    #   <img class="thumbnail" src="...uploads/....jpg" ...> ... <h3 ...>Nome</h3>
    mapa = {}
    for bloco in re.findall(r'card-vereador.*?</h3>', html, re.DOTALL):
        foto = re.search(r'thumbnail"\s+src="([^"]+wp-content/uploads/[^"]+\.(?:jpg|jpeg|png))"', bloco)
        nome = re.search(r'<h3[^>]*>([^<]+)</h3>', bloco)
        if foto and nome:
            mapa[_sem_acento(nome.group(1))] = foto.group(1)
    logger.info(f"{len(mapa)} foto(s) de vereadores mapeada(s).")
    return mapa


def foto_vereador(nome: str, mapa: dict = None) -> str:
    """Foto do vereador pelo nome (casamento tolerante a acento/caixa)."""
    mapa = mapa if mapa is not None else mapa_fotos_vereadores()
    alvo = _sem_acento(nome)
    if alvo in mapa:
        return mapa[alvo]
    # casamento parcial: primeiro e último termo do nome
    termos = alvo.split()
    for chave_nome, url in mapa.items():
        if termos and termos[0] in chave_nome and termos[-1] in chave_nome:
            return url
    return ""


def detalhar_vereador(nome: str, chave=None) -> dict:
    return {
        "nome_parlamentar": nome,
        "partido": None,  # SPLEGIS não expõe partido atual de forma estável
        "uf": "SP",
        "cargo": "Vereador(a) - São Paulo",
        "fonte": "Câmara Municipal de São Paulo (SPLEGIS / SisGV)",
        "link_fonte": "https://www.saopaulo.sp.leg.br/vereadores/membros",
    }


if __name__ == "__main__":
    atuais = listar_vereadores_atuais()
    print(atuais.head(10).to_string())
    if not atuais.empty:
        nome = atuais.iloc[0]["nome"]
        print(f"\n[TESTE] {nome}")
        proj = buscar_projetos_vereador(nome)
        print(f"  em tramitação: {len(proj['em_tramitacao'])} | leis: {len(proj['leis_aprovadas'])}")
        gastos = buscar_gastos_gabinete(nome, 2025)
        print(f"  gastos 2025: {resumir_gastos_gabinete(gastos)['total']:.2f}")
