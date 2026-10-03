# PharmaStock

Plateforme web de gestion de stock pour une pharmacie : catalogue et seuils de stock, commandes fournisseurs, entrées/sorties, alertes d'expiration, courriel d'alertes et assistant Microsoft Foundry.

## Démarrer

1. Python 3.11 ou supérieur est recommandé. Créez un environnement virtuel et installez les dépendances :

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Complétez les valeurs Foundry dans `.env` (ne commitez jamais ce fichier). Le projet fournit déjà des noms d'agents et les paramètres d'authentification/CORS.
3. Connectez-vous à Azure (`az login`), puis créez les agents :

   ```bash
   python scripts/create_agent.py
   # ou un seul agent dont le nom est dans FOUNDRY_AGENT_NAMES :
   python scripts/create_agent.py --agent "GestionAgent"
   ```

4. Lancez l'application depuis la racine du dépôt :

   ```bash
   uvicorn pharmacy_platform.main:app --app-dir backend --reload
   ```

   Ouvrez <http://127.0.0.1:8000>. La documentation interactive de l'API est sur `/docs`.

Les classeurs sont créés automatiquement dans `data/` au premier démarrage. `commandes_stock.xlsx` contient les feuilles **Stock** et **Commandes**; `entrees_sorties.xlsx` contient **Entrees** et **Sorties**. Ces classeurs constituent les sources de données opérationnelles : les modifications de stock et les mouvements sont conservés dans Excel.

## Agents

`FOUNDRY_AGENT_NAMES` associe, dans l'ordre, les noms Foundry aux rôles Commande&stock, Entrée&sortie, Veille produit et GestionAgent. GestionAgent reçoit un instantané du stock, des commandes, des mouvements et des alertes à chaque question; les agents spécialisés reçoivent ce même contexte pour fonder leurs réponses sur les données des classeurs. Configurez dans le portail Foundry le déploiement de modèle et les éventuelles sources de connaissance/outils Work IQ souhaités, puis testez et publiez chaque version.

Le backend calcule les alertes (seuils minimaux et dates d'expiration jusqu'à 90 jours), recommandations, statistiques et données du tableau de bord. L'envoi d'e-mails est une action explicite de l'interface; configurez `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM` et, si requis, `SMTP_USER` / `SMTP_PASSWORD` dans l'environnement du serveur. Sans configuration SMTP, l'API indique clairement que l'envoi n'est pas disponible.

## Authentification et exploitation

Lorsque `AUTH_ENABLED=true`, l'API exige un jeton Microsoft Entra Bearer et valide sa signature, son audience (`ENTRA_API_AUDIENCE`) et son tenant (`ENTRA_TENANT_ID`) à l'aide de `ENTRA_JWKS_URL`. L'interface offre un champ de jeton pour le développement; en production, reliez-la à votre flux de connexion Entra et ne stockez pas les jetons dans un navigateur partagé. `CORS_ORIGINS` définit les origines autorisées. Le endpoint `/api/health` reste disponible sans authentification.

Consultez [docs/FOUNDRY.md](docs/FOUNDRY.md) pour les étapes Foundry et [docs/OPERATIONS.md](docs/OPERATIONS.md) pour le modèle des classeurs et les routes API.
