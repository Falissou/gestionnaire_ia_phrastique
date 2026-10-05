# Données et API

## Base de données

SQLite est la source opérationnelle de l'application. Par défaut, le fichier est `data/pharmastock.sqlite3`; le chemin peut être remplacé par `SQLITE_DATABASE_PATH`. Les tables `products`, `commands` et `movements` sont créées automatiquement au démarrage. Le fichier de base est local au serveur : prévoyez des sauvegardes régulières et ne le supprimez pas pendant que l'application fonctionne.

Les classeurs Excel présents dans `data/` sont des sources de référence, pas des bases modifiées directement par l'application. Ils ne sont ni importés ni modifiés automatiquement au démarrage.

## Migration des classeurs

Dans l'application, ouvrez **Import & migration**. Pour les fichiers de référence déjà placés dans `data/`, choisissez le type correspondant, puis le classeur local. Vous pouvez également téléverser un fichier `.xlsx` ou `.csv` (UTF-8, 5 Mo maximum, 5 000 lignes).

Les correspondances reconnues sont :

| Type | Classeur de référence | Données principales |
|---|---|---|
| Stock des produits | `Stock_Medicaments.xlsx` | Code, nom, catégorie, quantité, seuil, prix, expiration |
| Commandes | `Commandes_Fournisseurs.xlsx` | Produit, quantité, fournisseur, statut, dates |
| Entrées | `Entrees_Stock.xlsx` | Produit/code, date, quantité, fournisseur, bon de livraison |
| Sorties | `Sorties_Stock.xlsx` | Produit/code, date, quantité, motif, client/service |

Importez dans cet ordre : **stock**, **commandes**, **entrées**, **sorties**. Les entrées/sorties doivent retrouver un produit par code ou nom; importez donc le stock avant l'historique des mouvements. Les mouvements importés sont historisés sans changer le stock par défaut, afin d'éviter de compter deux fois des quantités déjà présentes dans le classeur de stock. Pour importer des mouvements nouveaux, cochez **Ajuster le stock** après avoir vérifié les lignes et les quantités.

L'aperçu valide les nombres et dates, indique les lignes invalides, reconnaît les doublons et interdit la confirmation si des erreurs restent présentes. La confirmation utilise un aperçu temporaire à usage unique, valable 15 minutes; aucun fichier source n'est conservé dans la base. L'import des lignes prêtes est transactionnel : une erreur empêche l'enregistrement partiel.

`Produits_Perimes.xlsx` est un relevé de péremptions par lot et n'est pas importé dans le schéma actuel, qui stocke la date d'expiration au niveau produit. Ne l'importez pas comme un inventaire : un schéma de lots devra être ajouté avant d'intégrer fidèlement cet historique.

## Import de commandes

Depuis **Commandes fournisseurs**, l'ancien raccourci d'import accepte `.csv` et `.xlsx` (5 Mo, 500 lignes). Le fichier doit avoir une ligne d'en-tête avec `Produit`, `Quantité` et `Fournisseur`; la date de livraison prévue est facultative. Les dates acceptées sont `AAAA-MM-JJ` et `JJ/MM/AAAA`. L'interface affiche un aperçu, refuse les lignes invalides et ignore les doublons.

## Routes

| Méthode | Route | Fonction |
|---|---|---|
| `GET` | `/api/health` | Vérification de disponibilité |
| `GET` / `POST` | `/api/products` | Lire / créer des produits |
| `GET` / `POST` | `/api/commands` | Lire / créer des commandes |
| `POST` | `/api/commands/import/preview` | Prévisualiser un import de commandes |
| `POST` | `/api/commands/import` | Importer les commandes après validation |
| `PATCH` | `/api/commands/{id}` | Mettre à jour l'état d'une commande |
| `GET` / `POST` | `/api/movements` | Lire / enregistrer un mouvement |
| `GET` | `/api/import/references` | Lister les classeurs de référence disponibles dans `data/` |
| `POST` | `/api/import/preview` | Prévisualiser une migration ou un import |
| `POST` | `/api/import/confirm` | Confirmer un aperçu temporaire et enregistrer les lignes prêtes |
| `GET` | `/api/dashboard` | Indicateurs, alertes et mouvements récents |
| `GET` | `/api/alerts`, `/api/recommendations` | Veille et recommandations |
| `POST` | `/api/alerts/email` | Envoyer les alertes via SMTP |
| `GET` | `/api/agents` | Liste des agents configurés |
| `POST` | `/api/chat` | Interroger GestionAgent |

Les agents lisent les données de SQLite et peuvent proposer des ajouts, mais la confirmation de l'utilisateur reste nécessaire avant écriture. Le stockage de factures, leur lecture assistée par agent et la gestion des lots ne sont pas encore implémentés.

Toutes les routes, sauf la santé, requièrent un jeton lorsque `AUTH_ENABLED=true`.
