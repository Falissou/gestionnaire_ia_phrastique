"""Environment-backed application settings and agent role definitions."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

AGENT_ROLES = {
    "Command&stockAgent": (
        "Tu es l'agent Commande et stock d'une pharmacie. Analyse le stock disponible et "
        "les commandes fournisseurs. Signale les ruptures et les besoins de réapprovisionnement. "
        "Appuie-toi exclusivement sur les données de stock et de commandes fournies dans le contexte."
    ),
    "Entree&sortisAgent": (
        "Tu es l'agent Entrées et sorties d'une pharmacie. Suis les mouvements de produits, "
        "explique leurs effets sur les quantités en stock et repère les mouvements inhabituels. "
        "Appuie-toi sur les feuilles Entrées et Sorties fournies dans le contexte."
    ),
    "VeilleproduitAgent": (
        "Tu es l'agent de veille produit d'une pharmacie. Repère les produits périmés ou proches "
        "de leur date d'expiration, les stocks faibles et les anomalies. Priorise les alertes "
        "par urgence et recommande une action prudente; ne conseille jamais de délivrer un produit périmé."
    ),
    "GestionAgent": (
        "Tu es GestionAgent, l'orchestrateur de la plateforme de pharmacie. Coordonne les agents "
        "Commande et stock, Entrées et sorties, et Veille produit. Réponds aux questions à partir "
        "du contexte opérationnel fourni, synthétise les alertes, formule des recommandations et "
        "résume les indicateurs du tableau de bord. Ne prétends pas avoir envoyé un courriel ni "
        "effectué une opération qui n'est pas confirmée par un outil."
    ),
}

DEFAULT_AGENT_NAMES = list(AGENT_ROLES)


class Settings:
    def __init__(self) -> None:
        self.foundry_project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "").strip()
        self.foundry_model_deployment = os.getenv("FOUNDRY_MODEL_DEPLOYMENT", "").strip()
        configured = os.getenv("FOUNDRY_AGENT_NAMES", "")
        names = [name.strip() for name in configured.split(",") if name.strip()]
        self.foundry_agent_names = names or DEFAULT_AGENT_NAMES
        if len(self.foundry_agent_names) != len(AGENT_ROLES) or len(set(self.foundry_agent_names)) != len(AGENT_ROLES):
            raise ValueError("FOUNDRY_AGENT_NAMES doit contenir quatre noms distincts, dans l'ordre des rôles.")
        self.auth_enabled = os.getenv("AUTH_ENABLED", "false").strip().lower() == "true"
        self.entra_tenant_id = os.getenv("ENTRA_TENANT_ID", "").strip()
        self.entra_api_audience = os.getenv("ENTRA_API_AUDIENCE", "").strip()
        self.entra_jwks_url = os.getenv("ENTRA_JWKS_URL", "").strip()
        self.cors_origins = [
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        ]
        self.smtp_host = os.getenv("SMTP_HOST", "").strip()
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "").strip()
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from = os.getenv("SMTP_FROM", self.smtp_user).strip()
        self.data_dir = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve()

    @property
    def agent_roles(self) -> dict[str, str]:
        return dict(zip(self.foundry_agent_names, AGENT_ROLES.values()))
