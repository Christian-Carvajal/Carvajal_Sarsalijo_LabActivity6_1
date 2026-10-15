-- Perpetual Bistro Database Schema Initialization Script
-- Subject: BSCS 3112 - Artificial Intelligence Lab (Lesson 6)
-- Database: restaurant.db

-- 1. Drop existing tables if recreating
DROP TABLE IF EXISTS order_line_items;
DROP TABLE IF EXISTS table_sessions;
DROP TABLE IF EXISTS menu_items;

-- 2. Menu Items Table
-- Stores real-time campus bistro dining offerings, stock availability, and allergen profiles.
CREATE TABLE menu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    price REAL NOT NULL,
    stock_qty INTEGER NOT NULL DEFAULT 0,
    allergens TEXT DEFAULT 'None',
    description TEXT DEFAULT ''
);

-- 3. Table Sessions Table
-- Tracks conversational state machine lifecycle and table identification.
CREATE TABLE table_sessions (
    session_id TEXT PRIMARY KEY,
    table_no INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'STATE_GREETING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Order Line Items Table
-- Stores active cart items bound to a specific table session, including customizations.
CREATE TABLE order_line_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    item_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    special_instructions TEXT DEFAULT '',
    unit_price REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES table_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES menu_items(id)
);

-- 5. Seed Data: Perpetual Bistro Menu Offerings
-- Includes distinct categories, ingredients, allergens, and an out-of-stock item for edge testing.
INSERT INTO menu_items (name, category, price, stock_qty, allergens, description) VALUES
-- Burgers & Sandwiches
('Perpetual Classic Burger', 'Burgers', 150.00, 25, 'Gluten, Dairy', 'Juicy beef patty with cheddar cheese, crisp lettuce, tomato, and house bistro sauce.'),
('Bacon Mushroom Melt Burger', 'Burgers', 185.00, 15, 'Gluten, Dairy, Pork', 'Angus beef patty with smoked bacon, sautéed mushrooms, and melted Swiss cheese.'),
('Grilled Chicken Pesto Sandwich', 'Burgers', 165.00, 20, 'Gluten, Dairy, Nuts', 'Tender herb chicken breast, fragrant basil pesto, and fresh mozzarella on ciabatta.'),
('Crispy Buffalo Chicken Tenders', 'Burgers', 140.00, 0, 'Gluten, Dairy', 'Out-of-stock test item: spicy glazed chicken strips with ranch dipping sauce.'),

-- Pastas & Mains
('Truffle Mushroom Pasta', 'Pastas', 210.00, 14, 'Gluten, Dairy', 'Fettuccine tossed in a rich black truffle cream sauce with sautéed mushrooms.'),
('Classic Spaghetti Bolognese', 'Pastas', 175.00, 18, 'Gluten, Dairy, Beef', 'Slow-simmered beef bolognese sauce over al dente spaghetti with parmesan.'),
('Creamy Carbonara', 'Pastas', 190.00, 16, 'Gluten, Dairy, Pork, Egg', 'Traditional egg yolk cream sauce with crispy smoked bacon and cracked black pepper.'),

-- Sides & Appetizers
('Golden French Fries', 'Sides', 75.00, 50, 'None', 'Crisp skin-on russet potatoes seasoned with fine sea salt.'),
('Loaded Cheese Fries', 'Sides', 110.00, 30, 'Dairy', 'Golden fries smothered in warm aged cheddar sauce and pickled jalapeño rings.'),
('Crispy Onion Rings', 'Sides', 85.00, 22, 'Gluten', 'Thick cut sweet onions in seasoned batter fried golden and crunchy.'),
('Garden Fresh Caesar Salad', 'Sides', 130.00, 15, 'Dairy, Egg, Fish', 'Crisp romaine lettuce, garlic croutons, parmesan flakes, and homemade Caesar dressing.'),

-- Beverages
('Iced Caramel Macchiato', 'Beverages', 95.00, 40, 'Dairy', 'Espresso layered with whole milk, vanilla syrup, and rich caramel drizzle.'),
('Classic Brewed Coffee', 'Beverages', 60.00, 60, 'None', 'Freshly brewed house blend arabica beans served black or with sugar.'),
('Fresh Calamansi Iced Tea', 'Beverages', 55.00, 50, 'None', 'Chilled house black tea infused with natural Philippine calamansi citrus juice.'),
('Mango Passionfruit Smoothie', 'Beverages', 105.00, 25, 'Dairy', 'Sweet ripe mango puree blended with yogurt and passionfruit nectar.'),

-- Desserts
('Molten Lava Chocolate Cake', 'Desserts', 125.00, 12, 'Gluten, Dairy, Egg', 'Decadent dark chocolate sponge cake with warm molten chocolate center.'),
('Classic New York Cheesecake', 'Desserts', 135.00, 10, 'Gluten, Dairy, Egg', 'Dense velvety cream cheese on buttery graham cracker crust with berry compote.');
