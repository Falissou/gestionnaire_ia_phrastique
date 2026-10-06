import sqlite3
import tempfile
import unittest
from pathlib import Path

from pharmacy_platform.sqlite_store import SQLiteStore


class SQLiteStoreTests(unittest.TestCase):
    def test_existing_database_is_upgraded_and_keeps_existing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "legacy.db"
            connection = sqlite3.connect(database_path)
            connection.executescript(
                """
                CREATE TABLE products (
                    id TEXT PRIMARY KEY, product_code TEXT, name TEXT NOT NULL,
                    category TEXT NOT NULL, quantity INTEGER NOT NULL,
                    min_quantity INTEGER NOT NULL, unit_price REAL NOT NULL,
                    expiry_date TEXT, updated_at TEXT NOT NULL
                );
                CREATE TABLE commands (
                    id TEXT PRIMARY KEY, product_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL, supplier TEXT NOT NULL,
                    status TEXT NOT NULL, order_date TEXT NOT NULL,
                    expected_date TEXT
                );
                CREATE TABLE movements (
                    id TEXT PRIMARY KEY, product_id TEXT NOT NULL,
                    type TEXT NOT NULL, quantity INTEGER NOT NULL,
                    date TEXT NOT NULL, reason TEXT NOT NULL, reference TEXT
                );
                INSERT INTO products VALUES
                    ('legacy-id', 'OLD001', 'Produit historique', 'Médicament', 3, 1, 25, NULL, '2026-01-01');
                """
            )
            connection.close()

            store = SQLiteStore(database_path)
            product = store.products()[0]
            self.assertEqual(product["name"], "Produit historique")
            self.assertIsNone(product["supplier"])
            store.add_product({
                "name": "Nouveau produit",
                "category": "Médicament",
                "quantity": 1,
                "min_quantity": 0,
                "unit_price": 5,
                "expiry_date": None,
                "supplier": "Grossiste",
                "entry_date": "2026-03-01",
                "source_status": "Disponible",
                "comments": "Importé",
            })
            added_product = next(
                item for item in store.products() if item["name"] == "Nouveau produit"
            )
            self.assertEqual(added_product["supplier"], "Grossiste")

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

    def test_entry_creates_missing_product_and_existing_entry_increases_stock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "stock.db")
            entry = store.add_movement({
                "product_code": "MED002",
                "product_name": "Ibuprofène",
                "category": "Antalgique",
                "quantity": 8,
                "type": "entree",
                "reason": "Réception",
                "reference": "BL-2",
                "supplier": "Grossiste B",
                "entry_date": "2026-04-02",
                "source_status": "Disponible",
                "comments": "Nouvelle référence",
            })
            product = store.products()[0]
            self.assertEqual(entry["product_name"], "Ibuprofène")
            self.assertEqual(product["quantity"], 8)
            self.assertEqual(product["product_code"], "MED002")
            self.assertEqual(product["supplier"], "Grossiste B")
            self.assertEqual(product["entry_date"], "2026-04-02")
            self.assertEqual(product["source_status"], "Disponible")
            self.assertEqual(product["comments"], "Nouvelle référence")

            store.add_movement({
                "product_id": product["id"],
                "type": "entree",
                "quantity": 3,
                "reason": "Réception complémentaire",
            })
            self.assertEqual(store.products()[0]["quantity"], 11)
            self.assertEqual(len(store.movements("entree")), 2)

    def test_exit_is_registered_and_decreases_stock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "stock.db")
            product = store.add_product({
                "name": "Produit test",
                "category": "Médicament",
                "quantity": 9,
                "min_quantity": 2,
                "unit_price": 1,
                "expiry_date": None,
            })
            store.add_movement({
                "product_id": product["id"],
                "type": "sortie",
                "quantity": 4,
                "reason": "Vente",
            })
            self.assertEqual(store.products()[0]["quantity"], 5)
            self.assertEqual(store.movements("sortie")[0]["quantity"], 4)

    def test_confirmed_new_entry_import_creates_product_and_adjusts_stock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "stock.db")
            imported, duplicates = store.import_records(
                "entree",
                [{
                    "product_code": "MED003",
                    "product_name": "Amoxicilline",
                    "quantity": 6,
                    "date": "2026-10-06",
                    "reason": "Réception",
                    "reference": "BL-3",
                }],
                adjust_stock=True,
            )
            self.assertEqual(duplicates, 0)
            self.assertEqual(imported[0]["type"], "entree")
            self.assertEqual(store.products()[0]["name"], "Amoxicilline")
            self.assertEqual(store.products()[0]["quantity"], 6)


if __name__ == "__main__":
    unittest.main()
