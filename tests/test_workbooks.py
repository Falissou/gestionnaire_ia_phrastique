import tempfile
import unittest
from pathlib import Path

from pharmacy_platform.workbooks import WorkbookStore


class WorkbookCommandTests(unittest.TestCase):
    def test_duplicate_command_is_rejected_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = WorkbookStore(Path(directory))
            command = {
                "product_name": "Paracetamol",
                "quantity": 10,
                "supplier": "Grossiste A",
                "expected_date": "2026-11-01",
            }
            store.add_command(command)

            with self.assertRaisesRegex(ValueError, "identique"):
                store.add_command({**command, "product_name": " paracetamol "})

            self.assertEqual(len(store.commands()), 1)


if __name__ == "__main__":
    unittest.main()
