"""
web_dashboard.py
Lightweight local web-based tablet ordering dashboard for Perpetual Bistro.
Fulfills Option 1 (Highly Recommended) from Lab Activity 6.1.
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


class CartUpdateRequest(BaseModel):
    item_name: str
    qty: int


class SessionResetRequest(BaseModel):
    table_no: Optional[int] = 1


class LanguageRequest(BaseModel):
    language: str


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None
    language: Optional[str] = "filipino"


@app.get("/api/session")
def get_session_info():
    """Returns active session details, language, and FSM state."""
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


@app.post("/api/cart/update")
def update_cart_item(req: CartUpdateRequest):
    """Interactive quantity adjuster (+ / -) from the right panel."""
    res = db_tools.update_item_quantity(active_agent.session_id, req.item_name, req.qty)
    cart = db_tools.view_current_order(active_agent.session_id)
    return {"result": res, "cart": cart}


@app.post("/api/cart/remove")
def remove_cart_item(req: CartUpdateRequest):
    """Removes an item from the cart."""
    res = db_tools.remove_item_from_order(active_agent.session_id, req.item_name)
    cart = db_tools.view_current_order(active_agent.session_id)
    return {"result": res, "cart": cart}


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
    <title>Perpetual Bistro — Digital Ordering Tablet</title>
    <style>
        :root {
            --bg-body: #0b1120;
            --surface-card: #131c31;
            --surface-hover: #1b2640;
            --surface-accent: #1e293b;
            --border-subtle: #243452;
            --border-focus: #3b82f6;
            --accent-primary: #851419; /* Perpetual Maroon */
            --accent-gold: #f59e0b;    /* Perpetual Gold */
            --accent-blue: #38bdf8;
            --accent-green: #10b981;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: var(--font-family);
            background: var(--bg-body);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        /* Top Header */
        header {
            background: #0f172a;
            border-bottom: 1px solid var(--border-subtle);
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .brand-container {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand-logo {
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, var(--accent-primary), #991b1b);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            border: 1px solid var(--accent-gold);
        }

        .brand-title h1 {
            font-size: 1.15rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: #ffffff;
        }

        .brand-title p {
            font-size: 0.75rem;
            color: var(--text-secondary);
        }

        .header-meta {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .meta-pill {
            background: var(--surface-card);
            border: 1px solid var(--border-subtle);
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 0.8rem;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .lang-selector-group {
            display: inline-flex;
            align-items: center;
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid var(--border-subtle);
            border-radius: 9999px;
            padding: 2px;
            gap: 2px;
        }

        .lang-btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 12px;
            border-radius: 9999px;
            font-size: 0.78rem;
            font-weight: 600;
            color: var(--text-muted);
            background: transparent;
            border: none;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            user-select: none;
        }

        .lang-btn:hover {
            color: var(--text-primary);
            background: rgba(255, 255, 255, 0.05);
        }

        .lang-btn.active {
            background: var(--accent-gold);
            color: #0f172a;
            font-weight: 700;
            box-shadow: 0 1px 6px rgba(234, 179, 8, 0.35);
        }

        .lang-flag {
            font-size: 0.95rem;
            line-height: 1;
        }

        .state-badge {
            font-weight: 700;
            text-transform: uppercase;
            font-size: 0.72rem;
            letter-spacing: 0.05em;
            padding: 4px 10px;
            border-radius: 6px;
        }

        .state-GREETING { background: #78350f; color: #fde68a; border: 1px solid #d97706; }
        .state-MENU_BROWSING { background: #1e3a8a; color: #bfdbfe; border: 1px solid #3b82f6; }
        .state-TAKING_ORDER { background: #064e3b; color: #a7f3d0; border: 1px solid #10b981; }
        .state-REVIEW { background: #581c87; color: #f5d0fe; border: 1px solid #a855f7; }
        .state-CONFIRMED { background: #14532d; color: #bbf7d0; border: 1px solid #22c55e; }

        /* Main Workspace: 2-Panel Split */
        .workspace {
            flex: 1;
            display: grid;
            grid-template-columns: 1fr 420px;
            overflow: hidden;
        }

        /* Left Panel: Conversation & Voice Stream */
        .left-panel {
            display: flex;
            flex-direction: column;
            border-right: 1px solid var(--border-subtle);
            background: #0d1527;
            overflow: hidden;
        }

        .panel-header {
            padding: 12px 20px;
            background: #111a2e;
            border-bottom: 1px solid var(--border-subtle);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .panel-title {
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 8px;
        }

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
            border-radius: 12px;
            line-height: 1.5;
            font-size: 0.92rem;
            animation: fadeIn 0.2s ease-in;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message-user {
            align-self: flex-end;
            background: linear-gradient(135deg, #1e3a8a, #2563eb);
            color: #ffffff;
            border-bottom-right-radius: 2px;
            border: 1px solid #3b82f6;
        }

        .message-assistant {
            align-self: flex-start;
            background: var(--surface-card);
            color: var(--text-primary);
            border-bottom-left-radius: 2px;
            border: 1px solid var(--border-subtle);
        }

        .assistant-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 6px;
            font-size: 0.75rem;
            color: var(--accent-gold);
            font-weight: 600;
        }

        .tool-chip {
            display: inline-block;
            background: #1e293b;
            color: var(--accent-blue);
            font-size: 0.72rem;
            padding: 2px 8px;
            border-radius: 4px;
            margin-top: 6px;
            border: 1px solid #334155;
            font-family: monospace;
        }

        .thinking-dropdown {
            margin-top: 8px;
            font-size: 0.75rem;
            color: var(--text-muted);
            border-top: 1px dashed var(--border-subtle);
            padding-top: 6px;
        }

        .thinking-content {
            font-family: monospace;
            white-space: pre-wrap;
            max-height: 100px;
            overflow-y: auto;
            background: #0b1120;
            padding: 8px;
            border-radius: 6px;
            margin-top: 4px;
        }

        /* Input Controls */
        .chat-input-bar {
            padding: 16px 20px;
            background: #111a2e;
            border-top: 1px solid var(--border-subtle);
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .voice-btn {
            background: var(--surface-card);
            border: 1px solid var(--border-subtle);
            color: var(--text-primary);
            width: 44px;
            height: 44px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 1.1rem;
        }

        .voice-btn:hover {
            background: var(--surface-hover);
            border-color: var(--border-focus);
        }

        .voice-btn.listening {
            background: #dc2626;
            color: #ffffff;
            animation: pulse 1.2s infinite;
        }

        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.7); }
            70% { box-shadow: 0 0 0 10px rgba(220, 38, 38, 0); }
            100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0); }
        }

        .text-input {
            flex: 1;
            background: var(--bg-body);
            border: 1px solid var(--border-subtle);
            color: var(--text-primary);
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 0.92rem;
            outline: none;
            transition: border-color 0.2s;
        }

        .text-input:focus {
            border-color: var(--border-focus);
        }

        .send-btn {
            background: linear-gradient(135deg, var(--accent-primary), #991b1b);
            border: 1px solid var(--accent-gold);
            color: #ffffff;
            padding: 12px 20px;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }

        .send-btn:hover {
            filter: brightness(1.15);
        }

        /* Right Panel: Real-Time Order Cart */
        .right-panel {
            background: #0f172a;
            display: flex;
            flex-direction: column;
            overflow: hidden;
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
            background: var(--surface-card);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            padding: 12px 14px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            transition: border-color 0.2s;
        }

        .cart-card:hover {
            border-color: #3b82f6;
        }

        .card-row-top {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }

        .item-title {
            font-weight: 600;
            font-size: 0.92rem;
            color: #f1f5f9;
        }

        .item-price {
            font-weight: 700;
            color: var(--accent-gold);
            font-size: 0.92rem;
        }

        .customization-badge {
            background: #2e1065;
            color: #d8b4fe;
            border: 1px solid #7e22ce;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.72rem;
            font-style: italic;
            display: inline-block;
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
            background: #0b1120;
            padding: 4px 8px;
            border-radius: 6px;
            border: 1px solid var(--border-subtle);
        }

        .qty-btn {
            background: #1e293b;
            color: #ffffff;
            border: none;
            width: 24px;
            height: 24px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: bold;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .qty-btn:hover {
            background: #334155;
        }

        .qty-label {
            font-size: 0.85rem;
            font-weight: 700;
            min-width: 18px;
            text-align: center;
        }

        .remove-btn {
            background: transparent;
            border: none;
            color: #ef4444;
            font-size: 0.75rem;
            cursor: pointer;
            text-decoration: underline;
        }

        /* Cart Empty State */
        .empty-cart-state {
            margin: auto;
            text-align: center;
            padding: 40px 20px;
            color: var(--text-muted);
        }

        /* Bottom Bar: Checkout & FSM Control */
        .bottom-bar {
            background: #111a2e;
            border-top: 1px solid var(--border-subtle);
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .cart-totals-breakdown {
            display: flex;
            flex-direction: column;
            gap: 4px;
            font-size: 0.85rem;
            color: var(--text-secondary);
        }

        .totals-row {
            display: flex;
            justify-content: space-between;
        }

        .grand-total-row {
            font-size: 1.05rem;
            font-weight: 800;
            color: #ffffff;
            border-top: 1px solid var(--border-subtle);
            padding-top: 6px;
            margin-top: 4px;
        }

        .confirm-btn {
            background: linear-gradient(135deg, #059669, #10b981);
            color: #ffffff;
            border: none;
            padding: 14px;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 700;
            cursor: pointer;
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
            transition: all 0.2s;
        }

        .confirm-btn:hover:not(:disabled) {
            filter: brightness(1.15);
            transform: translateY(-1px);
        }

        .confirm-btn:disabled {
            background: #334155;
            color: #94a3b8;
            cursor: not-allowed;
            box-shadow: none;
        }

        /* Quick Action Pills */
        .quick-actions {
            display: flex;
            gap: 8px;
            padding: 8px 20px;
            background: #0f172a;
            border-top: 1px solid var(--border-subtle);
            overflow-x: auto;
        }

        .quick-pill {
            background: #1e293b;
            border: 1px solid var(--border-subtle);
            color: var(--text-secondary);
            font-size: 0.75rem;
            padding: 4px 12px;
            border-radius: 9999px;
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.2s;
        }

        .quick-pill:hover {
            color: #ffffff;
            border-color: #3b82f6;
            background: #243452;
        }

        /* Modal Overlay for Receipt */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(0, 0, 0, 0.75);
            backdrop-filter: blur(4px);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 100;
        }

        .receipt-card {
            background: #ffffff;
            color: #0f172a;
            width: 90%;
            max-width: 480px;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.5);
            animation: modalPop 0.25s ease-out;
            font-family: monospace;
        }

        @keyframes modalPop {
            from { transform: scale(0.9); opacity: 0; }
            to { transform: scale(1); opacity: 1; }
        }

        .receipt-header {
            text-align: center;
            border-bottom: 2px dashed #94a3b8;
            padding-bottom: 12px;
            margin-bottom: 12px;
        }

        .receipt-header h2 {
            font-size: 1.2rem;
            font-weight: 800;
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
            border-top: 2px dashed #94a3b8;
            padding-top: 12px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .modal-close-btn {
            background: #0f172a;
            color: #ffffff;
            border: none;
            padding: 10px;
            border-radius: 6px;
            font-weight: bold;
            margin-top: 14px;
            cursor: pointer;
            width: 100%;
        }
    </style>
</head>
<body>

    <!-- Header -->
    <header>
        <div class="brand-container">
            <div class="brand-logo">🍽️</div>
            <div class="brand-title">
                <h1>PERPETUAL BISTRO</h1>
                <p>Digital Table-Side Ordering System & Conversational Agent</p>
            </div>
        </div>
        <div class="header-meta">
            <div class="meta-pill">📍 Table #<span id="headerTableNo">1</span></div>
            <div class="meta-pill">🔑 Session: <span id="headerSessionId" style="font-family: monospace;">---</span></div>
            <div class="meta-pill">🤖 Qwen 3.5 (4B) Local</div>
            <!-- McDonald's Kiosk Language Selector -->
            <div class="lang-selector-group" role="radiogroup" aria-label="Select Kiosk Language">
                <button id="langFilipinoBtn" class="lang-btn active" onclick="setKioskLanguage('filipino')" title="Filipino (Taglish) Mode with Rosa">
                    <span class="lang-flag">🇵🇭</span> Filipino
                </button>
                <button id="langEnglishBtn" class="lang-btn" onclick="setKioskLanguage('english')" title="English Mode with Jenny">
                    <span class="lang-flag">🇺🇸</span> English
                </button>
            </div>
            <button id="ttsToggleBtn" class="meta-pill" style="cursor: pointer; background: var(--surface-card); color: var(--accent-gold); border: 1px solid var(--border-subtle);" onclick="toggleTtsAudio()">🔊 Voice Audio: ON</button>
            <button id="haltSpeechBtn" class="meta-pill" style="cursor: pointer; background: #dc2626; color: #ffffff; font-weight: bold; border: 1px solid #ef4444; display: none;" onclick="haltSpeech()">⏹️ HALT VOICE (Esc)</button>
            <span id="fsmStateBadge" class="state-badge state-GREETING">STATE_GREETING</span>
        </div>
    </header>

    <!-- Hidden Natural Audio Player -->
    <audio id="bistroAudioPlayer" style="display: none;"></audio>

    <!-- Workspace -->
    <div class="workspace">
        
        <!-- Left Panel: Conversation -->
        <div class="left-panel">
            <div class="panel-header">
                <div class="panel-title">
                    <span>💬 Table Dialogue Stream</span>
                </div>
                <div style="font-size: 0.75rem; color: var(--text-muted);" id="audioNotice">
                    Natural AI • Zero-Cloud • SQLite Bound
                </div>
            </div>

            <div id="micAlertBanner" style="display: none; background: #7f1d1d; color: #fecaca; padding: 8px 16px; font-size: 0.8rem; border-bottom: 1px solid #dc2626;">
                ⚠️ <strong>Microphone Notice:</strong> Browser speech recognition was blocked or unavailable. Please click the lock/settings icon in your address bar to allow microphone permissions, or type directly in the input box.
            </div>

            <div id="chatScroll" class="chat-scroll">
                <!-- Dialogue Bubbles Rendered Here -->
            </div>

            <!-- Quick Suggestions (Natural conversational queries) -->
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
                <span id="audioStatusText" style="font-size: 0.78rem; color: var(--text-muted); min-width: 130px; user-select: none;">🎙️ Mic: Ready</span>
                <input id="textInput" class="text-input" type="text" placeholder="Type your order, dietary preference, or question..." onkeydown="handleKey(event)">
                <button id="sendBtn" class="send-btn" onclick="sendMessage()">Send</button>
            </div>
        </div>

        <!-- Right Panel: Real-Time Order Cart -->
        <div class="right-panel">
            <div class="panel-header">
                <div class="panel-title">
                    <span>🛒 Active Order Tab</span>
                </div>
                <div style="font-size: 0.75rem; color: var(--accent-gold);" id="cartItemCount">
                    0 Items
                </div>
            </div>

            <div id="cartItemsContainer" class="cart-items-container">
                <div class="empty-cart-state">
                    <p style="font-size: 2rem; margin-bottom: 8px;">🍽️</p>
                    <p>Your tab is currently empty.</p>
                    <p style="font-size: 0.8rem; margin-top: 4px;">Ask BistroBot to add items or recommendations.</p>
                </div>
            </div>

            <!-- Bottom Bar: Checkout & FSM Control -->
            <div class="bottom-bar">
                <div class="cart-totals-breakdown">
                    <div class="totals-row">
                        <span>Subtotal:</span>
                        <span id="cartSubtotal">₱0.00</span>
                    </div>
                    <div class="totals-row">
                        <span>12% Government VAT (Included):</span>
                        <span id="cartVat">₱0.00</span>
                    </div>
                    <div class="totals-row grand-total-row">
                        <span>TOTAL AMOUNT:</span>
                        <span id="cartGrandTotal" style="color: var(--accent-green);">₱0.00</span>
                    </div>
                </div>

                <button id="confirmOrderBtn" class="confirm-btn" onclick="triggerCheckout()" disabled>
                    <span>CONFIRM & PLACE ORDER</span>
                    <span>→</span>
                </button>
            </div>

        </div>

    </div>

    <!-- Digital Receipt Modal -->
    <div id="receiptModal" class="modal-overlay">
        <div class="receipt-card">
            <div class="receipt-header">
                <h2>UNIVERSITY OF PERPETUAL HELP</h2>
                <p>PERPETUAL BISTRO — CAMPUS DINING</p>
                <p style="margin-top: 4px; font-size: 0.75rem;" id="receiptIdText">RECEIPT #PB-1-XXXXXX</p>
                <p style="font-size: 0.75rem;" id="receiptDateText"></p>
            </div>

            <div id="receiptItemsList" class="receipt-lines">
                <!-- Receipt Items Injected Here -->
            </div>

            <div class="receipt-footer">
                <div class="receipt-line-item">
                    <span>Subtotal:</span>
                    <span id="receiptSubtotal">₱0.00</span>
                </div>
                <div class="receipt-line-item">
                    <span>12% VAT Breakdown:</span>
                    <span id="receiptVat">₱0.00</span>
                </div>
                <div class="receipt-line-item" style="font-weight: 800; font-size: 1.05rem; border-top: 1px solid #0f172a; padding-top: 4px;">
                    <span>TOTAL BILLED:</span>
                    <span id="receiptTotal">₱0.00</span>
                </div>
            </div>

            <div style="text-align: center; margin-top: 12px; font-size: 0.75rem; color: #475569;">
                Status: Verified & Committed to restaurant.db<br>
                Kitchen ticket dispatched. Thank you!
            </div>

            <button class="modal-close-btn" onclick="closeReceiptModal()">Start New Table Session</button>
        </div>
    </div>

    <script>
        let currentTableNo = 1;
        let isListening = false;
        let recognition = null;
        let ttsAudioEnabled = true;
        let currentLanguage = 'filipino';

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

            if (isListening) {
                btn.classList.add('listening');
                btn.title = "Listening to speech (Click to cancel)...";
                if (statusEl) {
                    statusEl.innerText = '🔴 Listening...';
                    statusEl.style.color = '#ef4444';
                }
                try { recognition.start(); } catch(e){}
            } else {
                btn.classList.remove('listening');
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
                btn.innerText = "🔇 Voice Audio: MUTED";
                btn.style.color = "#94a3b8";
                btn.style.borderColor = "#475569";
            } else {
                btn.innerText = "🔊 Voice Audio: ON";
                btn.style.color = "var(--accent-gold)";
                btn.style.borderColor = "var(--border-subtle)";
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
        }

        async function speakText(text) {
            if (!ttsAudioEnabled || !text) return;
            haltSpeech();

            const haltBtn = document.getElementById('haltSpeechBtn');
            if (haltBtn) haltBtn.style.display = 'inline-block';

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
                    return;
                }
                const audioUrl = URL.createObjectURL(blob);
                const player = document.getElementById('bistroAudioPlayer');
                player.src = audioUrl;
                player.onended = () => { if (haltBtn) haltBtn.style.display = 'none'; };
                player.onerror = () => { if (haltBtn) haltBtn.style.display = 'none'; };
                await player.play();
            } catch (err) {
                console.warn("Natural neural voice playback failed, falling back to local speech synthesis:", err);
                speakFallbackLocal(text);
            }
        }

        function speakFallbackLocal(text) {
            if ('speechSynthesis' in window) {
                window.speechSynthesis.cancel();
                let cleanSpeech = text.replace(/\\b[Mm]abuhay\\b/g, 'Mabuhigh').replace(/₱\\s*(\\d+(?:\\.\\d+)?)/g, '$1 pesos').replace(/₱/g, ' pesos');
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
                cleanSpeech = Array.from(cleanSpeech)
                    .filter(char => {
                        const cp = char.codePointAt(0);
                        return !(cp >= 0x10000 || (cp >= 0x2600 && cp <= 0x27BF) || (cp >= 0xFE00 && cp <= 0xFE0F) || cp === 0x200D);
                    })
                    .join('');
                cleanSpeech = cleanSpeech
                    .replace(/[*#_~`>]/g, '')
                    .replace(/\\s+/g, ' ')
                    .trim();
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
            badge.innerText = state;
            badge.className = 'state-badge state-' + state.replace('STATE_', '');
        }

        async function fetchSession() {
            try {
                const res = await fetch('/api/session');
                const data = await res.json();
                document.getElementById('headerTableNo').innerText = data.table_no;
                document.getElementById('headerSessionId').innerText = data.session_id;
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
            document.getElementById('cartItemCount').innerText = `${cart.item_count || 0} Items`;
            document.getElementById('cartSubtotal').innerText = `₱${(cart.subtotal || 0).toFixed(2)}`;
            document.getElementById('cartVat').innerText = `₱${(cart.vat_12_pct_breakdown || 0).toFixed(2)}`;
            document.getElementById('cartGrandTotal').innerText = `₱${(cart.grand_total || 0).toFixed(2)}`;

            const confirmBtn = document.getElementById('confirmOrderBtn');
            confirmBtn.disabled = items.length === 0 || cart.fsm_state === 'STATE_CONFIRMED';

            if (items.length === 0) {
                container.innerHTML = `
                    <div class="empty-cart-state">
                        <p style="font-size: 2rem; margin-bottom: 8px;">🍽️</p>
                        <p>Your tab is currently empty.</p>
                        <p style="font-size: 0.8rem; margin-top: 4px;">Ask BistroBot to add items or recommendations.</p>
                    </div>`;
                return;
            }

            container.innerHTML = items.map(it => `
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
                            <button class="qty-btn" onclick="updateItemQty('${it.name}', ${it.quantity - 1})">-</button>
                            <span class="qty-label">${it.quantity}</span>
                            <button class="qty-btn" onclick="updateItemQty('${it.name}', ${it.quantity + 1})">+</button>
                        </div>
                        <button class="remove-btn" onclick="removeItem('${it.name}')">Remove</button>
                    </div>
                </div>
            `).join('');
        }

        function appendMessage(sender, text, toolCalls, thinking, speechText) {
            const chat = document.getElementById('chatScroll');
            const isUser = sender === 'Customer';
            const bubble = document.createElement('div');
            bubble.className = `message-bubble ${isUser ? 'message-user' : 'message-assistant'}`;

            let html = '';
            if (!isUser) {
                html += `<div class="assistant-header"><span>🍽️ BistroBot</span></div>`;
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
            } catch(e) {
                console.error("Remove item error:", e);
            }
        }

        async function triggerCheckout() {
            try {
                const res = await fetch('/api/confirm', {method: 'POST'});
                const data = await res.json();
                updateFsmBadge(data.fsm_state);
                renderCart(data.cart);
                showReceipt(data.receipt);
            } catch(e) {
                alert("Error confirming order: " + e);
            }
        }

        function showReceipt(rc) {
            document.getElementById('receiptIdText').innerText = `RECEIPT #${rc.receipt_id}`;
            document.getElementById('receiptDateText').innerText = new Date().toLocaleString();
            document.getElementById('receiptSubtotal').innerText = `₱${(rc.subtotal || 0).toFixed(2)}`;
            document.getElementById('receiptVat').innerText = `₱${(rc.vat_included || 0).toFixed(2)}`;
            document.getElementById('receiptTotal').innerText = `₱${(rc.grand_total || 0).toFixed(2)}`;

            const linesContainer = document.getElementById('receiptItemsList');
            linesContainer.innerHTML = (rc.itemized_receipt || []).map(it => `
                <div class="receipt-line-item">
                    <span>${it.quantity}x ${it.name} ${it.special_instructions ? `(${it.special_instructions})` : ''}</span>
                    <span>₱${(it.line_total).toFixed(2)}</span>
                </div>
            `).join('');

            document.getElementById('receiptModal').style.display = 'flex';
        }

        async function closeReceiptModal() {
            document.getElementById('receiptModal').style.display = 'none';
            await fetch('/api/reset', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({table_no: currentTableNo})
            });
            document.getElementById('chatScroll').innerHTML = '';
            fetchSession();
            if (currentLanguage === 'english') {
                appendMessage('BistroBot', 'Welcome to Table #' + currentTableNo + ' at Perpetual Bistro! What can I get for you today?', null, null);
            } else {
                appendMessage('BistroBot', 'Mabuhay! Welcome po sa Table #' + currentTableNo + ' sa Perpetual Bistro! Ano pong order ninyo today?', null, null, 'Mabuhigh! Welcome poh sa Table ' + currentTableNo + ' sa Perpetual Bistro! Ano pong order ninyo today?');
            }
        }

        function sendQuickPrompt(promptText) {
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

        // Global keydown listener so pressing Escape halts speech anywhere
        window.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                haltSpeech();
            }
        });

        // Initialize
        window.onload = () => {
            fetchSession();
            appendMessage(
                'BistroBot',
                'Mabuhay! Welcome to Table 1 at Perpetual Bistro! I am your table-side digital waiter powered by Qwen 3.5. You can ask for our menu recommendations, check allergens, or place an order po!',
                null,
                null,
                'Mabuhigh! Welcome to Table 1 at Perpetual Bistro! I am your table-side digital waiter powered by Qwen 3.5. You can ask for our menu recommendations, check allergens, or place an order poh!'
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
    print(f"🍽️  Starting Perpetual Bistro Web Tablet Dashboard")
    print(f"👉 Local URL: http://localhost:{port} or http://127.0.0.1:{port}")
    print(f"==================================================================\n")
    uvicorn.run("web_dashboard:app", host=args.host, port=port, reload=False)

