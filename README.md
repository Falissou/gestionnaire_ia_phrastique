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

   Si les agents ont déjà été créés, ajoutez les outils SQLite en publiant une nouvelle version :

   ```bash
   python scripts/create_agent.py --update
   ```

4. Lancez l'application depuis la racine du dépôt :

   ```bash
   uvicorn pharmacy_platform.main:app --app-dir backend --reload
   ```

   Ouvrez <http://127.0.0.1:8000>. La documentation interactive de l'API est sur `/docs`.

Les données opérationnelles sont conservées dans `data/pharmastock.sqlite3` (SQLite). Les classeurs Excel présents dans `data/` servent de fichiers de référence et peuvent être prévisualisés puis importés depuis **Import & migration** dans l'application. Ils ne sont pas modifiés et ne sont pas importés automatiquement au démarrage. Les entrées et sorties sont affichées dans deux registres distincts; une entrée peut créer un produit ou augmenter son stock, et une sortie diminue le stock dans la même transaction.

## Agents

`FOUNDRY_AGENT_NAMES` associe, dans l'ordre, les noms Foundry aux rôles Commande et stock, Entrées et sorties, Veille produit et GestionAgent. Utilisez des noms de 1 à 63 caractères alphanumériques, avec des tirets uniquement au milieu (par exemple `CommandeStockAgent`). Le chat du frontend interroge les trois agents spécialisés en parallèle avant de transmettre leurs comptes rendus à GestionAgent. Les versions d'agents configurées doivent disposer de leurs bases de connaissances Foundry. L'agent de commande reçoit également l'outil web_search; vous pouvez relier une connexion de recherche du projet avec `FOUNDRY_WEB_SEARCH_CONNECTION_ID`. Les résultats web sont affichés avec leurs liens. La lecture d'une liste de documents SharePoint est facultative et configurée côté serveur. Toute écriture opérationnelle reste soumise à confirmation dans l'interface. GestionAgent peut aussi être un agent Foundry créé en mode Voice; `FOUNDRY_VOICE_AGENT_NAME` le désigne (par défaut `GestionAgent`). Un bouton du chat permet alors d'enregistrer un message vocal et d'écouter la réponse parlée.

La page **Commandes** propose les réapprovisionnements calculés depuis les seuils et la quantité courante; les commandes actives évitent les suggestions en double. Les suggestions sont recalculées au plus toutes les cinq heures et conservées dans le navigateur entre les visites; les données opérationnelles, elles, restent actualisées toutes les 60 secondes. Les propositions n'envoient pas de commande fournisseur : renseignez le fournisseur, créez la commande, puis utilisez **Valider comme commandée** une fois la commande réellement passée. Le bouton **Exporter les commandes validées** télécharge les commandes avec le statut `Commandée` au format Excel. Le stock se met à jour à la réception via une entrée de stock.

Le backend calcule les alertes (seuils minimaux et dates d'expiration jusqu'à 90 jours), recommandations, statistiques et données du tableau de bord. Les commandes peuvent être créées dans le formulaire ou importées par CSV/Excel après vérification des lignes; les doublons sont ignorés. Configurez `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM` et, si requis, `SMTP_USER` / `SMTP_PASSWORD` dans `.env`. Pour l'envoi de l'état du stock par GestionAgent, renseignez également `SMTP_RECIPIENTS` avec une ou plusieurs adresses séparées par des virgules ou points-virgules. Cet envoi n'a lieu que lorsque l'utilisateur le demande explicitement. Sans configuration SMTP ou destinataire, l'agent signale que l'envoi n'est pas disponible.

## Authentification et exploitation

Lorsque `AUTH_ENABLED=true`, l'API exige un jeton Microsoft Entra Bearer et valide sa signature, son audience (`ENTRA_API_AUDIENCE`) et son tenant (`ENTRA_TENANT_ID`) à l'aide de `ENTRA_JWKS_URL`. L'interface offre un champ de jeton pour le développement; en production, reliez-la à votre flux de connexion Entra et ne stockez pas les jetons dans un navigateur partagé. `CORS_ORIGINS` définit les origines autorisées. Le endpoint `/api/health` reste disponible sans authentification.

Consultez [docs/FOUNDRY.md](docs/FOUNDRY.md) pour les étapes Foundry et [docs/OPERATIONS.md](docs/OPERATIONS.md) pour la migration Excel, SQLite et les routes API.


Pour lencer :
source .venv/bin/activate
uvicorn pharmacy_platform.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload