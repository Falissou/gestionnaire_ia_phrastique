# PharmaStock

Plateforme web de gestion de stock pour une pharmacie : catalogue et seuils de stock, commandes fournisseurs, entrées/sorties, alertes d'expiration, courriel d'alertes et assistant Microsoft Foundry.

## Démarrer

1. Python 3.11 ou supérieur est recommandé. Créez un environnement virtuel et installez les dépendances :

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Complétez les valeurs Foundry dans `.env` (ne commitez jamais ce fichier). Le projet fournit déjà des noms d'agents et les paramètres d'authentification/CORS. Pour activer la lecture SharePoint, ajoutez aussi les variables `SHAREPOINT_*` décrites dans [docs/FOUNDRY.md](docs/FOUNDRY.md).
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

Les données opérationnelles sont conservées dans `data/pharmastock.sqlite3` (SQLite). Les classeurs Excel présents dans `data/` servent de fichiers de référence et peuvent être prévisualisés puis importés depuis **Import & migration** dans l'application. Ils ne sont pas modifiés et ne sont pas importés automatiquement au démarrage. Les données du stock doivent être importées avant les mouvements, qui se rattachent aux produits par code ou nom.

## Agents

`FOUNDRY_AGENT_NAMES` associe, dans l'ordre, les noms Foundry aux rôles Commande et stock, Entrées et sorties, Veille produit et GestionAgent. Utilisez des noms de 1 à 63 caractères alphanumériques, avec des tirets uniquement au milieu (par exemple `CommandeStockAgent`). Le chat du frontend est relié à GestionAgent; l'application fournit aux agents un outil de lecture des données SQLite et propose des ajouts qui nécessitent une confirmation dans l'interface. La lecture d'une liste de documents SharePoint est facultative et configurée côté serveur. Configurez dans Foundry, pour chaque agent, sa base de connaissances et ses autres outils, puis testez et publiez chaque version.

Le backend calcule les alertes (seuils minimaux et dates d'expiration jusqu'à 90 jours), recommandations, statistiques et données du tableau de bord. Les commandes peuvent être créées dans le formulaire ou importées par CSV/Excel après vérification des lignes; les doublons sont ignorés. L'envoi d'e-mails est une action explicite de l'interface; configurez `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM` et, si requis, `SMTP_USER` / `SMTP_PASSWORD` dans l'environnement du serveur. Sans configuration SMTP, l'API indique clairement que l'envoi n'est pas disponible.

## Authentification et exploitation

Lorsque `AUTH_ENABLED=true`, l'API exige un jeton Microsoft Entra Bearer et valide sa signature, son audience (`ENTRA_API_AUDIENCE`) et son tenant (`ENTRA_TENANT_ID`) à l'aide de `ENTRA_JWKS_URL`. L'interface offre un champ de jeton pour le développement; en production, reliez-la à votre flux de connexion Entra et ne stockez pas les jetons dans un navigateur partagé. `CORS_ORIGINS` définit les origines autorisées. Le endpoint `/api/health` reste disponible sans authentification.

Consultez [docs/FOUNDRY.md](docs/FOUNDRY.md) pour les étapes Foundry et [docs/OPERATIONS.md](docs/OPERATIONS.md) pour la migration Excel, SQLite et les routes API.
