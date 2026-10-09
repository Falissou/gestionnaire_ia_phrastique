# Déployer les agents dans Microsoft Foundry

## Préparer le projet

Dans `.env`, configurez `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL_DEPLOYMENT` et les quatre noms séparés par des virgules dans `FOUNDRY_AGENT_NAMES`. Les noms par défaut sont `CommandeStockAgent`, `EntreesSortiesAgent`, `VeilleProduitAgent` et `GestionAgent`. Foundry exige des noms de 1 à 63 caractères alphanumériques, avec des tirets uniquement au milieu. L'endpoint du projet ressemble à `https://<ressource>.services.ai.azure.com/api/projects/<projet>`.

Installez `requirements.txt`, authentifiez-vous avec `az login`, puis exécutez depuis la racine :

```bash
python scripts/create_agent.py
python scripts/create_agent.py --agent "GestionAgent"
```

Le script crée les agents absents avec leurs instructions de rôle, le modèle configuré et les outils applicatifs décrits ci-dessous. Il ajoute l'outil web_search de Foundry à CommandeStockAgent. Pour relier une connexion de recherche web du projet, configurez son identifiant et, facultativement, le nom d'instance :

```dotenv
FOUNDRY_WEB_SEARCH_CONNECTION_ID=<identifiant-de-connexion-du-projet>
FOUNDRY_WEB_SEARCH_INSTANCE_NAME=pharmastock
```

Sans identifiant, l'outil web_search natif Foundry est activé sans connexion personnalisée. L'accès réel dépend des capacités activées pour le projet et le déploiement. Les identifiants restent côté serveur; ne les placez jamais dans le frontend.

Si les agents existent déjà, créez une nouvelle version munie des outils SQLite et de recherche. Le script conserve les outils Foundry préexistants et les sources de connaissances reliées; une nouvelle connexion web configurée remplace uniquement l'ancien outil web_search de CommandeStockAgent :

```bash
python scripts/create_agent.py --update
# ou mettre à jour uniquement l'agent utilisé par l'interface :
python scripts/create_agent.py --agent "GestionAgent" --update
```

Sans `--update`, les agents déjà présents ne sont pas modifiés. L'identité qui exécute le script doit avoir les droits nécessaires sur le projet.

## Relier les connaissances et outils

Les données opérationnelles gérées par l'application sont enregistrées dans SQLite (`data/pharmastock.sqlite3`). Le chat cible le véritable agent Foundry nommé avec une référence `agent_reference`. Ses outils de fonction sont enregistrés dans la définition de sa version Foundry (ils ne doivent pas être ajoutés au corps de la requête de l'agent). La requête transmet le texte utilisateur comme chaîne `input`; les retours de fonctions sont envoyés comme éléments `function_call_output`, selon le schéma Responses pris en charge par l'agent. L'application exécute les appels demandés par l'agent : `get_inventory_snapshot` lit les produits, commandes et mouvements dans SQLite; `propose_product`, `propose_command` et `propose_movement` préparent des ajouts qui ne sont écrits qu'après confirmation dans l'interface. Après avoir déployé le code, exécutez `python scripts/create_agent.py --update` pour ajouter ces outils et instructions aux versions d'agents existantes. Les classeurs Excel présents dans `data/` sont des sources d'import seulement.

Configurez dans Foundry les sources de connaissances propres à chaque agent et vérifiez qu'elles sont présentes dans sa version publiée. Lors d'une conversation avec GestionAgent, celui-ci demande un compte rendu aux trois agents spécialisés avant de répondre; les comptes rendus et les citations web sont visibles dans l'interface. Les questions sur les entrées et sorties sont traitées prioritairement par EntreesSortiesAgent; le snapshot transmis distingue les mouvements des unités et fournit des totaux sur tout l'historique, plus les lignes récentes. Pour les demandes de fournisseur ou de réapprovisionnement, CommandeStockAgent recherche en ligne les fournisseurs des produits concernés dont le fournisseur n'est pas connu dans SQLite, privilégie les sites officiels et cite les URL. Si le pays ou la région de livraison n'est pas indiqué, la disponibilité locale reste à confirmer. Ces recherches produisent des renseignements uniquement : elles ne changent pas les données SQLite et la passation d'une commande fournisseur nécessite toujours une action humaine.

