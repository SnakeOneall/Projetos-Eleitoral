"""
Radar Eleitoral IA - Coletor de emendas e verbas públicas.

No MVP, a importação é feita por CSV manual (Portal da Transparência,
SIGA Brasil, Transferegov não têm API simples e estável para uso
direto). A estrutura já deixa pronta a função de validação de vínculo
parlamentar/candidato para reduzir falsos positivos de atribuição.
"""

import logging
import os
import re
import unicodedata

import pandas as pd
import requests

from config.sources import get as get_fonte_oficial
from database.db_utils import inserir_emenda, buscar_emendas_por_parlamentar as _buscar_emendas_db, buscar_emendas as _buscar_emendas_filtros
from database.init_db import get_connection


def _criar_logger_emendas() -> logging.Logger:
    logger_emendas = logging.getLogger("radar_eleitoral.emendas")
    if not logger_emendas.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[EMENDAS] %(message)s"))
        logger_emendas.addHandler(handler)
    logger_emendas.setLevel(logging.INFO)
    logger_emendas.propagate = False
    return logger_emendas


logger = _criar_logger_emendas()

COLUNAS_ESPERADAS = [
    "parlamentar_nome", "parlamentar_nome_civil", "parlamentar_nome_urna",
    "partido", "uf", "ano", "municipio_beneficiado", "codigo_ibge", "area",
    "orgao", "entidade_beneficiada", "valor_empenhado", "valor_liquidado",
    "valor_pago", "fonte", "link_fonte",
]

COLUNAS_VALOR = ["valor_empenhado", "valor_liquidado", "valor_pago"]


# Mapa nome do estado (sem acento, maiúsculo) -> sigla, para interpretar
# o campo localidadeDoGasto da API (ex.: "SÃO PAULO (UF)" -> uf SP).
_UF_POR_NOME = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM",
    "BAHIA": "BA", "CEARA": "CE", "DISTRITO FEDERAL": "DF",
    "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA",
    "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG",
    "PARA": "PA", "PARAIBA": "PB", "PARANA": "PR", "PERNAMBUCO": "PE",
    "PIAUI": "PI", "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN",
    "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO", "RORAIMA": "RR",
    "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SERGIPE": "SE",
    "TOCANTINS": "TO",
}

_SIGLAS_UF = set(_UF_POR_NOME.values())


def _parse_localidade_do_gasto(texto) -> tuple:
    """Interpreta o campo localidadeDoGasto da API do Portal da Transparência.

    Formatos observados na API real (jul/2026):
      - "LONDRINA - PR"      -> município + UF
      - "SÃO PAULO (UF)"     -> apenas UF (emenda estadual)
      - "Nacional"           -> sem localidade específica
      - "MÚLTIPLO"           -> várias localidades

    Retorna (municipio, uf) — strings vazias quando não aplicável.
    """
    texto = str(texto or "").strip()
    if not texto:
        return "", ""

    chave = _normalizar_texto(texto).upper()
    if chave in {"NACIONAL", "MULTIPLO"}:
        return "", ""

    if texto.upper().endswith("(UF)"):
        nome_estado = _normalizar_texto(texto[: texto.upper().rfind("(UF)")]).upper().strip()
        return "", _UF_POR_NOME.get(nome_estado, "")

    if " - " in texto:
        municipio, _, uf = texto.rpartition(" - ")
        uf = uf.strip().upper()
        if uf in _SIGLAS_UF:
            return municipio.strip(), uf

    return texto, ""


def _primeiro_valor(dado: dict, caminhos: list, padrao=""):
    """Retorna o primeiro valor encontrado em caminhos simples ou aninhados."""
    for caminho in caminhos:
        atual = dado
        for parte in caminho.split("."):
            if isinstance(atual, dict) and parte in atual:
                atual = atual[parte]
            else:
                atual = None
                break
        if atual not in (None, ""):
            return atual
    return padrao


