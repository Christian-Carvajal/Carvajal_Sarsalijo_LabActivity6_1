"""
virtual_waiter_prototype.py
Executable CLI application running the interactive Perpetual Bistro Waiter Agent loop.
Powered by local Ollama (qwen3.5:4b), FSM dialogue state machine, and SQLite (restaurant.db).
Includes Voice I/O abstraction layer (get_input / send_output) per Lesson 6 Subtopic 6.5.
"""

import sys
import os
import time
import json
from typing import Optional

# Ensure 01_Work_In_Progress is on python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt
from rich import box

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

console = Console()

# =====================================================================
# Subtopic 6.5: Voice I/O Decoupling & Architecture Integration
# Wraps core agent in generic get_input() and send_output() functions
# =====================================================================

class IOChannel:
    """Abstracted I/O Layer allowing drop-in swap between Terminal and Audio/Speech STT/TTS."""

    def __init__(self, voice_simulation: bool = False):
        self.voice_simulation = voice_simulation

    def get_input(self, prompt_text: str = "Customer") -> str:
        """
        Generic input acquisition.
        In terminal mode: captures user keystrokes.
        In voice mode: can hook directly to Whisper / Silero VAD microphone stream.
        """
        return Prompt.ask(f"[bold cyan]{prompt_text}[/bold cyan]").strip()

    def send_output(self, speaker: str, message: str, fsm_state: str = "") -> None:
        """
        Generic output dispatch.
        In terminal mode: renders rich formatted speech panels.
        In voice mode: routes text to pyttsx3 / Edge-TTS audio stream.
        """
        state_color = {
            STATE_GREETING: "yellow",
            STATE_MENU_BROWSING: "blue",
            STATE_TAKING_ORDER: "green",
            STATE_REVIEW: "magenta",
            STATE_CONFIRMED: "bold green",
        }.get(fsm_state, "white")

        panel_title = f"[bold green]{speaker}[/bold green] [dim]({fsm_state})[/dim]"
        console.print(
            Panel(
                message,
                title=panel_title,
                border_style=state_color,
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

        if self.voice_simulation:
            # Simulated speech synthesis indicator
            console.print("[dim italic]🔊 [TTS Voice Stream Playing...] [/dim italic]")
            time.sleep(0.3)


def render_header(table_no: int, session_id: str, state: str, model: str) -> None:
    """Renders the top bistro banner and state machine badge."""
    state_style = {
        STATE_GREETING: "bold yellow on black",
        STATE_MENU_BROWSING: "bold blue on black",
        STATE_TAKING_ORDER: "bold green on black",
        STATE_REVIEW: "bold magenta on black",
        STATE_CONFIRMED: "bold white on dark_green",
    }.get(state, "bold white")

    title = Text(" 🍽️  PERPETUAL BISTRO — DIGITAL TABLE-SIDE ORDERING AGENT ", style="bold white on navy_blue")
    console.print(Panel(title, box=box.HEAVY, style="navy_blue", padding=(0, 2)))

    meta_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    meta_table.add_row(
        f"[bold]Campus Facility:[/bold] Perpetual Help DALTA",
        f"[bold]Table No:[/bold] #{table_no}",
        f"[bold]Session ID:[/bold] {session_id}",
    )
    meta_table.add_row(
        f"[bold]Local Engine:[/bold] Ollama ({model})",
        f"[bold]Database:[/bold] SQLite (restaurant.db)",
        f"[bold]Active FSM State:[/bold] [{state_style}] {state} [/{state_style}]",
    )
    console.print(meta_table)
    console.print("[dim]Type your message, or enter [bold]/menu[/bold], [bold]/cart[/bold], [bold]/confirm[/bold], [bold]/demo[/bold], or [bold]/exit[/bold].[/dim]\n")


def render_order_cart(cart: dict) -> None:
    """Renders the real-time order cart table synced to SQLite."""
    items = cart.get("line_items", [])
    if not items:
        console.print("[italic dim]🛒 Cart is currently empty. Start ordering by telling BistroBot what you'd like![/italic dim]\n")
        return

    table = Table(
        title=f"📋 Active Order Tab — Table #{cart.get('table_no')} (State: {cart.get('fsm_state')})",
        box=box.ROUNDED,
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("#", justify="center", style="dim", width=4)
    table.add_column("Item Name", style="bold white")
    table.add_column("Category", style="dim")
    table.add_column("Qty", justify="center", style="bold yellow")
    table.add_column("Special Instructions", style="italic magenta")
    table.add_column("Unit Price", justify="right")
    table.add_column("Total", justify="right", style="bold green")

    for idx, it in enumerate(items, 1):
        instructions = it.get("special_instructions") or "[dim]Standard[/dim]"
        table.add_row(
            str(idx),
            it["name"],
            it["category"],
            str(it["quantity"]),
            instructions,
            f"₱{it['unit_price']:.2f}",
            f"₱{it['line_total']:.2f}",
        )

    console.print(table)
    subtotal = cart.get("subtotal", 0.0)
    vat = cart.get("vat_12_pct_breakdown", 0.0)
    total = cart.get("grand_total", 0.0)

    summary_text = (
        f"[bold]Items:[/bold] {cart.get('item_count')}  |  "
        f"[bold]Subtotal:[/bold] ₱{subtotal:.2f}  |  "
        f"[bold]12% VAT Included:[/bold] ₱{vat:.2f}  |  "
        f"[bold green]Grand Total:[/bold green] [bold green]₱{total:.2f}[/bold green]"
    )
    console.print(Panel(summary_text, box=box.ROUNDED, style="green", padding=(0, 2)))
    console.print()


def render_receipt(receipt: dict) -> None:
    """Renders digital checkout receipt modal when state reaches STATE_CONFIRMED."""
    console.print("\n" + "=" * 60)
    receipt_table = Table(
        title="🧾 PERPETUAL BISTRO — OFFICIAL DIGITAL ORDER RECEIPT",
        box=box.DOUBLE,
        header_style="bold green",
        style="green",
    )
    receipt_table.add_column("Item", style="bold white")
    receipt_table.add_column("Qty", justify="center")
    receipt_table.add_column("Instructions", style="italic")
    receipt_table.add_column("Amount", justify="right", style="bold")

    for it in receipt.get("itemized_receipt", []):
        receipt_table.add_row(
            it["name"],
            str(it["quantity"]),
            it.get("special_instructions") or "-",
            f"₱{it['line_total']:.2f}",
        )

    console.print(receipt_table)
    summary_panel = (
        f"[bold]Receipt ID:[/bold] {receipt.get('receipt_id')}\n"
        f"[bold]Table Number:[/bold] #{receipt.get('table_no')}\n"
        f"[bold]Session ID:[/bold] {receipt.get('session_id')}\n"
        f"[bold]Subtotal:[/bold] ₱{receipt.get('subtotal', 0.0):.2f}\n"
        f"[bold]12% VAT Component:[/bold] ₱{receipt.get('vat_included', 0.0):.2f}\n"
        f"[bold green]AMOUNT PAID / BILLED:[/bold green] [bold green]₱{receipt.get('grand_total', 0.0):.2f}[/bold green]\n\n"
        f"[bold italic cyan]Status:[/bold italic cyan] Transaction committed to restaurant.db. Inventory deducted."
    )
    console.print(Panel(summary_panel, title="[bold]CHECKOUT SUCCESSFUL[/bold]", box=box.HEAVY, style="bold green"))
    console.print("=" * 60 + "\n")


def run_interactive_waiter(table_no: int = 1, model: str = DEFAULT_MODEL) -> None:
    """Runs the primary interactive CLI agent loop."""
    # Ensure database is initialized
    db_tools.init_db()

    # Initialize FSM agent
    agent = BistroFSMAgent(table_no=table_no, model=model)
    io = IOChannel(voice_simulation=False)

    console.clear()
    render_header(agent.table_no, agent.session_id, agent.state, agent.model)

    # Initial Welcome Greeting
    welcome_text = (
        f"Mabuhay and welcome to Perpetual Bistro! I am BistroBot, your virtual dining assistant for Table #{agent.table_no}.\n"
        "How may I serve you today? Feel free to ask about our menu categories, allergen details, or place an order!"
    )
    io.send_output("BistroBot", welcome_text, agent.state)

    while True:
        try:
            user_input = io.get_input("Customer")
            if not user_input:
                continue

            # Command shortcuts
            cmd = user_input.strip().lower()
            if cmd in ["/exit", "exit", "quit"]:
                console.print("\n[yellow]Thank you for visiting Perpetual Bistro! Have a great day.[/yellow]")
                break

            elif cmd in ["/cart", "/bill", "cart", "bill"]:
                cart = db_tools.view_current_order(agent.session_id)
                render_order_cart(cart)
                continue

            elif cmd in ["/menu", "menu"]:
                menu_data = db_tools.get_menu_by_category("all")
                console.print(Panel("\n".join([f"- {i['name']} (₱{i['price']:.2f}) [{i['category']}] - {i['description']}" for i in menu_data["items"]]), title="[bold cyan]Perpetual Bistro Menu[/bold cyan]"))
                continue

            elif cmd in ["/confirm", "confirm"]:
                user_input = "Please confirm and place my order now."

            elif cmd in ["/demo", "demo"]:
                run_autonomous_demo(agent, io)
                break

            # Process conversational turn
            console.print("[dim]Thinking & checking database tools...[/dim]")
            turn = agent.process_turn(user_input)

            # Display any tool calls executed behind the scenes
            if turn["tool_calls"]:
                tools_used = ", ".join([f"[cyan]{tc['tool']}[/cyan]" for tc in turn["tool_calls"]])
                console.print(f"[dim]⚙️ Database Tools Bound: {tools_used}[/dim]")

            # Render assistant speech
            io.send_output("BistroBot", turn["assistant_response"], turn["fsm_state"])

            # If state reached CONFIRMED, print receipt
            if turn["fsm_state"] == STATE_CONFIRMED:
                for tc in turn["tool_calls"]:
                    if tc["tool"] == "confirm_order_and_deduct_stock" and tc["result"].get("status") == "success":
                        render_receipt(tc["result"])
                        break

            # Render updated cart summary
            render_order_cart(turn["cart"])

        except KeyboardInterrupt:
            console.print("\n[yellow]Session terminated by user.[/yellow]")
            break
        except Exception as e:
            console.print(f"[bold red]Error in conversation step: {str(e)}[/bold red]")

    # Export session log to sample_conversation_log.json
    export_path = os.path.join(os.path.dirname(__file__), "sample_conversation_log.json")
    agent.export_audit_log(export_path)
    console.print(f"[dim green]✓ Session conversation log saved to {export_path}[/dim green]")


def run_autonomous_demo(agent: BistroFSMAgent, io: IOChannel) -> None:
    """Executes a complete 7-turn scripted demonstration of the FSM ordering agent."""
    console.print(Panel("[bold yellow]RUNNING SCRIPTED MULTI-TURN DEMONSTRATION OF PERPETUAL BISTRO FSM[/bold yellow]"))

    scenario = [
        "Hello! What burger options do you have today?",
        "Does the Perpetual Classic Burger have dairy? I have a mild lactose intolerance.",
        "Alright, please add one Perpetual Classic Burger with extra cheese and no onions, and one Loaded Cheese Fries.",
        "Can you also add one Crispy Buffalo Chicken Tenders?",
        "Since tenders are out of stock, what drinks do you have? Add one Iced Caramel Macchiato instead.",
        "Can I see my current bill and review the tab?",
        "Everything looks great, please confirm and place my order."
    ]

    for turn_idx, text in enumerate(scenario, 1):
        console.print(f"\n[bold yellow]--- TURN {turn_idx} ---[/bold yellow]")
        console.print(f"[bold cyan]Customer:[/bold cyan] {text}")
        turn = agent.process_turn(text)

        if turn["tool_calls"]:
            tools_used = ", ".join([f"[cyan]{tc['tool']}[/cyan]" for tc in turn["tool_calls"]])
            console.print(f"[dim]⚙️ Database Tools Bound: {tools_used}[/dim]")

        io.send_output("BistroBot", turn["assistant_response"], turn["fsm_state"])
        render_order_cart(turn["cart"])

        if turn["fsm_state"] == STATE_CONFIRMED:
            for tc in turn["tool_calls"]:
                if tc["tool"] == "confirm_order_and_deduct_stock" and tc["result"].get("status") == "success":
                    render_receipt(tc["result"])

        time.sleep(0.5)

    export_path = os.path.join(os.path.dirname(__file__), "sample_conversation_log.json")
    agent.export_audit_log(export_path)
    console.print(f"\n[bold green]✓ Demo complete! Multi-turn telemetry exported to {export_path}[/bold green]")


if __name__ == "__main__":
    table = 1
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        table = int(sys.argv[1])
    run_interactive_waiter(table_no=table)
