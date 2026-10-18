"""The vault: a VS Code style file explorer with a Google Drive style preview.

Shown only when the calculator receives its secret equation. Three stacked
screens (setup / lock / browser) — the browser is an icon rail plus an
explorer sidebar plus a preview pane, with a VS Code style status bar.
"""

from __future__ import annotations

import threading
import time
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox

import customtkinter as ctk

import icons
import theme as T
from file_types import viewer_for
from vault_store import (
    ItemInfo,
    VaultError,
    VaultStore,
    WrongPassphrase,
    human_size,
)
from viewer import ViewerFrame

COOLDOWN_SECONDS = 30
COOLDOWN_AFTER = 5   # failed attempts before a timed cooldown
WIPE_AFTER = 10      # failed attempts before the vault destroys itself


class VaultFrame(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app, fg_color=T.BG, corner_radius=0)
        self.app = app
        self.store = VaultStore()
        self.unlocked = False
        self.items: list[ItemInfo] = []
        self.selected_id: int | None = None
        self._cooldown_until = 0.0
        self._cooldown_job = None
        self._tick_job = None
        self._total_size = 0

        # three stacked screens — all gridded, only one lifted at a time
        self.lock_screen = self._build_lock_screen()
        self.setup_screen = self._build_setup_screen()
        self.main_screen = self._build_main_screen()
        for screen in (self.lock_screen, self.setup_screen, self.main_screen):
            screen.grid(row=0, column=0, sticky="nsew")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.show_gate()

    # ------------------------------------------------------------------ gate

    def show_gate(self):
        if self.store.exists():
            self.lock_screen.lift()
            self.after(50, self.lock_pass.focus_set)
        else:
            self.setup_screen.lift()
            self.after(50, self.setup_pass.focus_set)

    def handle_return(self):
        if self.setup_screen.winfo_ismapped():
            self._create_vault()
        elif self.lock_screen.winfo_ismapped():
            self._attempt_unlock()

    def handle_escape(self):
        if self.unlocked:
            self.lock()
        else:
            self.app.leave_vault()

    def lock(self):
        self.unlocked = False
        self.store.close()
        self.items = []
        self.selected_id = None
        self._cancel_ticks()
        self.lock_pass.delete(0, "end")
        self.lock_status.configure(text="", text_color=T.MUTED)
        self._clear_preview()
        self._clear_list()
        self.show_gate()
        self.app.leave_vault()

    def enter(self):
        self.unlocked = True
        self.store.set_fails(0)
        self.lock_pass.delete(0, "end")
        self.refresh_list()
        self.main_screen.lift()
        self.app.enter_vault()
        self._start_ticks()

    def _cancel_ticks(self):
        for job in (self._tick_job, self._cooldown_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._tick_job = None
        self._cooldown_job = None

    def _start_ticks(self):
        self._cancel_ticks()
        self._tick()
        self._update_status_bar()

    def _tick(self):
        """1 Hz clock: status bar refresh + idle auto-lock."""
        self._update_status_bar()
        if self.unlocked:
            idle_for = time.time() - self.app.last_activity
            if idle_for > self.app.idle_lock_seconds:
                self.lock()
                return
        self._tick_job = self.after(1000, self._tick)

    # ---------------------------------------------------------- lock screen

    def _build_lock_screen(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_rowconfigure(6, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text="", image=icons.get("lock", T.PURPLE, 44),
                     font=(T.MONO, 26, "bold")).grid(row=1, column=0)
        ctk.CTkLabel(frame, text="Vault locked", text_color=T.TEXT,
                     font=(T.MONO, 24, "bold")).grid(row=2, column=0, pady=(14, 4))
        ctk.CTkLabel(frame, text="Enter your passphrase to decrypt",
                     text_color=T.FAINT, font=(T.MONO, 12)).grid(row=3, column=0, pady=(0, 24))

        self.lock_pass = ctk.CTkEntry(
            frame, width=300, height=44, show="•", placeholder_text="Passphrase",
            fg_color=T.SURFACE, bg_color=T.BG, border_color=T.BORDER_SOFT,
            border_width=1, text_color=T.TEXT, font=(T.MONO, 14), corner_radius=12,
        )
        self.lock_pass.grid(row=4, column=0, pady=(0, 12))
        self.lock_pass.bind("<Return>", lambda _e: self._attempt_unlock())

        self.lock_button = ctk.CTkButton(
            frame, text="Unlock", width=300, height=44, corner_radius=12,
            fg_color=T.PURPLE, hover_color="#c4b5fd", text_color="#1a1b26",
            font=(T.MONO, 14, "bold"), command=self._attempt_unlock,
        )
        self.lock_button.grid(row=5, column=0, pady=(0, 10))

        self.lock_status = ctk.CTkLabel(frame, text="", text_color=T.DANGER,
                                        font=(T.MONO, 11))
        self.lock_status.grid(row=6, column=0, pady=(0, 4))

        ctk.CTkButton(
            frame, text="Back to calculator", width=220, height=32, corner_radius=10,
            fg_color="transparent", hover_color=T.RAISED, text_color=T.FAINT,
            font=(T.MONO, 11), command=self.app.leave_vault,
        ).grid(row=7, column=0, pady=(14, 24))
        return frame

    def _attempt_unlock(self):
        if time.time() < self._cooldown_until or not self.lock_pass.get():
            return
        password = self.lock_pass.get()
        self.lock_status.configure(text="Verifying…", text_color=T.FAINT)
        self.lock_button.configure(state="disabled")
        threading.Thread(target=self._unlock_worker, args=(password,), daemon=True).start()

    def _unlock_worker(self, password: str):
        try:
            self.store.open(password)
            ok, error = True, None
        except WrongPassphrase:
            ok, error = False, None
        except Exception as exc:  # corrupted header, unreadable file, …
            ok, error = False, str(exc)
        self.after(0, lambda: self._unlock_done(ok, error))

    def _unlock_done(self, ok: bool, error: str | None):
        self.lock_button.configure(state="normal")
        self.lock_pass.delete(0, "end")
        if ok:
            self.enter()
            return
        if error:
            self.lock_status.configure(text=error, text_color=T.DANGER)
            return
        fails = self.store.get_fails() + 1
        self.store.set_fails(fails)
        remaining = WIPE_AFTER - fails
        if fails >= WIPE_AFTER:
            self.store.wipe()
            self.lock_status.configure(
                text="Too many failed attempts. The vault has been erased.", text_color=T.DANGER)
            self.after(1500, self.show_gate)
        elif fails >= COOLDOWN_AFTER:
            self._cooldown_until = time.time() + COOLDOWN_SECONDS
            self.lock_status.configure(
                text=f"Too many attempts. Locked for {COOLDOWN_SECONDS} seconds.",
                text_color=T.WARN)
            self._cooldown_tick()
        else:
            self.lock_status.configure(
                text=f"Wrong passphrase. {remaining} attempt{'s' if remaining != 1 else ''} left.",
                text_color=T.DANGER,
            )

    def _cooldown_tick(self):
        remaining = self._cooldown_until - time.time()
        if remaining <= 0:
            self.lock_status.configure(text="", text_color=T.MUTED)
            return
        self.lock_status.configure(
            text=f"Too many attempts. Locked for {int(remaining) + 1}s.", text_color=T.WARN)
        self._cooldown_job = self.after(1000, self._cooldown_tick)

    # --------------------------------------------------------- setup screen

    def _build_setup_screen(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_rowconfigure(8, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text="", image=icons.get("shield", T.BLUE, 44),
                     font=(T.MONO, 24, "bold")).grid(row=1, column=0)
        ctk.CTkLabel(frame, text="Create your vault", text_color=T.TEXT,
                     font=(T.MONO, 24, "bold")).grid(row=2, column=0, pady=(14, 4))
        ctk.CTkLabel(frame, text="Everything stored here is encrypted on this device.",
                     text_color=T.FAINT, font=(T.MONO, 12)).grid(row=3, column=0, pady=(0, 20))

        entry_kwargs = dict(
            width=320, height=42, show="•", fg_color=T.SURFACE, bg_color=T.BG,
            border_color=T.BORDER_SOFT, border_width=1, text_color=T.TEXT,
            font=(T.MONO, 14), corner_radius=12,
        )
        self.setup_pass = ctk.CTkEntry(frame, placeholder_text="Passphrase", **entry_kwargs)
        self.setup_pass.grid(row=4, column=0, pady=(0, 10))
        self.setup_pass.bind("<Return>", lambda _e: self._create_vault())
        self.setup_confirm = ctk.CTkEntry(frame, placeholder_text="Confirm passphrase",
                                          **entry_kwargs)
        self.setup_confirm.grid(row=5, column=0, pady=(0, 14))
        self.setup_confirm.bind("<Return>", lambda _e: self._create_vault())

        warning = ctk.CTkFrame(frame, fg_color=T.SURFACE, corner_radius=12,
                               border_width=1, border_color=T.BORDER_SOFT)
        warning.grid(row=6, column=0, sticky="ew", padx=60, pady=(0, 14))
        ctk.CTkLabel(
            warning,
            text=("There is no password recovery. If the passphrase is lost, the data\n"
                  f"is unrecoverable. {WIPE_AFTER} failed attempts erase the vault."),
            text_color=T.WARN, font=(T.MONO, 11), justify="center",
        ).pack(padx=16, pady=12)

        self.setup_button = ctk.CTkButton(
            frame, text="Create vault", width=320, height=44, corner_radius=12,
            fg_color=T.PURPLE, hover_color="#c4b5fd", text_color="#1a1b26",
            font=(T.MONO, 14, "bold"), command=self._create_vault,
        )
        self.setup_button.grid(row=7, column=0, pady=(0, 8))

        self.setup_status = ctk.CTkLabel(frame, text="", text_color=T.DANGER,
                                         font=(T.MONO, 11))
        self.setup_status.grid(row=9, column=0, pady=(0, 24))
        return frame

    def _create_vault(self):
        password = self.setup_pass.get()
        if len(password) < 6:
            self.setup_status.configure(text="Use at least 6 characters.")
            return
        if password != self.setup_confirm.get():
            self.setup_status.configure(text="Passphrases do not match.")
            return
        self.setup_status.configure(text="Deriving key…", text_color=T.FAINT)
        self.setup_button.configure(state="disabled")
        threading.Thread(target=self._create_worker, args=(password,), daemon=True).start()

    def _create_worker(self, password: str):
        try:
            self.store.create(password)
            error = None
        except Exception as exc:
            error = str(exc)
        self.after(0, lambda: self._create_done(error))

    def _create_done(self, error: str | None):
        self.setup_button.configure(state="normal")
        if error:
            self.setup_status.configure(text=f"Could not create vault: {error}", text_color=T.DANGER)
            return
        self.setup_pass.delete(0, "end")
        self.setup_confirm.delete(0, "end")
        self.setup_status.configure(text="")
        self.enter()

    # ------------------------------------------------- browser: main screen

    def _build_main_screen(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=1)

        # -- icon rail (far left, VS Code activity bar) --
        rail = ctk.CTkFrame(frame, fg_color=T.PANEL, corner_radius=0, width=52)
        rail.grid(row=0, column=0, rowspan=3, sticky="nsew")
        rail.grid_rowconfigure(2, weight=1)
        rail.grid_propagate(False)

        ctk.CTkLabel(rail, text="", image=icons.get("shield", T.BLUE, 24)).grid(
            row=0, column=0, pady=(16, 0))
        ctk.CTkButton(
            rail, text="", width=44, height=44, corner_radius=10,
            fg_color="transparent", hover_color=T.RAISED,
            image=icons.get("key", T.FAINT, 20), command=self._change_password,
        ).grid(row=1, column=0, pady=(10, 0))
        lock_btn = ctk.CTkButton(
            rail, text="", width=44, height=44, corner_radius=10,
            fg_color="transparent", hover_color=T.RAISED,
            image=icons.get("lock", T.FAINT, 20), command=self.lock,
        )
        lock_btn.grid(row=2, column=0, sticky="s", pady=(0, 14))

        # -- explorer sidebar --
        explorer = ctk.CTkFrame(frame, fg_color=T.PANEL, corner_radius=0, width=300)
        explorer.grid(row=0, column=1, rowspan=3, sticky="nsew")
        explorer.grid_rowconfigure(3, weight=1)
        explorer.grid_columnconfigure(0, weight=1)
        explorer.grid_propagate(False)

        header = ctk.CTkFrame(explorer, fg_color=T.PANEL, corner_radius=0, height=40)
        header.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(header, text="EXPLORER", text_color=T.FAINT,
                     font=(T.MONO, 10, "bold")).place(x=16, y=12)

        root_row = ctk.CTkFrame(explorer, fg_color="transparent", corner_radius=0,
                                height=30, width=300)
        root_row.grid(row=1, column=0, sticky="ew")
        root_row.grid_propagate(False)
        root_inner = ctk.CTkFrame(root_row, fg_color=T.RAISED, corner_radius=0)
        root_inner.place(x=0, y=0, relwidth=1, relheight=1)
        ctk.CTkLabel(root_inner, text="", image=icons.get("chevron", T.FAINT, 12)).place(x=8, y=9)
        ctk.CTkLabel(root_inner, text="VAULT", text_color=T.TEXT,
                     font=(T.MONO, 11, "bold")).place(x=30, y=7)
        self.count_badge = ctk.CTkLabel(root_inner, text="0", text_color=T.FAINT,
                                        font=(T.MONO, 10))
        self.count_badge.place(x=84, y=8)

        self.item_list = ctk.CTkScrollableFrame(explorer, fg_color=T.PANEL,
                                                corner_radius=0, scrollbar_button_color=T.GUTTER,
                                                scrollbar_button_hover_color=T.FAINT)
        self.item_list.grid(row=3, column=0, sticky="nsew")

        footer = ctk.CTkFrame(explorer, fg_color=T.PANEL, corner_radius=0, height=34)
        footer.grid(row=4, column=0, sticky="ew")
        footer.grid_propagate(False)
        self.footer_label = ctk.CTkLabel(
            footer, text="",
            image=icons.get("lock", T.GREEN, 12), compound="left",
            text_color=T.FAINT, font=(T.MONO, 10))
        self.footer_label.place(x=14, y=9)

        # -- main column: toolbar + preview + status bar --
        toolbar = ctk.CTkFrame(frame, fg_color=T.BG, corner_radius=0, height=52)
        toolbar.grid(row=0, column=2, sticky="ew")
        toolbar.grid_columnconfigure(0, weight=1)

        self.breadcrumb = ctk.CTkLabel(toolbar, text="Vault", text_color=T.TEXT,
                                       font=(T.MONO, 13, "bold"), anchor="w")
        self.breadcrumb.grid(row=0, column=0, sticky="w", padx=20, pady=(14, 0))

        actions = ctk.CTkFrame(toolbar, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e", padx=16)
        ghost = dict(fg_color="transparent", hover_color=T.RAISED, corner_radius=10,
                     height=34, font=(T.MONO, 12))
        self.copy_button = ctk.CTkButton(actions, text="Copy", image=icons.get("copy", T.FAINT, 14),
                                         text_color=T.TEXT, width=76, compound="left",
                                         command=self._copy_selected, **ghost)
        self.copy_button.pack(side="left", padx=2)
        ctk.CTkButton(actions, text="Export", image=icons.get("download", T.FAINT, 14),
                      text_color=T.TEXT, width=88, compound="left",
                      command=self._export_selected, **ghost).pack(side="left", padx=2)
        ctk.CTkButton(actions, text="Delete", image=icons.get("trash", T.DANGER, 14),
                      text_color=T.DANGER, width=88, compound="left",
                      command=self._delete_selected, **ghost).pack(side="left", padx=2)

        # Drive-style action strip: new note / add files
        strip = ctk.CTkFrame(frame, fg_color=T.BG, corner_radius=0, height=46)
        strip.grid(row=1, column=2, sticky="ew")
        strip.grid_columnconfigure(2, weight=1)
        pill = dict(fg_color=T.SURFACE, hover_color=T.RAISED, corner_radius=10,
                    height=34, font=(T.MONO, 12))
        ctk.CTkButton(strip, text="New note", image=icons.get("plus", T.GREEN, 14),
                      text_color=T.TEXT, width=110, compound="left",
                      command=self._add_text, **pill).grid(row=0, column=0, padx=(20, 6), pady=6)
        ctk.CTkButton(strip, text="Add files", image=icons.get("upload", T.CYAN, 14),
                      text_color=T.TEXT, width=110, compound="left",
                      command=self._add_files, **pill).grid(row=0, column=1, padx=(0, 6), pady=6)

        self.viewer = ViewerFrame(frame)
        self.viewer.grid(row=2, column=2, sticky="nsew", padx=16, pady=(0, 8))

        # -- status bar (VS Code style) --
        status = ctk.CTkFrame(frame, fg_color=T.BLUE, corner_radius=0, height=26)
        status.grid(row=3, column=2, sticky="ew")
        status.grid_columnconfigure(0, weight=1)
        self.status_left = ctk.CTkLabel(status, text="Vault", text_color="#1a1b26",
                                        font=(T.MONO, 10, "bold"))
        self.status_left.grid(row=0, column=0, sticky="w", padx=12)
        self.status_right = ctk.CTkLabel(status, text="", text_color="#1a1b26",
                                         font=(T.MONO, 10))
        self.status_right.grid(row=0, column=1, sticky="e", padx=12)

        # -- empty-state hint over the preview area --
        self._show_empty_hint()
        return frame

    # -- status bar ----------------------------------------------------------

    def _update_status_bar(self):
        count = len(self.items)
        self.status_left.configure(
            text=f"Vault  ·  {count} item{'s' if count != 1 else ''}")
        idle_for = max(time.time() - self.app.last_activity, 0)
        remaining = max(self.app.idle_lock_seconds - idle_for, 0)
        mins, secs = divmod(int(remaining), 60)
        self.status_right.configure(
            text=f"AES-128-CBC + HMAC-SHA256  ·  PBKDF2 400k  ·  auto-lock {mins}:{secs:02d}")

    # -- explorer list -------------------------------------------------------

    def refresh_list(self):
        self._clear_list()
        try:
            self.items = self.store.list_items()
        except VaultError as exc:
            self._set_footer(str(exc), T.DANGER)
            return
        self._total_size = sum(i.size for i in self.items)
        count = len(self.items)
        self.count_badge.configure(text=str(count))
        self._set_footer(f"Encrypted · {human_size(self._total_size)}", T.GREEN)
        if not self.items:
            empty = ctk.CTkLabel(
                self.item_list, text="Vault is empty.\nAdd a note or some files.",
                text_color=T.FAINT, font=(T.MONO, 11), justify="center")
            empty.pack(pady=48)
            return
        for info in self.items:
            self._item_row(info)

    def _clear_list(self):
        for child in self.item_list.winfo_children():
            child.destroy()

    def _item_row(self, info: ItemInfo):
        selected = info.id == self.selected_id
        row = ctk.CTkFrame(self.item_list, fg_color=T.RAISED if selected else "transparent",
                           corner_radius=8, height=30)
        row.pack(fill="x", padx=6, pady=1)
        row.grid_columnconfigure(1, weight=1)
        if selected:
            bar = ctk.CTkFrame(row, fg_color=T.BLUE, corner_radius=0, width=3)
            bar.grid(row=0, column=0, sticky="ns", padx=(0, 6), pady=4)

        icon_color = T.KIND_COLORS.get(info.kind, T.CYAN)
        icon_name = {"text": "text", "code": "code", "image": "image", "audio": "audio",
                     "video": "video", "pdf": "pdf", "archive": "archive"}.get(info.kind, "file")
        ctk.CTkLabel(row, text="", image=icons.get(icon_name, icon_color, 16)).grid(
            row=0, column=1, sticky="w", padx=(8 if not selected else 2, 4))
        ctk.CTkLabel(row, text=info.name, text_color=T.TEXT if selected else T.MUTED,
                     font=(T.MONO, 11), anchor="w").grid(row=0, column=2, sticky="w")
        ctk.CTkLabel(row, text=human_size(info.size), text_color=T.GUTTER,
                     font=(T.MONO, 9)).grid(row=0, column=3, sticky="e", padx=(4, 10))

        for widget in (row, *row.winfo_children()[1:]):
            widget.bind("<Button-1>", lambda _e, i=info: self._select(i))
            widget.bind("<Double-Button-1>", lambda _e, i=info: self._select(i))

    def _set_footer(self, text: str, color):
        self.footer_label.configure(text=text, image=icons.get("lock", color, 12),
                                    text_color=T.FAINT)

    # -- selection / preview ---------------------------------------------------

    def _select(self, info: ItemInfo):
        self.selected_id = info.id
        self.breadcrumb.configure(text=f"Vault  /  {info.name}")
        self.copy_button.configure(
            state="normal" if info.kind in ("text", "code") else "disabled")
        for child in self.item_list.winfo_children():
            child.destroy()
        for item in self.items:
            self._item_row(item)
        try:
            data = self.store.read(info.id)
        except VaultError as exc:
            self._clear_preview()
            self.viewer.show(info, b"")
            self.status_right.configure(text=str(exc))
            return
        self._clear_preview()
        self.viewer.show(info, data)

    def _clear_preview(self):
        # redraw an empty preview pane with a hint
        self.viewer._viewer = None
        for child in self.viewer.winfo_children():
            child.destroy()
        hint = ctk.CTkFrame(self.viewer, fg_color=T.SURFACE, corner_radius=0)
        hint.grid(row=0, column=0, sticky="nsew")
        hint.grid_rowconfigure(0, weight=1)
        hint.grid_rowconfigure(2, weight=1)
        hint.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hint, text="", image=icons.get("file", T.GUTTER, 40),
                     font=(T.MONO, 12), text_color=T.FAINT).grid(row=1, column=0)

    def _show_empty_hint(self):
        pass  # replaced by _clear_preview's hint widget

    # -- mutations ----------------------------------------------------------

    def _add_text(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("New note")
        dialog.geometry("460x400")
        dialog.transient(self.app)
        dialog.grab_set()
        dialog.configure(fg_color=T.BG)

        ctk.CTkLabel(dialog, text="New note", text_color=T.TEXT,
                     font=(T.MONO, 16, "bold")).pack(padx=24, pady=(18, 12), anchor="w")

        name_entry = ctk.CTkEntry(
            dialog, width=400, height=38, placeholder_text="Note name",
            fg_color=T.SURFACE, border_color=T.BORDER_SOFT, border_width=1,
            text_color=T.TEXT, font=(T.MONO, 13), corner_radius=10)
        name_entry.pack(padx=24, pady=(0, 10), anchor="w")

        box = ctk.CTkTextbox(dialog, width=400, height=210, fg_color=T.SURFACE,
                             text_color=T.TEXT, font=(T.MONO, 13), corner_radius=10,
                             border_width=1, border_color=T.BORDER_SOFT)
        box.pack(padx=24, pady=(0, 12), fill="both", expand=True)

        def save():
            text = box.get("1.0", "end-1c")
            name = name_entry.get().strip() or f"note-{time.strftime('%Y%m%d-%H%M%S')}.txt"
            if not text.strip():
                return
            try:
                self.store.add_text(name, text)
            except VaultError as exc:
                messagebox.showerror("Vault", str(exc), parent=dialog)
                return
            dialog.destroy()
            self.refresh_list()
            self._update_status_bar()

        row = ctk.CTkFrame(dialog, fg_color="transparent")
        row.pack(padx=24, pady=(4, 16), anchor="w")
        ctk.CTkButton(row, text="Cancel", width=110, height=38, corner_radius=10,
                      fg_color=T.SURFACE, hover_color=T.RAISED, text_color=T.MUTED,
                      font=(T.MONO, 12), command=dialog.destroy).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Save", width=110, height=38, corner_radius=10,
                      fg_color=T.PURPLE, hover_color="#c4b5fd", text_color="#1a1b26",
                      font=(T.MONO, 12, "bold"), command=save).pack(side="left")
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        name_entry.focus_set()

    def _add_files(self):
        paths = filedialog.askopenfilenames(parent=self.app, title="Choose files")
        if not paths:
            return
        threading.Thread(target=self._add_files_worker, args=(list(paths),),
                         daemon=True).start()

    def _add_files_worker(self, paths: list[str]):
        errors = []
        for path in paths:
            try:
                self.store.add_file(path)
            except Exception as exc:
                errors.append(f"{path.split('/')[-1]}: {exc}")
        self.after(0, lambda: self._add_files_done(errors, len(paths)))

    def _add_files_done(self, errors: list[str], total: int):
        self.refresh_list()
        self._update_status_bar()
        if errors:
            self.status_right.configure(text=f"Added {total - len(errors)}, "
                                             f"skipped {len(errors)}: {errors[0]}")
        else:
            self.status_right.configure(text=f"Added {total} file(s).")

    def _delete_selected(self):
        info = next((i for i in self.items if i.id == self.selected_id), None)
        if info is None:
            return
        if not messagebox.askyesno(
                "Delete permanently",
                f"Delete \"{info.name}\"? This cannot be undone.", parent=self.app):
            return
        try:
            self.store.delete(info.id)
        except VaultError as exc:
            messagebox.showerror("Vault", str(exc), parent=self.app)
            return
        if self.selected_id == info.id:
            self.selected_id = None
            self.breadcrumb.configure(text="Vault")
            self._clear_preview()
        self.refresh_list()
        self._update_status_bar()

    def _export_selected(self):
        info = next((i for i in self.items if i.id == self.selected_id), None)
        if info is None:
            return
        path = filedialog.asksaveasfilename(parent=self.app, initialfile=info.name,
                                            title="Export decrypted copy")
        if not path:
            return
        try:
            data = self.store.read(info.id)
            with open(path, "wb") as fh:
                fh.write(data)
        except (VaultError, OSError) as exc:
            messagebox.showerror("Export failed", str(exc), parent=self.app)
            return
        self.status_right.configure(text=f"Exported to {path}")

    def _copy_selected(self):
        info = next((i for i in self.items if i.id == self.selected_id), None)
        if info is None:
            return
        try:
            data = self.store.read(info.id)
            text = data.decode("utf-8", errors="replace")
        except (VaultError, UnicodeDecodeError) as exc:
            messagebox.showerror("Copy failed", str(exc), parent=self.app)
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_right.configure(text="Copied to clipboard.")

    def _change_password(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Change passphrase")
        dialog.geometry("440x360")
        dialog.transient(self.app)
        dialog.grab_set()
        dialog.configure(fg_color=T.BG)

        ctk.CTkLabel(dialog, text="Change vault passphrase", text_color=T.TEXT,
                     font=(T.MONO, 16, "bold")).pack(padx=24, pady=(18, 14), anchor="w")

        entry_kwargs = dict(
            width=380, height=38, show="•", fg_color=T.SURFACE,
            border_color=T.BORDER_SOFT, border_width=1, text_color=T.TEXT,
            font=(T.MONO, 13), corner_radius=10,
        )
        old_entry = ctk.CTkEntry(dialog, placeholder_text="Current passphrase", **entry_kwargs)
        old_entry.pack(padx=24, pady=(0, 8), anchor="w")
        new_entry = ctk.CTkEntry(dialog, placeholder_text="New passphrase (min 6 characters)",
                                **entry_kwargs)
        new_entry.pack(padx=24, pady=(0, 8), anchor="w")
        confirm_entry = ctk.CTkEntry(dialog, placeholder_text="Confirm new passphrase",
                                    **entry_kwargs)
        confirm_entry.pack(padx=24, pady=(0, 10), anchor="w")

        status = ctk.CTkLabel(dialog, text="", text_color=T.DANGER, font=(T.MONO, 11))
        status.pack(padx=24, pady=(0, 8), anchor="w")

        def save():
            old = old_entry.get()
            new = new_entry.get()
            if not old or not new:
                status.configure(text="Fill in all fields.")
                return
            if len(new) < 6:
                status.configure(text="New passphrase must be at least 6 characters.")
                return
            if new != confirm_entry.get():
                status.configure(text="New passphrases do not match.")
                return
            status.configure(text="Re-wrapping keys…", text_color=T.FAINT)
            threading.Thread(target=self._change_password_worker,
                             args=(old, new, dialog, status), daemon=True).start()

        row = ctk.CTkFrame(dialog, fg_color="transparent")
        row.pack(padx=24, pady=(4, 16), anchor="w")
        ctk.CTkButton(row, text="Cancel", width=110, height=38, corner_radius=10,
                      fg_color=T.SURFACE, hover_color=T.RAISED, text_color=T.MUTED,
                      font=(T.MONO, 12), command=dialog.destroy).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Change", width=110, height=38, corner_radius=10,
                      fg_color=T.PURPLE, hover_color="#c4b5fd", text_color="#1a1b26",
                      font=(T.MONO, 12, "bold"), command=save).pack(side="left")
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        old_entry.focus_set()

    def _change_password_worker(self, old: str, new: str, dialog, status):
        try:
            self.store.change_password(old, new)
            error = None
        except WrongPassphrase:
            error = "Current passphrase is wrong."
        except Exception as exc:
            error = str(exc)
        self.after(0, lambda: self._change_password_done(error, dialog, status))

    def _change_password_done(self, error: str | None, dialog, status):
        if error:
            status.configure(text=error, text_color=T.DANGER)
            return
        dialog.destroy()
        self._update_status_bar()
