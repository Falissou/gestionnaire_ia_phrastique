# Déployer les agents dans Microsoft Foundry

## Préparer le projet

Dans `.env`, configurez `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL_DEPLOYMENT` et les quatre noms séparés par des virgules dans `FOUNDRY_AGENT_NAMES`. Les noms par défaut sont `CommandeStockAgent`, `EntreesSortiesAgent`, `VeilleProduitAgent` et `GestionAgent`. Foundry exige des noms de 1 à 63 caractères alphanumériques, avec des tirets uniquement au milieu. L'endpoint du projet ressemble à `https://<ressource>.services.ai.azure.com/api/projects/<projet>`.

Installez `requirements.txt`, authentifiez-vous avec `az login`, puis exécutez depuis la racine :

```bash
python scripts/create_agent.py
python scripts/create_agent.py --agent "GestionAgent"
```

Le script crée les agents absents avec leurs instructions de rôle et le déploiement configuré. Les agents déjà présents ne sont pas modifiés; ajustez leurs instructions ou leur version dans Foundry si nécessaire. L'identité qui exécute le script doit avoir les droits nécessaires sur le projet.

## Relier les connaissances et outils

Les données opérationnelles gérées par l'application sont enregistrées dans SQLite (`data/pharmastock.sqlite3`). Pour chaque conversation, l'API expose aux agents un outil de lecture de ces données et des outils de proposition d'ajouts; aucune ligne n'est écrite avant confirmation dans l'interface. Les classeurs Excel présents dans `data/` sont des sources d'import seulement. Configurez dans Foundry une base de connaissances et les outils propres à chaque agent si vous souhaitez compléter ces sources.

### Bibliothèque SharePoint (facultatif)

L'API peut lire une liste explicite de documents depuis une bibliothèque SharePoint Microsoft 365 et joindre leur contenu à la demande envoyée à l'agent. Elle n'explore pas toute la bibliothèque et ne modifie aucun fichier SharePoint. Dans `.env`, configurez :

```dotenv
SHAREPOINT_TENANT_ID=<tenant Entra ID>
SHAREPOINT_CLIENT_ID=<identifiant de l'inscription d'application>
SHAREPOINT_CLIENT_SECRET=<secret conservé uniquement côté serveur>
SHAREPOINT_DRIVE_ID=<identifiant Graph de la bibliothèque de documents>
SHAREPOINT_DOCUMENT_PATHS=Procédures/Reception.docx;Référentiels/Médicaments.pdf
```

Les chemins sont relatifs à la racine de la bibliothèque et séparés par des points-virgules; seuls ces fichiers sont lus. Formats pris en charge : `.docx`, `.pdf`, `.txt` et `.md` (les PDF scannés nécessitent une OCR préalable). Limites : 10 fichiers, 10 Mio par fichier et 80 000 caractères au total. L'application utilise une identité d'application Entra avec `SHAREPOINT_CLIENT_SECRET`; stockez ce secret dans le gestionnaire de secrets de votre hébergement, faites-le tourner régulièrement et ne le placez jamais dans le frontend ou Git. Accordez le minimum de droits Microsoft Graph possible (`Sites.Selected` avec accès en lecture au seul site, après consentement administrateur). Si la configuration est partielle ou que Graph refuse l'accès, le chat signale une erreur au lieu de prétendre avoir consulté les documents. Les sources effectivement jointes sont indiquées sous la réponse.

Pour obtenir l'identifiant de bibliothèque, sélectionnez la bibliothèque dans Microsoft Graph/SharePoint et relevez son `drive-id`. Le `site-id` SharePoint sert à l'administrateur pour accorder `Sites.Selected` au seul site; il n'est pas nécessaire dans l'environnement de l'application. Le chemin ne doit pas contenir `..` ni commencer par `/`.

GestionAgent est l'orchestrateur : il coordonne les agents spécialisés avec les outils dont il dispose dans Foundry. Le chat de l'interface appelle GestionAgent. Les outils applicatifs lui permettent de lire les données SQLite, puis de proposer l'ajout d'un produit, d'une commande ou d'un mouvement. L'utilisateur doit confirmer chaque proposition dans l'interface avant que l'API écrive dans la base. L'application expose également ces fonctions sous forme de routes API :

- `GET /api/dashboard`, `GET /api/alerts` et `GET /api/recommendations`;
- `POST /api/alerts/email` pour un envoi explicite via SMTP configuré;
- `POST /api/chat` pour interroger GestionAgent avec ses connaissances et outils Foundry;
- `POST /api/products`, `/api/commands` et `/api/movements` pour les ajouts après confirmation;
- `POST /api/commands/import/preview` et `POST /api/commands/import` pour prévisualiser puis importer un fichier de commandes CSV ou Excel.

La création des agents dans Foundry ne provisionne pas automatiquement les connexions Work IQ : leur disponibilité et leur configuration dépendent de votre projet et de votre tenant Microsoft.

## Tester et publier

Testez chaque agent dans le Playground, validez le comportement et les évaluations dans Foundry, puis publiez la version voulue. Lancez l'API avec `uvicorn pharmacy_platform.main:app --app-dir backend`; le frontend est servi par la même application. Pour la production, utilisez une identité managée avec les rôles minimaux, configurez Entra ID, CORS, SMTP et la connectivité réseau; définissez également une stratégie de sauvegarde pour le fichier SQLite.