def normalizar_resposta_portal_transparencia(dados: list | dict) -> pd.DataFrame:
    """Converte a resposta bruta da API para o formato interno de emendas."""
    if isinstance(dados, dict):
        for chave in ("data", "dados", "items", "itens", "content", "resultado"):
            if isinstance(dados.get(chave), list):
                dados = dados[chave]
                break
        else:
            dados = [dados]

    registros = []
    for item in dados or []:
        codigo = _primeiro_valor(item, ["codigo", "id", "codigoEmenda", "emenda.codigo"])
        # localidadeDoGasto é o único campo de localidade na API real de emendas
        # (ex.: "LONDRINA - PR", "SÃO PAULO (UF)", "Nacional", "MÚLTIPLO").
        municipio_loc, uf_loc = _parse_localidade_do_gasto(
            _primeiro_valor(item, ["localidadeDoGasto", "localidade.nome"])
        )
        registro = {
            "parlamentar_nome": _primeiro_valor(item, ["autor", "nomeAutor", "parlamentar.nome", "autorEmenda.nome"]),
            "parlamentar_nome_civil": _primeiro_valor(item, ["nomeAutor", "parlamentar.nome", "autorEmenda.nome"]),
            "parlamentar_nome_urna": _primeiro_valor(item, ["nomeAutor", "parlamentar.nome", "autorEmenda.nome"]),
            "partido": _primeiro_valor(item, ["partido", "siglaPartido", "parlamentar.siglaPartido"]),
            "uf": _primeiro_valor(item, ["uf", "siglaUf", "parlamentar.uf", "localidade.uf"]) or uf_loc,
            "ano": _primeiro_valor(item, ["ano", "anoEmenda", "exercicio"]),
            "municipio_beneficiado": _primeiro_valor(item, ["municipio", "municipioBeneficiado", "localidade.nomeMunicipio", "beneficiario.municipio"]) or municipio_loc,
            "codigo_ibge": _primeiro_valor(item, ["codigoIBGE", "codigoIbge", "localidade.codigoIBGE", "beneficiario.codigoIBGE"]),
            "area": _primeiro_valor(item, ["area", "funcao", "funcao.nome", "subfuncao.nome"]),
            "orgao": _primeiro_valor(item, ["orgao", "orgao.nome", "orgaoSuperior.nome"]),
            "entidade_beneficiada": _primeiro_valor(item, ["favorecido", "beneficiario.nome", "entidadeBeneficiada", "nomeFavorecido"]),
            "valor_empenhado": _primeiro_valor(item, ["valorEmpenhado", "valor_empenhado"], 0),
            "valor_liquidado": _primeiro_valor(item, ["valorLiquidado", "valor_liquidado"], 0),
            "valor_pago": _primeiro_valor(item, ["valorPago", "valor_pago"], 0),
            "fonte": "Portal da Transparencia",
            "link_fonte": f"https://portaldatransparencia.gov.br/emendas/detalhe?codigo={codigo}" if codigo else get_fonte_oficial("portal_transparencia", "consulta_emendas"),
        }
        registros.append(registro)

    return normalizar_emendas(pd.DataFrame(registros, columns=COLUNAS_ESPERADAS))


def normalizar_emendas_portal_transparencia(dados) -> pd.DataFrame:
    """Alias tolerante para normalizar dados do Portal da Transparencia."""
    if isinstance(dados, pd.DataFrame):
        colunas_norm = {_normalizar_texto(c, manter_espaco=False) for c in dados.columns}
        if not (set(COLUNAS_ESPERADAS) & colunas_norm):
            return normalizar_resposta_portal_transparencia(dados.to_dict(orient="records"))
        df = normalizar_emendas(dados)
        for coluna in COLUNAS_ESPERADAS:
            if coluna not in df.columns:
                df[coluna] = ""
        return df
    return normalizar_resposta_portal_transparencia(dados)


def _carregar_token_portal(token: str | None = None) -> str | None:
    if token:
        return token
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass
    token = os.getenv("PORTAL_TRANSPARENCIA_API_KEY")
    if token:
        return token
    try:
        from config.secrets_local import PORTAL_TRANSPARENCIA_API_KEY

        return PORTAL_TRANSPARENCIA_API_KEY
    except ImportError:
        return None


