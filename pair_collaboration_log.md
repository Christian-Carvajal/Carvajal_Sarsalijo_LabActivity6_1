# Tandem Pair Programming Collaboration Log
**Course & Section:** BSCS 3112 — Artificial Intelligence Lab  
**Lesson:** Lesson 6: Conversational State Machines and Workflows  
**Lab Activity 6.1:** Stateful Restaurant Order Agent & Dynamic Tool Calling Engine  
**Institution:** University of Perpetual Help System DALTA (Las Piñas Campus)  
**Instructor:** Prof. Rob Malitao  
**Date:** October 10, 2026 (Updated: October 11, 2026)  

### Team Members & Student Information
1. **Christian Ezekiel L. Carvajal** — BSCS - DS 3rd Year (Student ID: Lead Co-Developer)
2. **John Miko P. Sarsalijo** — BSCS - DS 3rd Year (Student ID: Lead Co-Developer)

---

## 1. Role Definitions & Pedagogical Framework

Following the Extreme Programming (XP) pair programming paradigm covered in Lesson 6, our team alternated between two distinct operational roles across each developmental milestone:

* **The Driver (Tactical Execution):** Operated the keyboard, authored SQL statements, wrote Python syntax, executed shell commands, resolved local runtime errors, and built automated tests.
* **The Navigator (Strategic Architecture):** Monitored the rubric checklist, audited function contracts, spotted edge cases (such as out-of-stock items and lactose intolerance queries), verified state transition boundaries, and inspected token window consumption.

---

## 2. Phase Breakdown & Role Rotation Schedule

### Milestone 1: Relational Schema & Database Tools (Setup Phase)
* **Driver:** Christian Ezekiel L. Carvajal
* **Navigator:** John Miko P. Sarsalijo
* **Focus Modules:** SQLite modeling (`restaurant.db` and `init_restaurant_db.sql`) and foundational database functions in `db_tools.py`.
* **Tactical Output (Carvajal):**
  - Designed relational tables: `menu_items`, `table_sessions`, and `order_line_items`.
  - Added sample inventory with realistic prices and allergen tags.
  - Included an intentionally depleted item (`Crispy Buffalo Chicken Tenders`, stock = 0) to verify inventory bounds.
  - Built atomic operations: `get_menu_by_category()`, `check_item_allergen()`, `check_availability()`, `add_item_to_order()`, and `view_current_order()`.
* **Navigator Review & Feedback (Sarsalijo):**
  - Noted that `add_item_to_order` needed to group identical items with identical special instructions into an updated quantity rather than creating redundant rows.
  - Ensured price figures use 12% VAT calculations common to campus dining billing.
  - Required that allergen queries perform case-insensitive substring matches to handle variations like "dairy" versus "Dairy".

---

### Milestone 2: Conversational FSM Engine & Local Qwen Tool Binding (Midpoint Rotation)
* **Driver:** John Miko P. Sarsalijo
* **Navigator:** Christian Ezekiel L. Carvajal
* **Focus Modules:** FSM controller (`fsm_agent.py`) and Ollama integration with `qwen3.5:4b`.
* **Tactical Output (Sarsalijo):**
  - Implemented the 5-state lifecycle: `STATE_GREETING`, `STATE_MENU_BROWSING`, `STATE_TAKING_ORDER`, `STATE_REVIEW`, and `STATE_CONFIRMED`.
  - Formatted JSON schemas for all 8 bistro tools in Ollama tool calling format.
  - Constructed the tool execution loop: sending tool calls to Python, feeding structured results back as `role: "tool"`, and retrieving the final customer-facing text.
  - Added regex-free conversational flexibility allowing natural Filipino/Taglish phrasing (e.g., "patingin ng menu", "kuha ako ng burger").
* **Navigator Review & Feedback (Carvajal):**
  - Detected that Ollama's default context window (`num_ctx = 4096`) caused truncation during extended multi-turn sessions due to Qwen's internal chain-of-thought tokens.
  - Directed the Driver to expand `num_ctx` to `8192` in the request options.
  - Introduced fallback text synthesis so that if the model returned only raw tool executions on final checkout, a clean, formatted receipt summary is always presented to the user.
  - Recommended stripping internal `<think>` reasoning tags from final user output while keeping them in the JSON telemetry log.

---

### Milestone 3: Interface Construction & Real-Time Synchronization
* **Driver:** Christian Ezekiel L. Carvajal
* **Navigator:** John Miko P. Sarsalijo
* **Focus Modules:** CLI prototype (`virtual_waiter_prototype.py`) and Web Tablet Dashboard (`web_dashboard.py`).
* **Tactical Output (Carvajal):**
  - Built terminal interface using `rich` tables, panels, and state badges.
  - Decoupled I/O into `IOChannel` (`get_input()` and `send_output()`) to satisfy Subtopic 6.5 voice abstraction requirements.
  - Developed the Web-Based Tablet Dashboard (Option 1) on `localhost:8000` with real-time SQLite syncing, quantity controls (+/-), and a modal digital receipt.
