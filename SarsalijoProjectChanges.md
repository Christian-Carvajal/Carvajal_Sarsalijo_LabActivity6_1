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

### [2026-10-16 15:45] - Commercial Kiosk & Landing Page Transformation (Perpetual Maroon & Gold)
- **Role:** John Miko P. Sarsalijo (Driver / Fullstack Lead) / AI Assistant (Navigator)
- **Target Files:** [`templates/index.html`](templates/index.html), [`web_dashboard.py`](web_dashboard.py), [`fsm_agent.py`](fsm_agent.py)
- **Category:** Commercial Tablet Kiosk & Restaurant Landing Page UI Architecture + Automated Waiter Hardening
- **Description:**
  1. **Dual-Experience UI (Landing Page & Tablet Kiosk):**
     - **Landing Page (Inspired by Reference Image 2 - "The Kitchen"):**
       - Implemented an appetizing culinary landing page with a hero header ("CHECK OUT OUR MENU AND PLACE AN ORDER EASILY").
       - Built an interactive Bento Grid with high-res food photography:
         - Weekend Offer & Campus Specials featured tile with direct "Start Ordering →" call-to-action.
         - Table Reservation & Dining Status tile with active table indicator and instant table switcher (Tables 1-8).
         - Order Now photography hero banner.
         - Bottom feature tiles: Chef Specialties gallery, BistroBot AI Waiter card, and Campus Location & Dining Hours.
     - **3-Column Tablet Ordering Kiosk (Inspired by Reference Image 1 - "Pizzeria Italiano"):**
       - **Column 1 (Left Sidebar):** Quick search bar, category menu items with count badges and active Perpetual Maroon pill indicator, dietary filter chips (`Dairy-Free`, `Gluten-Free`, `Nut-Free`, `In-Stock Only`), and a Student Discount 10% perk box.
       - **Column 2 (Center Catalog):** "EARN REWARD POINTS FROM ALL ORDERS" promotional reward banner with 20% first order and 10% all orders badges, active category counter, view toggle (`Grid` / `Compact`), and responsive food card grid featuring all 17 Perpetual Bistro dishes with high-res imagery, allergen badges, price in ₱, and dual action buttons (`+ Add`, `⚙️ Customize`, `⚡ Order Now`).
       - **Column 3 (Right Order Tab):** Sticky tablet order panel ("MY ORDER") showing active table number, live FSM state badge, itemized list with quantity controls (`-` `qty` `+`), tax & subtotal breakdown, and prominent pulsing `CONFIRM & PLACE ORDER (₱XXX.XX)` checkout button.
  2. **Automated Waiter & Model Hardening (`fsm_agent.py`):**
     - Implemented dynamic model detection that prioritizes lightweight models (`qwen2.5:1.5b`) over memory-heavy models (`qwen3.5:4b`) to completely eliminate CUDA out-of-memory (`cudaMalloc failed`) errors on laptop GPUs with 4GB-6GB VRAM.
     - Added an automated fallback dialogue engine that deterministically parses orders, allergen questions, menu categories, recommendations, and checkout requests with 100% reliability even if Ollama times out or is offline.
     - Added a safety guard (`_ensure_critical_tool_execution`) ensuring that natural language order requests always execute real SQLite database tools.
  3. **Modular Architecture:**
     - Separated front-end presentation cleanly into [`templates/index.html`](templates/index.html) and simplified [`web_dashboard.py`](web_dashboard.py) to load the template dynamically, ensuring clean maintainability.
- **Verification:**
  - Automated API tests: Verified HTTP 200 on root endpoint (`GET /`), item retrieval (`GET /api/menu`), cart modification (`POST /api/cart/add`), natural language chat (`POST /api/chat`), and checkout confirmation (`POST /api/confirm`).
  - Terminal CLI checks: Verified zero python syntax errors across all files.

