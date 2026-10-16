"""
web_dashboard.py
Ultra-Aesthetic, Super Organized, Clean Tabletop Ordering Kiosk & Waiter Dashboard
University of Perpetual Help System DALTA — Las Piñas Campus
Lab Activity 6.1 — Stateful Restaurant Order Agent & Dynamic Tool Calling Engine
Runs on localhost:8000 using FastAPI and Uvicorn.
Synchronized in real-time with SQLite (restaurant.db) and Ollama (qwen3.5:4b).
"""

import os
import sys
import json
import re
from typing import Optional, Dict, Any
from pydantic import BaseModel

# Add current folder to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import edge_tts

import db_tools
from fsm_agent import (
    BistroFSMAgent,
    STATE_GREETING,
    STATE_MENU_BROWSING,
    STATE_TAKING_ORDER,
    STATE_REVIEW,
    STATE_CONFIRMED,
    DEFAULT_MODEL,
)

# Initialize database
db_tools.init_db()

app = FastAPI(title="Perpetual Bistro Digital Table-Top Ordering System")

# Enable CORS for local cross-origin development if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active Agent Instance (Default Table #1)
CURRENT_TABLE = 1
active_agent = BistroFSMAgent(table_no=CURRENT_TABLE, model=DEFAULT_MODEL)


class ChatRequest(BaseModel):
    message: str
    table_no: Optional[int] = None


class CartAddRequest(BaseModel):
    item_name: str
    qty: Optional[int] = 1
    instructions: Optional[str] = ""


class CartUpdateRequest(BaseModel):
    item_name: str
    qty: int


class SessionResetRequest(BaseModel):
    table_no: Optional[int] = 1


class TableSwitchRequest(BaseModel):
    table_no: int


class LanguageRequest(BaseModel):
    language: str


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None
    language: Optional[str] = "filipino"


@app.get("/api/session")
def get_session_info():
    """Returns active session details, language, table number, and FSM state."""
    cart = db_tools.view_current_order(active_agent.session_id)
    return {
        "session_id": active_agent.session_id,
        "table_no": active_agent.table_no,
        "fsm_state": active_agent.state,
        "language": getattr(active_agent, "language", "filipino"),
        "model": active_agent.model,
        "cart": cart,
    }


@app.get("/api/menu")
def get_menu():
    """Returns the full bistro menu grouped by category."""
    return db_tools.get_menu_by_category("all")


@app.get("/api/cart")
def get_cart():
    """Returns current order cart synced with SQLite."""
    return db_tools.view_current_order(active_agent.session_id)


def sanitize_for_speech(t: str, language: str = "filipino") -> str:
    """Pre-cleans text for speech synthesis: tunes phonetics, strips emojis/markdown, and formats pesos."""
    if not t:
        return ""
    s = t

    # 1. Currency formatting: number first, always clean pesos
    s = re.sub(r'₱\s*(\d+(?:\.\d+)?)(?:\s*pesos)?', r'\1 pesos', s, flags=re.IGNORECASE)
    s = re.sub(r'₱', ' pesos', s)

    if (language or "filipino").lower() == "filipino":
        # 2. Phonetic tuning: Mabuhay -> Mabuhigh (/mɐˈbuːhaɪ/)
        s = re.sub(r'\b[Mm]abuhay\b', 'Mabuhigh', s)
        
        # 3. Short Tagalog particles that English G2P spells as initialisms/acronyms
        s = re.sub(r'\bmo\b', 'moh', s, flags=re.IGNORECASE)
        s = re.sub(r'\bba\b', 'bah', s, flags=re.IGNORECASE)
        s = re.sub(r'\bpo\b', 'poh', s, flags=re.IGNORECASE)
        s = re.sub(r'\bko\b', 'koh', s, flags=re.IGNORECASE)
        s = re.sub(r'\bka\b', 'kah', s, flags=re.IGNORECASE)
        s = re.sub(r'\bpa\b', 'pah', s, flags=re.IGNORECASE)
        s = re.sub(r'\bna\b', 'nah', s, flags=re.IGNORECASE)
        s = re.sub(r'\bsa\b', 'sah', s, flags=re.IGNORECASE)
        s = re.sub(r'\bng\b', 'nang', s, flags=re.IGNORECASE)
        s = re.sub(r'\bmga\b', 'manga', s, flags=re.IGNORECASE)
        s = re.sub(r'\bpwede\b', 'puwede', s, flags=re.IGNORECASE)
        s = re.sub(r'\bPwede\b', 'Puwede', s)

        # 4. Anti-awkward Tagalog numbers & phrases in campus Taglish
        s = re.sub(r'\b[Tt]able\s+isa\b', 'Table one', s, flags=re.IGNORECASE)
        s = re.sub(r'\b[Mm]esa\s+isa\b', 'Table one', s, flags=re.IGNORECASE)
        s = re.sub(r'\bqwen\s*tatlong\s*punto\s*lima\b', 'Qwen three point five', s, flags=re.IGNORECASE)
        s = re.sub(r'\bqwen\s*tatlung\s*punto\s*lima\b', 'Qwen three point five', s, flags=re.IGNORECASE)
        s = re.sub(r'\bPerpetual and by\b', 'Perpetual Bistro', s, flags=re.IGNORECASE)

    # 5. Strip all SMP emojis (U+10000 - U+10FFFF), Dingbats/Misc symbols, variation selectors, ZWJ
    emoji_pattern = re.compile(r'[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\ufe00-\ufe0f]|\u200d', flags=re.UNICODE)
    s = emoji_pattern.sub('', s)

    # 6. Strip markdown syntax
    s = re.sub(r'[*#_~`>]', '', s)

    # 7. Collapse extra whitespace
    return re.sub(r'\s+', ' ', s).strip()


@app.post("/api/language")
def set_language_endpoint(req: LanguageRequest):
    """Switches the active persona language (Filipino/Taglish vs. English)."""
    global active_agent
    lang = req.language.lower().strip()
    if lang not in ["filipino", "english"]:
        raise HTTPException(status_code=400, detail="Language must be 'filipino' or 'english'.")
    active_agent.set_language(lang)
    if lang == "english":
        greeting = f"Welcome to Perpetual Bistro! Table #{active_agent.table_no} language set to English. How may I assist you today?"
        default_voice = "en-US-JennyNeural"
    else:
        greeting = f"Mabuhay! Naka-set na sa Filipino Taglish para sa Table #{active_agent.table_no}. Ano po ang gusto ninyong i-order?"
        default_voice = "en-PH-RosaNeural"
    return {
        "status": "success",
        "language": lang,
        "greeting": greeting,
        "voice": default_voice,
        "speech_text": sanitize_for_speech(greeting, language=lang)
    }


@app.post("/api/chat")
def process_chat(req: ChatRequest):
    """Processes customer natural language input via BistroFSMAgent."""
    global active_agent
    if req.table_no and req.table_no != active_agent.table_no:
        active_agent.set_table_number(req.table_no)

    try:
        turn_data = active_agent.process_turn(req.message)
        turn_data["language"] = getattr(active_agent, "language", "filipino")
        turn_data["speech_text"] = sanitize_for_speech(
            turn_data.get("assistant_response", ""),
            language=turn_data["language"]
        )
        return turn_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cart/add")
def add_cart_item(req: CartAddRequest):
    """Direct visual menu addition with customizations, stock validation, and FSM progression."""
    global active_agent
    res = active_agent.execute_tool("add_item_to_order", {
        "item_name": req.item_name,
        "qty": req.qty or 1,
        "instructions": req.instructions or ""
    })
    cart = db_tools.view_current_order(active_agent.session_id)
    return {
        "result": res,
        "cart": cart,
        "fsm_state": active_agent.state
    }


@app.post("/api/cart/update")
def update_cart_item(req: CartUpdateRequest):
    """Interactive quantity adjuster (+ / -) from the right panel."""
    res = db_tools.update_item_quantity(active_agent.session_id, req.item_name, req.qty)
    cart = db_tools.view_current_order(active_agent.session_id)
    return {"result": res, "cart": cart, "fsm_state": active_agent.state}


@app.post("/api/cart/remove")
def remove_cart_item(req: CartUpdateRequest):
    """Removes an item from the cart."""
    res = db_tools.remove_item_from_order(active_agent.session_id, req.item_name)
    cart = db_tools.view_current_order(active_agent.session_id)
    return {"result": res, "cart": cart, "fsm_state": active_agent.state}


@app.post("/api/table/switch")
def switch_table_endpoint(req: TableSwitchRequest):
    """Switches the active dining table without breaking session context."""
    global active_agent
    if req.table_no != active_agent.table_no:
        active_agent.set_table_number(req.table_no)
    cart = db_tools.view_current_order(active_agent.session_id)
    return {
        "status": "success",
        "table_no": active_agent.table_no,
        "session_id": active_agent.session_id,
        "fsm_state": active_agent.state,
        "cart": cart
    }


@app.post("/api/confirm")
def confirm_order():
    """Triggers FSM transition from REVIEW to CONFIRMED and deducts stock."""
    res = active_agent.execute_tool("confirm_order_and_deduct_stock", {})
    cart = db_tools.view_current_order(active_agent.session_id)
    return {"receipt": res, "cart": cart, "fsm_state": active_agent.state}


@app.post("/api/reset")
def reset_session(req: SessionResetRequest):
    """Resets the tablet session for the next customer."""
    global active_agent
    table_num = req.table_no or 1
    current_lang = getattr(active_agent, "language", "filipino")
    active_agent = BistroFSMAgent(table_no=table_num, model=DEFAULT_MODEL, language=current_lang)
    return {"status": "success", "message": f"Table #{table_num} reset successfully."}


