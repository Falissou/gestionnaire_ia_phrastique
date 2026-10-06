import unittest

from fastapi import HTTPException

from pharmacy_platform.data_imports import parse_import_rows


class DataImportTests(unittest.TestCase):
    def test_reference_stock_columns_are_normalized(self) -> None:
        rows = [
            (1, [
                "Code Produit", "Nom Médicament", "Catégorie", "Fournisseur",
                "Quantité Stock", "Seuil Alerte", "Prix Unitaire (FCFA)",
                "Date Entrée", "Date Expiration", "Statut Stock", "Commentaires",
            ]),
            (2, [
                "MED001", "Paracétamol", "Antalgique", "Pharma Plus", 19, 16,
                500, "03/09/2026", "21/01/2027", "Disponible", "Lot reçu",
            ]),
        ]
        parsed = parse_import_rows("product", rows)
        self.assertEqual(parsed[0]["status"], "ready")
        self.assertEqual(parsed[0]["product_code"], "MED001")
        self.assertEqual(parsed[0]["quantity"], 19)
        self.assertEqual(parsed[0]["expiry_date"], "2027-01-21")
        self.assertEqual(parsed[0]["supplier"], "Pharma Plus")
        self.assertEqual(parsed[0]["entry_date"], "2026-09-03")
        self.assertEqual(parsed[0]["source_status"], "Disponible")
        self.assertEqual(parsed[0]["comments"], "Lot reçu")

    def test_reference_movement_requires_known_product_fields_and_date(self) -> None:
        rows = [
            (1, ["ID Sortie", "Date Sortie", "Code Produit", "Nom Médicament", "Quantité Sortie", "Motif", "Service/Client"]),
            (2, ["SOR1", "04/01/2026", "MED001", "Paracétamol", 6, "Vente", "Client 2"]),
        ]
        parsed = parse_import_rows("sortie", rows)
        self.assertEqual(parsed[0]["status"], "ready")
        self.assertEqual(parsed[0]["date"], "2026-01-04")
        self.assertEqual(parsed[0]["reason"], "Vente")
        self.assertEqual(parsed[0]["reference"], "Client 2")

    def test_updated_command_template_preserves_order_dates_and_source_status(self) -> None:
        rows = [
            (1, [
                "N° Commande", "Date Commande", "Fournisseur", "Code Produit",
                "Nom Médicament", "Quantité Commandée", "Prix Unitaire (FCFA)",
                "Montant Total (FCFA)", "Date Livraison Prévue", "Statut Commande",
            ]),
            (2, [
                "CMD0001", "06/01/2026", "Fournisseur 2", "MED001", "Paracétamol",
                52, 550, 28600, "20/01/2026", "Validée",
            ]),
        ]
        parsed = parse_import_rows("command", rows)
        self.assertEqual(parsed[0]["status"], "ready")
        self.assertEqual(parsed[0]["product_name"], "Paracétamol")
        self.assertEqual(parsed[0]["quantity"], 52)
        self.assertEqual(parsed[0]["order_date"], "2026-01-06")
        self.assertEqual(parsed[0]["expected_date"], "2026-01-20")
        self.assertEqual(parsed[0]["command_status"], "Commandée")

    def test_updated_entry_template_recognizes_planned_date_and_quantity(self) -> None:
        rows = [
            (1, [
                "Code Produit", "Nom Médicament", "Quantité à Ajouter",
                "Motif", "Date Entrée Prévue",
            ]),
            (2, ["MED001", "Paracétamol", 81, "Réapprovisionnement", "10/10/2026"]),
        ]
        parsed = parse_import_rows("entree", rows)
        self.assertEqual(parsed[0]["status"], "ready")
        self.assertEqual(parsed[0]["quantity"], 81)
        self.assertEqual(parsed[0]["date"], "2026-10-10")
        self.assertEqual(parsed[0]["reason"], "Réapprovisionnement")

    def test_missing_required_column_fails_with_clear_error(self) -> None:
        rows = [(1, ["Produit", "Quantité"]), (2, ["Article", 1])]
        with self.assertRaises(HTTPException) as context:
            parse_import_rows("command", rows)
        self.assertIn("fournisseur", context.exception.detail)


if __name__ == "__main__":
    unittest.main()