def _df_emendas_vazio(status: str = "") -> pd.DataFrame:
    df = pd.DataFrame(columns=COLUNAS_ESPERADAS)
    if status:
        df.attrs["status_consulta"] = status
    return df


def buscar_emendas_portal_transparencia(
    token: str = None,
    codigo_ibge: str = None,
    ano: int = None,
    pagina: int = 1,
    municipio: str = None,
    uf: str = None,
    autor: str = None,
    nivel: str = "municipal",
) -> pd.DataFrame:
    """Busca emendas parlamentares diretamente na API do Portal da Transparência.

    Requer um token de API (gratuito, mediante cadastro de e-mail em
    https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email).
    O token deve ser passado no header HTTP "chave-api-dados".

    Se `token` não for informado, tenta carregar automaticamente de
    config/secrets_local.py (PORTAL_TRANSPARENCIA_API_KEY) — esse arquivo
    é local e ignorado pelo git (.gitignore), nunca deve ser commitado.

    Esta função é a evolução natural de `importar_emendas_csv` para a Fase 2
    do roadmap (integração real com Portal da Transparência).
    """
    token = _carregar_token_portal(token)
    if not token:
        mensagem = (
            "PORTAL_TRANSPARENCIA_API_KEY não configurada. Consulta ao Portal não executada; "
            "use CSV manual ou configure a chave em .env/config/secrets_local.py."
        )
        logger.info(mensagem)
        return _df_emendas_vazio("sem_chave_api")

    endpoint = get_fonte_oficial("portal_transparencia", "endpoint_emendas")
    headers = {"chave-api-dados": token}

    # A API real de emendas aceita apenas: pagina, ano, nomeAutor, codigoEmenda,
    # numeroEmenda, tipoEmenda, codigoFuncao, codigoSubfuncao (verificado jul/2026).
    # Parâmetros uf/municipio/nivel são IGNORADOS pelo endpoint; a filtragem por
    # localidade é feita client-side em _filtrar_dataframe_emendas, a partir do
    # campo localidadeDoGasto da resposta.
    params = {"pagina": pagina}
    if ano:
        params["ano"] = ano
    if autor:
        params["nomeAutor"] = autor

    logger.info(f"Consultando {endpoint} com params={params}...")

    # Pagina até esgotar os resultados (limite de segurança de 20 páginas).
    dados = []
    pagina_atual = int(pagina or 1)
    for _ in range(20):
        params["pagina"] = pagina_atual
        resposta = requests.get(endpoint, headers=headers, params=params, timeout=30)
        resposta.raise_for_status()
        lote = resposta.json()
        if not lote:
            break
        dados.extend(lote)
        if len(lote) < 15:  # página incompleta = última página
            break
        pagina_atual += 1

    if not dados:
        logger.info("Nenhuma emenda retornada pela API para os filtros informados.")
        return _df_emendas_vazio("sem_resultados")

    df = normalizar_resposta_portal_transparencia(dados)
    df.attrs["status_consulta"] = "ok"
    logger.info(f"{len(df)} emenda(s) retornada(s) pela API do Portal da Transparência.")
    return df


