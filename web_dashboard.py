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
from fastapi.staticfiles import StaticFiles
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

# Mount static files directory
STATIC_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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


class KdsStatusRequest(BaseModel):
    ticket_id: str
    status: str


class PaymentCheckoutRequest(BaseModel):
    payment_method: str  # GCASH, STUDENT_CARD, CASH
    payment_ref: Optional[str] = ""
    student_id: Optional[str] = ""
    table_no: Optional[int] = None


class RestockRequest(BaseModel):
    item_name: Optional[str] = None
    qty: Optional[int] = 10
    restock_all: Optional[bool] = False
    target_min: Optional[int] = 20


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
    global active_agent
    db_tools.create_or_get_session(active_agent.table_no, active_agent.session_id)
    res = active_agent.execute_tool("confirm_order_and_deduct_stock", {})
    cart = db_tools.view_current_order(active_agent.session_id)
    return {"receipt": res, "cart": cart, "fsm_state": active_agent.state}


@app.get("/api/kds/tickets")
def get_kds_tickets(status: Optional[str] = None):
    """Retrieves all active kitchen fulfillment tickets."""
    return {"status": "success", "tickets": db_tools.get_kitchen_tickets(status_filter=status)}


@app.post("/api/kds/status")
def update_kds_ticket_status(req: KdsStatusRequest):
    """Updates the kitchen fulfillment status (PREPARING -> READY -> SERVED)."""
    ok = db_tools.update_kitchen_ticket_status(req.ticket_id, req.status)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid ticket status or ticket not found.")
    return {"status": "success", "ticket_id": req.ticket_id, "new_status": req.status}


@app.post("/api/payment/checkout")
def process_payment_and_checkout(req: PaymentCheckoutRequest):
    """Finalizes table order with selected payment method and dispatches kitchen ticket."""
    global active_agent
    if req.table_no and req.table_no != active_agent.table_no:
        active_agent.set_table_number(req.table_no)

    db_tools.create_or_get_session(active_agent.table_no, active_agent.session_id)

    # 1. Deduct stock & confirm FSM
    res = active_agent.execute_tool("confirm_order_and_deduct_stock", {})
    if res.get("status") != "success":
        return {"status": "error", "message": res.get("message", "Payment processing aborted.")}

    # 2. Update the created ticket with chosen payment details
    ticket_id = res.get("receipt_id")
    pay_ref = req.payment_ref or (f"STU-{req.student_id}" if req.student_id else "CASH-COUNTER")
    db_tools.create_kitchen_ticket(
        table_no=active_agent.table_no,
        session_id=active_agent.session_id,
        items=res.get("itemized_receipt", []),
        grand_total=res.get("grand_total", 0.0),
        payment_method=req.payment_method.upper(),
        payment_ref=pay_ref,
        ticket_id=ticket_id
    )

    cart = db_tools.view_current_order(active_agent.session_id)
    res["payment_method"] = req.payment_method.upper()
    res["payment_ref"] = pay_ref
    return {
        "status": "success",
        "receipt": res,
        "cart": cart,
        "fsm_state": active_agent.state
    }


@app.get("/api/admin/analytics")
def get_admin_analytics():
    """Returns real-time sales revenue, ticket throughput, and inventory status."""
    return db_tools.get_analytics_summary()


@app.post("/api/admin/restock")
def restock_inventory(req: RestockRequest):
    """Restocks inventory items for restaurant managers."""
    if req.restock_all:
        target = req.target_min or 20
        res = db_tools.restock_all_items(target_min_qty=target)
    else:
        if not req.item_name:
            raise HTTPException(status_code=400, detail="item_name required when restock_all is false.")
        res = db_tools.restock_menu_item(req.item_name, qty_to_add=req.qty or 10)
    return res


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


TEMPLATES_INDEX = os.path.join(os.path.dirname(__file__), "templates", "index.html")

@app.get("/", response_class=HTMLResponse)
def index_page():
    """Serves the complete single-page interactive tablet dashboard."""
    if os.path.exists(TEMPLATES_INDEX):
        with open(TEMPLATES_INDEX, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Perpetual Bistro Kiosk</h1><p>Please ensure templates/index.html exists.</p>")


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
