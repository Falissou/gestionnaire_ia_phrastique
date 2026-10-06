"""SQLite-backed repositories for pharmacy inventory data."""

from datetime import date, datetime, timezone
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4

from pharmacy_platform.workbooks import command_signature


class SQLiteStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY,
                    product_code TEXT UNIQUE COLLATE NOCASE,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    category TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK (quantity >= 0),
                    min_quantity INTEGER NOT NULL CHECK (min_quantity >= 0),
                    unit_price REAL NOT NULL CHECK (unit_price >= 0),
                    expiry_date TEXT,
                    supplier TEXT,
                    entry_date TEXT,
                    source_status TEXT,
                    comments TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commands (
                    id TEXT PRIMARY KEY,
                    product_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK (quantity > 0),
                    supplier TEXT NOT NULL,
                    status TEXT NOT NULL,
                    order_date TEXT NOT NULL,
                    expected_date TEXT,
                    source_order_number TEXT,
                    product_code TEXT,
                    unit_price REAL,
                    total_amount REAL,
                    responsible TEXT,
                    comments TEXT
                );
                CREATE TABLE IF NOT EXISTS movements (
                    id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL REFERENCES products(id),
                    type TEXT NOT NULL CHECK (type IN ('entree', 'sortie')),
                    quantity INTEGER NOT NULL CHECK (quantity > 0),
                    date TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    reference TEXT
                );
                CREATE INDEX IF NOT EXISTS movements_date_idx ON movements(date);
                """
            )
            optional_columns = {
                "products": {
                    "supplier": "TEXT",
                    "entry_date": "TEXT",
                    "source_status": "TEXT",
                    "comments": "TEXT",
                },
                "commands": {
                    "source_order_number": "TEXT",
                    "product_code": "TEXT",
                    "unit_price": "REAL",
                    "total_amount": "REAL",
                    "responsible": "TEXT",
                    "comments": "TEXT",
                },
            }
            for table, columns in optional_columns.items():
                existing_columns = {
                    row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
                }
                for name, column_type in columns.items():
                    if name not in existing_columns:
                        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _product(row: sqlite3.Row) -> dict:
        return dict(row)

    @staticmethod
    def _command(row: sqlite3.Row) -> dict:
        return dict(row)

    def products(self) -> list[dict]:
        with self.lock, self._connection() as connection:
            return [self._product(row) for row in connection.execute("SELECT * FROM products ORDER BY name")]

    def commands(self) -> list[dict]:
        with self.lock, self._connection() as connection:
            return [self._command(row) for row in connection.execute("SELECT * FROM commands ORDER BY order_date DESC")]

    def validated_commands(self) -> list[dict]:
        with self.lock, self._connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """SELECT commands.*,
                        COALESCE(commands.product_code, products.product_code) AS export_product_code
                    FROM commands
                    LEFT JOIN products ON products.name = commands.product_name COLLATE NOCASE
                    WHERE commands.status = 'Commandée'
                    ORDER BY commands.order_date DESC, commands.product_name"""
                )
            ]

    def movements(self, kind: str | None = None) -> list[dict]:
        with self.lock, self._connection() as connection:
            sql = """
                SELECT movements.*, products.name AS product_name
                FROM movements JOIN products ON products.id = movements.product_id
            """
            parameters: tuple = ()
            if kind in ("entree", "sortie"):
                sql += " WHERE movements.type = ?"
                parameters = (kind,)
            sql += " ORDER BY movements.date"
            return [dict(row) for row in connection.execute(sql, parameters)]

    def add_product(self, data: dict) -> dict:
        row = {
            "id": str(uuid4()),
            "product_code": data.get("product_code"),
            "name": data["name"].strip(),
            "category": data.get("category") or "Médicament",
            "quantity": data["quantity"],
            "min_quantity": data.get("min_quantity", 5),
            "unit_price": data.get("unit_price", 0),
            "expiry_date": data.get("expiry_date"),
            "supplier": data.get("supplier"),
            "entry_date": data.get("entry_date"),
            "source_status": data.get("source_status"),
            "comments": data.get("comments"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            with self.lock, self._connection() as connection:
                connection.execute(
                    """INSERT INTO products
                    (id, product_code, name, category, quantity, min_quantity, unit_price, expiry_date,
                     supplier, entry_date, source_status, comments, updated_at)
                    VALUES (:id, :product_code, :name, :category, :quantity, :min_quantity, :unit_price,
                            :expiry_date, :supplier, :entry_date, :source_status, :comments, :updated_at)""",
                    row,
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Un produit portant ce nom ou ce code existe déjà.") from exc
        return row

    def add_command(self, data: dict) -> dict:
        with self.lock, self._connection() as connection:
            existing = connection.execute(
                "SELECT product_name, quantity, supplier, expected_date, status FROM commands"
            ).fetchall()
            signature = command_signature(data)
            if any(
                command_signature(dict(row)) == signature and row["status"] != "Annulée"
                for row in existing
            ):
                raise ValueError("Une commande identique existe déjà.")
            row = {
                "id": str(uuid4()),
                "status": "En attente",
                "order_date": date.today().isoformat(),
                "source_order_number": data.get("source_order_number"),
                "product_code": data.get("product_code"),
                "unit_price": data.get("unit_price"),
                "total_amount": data.get("total_amount"),
                "responsible": data.get("responsible"),
                "comments": data.get("comments"),
                **data,
            }
            connection.execute(
                """INSERT INTO commands
                (id, product_name, quantity, supplier, status, order_date, expected_date,
                 source_order_number, product_code, unit_price, total_amount, responsible, comments)
                VALUES (:id, :product_name, :quantity, :supplier, :status, :order_date, :expected_date,
                        :source_order_number, :product_code, :unit_price, :total_amount, :responsible, :comments)""",
                row,
            )
            return row

    def place_purchase_order(
        self,
        order_number: str,
        supplier: str,
        expected_date: str | None,
        responsible: str | None,
        comments: str | None,
        lines: list[dict],
    ) -> list[dict]:
        created = []
        order_date = date.today().isoformat()
        with self.lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for line in lines:
                product = connection.execute(
                    "SELECT * FROM products WHERE id = ?", (line["product_id"],)
                ).fetchone()
                if product is None:
                    raise LookupError("Un des produits sélectionnés n'existe plus.")
                if product["quantity"] > product["min_quantity"]:
                    raise ValueError(
                        f"{product['name']} n'est plus sous son seuil de réapprovisionnement."
                    )
                active_command = connection.execute(
                    """SELECT 1 FROM commands
                    WHERE product_name = ? COLLATE NOCASE
                      AND status NOT IN ('Reçue', 'Annulée')
                    LIMIT 1""",
                    (product["name"],),
                ).fetchone()
                if active_command:
                    raise ValueError(
                        f"Une commande active existe déjà pour {product['name']}."
                    )
                quantity = line["quantity"]
                unit_price = line["unit_price"]
                row = {
                    "id": str(uuid4()),
                    "product_name": product["name"],
                    "product_code": product["product_code"],
                    "quantity": quantity,
                    "supplier": supplier,
                    "status": "Commandée",
                    "order_date": order_date,
                    "expected_date": expected_date,
                    "source_order_number": order_number,
                    "unit_price": unit_price,
                    "total_amount": round(quantity * unit_price, 2),
                    "responsible": responsible,
                    "comments": comments,
                }
                connection.execute(
                    """INSERT INTO commands
                    (id, product_name, quantity, supplier, status, order_date, expected_date,
                     source_order_number, product_code, unit_price, total_amount, responsible, comments)
                    VALUES (:id, :product_name, :quantity, :supplier, :status, :order_date,
                            :expected_date, :source_order_number, :product_code, :unit_price,
                            :total_amount, :responsible, :comments)""",
                    row,
                )
                created.append(row)
        return created

    def add_movement(self, data: dict) -> dict:
        with self.lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            product_id = data.get("product_id")
            if product_id:
                product = connection.execute(
                    "SELECT * FROM products WHERE id = ?", (product_id,)
                ).fetchone()
            elif data["type"] == "entree":
                product = None
                product_code = (data.get("product_code") or "").strip()
                product_name = (data.get("product_name") or "").strip()
                if product_code or product_name:
                    matches = connection.execute(
                        """SELECT * FROM products
                        WHERE (? != '' AND product_code = ? COLLATE NOCASE)
                           OR (? != '' AND name = ? COLLATE NOCASE)""",
                        (product_code, product_code, product_name, product_name),
                    ).fetchall()
                    if len(matches) > 1:
                        raise ValueError("Le code et le nom désignent des produits différents.")
                    product = matches[0] if matches else None
                if product is None:
                    if not product_name:
                        raise ValueError("Le nom du nouveau produit est obligatoire.")
                    product = {
                        "id": str(uuid4()),
                        "product_code": product_code or None,
                        "name": product_name,
                        "category": data.get("category") or "Médicament",
                        "quantity": 0,
                        "min_quantity": data.get("min_quantity", 5),
                        "unit_price": data.get("unit_price", 0),
                        "expiry_date": data.get("expiry_date"),
                        "supplier": data.get("supplier"),
                        "entry_date": data.get("entry_date"),
                        "source_status": data.get("source_status"),
                        "comments": data.get("comments"),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    try:
                        connection.execute(
                            """INSERT INTO products
                            (id, product_code, name, category, quantity, min_quantity,
                             unit_price, expiry_date, supplier, entry_date, source_status, comments,
                             updated_at)
                            VALUES (:id, :product_code, :name, :category, :quantity,
                                    :min_quantity, :unit_price, :expiry_date, :supplier, :entry_date,
                                    :source_status, :comments, :updated_at)""",
                            product,
                        )
                    except sqlite3.IntegrityError as exc:
                        raise ValueError(
                            "Un produit portant ce nom ou ce code existe déjà."
                        ) from exc
            else:
                product = None
            if product is None:
                raise LookupError("Produit introuvable.")
            quantity = data["quantity"]
            if data["type"] == "sortie" and quantity > product["quantity"]:
                raise ValueError("La sortie dépasse la quantité actuellement en stock.")
            updated_quantity = product["quantity"] + (quantity if data["type"] == "entree" else -quantity)
            connection.execute(
                "UPDATE products SET quantity = ?, updated_at = ? WHERE id = ?",
                (updated_quantity, datetime.now(timezone.utc).isoformat(), product["id"]),
            )
            row = {
                "id": str(uuid4()),
                "product_id": product["id"],
                "product_name": product["name"],
                "type": data["type"],
                "quantity": quantity,
                "date": date.today().isoformat(),
                "reason": data["reason"],
                "reference": data.get("reference"),
            }
            connection.execute(
                """INSERT INTO movements (id, product_id, type, quantity, date, reason, reference)
                VALUES (:id, :product_id, :type, :quantity, :date, :reason, :reference)""",
                row,
            )
            return row

    def update_command_status(self, command_id: str, status: str) -> dict | None:
        with self.lock, self._connection() as connection:
            cursor = connection.execute(
                "UPDATE commands SET status = ? WHERE id = ?", (status, command_id)
            )
            if not cursor.rowcount:
                return None
            row = connection.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
            return self._command(row)

    def import_records(
        self, target: str, records: list[dict], adjust_stock: bool = False
    ) -> tuple[list[dict], int]:
        created: list[dict] = []
        duplicates = 0
        with self.lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for data in records:
                if target == "product":
                    duplicate = connection.execute(
                        """SELECT id FROM products
                        WHERE (product_code IS NOT NULL AND product_code = ? COLLATE NOCASE)
                           OR name = ? COLLATE NOCASE""",
                        (data.get("product_code"), data["name"]),
                    ).fetchone()
                    if duplicate:
                        duplicates += 1
                        continue
                    row = {
                        "id": str(uuid4()),
                        "product_code": data.get("product_code"),
                        "name": data["name"],
                        "category": data.get("category") or "Médicament",
                        "quantity": data["quantity"],
                        "min_quantity": data.get("min_quantity", 5),
                        "unit_price": data.get("unit_price", 0),
                        "expiry_date": data.get("expiry_date"),
                        "supplier": data.get("supplier"),
                        "entry_date": data.get("entry_date"),
                        "source_status": data.get("source_status"),
                        "comments": data.get("comments"),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    connection.execute(
                        """INSERT INTO products
                        (id, product_code, name, category, quantity, min_quantity, unit_price, expiry_date,
                         supplier, entry_date, source_status, comments, updated_at)
                        VALUES (:id, :product_code, :name, :category, :quantity, :min_quantity, :unit_price,
                                :expiry_date, :supplier, :entry_date, :source_status, :comments, :updated_at)""",
                        row,
                    )
                elif target == "command":
                    existing = connection.execute(
                        "SELECT product_name, quantity, supplier, expected_date, status FROM commands"
                    ).fetchall()
                    if any(
                        command_signature(dict(item)) == command_signature(data)
                        and item["status"] != "Annulée"
                        for item in existing
                    ):
                        duplicates += 1
                        continue
                    row = {
                        "id": str(uuid4()),
                        "status": data.get("status") or "En attente",
                        "order_date": data.get("order_date") or date.today().isoformat(),
                        "source_order_number": data.get("source_order_number"),
                        "product_code": data.get("product_code"),
                        "unit_price": data.get("unit_price"),
                        "total_amount": data.get("total_amount"),
                        "responsible": data.get("responsible"),
                        "comments": data.get("comments"),
                        **data,
                    }
                    connection.execute(
                        """INSERT INTO commands
                        (id, product_name, quantity, supplier, status, order_date, expected_date,
                         source_order_number, product_code, unit_price, total_amount, responsible, comments)
                        VALUES (:id, :product_name, :quantity, :supplier, :status, :order_date, :expected_date,
                                :source_order_number, :product_code, :unit_price, :total_amount, :responsible, :comments)""",
                        row,
                    )
                else:
                    product_code = (data.get("product_code") or "").strip()
                    product_name = (data.get("product_name") or "").strip()
                    matches = connection.execute(
                        """SELECT * FROM products
                        WHERE (? != '' AND product_code = ? COLLATE NOCASE)
                           OR (? != '' AND name = ? COLLATE NOCASE)""",
                        (product_code, product_code, product_name, product_name),
                    ).fetchall()
                    if len(matches) > 1:
                        raise ValueError(
                            f"Le code et le nom désignent des produits différents "
                            f"à la ligne {data.get('source_row', '?')}."
                        )
                    product = matches[0] if matches else None
                    if product is None and target == "entree" and adjust_stock and product_name:
                        new_product = {
                            "id": str(uuid4()),
                            "product_code": product_code or None,
                            "name": product_name,
                            "category": data.get("category") or "Médicament",
                            "quantity": 0,
                            "min_quantity": data.get("min_quantity", 5),
                            "unit_price": data.get("unit_price", 0),
                            "expiry_date": data.get("expiry_date"),
                            "supplier": data.get("supplier"),
                            "entry_date": data.get("entry_date"),
                            "source_status": data.get("source_status"),
                            "comments": data.get("comments"),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                        try:
                            connection.execute(
                                """INSERT INTO products
                                (id, product_code, name, category, quantity, min_quantity,
                                 unit_price, expiry_date, supplier, entry_date, source_status, comments,
                                 updated_at)
                                VALUES (:id, :product_code, :name, :category, :quantity,
                                        :min_quantity, :unit_price, :expiry_date, :supplier, :entry_date,
                                        :source_status, :comments, :updated_at)""",
                                new_product,
                            )
                        except sqlite3.IntegrityError as exc:
                            raise ValueError(
                                f"Un produit portant ce nom ou ce code existe déjà à la ligne "
                                f"{data.get('source_row', '?')}."
                            ) from exc
                        product = connection.execute(
                            "SELECT * FROM products WHERE id = ?", (new_product["id"],)
                        ).fetchone()
                    if product is None:
                        raise LookupError(
                            f"Produit introuvable pour la ligne {data.get('source_row', '?')} "
                            "(importez d'abord le stock produits ou corrigez le code/nom)."
                        )
                    duplicate = connection.execute(
                        """SELECT id FROM movements
                        WHERE product_id = ? AND type = ? AND quantity = ? AND date = ?
                          AND COALESCE(reference, '') = COALESCE(?, '') AND reason = ?""",
                        (
                            product["id"], target, data["quantity"], data["date"],
                            data.get("reference"), data["reason"],
                        ),
                    ).fetchone()
                    if duplicate:
                        duplicates += 1
                        continue
                    if adjust_stock:
                        delta = data["quantity"] if target == "entree" else -data["quantity"]
                        updated_quantity = product["quantity"] + delta
                        if updated_quantity < 0:
                            raise ValueError(
                                f"Stock insuffisant pour {product['name']} à la ligne "
                                f"{data.get('source_row', '?')}."
                            )
                        connection.execute(
                            "UPDATE products SET quantity = ?, updated_at = ? WHERE id = ?",
                            (updated_quantity, datetime.now(timezone.utc).isoformat(), product["id"]),
                        )
                    row = {
                        "id": str(uuid4()),
                        "product_id": product["id"],
                        "product_name": product["name"],
                        "type": target,
                        "quantity": data["quantity"],
                        "date": data["date"],
                        "reason": data["reason"],
                        "reference": data.get("reference"),
                    }
                    connection.execute(
                        """INSERT INTO movements
                        (id, product_id, type, quantity, date, reason, reference)
                        VALUES (:id, :product_id, :type, :quantity, :date, :reason, :reference)""",
                        row,
                    )
                created.append(row)
        return created, duplicates
