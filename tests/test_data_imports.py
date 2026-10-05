import unittest

from fastapi import HTTPException

from pharmacy_platform.data_imports import parse_import_rows


class DataImportTests(unittest.TestCase):
    def test_reference_stock_columns_are_normalized(self) -> None:
        rows = [
            (1, ["Code Produit", "Nom Médicament", "Catégorie", "Quantité Stock", "Seuil Alerte", "Prix Unitaire (FCFA)", "Date Expiration"]),
            (2, ["MED001", "Paracétamol", "Antalgique", 19, 16, 500, "21/01/2027"]),
        ]
        parsed = parse_import_rows("product", rows)
        self.assertEqual(parsed[0]["status"], "ready")
        self.assertEqual(parsed[0]["product_code"], "MED001")
        self.assertEqual(parsed[0]["quantity"], 19)
        self.assertEqual(parsed[0]["expiry_date"], "2027-01-21")

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

    def test_missing_required_column_fails_with_clear_error(self) -> None:
        rows = [(1, ["Produit", "Quantité"]), (2, ["Article", 1])]
        with self.assertRaises(HTTPException) as context:
            parse_import_rows("command", rows)
        self.assertIn("fournisseur", context.exception.detail)


if __name__ == "__main__":
    unittest.main()
