import tempfile
import unittest
from pathlib import Path

from pharmacy_platform.sqlite_store import SQLiteStore


class SQLiteStoreTests(unittest.TestCase):
    def test_products_commands_and_manual_movements_use_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "stock.db")
            product = store.add_product({
                "product_code": "MED001",
                "name": "Paracétamol",
                "category": "Antalgique",
                "quantity": 10,
                "min_quantity": 2,
                "unit_price": 500,
                "expiry_date": None,
            })
            movement = store.add_movement({
                "product_id": product["id"],
                "type": "entree",
                "quantity": 4,
                "reason": "Réception",
                "reference": "BL-1",
            })
            self.assertEqual(store.products()[0]["quantity"], 14)
            self.assertEqual(store.movements()[0]["product_name"], "Paracétamol")
            self.assertEqual(movement["type"], "entree")

            command = store.add_command({
                "product_name": "Paracétamol",
                "quantity": 5,
                "supplier": "Grossiste",
                "expected_date": "2026-11-01",
            })
            self.assertEqual(store.update_command_status(command["id"], "Commandée")["status"], "Commandée")

    def test_import_is_idempotent_and_historical_movements_do_not_adjust_stock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "stock.db")
            product, duplicate = store.import_records("product", [{
                "product_code": "MED001",
                "name": "Paracétamol",
                "category": "Antalgique",
                "quantity": 19,
                "min_quantity": 5,
                "unit_price": 500,
                "expiry_date": "2027-01-21",
            }])
            self.assertEqual(len(product), 1)
            self.assertEqual(duplicate, 0)
            self.assertEqual(store.products()[0]["quantity"], 19)

            movement_data = [{
                "product_code": "MED001",
                "product_name": "Paracétamol",
                "quantity": 6,
                "date": "2026-01-04",
                "reason": "Vente",
                "reference": "Client 2",
            }]
            imported, duplicates = store.import_records("sortie", movement_data)
            self.assertEqual(len(imported), 1)
            self.assertEqual(duplicates, 0)
            self.assertEqual(store.products()[0]["quantity"], 19)

            imported_again, duplicates_again = store.import_records("sortie", movement_data)
            self.assertEqual(imported_again, [])
            self.assertEqual(duplicates_again, 1)
            self.assertEqual(len(store.movements()), 1)

    def test_failed_stock_adjustment_rolls_back_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "stock.db")
            store.add_product({
                "name": "Produit test",
                "category": "Médicament",
                "quantity": 2,
                "min_quantity": 0,
                "unit_price": 1,
                "expiry_date": None,
            })
            records = [{
                "product_name": "Produit test",
                "quantity": 1,
                "date": "2026-01-01",
                "reason": "Vente",
                "reference": None,
            }, {
                "product_name": "Produit test",
                "quantity": 2,
                "date": "2026-01-02",
                "reason": "Vente",
                "reference": None,
            }]
            with self.assertRaisesRegex(ValueError, "Stock insuffisant"):
                store.import_records("sortie", records, adjust_stock=True)
            self.assertEqual(store.products()[0]["quantity"], 2)
            self.assertEqual(store.movements(), [])


if __name__ == "__main__":
    unittest.main()
