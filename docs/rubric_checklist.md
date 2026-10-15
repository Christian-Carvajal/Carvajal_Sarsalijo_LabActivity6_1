# Lab Activity 6.1: Rubric & Compliance Checklist
**Subject:** BSCS 3112 - Artificial Intelligence – Lab (Lesson 6: Conversational State Machines and Workflows)  
**Professor:** Prof. Rob Malitao  
**Date:** October 10, 2026 (Due: October 17, 2026)  
**Students / Team Members:** Christian Ezekiel L. Carvajal & John Miko P. Sarsalijo (BSCS - DS 3rd Year)  
**Model Requirement:** Ollama `qwen3.5:4b`  

---

## 1. Itemized Grading Rubric (Exemplary 4/4 Target)

### Criterion 1: State Machine & Session Memory (4 / 4)
- [x] Implement explicit Finite State Machine (FSM) architecture with 5 distinct dialogue states:
  - `STATE_GREETING`: Welcome customer, capture table number.
  - `STATE_MENU_BROWSING`: Browse categories, query ingredients/allergens, provide item recommendations.
  - `STATE_TAKING_ORDER`: Handle multi-turn ordering, bind tool calls, process modifiers/customizations.
  - `STATE_REVIEW`: Present itemized tab with calculated subtotal, tax/service fees, and totals for customer verification.
  - `STATE_CONFIRMED`: Commit transactional order to SQLite, deduct inventory stock, generate digital receipt, reset session.
- [x] Preserve complete multi-turn conversation context across all dialogue turns.
- [x] Session memory maintains table number, active session ID, and dynamic cart state without losing items or resetting unexpectedly.

### Criterion 2: Tool Calling & Database Binding (4 / 4)
- [x] SQLite database setup (`restaurant.db` via `init_restaurant_db.sql`) with relational schemas:
  - `menu_items`: (id, name, category, price, stock_qty, allergens)
  - `table_sessions`: (session_id, table_no, status, created_at, updated_at)
  - `order_line_items`: (session_id, item_id, quantity, special_instructions)
- [x] Core tool bindings implemented in `db_tools.py`:
  - `get_menu_by_category(category)`
  - `check_item_allergen(item_id_or_name, allergen)`
  - `add_item_to_order(session_id, item_name, qty, instructions)`
  - `view_current_order(session_id)`
  - `remove_item_from_order(session_id, item_name)`
  - `update_item_quantity(session_id, item_name, qty)`
  - `check_availability(item_name, qty)`
  - `confirm_order_and_deduct_stock(session_id)`
- [x] Ollama `qwen3.5:4b` autonomously triggers tool calls with accurate argument parsing.
- [x] Tool execution results feed back into LLM context for polite, natural-language customer replies.

### Criterion 3: Robustness & Edge Handling (4 / 4)
- [x] Out-of-Stock Handling: Gracefully rejects items with insufficient stock and recommends available alternatives in the same category.
- [x] Allergen & Dietary Filter: Accurately checks allergens (peanuts, dairy, gluten, shellfish, etc.) and warns the customer.
- [x] Customization Parsing: Captures complex customer modifiers (e.g., "extra cheese, no onions, make it spicy") into `special_instructions`.
- [x] Out-of-Domain Guardrails: Politely redirects non-dining queries (e.g., general trivia, math questions) back to bistro dining.
- [x] Cancellation & Modifications: Safely updates or deletes line items without crashes or hallucinations.

### Criterion 4: Tandem Collaboration & Code Quality (4 / 4)
- [x] Code is modular, clean, and organized into designated files:
  - `init_restaurant_db.sql`
  - `db_tools.py`
  - `fsm_agent.py`
  - `virtual_waiter_prototype.py`
  - `web_dashboard.py` (Option 1 Highly Recommended web UI)
  - `pair_collaboration_log.md`
  - `sample_conversation_log.json`
- [x] Complete `pair_collaboration_log.md` detailing Driver & Navigator roles, role rotation milestones, design decisions, and code division.

---

## 2. Deliverables Checklist
- [x] `01_Work_In_Progress/init_restaurant_db.sql`
- [x] `01_Work_In_Progress/db_tools.py`
- [x] `01_Work_In_Progress/fsm_agent.py`
- [x] `01_Work_In_Progress/virtual_waiter_prototype.py`
- [x] `01_Work_In_Progress/web_dashboard.py` (Option 1 Web Tablet Interface)
- [x] `01_Work_In_Progress/pair_collaboration_log.md`
- [x] `01_Work_In_Progress/sample_conversation_log.json`
- [x] All final files verified and packaged in `Carvajal_Sarsalijo_LabActivity6_1/`
- [x] Formal Academic Lab Report compiled according to Perpetual institutional guidelines.
