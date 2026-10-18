"""Built-in viewers for every file kind.

- text / code  -> monospace editor with a VS Code style line-number gutter
- image        -> scaled preview (PIL)
- audio / video-> media player backed by Windows MCI (no external deps);
                  video embeds inside the app window
- everything else (pdf, archives, binaries) -> hex viewer

Nothing is ever "unsupported".
"""

from __future__ import annotations

import ctypes
import io
import os
import tempfile
import time

import customtkinter as ctk

import icons
import theme as T
from file_types import viewer_for
from vault_store import ItemInfo, human_size

MAX_TEXT_BYTES = 2_000_000   # text preview cap (~2 MB)
MAX_HEX_BYTES = 262_144      # hex preview cap (256 KB)


# ---------------------------------------------------------------------------
# viewer host
# ---------------------------------------------------------------------------

class ViewerFrame(ctk.CTkFrame):
    """Hosts whichever viewer fits the selected item."""

    def __init__(self, master):
        super().__init__(master, fg_color=T.SURFACE, corner_radius=12,
                         border_width=1, border_color=T.BORDER_SOFT)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._viewer = None

    def show(self, info: ItemInfo, data: bytes) -> None:
        if self._viewer is not None:
            self._viewer.destroy()
            self._viewer = None
        kind = viewer_for(info.kind)
        if kind == "text":
            self._viewer = TextViewer(self)
        elif kind == "image":
            self._viewer = ImageViewer(self)
        elif kind == "media":
            self._viewer = MediaPlayer(self, video=(info.kind == "video"))
        else:
            self._viewer = HexViewer(self)
        self._viewer.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._viewer.load(info, data)


# ---------------------------------------------------------------------------
# shared bits
# ---------------------------------------------------------------------------

class _Message(ctk.CTkFrame):
    """Centered notice with a warning icon."""

    def __init__(self, master, message: str, title: str = "Cannot preview"):
        super().__init__(master, fg_color=T.SURFACE, corner_radius=0)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text="", image=icons.get("warning", T.WARN, 36),
                     compound="top", font=(T.MONO, 15, "bold"), text_color=T.TEXT,
                     ).grid(row=1, column=0)
        ctk.CTkLabel(self, text=message, text_color=T.MUTED,
                     font=(T.MONO, 12), justify="center", wraplength=420,
                     ).grid(row=2, column=0, padx=24, pady=(10, 0))


class _InfoStrip(ctk.CTkFrame):
    """Small strip above a viewer: colored dot + kind label."""

    def __init__(self, master, info: ItemInfo):
        super().__init__(master, fg_color="transparent", corner_radius=0, height=22)
        dot = ctk.CTkLabel(self, text="●", text_color=T.KIND_COLORS.get(info.kind, T.CYAN),
                           font=(T.MONO, 9))
        dot.pack(side="left", padx=(10, 6))
        ctk.CTkLabel(self, text=f"{T.KIND_LABELS.get(info.kind, 'File')} · {human_size(info.size)}",
                     text_color=T.FAINT, font=(T.MONO, 10)).pack(side="left")


# ---------------------------------------------------------------------------
# text viewer
# ---------------------------------------------------------------------------

