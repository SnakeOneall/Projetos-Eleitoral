"""
Radar Eleitoral IA - Configurações gerais opcionais.

A chave da API do Portal da Transparência NÃO fica aqui: o
emendas_collector a carrega de .env (PORTAL_TRANSPARENCIA_API_KEY,
via python-dotenv) ou de config/secrets_local.py. Este módulo apenas
centraliza constantes simples de escopo do MVP.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# UF foco do MVP (pode ser sobrescrita pela variável de ambiente UF_FOCO)
UF_FOCO = os.environ.get("UF_FOCO", "SP")
