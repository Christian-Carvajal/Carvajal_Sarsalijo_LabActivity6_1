"""
db_tools.py
Database tool definitions and function bindings for Perpetual Bistro Order Agent.
Handles SQLite operations, transactional integrity, stock deduction, and allergen queries.
"""

import os
import sqlite3
import json
from typing import Dict, Any, List, Optional
import uuid
import re

_BASE_DIR = os.path.dirname(__file__)
_RESOURCE_DB = os.path.join(_BASE_DIR, "resources", "restaurant.db")
_ROOT_DB = os.path.join(_BASE_DIR, "restaurant.db")

if os.path.exists(_RESOURCE_DB):
    DB_PATH = _RESOURCE_DB
elif os.path.exists(_ROOT_DB):
    DB_PATH = _ROOT_DB
elif os.path.isdir(os.path.join(_BASE_DIR, "resources")):
    DB_PATH = _RESOURCE_DB
else:
    DB_PATH = _ROOT_DB

SQL_INIT_PATH = os.path.join(_BASE_DIR, "init_restaurant_db.sql")


def get_db_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Creates a thread-safe connection to the SQLite database with dictionary rows and ensures tables exist."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Ensure kitchen_tickets table exists
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kitchen_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT UNIQUE NOT NULL,
            table_no INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            items_json TEXT NOT NULL,
            subtotal REAL NOT NULL,
            payment_method TEXT NOT NULL DEFAULT 'CASH',
            payment_ref TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'PREPARING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
    return conn


def init_db(db_path: str = DB_PATH, sql_path: str = SQL_INIT_PATH) -> None:
    """Initializes the database schema using init_restaurant_db.sql."""
    if not os.path.exists(sql_path):
        raise FileNotFoundError(f"SQL init file not found at {sql_path}")
    with open(sql_path, "r", encoding="utf-8") as f:
        sql_script = f.read()
    with get_db_connection(db_path) as conn:
        conn.executescript(sql_script)
        conn.commit()


