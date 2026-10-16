"""
fsm_agent.py
Conversational Finite State Machine (FSM) Controller and Dynamic Tool Calling Engine.
Powered by local Ollama (qwen3.5:4b) and SQLite (restaurant.db).
"""

import json
import os
import re
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional, Tuple

import db_tools

OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://127.0.0.1:11434/api/chat")

def select_best_model() -> str:
    """Dynamically detects best available model without exceeding laptop VRAM limits."""
    if "OLLAMA_MODEL" in os.environ:
        return os.environ["OLLAMA_MODEL"]
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            installed = [m.get("name", "") for m in data.get("models", [])]
            # Prioritize qwen2.5:1.5b to prevent cudaMalloc OOM on 4GB/6GB laptop GPUs
            for cand in ["qwen2.5:1.5b", "qwen3.5:4b", "jarvis-trained-model:latest"]:
                for m in installed:
                    if cand in m:
                        return m
            if installed:
                return installed[0]
    except Exception:
        pass
    return "qwen2.5:1.5b"

DEFAULT_MODEL = select_best_model()

# 5 Discrete FSM States
STATE_GREETING = "STATE_GREETING"
STATE_MENU_BROWSING = "STATE_MENU_BROWSING"
STATE_TAKING_ORDER = "STATE_TAKING_ORDER"
STATE_REVIEW = "STATE_REVIEW"
STATE_CONFIRMED = "STATE_CONFIRMED"

# Tool JSON schemas for Ollama Function Calling
BISTRO_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_menu_by_category",
            "description": "Retrieve menu items from Perpetual Bistro, optionally filtered by category (Burgers, Pastas, Sides, Beverages, Desserts, or 'all').",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Category name such as Burgers, Pastas, Sides, Beverages, Desserts, or 'all'."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_item_allergen",
            "description": "Check if a menu item contains a specific allergen like Dairy, Gluten, Nuts, Egg, Pork, or Shellfish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "Name of the bistro menu item."
                    },
                    "allergen": {
                        "type": "string",
                        "description": "Specific allergen to verify."
                    }
                },
                "required": ["item_name", "allergen"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Verify current inventory and stock availability for a menu item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "Name of the menu item."
                    },
                    "qty": {
                        "type": "integer",
                        "description": "Quantity requested (defaults to 1)."
                    }
                },
                "required": ["item_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_item_to_order",
            "description": "Add an item to the customer's active order tab with specified quantity and special instructions/customizations (e.g., 'extra cheese', 'no onions').",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "Name of the menu item to add."
                    },
                    "qty": {
                        "type": "integer",
                        "description": "Quantity to add (e.g. 1, 2)."
                    },
                    "instructions": {
                        "type": "string",
                        "description": "Customer special instructions or dietary modifications (e.g. 'no onions', 'extra spicy')."
                    }
                },
                "required": ["item_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remove_item_from_order",
            "description": "Remove an item completely from the customer's current order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "Name of the menu item to remove."
                    }
                },
                "required": ["item_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_item_quantity",
            "description": "Modify the quantity of an item already in the order cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "Name of the menu item."
                    },
                    "qty": {
                        "type": "integer",
                        "description": "New desired quantity."
                    }
                },
                "required": ["item_name", "qty"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "view_current_order",
            "description": "View the customer's current itemized tab, subtotal, tax breakdown, and grand total.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_order_and_deduct_stock",
            "description": "Finalize and commit the order to the database, deduct inventory stock, and generate an official receipt.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_dialogue_state",
            "description": "Transition the conversational FSM state based on the customer's dialogue phase (e.g. STATE_MENU_BROWSING when asking about food, STATE_TAKING_ORDER when selecting dishes, STATE_REVIEW when asking for the bill, STATE_CONFIRMED on checkout).",
            "parameters": {
                "type": "object",
                "properties": {
                    "new_state": {
                        "type": "string",
                        "enum": ["STATE_GREETING", "STATE_MENU_BROWSING", "STATE_TAKING_ORDER", "STATE_REVIEW", "STATE_CONFIRMED"],
                        "description": "The destination FSM state."
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this transition occurred based on customer input."
                    }
                },
                "required": ["new_state"]
            }
        }
    }
]


