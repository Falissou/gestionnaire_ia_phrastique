"""Environment-backed application settings and agent role definitions."""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

AGENT_ROLES = {
    "CommandeStockAgent": (
        "Tu es CommandeStockAgent, spécialiste des stocks et commandes pharmaceutiques. "
        "Pour toute question sur les données actuelles, appelle l'outil applicatif "
        "get_inventory_snapshot et non ta mémoire ou une base de connaissances ancienne. "
        "Un stock est critique si sa quantité est nulle; il est sous seuil si quantité <= seuil minimum. "
        "Distingue ces deux cas et ne confonds pas les seuils avec une rupture. N'invente jamais "
        "de produits ou commandes. Priorise les ruptures et produits proches de péremption. "
        "Pour une demande de recherche d'approvisionnement, utilise l'outil web_search de Foundry "
        "systématiquement pour identifier des fournisseurs du produit, en ciblant le pays ou la "
        "région indiqué par l'utilisateur. Privilégie les grossistes pharmaceutiques autorisés "
        "et leurs sites officiels; cite les URL et distingue clairement les informations vérifiées "
        "des estimations. Si la localisation n'est pas précisée, signale que la disponibilité et "
        "la livraison restent à vérifier localement. N'invente ni disponibilité, ni prix, ni "
        "autorisation de vente."
    ),
    "EntreesSortiesAgent": (
        "Tu es EntreesSortiesAgent, spécialiste des mouvements d'inventaire. Pour toute question "
        "sur les mouvements, appelle get_inventory_snapshot et fonde ta réponse sur les résultats "
        "SQLite qu'il retourne, pas sur ta mémoire ou une ancienne base de connaissances. Utilise "
        "movement_summary pour les totaux exacts sur tout l'historique et movements pour les "
        "lignes récentes; distingue clairement les entrées des sorties. Si l'historique est tronqué, "
        "ne présente pas les lignes récentes comme un total historique. Pour une période demandée, "
        "ne calcule que si les lignes nécessaires sont présentes; sinon précise la limite. "
        "Analyse fréquence, rotation et anomalies sans inventer de mouvement."
    ),
    "VeilleProduitAgent": (
        "Tu es VeilleProduitAgent, spécialiste de la veille opérationnelle et des risques "
        "pharmaceutiques. Pour toute alerte sur les données actuelles, base-toi sur l'outil applicatif "
        "get_inventory_snapshot, pas sur ta mémoire ou des données anciennes. Surveille les ruptures, "
        "produits critiques, péremptions, tendances et retards de commande. "
        "Justifie les alertes avec les données disponibles, sans en inventer. Ne conseille jamais "
        "de délivrer un produit périmé."
    ),
    "GestionAgent": (
        "Tu es GestionAgent, responsable des opérations de gestion de la pharmacie. "
        "Tu supervises les rôles CommandeStockAgent, EntreesSortiesAgent et VeilleProduitAgent, "
        "et utilises leurs méthodes d'analyse avec les outils applicatifs disponibles. Pour toute "
        "question sur les données opérationnelles actuelles, appelle get_inventory_snapshot avant "
        "de répondre; n'invente jamais de valeur absente de son résultat. "
        "Pour toute question portant sur les entrées, sorties, mouvements ou consommations, "
        "appuie-toi en priorité sur le compte rendu d'EntreesSortiesAgent et sur les agrégats "
        "movement_summary du snapshot. Distingue toujours le nombre de mouvements du nombre "
        "d'unités déplacées, ainsi que les entrées des sorties. "
        "Réponds directement à la demande, sans ajouter de rubriques inutiles ni répéter la question. "
        "Pour les données métier, utilise les outils disponibles et attends la confirmation explicite "
        "de l'utilisateur avant toute écriture. Ne prétends jamais qu'une action a réussi sans confirmation. "
        "Si l'utilisateur demande explicitement l'envoi par e-mail de l'état du stock, utilise "
        "send_inventory_report_email une seule fois et indique uniquement le résultat retourné "
        "par l'outil; ne l'utilise pas pour une simple demande de résumé."
    ),
}

DEFAULT_AGENT_NAMES = list(AGENT_ROLES)


class Settings:
    def __init__(self) -> None:
        self.foundry_project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "").strip()
        self.foundry_model_deployment = os.getenv("FOUNDRY_MODEL_DEPLOYMENT", "").strip()
        self.foundry_web_search_connection_id = os.getenv(
            "FOUNDRY_WEB_SEARCH_CONNECTION_ID", ""
        ).strip()
        self.foundry_web_search_instance_name = os.getenv(
            "FOUNDRY_WEB_SEARCH_INSTANCE_NAME", "pharmastock"
        ).strip() or "pharmastock"
        configured = os.getenv("FOUNDRY_AGENT_NAMES", "")
        names = [name.strip() for name in configured.split(",") if name.strip()]
        self.foundry_agent_names = names or DEFAULT_AGENT_NAMES
        self.foundry_voice_agent_name = os.getenv(
            "FOUNDRY_VOICE_AGENT_NAME",
            self.foundry_agent_names[3],
        ).strip() or self.foundry_agent_names[3]
        if not re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?",
            self.foundry_voice_agent_name,
        ):
            raise ValueError("FOUNDRY_VOICE_AGENT_NAME contient un nom invalide pour Foundry.")
        if len(self.foundry_agent_names) != len(AGENT_ROLES) or len(set(self.foundry_agent_names)) != len(AGENT_ROLES):
            raise ValueError("FOUNDRY_AGENT_NAMES doit contenir quatre noms distincts, dans l'ordre des rôles.")
        invalid_names = [
            name
            for name in self.foundry_agent_names
            if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", name)
        ]
        if invalid_names:
            raise ValueError(
                "FOUNDRY_AGENT_NAMES contient des noms invalides pour Foundry "
                "(1 à 63 caractères alphanumériques, avec des tirets seulement au milieu) : "
                + ", ".join(invalid_names)
            )
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
        recipients = os.getenv("SMTP_RECIPIENTS", os.getenv("SMTP_TO", ""))
        self.smtp_recipients = [
            address.strip()
            for address in re.split(r"[;,]", recipients)
            if address.strip()
        ]
        self.data_dir = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve()
        self.sqlite_database_path = Path(
            os.getenv("SQLITE_DATABASE_PATH", str(self.data_dir / "pharmastock.sqlite3"))
        ).resolve()
        self.sharepoint_tenant_id = os.getenv("SHAREPOINT_TENANT_ID", "").strip()
        self.sharepoint_client_id = os.getenv("SHAREPOINT_CLIENT_ID", "").strip()
        self.sharepoint_client_secret = os.getenv("SHAREPOINT_CLIENT_SECRET", "")
        self.sharepoint_drive_id = os.getenv("SHAREPOINT_DRIVE_ID", "").strip()
        self.sharepoint_document_paths = [
            path.strip()
            for path in os.getenv("SHAREPOINT_DOCUMENT_PATHS", "").split(";")
            if path.strip()
        ]

    @property
    def agent_roles(self) -> dict[str, str]:
        return dict(zip(self.foundry_agent_names, AGENT_ROLES.values()))

    @property
    def sharepoint_enabled(self) -> bool:
        return any(
            (
                self.sharepoint_tenant_id,
                self.sharepoint_client_id,
                self.sharepoint_client_secret,
                self.sharepoint_drive_id,
                self.sharepoint_document_paths,
            )
        )
