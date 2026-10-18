"""A calculator with a hidden vault behind it.

To a casual user it is a plain dark calculator. Enter the equation 6769÷6996
and press = and the window transforms into the vault browser.
"""

from __future__ import annotations

import os
import time

import customtkinter as ctk

import theme as T
from calc_engine import CalcError, evaluate, format_result, normalize, toggle_sign
from vault_ui import VaultFrame

SECRET_EQUATION = "6769/6996"          # after normalize()
CALCULATOR_GEOMETRY = "400x600"
VAULT_GEOMETRY = "980x620"
IDLE_LOCK_SECONDS = 300                # vault locks itself after 5 idle minutes

OPERATOR_CHARS = "+-×÷%^"


class CalculatorFrame(ctk.CTkFrame):
    def __init__(self, app: "App"):
        super().__init__(app, fg_color=T.BG, corner_radius=0)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=4)

        # display -----------------------------------------------------------
        display = ctk.CTkFrame(self, fg_color=T.SURFACE, corner_radius=16,
                               border_width=1, border_color=T.BORDER_SOFT)
        display.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 16))
        display.grid_columnconfigure(0, weight=1)

        self.history = ctk.CTkLabel(display, text="", anchor="e", justify="right",
                                    text_color=T.FAINT, font=(T.MONO, T.HISTORY_SIZE))
        self.history.grid(row=0, column=0, sticky="e", padx=20, pady=(14, 0))

        self.value = ctk.CTkLabel(display, text="0", anchor="e", justify="right",
                                  text_color=T.TEXT,
                                  font=(T.MONO, T.DISPLAY_SIZE, "bold"))
        self.value.grid(row=1, column=0, sticky="e", padx=20, pady=(0, 14))

        # keypad ------------------------------------------------------------
        keys = ctk.CTkFrame(self, fg_color="transparent")
        keys.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 20))
        for col in range(4):
            keys.grid_columnconfigure(col, weight=1)
        for row in range(5):
            keys.grid_rowconfigure(row, weight=1)

        layout = [
            [("AC", "fn"), ("⌫", "fn"), ("%", "op"), ("÷", "op")],
            [("7", "num"), ("8", "num"), ("9", "num"), ("×", "op")],
            [("4", "num"), ("5", "num"), ("6", "num"), ("−", "op")],
            [("1", "num"), ("2", "num"), ("3", "num"), ("+", "op")],
            [("±", "num"), ("0", "num"), (".", "num"), ("=", "eq")],
        ]
        for r, row_def in enumerate(layout):
            for c, (label, style) in enumerate(row_def):
                style = T.KEY_STYLES[style]
                ctk.CTkButton(
                    keys, text=label, corner_radius=T.KEY_RADIUS,
                    fg_color=style["fg_color"], hover_color=style["hover_color"],
                    text_color=style["text_color"],
                    font=(T.MONO, 19, "bold"),
                    command=lambda ch=label: self.app.press(ch),
                ).grid(row=r, column=c, sticky="nsew", padx=4, pady=4)

    # -- display -------------------------------------------------------------

    def show(self, buffer: str):
        self.value.configure(text=buffer if buffer else "0",
                             text_color=T.TEXT, font=(T.MONO, T.DISPLAY_SIZE, "bold"))

    def show_error(self, message: str):
        self.value.configure(text="Error", text_color=T.DANGER,
                             font=(T.MONO, T.DISPLAY_SIZE, "bold"))
        self.history.configure(text=message)
        self.after(1100, lambda: self.app.reset_display())

    def show_history(self, text: str):
        self.history.configure(text=text)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.mono = T.resolve_mono_family(self)

        self.title("Calculator")
        self.geometry(CALCULATOR_GEOMETRY)
        self.minsize(360, 540)
        self.configure(fg_color=T.BG)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.buffer = ""
        self.just_evaluated = False
        self.last_activity = time.time()
        self.idle_lock_seconds = IDLE_LOCK_SECONDS
        self._in_vault = False

        self.calculator = CalculatorFrame(self)
        self.calculator.grid(row=0, column=0, sticky="nsew")
        self.vault = VaultFrame(self)
        self.vault.grid(row=0, column=0, sticky="nsew")
        self.calculator.lift()

        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- input routing -------------------------------------------------------

    def _bind_keys(self):
        for digit in "0123456789":
            self.bind(digit, lambda _e, d=digit: self.press(d))
        for key, char in {
            ".": ".", "+": "+", "-": "−", "*": "×", "/": "÷",
            "%": "%", "^": "^", "=": "=",
        }.items():
            self.bind(key, lambda _e, c=char: self.press(c))
        for n in range(10):
            self.bind(f"<KP_{n}>", lambda _e, n=n: self.press(str(n)))
        self.bind("<KP_Add>", lambda _e: self.press("+"))
        self.bind("<KP_Subtract>", lambda _e: self.press("−"))
        self.bind("<KP_Multiply>", lambda _e: self.press("×"))
        self.bind("<KP_Divide>", lambda _e: self.press("÷"))
        self.bind("<KP_Decimal>", lambda _e: self.press("."))
        self.bind("<Return>", self._on_return)
        self.bind("<KP_Enter>", lambda _e: self.press("="))
        self.bind("<BackSpace>", lambda _e: self.press("⌫"))
        self.bind("<Delete>", lambda _e: self.press("AC"))
        self.bind("<Escape>", self._on_escape)
        self.bind("<Key>", lambda _e: setattr(self, "last_activity", time.time()))
        self.bind("<Button-1>", lambda _e: setattr(self, "last_activity", time.time()))

    def _on_return(self, _event=None):
        if self._in_vault:
            self.vault.handle_return()
        else:
            self.press("=")

    def _on_escape(self, _event=None):
        if self._in_vault:
            self.vault.handle_escape()
        else:
            self.press("AC")

    # -- calculator logic ----------------------------------------------------

    def press(self, char: str):
        if self._in_vault:
            return
        if char == "AC":
            self.buffer = ""
            self.just_evaluated = False
            self.calculator.show_history("")
        elif char == "⌫":
            self.buffer = self.buffer[:-1]
            self.just_evaluated = False
        elif char == "=":
            self._evaluate()
            return
        elif char == "±":
            self.buffer = toggle_sign(self.buffer)
        elif char in OPERATOR_CHARS:
            if not self.buffer and char not in "-%":
                return
            if self.buffer and self.buffer[-1] in OPERATOR_CHARS:
                self.buffer = self.buffer[:-1] + char
            else:
                self.buffer += char
            self.just_evaluated = False
        else:  # digit or dot
            if self.just_evaluated:
                self.buffer = ""
                self.just_evaluated = False
            if char == ".":
                tail = self.buffer.rsplit("(-", 1)[-1]
                if "." in tail:
                    return
                if not tail or not tail[-1].isdigit():
                    char = "0."
            self.buffer += char
        self.calculator.show(self.buffer)

    def _evaluate(self):
        if not self.buffer:
            return
        if normalize(self.buffer) == SECRET_EQUATION:
            self.enter_vault()
            return
        try:
            result = evaluate(self.buffer)
        except CalcError as exc:
            self.calculator.show_error(str(exc))
            self.buffer = ""
            self.just_evaluated = False
            return
        self.calculator.show_history(f"{self.buffer} =")
        self.buffer = format_result(result)
        self.just_evaluated = True
        self.calculator.show(self.buffer)

    def reset_display(self):
        self.calculator.show(self.buffer)
        self.calculator.show_history("")

    # -- screen switching ----------------------------------------------------

    def enter_vault(self):
        self.buffer = ""
        self.just_evaluated = False
        self.calculator.show("")
        self.calculator.show_history("")
        self._in_vault = True
        self.geometry(VAULT_GEOMETRY)
        self.minsize(720, 520)
        self.vault.lift()

    def leave_vault(self):
        self._in_vault = False
        self.geometry(CALCULATOR_GEOMETRY)
        self.minsize(360, 540)
        self.calculator.lift()

    def on_vault_entered(self):
        pass

    # -- safety --------------------------------------------------------------

    def _on_close(self):
        if self.vault.unlocked:
            self.vault.store.close()
        self.destroy()


def main():
    app = App()
    if os.environ.get("SPC_SMOKE"):  # used by automated smoke tests
        app.after(1500, app.destroy)
    app.mainloop()


if __name__ == "__main__":
    main()
