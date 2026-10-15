# Perpetual Bistro: Stateful Restaurant Order Agent & Dynamic Tool Calling Engine
### Lab Activity 6.1 — Artificial Intelligence (CS FSM & AI Workflows)
**University of Perpetual Help System DALTA — Las Piñas Campus**  
**Instructor:** Prof. Rob Malitao  
**Authors:** Christian Ezekiel L. Carvajal & John Miko P. Sarsalijo  

---

## 📋 Required Deliverables (100% Compliant)

| Deliverable | File | Description |
| :--- | :--- | :--- |
| **1. Database Setup & Tool Binding** | [`init_restaurant_db.sql`](init_restaurant_db.sql) & [`db_tools.py`](db_tools.py) | SQLite DDL schema, initial menu seeds, and Python tool functions with atomic inventory management. |
| **2. FSM Controller** | [`fsm_agent.py`](fsm_agent.py) | 5-state deterministic dialogue engine (`GREETING`, `TAKING_ORDER`, `REVIEW`, `CONFIRMED`, `CANCELLED`). |
| **3. Executable CLI Prototype** | [`virtual_waiter_prototype.py`](virtual_waiter_prototype.py) | Full terminal application with Rich TUI tables and voice synthesis. |
| **4. Tandem Collaboration Log** | [`pair_collaboration_log.md`](pair_collaboration_log.md) | Role rotations (Driver/Navigator), task distributions (50/50 split), and architectural decisions. |
| **5. Conversation & Trace Log** | [`sample_conversation_log.json`](sample_conversation_log.json) | Saved multi-turn dialogue log capturing tool executions, FSM state updates, and SQLite commits. |
| **Option 1 Web Dashboard** | [`web_dashboard.py`](web_dashboard.py) | FastAPI + WebSocket tabletop kiosk UI with McDonald's language toggle (🇵🇭 Filipino / 🇺🇸 English). |
| **Formal Academic Report** | [`Carvajal_Sarsalijo_LabActivity6_1_Report.pdf`](Carvajal_Sarsalijo_LabActivity6_1_Report.pdf) | Formal project documentation formatted per Perpetual institutional template. |

---

## 🚀 Quick Start Guide

### 1. Requirements
- Python 3.10+
- [Ollama](https://ollama.com/) running locally with model: `qwen2.5` or `qwen3.5` (`ollama run qwen3.5:4b`)
- Dependencies: `pip install fastapi uvicorn websockets edge-tts rich requests sounddevice`

### 2. Launching the Web Kiosk Dashboard (Recommended)
```powershell
python web_dashboard.py --port 8000
```
Open **`http://127.0.0.1:8000`** in your browser to interact with the McDonald's Kiosk UI.

### 3. Launching the Terminal CLI Prototype
```powershell
python virtual_waiter_prototype.py --table 5
```

---

## 🤖 Guide for Collaborating AI Agents (Miko & Assistants)

For John Miko P. Sarsalijo and any AI assistant working on this repository, please review:
👉 **[`docs/AGENT_ONBOARDING_GUIDE.md`](docs/AGENT_ONBOARDING_GUIDE.md)**

It contains:
- Mandatory read-first protocol and briefing steps for John Miko.
- Instructions for logging contributions in `SarsalijoProjectChanges.md`.
- Recommended UI/UX enhancements and testing workflows.
- Full architectural breakdown of database tools, state machine, and acoustic speech normalization.
