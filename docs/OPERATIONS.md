# Données et API

## Base de données

SQLite est la source opérationnelle de l'application. Par défaut, le fichier est `data/pharmastock.sqlite3`; le chemin peut être remplacé par `SQLITE_DATABASE_PATH`. Les tables `products`, `commands` et `movements` sont créées automatiquement au démarrage. Le fichier de base est local au serveur : prévoyez des sauvegardes régulières et ne le supprimez pas pendant que l'application fonctionne.

Les classeurs Excel présents dans `data/` sont des sources de référence, pas des bases modifiées directement par l'application. Ils ne sont ni importés ni modifiés automatiquement au démarrage.

Les listes du catalogue, des commandes, des suggestions, des mouvements et des alertes sont paginées. Chaque liste permet d'afficher 5 ou 10 lignes à la fois et de naviguer vers les pages précédentes ou suivantes.

## Migration des classeurs

Dans l'application, ouvrez **Import & migration**. Choisissez le type de données : le classeur de référence correspondant dans `data/` est sélectionné automatiquement. Vous pouvez également téléverser un fichier `.xlsx` ou `.csv` (UTF-8, 5 Mo maximum, 5 000 lignes), qui remplacera la référence automatique.

Les correspondances reconnues sont :

| Type | Classeur de référence | Données principales |
|---|---|---|
| Stock des produits | `Stock_Medicaments.xlsx` | Code, nom, catégorie, quantité en stock, seuil, prix, expiration |
| Commandes | `Commandes_type.xlsx` | N° commande, dates, fournisseur, code/nom produit, quantité, statut |
| Entrées | `Entrée_type.xlsx` | Code/nom produit, quantité à ajouter, motif, date prévue |
| Sorties | `Sortis_type.xlsx` | Code/nom produit, quantité sortie, date |

Les noms de colonnes sont normalisés (accents, espaces et ponctuation ignorés). L'import du stock conserve aussi le fournisseur, la date d'entrée, le statut source et les commentaires. L'import des commandes conserve le numéro de commande source, le code produit, le prix unitaire, le montant total, le responsable et les commentaires en plus des dates et du statut. Les statuts source `Validée` et `En cours de livraison` sont importés comme `Commandée`; `Reçue`/`Livrée` deviennent `Reçue`, et les statuts annulés restent `Annulée`. Pour les entrées, `Date Entrée Prévue` alimente la date du mouvement; le motif est également conservé. Une base SQLite existante reçoit automatiquement les nouvelles colonnes au démarrage, sans supprimer les données déjà enregistrées.

Importez dans cet ordre : **stock**, **commandes**, **entrées**, **sorties**. Les entrées/sorties doivent retrouver un produit par code ou nom; importez donc le stock avant l'historique des mouvements. Les mouvements importés sont historisés sans changer le stock par défaut, afin d'éviter de compter deux fois des quantités déjà présentes dans le classeur de stock. Pour importer des mouvements nouveaux, cochez **Ajuster le stock** après avoir vérifié les lignes et les quantités. Une entrée nouvelle avec un nom de produit et cette option cochée crée aussi la référence absente et initialise son stock avec la quantité reçue.

Dans **Entrées & sorties**, les deux registres sont séparés. Une entrée manuelle peut sélectionner un produit existant ou créer une nouvelle référence; dans les deux cas, la quantité entrée est ajoutée au stock dans la même transaction. Une sortie ne peut porter que sur un produit existant et est refusée si le stock est insuffisant.

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
| `GET` | `/api/commands/export/validated` | Télécharger les commandes au statut `Commandée` au format Excel |
| `POST` | `/api/commands/import/preview` | Prévisualiser un import de commandes |
| `POST` | `/api/commands/import` | Importer les commandes après validation |
| `PATCH` | `/api/commands/{id}` | Mettre à jour l'état d'une commande |
| `GET` / `POST` | `/api/movements` | Lire / enregistrer un mouvement (`GET` accepte `?kind=entree` ou `?kind=sortie`) |
| `GET` | `/api/import/references` | Lister les classeurs de référence disponibles dans `data/` |
| `POST` | `/api/import/preview` | Prévisualiser une migration ou un import |
| `POST` | `/api/import/confirm` | Confirmer un aperçu temporaire et enregistrer les lignes prêtes |
| `GET` | `/api/dashboard` | Indicateurs, alertes et mouvements récents |
| `GET` | `/api/alerts`, `/api/recommendations` | Veille et recommandations |
| `POST` | `/api/alerts/email` | Envoyer les alertes via SMTP |
| `GET` | `/api/agents` | Liste des agents configurés |
| `POST` | `/api/chat` | Interroger GestionAgent |

Les agents lisent les données de SQLite et peuvent proposer des ajouts, mais la confirmation de l'utilisateur reste nécessaire avant écriture. Le stockage de factures, leur lecture assistée par agent et la gestion des lots ne sont pas encore implémentés.

GestionAgent peut envoyer par SMTP un état de stock lorsque l'utilisateur le demande explicitement. Définissez `SMTP_RECIPIENTS` dans `.env` (adresses séparées par `,` ou `;`) avec `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM` et, si requis, `SMTP_USER` / `SMTP_PASSWORD`. Les destinataires sont fixes côté serveur et ne peuvent pas être choisis par l'agent.

Le chat fonctionne uniquement en texte et n'ouvre pas de session audio temps réel Foundry. L'agent GestionAgent configuré dans Foundry doit être de type Prompt; un agent créé en mode Voice n'est pas utilisé pour les échanges du chat.

`GET /api/recommendations` inclut `orders`, une liste de produits sous leur seuil (hors commandes déjà actives) et une quantité suggérée pour remonter au seuil. Le navigateur met en cache les suggestions pendant cinq heures et les recharge au plus à cette fréquence, y compris après une visite interrompue. Les données opérationnelles restent actualisées toutes les 60 secondes. La création d'une commande et le passage au statut `Commandée` restent des actions manuelles; une réception doit être enregistrée comme une entrée de stock.

Dans **Commandes fournisseurs**, **Exporter les commandes validées** télécharge les commandes ayant le statut `Commandée`. Les commandes en attente, reçues ou annulées sont exclues. Le fichier reprend les champs du modèle des classeurs : numéro source (ou identifiant généré), date, fournisseur, code et nom du produit, quantité, prix unitaire, montant total, date prévue, statut, responsable et commentaires.

Le bon Excel généré lors de la passation contient un onglet **Import entrée** compatible avec l'import des mouvements. Lors de la réception réelle, complétez la colonne **Date Entrée**, puis importez le classeur depuis **Import & migration** comme **Entrées de stock**, avec **Ajuster le stock** coché. La quantité reçue sera ajoutée au stock et enregistrée comme mouvement; le second onglet conserve le bon fournisseur imprimable. Si les quantités effectivement reçues diffèrent du bon, corrigez-les dans l'onglet d'import avant de confirmer.

Toutes les routes, sauf la santé, requièrent un jeton lorsque `AUTH_ENABLED=true`.