class TextViewer(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=T.SURFACE, corner_radius=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.info = None
        self._build()

    def _build(self):
        wrap = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        wrap.grid(row=0, column=0, columnspan=2, sticky="ew")

        gutter = ctk.CTkTextbox(self, width=52, fg_color=T.PANEL, border_width=0,
                                corner_radius=0, font=(T.MONO, 12),
                                text_color=T.GUTTER, activate_scrollbars=False)
        gutter.grid(row=1, column=0, sticky="nsew", padx=(2, 0), pady=2)
        gutter.configure(state="disabled")
        body = ctk.CTkTextbox(self, fg_color=T.SURFACE, border_width=0,
                              corner_radius=0, font=(T.MONO, 12),
                              text_color=T.TEXT, wrap="none",
                              activate_scrollbars=True)
        body.grid(row=1, column=1, sticky="nsew", padx=(0, 2), pady=2)
        body.configure(state="disabled")

        # gutter follows the body's scroll position
        self._gutter = gutter
        self._body = body
        body._textbox.configure(yscrollcommand=lambda *a: self._sync_gutter(*a))

    def _sync_gutter(self, first, last):
        try:
            self._gutter.textbox.yview_moveto(first)
        except Exception:
            pass

    def load(self, info: ItemInfo, data: bytes):
        self.info = info
        for child in self.winfo_children():
            if isinstance(child, ctk.CTkFrame) and child._name == "infostrip":
                child.destroy()
        strip = _InfoStrip(self, info)
        strip._name = "infostrip"
        strip.grid(row=0, column=0, columnspan=2, sticky="ew")

        if len(data) > MAX_TEXT_BYTES:
            data = data[:MAX_TEXT_BYTES]
        text = data.decode("utf-8", errors="replace")
        if len(text) > 300_000:
            text = text[:300_000]
        truncated = len(data) > MAX_TEXT_BYTES

        lines = text.splitlines()
        numbers = "\n".join(str(i) for i in range(1, len(lines) + 1))
        if truncated:
            text += f"\n\n--- preview truncated ({human_size(len(data))} file) ---"

        self._body.configure(state="normal")
        self._body.delete("1.0", "end")
        self._body.insert("1.0", text)
        self._body.configure(state="disabled")
        self._gutter.configure(state="normal")
        self._gutter.delete("1.0", "end")
        self._gutter.insert("1.0", numbers)
        self._gutter.configure(state="disabled")


# ---------------------------------------------------------------------------
# image viewer
# ---------------------------------------------------------------------------

class ImageViewer(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=T.SURFACE, corner_radius=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._photo = None
        self.info = None

    def load(self, info: ItemInfo, data: bytes):
        self.info = info
        for child in self.winfo_children():
            child.destroy()
        _InfoStrip(self, info).grid(row=0, column=0, sticky="ew")

        try:
            from PIL import Image
            image = Image.open(io.BytesIO(data))
            image.load()
        except Exception:
            _Message(self, "This image could not be decoded.").grid(
                row=1, column=0, sticky="nsew")
            return

        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")

        # fit the preview pane while it is being laid out
        def fit(_event=None):
            try:
                w = max(self.winfo_width() - 32, 64)
                h = max(self.winfo_height() - 56, 64)
            except Exception:
                return
            scale = min(w / image.width, h / image.height, 1.0)
            if scale <= 0:
                return
            fitted = image.resize((max(int(image.width * scale), 1),
                                   max(int(image.height * scale), 1)),
                                  Image.LANCZOS)
            self._photo = ctk.CTkImage(light_image=fitted, dark_image=fitted,
                                       size=fitted.size)
            label = getattr(self, "_label", None)
            if label is not None:
                label.configure(image=self._photo, text="")

        self._label = ctk.CTkLabel(self, text="", fg_color=T.SURFACE, corner_radius=0)
        self._label.grid(row=1, column=0, sticky="nsew", padx=16, pady=14)
        self.bind("<Configure>", fit, add="+")
        self.after(60, fit)


# ---------------------------------------------------------------------------
# hex viewer (for every other file type — pdfs, archives, binaries, …)
# ---------------------------------------------------------------------------

class HexViewer(ctk.CTkFrame):
    """Classic hexdump: offset | hex bytes | ascii. Nothing is unsupported."""

    def __init__(self, master):
        super().__init__(master, fg_color=T.SURFACE, corner_radius=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._text = None

    def load(self, info: ItemInfo, data: bytes):
        for child in self.winfo_children():
            child.destroy()
        _InfoStrip(self, info).grid(row=0, column=0, sticky="ew")

        truncated = len(data) > MAX_HEX_BYTES
        if truncated:
            data = data[:MAX_HEX_BYTES]

        lines = []
        for offset in range(0, len(data), 16):
            chunk = data[offset : offset + 16]
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            hex_part = hex_part.ljust(16 * 3 - 1)
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append((f"{offset:08x}", hex_part, ascii_part))
        if truncated:
            note = f"--- preview truncated ({human_size(len(data))} total) ---"
            lines.append((note, "", ""))

        box = ctk.CTkTextbox(self, fg_color=T.SURFACE, border_width=0, corner_radius=0,
                             font=(T.MONO, 12), text_color=T.TEXT, wrap="none")
        box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(4, 10))
        tb = box._textbox
        tb.tag_configure("offset", foreground=T.GUTTER)
        tb.tag_configure("hex", foreground=T.MUTED)
        tb.tag_configure("ascii", foreground=T.FAINT)

        for offset_text, hex_part, ascii_part in lines:
            tb.insert("end", f"  {offset_text}  ", "offset")
            tb.insert("end", hex_part + "  ", "hex")
            tb.insert("end", f"|{ascii_part}|\n", "ascii")
        tb.configure(state="disabled")
        self._text = box


# ---------------------------------------------------------------------------
# media player (Windows MCI via ctypes — ships with every Windows install)
# ---------------------------------------------------------------------------

class _Mci:
    """Tiny ctypes wrapper around winmm's MCI interface."""

    def __init__(self):
        self._dll = ctypes.windll.winmm
        self._buf = ctypes.create_unicode_buffer(512)

    def send(self, command: str) -> tuple[int, str]:
        self._buf.value = ""
        err = self._dll.mciSendStringW(command, self._buf, 512, None)
        return err, self._buf.value

    def error_text(self, code: int) -> str:
        buf = ctypes.create_unicode_buffer(256)
        self._dll.mciGetErrorStringW(code, buf, 256)
        return buf.value or f"MCI error {code}"


def _ms_to_clock(ms: int) -> str:
    total = int(ms) // 1000
    return f"{total // 60}:{total % 60:02d}"


class MediaPlayer(ctk.CTkFrame):
    """Audio / video player with play-pause, stop, seek and position."""

    def __init__(self, master, video: bool = False):
        super().__init__(master, fg_color=T.SURFACE, corner_radius=0)
        self._video = video
        self._mci = _Mci()
        self._alias = "videovault" if video else "audiovault"
        self._length = 0
        self._playing = False
        self._seeking = False
        self._poll_job = None
        self.info = None
        self._build()

    # -- ui ---------------------------------------------------------------

    def _build(self):
        if self._video:
            self.video_frame = ctk.CTkFrame(self, fg_color="#000000", corner_radius=8)
            self.video_frame.grid(row=0, column=0, sticky="nsew", padx=14, pady=(34, 8))
            self.grid_rowconfigure(0, weight=1)
            self.grid_columnconfigure(0, weight=1)
        else:
            self.grid_rowconfigure(1, weight=1)
            self.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(self, text="", image=icons.get("audio", T.YELLOW, 64),
                         compound="top", font=(T.MONO, 13), text_color=T.FAINT,
                         ).grid(row=0, column=0, pady=(56, 0))

        controls = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        controls.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 16))
        controls.grid_columnconfigure(1, weight=1)

        self.play_button = ctk.CTkButton(
            controls, text="", width=40, height=40, corner_radius=10,
            fg_color=T.RAISED, hover_color=T.BORDER_SOFT,
            image=icons.get("play", T.TEXT, 18), command=self._toggle_play,
        )
        self.play_button.grid(row=0, column=0, padx=(0, 8))

        ctk.CTkButton(
            controls, text="", width=40, height=40, corner_radius=10,
            fg_color=T.RAISED, hover_color=T.BORDER_SOFT,
            image=icons.get("stop", T.TEXT, 16), command=self._stop,
        ).grid(row=0, column=2, padx=(8, 0))

        self.slider = ctk.CTkSlider(
            controls, from_=0, to=100, height=16, corner_radius=8,
            fg_color=T.GUTTER, progress_color=T.BLUE, button_color=T.BLUE,
            command=lambda _v: None,
        )
        self.slider.grid(row=0, column=1, sticky="ew", padx=12)
        self.slider.bind("<ButtonPress-1>", lambda _e: setattr(self, "_seeking", True))
        self.slider.bind("<ButtonRelease-1>", self._seek)

        self.position_label = ctk.CTkLabel(controls, text="0:00 / 0:00",
                                           text_color=T.FAINT, font=(T.MONO, 11))
        self.position_label.grid(row=0, column=3, padx=(12, 0))

    # -- transport --------------------------------------------------------

    def load(self, info: ItemInfo, data: bytes):
        self.info = info
        # write decrypted bytes to a temp file — MCI needs a real path
        self._cleanup_mci()
        suffix = "." + (info.name.rsplit(".", 1)[-1] if "." in info.name else "bin")
        fd, self._tmp_path = tempfile.mkstemp(prefix="vault_", suffix=suffix)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)

        kind_type = "avivideo" if self._video else None
        if kind_type is None:
            kind_type = "mpegaudio" if info.mime in (
                "audio/mpeg", "audio/mp3") else None

        if self._video:
            hwnd = self.video_frame.winfo_id()
            cmd = (f'open "{self._tmp_path}" type avivideo parent {hwnd} '
                   f'alias {self._alias}')
        else:
            type_clause = f"type {kind_type} " if kind_type else ""
            cmd = f'open "{self._tmp_path}" {type_clause}alias {self._alias}'

        err, _ = self._mci.send(cmd)
        if err != 0:
            msg = self._mci.error_text(err)
            for child in self.winfo_children():
                child.destroy()
            _Message(self, f"The built-in player cannot open this {T.KIND_LABELS.get(info.kind, 'file').lower()}.",
                     title="Playback failed")
            self._status_note(msg)
            return

        self._mci.send(f"set {self._alias} time format ms")
        err, length = self._mci.send(f"status {self._alias} length")
        try:
            self._length = int(length)
        except (TypeError, ValueError):
            self._length = 0

        if self._video:
            try:
                w = self.video_frame.winfo_width()
                h = self.video_frame.winfo_height()
                self._mci.send(f"put {self._alias} window at 0 0 {w} {h}")
            except Exception:
                pass

        self._update_label()
        self._play()

    def _status_note(self, note: str):
        ctk.CTkLabel(self, text=note, text_color=T.FAINT, font=(T.MONO, 10),
                     wraplength=420, justify="center").grid(
            row=3 if self._video else 2, column=0, padx=16)

    def _toggle_play(self):
        if self._playing:
            self._mci.send(f"pause {self._alias}")
            self._playing = False
            self.play_button.configure(image=icons.get("play", T.TEXT, 18))
            self._cancel_poll()
        else:
            self._mci.send(f"play {self._alias}")
            self._playing = True
            self.play_button.configure(image=icons.get("pause", T.TEXT, 16))
            self._schedule_poll()

    def _stop(self):
        self._mci.send(f"stop {self._alias}")
        self._mci.send(f"seek {self._alias} to start")
        self._playing = False
        self.play_button.configure(image=icons.get("play", T.TEXT, 18))
        self._cancel_poll()
        self.slider.set(0)
        self._update_label()

    def _seek(self, _event=None):
        self._seeking = False
        if self._length <= 0:
            return
        target = int(self.slider.get() / 100 * self._length)
        self._mci.send(f"seek {self._alias} to {target}")
        if not self._playing:
            self._mci.send(f"play {self._alias}")

    def _schedule_poll(self):
        self._cancel_poll()
        self._poll_job = self.after(250, self._poll)

    def _cancel_poll(self):
        if self._poll_job is not None:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None

    def _poll(self):
        if not self._playing:
            return
        err, pos = self._mci.send(f"status {self._alias} position")
        try:
            current = int(pos)
        except (TypeError, ValueError):
            current = 0
        self._update_label(current)
        if not self._seeking and self._length > 0:
            self.slider.set(min(current / self._length * 100, 100))
        if self._length > 0 and current >= self._length:
            self._stop()
            return
        self._schedule_poll()

    def _update_label(self, current: int = 0):
        self.position_label.configure(
            text=f"{_ms_to_clock(current)} / {_ms_to_clock(self._length)}")

    def _cleanup_mci(self):
        self._cancel_poll()
        self._mci.send(f"stop {self._alias}")
        self._mci.send(f"close {self._alias}")
        self._playing = False
        path = getattr(self, "_tmp_path", None)
        if path:
            try:
                os.remove(path)
            except OSError:
                pass
            self._tmp_path = None

    def destroy(self):
        self._cleanup_mci()
        super().destroy()
