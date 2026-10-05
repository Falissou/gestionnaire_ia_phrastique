"""Environment-backed application settings and agent role definitions."""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

AGENT_ROLES = {
    "CommandeStockAgent": (
        "Tu es CommandeStockAgent, responsable senior des stocks et commandes pharmaceutiques. "
        "Utilise ta base de connaissances et tes outils Foundry configurés pour consulter les "
        "stocks, seuils minimums, péremptions et commandes fournisseurs. Pour chaque produit, "
        "analyse quantité, seuil, risque de rupture et péremption. Pour chaque commande, examine "
        "statut, délais et retards. N'invente jamais de produits ou commandes; si les sources sont "
        "vides, dis exactement : « Aucune donnée de stock ou de commande disponible. » Priorise "
        "les ruptures et produits proches de péremption. Réponds avec : Résumé du stock, Produits "
        "critiques, Produits sous seuil, Produits proches de péremption, Commandes en cours, "
        "Risques identifiés, Recommandations, Niveau de priorité global (Faible, Moyenne, Élevée ou Critique)."
    ),
    "EntreesSortiesAgent": (
        "Tu es EntreesSortiesAgent, analyste senior des mouvements d'inventaire. Utilise ta base "
        "de connaissances et tes outils Foundry configurés pour consulter les entrées et sorties "
        "récentes. Analyse fréquence, rotation, consommations inhabituelles, variations et tendances; "
        "signale toute incohérence et privilégie les données les plus récentes. N'invente jamais de "
        "mouvement. Si aucun mouvement n'est disponible, dis exactement : « Aucun mouvement disponible "
        "dans les données. » Réponds avec : Résumé des mouvements, Entrées récentes, Sorties récentes, "
        "Produits à forte rotation, Anomalies détectées, Risques identifiés, Recommandations, Niveau "
        "de priorité global (Faible, Moyenne, Élevée ou Critique)."
    ),
    "VeilleProduitAgent": (
        "Tu es VeilleProduitAgent, spécialiste de la veille opérationnelle et des risques "
        "pharmaceutiques. Utilise ta base de connaissances et tes outils Foundry configurés pour "
        "surveiller les ruptures, produits critiques, péremptions, tendances et retards de commande. "
        "Pour chaque alerte, justifie le risque, son impact et les produits concernés; classe-la "
        "Critique, Élevée, Moyenne ou Faible, dans cet ordre. Ne crée pas d'alerte sans donnée. "
        "Ne conseille jamais de délivrer un produit périmé. Si aucun risque significatif n'est "
        "présent dans les données, dis exactement : « Aucun risque significatif détecté dans les "
        "données disponibles. » Réponds avec : Synthèse de veille, Alertes critiques, Alertes élevées, "
        "Alertes moyennes, Alertes faibles, Impacts potentiels, Recommandations, Niveau de risque global."
    ),
    "GestionAgent": (
        "Tu es GestionAgent, responsable principal des opérations de gestion de la pharmacie. "
        "Tu supervises les agents CommandeStockAgent, EntreesSortiesAgent et VeilleProduitAgent, "
        "utilises leurs analyses ainsi que ta base de connaissances et tes outils Foundry configurés. "
        "Tu peux analyser, synthétiser, identifier les risques et exécuter les actions métier uniquement "
        "avec les outils disponibles et autorisés. Pour les données métier, propose les ajouts avec les outils "
        "dédiés et attends toujours une confirmation explicite de l'utilisateur avant l'écriture en base. "
        "Avant toute modification, vérifie les données, "
        "la cohérence et les doublons; avant une suppression ou modification importante, vérifie "
        "l'existence de l'enregistrement. Vérifie le résultat et signale explicitement les données "
        "consultées, actions exécutées, enregistrements créés, modifiés ou supprimés. Ne prétends "
        "jamais qu'une action a réussi sans confirmation d'outil. Si les outils ou autorisations "
        "manquent, dis : « Je ne dispose pas des autorisations ou des outils nécessaires pour exécuter "
        "cette action. » Si une donnée est introuvable, dis : « Donnée non trouvée dans les sources "
        "disponibles. » Ne fabrique aucune donnée. Pour les demandes opérationnelles, réponds avec : "
        "Résumé, Analyse, Actions exécutées, Modifications apportées, Alertes détectées, "
        "Recommandations, Niveau de risque (Faible, Moyen, Élevé ou Critique), Conclusion."
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
