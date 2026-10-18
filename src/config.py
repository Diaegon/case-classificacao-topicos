"""Carrega config/settings.yaml e o .env. Todos os módulos importam daqui."""

from pathlib import Path

import yaml
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

with open(RAIZ / "config" / "settings.yaml", encoding="utf-8") as f:
    SETTINGS = yaml.safe_load(f)


def caminho(nome: str) -> Path:
    """Caminho absoluto de uma das pastas em settings.caminhos (raw, interim, gold...)."""
    return RAIZ / SETTINGS["caminhos"][nome]
