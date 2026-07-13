"""
Radar Eleitoral IA - Funções utilitárias de acesso ao banco.

Funções simples de CRUD usadas pelos demais módulos (collectors,
analysis, ai, app.py). Mantém o acesso a banco centralizado em um
único lugar para facilitar a futura migração para PostgreSQL.
"""

from datetime import datetime

import pandas as pd

from database.init_db import get_connection


# ----------------------------------------------------------------------
# Candidatos
# ----------------------------------------------------------------------

def inserir_candidato(dados: dict) -> int:
    """Insere um candidato e retorna o id gerado.

    `dados` deve conter as chaves correspondentes às colunas da tabela
    `candidatos` (id_tse, nome_civil, nome_urna, numero, cpf_mascarado,
    partido, sigla_partido, cargo, uf, ano, situacao).
    """
    dados = {
        **dados,
        "origem_dados": dados.get("origem_dados", "demo"),
        "fonte_dados": dados.get("fonte_dados", "Dados de demonstração do MVP"),
    }
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO candidatos
           (id_tse, nome_civil, nome_urna, numero, cpf_mascarado, partido,
            sigla_partido, cargo, uf, ano, situacao, origem_dados, fonte_dados)
           VALUES (:id_tse, :nome_civil, :nome_urna, :numero, :cpf_mascarado,
                   :partido, :sigla_partido, :cargo, :uf, :ano, :situacao,
                   :origem_dados, :fonte_dados)""",
        dados,
    )
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def buscar_candidato(candidato_id: int):
    """Busca um único candidato por id. Retorna dict ou None."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM candidatos WHERE id = ?", (candidato_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def listar_candidatos(
    nome_civil: str = None,
    nome_urna: str = None,
    numero: str = None,
    partido: str = None,
    uf: str = None,
    cargo: str = None,
    ano: int = None,
) -> list:
    """Lista candidatos filtrando por qualquer combinação de critérios.

    Busca por nome usa LIKE case-insensitive (parcial).
    """
    query = "SELECT * FROM candidatos WHERE 1=1"
    params = []

    if nome_civil:
        query += " AND nome_civil LIKE ?"
        params.append(f"%{nome_civil}%")
    if nome_urna:
        query += " AND nome_urna LIKE ?"
        params.append(f"%{nome_urna}%")
    if numero:
        query += " AND numero = ?"
        params.append(numero)
    if partido:
        query += " AND (partido LIKE ? OR sigla_partido LIKE ?)"
        params.extend([f"%{partido}%", f"%{partido}%"])
    if uf:
        query += " AND uf = ?"
        params.append(uf)
    if cargo:
        query += " AND cargo = ?"
        params.append(cargo)
    if ano:
        query += " AND ano = ?"
        params.append(ano)

    query += " ORDER BY ano DESC"

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ----------------------------------------------------------------------
# Votação
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# Cache tratado do TSE
# ----------------------------------------------------------------------

TIPO_ARQUIVO_TSE_PADRAO = "votacao_candidato_munzona"


def listar_importacoes_tse() -> list:
    """Lista o historico de importacoes TSE, mais recentes primeiro."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT *
           FROM tse_importacoes
           ORDER BY data_importacao DESC, id DESC"""
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def verificar_importacao_tse(
    ano: int,
    uf: str,
    tipo_arquivo: str = TIPO_ARQUIVO_TSE_PADRAO,
):
    """Retorna a importacao concluida mais recente para ano/UF, ou None."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT *
           FROM tse_importacoes
           WHERE ano = ?
             AND UPPER(uf) = ?
             AND tipo_arquivo = ?
             AND status = 'importado'
           ORDER BY data_importacao DESC, id DESC
           LIMIT 1""",
        (int(ano), str(uf).upper().strip(), tipo_arquivo),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def registrar_importacao_tse(
    ano: int,
    uf: str,
    tipo_arquivo: str = TIPO_ARQUIVO_TSE_PADRAO,
    arquivo_origem: str = None,
    status: str = "importado",
    quantidade_linhas: int = 0,
    mensagem: str = "",
    hash_arquivo: str = None,
) -> int:
    """Registra uma tentativa ou conclusao de importacao TSE."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO tse_importacoes
           (ano, uf, tipo_arquivo, arquivo_origem, status, quantidade_linhas,
            data_importacao, mensagem, hash_arquivo)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            int(ano),
            str(uf).upper().strip(),
            tipo_arquivo,
            arquivo_origem,
            status,
            int(quantidade_linhas or 0),
            datetime.now().isoformat(timespec="seconds"),
            mensagem,
            hash_arquivo,
        ),
    )
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def _safe_int(valor, default=None):
    if valor is None or pd.isna(valor) or valor == "":
        return default
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return default


def _safe_text(valor):
    if valor is None or pd.isna(valor):
        return None
    texto = str(valor).strip()
    return texto if texto else None


def salvar_candidaturas_tse(df: pd.DataFrame, ano: int, uf: str) -> int:
    """Salva no cache tratado uma linha por candidato/municipio/zona.

    A importacao e idempotente para ano/UF: antes de inserir, remove as
    linhas tratadas anteriores daquele recorte.
    """
    ano = int(ano)
    uf = str(uf).upper().strip()
    if df is None or df.empty:
        return 0

    colunas = [
        "id_tse", "ano", "turno", "uf", "municipio", "codigo_municipio_tse",
        "zona", "cargo", "nome_civil", "nome_urna", "numero", "partido",
        "nome_partido", "votos", "votos_validos", "situacao", "origem_arquivo",
    ]
    df_tratado = df.copy()
    for coluna in colunas:
        if coluna not in df_tratado.columns:
            df_tratado[coluna] = None

    df_tratado["ano"] = ano
    df_tratado["uf"] = uf
    df_tratado["votos"] = pd.to_numeric(df_tratado["votos"], errors="coerce").fillna(0)
    df_tratado["votos_validos"] = pd.to_numeric(df_tratado["votos_validos"], errors="coerce")
    df_tratado["turno"] = pd.to_numeric(df_tratado["turno"], errors="coerce")

    registros = []
    for _, linha in df_tratado[colunas].iterrows():
        registros.append((
            _safe_text(linha.get("id_tse")),
            ano,
            _safe_int(linha.get("turno")),
            uf,
            _safe_text(linha.get("municipio")),
            _safe_text(linha.get("codigo_municipio_tse")),
            _safe_text(linha.get("zona")),
            _safe_text(linha.get("cargo")),
            _safe_text(linha.get("nome_civil")),
            _safe_text(linha.get("nome_urna")),
            _safe_text(linha.get("numero")),
            _safe_text(linha.get("partido")),
            _safe_text(linha.get("nome_partido")),
            _safe_int(linha.get("votos"), 0),
            _safe_int(linha.get("votos_validos")),
            _safe_text(linha.get("situacao")),
            _safe_text(linha.get("origem_arquivo")),
        ))

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM candidaturas_tse WHERE ano = ? AND UPPER(uf) = ?",
            (ano, uf),
        )
        cur.executemany(
            """INSERT INTO candidaturas_tse
               (id_tse, ano, turno, uf, municipio, codigo_municipio_tse, zona,
                cargo, nome_civil, nome_urna, numero, partido, nome_partido,
                votos, votos_validos, situacao, origem_arquivo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            registros,
        )
        conn.commit()
    finally:
        conn.close()
    return len(registros)


def buscar_candidaturas_tse(
    ano: int = None,
    uf: str = None,
    cargo: str = None,
    nome_urna: str = None,
    nome_civil: str = None,
    numero: str = None,
    partido: str = None,
    municipio: str = None,
    id_tse: str = None,
    limite: int = None,
) -> list:
    """Busca candidaturas no cache local tratado, sem baixar arquivos."""
    query = "SELECT * FROM candidaturas_tse WHERE 1=1"
    params = []

    if ano:
        query += " AND ano = ?"
        params.append(int(ano))
    if uf:
        query += " AND UPPER(uf) = ?"
        params.append(str(uf).upper().strip())
    if cargo:
        query += " AND UPPER(cargo) = ?"
        params.append(str(cargo).upper().strip())
    if nome_urna:
        query += " AND nome_urna LIKE ? COLLATE NOCASE"
        params.append(f"%{nome_urna}%")
    if nome_civil:
        query += " AND nome_civil LIKE ? COLLATE NOCASE"
        params.append(f"%{nome_civil}%")
    if numero:
        query += " AND numero = ?"
        params.append(str(numero).strip())
    if partido:
        query += " AND (partido LIKE ? COLLATE NOCASE OR nome_partido LIKE ? COLLATE NOCASE)"
        params.extend([f"%{partido}%", f"%{partido}%"])
    if municipio:
        query += " AND municipio LIKE ? COLLATE NOCASE"
        params.append(f"%{municipio}%")
    if id_tse:
        query += " AND id_tse = ?"
        params.append(str(id_tse).strip())

    query += " ORDER BY ano DESC, nome_urna ASC, municipio ASC, zona ASC"
    if limite:
        query += " LIMIT ?"
        params.append(int(limite))

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def inserir_votacao(dados: dict) -> int:
    """Insere um registro de votação por município."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO votacao_municipio
           (candidato_id, ano, turno, uf, codigo_municipio_tse, municipio,
            cargo, partido, votos, votos_validos_municipio, percentual_votos)
           VALUES (:candidato_id, :ano, :turno, :uf, :codigo_municipio_tse,
                   :municipio, :cargo, :partido, :votos, :votos_validos_municipio,
                   :percentual_votos)""",
        dados,
    )
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def buscar_votacao_por_candidato(candidato_id: int, ano_inicial: int = None, ano_final: int = None) -> list:
    """Retorna todos os registros de votação por município de um candidato."""
    query = "SELECT * FROM votacao_municipio WHERE candidato_id = ?"
    params = [candidato_id]

    if ano_inicial:
        query += " AND ano >= ?"
        params.append(ano_inicial)
    if ano_final:
        query += " AND ano <= ?"
        params.append(ano_final)

    query += " ORDER BY ano ASC, municipio ASC"

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def buscar_votacao_zona_por_candidato(candidato_id: int, ano: int = None) -> list:
    """Retorna votos por zona eleitoral de um candidato."""
    query = """SELECT candidato_id, ano, turno, uf, municipio, zona, SUM(votos) AS votos
               FROM votacao_zona
               WHERE candidato_id = ?"""
    params = [candidato_id]

    if ano:
        query += " AND ano = ?"
        params.append(int(ano))

    query += """
               GROUP BY candidato_id, ano, turno, uf, municipio, zona
               ORDER BY ano DESC, municipio ASC, CAST(zona AS INTEGER) ASC"""

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def buscar_votacao_secao_por_candidato(candidato_id: int, ano: int = None) -> list:
    """Retorna votos por seção/local de votação para um candidato, quando importados."""
    candidato = buscar_candidato(candidato_id)
    if not candidato:
        return []

    query = """SELECT ano, turno, uf, municipio, codigo_municipio_tse, zona, secao,
                      local_votacao, endereco_local, bairro, cargo, id_tse,
                      nome_civil, nome_urna, numero, partido,
                      SUM(votos) AS votos,
                      SUM(COALESCE(votos_validos, 0)) AS votos_validos
               FROM votacao_secao_tse
               WHERE 1=1"""
    params = []

    if ano:
        query += " AND ano = ?"
        params.append(int(ano))
    if candidato.get("uf"):
        query += " AND UPPER(uf) = ?"
        params.append(str(candidato.get("uf")).upper().strip())
    if candidato.get("id_tse"):
        query += " AND id_tse = ?"
        params.append(str(candidato.get("id_tse")).strip())
    else:
        if candidato.get("nome_civil"):
            query += " AND nome_civil LIKE ? COLLATE NOCASE"
            params.append(f"%{candidato.get('nome_civil')}%")
        if candidato.get("nome_urna"):
            query += " AND nome_urna LIKE ? COLLATE NOCASE"
            params.append(f"%{candidato.get('nome_urna')}%")
        if candidato.get("numero"):
            query += " AND numero = ?"
            params.append(str(candidato.get("numero")).strip())
    if candidato.get("cargo"):
        query += " AND UPPER(cargo) = ?"
        params.append(str(candidato.get("cargo")).upper().strip())

    query += """ GROUP BY ano, turno, uf, municipio, codigo_municipio_tse, zona, secao,
                         local_votacao, endereco_local, bairro, cargo, id_tse,
                         nome_civil, nome_urna, numero, partido
                ORDER BY municipio ASC, CAST(zona AS INTEGER) ASC, CAST(secao AS INTEGER) ASC"""

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ----------------------------------------------------------------------
# Emendas
# ----------------------------------------------------------------------