* **Navigator Review & Feedback (Sarsalijo):**
  - Verified that manual quantity changes in the right panel immediately updated SQLite and reflected in the conversation state.
  - Confirmed that confirming the order safely decremented `menu_items.stock_qty` within an explicit database transaction.
  - Validated that mobile and tablet viewports maintain zero horizontal overflow.

---

### Milestone 4: Edge-TTS Voice Audio Pipeline & Multimodal Refinement
* **Driver:** John Miko P. Sarsalijo
* **Navigator:** Christian Ezekiel L. Carvajal
* **Focus Modules:** Voice synthesis API (`/api/tts`), phonetic preprocessing, and Web Speech API audio diagnostics in `web_dashboard.py`.
* **Tactical Output (Sarsalijo):**
  - Integrated local asynchronous Edge-TTS using natural Philippine English neural voice (`en-PH-RosaNeural`).
  - Implemented phonetic tuning rules ensuring natural Taglish delivery (e.g. converting "Mabuhay" to phonetic "Mabu-HAI" and formatting prices as "185 pesos" instead of "pesos 185").
  - Added voice enable/disable toggle button with real-time audio state indicators (Listening, Speaking, Muted).
* **Navigator Review & Feedback (Carvajal):**
  - Verified that raw emoji symbols are stripped prior to audio generation to prevent speech synthesis crashes.
  - Tested browser audio autoplay permissions and confirmed smooth audio stream playback via base64 data transfers.
  - Ensured microphone Web Speech recognition accurately captures order modifications without audio clipping.

---

## 3. Key Design Decisions & Problem Resolution

| Challenge | Root Cause | Engineering Solution Implemented | Lead Investigator |
| :--- | :--- | :--- | :--- |
| **Out-of-Stock Handling** | Customer requests items with 0 stock (e.g., Crispy Buffalo Chicken Tenders). | `add_item_to_order()` checks stock before inserting. If depleted, it queries alternatives in the same category and instructs Qwen to suggest them. | Carvajal |
| **Allergen Alerts** | Customers with allergies need verified warnings. | Bound `check_item_allergen()` directly to `menu_items.allergens`. The agent explicitly verifies dairy, gluten, or nuts before confirming orders. | Sarsalijo |
| **Context Window Exhaustion** | Multi-turn reasoning traces in `qwen3.5:4b` filled the default 4K token buffer. | Raised `num_ctx` to 8192 in the Ollama request payload; stripped `<think>` tags from final user-facing text while preserving them in telemetry logs. | Carvajal |
| **Transactional Checkout** | Stock deductions must be atomic to prevent race conditions. | Wrapped `confirm_order_and_deduct_stock()` in `BEGIN TRANSACTION ... COMMIT` with `ROLLBACK` on stock mismatch. | Sarsalijo |
| **Voice Decoupling** | Architecture must allow voice input/output without rewriting state logic. | Implemented `IOChannel` abstraction with `get_input()` and `send_output()`, enabling terminal text, browser Web Speech API, or Python audio pipelines to swap in seamlessly. | Carvajal |
| **Natural Taglish Speech** | Neural voice mispronounced Philippine greetings and currency symbols. | Added regex phonetic substitution pipeline replacing "₱X" with "X pesos" and "Mabuhay" with "Mabu-HAI" before passing text to Edge-TTS. | Sarsalijo |

---

## 4. Work Distribution Summary

| Team Member | Primary Roles Held | Key Modules Authored / Reviewed | Contribution Share |
| :--- | :--- | :--- | :---: |
| **Christian Ezekiel L. Carvajal** | Driver (Milestones 1, 3)<br>Navigator (Milestones 2, 4) | `init_restaurant_db.sql`, `db_tools.py`, `virtual_waiter_prototype.py`, `web_dashboard.py` (UI/CSS/Layout) | 50% |
| **John Miko P. Sarsalijo** | Driver (Milestones 2, 4)<br>Navigator (Milestones 1, 3) | `fsm_agent.py`, Ollama JSON Tool Calling Schemas, Edge-TTS Audio Pipeline (`/api/tts`), Speech Sanitizer | 50% |

### Partner Sign-Off & Verification
Both team members certify that this submission represents genuine collaborative effort adhering to the Extreme Programming Pair Programming standard required by the University of Perpetual Help System DALTA Artificial Intelligence Department.
