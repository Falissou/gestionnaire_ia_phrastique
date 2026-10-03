# Données et API

## Classeurs Excel

Les classeurs sont générés à la première exécution si absents; les fichiers ne sont pas inclus dans Git.

| Fichier | Feuille | Champs |
|---|---|---|
| `commandes_stock.xlsx` | `Stock` | id, name, category, quantity, min_quantity, unit_price, expiry_date, updated_at |
| `commandes_stock.xlsx` | `Commandes` | id, product_name, quantity, supplier, status, order_date, expected_date |
| `entrees_sorties.xlsx` | `Entrees` / `Sorties` | id, product_id, product_name, quantity, date, reason, reference |

L'API ajoute les produits, commandes et mouvements dans ces classeurs. Un mouvement entrant augmente le stock; un mouvement sortant le diminue après vérification de la quantité disponible. Les commandes ont les états `En attente`, `Commandée`, `Reçue` ou `Annulée`.

## Routes

| Méthode | Route | Fonction |
|---|---|---|
| `GET` | `/api/health` | Vérification de disponibilité |
| `GET` / `POST` | `/api/products` | Lire / créer des produits |
| `GET` / `POST` | `/api/commands` | Lire / créer des commandes |
| `PATCH` | `/api/commands/{id}` | Mettre à jour l'état d'une commande |
| `GET` / `POST` | `/api/movements` | Lire / enregistrer un mouvement |
| `GET` | `/api/dashboard` | Indicateurs, alertes et mouvements récents |
| `GET` | `/api/alerts`, `/api/recommendations` | Veille et recommandations |
| `POST` | `/api/alerts/email` | Envoyer les alertes via SMTP |
| `GET` | `/api/agents` | Liste des agents configurés |
| `POST` | `/api/agents/{name}/chat` | Question à un agent Foundry |

Toutes les routes, sauf la santé, requièrent un Bearer token lorsque `AUTH_ENABLED=true`.