@app.post("/api/tts")
async def natural_tts_endpoint(req: TTSRequest):
    """Generates broadcast-quality natural human speech using Microsoft Jenny (English) or Rosa (Taglish)."""
    lang = (req.language or getattr(active_agent, "language", "filipino")).lower().strip()
    clean_text = sanitize_for_speech(req.text, language=lang)
    if not clean_text:
        return Response(content=b"", media_type="audio/mpeg")

    if req.voice:
        voice = req.voice
    elif lang == "english":
        voice = "en-US-JennyNeural"
    else:
        voice = "en-PH-RosaNeural"

    try:
        communicate = edge_tts.Communicate(clean_text, voice)
        chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        audio_bytes = b"".join(chunks)
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        print(f"Edge-TTS synthesis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/", response_class=HTMLResponse)
def index_page():
    """Serves the complete single-page interactive tablet dashboard."""
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>University of Perpetual Help — Perpetual Bistro Kiosk</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800;900&family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            /* Official UPHSD Prestige Palette */
            --uphsd-maroon: #7B1113;
            --uphsd-maroon-dark: #4A070B;
            --uphsd-maroon-deep: #220407;
            --uphsd-maroon-light: #9B1B1E;
            --uphsd-maroon-glow: rgba(123, 17, 19, 0.4);

            --uphsd-gold: #D4AF37;
            --uphsd-gold-bright: #F5B041;
            --uphsd-gold-deep: #AA820A;
            --uphsd-gold-light: #FEF3C7;
            --uphsd-gold-glow: rgba(212, 175, 55, 0.28);

            /* Surfaces & Dark Glassmorphism */
            --bg-base: #0A0305;
            --bg-gradient: radial-gradient(circle at 10% 15%, rgba(123, 17, 19, 0.22) 0%, transparent 55%),
                           radial-gradient(circle at 90% 85%, rgba(212, 175, 55, 0.12) 0%, transparent 50%),
                           linear-gradient(180deg, #0C0406 0%, #070203 100%);
            --surface-panel: rgba(18, 5, 8, 0.88);
            --surface-card: rgba(26, 8, 12, 0.82);
            --surface-card-hover: rgba(42, 13, 19, 0.96);
            --border-subtle: rgba(212, 175, 55, 0.18);
            --border-gold: rgba(212, 175, 55, 0.4);
            --border-focus: #F5B041;

            /* Typography & Neutrals */
            --text-primary: #FFFFFF;
            --text-secondary: #E8D8DB;
            --text-muted: #A3858B;
            --accent-green: #10B981;
            --accent-green-bg: rgba(16, 185, 129, 0.15);
            --accent-red: #EF4444;
            --accent-red-bg: rgba(239, 68, 68, 0.15);

            --font-heading: 'Cinzel', Georgia, serif;
            --font-ui: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            --font-mono: 'JetBrains Mono', Consolas, monospace;
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 16px;
            --radius-pill: 9999px;
            --shadow-card: 0 4px 20px rgba(0, 0, 0, 0.4), 0 1px 3px rgba(0, 0, 0, 0.2);
            --shadow-gold: 0 4px 18px rgba(212, 175, 55, 0.25);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: var(--font-ui);
            background: var(--bg-base);
            background-image: var(--bg-gradient);
            background-attachment: fixed;
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            -webkit-font-smoothing: antialiased;
        }

        /* Top Institutional Utility Ribbon */
        .uphsd-top-ribbon {
            background: linear-gradient(90deg, #1C0305 0%, #300609 50%, #1C0305 100%);
            border-bottom: 1px solid rgba(212, 175, 55, 0.25);
            padding: 4px 24px;
            font-size: 0.72rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            color: var(--uphsd-gold-light);
            letter-spacing: 0.03em;
            user-select: none;
            z-index: 20;
        }

        .ribbon-motto {
            font-family: var(--font-heading);
            font-weight: 700;
            color: var(--uphsd-gold-bright);
            letter-spacing: 0.06em;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        .ribbon-campus {
            color: var(--text-muted);
            margin-left: 10px;
            font-size: 0.7rem;
        }

        .ribbon-right {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .live-clock {
            font-family: var(--font-mono);
            color: var(--uphsd-gold-light);
            font-weight: 600;
        }

        .system-status-indicator {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 0.68rem;
            color: #A7F3D0;
        }

        .status-dot {
            width: 7px;
            height: 7px;
            background: #10B981;
            border-radius: 50%;
            box-shadow: 0 0 8px #10B981;
            animation: pulseDot 2s infinite;
        }

        @keyframes pulseDot {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(0.85); }
        }

        /* Main Institutional Header */
        header {
            background: linear-gradient(135deg, #2D0407 0%, #4D090E 45%, #6B0F15 75%, #350508 100%);
            border-bottom: 2px solid var(--uphsd-gold);
            box-shadow: 0 4px 24px rgba(0, 0, 0, 0.6), 0 0 15px var(--uphsd-gold-glow);
            padding: 8px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: relative;
            z-index: 19;
            backdrop-filter: blur(12px);
        }

        .brand-container {
            display: flex;
            align-items: center;
            gap: 14px;
            cursor: pointer;
        }

        .brand-seal {
            width: 44px;
            height: 44px;
            flex-shrink: 0;
            filter: drop-shadow(0 2px 8px rgba(0, 0, 0, 0.5));
            transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
        }

        .brand-container:hover .brand-seal {
            transform: scale(1.08) rotate(2deg);
        }

        .brand-title {
            display: flex;
            flex-direction: column;
            gap: 1px;
        }

        .university-name {
            font-family: var(--font-heading);
            font-size: 0.63rem;
            font-weight: 700;
            color: var(--uphsd-gold-bright);
            letter-spacing: 0.09em;
            text-transform: uppercase;
        }

        .brand-title h1 {
            font-family: var(--font-heading);
            font-size: 1.22rem;
            font-weight: 900;
            letter-spacing: 0.04em;
            color: #FFFFFF;
            text-shadow: 0 2px 8px rgba(0, 0, 0, 0.7), 0 0 14px rgba(212, 175, 55, 0.3);
            line-height: 1.1;
        }

        .brand-title p {
            font-size: 0.7rem;
            color: var(--text-secondary);
            font-weight: 500;
        }

        .header-meta {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }

        /* Interactive Table Dropdown Selector */
        .table-selector-wrap {
            position: relative;
        }

        .table-select-btn {
            background: rgba(22, 6, 9, 0.9);
            border: 1px solid var(--border-gold);
            color: var(--uphsd-gold-bright);
            padding: 5px 12px;
            border-radius: var(--radius-pill);
            font-size: 0.78rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        }

        .table-select-btn:hover {
            border-color: var(--uphsd-gold-bright);
            background: rgba(45, 12, 18, 0.95);
        }

        .table-dropdown-menu {
            position: absolute;
            top: 110%;
            left: 0;
            background: #1A0609;
            border: 1px solid var(--uphsd-gold);
            border-radius: var(--radius-md);
            padding: 6px;
            display: none;
            flex-direction: column;
            gap: 3px;
            min-width: 140px;
            z-index: 50;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.8), 0 0 15px var(--uphsd-gold-glow);
            animation: fadeIn 0.15s ease-out;
        }

        .table-dropdown-menu.show {
            display: flex;
        }

        .table-opt-btn {
            background: transparent;
            border: none;
            color: var(--text-secondary);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 0.78rem;
            font-weight: 600;
            text-align: left;
            cursor: pointer;
            transition: all 0.15s;
            display: flex;
            justify-content: space-between;
        }

        .table-opt-btn:hover {
            background: var(--uphsd-maroon);
            color: #FFFFFF;
        }

        .table-opt-btn.active {
            background: linear-gradient(135deg, var(--uphsd-gold-bright) 0%, var(--uphsd-gold) 100%);
            color: var(--uphsd-maroon-dark);
            font-weight: 800;
        }

        /* Pill Badges */
        .meta-pill {
            background: rgba(22, 6, 9, 0.85);
            border: 1px solid var(--border-gold);
            color: var(--uphsd-gold-light);
            padding: 5px 12px;
            border-radius: var(--radius-pill);
            font-size: 0.76rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
        }

        /* Sound Wave Audio Visualizer */
        .audio-wave-container {
            display: inline-flex;
            align-items: center;
            gap: 3px;
            height: 18px;
            padding: 0 3px;
        }

        .wave-bar {
            width: 3px;
            height: 5px;
            background: var(--uphsd-gold-bright);
            border-radius: 2px;
            transition: height 0.15s ease;
        }

        .audio-wave-container.speaking .wave-bar {
            animation: wavePulse 1s ease-in-out infinite;
        }

        .audio-wave-container.speaking .wave-bar:nth-child(1) { animation-delay: 0.0s; }
        .audio-wave-container.speaking .wave-bar:nth-child(2) { animation-delay: 0.2s; }
        .audio-wave-container.speaking .wave-bar:nth-child(3) { animation-delay: 0.4s; }
        .audio-wave-container.speaking .wave-bar:nth-child(4) { animation-delay: 0.1s; }
        .audio-wave-container.speaking .wave-bar:nth-child(5) { animation-delay: 0.3s; }

        @keyframes wavePulse {
            0%, 100% { height: 5px; }
            50% { height: 16px; background: #FFF; }
        }

        /* Language Selector Group */
        .lang-selector-group {
            display: inline-flex;
            align-items: center;
            background: rgba(24, 7, 10, 0.95);
            border: 1px solid var(--uphsd-gold);
            border-radius: var(--radius-pill);
            padding: 2px;
            gap: 2px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
        }

        .lang-btn {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 4px 12px;
            border-radius: var(--radius-pill);
            font-size: 0.74rem;
            font-weight: 700;
            color: var(--uphsd-gold-light);
            background: transparent;
            border: none;
            cursor: pointer;
            transition: all 0.2s ease;
            user-select: none;
        }

        .lang-btn:hover {
            color: #FFFFFF;
            background: rgba(212, 175, 55, 0.18);
        }

        .lang-btn.active {
            background: linear-gradient(135deg, var(--uphsd-gold-bright) 0%, var(--uphsd-gold) 100%);
            color: var(--uphsd-maroon-dark);
            font-weight: 800;
            box-shadow: 0 2px 6px rgba(212, 175, 55, 0.4);
        }

        /* FSM State Badge */
        .state-badge {
            font-family: var(--font-heading);
            font-weight: 800;
            text-transform: uppercase;
            font-size: 0.7rem;
            letter-spacing: 0.08em;
            padding: 5px 12px;
            border-radius: 6px;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35);
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        .state-dot-live {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: currentColor;
            display: inline-block;
            box-shadow: 0 0 6px currentColor;
        }

        .state-GREETING {
            background: linear-gradient(135deg, #78350F, #92400E);
            color: #FEF3C7;
            border: 1px solid var(--uphsd-gold);
        }

        .state-MENU_BROWSING {
            background: linear-gradient(135deg, #1E3A8A, #2563EB);
            color: #DBEAFE;
            border: 1px solid #60A5FA;
        }

        .state-TAKING_ORDER {
            background: linear-gradient(135deg, #064E3B, #047857);
            color: #D1FAE5;
            border: 1px solid #34D399;
        }

        .state-REVIEW {
            background: linear-gradient(135deg, #581C87, #7E22CE);
            color: #F5D0FE;
            border: 1px solid #C084FC;
        }

        .state-CONFIRMED {
            background: linear-gradient(135deg, #14532D, #15803D);
            color: #DCFCE7;
            border: 1px solid var(--uphsd-gold-bright);
        }

        /* Top Kiosk Navigation View Switcher (Tabs) */
        .kiosk-nav-bar {
            background: linear-gradient(180deg, #180507 0%, #110305 100%);
            border-bottom: 1px solid var(--border-gold);
            padding: 6px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            user-select: none;
            z-index: 18;
        }

        .nav-tabs-group {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .nav-view-btn {
            background: rgba(26, 8, 12, 0.7);
            border: 1px solid var(--border-subtle);
            color: var(--text-secondary);
            padding: 6px 16px;
            border-radius: var(--radius-pill);
            font-size: 0.8rem;
            font-weight: 700;
            display: inline-flex;
            align-items: center;
            gap: 7px;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .nav-view-btn:hover {
            color: #FFFFFF;
            border-color: var(--uphsd-gold);
            background: rgba(45, 12, 18, 0.9);
            transform: translateY(-1px);
        }

        .nav-view-btn.active {
            background: linear-gradient(135deg, var(--uphsd-maroon) 0%, var(--uphsd-maroon-dark) 100%);
            border-color: var(--uphsd-gold);
            color: var(--uphsd-gold-bright);
            font-weight: 800;
            box-shadow: 0 2px 10px rgba(123, 17, 19, 0.45);
        }

        .nav-badge-count {
            background: rgba(212, 175, 55, 0.2);
            color: var(--uphsd-gold-bright);
            padding: 1px 7px;
            border-radius: 9999px;
            font-size: 0.7rem;
            font-family: var(--font-mono);
        }

        .btn-reset-session {
            background: rgba(30, 8, 12, 0.8);
            border: 1px solid rgba(239, 68, 68, 0.4);
            color: #FCA5A5;
            padding: 5px 12px;
            border-radius: var(--radius-pill);
            font-size: 0.74rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }

        .btn-reset-session:hover {
            background: #7F1D1D;
            color: #FFFFFF;
            border-color: #EF4444;
        }

        /* Main Workspace: 2-Panel Split */
        .workspace {
            flex: 1;
            display: grid;
            grid-template-columns: 1fr 430px;
            overflow: hidden;
            background: var(--bg-base);
        }

        /* Left Workspace Canvas */
        .left-panel {
            display: flex;
            flex-direction: column;
            border-right: 1px solid var(--border-subtle);
            background: var(--surface-panel);
            overflow: hidden;
            position: relative;
        }

        /* Views (Menu vs Chat) */
        .view-content-pane {
            flex: 1;
            display: none;
            flex-direction: column;
            overflow: hidden;
        }

        .view-content-pane.active {
            display: flex;
        }

        /* Split Mode: displays both panes side-by-side */
        .left-panel.split-layout {
            display: grid;
            grid-template-columns: 1.15fr 0.85fr;
        }

        .left-panel.split-layout .view-content-pane {
            display: flex !important;
            border-right: 1px solid var(--border-subtle);
        }

        /* 1. VISUAL MENU CATALOG VIEW */
        .menu-toolbar {
            padding: 12px 20px;
            background: linear-gradient(180deg, #170406 0%, #120305 100%);
            border-bottom: 1px solid var(--border-subtle);
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .search-and-dietary-row {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .menu-search-box {
            flex: 1;
            position: relative;
            display: flex;
            align-items: center;
        }

        .search-icon {
            position: absolute;
            left: 12px;
            font-size: 0.9rem;
            color: var(--uphsd-gold);
            pointer-events: none;
        }

        .menu-search-input {
            width: 100%;
            background: rgba(14, 4, 6, 0.9);
            border: 1px solid var(--border-gold);
            border-radius: var(--radius-pill);
            padding: 8px 14px 8px 36px;
            font-size: 0.84rem;
            color: #FFFFFF;
            font-family: var(--font-ui);
            outline: none;
            transition: all 0.2s;
        }

        .menu-search-input:focus {
            border-color: var(--uphsd-gold-bright);
            box-shadow: 0 0 0 3px rgba(212, 175, 55, 0.25);
            background: #180608;
        }

        .dietary-filters-wrap {
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .diet-chip {
            background: rgba(30, 8, 12, 0.7);
            border: 1px solid var(--border-subtle);
            color: var(--text-muted);
            font-size: 0.72rem;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: var(--radius-pill);
            cursor: pointer;
            user-select: none;
            transition: all 0.15s;
        }

        .diet-chip:hover {
            color: #FFF;
            border-color: var(--uphsd-gold);
        }

        .diet-chip.active {
            background: rgba(212, 175, 55, 0.2);
            border-color: var(--uphsd-gold-bright);
            color: var(--uphsd-gold-bright);
            font-weight: 700;
        }

        /* Category Tabs Bar */
        .category-tabs-bar {
            display: flex;
            align-items: center;
            gap: 8px;
            overflow-x: auto;
            scrollbar-width: none;
            padding-bottom: 2px;
        }

        .category-tabs-bar::-webkit-scrollbar {
            display: none;
        }

        .cat-pill {
            background: var(--surface-card);
            border: 1px solid var(--border-subtle);
            color: var(--text-secondary);
            font-size: 0.76rem;
            font-weight: 600;
            padding: 5px 14px;
            border-radius: var(--radius-pill);
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            user-select: none;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }

        .cat-pill:hover {
            color: #FFFFFF;
            border-color: var(--uphsd-gold);
            background: var(--surface-card-hover);
            transform: translateY(-1px);
        }

        .cat-pill.active {
            background: linear-gradient(135deg, var(--uphsd-maroon) 0%, var(--uphsd-maroon-dark) 100%);
            border-color: var(--uphsd-gold);
            color: var(--uphsd-gold-bright);
            font-weight: 700;
            box-shadow: 0 2px 8px rgba(123, 17, 19, 0.4);
        }

        /* Menu Items Grid */
        .menu-grid-scroll {
            flex: 1;
            overflow-y: auto;
            padding: 18px;
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
            gap: 16px;
            align-content: start;
        }

        /* Entire Card is Clickable! */
        .menu-item-card {
            background: linear-gradient(145deg, rgba(32, 10, 15, 0.88) 0%, rgba(20, 6, 9, 0.94) 100%);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            padding: 14px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            transition: all 0.22s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: var(--shadow-card);
            position: relative;
            cursor: pointer;
            user-select: none;
        }

        .menu-item-card:hover {
            border-color: var(--uphsd-gold);
            transform: translateY(-3px);
            box-shadow: 0 10px 26px rgba(0, 0, 0, 0.65), 0 0 16px rgba(212, 175, 55, 0.25);
            background: linear-gradient(145deg, rgba(45, 14, 20, 0.98) 0%, rgba(26, 8, 12, 1) 100%);
        }

        .menu-item-card.card-pulse {
            animation: cardHighlight 0.45s ease-out;
        }

        @keyframes cardHighlight {
            0% { transform: scale(0.98); box-shadow: 0 0 0 4px var(--uphsd-gold-bright); }
            100% { transform: scale(1); box-shadow: var(--shadow-card); }
        }

        .menu-item-card.out-of-stock {
            opacity: 0.6;
            filter: grayscale(0.4);
            cursor: not-allowed;
        }

        .menu-item-card.out-of-stock:hover {
            transform: none;
            border-color: var(--accent-red);
        }

        .card-top-badges {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .dish-cat-badge {
            font-size: 0.68rem;
            font-weight: 700;
            color: var(--uphsd-gold-light);
            background: rgba(212, 175, 55, 0.15);
            border: 1px solid rgba(212, 175, 55, 0.3);
            padding: 2px 8px;
            border-radius: var(--radius-pill);
            letter-spacing: 0.04em;
        }

        .stock-indicator-badge {
            font-size: 0.68rem;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: var(--radius-pill);
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }

        .stock-indicator-badge.in-stock {
            background: var(--accent-green-bg);
            color: #6EE7B7;
            border: 1px solid rgba(16, 185, 129, 0.35);
        }

        .stock-indicator-badge.out-stock {
            background: var(--accent-red-bg);
            color: #FCA5A5;
            border: 1px solid rgba(239, 68, 68, 0.35);
        }

        .dish-visual-header {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .dish-icon-box {
            width: 48px;
            height: 48px;
            border-radius: var(--radius-md);
            background: linear-gradient(135deg, rgba(123, 17, 19, 0.45) 0%, rgba(212, 175, 55, 0.18) 100%);
            border: 1px solid rgba(212, 175, 55, 0.3);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.55rem;
            flex-shrink: 0;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3);
        }

        .dish-title-group {
            flex: 1;
            min-width: 0;
        }

        .dish-name {
            font-weight: 700;
            font-size: 0.94rem;
            color: #FFFFFF;
            line-height: 1.25;
            margin-bottom: 2px;
        }

        .dish-price {
            font-family: var(--font-heading);
            font-weight: 800;
            color: var(--uphsd-gold-bright);
            font-size: 1rem;
        }

        .dish-desc {
            font-size: 0.77rem;
            color: var(--text-secondary);
            line-height: 1.45;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            flex: 1;
        }

        /* Allergen Badges */
        .allergen-pills-row {
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
        }

        .allergen-pill {
            font-size: 0.66rem;
            font-weight: 600;
            padding: 2px 7px;
            border-radius: 4px;
            display: inline-flex;
            align-items: center;
            gap: 3px;
        }

        .allergen-dairy { background: rgba(56, 189, 248, 0.15); color: #7DD3FC; border: 1px solid rgba(56, 189, 248, 0.3); }
        .allergen-gluten { background: rgba(251, 191, 36, 0.15); color: #FCD34D; border: 1px solid rgba(251, 191, 36, 0.3); }
        .allergen-nuts { background: rgba(245, 158, 11, 0.18); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.35); }
        .allergen-pork { background: rgba(244, 63, 94, 0.15); color: #FDA4AF; border: 1px solid rgba(244, 63, 94, 0.3); }
        .allergen-egg { background: rgba(250, 204, 21, 0.15); color: #FEF08A; border: 1px solid rgba(250, 204, 21, 0.3); }
        .allergen-fish { background: rgba(99, 102, 241, 0.15); color: #A5B4FC; border: 1px solid rgba(99, 102, 241, 0.3); }
        .allergen-beef { background: rgba(180, 83, 9, 0.18); color: #FDE68A; border: 1px solid rgba(180, 83, 9, 0.3); }
        .allergen-none { background: rgba(16, 185, 129, 0.12); color: #A7F3D0; border: 1px solid rgba(16, 185, 129, 0.25); }

        .card-actions-row {
            display: flex;
            gap: 6px;
            margin-top: auto;
            padding-top: 8px;
            border-top: 1px solid rgba(212, 175, 55, 0.12);
        }

        /* 1-Click Order Now Button */
        .btn-card-order-now {
            flex: 1.1;
            background: linear-gradient(135deg, #10B981 0%, #059669 100%);
            border: 1px solid #34D399;
            color: #FFFFFF;
            padding: 8px 10px;
            border-radius: var(--radius-sm);
            font-size: 0.78rem;
            font-weight: 800;
            cursor: pointer;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            box-shadow: 0 2px 8px rgba(16, 185, 129, 0.35);
        }

        .btn-card-order-now:hover:not(:disabled) {
            filter: brightness(1.15);
            transform: translateY(-1px);
            box-shadow: 0 4px 14px rgba(16, 185, 129, 0.5);
        }

        .btn-card-add {
            flex: 0.9;
            background: linear-gradient(135deg, var(--uphsd-gold-bright) 0%, var(--uphsd-gold) 100%);
            border: 1px solid var(--uphsd-gold-bright);
            color: var(--uphsd-maroon-dark);
            padding: 8px 10px;
            border-radius: var(--radius-sm);
            font-size: 0.78rem;
            font-weight: 800;
            cursor: pointer;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            box-shadow: 0 2px 8px rgba(212, 175, 55, 0.3);
        }

        .btn-card-add:hover:not(:disabled) {
            filter: brightness(1.12);
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(212, 175, 55, 0.45);
        }

        .btn-card-add:disabled, .btn-card-order-now:disabled {
            background: #240A0E;
            color: #7A5358;
            border-color: #381218;
            cursor: not-allowed;
            box-shadow: none;
            transform: none;
        }

        .btn-card-customize {
            background: rgba(35, 10, 15, 0.85);
            border: 1px solid var(--border-gold);
            color: var(--uphsd-gold-light);
            padding: 8px 9px;
            border-radius: var(--radius-sm);
            font-size: 0.76rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }

        .btn-card-customize:hover:not(:disabled) {
            background: var(--uphsd-maroon);
            color: #FFF;
            border-color: var(--uphsd-gold-bright);
        }

        /* 2. DIALOGUE STREAM (AI WAITER) VIEW */
        .chat-scroll {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .message-bubble {
            max-width: 85%;
            padding: 14px 18px;
            border-radius: var(--radius-md);
            line-height: 1.55;
            font-size: 0.92rem;
            animation: fadeIn 0.2s ease-in;
            box-shadow: var(--shadow-card);
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message-user {
            align-self: flex-end;
            background: linear-gradient(135deg, #6B0F1A 0%, #88151B 100%);
            color: #FFFFFF;
            border-bottom-right-radius: 2px;
            border: 1px solid var(--uphsd-gold);
            box-shadow: 0 4px 14px rgba(123, 17, 19, 0.4);
        }

        .message-assistant {
            align-self: flex-start;
            background: rgba(28, 8, 12, 0.92);
            color: var(--text-primary);
            border-bottom-left-radius: 2px;
            border: 1px solid var(--border-gold);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
        }

        .assistant-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 6px;
            font-family: var(--font-heading);
            font-size: 0.78rem;
            color: var(--uphsd-gold-bright);
            font-weight: 700;
            letter-spacing: 0.04em;
        }

        .tool-chip {
            display: inline-block;
            background: #2D0A0F;
            color: var(--uphsd-gold-bright);
            font-size: 0.72rem;
            padding: 3px 10px;
            border-radius: 4px;
            margin-top: 6px;
            border: 1px solid rgba(212, 175, 55, 0.35);
            font-family: var(--font-mono);
        }

        .thinking-dropdown {
            margin-top: 8px;
            font-size: 0.75rem;
            color: var(--text-muted);
            border-top: 1px dashed var(--border-subtle);
            padding-top: 6px;
        }

        .thinking-content {
            font-family: var(--font-mono);
            white-space: pre-wrap;
            max-height: 100px;
            overflow-y: auto;
            background: #0E0305;
            border: 1px solid var(--border-subtle);
            padding: 8px;
            border-radius: 6px;
            margin-top: 4px;
            color: var(--text-secondary);
        }

        /* Quick Suggestions Carousel */
        .quick-actions {
            display: flex;
            gap: 8px;
            padding: 8px 20px;
            background: #140406;
            border-top: 1px solid var(--border-subtle);
            overflow-x: auto;
            scrollbar-width: none;
        }

        .quick-actions::-webkit-scrollbar {
            display: none;
        }

        .quick-pill {
            background: var(--surface-card);
            border: 1px solid var(--border-subtle);
            color: var(--text-secondary);
            font-size: 0.75rem;
            font-weight: 500;
            padding: 5px 14px;
            border-radius: var(--radius-pill);
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.2s;
            user-select: none;
        }

        .quick-pill:hover {
            color: #FFFFFF;
            border-color: var(--uphsd-gold);
            background: var(--surface-card-hover);
            transform: translateY(-1px);
        }

        /* Input Controls */
        .chat-input-bar {
            padding: 12px 20px;
            background: linear-gradient(180deg, #160507 0%, #0E0305 100%);
            border-top: 1px solid var(--border-gold);
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .voice-btn {
            background: var(--surface-card);
            border: 1px solid var(--uphsd-gold);
            color: var(--uphsd-gold-bright);
            width: 44px;
            height: 44px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            font-size: 1.15rem;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
            flex-shrink: 0;
        }

        .voice-btn:hover {
            background: var(--surface-card-hover);
            transform: scale(1.05);
            box-shadow: 0 0 14px var(--uphsd-gold-glow);
        }

        .voice-btn.listening {
            background: #DC2626;
            color: #FFFFFF;
            border-color: #EF4444;
            animation: pulseListening 1.2s infinite;
        }

        @keyframes pulseListening {
            0% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.7); }
            70% { box-shadow: 0 0 0 10px rgba(220, 38, 38, 0); }
            100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0); }
        }

        .text-input {
            flex: 1;
            background: #0D0304;
            border: 1px solid var(--border-subtle);
            color: var(--text-primary);
            padding: 11px 16px;
            border-radius: var(--radius-sm);
            font-size: 0.92rem;
            font-family: var(--font-ui);
            outline: none;
            transition: border-color 0.2s, box-shadow 0.2s;
        }

        .text-input:focus {
            border-color: var(--uphsd-gold);
            box-shadow: 0 0 0 3px rgba(212, 175, 55, 0.2);
            background: #140507;
        }

        .send-btn {
            background: linear-gradient(135deg, var(--uphsd-gold-bright) 0%, var(--uphsd-gold) 100%);
            border: 1px solid var(--uphsd-gold-bright);
            color: var(--uphsd-maroon-dark);
            padding: 11px 22px;
            border-radius: var(--radius-sm);
            font-size: 0.88rem;
            font-weight: 800;
            letter-spacing: 0.02em;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 2px 8px rgba(212, 175, 55, 0.3);
            flex-shrink: 0;
        }

        .send-btn:hover {
            filter: brightness(1.12);
            transform: translateY(-1px);
        }

        /* RIGHT PANEL: REAL-TIME ORDER CART */
        .right-panel {
            background: #0E0305;
            border-left: 1px solid var(--border-subtle);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .panel-header {
            padding: 12px 20px;
            background: linear-gradient(180deg, #180608 0%, #120406 100%);
            border-bottom: 1px solid var(--border-gold);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .panel-title {
            font-family: var(--font-heading);
            font-size: 0.9rem;
            font-weight: 700;
            color: var(--uphsd-gold-bright);
            letter-spacing: 0.04em;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .cart-items-container {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .cart-card {
            background: linear-gradient(145deg, rgba(28, 8, 12, 0.9) 0%, rgba(20, 5, 8, 0.95) 100%);
            border: 1px solid var(--border-gold);
            border-radius: var(--radius-md);
            padding: 12px 14px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            transition: all 0.2s;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
        }

        .cart-card:hover {
            border-color: var(--uphsd-gold-bright);
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(212, 175, 55, 0.2);
        }

        .card-row-top {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 8px;
        }

        .item-title {
            font-weight: 700;
            font-size: 0.92rem;
            color: #FFFFFF;
            line-height: 1.3;
        }

        .item-price {
            font-family: var(--font-heading);
            font-weight: 800;
            color: var(--uphsd-gold-bright);
            font-size: 0.95rem;
            white-space: nowrap;
        }

        .customization-badge {
            background: rgba(59, 10, 14, 0.85);
            color: var(--uphsd-gold-light);
            border: 1px solid rgba(212, 175, 55, 0.3);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.72rem;
            font-style: italic;
            display: inline-block;
            margin-top: 4px;
        }

        .card-controls {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-top: 4px;
        }

        .qty-controls {
            display: flex;
            align-items: center;
            gap: 8px;
            background: #0A0204;
            padding: 3px 8px;
            border-radius: 6px;
            border: 1px solid var(--border-gold);
        }

        .qty-btn {
            background: var(--surface-card);
            color: var(--uphsd-gold-bright);
            border: 1px solid var(--border-subtle);
            width: 24px;
            height: 24px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: bold;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.15s;
        }

        .qty-btn:hover {
            background: var(--uphsd-maroon);
            color: #FFFFFF;
            border-color: var(--uphsd-gold);
        }

        .qty-label {
            font-size: 0.85rem;
            font-weight: 800;
            min-width: 18px;
            text-align: center;
            color: #FFFFFF;
        }

        .remove-btn {
            background: transparent;
            border: none;
            color: #EF4444;
            font-size: 0.75rem;
            font-weight: 600;
            cursor: pointer;
            text-decoration: underline;
            transition: color 0.15s;
            display: inline-flex;
            align-items: center;
            gap: 3px;
        }

        .remove-btn:hover {
            color: #F87171;
        }

        /* Cart Empty State */
        .empty-cart-state {
            margin: auto;
            text-align: center;
            padding: 40px 20px;
            color: var(--text-muted);
        }

        /* Bottom Bar: Checkout & Totals */
        .bottom-bar {
            background: linear-gradient(180deg, #160507 0%, #0E0305 100%);
            border-top: 1px solid var(--border-gold);
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .cart-totals-breakdown {
            display: flex;
            flex-direction: column;
            gap: 5px;
            font-size: 0.85rem;
            color: var(--text-secondary);
        }

        .totals-row {
            display: flex;
            justify-content: space-between;
        }

        .grand-total-row {
            font-size: 1.15rem;
            font-weight: 900;
            color: #FFFFFF;
            border-top: 1px solid var(--border-gold);
            padding-top: 8px;
            margin-top: 4px;
        }

        .confirm-btn {
            background: linear-gradient(135deg, var(--uphsd-gold-bright) 0%, var(--uphsd-gold) 50%, var(--uphsd-gold-deep) 100%);
            color: var(--uphsd-maroon-dark);
            border: 1px solid var(--uphsd-gold-bright);
            padding: 14px;
            border-radius: var(--radius-sm);
            font-family: var(--font-heading);
            font-size: 0.95rem;
            font-weight: 900;
            letter-spacing: 0.05em;
            cursor: pointer;
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            box-shadow: 0 4px 16px rgba(212, 175, 55, 0.4);
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .confirm-btn.ready-to-order {
            animation: pulseGlow 1.8s infinite;
        }

        @keyframes pulseGlow {
            0%, 100% { box-shadow: 0 4px 16px rgba(212, 175, 55, 0.4); }
            50% { box-shadow: 0 6px 26px rgba(212, 175, 55, 0.75), 0 0 12px #FFFFFF; }
        }

        .confirm-btn:hover:not(:disabled) {
            filter: brightness(1.15);
            transform: translateY(-2px);
            box-shadow: 0 6px 22px rgba(212, 175, 55, 0.6);
        }

        .confirm-btn:disabled {
            background: #240A0E;
            color: #6B494E;
            border-color: #381218;
            cursor: not-allowed;
            box-shadow: none;
            transform: none;
            animation: none;
        }

        /* CUSTOMIZATION MODAL */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(0, 0, 0, 0.85);
            backdrop-filter: blur(8px);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 100;
            padding: 20px;
        }

        .modal-overlay.show {
            display: flex;
        }

        .customize-dialog {
            background: linear-gradient(145deg, #1C070B 0%, #120305 100%);
            border: 2px solid var(--uphsd-gold);
            border-radius: var(--radius-lg);
            width: 100%;
            max-width: 480px;
            padding: 24px;
            color: var(--text-primary);
            box-shadow: 0 25px 60px rgba(0, 0, 0, 0.9), 0 0 25px var(--uphsd-gold-glow);
            animation: modalPop 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        @keyframes modalPop {
            from { transform: scale(0.92); opacity: 0; }
            to { transform: scale(1); opacity: 1; }
        }

        .customize-dialog-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 1px solid var(--border-gold);
            padding-bottom: 12px;
        }

        .dialog-title {
            font-size: 1.15rem;
            font-weight: 800;
            color: #FFFFFF;
        }

        .dialog-price {
            font-family: var(--font-heading);
            font-weight: 800;
            color: var(--uphsd-gold-bright);
            font-size: 1.1rem;
        }

        .dialog-close-x {
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 1.2rem;
            cursor: pointer;
            padding: 4px;
            transition: color 0.15s;
        }

        .dialog-close-x:hover {
            color: #FFFFFF;
        }

        .custom-options-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .custom-options-title {
            font-size: 0.8rem;
            font-weight: 700;
            color: var(--uphsd-gold-light);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .custom-options-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }

        .custom-tag-btn {
            background: rgba(30, 8, 12, 0.8);
            border: 1px solid var(--border-subtle);
            color: var(--text-secondary);
            padding: 8px 12px;
            border-radius: var(--radius-sm);
            font-size: 0.78rem;
            font-weight: 600;
            cursor: pointer;
            text-align: left;
            transition: all 0.15s;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .custom-tag-btn:hover {
            border-color: var(--uphsd-gold);
            color: #FFFFFF;
            background: rgba(45, 12, 18, 0.9);
        }

        .custom-tag-btn.active {
            background: var(--uphsd-maroon);
            border-color: var(--uphsd-gold);
            color: var(--uphsd-gold-bright);
            font-weight: 700;
            box-shadow: 0 2px 8px rgba(212, 175, 55, 0.25);
        }

        .dialog-qty-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(14, 4, 6, 0.85);
            border: 1px solid var(--border-subtle);
            padding: 10px 16px;
            border-radius: var(--radius-md);
        }

        .dialog-notes-input {
            width: 100%;
            background: #0E0305;
            border: 1px solid var(--border-subtle);
            color: #FFFFFF;
            padding: 10px 14px;
            border-radius: var(--radius-sm);
            font-family: var(--font-ui);
            font-size: 0.85rem;
            outline: none;
            transition: border-color 0.2s;
        }

        .dialog-notes-input:focus {
            border-color: var(--uphsd-gold);
        }

        .modal-action-buttons {
            display: flex;
            gap: 10px;
        }

        /* Modal Overlay for Receipt */
        .receipt-card {
            background: #FCFBF7;
            color: #1A0507;
            width: 90%;
            max-width: 500px;
            border-radius: var(--radius-md);
            border: 2px solid var(--uphsd-gold);
            padding: 24px;
            box-shadow: 0 24px 60px rgba(0, 0, 0, 0.8), 0 0 20px var(--uphsd-gold-glow);
            animation: modalPop 0.25s ease-out;
            font-family: var(--font-mono);
        }

        .receipt-seal-watermark {
            display: flex;
            justify-content: center;
            margin-bottom: 8px;
        }

        .receipt-header {
            text-align: center;
            border-bottom: 2px dashed #B8860B;
            padding-bottom: 12px;
            margin-bottom: 12px;
        }

        .receipt-header h2 {
            font-family: var(--font-heading);
            font-size: 1.15rem;
            font-weight: 900;
            color: var(--uphsd-maroon);
            letter-spacing: 0.04em;
        }

        .receipt-header p {
            font-size: 0.78rem;
            color: #4A070B;
            font-weight: 600;
        }

        .receipt-lines {
            display: flex;
            flex-direction: column;
            gap: 6px;
            margin-bottom: 12px;
            font-size: 0.85rem;
        }

        .receipt-line-item {
            display: flex;
            justify-content: space-between;
        }

        .receipt-footer {
            border-top: 2px dashed #B8860B;
            padding-top: 12px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .receipt-actions {
            display: flex;
            gap: 10px;
            margin-top: 14px;
        }

        .receipt-btn-action {
            flex: 1;
            padding: 10px;
            border-radius: 6px;
            font-weight: 700;
            font-size: 0.82rem;
            cursor: pointer;
            border: none;
            transition: all 0.15s;
        }

        .btn-print {
            background: var(--uphsd-maroon);
            color: #FFFFFF;
            border: 1px solid var(--uphsd-maroon-dark);
        }

        .btn-print:hover {
            background: var(--uphsd-maroon-light);
        }

        .btn-download {
            background: #E2D4CF;
            color: #380508;
            border: 1px solid #B8860B;
        }

        .btn-download:hover {
            background: #D4AF37;
            color: #FFFFFF;
        }

        .modal-close-btn {
            background: linear-gradient(135deg, var(--uphsd-maroon) 0%, #42070A 100%);
            color: #FFFFFF;
            border: 1px solid var(--uphsd-gold);
            padding: 12px;
            border-radius: 6px;
            font-family: var(--font-heading);
            font-weight: 800;
            letter-spacing: 0.04em;
            margin-top: 10px;
            cursor: pointer;
            width: 100%;
            transition: filter 0.2s;
        }

        .modal-close-btn:hover {
            filter: brightness(1.15);
        }

        /* Floating Toast Notification */
        .toast-notification {
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: linear-gradient(135deg, #2D080D 0%, #150306 100%);
            border: 1px solid var(--uphsd-gold);
            color: #FFFFFF;
            padding: 12px 20px;
            border-radius: var(--radius-md);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.8), 0 0 16px var(--uphsd-gold-glow);
            font-size: 0.86rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
            z-index: 200;
            transform: translateY(100px);
            opacity: 0;
            transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
            pointer-events: none;
        }

        .toast-notification.show {
            transform: translateY(0);
            opacity: 1;
            pointer-events: auto;
        }

        /* Print styles */
        @media print {
            body * {
                visibility: hidden;
            }
            #receiptModal, #receiptModal * {
                visibility: visible;
            }
            #receiptModal {
                position: absolute;
                left: 0;
                top: 0;
                width: 100%;
                background: white;
            }
            .receipt-actions, .modal-close-btn {
                display: none !important;
            }
        }
    </style>
</head>
<body>

    <!-- Top Institutional Utility Ribbon -->
    <div class="uphsd-top-ribbon">
        <div class="ribbon-left">
            <span class="ribbon-motto">★ Character Building is Nation Building</span>
            <span class="ribbon-campus">Las Piñas Campus • College of Computer Studies • AI Lab</span>
        </div>
        <div class="ribbon-right">
            <span class="live-clock" id="ribbonClock">--:--:--</span>
            <div class="system-status-indicator">
                <span class="status-dot"></span>
                <span>SQLite & Local Qwen Online</span>
            </div>
        </div>
    </div>

    <!-- Official Institutional Header -->
    <header>
        <div class="brand-container" onclick="switchView('menu')" title="Go to Visual Menu">
            <!-- Authentic University of Perpetual Help Cameo Seal SVG -->
            <svg class="brand-seal" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="50" cy="50" r="48" fill="#4A070B" stroke="#D4AF37" stroke-width="3"/>
                <circle cx="50" cy="50" r="42" fill="#6B0F1A" stroke="#F5B041" stroke-width="1.5" stroke-dasharray="3 2"/>
                <path d="M25 65 C20 50, 23 35, 34 24 C29 35, 31 48, 38 56 Z" fill="#D4AF37" opacity="0.95"/>
                <path d="M75 65 C80 50, 77 35, 66 24 C71 35, 69 48, 62 56 Z" fill="#D4AF37" opacity="0.95"/>
                <path d="M34 32 L66 32 C66 54, 50 70, 50 74 C50 70, 34 54, 34 32 Z" fill="#7B1113" stroke="#D4AF37" stroke-width="2"/>
                <path d="M50 36 L50 62 M42 45 L58 45" stroke="#F5B041" stroke-width="2.5" stroke-linecap="round"/>
                <polygon points="50,29 53,35 47,35" fill="#FFD700"/>
                <polygon points="50,16 52,21 57,21 53,24 55,29 50,26 45,29 47,24 43,21 48,21" fill="#F5B041"/>
            </svg>
            <div class="brand-title">
                <div class="university-name">University of Perpetual Help System DALTA</div>
                <h1>PERPETUAL BISTRO</h1>
                <p>Campus Dining Table-Side Tablet & Autonomous Waiter</p>
            </div>
        </div>

        <div class="header-meta">
            <!-- Interactive Table Selector Dropdown -->
            <div class="table-selector-wrap">
                <button class="table-select-btn" onclick="toggleTableDropdown(event)" id="tableDropdownBtn" title="Switch Dining Table">
                    <span>📍 Table #<span id="headerTableNo">1</span></span>
                    <span style="font-size: 0.65rem;">▼</span>
                </button>
                <div class="table-dropdown-menu" id="tableDropdownMenu">
                    <button class="table-opt-btn active" onclick="changeTable(1)">Table #1 (Active)</button>
                    <button class="table-opt-btn" onclick="changeTable(2)">Table #2</button>
                    <button class="table-opt-btn" onclick="changeTable(3)">Table #3</button>
                    <button class="table-opt-btn" onclick="changeTable(4)">Table #4</button>
                    <button class="table-opt-btn" onclick="changeTable(5)">Table #5</button>
                    <button class="table-opt-btn" onclick="changeTable(6)">Table #6</button>
                    <button class="table-opt-btn" onclick="changeTable(7)">Table #7</button>
                    <button class="table-opt-btn" onclick="changeTable(8)">Table #8</button>
                </div>
            </div>

            <div class="meta-pill" title="Active SQLite Session ID">
                🔑 Session: <span id="headerSessionId" style="font-family: var(--font-mono); font-size: 0.72rem;">---</span>
            </div>

            <!-- McDonald's Kiosk Language Selector -->
            <div class="lang-selector-group" role="radiogroup" aria-label="Select Kiosk Language">
                <button id="langFilipinoBtn" class="lang-btn active" onclick="setKioskLanguage('filipino')" title="Filipino (Taglish) Mode with Rosa">
                    <span>🇵🇭</span> Filipino
                </button>
                <button id="langEnglishBtn" class="lang-btn" onclick="setKioskLanguage('english')" title="English Mode with Jenny">
                    <span>🇺🇸</span> English
                </button>
            </div>

            <!-- Voice Controls & Audio Visualizer -->
            <div class="meta-pill" style="gap: 8px;">
                <button id="ttsToggleBtn" style="cursor: pointer; background: transparent; border: none; color: var(--uphsd-gold-bright); font-weight: 700;" onclick="toggleTtsAudio()">🔊 Voice: ON</button>
                <div class="audio-wave-container" id="audioWaveform" title="Speech Audio Activity">
                    <span class="wave-bar"></span>
                    <span class="wave-bar"></span>
                    <span class="wave-bar"></span>
                    <span class="wave-bar"></span>
                    <span class="wave-bar"></span>
                </div>
            </div>

            <button id="haltSpeechBtn" class="meta-pill" style="cursor: pointer; background: #DC2626; color: #FFFFFF; font-weight: bold; border: 1px solid #EF4444; display: none;" onclick="haltSpeech()">⏹️ HALT (Esc)</button>

            <!-- FSM State Badge -->
            <span id="fsmStateBadge" class="state-badge state-GREETING">
                <span class="state-dot-live"></span>
                <span id="fsmStateText">STATE_GREETING</span>
            </span>
        </div>
    </header>

    <!-- Top View Switcher Navigation Bar -->
    <div class="kiosk-nav-bar">
        <div class="nav-tabs-group">
            <button id="navViewMenu" class="nav-view-btn active" onclick="switchView('menu')">
                <span>🍽️ Visual Menu Catalog</span>
                <span class="nav-badge-count" id="menuCountBadge">17</span>
            </button>
            <button id="navViewChat" class="nav-view-btn" onclick="switchView('chat')">
                <span>💬 AI Waiter Dialogue</span>
            </button>
            <button id="navViewSplit" class="nav-view-btn" onclick="switchView('split')">
                <span>⚡ Split Kiosk View</span>
            </button>
        </div>

        <div style="display: flex; align-items: center; gap: 10px;">
            <span id="audioNotice" style="font-size: 0.73rem; color: var(--uphsd-gold-light);">Natural AI • Taglish (Rosa) • SQLite Bound</span>
            <button class="btn-reset-session" onclick="confirmResetSession()">
                <span>🔄 Restart Table</span>
            </button>
        </div>
    </div>

    <!-- Hidden Audio Player for Speech Synthesis -->
    <audio id="bistroAudioPlayer" style="display: none;"></audio>

    <!-- Main Workspace -->
    <div class="workspace">
        
        <!-- Left Panel: Multi-View Area -->
        <div class="left-panel" id="leftWorkspacePanel">

            <!-- VIEW 1: VISUAL MENU CATALOG -->
            <div id="paneMenu" class="view-content-pane active">
                <div class="menu-toolbar">
                    <div class="search-and-dietary-row">
                        <div class="menu-search-box">
                            <span class="search-icon">🔍</span>
                            <input type="text" id="menuSearchInput" class="menu-search-input" placeholder="Search menu dishes, ingredients (e.g. burger, truffle, fries)..." oninput="applyMenuFilters()">
                        </div>
                        <div class="dietary-filters-wrap">
                            <button class="diet-chip" data-diet="Dairy" onclick="toggleDietFilter('Dairy', this)">🥛 Dairy-Free</button>
                            <button class="diet-chip" data-diet="Gluten" onclick="toggleDietFilter('Gluten', this)">🌾 Gluten-Free</button>
                            <button class="diet-chip" data-diet="Nuts" onclick="toggleDietFilter('Nuts', this)">🥜 Nut-Free</button>
                            <button class="diet-chip" id="filterInStockOnly" onclick="toggleInStockFilter(this)">🌿 In-Stock Only</button>
                        </div>
                    </div>

                    <!-- Category Filter Tabs -->
                    <div class="category-tabs-bar" id="categoryTabs">
                        <button class="cat-pill active" onclick="selectMenuCategory('all', this)">🌟 All Specials</button>
                        <button class="cat-pill" onclick="selectMenuCategory('Burgers', this)">🍔 Burgers & Sandwiches</button>
                        <button class="cat-pill" onclick="selectMenuCategory('Pastas', this)">🍝 Pastas & Mains</button>
                        <button class="cat-pill" onclick="selectMenuCategory('Sides', this)">🍟 Sides & Appetizers</button>
                        <button class="cat-pill" onclick="selectMenuCategory('Beverages', this)">🥤 Beverages</button>
                        <button class="cat-pill" onclick="selectMenuCategory('Desserts', this)">🍨 Desserts</button>
                    </div>
                </div>

                <!-- Food Cards Grid -->
                <div class="menu-grid-scroll" id="menuGrid">
                    <!-- Food Cards Rendered In Real-Time by JS -->
                </div>
            </div>

            <!-- VIEW 2: AI WAITER DIALOGUE -->
            <div id="paneChat" class="view-content-pane">
                <div id="micAlertBanner" style="display: none; background: #7F1D1D; color: #FECACA; padding: 8px 16px; font-size: 0.8rem; border-bottom: 1px solid #DC2626;">
                    ⚠️ <strong>Microphone Notice:</strong> Browser speech recognition was blocked or unavailable. Please click the lock/settings icon in your address bar to allow microphone permissions, or type directly in the input box.
                </div>

                <div id="chatScroll" class="chat-scroll">
                    <!-- Dialogue Bubbles Rendered Here -->
                </div>

                <!-- Quick Suggestions Carousel -->
                <div class="quick-actions">
                    <span class="quick-pill" onclick="sendQuickPrompt('What do you personally recommend for lunch today?')">💬 What's Recommended?</span>
                    <span class="quick-pill" onclick="sendQuickPrompt('What burger options do you have available?')">🍔 Browse Burgers</span>
                    <span class="quick-pill" onclick="sendQuickPrompt('Does the Perpetual Classic Burger have dairy? I have mild lactose intolerance.')">🥛 Check Dairy Allergen</span>
                    <span class="quick-pill" onclick="sendQuickPrompt('Please add 1 Perpetual Classic Burger with no onions and extra cheese, and 1 Loaded Cheese Fries.')">🍟 Order Burger & Fries</span>
                    <span class="quick-pill" onclick="sendQuickPrompt('Can you add one Crispy Buffalo Chicken Tenders?')">🍗 Test Out-of-Stock</span>
                    <span class="quick-pill" onclick="sendQuickPrompt('What beverages do you have? Add 1 Iced Caramel Macchiato.')">☕ Order Drink</span>
                    <span class="quick-pill" onclick="sendQuickPrompt('Can I see my current tab and total bill?')">📋 Review Bill</span>
                    <span class="quick-pill" onclick="sendQuickPrompt('Everything looks great, please confirm and place my order.')">✅ Confirm Order</span>
                </div>

                <!-- Input Bar -->
                <div class="chat-input-bar">
                    <button id="voiceBtn" class="voice-btn" title="Click to Speak into Microphone" onclick="toggleVoice()">🎙️</button>
                    <span id="audioStatusText" style="font-size: 0.78rem; color: var(--text-muted); min-width: 120px; user-select: none;">🎙️ Mic: Ready</span>
                    <input id="textInput" class="text-input" type="text" placeholder="Type your order, dietary preference, or question..." onkeydown="handleKey(event)">
                    <button id="sendBtn" class="send-btn" onclick="sendMessage()">Send</button>
                </div>
            </div>

        </div>

        <!-- Right Panel: Real-Time Active Order Cart -->
        <div class="right-panel">
            <div class="panel-header">
                <div class="panel-title">
                    <span>🛒 Active Order Tab</span>
                </div>
                <div style="font-size: 0.78rem; font-weight: 700; color: var(--uphsd-gold-bright);" id="cartItemCount">
                    0 Items
                </div>
            </div>

            <div id="cartItemsContainer" class="cart-items-container">
                <div class="empty-cart-state">
                    <p style="font-size: 2.2rem; margin-bottom: 8px;">🍽️</p>
                    <p style="font-weight: 600; color: var(--text-secondary);">Your table tab is currently empty.</p>
                    <p style="font-size: 0.8rem; margin-top: 4px; color: var(--text-muted);">Click on any menu item or tap "⚡ Order Now" to place your order!</p>
                </div>
            </div>

            <!-- Bottom Bar: Checkout & Totals -->
            <div class="bottom-bar">
                <div class="cart-totals-breakdown">
                    <div class="totals-row">
                        <span>Subtotal:</span>
                        <span id="cartSubtotal" style="font-weight: 600;">₱0.00</span>
                    </div>
                    <div class="totals-row">
                        <span>12% Government VAT (Included):</span>
                        <span id="cartVat">₱0.00</span>
                    </div>
                    <div class="totals-row grand-total-row">
                        <span>TOTAL AMOUNT:</span>
                        <span id="cartGrandTotal" style="color: var(--uphsd-gold-bright);">₱0.00</span>
                    </div>
                </div>

                <button id="confirmOrderBtn" class="confirm-btn" onclick="triggerCheckout()" disabled>
                    <span id="confirmOrderBtnText">CONFIRM & PLACE ORDER</span>
                    <span>→</span>
                </button>
            </div>

        </div>

    </div>

    <!-- Interactive Dish Customization Modal -->
    <div id="customizeModal" class="modal-overlay">
        <div class="customize-dialog">
            <div class="customize-dialog-header">
                <div>
                    <div class="dialog-title" id="custItemName">Perpetual Classic Burger</div>
                    <div style="font-size: 0.75rem; color: var(--text-muted);" id="custItemCategory">Burgers & Sandwiches</div>
                </div>
                <div style="text-align: right;">
                    <div class="dialog-price" id="custItemPrice">₱150.00</div>
                    <button class="dialog-close-x" onclick="closeCustomizeModal()">✕</button>
                </div>
            </div>

            <p style="font-size: 0.82rem; color: var(--text-secondary); line-height: 1.4;" id="custItemDesc">
                Juicy beef patty with cheddar cheese, crisp lettuce, tomato, and house bistro sauce.
            </p>

            <div id="custAllergensNotice" class="allergen-pills-row">
                <!-- Injected allergen pills -->
            </div>

            <div class="dialog-qty-row">
                <span style="font-size: 0.85rem; font-weight: 700; color: #FFFFFF;">Order Quantity:</span>
                <div class="qty-controls">
                    <button class="qty-btn" onclick="adjustCustomQty(-1)">-</button>
                    <span class="qty-label" id="custItemQty">1</span>
                    <button class="qty-btn" onclick="adjustCustomQty(1)">+</button>
                </div>
            </div>

            <div class="custom-options-group">
                <span class="custom-options-title">Popular Modifications:</span>
                <div class="custom-options-grid">
                    <button class="custom-tag-btn" onclick="toggleCustomOption('No Onions', this)">🧅 No Onions</button>
                    <button class="custom-tag-btn" onclick="toggleCustomOption('Extra Cheese', this)">🧀 Extra Cheese</button>
                    <button class="custom-tag-btn" onclick="toggleCustomOption('Make it Spicy', this)">🌶️ Extra Spicy</button>
                    <button class="custom-tag-btn" onclick="toggleCustomOption('Less Ice', this)">🧊 Less Ice</button>
                    <button class="custom-tag-btn" onclick="toggleCustomOption('Sauce on Side', this)">🥣 Sauce on Side</button>
                    <button class="custom-tag-btn" onclick="toggleCustomOption('Extra Garlic Rice', this)">🍚 Extra Garlic Rice</button>
                </div>
            </div>

            <div>
                <label style="font-size: 0.78rem; font-weight: 700; color: var(--uphsd-gold-light); display: block; margin-bottom: 5px;">Special Kitchen Instructions / Allergies:</label>
                <input type="text" id="custSpecialNotes" class="dialog-notes-input" placeholder="e.g. Mild lactose intolerance, well-done, separate dip...">
            </div>

            <div class="modal-action-buttons">
                <button class="btn-card-order-now" style="padding: 12px; font-size: 0.9rem;" onclick="submitCustomizedItem(true)">
                    <span>⚡ Order Now (Instant Checkout)</span>
                </button>
                <button class="confirm-btn" style="flex: 1; padding: 12px; font-size: 0.88rem;" onclick="submitCustomizedItem(false)">
                    <span id="custAddBtnText">Add to Tab • ₱150.00</span>
                </button>
            </div>
        </div>
    </div>

    <!-- Official University of Perpetual Help Digital Receipt Modal -->
    <div id="receiptModal" class="modal-overlay">
        <div class="receipt-card">
            <div class="receipt-seal-watermark">
                <svg width="42" height="42" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="50" cy="50" r="48" fill="#4A070B" stroke="#D4AF37" stroke-width="3"/>
                    <path d="M34 32 L66 32 C66 54, 50 70, 50 74 C50 70, 34 54, 34 32 Z" fill="#7B1113" stroke="#D4AF37" stroke-width="2"/>
                    <path d="M50 36 L50 62 M42 45 L58 45" stroke="#F5B041" stroke-width="2.5" stroke-linecap="round"/>
                </svg>
            </div>
            <div class="receipt-header">
                <h2>UNIVERSITY OF PERPETUAL HELP SYSTEM DALTA</h2>
                <p>PERPETUAL BISTRO — CAMPUS DINING FACILITY</p>
                <p style="font-size: 0.72rem; color: #555; margin-top: 2px;">Las Piñas Campus • Alabang-Zapote Rd, Pamplona 3</p>
                <p style="font-size: 0.72rem; font-style: italic; color: #7B1113; margin-top: 3px;">"Character Building is Nation Building"</p>
                <p style="margin-top: 8px; font-size: 0.76rem; font-weight: 800; color: #1A0507;" id="receiptIdText">OFFICIAL RECEIPT #PB-1-XXXXXX</p>
                <p style="font-size: 0.72rem; color: #666;" id="receiptDateText"></p>
            </div>

            <div id="receiptItemsList" class="receipt-lines">
                <!-- Receipt Items Injected Here -->
            </div>

            <div class="receipt-footer">
                <div class="receipt-line-item">
                    <span>Subtotal:</span>
                    <span id="receiptSubtotal" style="font-weight: 600;">₱0.00</span>
                </div>
                <div class="receipt-line-item">
                    <span>12% VAT Breakdown:</span>
                    <span id="receiptVat">₱0.00</span>
                </div>
                <div class="receipt-line-item" style="font-weight: 900; font-size: 1.15rem; color: #7B1113; border-top: 2px solid #7B1113; padding-top: 6px;">
                    <span>TOTAL BILLED:</span>
                    <span id="receiptTotal">₱0.00</span>
                </div>
            </div>

            <div style="text-align: center; margin-top: 10px; font-size: 0.74rem; color: #475569;">
                Status: Verified & Committed to restaurant.db<br>
                Kitchen ticket dispatched. Maraming salamat po!
            </div>

            <div class="receipt-actions">
                <button class="receipt-btn-action btn-print" onclick="window.print()">🖨️ Print Receipt</button>
                <button class="receipt-btn-action btn-download" onclick="downloadReceiptTxt()">📥 Download (TXT)</button>
            </div>

            <button class="modal-close-btn" onclick="closeReceiptModal()">Start New Table Session</button>
        </div>
    </div>

    <!-- Floating Interactive Toast Notification -->
    <div id="appToast" class="toast-notification">
        <span id="toastIcon">✨</span>
        <span id="toastMessage">Item added to tab</span>
    </div>

    <script>
        let currentTableNo = 1;
        let isListening = false;
        let recognition = null;
        let ttsAudioEnabled = true;
        let currentLanguage = 'filipino';
        let currentReceiptData = null;
        let fullMenuList = [];
        let activeCategoryFilter = 'all';
        let activeDietFilters = new Set();
        let inStockOnlyFilter = false;
        let currentView = 'menu'; // 'menu', 'chat', 'split'

        // Modal customization state
        let customizingItem = null;
        let customQuantity = 1;
        let selectedOptions = new Set();

        // Live Clock
        function updateLiveClock() {
            const clockEl = document.getElementById('ribbonClock');
            if (clockEl) {
                const now = new Date();
                clockEl.innerText = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            }
        }
        setInterval(updateLiveClock, 1000);
        updateLiveClock();

        // Toast Feedback System
        function showToast(message, icon = '✨') {
            const toast = document.getElementById('appToast');
            const toastMsg = document.getElementById('toastMessage');
            const toastIco = document.getElementById('toastIcon');
            if (!toast) return;
            toastMsg.innerText = message;
            toastIco.innerText = icon;
            toast.classList.add('show');
            clearTimeout(window._toastTimer);
            window._toastTimer = setTimeout(() => {
                toast.classList.remove('show');
            }, 3500);
        }

        // View Navigation Switcher
        function switchView(viewName) {
            currentView = viewName;
            const btnMenu = document.getElementById('navViewMenu');
            const btnChat = document.getElementById('navViewChat');
            const btnSplit = document.getElementById('navViewSplit');

            const paneMenu = document.getElementById('paneMenu');
            const paneChat = document.getElementById('paneChat');
            const leftPanel = document.getElementById('leftWorkspacePanel');

            [btnMenu, btnChat, btnSplit].forEach(b => b.classList.remove('active'));

            if (viewName === 'menu') {
                btnMenu.classList.add('active');
                leftPanel.classList.remove('split-layout');
                paneMenu.classList.add('active');
                paneChat.classList.remove('active');
            } else if (viewName === 'chat') {
                btnChat.classList.add('active');
                leftPanel.classList.remove('split-layout');
                paneMenu.classList.remove('active');
                paneChat.classList.add('active');
            } else if (viewName === 'split') {
                btnSplit.classList.add('active');
                leftPanel.classList.add('split-layout');
                paneMenu.classList.add('active');
                paneChat.classList.add('active');
            }
        }

        // Table Selection Dropdown
        function toggleTableDropdown(e) {
            e.stopPropagation();
            const menu = document.getElementById('tableDropdownMenu');
            if (menu) menu.classList.toggle('show');
        }

        window.addEventListener('click', () => {
            const menu = document.getElementById('tableDropdownMenu');
            if (menu) menu.classList.remove('show');
        });

        async function changeTable(tableNum) {
            try {
                const res = await fetch('/api/table/switch', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({table_no: tableNum})
                });
                const data = await res.json();
                currentTableNo = data.table_no;
                document.getElementById('headerTableNo').innerText = data.table_no;
                document.getElementById('headerSessionId').innerText = data.session_id;
                updateFsmBadge(data.fsm_state);
                renderCart(data.cart);

                // Update dropdown active state
                const buttons = document.querySelectorAll('.table-opt-btn');
                buttons.forEach((btn, idx) => {
                    if (idx + 1 === tableNum) {
                        btn.classList.add('active');
                        btn.innerText = `Table #${tableNum} (Active)`;
                    } else {
                        btn.classList.remove('active');
                        btn.innerText = `Table #${idx + 1}`;
                    }
                });

                showToast(`Switched active session to Table #${tableNum}!`, '📍');
            } catch(e) {
                console.error("Failed to switch table:", e);
            }
        }

        // Menu Data & Rendering
        const DISH_EMOJIS = {
            'Burgers': '🍔',
            'Pastas': '🍝',
            'Sides': '🍟',
            'Beverages': '🥤',
            'Desserts': '🍰'
        };

        function getDishEmoji(item) {
            const name = item.name.toLowerCase();
            if (name.includes('coffee')) return '☕';
            if (name.includes('tea') || name.includes('calamansi')) return '🍹';
            if (name.includes('smoothie')) return '🥭';
            if (name.includes('cheesecake')) return '🧀';
            if (name.includes('chocolate') || name.includes('lava')) return '🍫';
            if (name.includes('salad') || name.includes('caesar')) return '🥗';
            if (name.includes('onion')) return '🧅';
            if (name.includes('tender') || name.includes('chicken')) return '🍗';
            if (name.includes('sandwich')) return '🥪';
            return DISH_EMOJIS[item.category] || '🍽️';
        }

        function formatAllergenBadges(allergenString) {
            if (!allergenString || allergenString.trim().toLowerCase() === 'none') {
                return '<span class="allergen-pill allergen-none">🌿 None</span>';
            }
            const parts = allergenString.split(',').map(s => s.trim());
            return parts.map(alg => {
                const lower = alg.toLowerCase();
                let cls = 'allergen-gluten';
                let icon = '🌾';
                if (lower.includes('dairy')) { cls = 'allergen-dairy'; icon = '🥛'; }
                else if (lower.includes('nuts') || lower.includes('peanut')) { cls = 'allergen-nuts'; icon = '🥜'; }
                else if (lower.includes('pork')) { cls = 'allergen-pork'; icon = '🥓'; }
                else if (lower.includes('egg')) { cls = 'allergen-egg'; icon = '🥚'; }
                else if (lower.includes('fish') || lower.includes('shellfish')) { cls = 'allergen-fish'; icon = '🦐'; }
                else if (lower.includes('beef')) { cls = 'allergen-beef'; icon = '🥩'; }
                return `<span class="allergen-pill ${cls}">${icon} ${alg}</span>`;
            }).join(' ');
        }

        async function loadMenu() {
            try {
                const res = await fetch('/api/menu');
                const data = await res.json();
                fullMenuList = data.items || [];
                const countBadge = document.getElementById('menuCountBadge');
                if (countBadge) countBadge.innerText = fullMenuList.length;
                renderMenuCards(fullMenuList);
            } catch(e) {
                console.error("Failed to load menu:", e);
            }
        }

        function renderMenuCards(items) {
            const container = document.getElementById('menuGrid');
            if (!container) return;

            if (items.length === 0) {
                container.innerHTML = `
                    <div style="grid-column: 1 / -1; text-align: center; padding: 40px 20px; color: var(--text-muted);">
                        <p style="font-size: 2.2rem; margin-bottom: 8px;">🔍</p>
                        <p style="font-weight: 700; color: #FFFFFF;">No menu items matched your filter criteria.</p>
                        <p style="font-size: 0.8rem; margin-top: 4px;">Try searching for other dishes or clearing dietary tags.</p>
                    </div>`;
                return;
            }

            container.innerHTML = items.map(it => {
                const isOutOfStock = !it.in_stock || it.stock_qty <= 0;
                const emoji = getDishEmoji(it);
                const allergenHtml = formatAllergenBadges(it.allergens);
                const safeName = it.name.replace(/'/g, "\\\\'");

                return `
                <div class="menu-item-card ${isOutOfStock ? 'out-of-stock' : ''}" id="card_${it.id}" onclick="handleCardClick('${safeName}', event)">
                    <div class="card-top-badges">
                        <span class="dish-cat-badge">${it.category}</span>
                        <span class="stock-indicator-badge ${isOutOfStock ? 'out-stock' : 'in-stock'}">
                            ${isOutOfStock ? '⚠️ Out of Stock' : `🌿 In Stock (${it.stock_qty})`}
                        </span>
                    </div>

                    <div class="dish-visual-header">
                        <div class="dish-icon-box">${emoji}</div>
                        <div class="dish-title-group">
                            <div class="dish-name">${it.name}</div>
                            <div class="dish-price">₱${it.price.toFixed(2)}</div>
                        </div>
                    </div>

                    <p class="dish-desc">${it.description || 'Specially crafted campus favorite at Perpetual Bistro.'}</p>

                    <div class="allergen-pills-row">
                        ${allergenHtml}
                    </div>

                    <div class="card-actions-row">
                        <button class="btn-card-order-now" onclick="event.stopPropagation(); instantPlaceOrder('${safeName}')" ${isOutOfStock ? 'disabled title="Dish is out of stock"' : ''} title="Instant Order & Place Now">
                            <span>⚡</span>
                            <span>Order Now</span>
                        </button>
                        <button class="btn-card-add" onclick="event.stopPropagation(); quickAddItem('${safeName}')" ${isOutOfStock ? 'disabled title="Dish is out of stock"' : ''} title="Add 1x to Active Tab">
                            <span>+</span>
                            <span>Add</span>
                        </button>
                        <button class="btn-card-customize" onclick="event.stopPropagation(); openCustomizeModal('${safeName}')" ${isOutOfStock ? 'disabled' : ''} title="Customize Dish Options">
                            <span>⚙️</span>
                        </button>
                    </div>
                </div>`;
            }).join('');
        }

        // Entire Card Click Handler: Clicking anywhere on the card adds it to the order!
        function handleCardClick(itemName, event) {
            const item = fullMenuList.find(i => i.name.toLowerCase() === itemName.toLowerCase());
            if (!item) return;

            if (!item.in_stock || item.stock_qty <= 0) {
                showToast(`Sorry, ${item.name} is currently out of stock!`, '⚠️');
                return;
            }

            // Animate card highlight
            const cardEl = event.currentTarget;
            if (cardEl) {
                cardEl.classList.add('card-pulse');
                setTimeout(() => cardEl.classList.remove('card-pulse'), 500);
            }

            // Add item to active order tab
            quickAddItem(itemName);
        }

        function selectMenuCategory(cat, el) {
            activeCategoryFilter = cat;
            const pills = document.querySelectorAll('.category-tabs-bar .cat-pill');
            pills.forEach(p => p.classList.remove('active'));
            if (el) el.classList.add('active');
            applyMenuFilters();
        }

        function toggleDietFilter(diet, el) {
            if (activeDietFilters.has(diet)) {
                activeDietFilters.delete(diet);
                el.classList.remove('active');
            } else {
                activeDietFilters.add(diet);
                el.classList.add('active');
            }
            applyMenuFilters();
        }

        function toggleInStockFilter(el) {
            inStockOnlyFilter = !inStockOnlyFilter;
            el.classList.toggle('active', inStockOnlyFilter);
            applyMenuFilters();
        }

        function applyMenuFilters() {
            const query = (document.getElementById('menuSearchInput').value || '').toLowerCase().trim();
            let filtered = fullMenuList.filter(item => {
                // Category filter
                if (activeCategoryFilter !== 'all' && item.category.toLowerCase() !== activeCategoryFilter.toLowerCase()) {
                    return false;
                }
                // In-Stock Only filter
                if (inStockOnlyFilter && (!item.in_stock || item.stock_qty <= 0)) {
                    return false;
                }
                // Dietary/Allergen exclusions: if filter is checked, dish must NOT contain that allergen
                for (let diet of activeDietFilters) {
                    if (item.allergens && item.allergens.toLowerCase().includes(diet.toLowerCase())) {
                        return false;
                    }
                }
                // Text search query
                if (query) {
                    const matchName = item.name.toLowerCase().includes(query);
                    const matchDesc = (item.description || '').toLowerCase().includes(query);
                    const matchCat = item.category.toLowerCase().includes(query);
                    if (!matchName && !matchDesc && !matchCat) return false;
                }
                return true;
            });

            renderMenuCards(filtered);
        }

        // Quick Add to Order
        async function quickAddItem(itemName) {
            try {
                const res = await fetch('/api/cart/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ item_name: itemName, qty: 1, instructions: "" })
                });
                const data = await res.json();
                if (data.result && data.result.status === 'out_of_stock') {
                    showToast(data.result.message || 'Item is currently out of stock!', '⚠️');
                    return;
                }
                updateFsmBadge(data.fsm_state);
                renderCart(data.cart);
                showToast(`Added 1x ${itemName} to your tab! Click 'CONFIRM & PLACE ORDER' to checkout.`, '✨');
            } catch(e) {
                console.error("Quick add error:", e);
                showToast("Failed to add item to tab", '❌');
            }
        }

        // 1-Click Instant Place Order
        async function instantPlaceOrder(itemName) {
            try {
                showToast(`Placing order for ${itemName}...`, '⚡');

                // 1. Add item to order
                const addRes = await fetch('/api/cart/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ item_name: itemName, qty: 1, instructions: "" })
                });
                const addData = await addRes.json();
                if (addData.result && addData.result.status === 'out_of_stock') {
                    showToast(addData.result.message || 'Item is currently out of stock!', '⚠️');
                    return;
                }
                updateFsmBadge(addData.fsm_state);
                renderCart(addData.cart);

                // 2. Immediately trigger checkout and place order
                const confRes = await fetch('/api/confirm', { method: 'POST' });
                const confData = await confRes.json();
                updateFsmBadge(confData.fsm_state);
                renderCart(confData.cart);
                showReceipt(confData.receipt);
                showToast(`Order placed successfully for ${itemName}! 🎉`, '🧾');
            } catch(e) {
                console.error("Instant order error:", e);
                showToast("Error placing order: " + e, '❌');
            }
        }

        // Customization Modal Logic
        function openCustomizeModal(itemName) {
            const item = fullMenuList.find(i => i.name.toLowerCase() === itemName.toLowerCase());
            if (!item) return;
            customizingItem = item;
            customQuantity = 1;
            selectedOptions.clear();

            document.getElementById('custItemName').innerText = item.name;
            document.getElementById('custItemCategory').innerText = item.category;
            document.getElementById('custItemPrice').innerText = `₱${item.price.toFixed(2)}`;
            document.getElementById('custItemDesc').innerText = item.description || 'Prepared fresh upon order.';
            document.getElementById('custItemQty').innerText = '1';
            document.getElementById('custSpecialNotes').value = '';

            // Reset option buttons
            const optionBtns = document.querySelectorAll('.custom-tag-btn');
            optionBtns.forEach(btn => btn.classList.remove('active'));

            // Set allergens notice
            const algContainer = document.getElementById('custAllergensNotice');
            algContainer.innerHTML = formatAllergenBadges(item.allergens);

            updateCustAddButton();
            document.getElementById('customizeModal').classList.add('show');
        }

        function closeCustomizeModal() {
            document.getElementById('customizeModal').classList.remove('show');
            customizingItem = null;
        }

        function adjustCustomQty(delta) {
            if (!customizingItem) return;
            customQuantity = Math.max(1, Math.min(customizingItem.stock_qty || 99, customQuantity + delta));
            document.getElementById('custItemQty').innerText = customQuantity;
            updateCustAddButton();
        }

        function toggleCustomOption(opt, el) {
            if (selectedOptions.has(opt)) {
                selectedOptions.delete(opt);
                el.classList.remove('active');
            } else {
                selectedOptions.add(opt);
                el.classList.add('active');
            }
            updateCustAddButton();
        }

        function updateCustAddButton() {
            if (!customizingItem) return;
            const total = customizingItem.price * customQuantity;
            document.getElementById('custAddBtnText').innerText = `Add to Tab • ₱${total.toFixed(2)}`;
        }

        async function submitCustomizedItem(instantCheckout = false) {
            if (!customizingItem) return;
            const notesInput = document.getElementById('custSpecialNotes').value.trim();
            const allInstructions = [...selectedOptions];
            if (notesInput) allInstructions.push(notesInput);
            const instructionsStr = allInstructions.join(', ');
            const dishName = customizingItem.name;

            try {
                const res = await fetch('/api/cart/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        item_name: dishName,
                        qty: customQuantity,
                        instructions: instructionsStr
                    })
                });
                const data = await res.json();
                if (data.result && data.result.status === 'out_of_stock') {
                    showToast(data.result.message || 'Item is out of stock!', '⚠️');
                    return;
                }
                updateFsmBadge(data.fsm_state);
                renderCart(data.cart);
                closeCustomizeModal();

                if (instantCheckout) {
                    // Instantly trigger confirm order
                    const confRes = await fetch('/api/confirm', { method: 'POST' });
                    const confData = await confRes.json();
                    updateFsmBadge(confData.fsm_state);
                    renderCart(confData.cart);
                    showReceipt(confData.receipt);
                    showToast(`Order placed for ${customQuantity}x ${dishName}! 🎉`, '🧾');
                } else {
                    showToast(`Added ${customQuantity}x ${dishName} with customizations!`, '✨');
                }
            } catch(e) {
                console.error("Customize add error:", e);
                showToast("Failed to add customized item", '❌');
            }
        }

        // Language Selector
        async function setKioskLanguage(lang, announce = true) {
            currentLanguage = lang.toLowerCase().trim();
            const filBtn = document.getElementById('langFilipinoBtn');
            const engBtn = document.getElementById('langEnglishBtn');
            const chatInput = document.getElementById('textInput');
            const voiceNotice = document.getElementById('audioNotice');

            if (currentLanguage === 'english') {
                if (filBtn) filBtn.classList.remove('active');
                if (engBtn) engBtn.classList.add('active');
                if (chatInput) chatInput.placeholder = "Type your order, dietary preference, or question...";
                if (voiceNotice) voiceNotice.innerHTML = "Natural AI • English (Jenny) • SQLite Bound";
                if (recognition) recognition.lang = 'en-US';
            } else {
                if (engBtn) engBtn.classList.remove('active');
                if (filBtn) filBtn.classList.add('active');
                if (chatInput) chatInput.placeholder = "Mag-order o magtanong sa Taglish... (e.g., 'Anong burger meron kayo?')";
                if (voiceNotice) voiceNotice.innerHTML = "Natural AI • Taglish (Rosa) • SQLite Bound";
                if (recognition) recognition.lang = 'fil-PH';
            }

            try {
                const res = await fetch('/api/language', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ language: currentLanguage })
                });
                const data = await res.json();
                if (announce && data.greeting) {
                    appendMessage('BistroBot', data.greeting, null, null, data.speech_text);
                }
            } catch (err) {
                console.error("Failed to switch language:", err);
            }
        }

        // Initialize Web Speech API if supported
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognition = new SpeechRec();
            recognition.continuous = false;
            recognition.interimResults = false;
            recognition.lang = 'fil-PH';

            recognition.onstart = () => {
                const statusEl = document.getElementById('audioStatusText');
                if (statusEl) {
                    statusEl.innerText = '🔴 Listening...';
                    statusEl.style.color = '#ef4444';
                }
            };

            recognition.onspeechstart = () => {
                const statusEl = document.getElementById('audioStatusText');
                if (statusEl) {
                    statusEl.innerText = '🎙️ Hearing voice...';
                    statusEl.style.color = '#f59e0b';
                }
            };

            recognition.onresult = (event) => {
                const statusEl = document.getElementById('audioStatusText');
                if (statusEl) {
                    statusEl.innerText = '⚙️ Transcribing...';
                    statusEl.style.color = '#3b82f6';
                }
                const transcript = event.results[0][0].transcript;
                document.getElementById('textInput').value = transcript;
                toggleVoice(false);
                sendMessage();
            };

            recognition.onerror = (e) => {
                console.error("Speech error:", e);
                const banner = document.getElementById('micAlertBanner');
                if (banner) banner.style.display = 'block';
                const statusEl = document.getElementById('audioStatusText');
                if (statusEl) {
                    statusEl.innerText = '⚠️ Mic Error';
                    statusEl.style.color = '#f87171';
                }
                toggleVoice(false);
            };

            recognition.onend = () => {
                toggleVoice(false);
            };
        } else {
            console.warn("Web Speech API not natively supported in this browser environment.");
        }

        function toggleVoice(forceState) {
            const btn = document.getElementById('voiceBtn');
            const statusEl = document.getElementById('audioStatusText');
            if (!recognition) {
                const banner = document.getElementById('micAlertBanner');
                if (banner) banner.style.display = 'block';
                if (statusEl) {
                    statusEl.innerText = '❌ Mic Unsupported';
                    statusEl.style.color = '#ef4444';
                }
                alert("Web Speech API is not supported in this browser or permission was denied. Please use keyboard text input.");
                return;
            }

            if (forceState !== undefined) {
                isListening = forceState;
            } else {
                isListening = !isListening;
            }

            const waveform = document.getElementById('audioWaveform');
            if (isListening) {
                btn.classList.add('listening');
                if (waveform) waveform.classList.add('speaking');
                btn.title = "Listening to speech (Click to cancel)...";
                if (statusEl) {
                    statusEl.innerText = '🔴 Listening...';
                    statusEl.style.color = '#EF4444';
                }
                try { recognition.start(); } catch(e){}
            } else {
                btn.classList.remove('listening');
                if (waveform) waveform.classList.remove('speaking');
                btn.title = "Click to Speak into Microphone";
                if (statusEl) {
                    statusEl.innerText = '🎙️ Mic: Ready';
                    statusEl.style.color = 'var(--text-muted)';
                }
                try { recognition.stop(); } catch(e){}
            }
        }

        function toggleTtsAudio() {
            ttsAudioEnabled = !ttsAudioEnabled;
            const btn = document.getElementById('ttsToggleBtn');
            if (!ttsAudioEnabled) {
                haltSpeech();
                btn.innerText = "🔇 Voice: MUTED";
                btn.style.color = "#9E8083";
            } else {
                btn.innerText = "🔊 Voice: ON";
                btn.style.color = "var(--uphsd-gold-bright)";
            }
        }

        function haltSpeech() {
            const player = document.getElementById('bistroAudioPlayer');
            if (player) {
                player.pause();
                player.currentTime = 0;
            }
            if ('speechSynthesis' in window) {
                window.speechSynthesis.cancel();
            }
            const haltBtn = document.getElementById('haltSpeechBtn');
            if (haltBtn) {
                haltBtn.style.display = 'none';
            }
            const waveform = document.getElementById('audioWaveform');
            if (waveform) {
                waveform.classList.remove('speaking');
            }
        }

        async function speakText(text) {
            if (!ttsAudioEnabled || !text) return;
            haltSpeech();

            const haltBtn = document.getElementById('haltSpeechBtn');
            if (haltBtn) haltBtn.style.display = 'inline-block';
            const waveform = document.getElementById('audioWaveform');
            if (waveform) waveform.classList.add('speaking');

            const selectedVoice = (currentLanguage === 'english') ? 'en-US-JennyNeural' : 'en-PH-RosaNeural';

            try {
                const res = await fetch('/api/tts', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        text: text,
                        voice: selectedVoice,
                        language: currentLanguage
                    })
                });
                if (!res.ok) throw new Error("TTS endpoint returned " + res.status);
                const blob = await res.blob();
                if (blob.size === 0) {
                    if (haltBtn) haltBtn.style.display = 'none';
                    if (waveform) waveform.classList.remove('speaking');
                    return;
                }
                const audioUrl = URL.createObjectURL(blob);
                const player = document.getElementById('bistroAudioPlayer');
                player.src = audioUrl;
                player.onended = () => { 
                    if (haltBtn) haltBtn.style.display = 'none'; 
                    if (waveform) waveform.classList.remove('speaking');
                };
                player.onerror = () => { 
                    if (haltBtn) haltBtn.style.display = 'none'; 
                    if (waveform) waveform.classList.remove('speaking');
                };
                await player.play();
            } catch (err) {
                console.warn("Natural neural voice playback failed, falling back to local speech synthesis:", err);
                speakFallbackLocal(text);
            }
        }

        function speakFallbackLocal(text) {
            if ('speechSynthesis' in window) {
                window.speechSynthesis.cancel();
                let cleanSpeech = (text || '')
                    .replace(/Mabuhay/gi, 'Mabuhigh')
                    .replace(/₱\\s*(\\d+(?:\\.\\d+)?)/g, '$1 pesos')
                    .replace(/₱/g, ' pesos');

                if (currentLanguage === 'filipino') {
                    cleanSpeech = cleanSpeech
                        .replace(/\\bmo\\b/gi, 'moh')
                        .replace(/\\bba\\b/gi, 'bah')
                        .replace(/\\bpo\\b/gi, 'poh')
                        .replace(/\\bko\\b/gi, 'koh')
                        .replace(/\\bng\\b/gi, 'nang')
                        .replace(/\\bmga\\b/gi, 'manga')
                        .replace(/\\bpwede\\b/gi, 'puwede');
                }

                cleanSpeech = cleanSpeech.replace(/[#*~`_>]/g, '').trim();
                if (!cleanSpeech) return;

                const utterance = new SpeechSynthesisUtterance(cleanSpeech);
                utterance.rate = 1.02;
                utterance.lang = (currentLanguage === 'english') ? 'en-US' : 'fil-PH';

                const haltBtn = document.getElementById('haltSpeechBtn');
                utterance.onend = () => { if (haltBtn) haltBtn.style.display = 'none'; };
                utterance.onerror = () => { if (haltBtn) haltBtn.style.display = 'none'; };
            }
        }

        function updateFsmBadge(state) {
            const badge = document.getElementById('fsmStateBadge');
            const textEl = document.getElementById('fsmStateText');
            if (textEl) textEl.innerText = state;
            if (badge) {
                badge.className = 'state-badge state-' + state.replace('STATE_', '');
            }
        }

        async function fetchSession() {
            try {
                const res = await fetch('/api/session');
                const data = await res.json();
                document.getElementById('headerTableNo').innerText = data.table_no;
                document.getElementById('headerSessionId').innerText = data.session_id;
                currentTableNo = data.table_no;
                if (data.language) {
                    setKioskLanguage(data.language, false);
                }
                updateFsmBadge(data.fsm_state);
                renderCart(data.cart);
            } catch(e) {
                console.error("Fetch session failed:", e);
            }
        }

        function renderCart(cart) {
            const container = document.getElementById('cartItemsContainer');
            const items = cart.line_items || [];
            const count = cart.item_count || 0;
            const grandTotal = cart.grand_total || 0;

            document.getElementById('cartItemCount').innerText = `${count} Items`;
            document.getElementById('cartSubtotal').innerText = `₱${(cart.subtotal || 0).toFixed(2)}`;
            document.getElementById('cartVat').innerText = `₱${(cart.vat_12_pct_breakdown || 0).toFixed(2)}`;
            document.getElementById('cartGrandTotal').innerText = `₱${grandTotal.toFixed(2)}`;

            const confirmBtn = document.getElementById('confirmOrderBtn');
            const confirmBtnText = document.getElementById('confirmOrderBtnText');

            if (items.length > 0 && cart.fsm_state !== 'STATE_CONFIRMED') {
                confirmBtn.disabled = false;
                confirmBtn.classList.add('ready-to-order');
                confirmBtnText.innerText = `CONFIRM & PLACE ORDER (₱${grandTotal.toFixed(2)})`;
            } else {
                confirmBtn.disabled = true;
                confirmBtn.classList.remove('ready-to-order');
                confirmBtnText.innerText = `CONFIRM & PLACE ORDER`;
            }

            if (items.length === 0) {
                container.innerHTML = `
                    <div class="empty-cart-state">
                        <p style="font-size: 2.2rem; margin-bottom: 8px;">🍽️</p>
                        <p style="font-weight: 600; color: var(--text-secondary);">Your table tab is currently empty.</p>
                        <p style="font-size: 0.8rem; margin-top: 4px; color: var(--text-muted);">Click on any menu item or tap "⚡ Order Now" to place your order!</p>
                    </div>`;
                return;
            }

            container.innerHTML = items.map(it => {
                const safeName = it.name.replace(/'/g, "\\\\'");
                return `
                <div class="cart-card">
                    <div class="card-row-top">
                        <div>
                            <div class="item-title">${it.name}</div>
                            ${it.special_instructions ? `<div class="customization-badge">⚠️ ${it.special_instructions}</div>` : ''}
                        </div>
                        <div class="item-price">₱${(it.line_total).toFixed(2)}</div>
                    </div>
                    <div class="card-controls">
                        <div class="qty-controls">
                            <button class="qty-btn" onclick="updateItemQty('${safeName}', ${it.quantity - 1})">-</button>
                            <span class="qty-label">${it.quantity}</span>
                            <button class="qty-btn" onclick="updateItemQty('${safeName}', ${it.quantity + 1})">+</button>
                        </div>
                        <button class="remove-btn" onclick="removeItem('${safeName}')">🗑️ Remove</button>
                    </div>
                </div>`;
            }).join('');
        }

        function appendMessage(sender, text, toolCalls, thinking, speechText) {
            const chat = document.getElementById('chatScroll');
            const isUser = sender === 'Customer';
            const bubble = document.createElement('div');
            bubble.className = `message-bubble ${isUser ? 'message-user' : 'message-assistant'}`;

            let html = '';
            if (!isUser) {
                html += `<div class="assistant-header"><span>🍽️ BistroBot Digital Waiter</span></div>`;
            }

            // Convert markdown-style bullet points or bold text
            const safeText = text || '';
            const formatted = safeText
                .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')
                .replace(/\\n/g, '<br>');

            html += `<div>${formatted}</div>`;

            if (toolCalls && toolCalls.length > 0) {
                const toolsHtml = toolCalls.map(tc => `<span class="tool-chip">⚙️ ${tc.tool}()</span>`).join(' ');
                html += `<div>${toolsHtml}</div>`;
            }

            if (thinking) {
                html += `
                    <div class="thinking-dropdown">
                        <details>
                            <summary>🧠 Model CoT Reasoning</summary>
                            <div class="thinking-content">${thinking}</div>
                        </details>
                    </div>`;
            }

            bubble.innerHTML = html;
            chat.appendChild(bubble);
            chat.scrollTop = chat.scrollHeight;

            if (!isUser && (speechText || safeText)) {
                speakText(speechText || safeText);
            }
        }

        async function sendMessage() {
            const input = document.getElementById('textInput');
            const text = input.value.trim();
            if (!text) return;

            input.value = '';
            appendMessage('Customer', text, null, null);

            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: text, table_no: currentTableNo})
                });
                const data = await res.json();
                if (!res.ok) {
                    appendMessage('BistroBot', 'Server Error: ' + (data.detail || res.statusText), null, null);
                    return;
                }
                appendMessage('BistroBot', data.assistant_response, data.tool_calls, data.thinking, data.speech_text);
                updateFsmBadge(data.fsm_state);
                renderCart(data.cart);
            } catch(e) {
                appendMessage('BistroBot', 'Error connecting to local Ollama agent: ' + e, null, null);
            }
        }

        async function updateItemQty(itemName, newQty) {
            try {
                const res = await fetch('/api/cart/update', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({item_name: itemName, qty: newQty})
                });
                const data = await res.json();
                renderCart(data.cart);
            } catch(e) {
                console.error("Cart update error:", e);
            }
        }

        async function removeItem(itemName) {
            try {
                const res = await fetch('/api/cart/remove', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({item_name: itemName, qty: 0})
                });
                const data = await res.json();
                renderCart(data.cart);
                showToast(`Removed ${itemName} from your order`, '🗑️');
            } catch(e) {
                console.error("Remove item error:", e);
            }
        }

        async function triggerCheckout() {
            try {
                showToast("Finalizing and confirming order...", "🧾");
                const res = await fetch('/api/confirm', {method: 'POST'});
                const data = await res.json();
                updateFsmBadge(data.fsm_state);
                renderCart(data.cart);
                showReceipt(data.receipt);
                showToast("Order placed successfully! Official receipt generated.", "🎉");
            } catch(e) {
                alert("Error confirming order: " + e);
            }
        }

        function showReceipt(rc) {
            currentReceiptData = rc;
            document.getElementById('receiptIdText').innerText = `OFFICIAL RECEIPT #${rc.receipt_id}`;
            document.getElementById('receiptDateText').innerText = new Date().toLocaleString();
            document.getElementById('receiptSubtotal').innerText = `₱${(rc.subtotal || 0).toFixed(2)}`;
            document.getElementById('receiptVat').innerText = `₱${(rc.vat_included || 0).toFixed(2)}`;
            document.getElementById('receiptTotal').innerText = `₱${(rc.grand_total || 0).toFixed(2)}`;

            const linesContainer = document.getElementById('receiptItemsList');
            linesContainer.innerHTML = (rc.itemized_receipt || []).map(it => `
                <div class="receipt-line-item">
                    <span>${it.quantity}x ${it.name} ${it.special_instructions ? `(${it.special_instructions})` : ''}</span>
                    <span style="font-weight: 700;">₱${(it.line_total).toFixed(2)}</span>
                </div>
            `).join('');

            document.getElementById('receiptModal').style.display = 'flex';
        }

        function downloadReceiptTxt() {
            if (!currentReceiptData) return;
            const rc = currentReceiptData;
            let text = "========================================================\\n";
            text += "    UNIVERSITY OF PERPETUAL HELP SYSTEM DALTA\\n";
            text += "           PERPETUAL BISTRO CAMPUS DINING\\n";
            text += "   Las Piñas Campus • Alabang-Zapote Rd, Pamplona 3\\n";
            text += "      Motto: Character Building is Nation Building\\n";
            text += "========================================================\\n\\n";
            text += `OFFICIAL RECEIPT: #${rc.receipt_id}\\n`;
            text += `TABLE NUMBER:     Table #${currentTableNo}\\n`;
            text += `DATE & TIME:      ${new Date().toLocaleString()}\\n`;
            text += `STATUS:           Verified & Committed to restaurant.db\\n`;
            text += "--------------------------------------------------------\\n";
            text += "QTY  ITEM DESCRIPTION                     AMOUNT\\n";
            text += "--------------------------------------------------------\\n";
            (rc.itemized_receipt || []).forEach(it => {
                const itemDesc = (it.name + (it.special_instructions ? ` (${it.special_instructions})` : '')).padEnd(36, ' ').slice(0, 36);
                const price = `PHP ${(it.line_total || 0).toFixed(2)}`.padStart(12, ' ');
                text += `${String(it.quantity).padEnd(4, ' ')} ${itemDesc} ${price}\\n`;
            });
            text += "--------------------------------------------------------\\n";
            text += `SUBTOTAL:                           PHP ${(rc.subtotal || 0).toFixed(2)}\\n`;
            text += `12% VAT BREAKDOWN (INCLUDED):       PHP ${(rc.vat_included || 0).toFixed(2)}\\n`;
            text += `TOTAL BILLED:                       PHP ${(rc.grand_total || 0).toFixed(2)}\\n`;
            text += "========================================================\\n";
            text += "   Thank you for dining at Perpetual Bistro! Mabuhay!\\n";
            text += "========================================================\\n";

            const blob = new Blob([text], {type: 'text/plain;charset=utf-8'});
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = `UPHSD_Bistro_Receipt_${rc.receipt_id}.txt`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }

        async function closeReceiptModal() {
            document.getElementById('receiptModal').style.display = 'none';
            await confirmResetSession();
        }

        async function confirmResetSession() {
            await fetch('/api/reset', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({table_no: currentTableNo})
            });
            document.getElementById('chatScroll').innerHTML = '';
            fetchSession();
            loadMenu();
            showToast(`Session reset for Table #${currentTableNo}`, '🔄');
            if (currentLanguage === 'english') {
                appendMessage('BistroBot', 'Welcome to Table #' + currentTableNo + ' at Perpetual Bistro! What can I get for you today?', null, null);
            } else {
                appendMessage('BistroBot', 'Mabuhay! Welcome po sa Table #' + currentTableNo + ' sa Perpetual Bistro! Ano pong order ninyo today?', null, null, 'Mabuhigh! Welcome poh sa Table ' + currentTableNo + ' sa Perpetual Bistro! Ano pong order ninyo today?');
            }
        }

        function sendQuickPrompt(promptText) {
            switchView('chat');
            document.getElementById('textInput').value = promptText;
            sendMessage();
        }

        function handleKey(event) {
            if (event.key === 'Enter') {
                sendMessage();
            } else if (event.key === 'Escape') {
                haltSpeech();
            }
        }

        // Global keydown listener
        window.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                haltSpeech();
            }
        });

        // Initialize on Load
        window.onload = () => {
            fetchSession();
            loadMenu();
            appendMessage(
                'BistroBot',
                'Mabuhay! Welcome to Table 1 at Perpetual Bistro — University of Perpetual Help System DALTA! I am your table-side digital waiter powered by Qwen 3.5. You can click on any dish to add it to your order, tap "⚡ Order Now" for instant checkout, or speak directly with me!',
                null,
                null,
                'Mabuhigh! Welcome to Table 1 at Perpetual Bistro — University of Perpetual Help System DALTA! I am your table-side digital waiter powered by Qwen 3.5. You can click on any dish to add it to your order, tap "⚡ Order Now" for instant checkout, or speak directly with me!'
            );
        };
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


def find_available_port(preferred_port=8000, fallback_ports=(5000, 8001, 8080, 8888)):
    import socket
    for port in [preferred_port] + list(fallback_ports):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return preferred_port


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Perpetual Bistro Web Tablet Ordering Dashboard")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the dashboard on (default: 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    args = parser.parse_args()

    port = args.port
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((args.host, port))
        except OSError:
            old_port = port
            port = find_available_port(preferred_port=8000)
            print(f"Notice: Port {old_port} was occupied. Automatically selected available port {port}.")

    print(f"\n==================================================================")
    print(f"[Perpetual Bistro] Starting Perpetual Bistro Web Tablet Dashboard")
    print(f"[Perpetual Bistro] Local URL: http://localhost:{port} or http://127.0.0.1:{port}")
    print(f"==================================================================\n")
    uvicorn.run("web_dashboard:app", host=args.host, port=port, reload=True)