def buscar_emendas_filtradas(
    ano: int = None,
    codigo_ibge: str = None,
    municipio: str = None,
    uf: str = None,
    autor: str = None,
    nivel_territorial: str = "municipal",
    aceitar_uf: bool = False,
    aceitar_nacional: bool = False,
    aceitar_multiplo: bool = False,
    nivel: str = None,
    token: str = None,
    **kwargs,
) -> pd.DataFrame:
    """Busca emendas filtradas e retorna um DataFrame normalizado.

    Por padrão, consulta o banco local/CSV já importado. Para usar a API do
    Portal da Transparência, passe `usar_portal=True` ou `token=...`.
    Falhas de API, rede ou chave ausente retornam DataFrame vazio com status
    em `df.attrs["status_consulta"]`, evitando quebrar a interface Streamlit.
    """
    pagina = kwargs.pop("pagina", 1)
    usar_portal = bool(kwargs.pop("usar_portal", False) or token)
    if kwargs:
        logger.info(f"Filtros de emendas ignorados por compatibilidade: {sorted(kwargs)}")

    niveis = []
    if nivel:
        nivel_consulta = nivel
    else:
        if nivel_territorial:
            niveis.append(nivel_territorial)
        if aceitar_uf:
            niveis.append("estadual")
        if aceitar_nacional:
            niveis.append("nacional")
        if aceitar_multiplo:
            niveis.append("multiplo")
        nivel_consulta = ",".join(dict.fromkeys(niveis)) or "municipal"

    if usar_portal:
        try:
            df = buscar_emendas_portal_transparencia(
                token=token,
                codigo_ibge=codigo_ibge,
                ano=ano,
                pagina=pagina,
                municipio=municipio,
                uf=uf,
                autor=autor,
                nivel=nivel_consulta,
            )
            df = normalizar_emendas_portal_transparencia(df)
        except Exception as exc:
            logger.info(
                "Não foi possível consultar emendas no Portal da Transparência. "
                "Verifique a chave da API e tente novamente. Detalhe: %s",
                exc,
            )
            return _df_emendas_vazio("erro_api")
    else:
        registros = _buscar_emendas_filtros(
            ano=ano,
            codigo_ibge=codigo_ibge,
            municipio=None,
            uf=uf,
            autor=autor,
            nivel="multiplo",
        )
        df = normalizar_emendas(pd.DataFrame(registros)) if registros else _df_emendas_vazio("sem_resultados_local")
        df.attrs["status_consulta"] = "banco_local"

    if df.empty:
        return df if len(df.columns) else _df_emendas_vazio(df.attrs.get("status_consulta", "sem_resultados"))

    return _filtrar_dataframe_emendas(
        df,
        ano=ano,
        codigo_ibge=codigo_ibge,
        municipio=municipio,
        uf=uf,
        autor=autor,
        nivel=nivel_consulta,
    ).reset_index(drop=True)


def _filtrar_dataframe_emendas(
    df: pd.DataFrame,
    ano: int = None,
    codigo_ibge: str = None,
    municipio: str = None,
    uf: str = None,
    autor: str = None,
    nivel: str = "multiplo",
) -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        return df

    for coluna in [
        "ano", "codigo_ibge", "municipio_beneficiado", "uf", "parlamentar_nome",
        "parlamentar_nome_civil", "parlamentar_nome_urna",
    ]:
        if coluna not in df.columns:
            df[coluna] = ""

    if ano:
        df = df[pd.to_numeric(df["ano"], errors="coerce") == int(ano)]
    if codigo_ibge:
        alvo_codigo = str(codigo_ibge).strip()
        df = df[df["codigo_ibge"].astype(str).str.strip() == alvo_codigo]
    if municipio:
        alvo_municipio = _normalizar_texto(municipio)
        df = df[df["municipio_beneficiado"].map(_normalizar_texto) == alvo_municipio]
    if uf:
        alvo_uf = str(uf).upper().strip()
        df = df[df["uf"].astype(str).str.upper().str.strip() == alvo_uf]
    if autor:
        alvo_autor = _normalizar_texto(autor)
        nomes = (
            df["parlamentar_nome"].map(_normalizar_texto) + " "
            + df["parlamentar_nome_civil"].map(_normalizar_texto) + " "
            + df["parlamentar_nome_urna"].map(_normalizar_texto)
        )
        df = df[nomes.str.contains(alvo_autor, na=False, regex=False)]

    niveis = {_normalizar_texto(n) for n in str(nivel or "multiplo").split(",") if n}
    if "multiplo" not in niveis:
        masks = []
        municipio_preenchido = df["municipio_beneficiado"].astype(str).str.strip().ne("")
        codigo_preenchido = df["codigo_ibge"].astype(str).str.strip().ne("")
        uf_preenchida = df["uf"].astype(str).str.strip().ne("")
        if "municipal" in niveis:
            masks.append(municipio_preenchido | codigo_preenchido)
        if "estadual" in niveis:
            masks.append(uf_preenchida & ~municipio_preenchido & ~codigo_preenchido)
        if "nacional" in niveis:
            masks.append(~uf_preenchida & ~municipio_preenchido & ~codigo_preenchido)
        if masks:
            mask_final = masks[0]
            for mask in masks[1:]:
                mask_final = mask_final | mask
            df = df[mask_final]

    return df