def inserir_emenda(dados: dict) -> int:
    """Insere um registro de emenda/verba pública."""
    conn = get_connection()
    cur = conn.cursor()
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
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id



def buscar_emendas(
    ano: int = None,
    codigo_ibge: str = None,
    municipio: str = None,
    uf: str = None,
    autor: str = None,
    nivel: str = "multiplo",
) -> list:
    """Busca emendas por filtros comerciais de localidade e autoria."""
    query = "SELECT * FROM emendas WHERE 1=1"
    params = []

    if ano:
        query += " AND ano = ?"
        params.append(int(ano))
    if codigo_ibge:
        query += " AND codigo_ibge = ?"
        params.append(str(codigo_ibge).strip())
    if municipio:
        query += " AND municipio_beneficiado LIKE ?"
        params.append(f"%{municipio}%")
    if uf:
        query += " AND uf = ?"
        params.append(str(uf).upper().strip())
    if autor:
        query += """ AND (parlamentar_nome LIKE ? OR parlamentar_nome_civil LIKE ?
                      OR parlamentar_nome_urna LIKE ?)"""
        like = f"%{autor}%"
        params.extend([like, like, like])

    nivel_normalizado = (nivel or "multiplo").strip().lower()
    if nivel_normalizado == "municipal":
        query += " AND (municipio_beneficiado IS NOT NULL AND municipio_beneficiado != '')"
    elif nivel_normalizado == "estadual":
        query += " AND (uf IS NOT NULL AND uf != '') AND (municipio_beneficiado IS NULL OR municipio_beneficiado = '')"
    elif nivel_normalizado == "nacional":
        query += " AND (uf IS NULL OR uf = '') AND (municipio_beneficiado IS NULL OR municipio_beneficiado = '')"

    query += " ORDER BY ano ASC, uf ASC, municipio_beneficiado ASC"

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def buscar_emendas_por_parlamentar(nome: str, uf: str = None, ano_inicial: int = None, ano_final: int = None) -> list:
    """Busca emendas vinculadas a um parlamentar (nome civil, urna ou nome geral)."""
    query = """SELECT * FROM emendas
               WHERE (parlamentar_nome LIKE ? OR parlamentar_nome_civil LIKE ?
                      OR parlamentar_nome_urna LIKE ?)"""
    like = f"%{nome}%"
    params = [like, like, like]

    if uf:
        query += " AND uf = ?"
        params.append(uf)
    if ano_inicial:
        query += " AND ano >= ?"
        params.append(ano_inicial)
    if ano_final:
        query += " AND ano <= ?"
        params.append(ano_final)

    query += " ORDER BY ano ASC"

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    # Teste rápido manual
    candidatos = listar_candidatos(uf="SP")
    print(f"[TESTE] {len(candidatos)} candidato(s) encontrado(s) em SP.")
    for c in candidatos:
        print(f"  - {c['nome_urna']} ({c['ano']}) [{c['cargo']}]")