GestionAgent dispose également de l'outil `send_inventory_report_email`. Il envoie un état actualisé du stock (références, quantités, seuils et alertes) uniquement lorsque l'utilisateur demande explicitement cet envoi. Les destinataires ne sont pas fournis par le modèle : ils sont définis par `SMTP_RECIPIENTS` côté serveur, avec plusieurs adresses séparées par des virgules ou des points-virgules. Configurez aussi `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM` et, si nécessaire, `SMTP_USER` / `SMTP_PASSWORD`. Après avoir déployé le code, exécutez `python scripts/create_agent.py --agent "GestionAgent" --update` pour ajouter cet outil à la version Foundry existante.

### Bibliothèque SharePoint (facultatif)

L'API peut lire une liste explicite de documents depuis une bibliothèque SharePoint Microsoft 365 et joindre leur contenu à la demande envoyée à l'agent lorsque la question porte sur SharePoint, un document ou une procédure. Les questions opérationnelles ordinaires sont traitées à partir de SQLite et ne dépendent pas de SharePoint. Elle n'explore pas toute la bibliothèque et ne modifie aucun fichier SharePoint. Dans `.env`, configurez :

```dotenv
SHAREPOINT_TENANT_ID=<tenant Entra ID>
SHAREPOINT_CLIENT_ID=<identifiant de l'inscription d'application>
SHAREPOINT_CLIENT_SECRET=<secret conservé uniquement côté serveur>
SHAREPOINT_DRIVE_ID=<identifiant Graph de la bibliothèque de documents>
SHAREPOINT_DOCUMENT_PATHS=Procédures/Reception.docx;Référentiels/Médicaments.pdf
```

Les chemins sont relatifs à la racine de la bibliothèque et séparés par des points-virgules; seuls ces fichiers sont lus. Formats pris en charge : `.docx`, `.pdf`, `.txt` et `.md` (les PDF scannés nécessitent une OCR préalable). Limites : 10 fichiers, 10 Mio par fichier et 80 000 caractères au total. L'application utilise une identité d'application Entra avec `SHAREPOINT_CLIENT_SECRET`; stockez ce secret dans le gestionnaire de secrets de votre hébergement, faites-le tourner régulièrement et ne le placez jamais dans le frontend ou Git. Accordez le minimum de droits Microsoft Graph possible (`Sites.Selected` avec accès en lecture au seul site, après consentement administrateur). Si la configuration est partielle ou que Graph refuse l'accès, le chat signale une erreur au lieu de prétendre avoir consulté les documents. Les sources effectivement jointes sont indiquées sous la réponse.

Pour obtenir l'identifiant de bibliothèque, sélectionnez la bibliothèque dans Microsoft Graph/SharePoint et relevez son `drive-id`. Le `site-id` SharePoint sert à l'administrateur pour accorder `Sites.Selected` au seul site; il n'est pas nécessaire dans l'environnement de l'application. Le chemin ne doit pas contenir `..` ni commencer par `/`.

GestionAgent est l'orchestrateur. Le chat de l'interface appelle sa version Foundry et traite les retours de fonctions pour accéder à SQLite. L'utilisateur doit confirmer chaque proposition dans l'interface avant que l'API écrive dans la base. L'application expose également ces fonctions sous forme de routes API :

- `GET /api/dashboard`, `GET /api/alerts` et `GET /api/recommendations`;
- `POST /api/alerts/email` pour un envoi explicite via SMTP configuré;
- `POST /api/chat` pour interroger GestionAgent avec ses connaissances et outils Foundry;
- `POST /api/products`, `/api/commands` et `/api/movements` pour les ajouts après confirmation;
- `POST /api/commands/import/preview` et `POST /api/commands/import` pour prévisualiser puis importer un fichier de commandes CSV ou Excel.

La création des agents dans Foundry ne provisionne pas automatiquement les connexions Work IQ : leur disponibilité et leur configuration dépendent de votre projet et de votre tenant Microsoft.

## Tester et publier

Testez chaque agent dans le Playground, validez le comportement et les évaluations dans Foundry, puis publiez la version voulue. Lancez l'API avec `uvicorn pharmacy_platform.main:app --app-dir backend`; le frontend est servi par la même application. Pour la production, utilisez une identité managée avec les rôles minimaux, configurez Entra ID, CORS, SMTP et la connectivité réseau; définissez également une stratégie de sauvegarde pour le fichier SQLite.