def create_or_get_session(table_no: int, session_id: Optional[str] = None, db_path: str = DB_PATH) -> Dict[str, Any]:
    """Creates a new table session or retrieves an existing active session."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        if session_id:
            cursor.execute("SELECT * FROM table_sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)

        new_session_id = session_id or str(uuid.uuid4())[:8]
        cursor.execute(
            """
            INSERT OR REPLACE INTO table_sessions (session_id, table_no, status, updated_at)
            VALUES (?, ?, 'STATE_GREETING', CURRENT_TIMESTAMP)
            """,
            (new_session_id, table_no),
        )
        conn.commit()
        return {"session_id": new_session_id, "table_no": table_no, "status": "STATE_GREETING"}


def set_session_status(session_id: str, new_status: str, db_path: str = DB_PATH) -> bool:
    """Updates the FSM state stored in the table_sessions table."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE table_sessions SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
            (new_status, session_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_all_categories(db_path: str = DB_PATH) -> List[str]:
    """Returns a list of distinct menu categories."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM menu_items ORDER BY category")
        return [row["category"] for row in cursor.fetchall()]


MENU_ITEM_SYNONYMS = {
    # Burgers
    "perpetual cheeseburger": "Perpetual Classic Burger",
    "perpetual cheese burger": "Perpetual Classic Burger",
    "cheeseburger": "Perpetual Classic Burger",
    "cheese burger": "Perpetual Classic Burger",
    "classic cheeseburger": "Perpetual Classic Burger",
    "perpetual burger": "Perpetual Classic Burger",
    "classic burger": "Perpetual Classic Burger",
    "classic beef burger": "Perpetual Classic Burger",
    "beef burger": "Perpetual Classic Burger",
    "burger": "Perpetual Classic Burger",
    "burgers": "Perpetual Classic Burger",
    "bacon burger": "Bacon Mushroom Melt Burger",
    "bacon mushroom": "Bacon Mushroom Melt Burger",
    "mushroom burger": "Bacon Mushroom Melt Burger",
    "mushroom melt": "Bacon Mushroom Melt Burger",
    "chicken pesto": "Grilled Chicken Pesto Sandwich",
    "chicken pesto sandwich": "Grilled Chicken Pesto Sandwich",
    "pesto sandwich": "Grilled Chicken Pesto Sandwich",
    "chicken sandwich": "Grilled Chicken Pesto Sandwich",
    "buffalo tenders": "Crispy Buffalo Chicken Tenders",
    "buffalo chicken tenders": "Crispy Buffalo Chicken Tenders",
    "chicken tenders": "Crispy Buffalo Chicken Tenders",
    "tenders": "Crispy Buffalo Chicken Tenders",
    "bbq burger": "Smoked BBQ Bacon Brisket Burger",
    "brisket burger": "Smoked BBQ Bacon Brisket Burger",
    "bbq brisket burger": "Smoked BBQ Bacon Brisket Burger",

    # Pastas
    "truffle pasta": "Truffle Mushroom Pasta",
    "mushroom pasta": "Truffle Mushroom Pasta",
    "truffle mushroom": "Truffle Mushroom Pasta",
    "spaghetti": "Classic Spaghetti Bolognese",
    "spag": "Classic Spaghetti Bolognese",
    "spaghetti bolognese": "Classic Spaghetti Bolognese",
    "bolognese": "Classic Spaghetti Bolognese",
    "carbonara": "Creamy Carbonara",
    "creamy carbonara": "Creamy Carbonara",
    "seafood fettuccine": "Seafood Marinara Fettuccine",
    "seafood pasta": "Seafood Marinara Fettuccine",
    "marinara fettuccine": "Seafood Marinara Fettuccine",
    "marinara": "Seafood Marinara Fettuccine",

    # Sides
    "french fries": "Golden French Fries",
    "fries": "Golden French Fries",
    "golden fries": "Golden French Fries",
    "cheese fries": "Loaded Cheese Fries",
    "loaded fries": "Loaded Cheese Fries",
    "onion rings": "Crispy Onion Rings",
    "rings": "Crispy Onion Rings",
    "caesar salad": "Garden Fresh Caesar Salad",
    "salad": "Garden Fresh Caesar Salad",
    "mozzarella sticks": "Crispy Mozzarella Sticks",
    "cheese sticks": "Crispy Mozzarella Sticks",

    # Beverages
    "brewed coffee": "Classic Brewed Coffee",
    "coffee": "Classic Brewed Coffee",
    "classic coffee": "Classic Brewed Coffee",
    "hot coffee": "Classic Brewed Coffee",
    "black coffee": "Classic Brewed Coffee",
    "caramel macchiato": "Iced Caramel Macchiato",
    "macchiato": "Iced Caramel Macchiato",
    "iced coffee": "Iced Caramel Macchiato",
    "calamansi tea": "Fresh Calamansi Iced Tea",
    "calamansi iced tea": "Fresh Calamansi Iced Tea",
    "iced tea": "Fresh Calamansi Iced Tea",
    "tea": "Fresh Calamansi Iced Tea",
    "mango smoothie": "Mango Passionfruit Smoothie",
    "passionfruit smoothie": "Mango Passionfruit Smoothie",
    "smoothie": "Mango Passionfruit Smoothie",
    "avocado smoothie": "Avocado Cream Cheese Smoothie",

    # Desserts
    "lava cake": "Molten Lava Chocolate Cake",
    "molten lava cake": "Molten Lava Chocolate Cake",
    "chocolate cake": "Molten Lava Chocolate Cake",
    "cake": "Molten Lava Chocolate Cake",
    "cheesecake": "Classic New York Cheesecake",
    "new york cheesecake": "Classic New York Cheesecake",
    "ny cheesecake": "Classic New York Cheesecake",
    "matcha tiramisu": "Matcha Green Tea Tiramisu",
    "tiramisu": "Matcha Green Tea Tiramisu",

    # Combos
    "champion combo": "Perpetual Champion Combo",
    "pasta combo": "Pasta & Sweet Treat Combo",
    "chef duo": "Chef Ezekiel's Special Duo",
    "duo combo": "Chef Ezekiel's Special Duo",
    "study fuel": "Late Night Study Fuel Combo",
    "late night combo": "Late Night Study Fuel Combo"
}


def _find_menu_item(item_query: str, conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    """Helper to locate a menu item by exact name, alias dictionary, or substring matching."""
    cursor = conn.cursor()
    clean_q = item_query.strip().lower()

    # 1. Alias / Synonym direct lookup
    if clean_q in MENU_ITEM_SYNONYMS:
        canonical_name = MENU_ITEM_SYNONYMS[clean_q]
        cursor.execute("SELECT * FROM menu_items WHERE LOWER(name) = LOWER(?)", (canonical_name,))
        row = cursor.fetchone()
        if row:
            return row

    # 1b. Check if any synonym matches within clean_q
    for syn_key, can_name in sorted(MENU_ITEM_SYNONYMS.items(), key=lambda x: len(x[0]), reverse=True):
        pattern = r'' + re.escape(syn_key) + r''
        if re.search(pattern, clean_q) or syn_key in clean_q:
            cursor.execute("SELECT * FROM menu_items WHERE LOWER(name) = LOWER(?)", (can_name,))
            row = cursor.fetchone()
            if row:
                return row

    # 2. Exact match (case insensitive)
    cursor.execute("SELECT * FROM menu_items WHERE LOWER(name) = LOWER(?)", (item_query.strip(),))
    row = cursor.fetchone()
    if row:
        return row

    # 3. Substring match
    cursor.execute("SELECT * FROM menu_items WHERE LOWER(name) LIKE LOWER(?) ORDER BY LENGTH(name) ASC LIMIT 1", (f"%{item_query.strip()}%",))
    row = cursor.fetchone()
    if row:
        return row

    # 4. Reverse substring
    cursor.execute("SELECT * FROM menu_items")
    for item in cursor.fetchall():
        if item["name"].lower() in clean_q:
            return item

    return None

# =====================================================================
# Professor-Specified Tool Functions (bound directly to local LLM)
# =====================================================================

def get_menu_by_category(category: Optional[str] = None, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Retrieves menu items filtered by category.
    If category is None, empty, or 'all', returns the full bistro menu grouped by category.
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        if not category or category.strip().lower() in ["all", "everything", "menu"]:
            cursor.execute("SELECT id, name, category, price, stock_qty, allergens, description FROM menu_items ORDER BY category, name")
        else:
            cursor.execute(
                "SELECT id, name, category, price, stock_qty, allergens, description FROM menu_items WHERE LOWER(category) = LOWER(?) OR LOWER(category) LIKE LOWER(?) ORDER BY name",
                (category.strip(), f"%{category.strip()}%"),
            )
        rows = cursor.fetchall()
        items = [
            {
                "id": r["id"],
                "name": r["name"],
                "category": r["category"],
                "price": r["price"],
                "stock_qty": r["stock_qty"],
                "in_stock": r["stock_qty"] > 0,
                "allergens": r["allergens"],
                "description": r["description"],
            }
            for r in rows
        ]
        return {
            "status": "success",
            "category_queried": category or "all",
            "item_count": len(items),
            "items": items,
        }


def check_item_allergen(item_name: str, allergen: str, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Checks if a menu item contains a specific allergen (e.g., dairy, gluten, nuts, egg, pork, shellfish).
    Handles common synonyms such as lactose -> dairy, milk -> dairy, wheat -> gluten.
    """
    with get_db_connection(db_path) as conn:
        row = _find_menu_item(item_name, conn)
        if not row:
            return {
                "status": "not_found",
                "message": f"Menu item '{item_name}' was not found in Perpetual Bistro catalog.",
                "contains_allergen": False,
                "all_item_allergens": [],
            }

        allergens_str = (row["allergens"] or "").lower()
        query_allergen = allergen.strip().lower()

        # Map common dietary terms & ingredient synonyms
        allergen_map = {
            "lactose": "dairy",
            "milk": "dairy",
            "cheese": "dairy",
            "cream": "dairy",
            "butter": "dairy",
            "wheat": "gluten",
            "flour": "gluten",
            "bun": "gluten",
            "peanut": "nuts",
            "peanuts": "nuts",
            "cashew": "nuts",
            "almond": "nuts",
            "bacon": "pork",
            "ham": "pork",
            "prawn": "shellfish",
            "shrimp": "shellfish",
            "mussel": "shellfish",
            "squid": "shellfish",
        }
        effective_allergen = allergen_map.get(query_allergen, query_allergen)
        contains = (effective_allergen in allergens_str) or (query_allergen in allergens_str)

        all_allergens = [
            a.strip() for a in (row["allergens"] or "").split(",")
            if a.strip() and a.strip().lower() != "none"
        ]

        # Dietary customization suggestions
        customization_tips = []
        if contains:
            if effective_allergen == "dairy":
                if "Burger" in row["name"] or "Sandwich" in row["name"]:
                    customization_tips.append("Ask for 'No Cheese' or 'No Sauce' to eliminate dairy.")
                elif "Coffee" in row["name"] or "Macchiato" in row["name"]:
                    customization_tips.append("Can be served black as Classic Brewed Coffee without milk.")
                elif "Fries" in row["name"]:
                    customization_tips.append("Try Golden French Fries which are naturally 100% dairy-free.")
            elif effective_allergen == "gluten":
                customization_tips.append("Gluten-free dining: enjoy Golden French Fries or Calamansi Iced Tea.")

        # Find safe alternatives in same or different categories
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, price, category FROM menu_items WHERE stock_qty > 0 AND LOWER(allergens) NOT LIKE ? LIMIT 3",
            (f"%{effective_allergen}%",)
        )
        safe_alts = [dict(r) for r in cursor.fetchall()]

        return {
            "status": "success",
            "item_name": row["name"],
            "allergen_queried": allergen,
            "effective_allergen": effective_allergen,
            "declared_allergens": row["allergens"],
            "all_item_allergens": all_allergens,
            "contains_allergen": contains,
            "customization_tips": customization_tips,
            "safe_alternatives": safe_alts,
            "warning": (
                f"Caution: {row['name']} CONTAINS {effective_allergen.upper()} ({row['allergens']})."
                if contains
                else f"Safe: {row['name']} does NOT list {allergen} in its recorded allergen profile ({row['allergens'] or 'None'})."
            ),
        }