class BistroFSMAgent:
    """
    Stateful Conversational Finite State Machine Agent.
    Manages session memory, dialogue state transitions, and Ollama tool binding.
    """

    def __init__(
        self,
        table_no: int = 1,
        session_id: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        db_path: str = db_tools.DB_PATH,
        language: str = "filipino",
    ):
        self.table_no = table_no
        self.model = model
        self.db_path = db_path
        self.language = language.lower().strip()
        self.session = db_tools.create_or_get_session(table_no, session_id, db_path=self.db_path)
        self.session_id = self.session["session_id"]
        self.state = self.session["status"] or STATE_GREETING
        self.messages: List[Dict[str, Any]] = []
        self.audit_log: List[Dict[str, Any]] = []
        self._init_system_prompt()

    def _init_system_prompt(self) -> None:
        """Constructs the authoritative system prompt with conversational flexibility and guardrails."""
        if self.language == "english":
            language_rule = (
                "6. LANGUAGE & TONE: Speak in fluent, professional, courteous English. "
                "Be welcoming, helpful, and clear. Maintain friendly dining hospitality at all times.\n"
            )
        else:
            language_rule = (
                "6. NATURAL TAGLISH & TONE: Speak in natural, modern conversational Taglish (the casual bilingual English-Tagalog spoken in Metro Manila college campus bistros). "
                "Use English for table numbers and tech names (say 'Table 1', 'Qwen 3.5', '150 pesos', 'Mabuhay po!'). "
                "NEVER use archaic, deep pure Tagalog (never say 'mesa isa' or 'tatlong punto lima'). Be friendly, natural, and welcoming.\n"
            )

        system_content = (
            "You are 'BistroBot', the intelligent, friendly, conversational AI table-side waiter at Perpetual Bistro, "
            "University of Perpetual Help System DALTA.\n"
            f"You are actively serving Table #{self.table_no} (Session ID: {self.session_id}).\n\n"
            "NATURAL CONVERSATION & INTELLIGENCE GUIDELINES:\n"
            "1. CONVERSE DYNAMICALLY LIKE CHATGPT: Answer questions spontaneously on the spot. If a customer chats, "
            "asks what you personally recommend, asks for pairing ideas, jokes about food, or asks general dining questions, "
            "respond warmly, naturally, and intelligently in your own words. Never sound robotic or scripted.\n"
            "2. CURRENCY RULE: All prices in Perpetual Bistro are strictly in Philippine Pesos (PHP, ₱). "
            "Always state prices simply as 'pesos' or '₱' (e.g., '150 pesos' or '₱150.00'). "
            "NEVER say 'Cuban pesos', 'Mexican pesos', or any foreign currency denomination.\n"
            "3. STATE MACHINE CONTEXT:\n"
            f"   - Current FSM State: {self.state}.\n"
            "   - When customer browses menu or asks about dishes: explore using `get_menu_by_category` or `check_item_allergen` (STATE_MENU_BROWSING).\n"
            "   - When customer wants to order: invoke `add_item_to_order` with their requested quantity and customizations (STATE_TAKING_ORDER).\n"
            "   - When customer asks about their bill, current tab, or summary: call `view_current_order` to present their bill (STATE_REVIEW).\n"
            "   - When customer confirms or says they are ready to finalize: call `confirm_order_and_deduct_stock` (STATE_CONFIRMED).\n"
            "   - You can also call `set_dialogue_state` to transition the state whenever appropriate.\n"
            "4. TOOL CALLING AUTONOMY: Autonomously call the tools whenever needed to fetch real database data. "
            "Do not guess or hallucinate menu prices or inventory counts.\n"
            "5. OUT-OF-STOCK POLICY: If an item is out of stock (such as Crispy Buffalo Chicken Tenders), explain politely and suggest in-stock alternatives from the same category.\n"
            + language_rule +
            "7. EMOJI AND SPEECH CLEANLINESS: Do not use emojis in your responses. Keep text clean and verbal so text-to-speech audio speaks words cleanly without describing symbols."
        )
        self.messages = [{"role": "system", "content": system_content}]

    def set_language(self, new_lang: str) -> None:
        """Updates the active persona language ('filipino' or 'english')."""
        self.language = new_lang.lower().strip()
        self._init_system_prompt()

    def set_table_number(self, new_table_no: int) -> None:
        """Updates the active table number."""
        self.table_no = new_table_no
        self.session = db_tools.create_or_get_session(new_table_no, self.session_id, db_path=self.db_path)
        self._init_system_prompt()

    def transition_state(self, new_state: str, reason: str = "") -> None:
        """Executes a formal FSM state transition and persists it in SQLite."""
        old_state = self.state
        self.state = new_state
        db_tools.set_session_status(self.session_id, new_state, db_path=self.db_path)
        transition_record = {
            "from_state": old_state,
            "to_state": new_state,
            "reason": reason,
            "turn_index": len(self.messages),
        }
        self.audit_log.append({"type": "state_transition", "data": transition_record})
        # Update system prompt to reflect current state
        self.messages[0]["content"] = re.sub(
            r"Current FSM State: \w+",
            f"Current FSM State: {self.state}",
            self.messages[0]["content"]
        )

    def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches an Ollama tool call to the corresponding db_tools function."""
        # Sanitize arguments and inject session_id where required
        if tool_name == "set_dialogue_state":
            new_st = args.get("new_state", self.state)
            reason = args.get("reason", "Model-directed state transition")
            self.transition_state(new_st, reason=reason)
            return {"status": "success", "current_state": self.state}

        elif tool_name == "get_menu_by_category":
            category = args.get("category")
            if self.state == STATE_GREETING:
                self.transition_state(STATE_MENU_BROWSING, reason="Customer inquiring about menu")
            return db_tools.get_menu_by_category(category, db_path=self.db_path)

        elif tool_name == "check_item_allergen":
            item = args.get("item_name", "")
            allergen = args.get("allergen", "")
            if self.state == STATE_GREETING:
                self.transition_state(STATE_MENU_BROWSING, reason="Customer allergen query")
            return db_tools.check_item_allergen(item, allergen, db_path=self.db_path)

        elif tool_name == "check_availability":
            item = args.get("item_name", "")
            qty = int(args.get("qty", 1))
            return db_tools.check_availability(item, qty, db_path=self.db_path)

        elif tool_name == "add_item_to_order":
            item = args.get("item_name", "")
            qty = int(args.get("qty", 1))
            instructions = args.get("instructions", "")
            res = db_tools.add_item_to_order(self.session_id, item, qty, instructions, db_path=self.db_path)
            if res.get("status") == "success":
                self.transition_state(STATE_TAKING_ORDER, reason=f"Item added: {item}")
            return res

        elif tool_name == "remove_item_from_order":
            item = args.get("item_name", "")
            res = db_tools.remove_item_from_order(self.session_id, item, db_path=self.db_path)
            self.transition_state(STATE_TAKING_ORDER, reason=f"Item removed: {item}")
            return res

        elif tool_name == "update_item_quantity":
            item = args.get("item_name", "")
            qty = int(args.get("qty", 1))
            res = db_tools.update_item_quantity(self.session_id, item, qty, db_path=self.db_path)
            self.transition_state(STATE_TAKING_ORDER, reason=f"Quantity updated: {item}")
            return res

        elif tool_name == "view_current_order":
            res = db_tools.view_current_order(self.session_id, db_path=self.db_path)
            self.transition_state(STATE_REVIEW, reason="Customer reviewing bill tab")
            return res

        elif tool_name == "confirm_order_and_deduct_stock":
            res = db_tools.confirm_order_and_deduct_stock(self.session_id, db_path=self.db_path)
            if res.get("status") == "success":
                self.transition_state(STATE_CONFIRMED, reason="Order committed and inventory deducted")
            return res

        else:
            return {"status": "error", "message": f"Unknown tool name: {tool_name}"}

    def _call_ollama_chat(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Sends HTTP request to local Ollama /api/chat endpoint."""
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            OLLAMA_API_URL,
            data=data_bytes,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama connection error at {OLLAMA_API_URL}: {str(e)}")

    def process_turn(self, user_input: str) -> Dict[str, Any]:
        """
        Executes a single conversational multi-turn dialogue step:
        1. Appends user input to conversation history.
        2. Calls Qwen model with available tool definitions (NO hard-coded regex).
        3. Model autonomously decides whether to converse naturally or trigger tools.
        4. Detects and executes tool calls recursively until final response is generated.
        5. Logs step telemetry.
        """
        # Append user message directly (no regex pre-filtering)
        self.messages.append({"role": "user", "content": user_input})
        turn_tool_calls: List[Dict[str, Any]] = []

        max_tool_iterations = 5
        iteration = 0
        final_content = ""
        model_thinking = ""

        while iteration < max_tool_iterations:
            iteration += 1

            payload = {
                "model": self.model,
                "messages": self.messages,
                "tools": BISTRO_TOOLS,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_ctx": 8192,
                }
            }

            resp = self._call_ollama_chat(payload)
            assistant_msg = resp.get("message", {})
            raw_content = assistant_msg.get("content", "")
            thinking = assistant_msg.get("thinking", "")
            if thinking:
                model_thinking += ("\n" + thinking if model_thinking else thinking)

            tool_calls = assistant_msg.get("tool_calls", [])

            # Fallback regex for models that emit tool calls inside markdown code blocks
            if not tool_calls and "```json" in raw_content and '"name":' in raw_content:
                try:
                    match = re.search(r"```json\s*(\{.*?\})\s*```", raw_content, re.DOTALL)
                    if match:
                        parsed = json.loads(match.group(1))
                        if "name" in parsed and "arguments" in parsed:
                            tool_calls = [{"function": parsed}]
                except Exception:
                    pass

            if not tool_calls:
                # No tool calls; final assistant response reached
                final_content = raw_content
                self.messages.append({"role": "assistant", "content": final_content})
                break

            # Handle Tool Calls
            # Append assistant message with tool_calls to conversation history
            self.messages.append(assistant_msg)

            for tc in tool_calls:
                fn_info = tc.get("function", {})
                fn_name = fn_info.get("name", "")
                fn_args = fn_info.get("arguments", {})
                if isinstance(fn_args, str):
                    try:
                        fn_args = json.loads(fn_args)
                    except Exception:
                        fn_args = {}

                # Execute local Python function
                tool_result = self.execute_tool(fn_name, fn_args)
                turn_tool_calls.append({
                    "tool": fn_name,
                    "arguments": fn_args,
                    "result": tool_result,
                })

                # Append tool output message
                tool_msg = {
                    "role": "tool",
                    "name": fn_name,
                    "content": json.dumps(tool_result, ensure_ascii=False)
                }
                self.messages.append(tool_msg)

        # Clean any leftover thinking tags from final user-facing text
        clean_text = re.sub(r"<think>.*?</think>", "", final_content, flags=re.DOTALL).strip()
        
        # Robust synthesis if model exited tool loop without conversational text
        if not clean_text and turn_tool_calls:
            synthesis_parts = []
            for tc in turn_tool_calls:
                t_name = tc["tool"]
                t_res = tc["result"]
                if t_name == "confirm_order_and_deduct_stock" and t_res.get("status") == "success":
                    synthesis_parts.append(
                        f"🎉 **Order Confirmed!** (Receipt #{t_res.get('receipt_id')})\n"
                        f"Your order for Table #{t_res.get('table_no')} has been sent to the kitchen!\n"
                        f"**Subtotal:** ₱{t_res.get('subtotal'):.2f} | **Total:** ₱{t_res.get('grand_total'):.2f}\n"
                        f"Thank you for dining with Perpetual Bistro! Your food will be served shortly."
                    )
                elif t_name == "view_current_order" and t_res.get("status") == "success":
                    items_desc = "\n".join([f"- {it['quantity']}x {it['name']} (₱{it['line_total']:.2f})" for it in t_res.get("line_items", [])])
                    synthesis_parts.append(
                        f"Here is your current order for Table #{t_res.get('table_no')}:\n{items_desc}\n\n"
                        f"**Subtotal:** ₱{t_res.get('subtotal'):.2f} (12% VAT included: ₱{t_res.get('vat_12_pct_breakdown'):.2f})\n"
                        f"**Grand Total:** ₱{t_res.get('grand_total'):.2f}\n\nWould you like to confirm this order or make any changes?"
                    )
                elif t_name == "add_item_to_order":
                    synthesis_parts.append(t_res.get("message", "Item updated in your order."))
                elif t_name == "remove_item_from_order":
                    synthesis_parts.append(t_res.get("message", "Item removed."))
                elif t_name == "get_menu_by_category" and t_res.get("status") == "success":
                    item_names = ", ".join([it['name'] + f" (₱{it['price']:.2f})" for it in t_res.get("items", [])])
                    synthesis_parts.append(f"Here are the items available in {t_res.get('category_queried')}: {item_names}")
            clean_text = "\n\n".join(synthesis_parts)

        if not clean_text:
            clean_text = final_content.strip() or "How can I assist you with your Perpetual Bistro order?"

        # Compile turn response
        cart_state = db_tools.view_current_order(self.session_id, db_path=self.db_path)
        turn_data = {
            "session_id": self.session_id,
            "table_no": self.table_no,
            "fsm_state": self.state,
            "user_input": user_input,
            "assistant_response": clean_text,
            "thinking": model_thinking.strip(),
            "tool_calls": turn_tool_calls,
            "cart": cart_state,
        }

        self.audit_log.append({"type": "dialogue_turn", "data": turn_data})
        return turn_data

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Returns the full message list for auditing and logging."""
        return self.messages

    def export_audit_log(self, filepath: str) -> None:
        """Saves session audit trail to JSON."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({
                "session_id": self.session_id,
                "table_no": self.table_no,
                "fsm_state": self.state,
                "model": self.model,
                "audit_trail": self.audit_log,
                "final_cart": db_tools.view_current_order(self.session_id, db_path=self.db_path)
            }, f, indent=2, ensure_ascii=False)
