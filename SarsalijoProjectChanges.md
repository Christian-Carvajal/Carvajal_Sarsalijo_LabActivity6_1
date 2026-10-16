# John Miko P. Sarsalijo - Project Contributions & Change Log
## Lab Activity 6.1: Stateful Restaurant Order Agent & Dynamic Tool Calling Engine
**Course:** CS FSM & AI Workflows | **Term:** 1st Trimester, Finals AY 2026–2027  
**Institution:** University of Perpetual Help System DALTA — Las Piñas Campus  
**Authors:** Christian Ezekiel L. Carvajal & John Miko P. Sarsalijo  
**Instructor:** Prof. Rob Malitao  

---

### [2026-10-16 14:00] - Major UI/UX Overhaul: Ultra-Aesthetic Kiosk & Multi-View Architecture
- **Role:** John Miko P. Sarsalijo (Driver / Frontend Lead) / AI Assistant (Navigator)
- **Target Files:** [`web_dashboard.py`](web_dashboard.py)
- **Category:** UI Polish & Multi-View Navigation Architecture
- **Description:**
  1. **Multi-View Navigation Switcher (`kiosk-nav-bar`):**
     - Implemented 3 interactive layout views accessible via top pill buttons:
       - **`🍽️ Visual Menu Catalog`**: Dedicated grid of appetizing food cards with live filtering.
       - **`💬 AI Waiter Dialogue`**: Conversational chat stream with BistroBot, speech visualization, and quick prompts.
       - **`⚡ Split Kiosk View`**: Dual-pane simultaneous layout showing both the visual menu and AI waiter side-by-side.
  2. **Visual Menu Catalog Grid & Live Filtering:**
     - Created a responsive grid displaying all 17 Perpetual Bistro dishes with category icons, stock counts, and prices.
     - Built an instant live search input (`🔍 Search menu items, e.g. Truffle, Burger, Calamansi...`) filtering dishes in real time.
     - Added dietary & allergen quick filter chips (`🥛 Dairy-Free`, `🌾 Gluten-Free`, `🥜 Nut-Free`, `🌿 In-Stock Only`).
     - Added category tabs (`🌟 All Specials`, `🍔 Burgers`, `🍝 Pastas`, `🍟 Sides`, `🥤 Beverages`, `🍨 Desserts`).
     - Added direct `+ Quick Add` buttons and `⚙️ Customize` buttons on every dish card.
     - Visualized out-of-stock items (such as `Crispy Buffalo Chicken Tenders`) with dimmed cards and disabled buttons to fulfill edge-case testing requirements.
  3. **Interactive Dish Customization Modal:**
     - Built a popup modal allowing guests to customize dishes before adding to order:
       - Quantity adjuster (`-` / `+`).
       - Popular modification toggle chips (`🧅 No Onions`, `🧀 Extra Cheese`, `🌶️ Extra Spicy`, `🧊 Less Ice`, `🥣 Sauce on Side`, `🍚 Extra Garlic Rice`).
       - Custom kitchen instructions text input for allergy notes or specific preferences.
       - Real-time subtotal calculation and direct SQLite cart synchronization.
  4. **Interactive Table Selector Dropdown:**
     - Added a table selection dropdown in the header allowing staff/customers to switch between Table #1 and Table #8 without losing context.
     - Added backend API endpoint `/api/table/switch`.
  5. **Direct Cart Addition API (`/api/cart/add`):**
     - Built FastAPI endpoint allowing visual menu cards to directly invoke `add_item_to_order`, updating SQLite and advancing the FSM to `STATE_TAKING_ORDER`.
  6. **Interactive Toast Notifications:**
     - Created floating animated toast feedback banner in the bottom-right corner confirming actions (e.g., `"✨ Added 1x Perpetual Classic Burger to your tab!"`).
  7. **Visual Polish & Ergonomics:**
     - Refined contrast ratios, glassmorphism (`backdrop-filter: blur(12px)`), warm obsidian tones, and signature UPHSD Maroon (`#7B1113`) & Academic Gold (`#D4AF37`).
     - Added live digital clock in the top institutional utility ribbon.
- **Rationale:** Directly fulfills the prompt's demand for an aesthetic, super organized, clean, and easily navigable interface. Fulfills Option 1 tablet kiosk recommendations from Section 6 of the onboarding guide.
- **Verification:** Tested with FastAPI `TestClient` across all endpoints (`GET /`, `GET /api/session`, `GET /api/menu`, `POST /api/cart/add`, `POST /api/table/switch`, `POST /api/cart/update`). All automated tests passed with 100% success.
