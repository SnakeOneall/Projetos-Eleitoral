"""Regras de granularidade territorial por cargo eleitoral."""

from __future__ import annotations

import unicodedata


def _normalizar(texto: str | None) -> str:
    valor = str(texto or "").strip().lower()
    valor = "".join(
        char for char in unicodedata.normalize("NFKD", valor)
        if not unicodedata.combining(char)
    )
    return " ".join(valor.split())


def detectar_escopo_cargo(cargo: str) -> dict:
    """Retorna a prioridade territorial adequada para o cargo informado."""
    cargo_norm = _normalizar(cargo)

    if "deputado distrital" in cargo_norm:
        return {
            "nivel_principal": "distrital",
            "agrupar_por": ["regiao_administrativa", "zona", "secao"],
            "fallback": ["zona", "municipio"],
            "mensagem": "Cargo distrital: análise prioriza região administrativa, zona e seção.",
        }

    cargos_municipais = ("vereador", "prefeito", "vice-prefeito", "vice prefeito")
    if any(nome in cargo_norm for nome in cargos_municipais):
        return {
            "nivel_principal": "municipal",
            "agrupar_por": ["zona", "secao", "local_votacao", "bairro"],
            "fallback": ["zona", "municipio"],
            "mensagem": (
                "Cargo municipal: análise deve priorizar zona, seção, local de votação "
                "e bairro quando disponíveis."
            ),
        }

    return {
        "nivel_principal": "estadual_federal",
        "agrupar_por": ["municipio", "zona"],
        "fallback": ["municipio"],
        "mensagem": "Cargo estadual/federal: análise prioriza municípios e zonas eleitorais.",
    }