def importar_emendas_csv(caminho_arquivo: str, separador: str = ";") -> pd.DataFrame:
    """Carrega um CSV de emendas/verbas no formato esperado pelo sistema.

    Aceita tanto ; quanto , como separador (detecta automaticamente se
    `separador` não funcionar).
    """
    try:
        df = pd.read_csv(caminho_arquivo, sep=separador, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(caminho_arquivo, sep=separador, encoding="latin-1")

    if len(df.columns) == 1:
        # Separador errado, tenta o outro
        outro_sep = "," if separador == ";" else ";"
        df = pd.read_csv(caminho_arquivo, sep=outro_sep, encoding="utf-8")

    faltantes = [c for c in COLUNAS_ESPERADAS if c not in df.columns]
    if faltantes:
        logger.info(f"Aviso: colunas ausentes no CSV (serão preenchidas vazias): {faltantes}")
        for c in faltantes:
            df[c] = None

    logger.info(f"{len(df)} linha(s) carregada(s) de {caminho_arquivo}.")
    return normalizar_emendas(df)


def normalizar_emendas(df: pd.DataFrame) -> pd.DataFrame:
    """Padroniza nomes de colunas, valores monetários, município/UF e remove duplicados."""
    df = df.copy()

    # Padroniza nomes de colunas (lowercase, sem espaço/acento)
    df.columns = [_normalizar_texto(c, manter_espaco=False) for c in df.columns]

    for col in COLUNAS_VALOR:
        if col in df.columns:
            df[col] = df[col].map(_converter_valor_monetario)

    if "uf" in df.columns:
        df["uf"] = df["uf"].astype(str).str.upper().str.strip()

    if "municipio_beneficiado" in df.columns:
        df["municipio_beneficiado"] = df["municipio_beneficiado"].astype(str).str.strip()

    df = df.fillna("")
    df = df.drop_duplicates()

    logger.info(f"Normalização concluída: {len(df)} linha(s) após remover duplicados.")
    return df


def _converter_valor_monetario(valor) -> float:
    """Converte valores monetarios BR/US sem alterar numeros ja normalizados."""
    if pd.isna(valor) or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()
    if not texto:
        return 0.0

    texto = re.sub(r"[^\d,.\-]", "", texto)
    if texto in {"", ".", ",", "-", "-.", "-,"}:
        return 0.0

    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(".", "").replace(",", ".")

    numero = pd.to_numeric(texto, errors="coerce")
    return 0.0 if pd.isna(numero) else float(numero)

def _normalizar_texto(texto: str, manter_espaco: bool = True) -> str:
    """Remove acentos e normaliza caixa de um texto, para comparações robustas."""
    texto = str(texto).strip().lower()
    texto = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    if not manter_espaco:
        texto = texto.replace(" ", "_")
    return texto


def buscar_emendas_por_parlamentar(nome: str, uf: str = None, ano_inicial: int = None, ano_final: int = None) -> list:
    """Busca emendas já salvas no banco para um parlamentar."""
    return _buscar_emendas_db(nome, uf=uf, ano_inicial=ano_inicial, ano_final=ano_final)


def salvar_emendas_no_banco(df: pd.DataFrame) -> int:
    """Persiste um DataFrame normalizado de emendas no banco. Retorna quantidade inserida."""
    if df is None or df.empty:
        logger.info("Nenhuma emenda para salvar no banco.")
        return 0

    df = normalizar_emendas(df)
    inseridas = 0
    duplicadas = 0
    conn = get_connection()
    cur = conn.cursor()
    try:
        for _, linha in df.iterrows():
            dados = {
            "parlamentar_nome": linha.get("parlamentar_nome", ""),
            "parlamentar_nome_civil": linha.get("parlamentar_nome_civil", ""),
            "parlamentar_nome_urna": linha.get("parlamentar_nome_urna", ""),
            "partido": linha.get("partido", ""),
            "uf": linha.get("uf", ""),
            "ano": int(linha.get("ano") or 0),
            "municipio_beneficiado": linha.get("municipio_beneficiado", ""),
            "codigo_ibge": linha.get("codigo_ibge", ""),
            "area": linha.get("area", ""),
            "orgao": linha.get("orgao", ""),
            "entidade_beneficiada": linha.get("entidade_beneficiada", ""),
            "valor_empenhado": float(linha.get("valor_empenhado") or 0),
            "valor_liquidado": float(linha.get("valor_liquidado") or 0),
            "valor_pago": float(linha.get("valor_pago") or 0),
            "fonte": linha.get("fonte", ""),
            "link_fonte": linha.get("link_fonte", ""),
            "status_validacao": "importado_csv",
            }
            cur.execute(
                """SELECT 1 FROM emendas
                   WHERE COALESCE(parlamentar_nome, '') = ?
                     AND COALESCE(parlamentar_nome_civil, '') = ?
                     AND COALESCE(parlamentar_nome_urna, '') = ?
                     AND COALESCE(partido, '') = ?
                     AND COALESCE(uf, '') = ?
                     AND COALESCE(ano, 0) = ?
                     AND COALESCE(municipio_beneficiado, '') = ?
                     AND COALESCE(codigo_ibge, '') = ?
                     AND COALESCE(area, '') = ?
                     AND COALESCE(orgao, '') = ?
                     AND COALESCE(entidade_beneficiada, '') = ?
                     AND COALESCE(valor_empenhado, 0) = ?
                     AND COALESCE(valor_liquidado, 0) = ?
                     AND COALESCE(valor_pago, 0) = ?
                     AND COALESCE(fonte, '') = ?
                     AND COALESCE(link_fonte, '') = ?
                   LIMIT 1""",
                (
                    dados["parlamentar_nome"],
                    dados["parlamentar_nome_civil"],
                    dados["parlamentar_nome_urna"],
                    dados["partido"],
                    dados["uf"],
                    dados["ano"],
                    dados["municipio_beneficiado"],
                    dados["codigo_ibge"],
                    dados["area"],
                    dados["orgao"],
                    dados["entidade_beneficiada"],
                    dados["valor_empenhado"],
                    dados["valor_liquidado"],
                    dados["valor_pago"],
                    dados["fonte"],
                    dados["link_fonte"],
                ),
            )
            if cur.fetchone():
                duplicadas += 1
                continue
            cur.execute(
                """INSERT INTO emendas
                   (parlamentar_nome, parlamentar_nome_civil, parlamentar_nome_urna, partido,
                    uf, ano, municipio_beneficiado, codigo_ibge, area, orgao, entidade_beneficiada,
                    valor_empenhado, valor_liquidado, valor_pago, fonte, link_fonte, status_validacao)
                   VALUES (:parlamentar_nome, :parlamentar_nome_civil, :parlamentar_nome_urna,
                           :partido, :uf, :ano, :municipio_beneficiado, :codigo_ibge, :area,
                           :orgao, :entidade_beneficiada, :valor_empenhado, :valor_liquidado,
                           :valor_pago, :fonte, :link_fonte, :status_validacao)""",
                dados,
            )
            inseridas += 1
        conn.commit()
    finally:
        conn.close()

    logger.info(f"{inseridas} emenda(s) salva(s) no banco; {duplicadas} duplicada(s) ignorada(s).")
    return inseridas


def salvar_emendas_portal_no_banco(df: pd.DataFrame) -> int:
    """Alias para persistir emendas normalizadas vindas do Portal."""
    return salvar_emendas_no_banco(df)

def validar_vinculo_emenda_candidato(candidato: dict, emendas: pd.DataFrame) -> str:
    """Estima o nível de confiança do vínculo entre um candidato e um conjunto de emendas.

    Retorna: "alto", "médio", "baixo" ou "precisa validação manual".
    Regra simples para MVP: compara nome civil/urna e UF; reforça com partido.
    """
    if emendas is None or len(emendas) == 0:
        return "baixo"

    nome_civil = _normalizar_texto(candidato.get("nome_civil", ""))
    nome_urna = _normalizar_texto(candidato.get("nome_urna", ""))
    uf_candidato = (candidato.get("uf") or "").upper()
    partido_candidato = _normalizar_texto(candidato.get("partido", "") or candidato.get("sigla_partido", ""))

    pontos = 0
    total = 0

    for _, linha in emendas.iterrows():
        total += 1
        nome_civil_emenda = _normalizar_texto(linha.get("parlamentar_nome_civil", ""))
        nome_urna_emenda = _normalizar_texto(linha.get("parlamentar_nome_urna", ""))
        uf_emenda = (linha.get("uf") or "").upper()
        partido_emenda = _normalizar_texto(linha.get("partido", ""))

        match_nome = nome_civil in nome_civil_emenda or nome_urna in nome_urna_emenda
        match_uf = uf_emenda == uf_candidato
        match_partido = partido_emenda == partido_candidato

        if match_nome and match_uf and match_partido:
            pontos += 3
        elif match_nome and match_uf:
            pontos += 2
        elif match_nome:
            pontos += 1

    if total == 0:
        return "baixo"

    media = pontos / total
    if media >= 2.5:
        return "alto"
    elif media >= 1.5:
        return "médio"
    elif media >= 1:
        return "baixo"
    return "precisa validação manual"


def gerar_resumo_emendas(candidato_id: int) -> dict:
    """Gera um resumo agregado das emendas vinculadas a um candidato.

    Nota: a vinculação por candidato_id ainda depende de um campo de
    relação explícito; no MVP, a busca é feita por nome (ver
    buscar_emendas_por_parlamentar) e o resumo é calculado a partir do
    resultado dessa busca.
    """
    from database.db_utils import buscar_candidato

    candidato = buscar_candidato(candidato_id)
    if not candidato:
        return {"erro": "Candidato não encontrado."}

    emendas = buscar_emendas_por_parlamentar(
        candidato.get("nome_urna") or candidato.get("nome_civil"),
        uf=candidato.get("uf"),
    )

    if not emendas:
        return {
            "total_empenhado": 0.0,
            "total_liquidado": 0.0,
            "total_pago": 0.0,
            "municipios_beneficiados": [],
            "areas_atendidas": {},
            "ranking_municipios": [],
        }

    df = pd.DataFrame(emendas)
    ranking = (
        df.groupby("municipio_beneficiado")["valor_pago"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
        .to_dict(orient="records")
    )

    return {
        "total_empenhado": float(df["valor_empenhado"].sum()),
        "total_liquidado": float(df["valor_liquidado"].sum()),
        "total_pago": float(df["valor_pago"].sum()),
        "municipios_beneficiados": sorted(df["municipio_beneficiado"].dropna().unique().tolist()),
        "areas_atendidas": df.groupby("area")["valor_pago"].sum().to_dict(),
        "ranking_municipios": ranking,
    }


if __name__ == "__main__":
    df_teste = importar_emendas_csv("data/templates/modelo_emendas.csv")
    print(df_teste)
    n = salvar_emendas_no_banco(df_teste)
    print(f"[TESTE] {n} emenda(s) inserida(s).")
    resumo = gerar_resumo_emendas(1)
    print(f"[TESTE] Resumo emendas candidato 1: {resumo}")