### [2026-10-16 16:10] - High-Res Food Photography & Official UPHSD Vector Logo Restoration
- **Role:** John Miko P. Sarsalijo (Driver / Fullstack Lead) / AI Assistant (Navigator)
- **Target Files:** [`templates/index.html`](templates/index.html)
- **Category:** Asset Restoration, Food Photography, Vector SVG Branding & Image Fallback Guard
- **Description:**
  1. **Fixed 5 Broken Menu Item Photos:**
     - Investigated HTTP 404 image links in `FOOD_PHOTOS` for *Truffle Mushroom Pasta*, *Classic Spaghetti Bolognese*, *Golden French Fries*, *Crispy Onion Rings*, and *Mango Passionfruit Smoothie*.
     - Sourced and verified 5 replacement high-resolution food photography assets from Unsplash. All 17/17 catalog items now return HTTP 200 OK.
  2. **Official UPHSD Collegiate Vector SVG Seal:**
     - Replaced the generic emoji placeholder in the top institutional header with an official vector SVG seal of the University of Perpetual Help System DALTA.
     - Modeled with collegiate accuracy: Perpetual Maroon (`#7B1113`) background, dual Academic Gold (`#D4AF37`) concentric rims, university shield emblem, torch of knowledge/character building, laurel wreath of excellence, and crisp typography (`UPHSD`, `DALTA • 1975`).
     - Also embedded the official seal into the printable digital order receipt modal header.
  3. **Graceful Image Fallback Guard:**
     - Added an inline `onerror` fallback handler to `<img class="food-card-img">` in `renderFoodGrid()`, preventing broken image icons in the event of client-side network interruptions.
### [2026-10-16 16:35] - Enterprise Suite: Live Kitchen Display System (KDS), Multi-Option Checkout (GCash/Maya/Student ID), Manager Analytics & Smart Allergen Guard
- **Role:** John Miko P. Sarsalijo (Driver / Fullstack Lead) / AI Assistant (Navigator)
- **Target Files:** [`db_tools.py`](db_tools.py), [`web_dashboard.py`](web_dashboard.py), [`templates/index.html`](templates/index.html)
- **Category:** Full-Stack Commercial Hospitality Architecture & Enterprise Extensions
- **Description:**
  1. **🍳 Live Kitchen Display System (KDS / Back-of-House Screen):**
     - Built dedicated `kitchen_tickets` SQLite table with transactional dispatch whenever front-of-house orders are confirmed.
     - Added `viewKds` live kitchen board featuring:
       - Header metrics: Total Preparing, Ready for Server, Completed Today.
       - Real-time ticket cards displaying Ticket ID, Table Number, dynamic elapsed time (`⏱️ 2m ago`), payment status, itemized quantities, and highlighted amber badges for custom kitchen instructions (e.g., `🧅 No Onions`, `🧀 Extra Melted Cheddar`).
       - Interactive progression buttons: `🔔 Mark as Ready for Server` $\rightarrow$ `✅ Mark as Served to Table`.
       - Filter tabs: All Orders, In Preparation, Ready for Pickup, Completed.
       - Auto-polling background synchronization every 5 seconds.
  2. **💳 Multi-Option Payment & Checkout Modal:**
     - Enhanced checkout flow with a dedicated payment selection modal:
       - **GCash / Maya (QR Ph):** Generates an interactive mock QR Ph code with merchant name ("PERPETUAL BISTRO - UPHSD DALTA"), formatted total, and a 1-click "Simulate GCash Scan & Pay" action.
       - **Perpetual Student ID Card:** Enter 8-digit student number (e.g. `2023-01842-LP`) to simulate meal allowance balance deduction (`₱1,250.00` fund).
       - **Cash at Counter:** Orders claimable and payable upon delivery or at the student center cashier.
     - Stamped Payment Verification Banner on the printable digital receipt (`PAID VIA GCASH [Ref: GC-XXXXXX]`).
     - Added an interactive **Split Bill Calculator** on the receipt allowing diners to calculate equal splits for 1x, 2x, 3x, or 4x diners.
  3. **📊 Manager Analytics & Inventory Control Drawer:**
     - Added executive analytics modal showing Today's Gross Revenue (₱), Total Completed Orders, Average Ticket Size, and Low-Stock Alerts.
     - Interactive inventory management table displaying stock levels for all 17 dishes with quick `+10 Stock` restock buttons and a master `⚡ Restock All Items (+15)` action directly mutating SQLite.
  4. **🛡️ Smart Dietary / Allergen Conflict Detector:**
     - Connected dietary filter chips (`Dairy-Free`, `Gluten-Free`, `Nut-Free`) with automatic dish allergen scanning.
     - If a diner attempts to order a dish that conflicts with their active dietary filter, an interactive alert modal prompts them with recommended chef adaptations (e.g. substituting dairy with plant-based olive oil) and allows 1-click addition of sanitized kitchen instructions.
  5. **🎙️ Web Browser Hands-Free Voice Ordering:**
     - Wired native Web Speech API microphone recognition in the AI chat and kiosk header, enabling customers to speak in English or Filipino Taglish, automatically transcribing their order and triggering conversational voice synthesis via Edge-TTS.
