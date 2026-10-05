import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from pharmacy_platform import main
from pharmacy_platform.sqlite_store import SQLiteStore


class ImportApiTests(unittest.TestCase):
    def test_import_requires_a_valid_one_time_preview(self) -> None:
        csv_content = (
            "Code Produit,Nom Médicament,Catégorie,Quantité Stock,Seuil Alerte,Prix Unitaire (FCFA)\n"
            "MED001,Paracétamol,Antalgique,19,5,500\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "test.sqlite3")
            main.app.dependency_overrides[main.require_auth] = lambda: None
            try:
                with (
                    patch.object(main, "store", store),
                    patch.object(main.settings, "data_dir", Path(directory)),
                    TestClient(main.app) as client,
                ):
                    preview = client.post(
                        "/api/import/preview",
                        data={"target": "product"},
                        files={"file": ("stock.csv", csv_content, "text/csv")},
                    )
                    self.assertEqual(preview.status_code, 200, preview.text)
                    result = preview.json()
                    self.assertEqual(result["ready_count"], 1)
                    self.assertTrue(result["preview_id"])
                    self.assertEqual(store.products(), [])

                    imported = client.post(
                        "/api/import/confirm",
                        data={"preview_id": result["preview_id"]},
                    )
                    self.assertEqual(imported.status_code, 200, imported.text)
                    self.assertEqual(imported.json()["created_count"], 1)
                    self.assertEqual(store.products()[0]["product_code"], "MED001")

                    replay = client.post(
                        "/api/import/confirm",
                        data={"preview_id": result["preview_id"]},
                    )
                    self.assertEqual(replay.status_code, 409)
            finally:
                main.app.dependency_overrides.pop(main.require_auth, None)


if __name__ == "__main__":
    unittest.main()