def check_availability(item_name: str, qty: int = 1, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Verifies real-time stock availability for a given menu item and quantity.
    """
    with get_db_connection(db_path) as conn:
        row = _find_menu_item(item_name, conn)
        if not row:
            return {
                "status": "not_found",
                "message": f"Menu item '{item_name}' does not exist in the bistro menu.",
                "available": False,
            }

        stock = row["stock_qty"]
        available = stock >= qty
        return {
            "status": "success",
            "item_name": row["name"],
            "requested_qty": qty,
            "current_stock": stock,
            "available": available,
            "message": (
                f"{row['name']} is available ({stock} in stock)."
                if available
                else f"Sorry, {row['name']} is OUT OF STOCK (available: {stock}, requested: {qty})."
            ),
        }


def add_item_to_order(session_id: str, item_name: str, qty: int = 1, instructions: str = "", db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Adds a menu item to the table's active order cart with optional customizations.
    Defensively checks stock availability before mutating order state.
    """
    if qty <= 0:
        return {"status": "error", "message": "Quantity must be greater than zero."}

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        item = _find_menu_item(item_name, conn)
        if not item:
            return {
                "status": "not_found",
                "message": f"Item '{item_name}' was not recognized. Please check the bistro menu.",
            }

        # Verify stock level
        if item["stock_qty"] < qty:
            # Out of stock or insufficient stock: recommend alternative from same category
            cursor.execute(
                "SELECT name, price, stock_qty FROM menu_items WHERE category = ? AND id != ? AND stock_qty > 0 LIMIT 2",
                (item["category"], item["id"]),
            )
            alternatives = [dict(r) for r in cursor.fetchall()]
            alt_names = ", ".join([a["name"] for a in alternatives]) if alternatives else "other menu categories"
            return {
                "status": "out_of_stock",
                "item_name": item["name"],
                "stock_available": item["stock_qty"],
                "requested_qty": qty,
                "message": f"Unable to add {item['name']}: item is currently out of stock ({item['stock_qty']} available).",
                "recommended_alternatives": alternatives,
                "suggestion": f"Would you like to try our {alt_names} instead?",
            }

        # Ensure session exists in table_sessions (self-healing for web kiosk)
        cursor.execute("SELECT session_id FROM table_sessions WHERE session_id = ?", (session_id,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT OR REPLACE INTO table_sessions (session_id, table_no, status, updated_at) VALUES (?, 1, 'STATE_TAKING_ORDER', CURRENT_TIMESTAMP)",
                (session_id,),
            )

        # Check if identical item with identical instructions already exists in this session
        cursor.execute(
            """
            SELECT id, quantity FROM order_line_items
            WHERE session_id = ? AND item_id = ? AND LOWER(special_instructions) = LOWER(?)
            """,
            (session_id, item["id"], instructions.strip()),
        )
        existing_line = cursor.fetchone()

        if existing_line:
            new_qty = existing_line["quantity"] + qty
            if item["stock_qty"] < new_qty:
                return {
                    "status": "stock_limit_reached",
                    "message": f"Cannot add {qty} more of {item['name']}. Current cart has {existing_line['quantity']} and total inventory is {item['stock_qty']}.",
                }
            cursor.execute(
                "UPDATE order_line_items SET quantity = ? WHERE id = ?",
                (new_qty, existing_line["id"]),
            )
        else:
            cursor.execute(
                """
                INSERT INTO order_line_items (session_id, item_id, quantity, special_instructions, unit_price)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, item["id"], qty, instructions.strip(), item["price"]),
            )

        # Update session status to TAKING_ORDER if still in GREETING
        cursor.execute(
            "UPDATE table_sessions SET status = 'STATE_TAKING_ORDER', updated_at = CURRENT_TIMESTAMP WHERE session_id = ? AND status = 'STATE_GREETING'",
            (session_id,),
        )
        conn.commit()

        # Fetch updated cart total
        current_order = view_current_order(session_id, db_path=db_path)
        return {
            "status": "success",
            "message": f"Added {qty}x {item['name']}" + (f" with instructions: '{instructions}'" if instructions else "") + " to your tab.",
            "added_item": {
                "name": item["name"],
                "quantity": qty,
                "unit_price": item["price"],
                "special_instructions": instructions.strip(),
            },
            "new_order_subtotal": current_order["subtotal"],
            "new_order_total": current_order["grand_total"],
            "total_items_in_cart": current_order["item_count"],
        }


def clear_order(session_id: str, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Clears all line items from the customer's active order tab.
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM order_line_items WHERE session_id = ?", (session_id,))
        conn.commit()
        return {
            "status": "success",
            "message": "Your order tab has been cleared.",
            "total_items_in_cart": 0,
            "grand_total": 0.0,
        }


def remove_item_from_order(session_id: str, item_name: str, qty: Optional[int] = None, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Safely removes an item or line item from the active table order.
    If qty is specified and less than current quantity in cart, decrements quantity.
    Otherwise, removes the item completely from the order tab.
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        item = _find_menu_item(item_name, conn)
        if not item:
            return {"status": "not_found", "message": f"'{item_name}' is not a recognized menu item."}

        cursor.execute(
            "SELECT id, quantity FROM order_line_items WHERE session_id = ? AND item_id = ?",
            (session_id, item["id"]),
        )
        lines = cursor.fetchall()
        if not lines:
            return {
                "status": "not_in_cart",
                "message": f"'{item['name']}' is not currently in your order cart.",
            }

        total_current_qty = sum(l["quantity"] for l in lines)
        if qty is not None and 0 < qty < total_current_qty:
            rem_to_deduct = qty
            for l in lines:
                if rem_to_deduct <= 0:
                    break
                if l["quantity"] <= rem_to_deduct:
                    cursor.execute("DELETE FROM order_line_items WHERE id = ?", (l["id"],))
                    rem_to_deduct -= l["quantity"]
                else:
                    new_q = l["quantity"] - rem_to_deduct
                    cursor.execute("UPDATE order_line_items SET quantity = ? WHERE id = ?", (new_q, l["id"]))
                    rem_to_deduct = 0
            conn.commit()
            msg = f"Removed {qty}x {item['name']} from your order tab."
        else:
            cursor.execute(
                "DELETE FROM order_line_items WHERE session_id = ? AND item_id = ?",
                (session_id, item["id"]),
            )
            conn.commit()
            msg = f"Removed all instances of {item['name']} from your order."

        updated_order = view_current_order(session_id, db_path=db_path)
        return {
            "status": "success",
            "message": msg,
            "removed_item": item["name"],
            "new_order_total": updated_order["grand_total"],
            "remaining_items": updated_order["item_count"],
            "cart": updated_order,
        }



def remove_order_by_ordinal(session_id: str, ordinal: int, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Removes an item from the active order tab based on its 1-based chronological addition sequence.
    ordinal=1 removes the 1st added order, ordinal=2 removes 2nd, etc.
    ordinal=-1 removes the last added order.
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT oli.id, oli.quantity, oli.special_instructions, mi.name, mi.price
            FROM order_line_items oli
            JOIN menu_items mi ON oli.item_id = mi.id
            WHERE oli.session_id = ?
            ORDER BY oli.id ASC
            """,
            (session_id,)
        )
        lines = cursor.fetchall()
        if not lines:
            return {
                "status": "empty_cart",
                "message": "Your order tab is currently empty. There are no orders to remove.",
                "remaining_items": 0,
                "new_order_total": 0.0
            }

        total_lines = len(lines)
        if ordinal == -1:
            target_idx = total_lines - 1
            display_pos = f"last (order #{total_lines})"
        elif 1 <= ordinal <= total_lines:
            target_idx = ordinal - 1
            display_pos = f"order #{ordinal}"
        else:
            return {
                "status": "invalid_ordinal",
                "message": f"Order #{ordinal} does not exist. You currently have {total_lines} item(s) on your tab.",
                "total_items": total_lines
            }

        target_line = lines[target_idx]
        target_id = target_line["id"]
        target_name = target_line["name"]
        target_qty = target_line["quantity"]

        cursor.execute("DELETE FROM order_line_items WHERE id = ?", (target_id,))
        conn.commit()

        updated_order = view_current_order(session_id, db_path=db_path)
        return {
            "status": "success",
            "message": f"Removed {display_pos} ({target_qty}x {target_name}) from your order tab.",
            "removed_item": target_name,
            "removed_qty": target_qty,
            "ordinal": ordinal,
            "new_order_total": updated_order["grand_total"],
            "remaining_items": updated_order["item_count"],
            "cart": updated_order
        }


def replace_item_in_order(
    session_id: str,
    old_item_name: str,
    new_item_name: str,
    qty: Optional[int] = None,
    instructions: str = "",
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    """
    Replaces an item in the active order cart with another item from the menu.
    Validates that the old item is currently in the cart and the replacement item is in stock.
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        old_item = _find_menu_item(old_item_name, conn)
        if not old_item:
            return {"status": "not_found", "message": f"Original item '{old_item_name}' was not recognized in our menu."}

        cursor.execute(
            "SELECT id, quantity FROM order_line_items WHERE session_id = ? AND item_id = ?",
            (session_id, old_item["id"]),
        )
        lines = cursor.fetchall()
        if not lines:
            return {
                "status": "not_in_cart",
                "message": f"'{old_item['name']}' is not currently in your order tab to replace.",
            }

        total_old_qty = sum(l["quantity"] for l in lines)
        replace_qty = qty if (qty is not None and qty > 0) else total_old_qty

        new_item = _find_menu_item(new_item_name, conn)
        if not new_item:
            return {"status": "not_found", "message": f"Replacement item '{new_item_name}' was not recognized in our menu."}

        if new_item["stock_qty"] < replace_qty:
            cursor.execute(
                "SELECT name, price FROM menu_items WHERE category = ? AND id != ? AND stock_qty > 0 LIMIT 2",
                (new_item["category"], new_item["id"])
            )
            alts = [f"{r['name']} (₱{r['price']:.2f})" for r in cursor.fetchall()]
            alt_str = ", ".join(alts) if alts else "other in-stock items"
            return {
                "status": "out_of_stock",
                "message": f"Cannot replace with {new_item['name']} because it is currently out of stock ({new_item['stock_qty']} available). Would you like to try {alt_str} instead?",
                "item_name": new_item["name"],
                "stock_available": new_item["stock_qty"]
            }

        # Remove or decrement old item
        if replace_qty < total_old_qty:
            rem_to_deduct = replace_qty
            for l in lines:
                if rem_to_deduct <= 0:
                    break
                if l["quantity"] <= rem_to_deduct:
                    cursor.execute("DELETE FROM order_line_items WHERE id = ?", (l["id"],))
                    rem_to_deduct -= l["quantity"]
                else:
                    new_q = l["quantity"] - rem_to_deduct
                    cursor.execute("UPDATE order_line_items SET quantity = ? WHERE id = ?", (new_q, l["id"]))
                    rem_to_deduct = 0
        else:
            cursor.execute(
                "DELETE FROM order_line_items WHERE session_id = ? AND item_id = ?",
                (session_id, old_item["id"]),
            )

        # Add replacement item
        cursor.execute(
            """
            SELECT id, quantity FROM order_line_items
            WHERE session_id = ? AND item_id = ? AND LOWER(special_instructions) = LOWER(?)
            """,
            (session_id, new_item["id"], instructions.strip()),
        )
        existing_new = cursor.fetchone()
        if existing_new:
            cursor.execute(
                "UPDATE order_line_items SET quantity = quantity + ? WHERE id = ?",
                (replace_qty, existing_new["id"]),
            )
        else:
            cursor.execute(
                """
                INSERT INTO order_line_items (session_id, item_id, quantity, special_instructions, unit_price)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, new_item["id"], replace_qty, instructions.strip(), new_item["price"]),
            )

        conn.commit()

        updated_order = view_current_order(session_id, db_path=db_path)
        inst_str = f" with note: '{instructions}'" if instructions else ""
        return {
            "status": "success",
            "message": f"Replaced {replace_qty}x {old_item['name']} with {replace_qty}x {new_item['name']}{inst_str} in your order tab.",
            "old_item": old_item["name"],
            "new_item": new_item["name"],
            "quantity": replace_qty,
            "new_order_total": updated_order["grand_total"],
            "cart": updated_order,
        }


def update_item_quantity(session_id: str, item_name: str, qty: int, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Updates the quantity of an item in the active order. If qty <= 0, deletes the item.
    """
    if qty <= 0:
        return remove_item_from_order(session_id, item_name, db_path=db_path)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        item = _find_menu_item(item_name, conn)
        if not item:
            return {"status": "not_found", "message": f"'{item_name}' was not recognized."}

        if item["stock_qty"] < qty:
            return {
                "status": "insufficient_stock",
                "message": f"Cannot set {item['name']} to {qty}: only {item['stock_qty']} are in stock.",
            }

        cursor.execute(
            "SELECT id FROM order_line_items WHERE session_id = ? AND item_id = ? LIMIT 1",
            (session_id, item["id"]),
        )
        line = cursor.fetchone()
        if not line:
            return {"status": "not_in_cart", "message": f"'{item['name']}' is not in your current order."}

        cursor.execute(
            "UPDATE order_line_items SET quantity = ? WHERE id = ?",
            (qty, line["id"]),
        )
        conn.commit()

        updated_order = view_current_order(session_id, db_path=db_path)
        return {
            "status": "success",
            "message": f"Updated {item['name']} quantity to {qty}.",
            "new_order_total": updated_order["grand_total"],
        }


def view_current_order(session_id: str, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Calculates and returns the complete itemized tab for the table session,
    including unit prices, special instruction badges, 12% VAT, and total.
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT table_no, status FROM table_sessions WHERE session_id = ?", (session_id,))
        session_row = cursor.fetchone()
        table_no = session_row["table_no"] if session_row else "Unknown"
        status = session_row["status"] if session_row else "STATE_GREETING"

        cursor.execute(
            """
            SELECT oli.id, oli.quantity, oli.special_instructions, oli.unit_price,
                   mi.name, mi.category, mi.allergens
            FROM order_line_items oli
            JOIN menu_items mi ON oli.item_id = mi.id
            WHERE oli.session_id = ?
            ORDER BY oli.id ASC
            """,
            (session_id,),
        )
        lines = cursor.fetchall()

        items = []
        subtotal = 0.0
        total_qty = 0

        for idx, line in enumerate(lines, 1):
            line_total = line["quantity"] * line["unit_price"]
            subtotal += line_total
            total_qty += line["quantity"]
            items.append({
                "order_number": idx,
                "line_id": line["id"],
                "name": line["name"],
                "category": line["category"],
                "quantity": line["quantity"],
                "unit_price": line["unit_price"],
                "line_total": round(line_total, 2),
                "special_instructions": line["special_instructions"] or "",
                "allergens": line["allergens"],
            })

        # Calculations: Subtotal, 12% Government VAT included/standard, Grand Total
        vat_amount = round(subtotal * 0.12, 2)
        grand_total = round(subtotal, 2)  # Standard campus dining retail includes tax in menu prices

        return {
            "status": "success",
            "session_id": session_id,
            "table_no": table_no,
            "fsm_state": status,
            "item_count": total_qty,
            "line_items": items,
            "subtotal": round(subtotal, 2),
            "vat_12_pct_breakdown": vat_amount,
            "grand_total": grand_total,
            "currency": "Philippine Pesos (pesos, ₱)",
        }


def confirm_order_and_deduct_stock(session_id: str, discount_type: str = "regular", db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Transactional order confirmation:
    1. Validates all line items against current inventory.
    2. Atomically decrements menu_items stock_qty in SQLite.
    3. Sets table_sessions status to 'STATE_CONFIRMED'.
    4. Generates an immutable digital checkout receipt.
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN TRANSACTION")

            cursor.execute("SELECT table_no, status FROM table_sessions WHERE session_id = ?", (session_id,))
            session = cursor.fetchone()
            if not session:
                # Self-healing: Check if order items exist for this session in order_line_items
                cursor.execute("SELECT COUNT(*) as cnt FROM order_line_items WHERE session_id = ?", (session_id,))
                cnt_row = cursor.fetchone()
                if cnt_row and cnt_row["cnt"] > 0:
                    cursor.execute(
                        "INSERT OR REPLACE INTO table_sessions (session_id, table_no, status, updated_at) VALUES (?, 1, 'STATE_REVIEW', CURRENT_TIMESTAMP)",
                        (session_id,),
                    )
                    cursor.execute("SELECT table_no, status FROM table_sessions WHERE session_id = ?", (session_id,))
                    session = cursor.fetchone()
                else:
                    conn.rollback()
                    return {"status": "error", "message": f"Session {session_id} not found."}

            # Retrieve order line items
            cursor.execute(
                """
                SELECT oli.item_id, oli.quantity, oli.special_instructions, oli.unit_price,
                       mi.name, mi.stock_qty
                FROM order_line_items oli
                JOIN menu_items mi ON oli.item_id = mi.id
                WHERE oli.session_id = ?
                """,
                (session_id,),
            )
            items = cursor.fetchall()
            if not items:
                conn.rollback()
                return {"status": "error", "message": "Cannot confirm empty order. Cart has no items."}

            # Check stock for all items
            for it in items:
                if it["stock_qty"] < it["quantity"]:
                    conn.rollback()
                    return {
                        "status": "stock_error",
                        "message": f"Transactional failure: '{it['name']}' only has {it['stock_qty']} in stock, but {it['quantity']} was ordered.",
                    }

            # Atomically decrement stock
            for it in items:
                cursor.execute(
                    "UPDATE menu_items SET stock_qty = stock_qty - ? WHERE id = ?",
                    (it["quantity"], it["item_id"]),
                )

            # Update session state to STATE_CONFIRMED
            cursor.execute(
                "UPDATE table_sessions SET status = 'STATE_CONFIRMED', updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                (session_id,),
            )

            conn.commit()

            # Compile final receipt with discount calculation
            tab = view_current_order(session_id, db_path=db_path)
            subtotal = tab["subtotal"]

            # Student, Senior, PWD 20% statutory discount; regular is as-is
            disc_clean = (discount_type or "regular").lower().strip()
            if "student" in disc_clean:
                discount_rate = 0.20
                discount_label = "Student Discount (20%)"
            elif "senior" in disc_clean:
                discount_rate = 0.20
                discount_label = "Senior Citizen Discount (20%)"
            elif "pwd" in disc_clean or "disability" in disc_clean:
                discount_rate = 0.20
                discount_label = "PWD Discount (20%)"
            else:
                discount_rate = 0.0
                discount_label = "Regular (No Discount)"

            discount_amount = round(subtotal * discount_rate, 2)
            grand_total = round(subtotal - discount_amount, 2)

            receipt_id = f"PB-{session['table_no']}-{str(uuid.uuid4())[:6].upper()}"

            # Automatically dispatch to Kitchen Display System (KDS)
            create_kitchen_ticket(
                table_no=session["table_no"],
                session_id=session_id,
                items=tab["line_items"],
                grand_total=tab["grand_total"],
                payment_method="CASH",
                payment_ref="COUNTER",
                ticket_id=receipt_id,
                db_path=db_path
            )

            return {
                "status": "success",
                "receipt_id": receipt_id,
                "table_no": session["table_no"],
                "session_id": session_id,
                "fsm_state": "STATE_CONFIRMED",
                "message": f"Order successfully finalized and confirmed! Kitchen ticket dispatched. {discount_label}: -₱{discount_amount:.2f}" if discount_amount > 0 else "Order successfully finalized and confirmed! Kitchen ticket dispatched.",
                "itemized_receipt": tab["line_items"],
                "subtotal": subtotal,
                "discount_type": discount_label,
                "discount_rate": discount_rate,
                "discount_amount": discount_amount,
                "vat_included": tab["vat_12_pct_breakdown"],
                "grand_total": grand_total,
                "currency": "Philippine Pesos (pesos, ₱)",
            }
        except Exception as e:
            conn.rollback()
            return {"status": "error", "message": f"Database transaction aborted: {str(e)}"}


# =====================================================================
# KITCHEN DISPLAY SYSTEM (KDS) & INVENTORY ANALYTICS EXTENSIONS
# =====================================================================

def create_kitchen_ticket(
    table_no: int,
    session_id: str,
    items: List[Dict[str, Any]],
    grand_total: float,
    payment_method: str = "CASH",
    payment_ref: str = "",
    ticket_id: Optional[str] = None,
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    """Inserts an active kitchen ticket into the kitchen fulfillment queue."""
    t_id = ticket_id or f"PB-{table_no}-{str(uuid.uuid4())[:6].upper()}"
    items_serialized = json.dumps(items)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO kitchen_tickets 
            (ticket_id, table_no, session_id, items_json, subtotal, payment_method, payment_ref, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'PREPARING', CURRENT_TIMESTAMP)
            """,
            (t_id, table_no, session_id, items_serialized, grand_total, payment_method, payment_ref),
        )
        conn.commit()
    return {
        "status": "success",
        "ticket_id": t_id,
        "table_no": table_no,
        "payment_method": payment_method,
        "payment_ref": payment_ref,
        "kitchen_status": "PREPARING"
    }


def get_kitchen_tickets(status_filter: Optional[str] = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Retrieves kitchen tickets with parsed item arrays."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        if status_filter and status_filter.upper() != "ALL":
            cursor.execute(
                "SELECT * FROM kitchen_tickets WHERE status = ? ORDER BY id DESC",
                (status_filter.upper(),)
            )
        else:
            cursor.execute("SELECT * FROM kitchen_tickets ORDER BY id DESC")
        rows = cursor.fetchall()

    results = []
    for r in rows:
        ticket = dict(r)
        try:
            ticket["items"] = json.loads(ticket.get("items_json") or "[]")
        except Exception:
            ticket["items"] = []
        results.append(ticket)
    return results


def update_kitchen_ticket_status(ticket_id: str, new_status: str, db_path: str = DB_PATH) -> bool:
    """Updates the status of a kitchen ticket ('PREPARING', 'READY', 'SERVED')."""
    valid = ["PREPARING", "READY", "SERVED"]
    clean_status = new_status.upper().strip()
    if clean_status not in valid:
        return False
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE kitchen_tickets SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE ticket_id = ?",
            (clean_status, ticket_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_analytics_summary(db_path: str = DB_PATH) -> Dict[str, Any]:
    """Aggregates business intelligence metrics: total sales, order volume, and inventory health."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # 1. Total revenue & count from kitchen tickets
        cursor.execute("SELECT COUNT(*) as count, COALESCE(SUM(subtotal), 0) as total_rev FROM kitchen_tickets")
        sales_row = cursor.fetchone()
        total_orders = sales_row["count"] if sales_row else 0
        total_revenue = sales_row["total_rev"] if sales_row else 0.0

        # 2. Tickets by status
        cursor.execute("SELECT status, COUNT(*) as count FROM kitchen_tickets GROUP BY status")
        status_counts = {r["status"]: r["count"] for r in cursor.fetchall()}

        # 3. Inventory overview: low stock (<= 5)
        cursor.execute("SELECT name, category, price, stock_qty FROM menu_items ORDER BY stock_qty ASC")
        all_items = [dict(r) for r in cursor.fetchall()]
        low_stock_items = [item for item in all_items if item["stock_qty"] <= 5]

        # 4. Categories sales count
        cursor.execute("SELECT category, COUNT(*) as item_count, AVG(price) as avg_price FROM menu_items GROUP BY category")
        categories_stat = [dict(r) for r in cursor.fetchall()]

    return {
        "status": "success",
        "total_revenue": round(total_revenue, 2),
        "total_orders": total_orders,
        "status_breakdown": status_counts,
        "low_stock_count": len(low_stock_items),
        "low_stock_items": low_stock_items,
        "all_inventory": all_items,
        "category_summary": categories_stat
    }


def restock_menu_item(item_name: str, qty_to_add: int = 10, db_path: str = DB_PATH) -> Dict[str, Any]:
    """Adds stock quantity to a specific menu item."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        item = _find_menu_item(item_name, conn)
        if not item:
            return {"status": "error", "message": f"Item '{item_name}' not found."}
        
        cursor.execute(
            "UPDATE menu_items SET stock_qty = stock_qty + ? WHERE id = ?",
            (qty_to_add, item["id"])
        )
        conn.commit()
        cursor.execute("SELECT stock_qty FROM menu_items WHERE id = ?", (item["id"],))
        updated_stock = cursor.fetchone()["stock_qty"]
    return {
        "status": "success",
        "item_name": item["name"],
        "added_qty": qty_to_add,
        "new_stock": updated_stock,
        "message": f"Successfully added {qty_to_add} stock to {item['name']}. Current stock: {updated_stock}."
    }


def restock_all_items(target_min_qty: int = 20, db_path: str = DB_PATH) -> Dict[str, Any]:
    """Restocks any item below target_min_qty up to target_min_qty."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE menu_items SET stock_qty = ? WHERE stock_qty < ?",
            (target_min_qty, target_min_qty)
        )
        affected = cursor.rowcount
        conn.commit()
    return {
        "status": "success",
        "affected_items": affected,
        "new_minimum": target_min_qty,
        "message": f"Restocked {affected} items to at least {target_min_qty} units."
    }
