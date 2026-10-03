# Déployer les agents dans Microsoft Foundry

## Préparer le projet

Dans `.env`, configurez `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL_DEPLOYMENT` et les quatre noms séparés par des virgules dans `FOUNDRY_AGENT_NAMES`. Les noms présents dans le dépôt sont `Commande&stockAgent`, `Entree&sortisAgent`, `VeilleproduitAgent` et `GestionAgent`. L'endpoint du projet ressemble à `https://<ressource>.services.ai.azure.com/api/projects/<projet>`.

Installez `requirements.txt`, authentifiez-vous avec `az login`, puis exécutez depuis la racine :

```bash
python scripts/create_agent.py
python scripts/create_agent.py --agent "GestionAgent"
```

Le script crée les agents absents avec leurs instructions de rôle et le déploiement configuré. Les agents déjà présents ne sont pas modifiés; ajustez leurs instructions ou leur version dans Foundry si nécessaire. L'identité qui exécute le script doit avoir les droits nécessaires sur le projet.

## Relier les connaissances et outils

Les classeurs gérés par l'application se trouvent dans `data/commandes_stock.xlsx` (**Stock**, **Commandes**) et `data/entrees_sorties.xlsx` (**Entrees**, **Sorties**). Le backend lit les classeurs pour les opérations métier et transmet un instantané courant à l'agent interrogé. Les classeurs ne sont pas automatiquement chargés dans les connaissances hébergées de Foundry : si vous souhaitez une recherche documentaire native, ajoutez les fichiers ou une source indexée depuis Foundry et validez les droits d'accès.

Dans Foundry, ouvrez chaque agent pour sélectionner le modèle et configurer les outils Work IQ ou les connexions disponibles dans votre tenant. GestionAgent est l'orchestrateur : son rôle est de synthétiser les informations et recommandations des domaines stock/commandes, mouvements et veille. L'application expose également ces fonctions sous forme de routes API :

- `GET /api/dashboard`, `GET /api/alerts` et `GET /api/recommendations`;
- `POST /api/alerts/email` pour un envoi explicite via SMTP configuré;
- `POST /api/agents/{nom}/chat` pour interroger un agent avec son contexte Excel opérationnel.

La création des agents dans Foundry ne provisionne pas automatiquement les connexions Work IQ : leur disponibilité et leur configuration dépendent de votre projet et de votre tenant Microsoft.

## Tester et publier

Testez chaque agent dans le Playground, validez le comportement et les évaluations dans Foundry, puis publiez la version voulue. Lancez l'API avec `uvicorn pharmacy_platform.main:app --app-dir backend`; le frontend est servi par la même application. Pour la production, utilisez une identité managée avec les rôles minimaux, configurez Entra ID, CORS, SMTP et la connectivité réseau; définissez également une stratégie de sauvegarde pour les classeurs.