- **Verification:**
  - Automated API verification: Verified `GET /api/kds/tickets`, `POST /api/payment/checkout`, `POST /api/kds/status`, `GET /api/admin/analytics`, and `POST /api/admin/restock` all returning HTTP 200 with 100% success.
  - Server successfully running and tested on port 8000 (`http://localhost:8000`).

### [2026-10-16 17:30] - Hands-Free Voice Auto-Send (3-Second Silence Detection) & Interaction Stability
- **Role:** John Miko P. Sarsalijo (Driver / Voice & UX Lead) / AI Assistant (Navigator)
- **Target Files:** [`templates/index.html`](templates/index.html)
- **Category:** Voice AI & Speech Usability
- **Description:**
  1. **3-Second Silence Auto-Send Mechanism:**
     - Added an automatic 3-second speech silence countdown timer. When the diner pauses, a live countdown badge (`⏱️ Sending in 3s...`, `2s...`, `1s...`) appears in the voice banner.
     - Automatically dispatches the voice query to BistroBot without requiring manual button clicks, while resetting the timer seamlessly whenever the user continues speaking.
  2. **Accurate Speech-to-Order Pipeline:**
     - Connected transcribed speech directly to FSM intent processing and SQLite cart addition.
  3. **Script Scope & Event Listener Hardening:**
     - Resolved duplicate top-level variable declarations, ensuring robust event listener bindings across all interactive elements (navigation buttons, category tabs, food cards, modals).

### [2026-10-16 18:15] - Campus Value Combos (Recommendation #3) & Signature Best Sellers
- **Role:** John Miko P. Sarsalijo (Driver / Fullstack Lead) / AI Assistant (Navigator)
- **Target Files:** [`templates/index.html`](templates/index.html), [`fsm_agent.py`](fsm_agent.py), [`resources/restaurant.db`](resources/restaurant.db), [`init_restaurant_db.sql`](init_restaurant_db.sql)
- **Category:** Menu Engineering, Commercial Bundle Pricing & Smart Recommendations
- **Description:**
  1. **🍱 Campus Value Combos ("Value Meal Bundles"):**
     - Seeded 4 curated combo bundles into `resources/restaurant.db` with discounted prices:
       - *Perpetual Champion Combo* (₱285.00 - Perpetual Classic Burger + Golden French Fries + Fresh Calamansi Iced Tea, Save ₱30)
       - *Pasta & Sweet Treat Combo* (₱330.00 - Creamy Carbonara + Molten Lava Chocolate Cake + Classic Brewed Coffee, Save ₱50)
       - *Chef Ezekiel's Special Duo* (₱420.00 - Bacon Mushroom Melt Burger + Truffle Mushroom Pasta + 2x Iced Teas, Save ₱60)
       - *Late Night Study Fuel Combo* (₱210.00 - Loaded Cheese Fries + Crispy Onion Rings + Iced Caramel Macchiato, Save ₱30)
     - Added dedicated `🍱 Campus Value Combos` category sidebar button with live count badge (`4`).
     - Added 1-click `⚡ Order` and `+ Add` actions for instant combo checkout and KDS dispatch.
     - Registered combos and natural language aliases (`champion combo`, `duo combo`, `study fuel combo`, `value meal`) in `fsm_agent.py`'s `DISH_CATALOG`.
  2. **⭐ Signature Best Sellers System:**
     - Added dedicated `🔥 Best Sellers` category filter tab in the left sidebar highlighting top signature favorites.
     - Designed dynamic badge pills rendered directly on food cards:
       - `⭐ #1 BESTSELLER` (Perpetual Classic Burger)
       - `⭐ CHEF'S SIGNATURE` (Truffle Mushroom Pasta)
       - `🔥 CROWD FAVORITE` (Loaded Cheese Fries)
       - `🌟 MOST POPULAR` (Fresh Calamansi Iced Tea)
       - `🍰 DESSERT OF THE HOUSE` (Molten Lava Chocolate Cake)
       - `🍱 TOP VALUE COMBO` (Perpetual Champion Combo)
     - Enhanced BistroBot AI recommendation dialogue in both Filipino Taglish and English to proactively suggest bestsellers and value combo pairings.
- **Verification:**
  - Automated tests verified database count increased to 21 items (`GET /api/menu`).
  - Headless Edge DOM dump confirmed clean rendering of `.card-badge-bestseller`, `.card-badge-combo`, and category filters.
  - End-to-end chat and voice ordering verified: combo items add to cart, transition FSM, deduct stock, and dispatch KDS fulfillment tickets.



