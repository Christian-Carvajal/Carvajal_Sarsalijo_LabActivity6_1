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
    <title>University of Perpetual Help — Perpetual Bistro Kiosk</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800;900&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            /* Official University of Perpetual Help System DALTA Palette */
            --uphsd-maroon: #7B1113;        /* Signature UPHSD Maroon */
            --uphsd-maroon-dark: #4A070B;   /* Deep Institutional Maroon */
            --uphsd-maroon-deep: #2A0407;   /* Charcoal Maroon Shadow */
            --uphsd-maroon-light: #9B1B1E;  /* Bright Maroon Accent */
            --uphsd-maroon-glow: rgba(123, 17, 19, 0.45);

            --uphsd-gold: #D4AF37;          /* Official Academic Gold */
            --uphsd-gold-bright: #F5B041;   /* Radiant Interactive Gold */
            --uphsd-gold-deep: #AA820A;     /* Metallic Burnished Gold */
            --uphsd-gold-light: #FEF3C7;    /* Cream Gold Text */
            --uphsd-gold-glow: rgba(212, 175, 55, 0.35);

            /* Surfaces & Dark Mode Kiosk Depth */
            --bg-body: #0A0304;             /* Obsidian with Warm Maroon Base */
            --surface-panel: #120406;       /* Split Panel Canvas */
            --surface-card: #1C080B;        /* Elevated Container Card */
            --surface-hover: #260B10;       /* Interactive Hover State */
            --surface-accent: #320E15;      /* Accent Layer */
            --border-subtle: #3A0F14;       /* Base Structural Border */
            --border-gold: rgba(212, 175, 55, 0.35); /* Institutional Gold Accent Border */
            --border-focus: #F5B041;        /* Focused Ring */

            /* Typography & Neutrals */
            --text-primary: #FFFFFF;        /* Pure White Headings */
            --text-secondary: #E8D8D3;      /* Soft Parchment Body */
            --text-muted: #A38286;          /* Muted Dusty Rose */
            --accent-green: #10B981;        /* Checkout & Stock Affirmation */

            --font-heading: 'Cinzel', Georgia, 'Times New Roman', serif;
            --font-ui: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            --font-mono: 'JetBrains Mono', Consolas, monospace;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: var(--font-ui);
            background: var(--bg-body);
            background-image: 
                radial-gradient(ellipse at 15% 10%, rgba(123, 17, 19, 0.22) 0%, transparent 60%),
                radial-gradient(ellipse at 85% 90%, rgba(212, 175, 55, 0.12) 0%, transparent 50%);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            -webkit-font-smoothing: antialiased;
        }

        /* Top Institutional Motto Ribbon */
        .uphsd-top-ribbon {
            background: linear-gradient(90deg, #240305 0%, #3D0609 50%, #240305 100%);
            border-bottom: 1px solid rgba(212, 175, 55, 0.35);
            padding: 4px 24px;
            font-size: 0.72rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            color: var(--uphsd-gold-light);
            letter-spacing: 0.04em;
            user-select: none;
            z-index: 10;
        }

        .ribbon-motto {
            font-family: var(--font-heading);
            font-weight: 700;
            color: var(--uphsd-gold-bright);
            letter-spacing: 0.06em;
            text-transform: uppercase;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        .ribbon-campus {
            color: var(--text-muted);
            margin-left: 12px;
            font-size: 0.7rem;
        }

        .ribbon-badge {
            background: rgba(212, 175, 55, 0.15);
            border: 1px solid rgba(212, 175, 55, 0.3);
            color: var(--uphsd-gold-bright);
            padding: 2px 10px;
            border-radius: 9999px;
            font-size: 0.68rem;
            font-weight: 600;
        }

        /* Institutional Main Header */
        header {
            background: linear-gradient(135deg, #380508 0%, #5C0B12 45%, #7B1113 75%, #420609 100%);
            border-bottom: 3px solid var(--uphsd-gold);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5), 0 1px 10px var(--uphsd-gold-glow);
            padding: 10px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: relative;
            z-index: 9;
        }

        .brand-container {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .brand-seal {
            width: 48px;
            height: 48px;
            flex-shrink: 0;
            filter: drop-shadow(0 2px 8px rgba(0, 0, 0, 0.5));
            transition: transform 0.25s ease;
        }

        .brand-seal:hover {
            transform: scale(1.05) rotate(1deg);
        }

        .brand-title {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }

        .university-name {
            font-family: var(--font-heading);
            font-size: 0.65rem;
            font-weight: 700;
            color: var(--uphsd-gold-bright);
            letter-spacing: 0.09em;
            text-transform: uppercase;
            text-shadow: 0 1px 2px rgba(0,0,0,0.6);
        }

        .brand-title h1 {
            font-family: var(--font-heading);
            font-size: 1.28rem;
            font-weight: 900;
            letter-spacing: 0.04em;
            color: #FFFFFF;
            text-shadow: 0 2px 6px rgba(0, 0, 0, 0.6), 0 0 12px rgba(212, 175, 55, 0.35);
            line-height: 1.1;
        }

        .brand-title p {
            font-size: 0.72rem;
            color: var(--text-secondary);
            font-weight: 500;
        }

        .header-meta {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }

        .meta-pill {
            background: rgba(22, 6, 8, 0.85);
            border: 1px solid var(--border-gold);
            color: var(--uphsd-gold-light);
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 0.8rem;
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
            height: 20px;
            padding: 0 4px;
        }

        .wave-bar {
            width: 3px;
            height: 6px;
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
            0%, 100% { height: 6px; }
            50% { height: 18px; background: #FFF; }
        }

        /* Language Selector Group */
        .lang-selector-group {
            display: inline-flex;
            align-items: center;
            background: rgba(28, 8, 11, 0.95);
            border: 1px solid var(--uphsd-gold);
            border-radius: 9999px;
            padding: 2px;
            gap: 2px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
        }

        .lang-btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 14px;
            border-radius: 9999px;
            font-size: 0.78rem;
            font-weight: 700;
            color: var(--uphsd-gold-light);
            background: transparent;
            border: none;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
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
            box-shadow: 0 2px 8px rgba(212, 175, 55, 0.4);
        }

        .lang-flag {
            font-size: 1rem;
            line-height: 1;
        }

        /* State Badges in School Heraldry */
        .state-badge {
            font-family: var(--font-heading);
            font-weight: 800;
            text-transform: uppercase;
            font-size: 0.72rem;
            letter-spacing: 0.08em;
            padding: 5px 12px;
            border-radius: 6px;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35);
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

        /* Main Workspace: 2-Panel Split */
        .workspace {
            flex: 1;
            display: grid;
            grid-template-columns: 1fr 440px;
            overflow: hidden;
            background: var(--bg-body);
        }

        /* Left Panel: Conversation & Voice Stream */
        .left-panel {
            display: flex;
            flex-direction: column;
            border-right: 1px solid var(--border-subtle);
            background: var(--surface-panel);
            overflow: hidden;
            position: relative;
        }

        .panel-header {
            padding: 12px 22px;
            background: linear-gradient(180deg, #1A0609 0%, #150406 100%);
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
            gap: 10px;
        }

        /* Menu Category Quick-Filter Bar */
        .category-tabs-bar {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 20px;
            background: #190507;
            border-bottom: 1px solid var(--border-subtle);
            overflow-x: auto;
            scrollbar-width: none;
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
            border-radius: 9999px;
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            user-select: none;
        }

        .cat-pill:hover {
            color: #FFFFFF;
            border-color: var(--uphsd-gold);
            background: var(--surface-hover);
        }

        .cat-pill.active {
            background: linear-gradient(135deg, var(--uphsd-maroon) 0%, var(--uphsd-maroon-dark) 100%);
            border-color: var(--uphsd-gold);
            color: var(--uphsd-gold-bright);
            font-weight: 700;
            box-shadow: 0 1px 6px rgba(212, 175, 55, 0.25);
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
            line-height: 1.55;
            font-size: 0.92rem;
            animation: fadeIn 0.2s ease-in;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.25);
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message-user {
            align-self: flex-end;
            background: linear-gradient(135deg, #6B0F1A 0%, #851419 100%);
            color: #FFFFFF;
            border-bottom-right-radius: 2px;
            border: 1px solid var(--uphsd-gold);
            box-shadow: 0 4px 12px rgba(123, 17, 19, 0.35);
        }

        .message-assistant {
            align-self: flex-start;
            background: var(--surface-card);
            color: var(--text-primary);
            border-bottom-left-radius: 2px;
            border: 1px solid var(--border-gold);
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
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

        /* Input Controls */
        .chat-input-bar {
            padding: 14px 20px;
            background: linear-gradient(180deg, #160507 0%, #100305 100%);
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
        }

        .voice-btn:hover {
            background: var(--surface-hover);
            transform: scale(1.05);
            box-shadow: 0 0 12px var(--uphsd-gold-glow);
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
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 0.92rem;
            font-family: var(--font-ui);
            outline: none;
            transition: border-color 0.2s, box-shadow 0.2s;
        }

        .text-input:focus {
            border-color: var(--uphsd-gold);
            box-shadow: 0 0 0 3px rgba(212, 175, 55, 0.2);
        }

        .send-btn {
            background: linear-gradient(135deg, var(--uphsd-gold-bright) 0%, var(--uphsd-gold) 100%);
            border: 1px solid var(--uphsd-gold-bright);
            color: var(--uphsd-maroon-dark);
            padding: 12px 22px;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 800;
            letter-spacing: 0.02em;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 2px 8px rgba(212, 175, 55, 0.3);
        }

        .send-btn:hover {
            filter: brightness(1.1);
            transform: translateY(-1px);
        }

        /* Right Panel: Real-Time Order Cart */
        .right-panel {
            background: #0F0305;
            border-left: 1px solid var(--border-subtle);
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
            border: 1px solid var(--border-gold);
            border-radius: 10px;
            padding: 14px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            transition: border-color 0.2s, transform 0.15s;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
        }

        .cart-card:hover {
            border-color: var(--uphsd-gold-bright);
            transform: translateY(-1px);
        }

        .card-row-top {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }

        .item-title {
            font-weight: 700;
            font-size: 0.94rem;
            color: #FFFFFF;
        }

        .item-price {
            font-family: var(--font-heading);
            font-weight: 800;
            color: var(--uphsd-gold-bright);
            font-size: 0.95rem;
        }

        .customization-badge {
            background: #3B0A0E;
            color: var(--uphsd-gold-light);
            border: 1px solid var(--border-gold);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.72rem;
            font-style: italic;
            display: inline-block;
            margin-top: 3px;
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
            background: #0E0305;
            padding: 4px 8px;
            border-radius: 6px;
            border: 1px solid var(--border-gold);
        }

        .qty-btn {
            background: var(--surface-card);
            color: var(--uphsd-gold-bright);
            border: 1px solid var(--border-subtle);
            width: 26px;
            height: 26px;
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
            font-size: 0.88rem;
            font-weight: 800;
            min-width: 20px;
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

        /* Bottom Bar: Checkout & FSM Control */
        .bottom-bar {
            background: linear-gradient(180deg, #180608 0%, #100305 100%);
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
            border-radius: 8px;
            font-family: var(--font-heading);
            font-size: 1rem;
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

        .confirm-btn:hover:not(:disabled) {
            filter: brightness(1.12);
            transform: translateY(-2px);
            box-shadow: 0 6px 22px rgba(212, 175, 55, 0.55);
        }

        .confirm-btn:disabled {
            background: #2A0D11;
            color: #7A555A;
            border-color: #3D141A;
            cursor: not-allowed;
            box-shadow: none;
            transform: none;
        }

        /* Quick Action Pills */
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
            border-radius: 9999px;
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.2s;
        }

        .quick-pill:hover {
            color: #FFFFFF;
            border-color: var(--uphsd-gold);
            background: var(--surface-hover);
        }

        /* Modal Overlay for Receipt */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(0, 0, 0, 0.85);
            backdrop-filter: blur(6px);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 100;
        }

        .receipt-card {
            background: #FCFBF7;
            color: #1A0507;
            width: 90%;
            max-width: 500px;
            border-radius: 12px;
            border: 2px solid var(--uphsd-gold);
            padding: 24px;
            box-shadow: 0 24px 60px rgba(0, 0, 0, 0.8), 0 0 20px var(--uphsd-gold-glow);
            animation: modalPop 0.25s ease-out;
            font-family: var(--font-mono);
        }

        @keyframes modalPop {
            from { transform: scale(0.92); opacity: 0; }
            to { transform: scale(1); opacity: 1; }
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

    <!-- Top Institutional Motto Ribbon -->
    <div class="uphsd-top-ribbon">
        <div class="ribbon-left">
            <span class="ribbon-motto">★ Character Building is Nation Building</span>
            <span class="ribbon-campus">Las Piñas Campus • College of Computer Studies</span>
        </div>
        <div class="ribbon-right">
            <span class="ribbon-badge">Perpetual Bistro Kiosk v2.5 • AI Autonomous Dining</span>
        </div>
    </div>

    <!-- Official Institutional Header -->
    <header>
        <div class="brand-container">
            <!-- Authentic University of Perpetual Help Cameo Seal SVG -->
            <svg class="brand-seal" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="50" cy="50" r="48" fill="#4A070B" stroke="#D4AF37" stroke-width="3"/>
                <circle cx="50" cy="50" r="42" fill="#6B0F1A" stroke="#F5B041" stroke-width="1.5" stroke-dasharray="3 2"/>
                <!-- Golden Laurel Leaves -->
                <path d="M25 65 C20 50, 23 35, 34 24 C29 35, 31 48, 38 56 Z" fill="#D4AF37" opacity="0.95"/>
                <path d="M75 65 C80 50, 77 35, 66 24 C71 35, 69 48, 62 56 Z" fill="#D4AF37" opacity="0.95"/>
                <!-- Central Maroon Cameo Shield -->
                <path d="M34 32 L66 32 C66 54, 50 70, 50 74 C50 70, 34 54, 34 32 Z" fill="#7B1113" stroke="#D4AF37" stroke-width="2"/>
                <!-- Torch & Cross of Learning -->
                <path d="M50 36 L50 62 M42 45 L58 45" stroke="#F5B041" stroke-width="2.5" stroke-linecap="round"/>
                <polygon points="50,29 53,35 47,35" fill="#FFD700"/>
                <!-- Star of Excellence -->
                <polygon points="50,16 52,21 57,21 53,24 55,29 50,26 45,29 47,24 43,21 48,21" fill="#F5B041"/>
            </svg>
            <div class="brand-title">
                <div class="university-name">University of Perpetual Help System DALTA</div>
                <h1>PERPETUAL BISTRO</h1>
                <p>Campus Dining Table-Side Tablet & Autonomous Waiter</p>
            </div>
        </div>
        <div class="header-meta">
            <div class="meta-pill">📍 Table #<span id="headerTableNo">1</span></div>
            <div class="meta-pill">🔑 Session: <span id="headerSessionId" style="font-family: var(--font-mono);">---</span></div>
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

            <!-- Voice Controls & Audio Visualizer -->
            <div class="meta-pill" style="gap: 8px;">
                <button id="ttsToggleBtn" style="cursor: pointer; background: transparent; border: none; color: var(--uphsd-gold-bright); font-weight: 700;" onclick="toggleTtsAudio()">🔊 Voice Audio: ON</button>
                <div class="audio-wave-container" id="audioWaveform" title="Speech Audio Activity">
                    <span class="wave-bar"></span>
                    <span class="wave-bar"></span>
                    <span class="wave-bar"></span>
                    <span class="wave-bar"></span>
                    <span class="wave-bar"></span>
                </div>
            </div>

            <button id="haltSpeechBtn" class="meta-pill" style="cursor: pointer; background: #DC2626; color: #FFFFFF; font-weight: bold; border: 1px solid #EF4444; display: none;" onclick="haltSpeech()">⏹️ HALT VOICE (Esc)</button>
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
                <div style="font-size: 0.75rem; color: var(--uphsd-gold-light);" id="audioNotice">
                    Natural AI • Taglish (Rosa) • SQLite Bound
                </div>
            </div>

            <!-- Interactive Menu Category Quick-Filter Tabs -->
            <div class="category-tabs-bar" id="categoryTabs">
                <button class="cat-pill active" onclick="filterMenuCategory('all')">🌟 All Bistro Specials</button>
                <button class="cat-pill" onclick="filterMenuCategory('Mains')">🍲 Mains</button>
                <button class="cat-pill" onclick="filterMenuCategory('Sides')">🍟 Sides</button>
                <button class="cat-pill" onclick="filterMenuCategory('Drinks')">🥤 Beverages</button>
                <button class="cat-pill" onclick="filterMenuCategory('Dessert')">🍨 Desserts</button>
            </div>

            <div id="micAlertBanner" style="display: none; background: #7F1D1D; color: #FECACA; padding: 8px 16px; font-size: 0.8rem; border-bottom: 1px solid #DC2626;">
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
                <div style="font-size: 0.78rem; font-weight: 700; color: var(--uphsd-gold-bright);" id="cartItemCount">
                    0 Items
                </div>
            </div>

            <div id="cartItemsContainer" class="cart-items-container">
                <div class="empty-cart-state">
                    <p style="font-size: 2.2rem; margin-bottom: 8px;">🍽️</p>
                    <p style="font-weight: 600; color: var(--text-secondary);">Your table tab is currently empty.</p>
                    <p style="font-size: 0.8rem; margin-top: 4px; color: var(--text-muted);">Ask BistroBot to recommend specials or add items.</p>
                </div>
            </div>

            <!-- Bottom Bar: Checkout & FSM Control -->
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
                    <span>CONFIRM & PLACE ORDER</span>
                    <span>→</span>
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

    <script>
        let currentTableNo = 1;
        let isListening = false;
        let recognition = null;
        let ttsAudioEnabled = true;
        let currentLanguage = 'filipino';
        let currentReceiptData = null;

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
                btn.innerText = "🔇 Voice Audio: MUTED";
                btn.style.color = "#9E8083";
            } else {
                btn.innerText = "🔊 Voice Audio: ON";
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
            let text = "========================================================\n";
            text += "    UNIVERSITY OF PERPETUAL HELP SYSTEM DALTA\n";
            text += "           PERPETUAL BISTRO CAMPUS DINING\n";
            text += "   Las Piñas Campus • Alabang-Zapote Rd, Pamplona 3\n";
            text += "      Motto: Character Building is Nation Building\n";
            text += "========================================================\n\n";
            text += `OFFICIAL RECEIPT: #${rc.receipt_id}\n`;
            text += `TABLE NUMBER:     Table #${currentTableNo}\n`;
            text += `DATE & TIME:      ${new Date().toLocaleString()}\n`;
            text += `STATUS:           Verified & Committed to restaurant.db\n`;
            text += "--------------------------------------------------------\n";
            text += "QTY  ITEM DESCRIPTION                     AMOUNT\n";
            text += "--------------------------------------------------------\n";
            (rc.itemized_receipt || []).forEach(it => {
                const itemDesc = (it.name + (it.special_instructions ? ` (${it.special_instructions})` : '')).padEnd(36, ' ').slice(0, 36);
                const price = `PHP ${(it.line_total || 0).toFixed(2)}`.padStart(12, ' ');
                text += `${String(it.quantity).padEnd(4, ' ')} ${itemDesc} ${price}\n`;
            });
            text += "--------------------------------------------------------\n";
            text += `SUBTOTAL:                           PHP ${(rc.subtotal || 0).toFixed(2)}\n`;
            text += `12% VAT BREAKDOWN (INCLUDED):       PHP ${(rc.vat_included || 0).toFixed(2)}\n`;
            text += `TOTAL BILLED:                       PHP ${(rc.grand_total || 0).toFixed(2)}\n`;
            text += "========================================================\n";
            text += "   Thank you for dining at Perpetual Bistro! Mabuhay!\n";
            text += "========================================================\n";

            const blob = new Blob([text], {type: 'text/plain;charset=utf-8'});
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = `UPHSD_Bistro_Receipt_${rc.receipt_id}.txt`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }

        function filterMenuCategory(category) {
            const tabs = document.querySelectorAll('.category-tabs-bar .cat-pill');
            tabs.forEach(tab => tab.classList.remove('active'));
            if (window.event && window.event.target) {
                window.event.target.classList.add('active');
            }

            if (category === 'all') {
                sendQuickPrompt(currentLanguage === 'english' ? 'What are all the specials available today at Perpetual Bistro?' : 'Ano-ano po ang lahat ng available bistro specials today?');
            } else {
                sendQuickPrompt(currentLanguage === 'english' ? `Can you show me what you have under ${category}?` : `Ano-ano po ang mga available na ${category}?`);
            }
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
                'Mabuhay! Welcome to Table 1 at Perpetual Bistro — University of Perpetual Help System DALTA! I am your table-side digital waiter powered by Qwen 3.5. You can ask for our menu recommendations, check allergens, or place an order po!',
                null,
                null,
                'Mabuhigh! Welcome to Table 1 at Perpetual Bistro — University of Perpetual Help System DALTA! I am your table-side digital waiter powered by Qwen 3.5. You can ask for our menu recommendations, check allergens, or place an order poh!'
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

