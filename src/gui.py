"""Fase 4 — GUI: status + log + manuel toneart-override.

Viser YouTube-titel, aktuel toneart, retune-status, og en log der opdateres
hver gang noget nyt sker (titel, opslag, key-skifte, retune, reset). 12 knapper
sætter toneart manuelt (sender CC#16 + låser auto-detektion til "Auto" trykkes).

Arkitektur: audio-pipeline kører i baggrundstråd; MidiController.on_event pusher
events i en tråd-sikker kø; tkinter-hovedtråden tømmer køen via root.after().
(macOS kræver tkinter i hovedtråden.)

Kør:
  PYTHONPATH=src ./venv/bin/python src/gui.py
"""
import queue
import threading
import time
import tkinter as tk
from tkinter import scrolledtext

from realtime import load_config, Pipeline, run_live_loop
from key_detection import NOTE_NAMES
from main import MidiController

BG = "#1e1e1e"; FG = "#e0e0e0"; ACC = "#3a7afe"; OK = "#3ad07a"; OFF = "#d04a4a"


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.stop = threading.Event()
        root.title("AL_KEY DETECTOR")
        root.configure(bg=BG)

        cfg = load_config()
        self.ctrl = MidiController(cfg)
        self.ctrl.on_event = lambda kind, p: self.q.put((kind, p))

        self.pipe = Pipeline(cfg)
        self.pipe.on_stable = self.ctrl.on_stable
        self.pipe.on_analysis = self.ctrl.on_analysis
        self.pipe.on_reset = self.ctrl.on_reset
        self.pipe.on_new_title = self.ctrl.on_new_title

        self._build()
        self.thread = threading.Thread(target=self._audio, args=(cfg,), daemon=True)
        self.thread.start()
        self.log("Start — lytter live. Vælg sang i YouTube.")
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.after(100, self._drain)

    # ---------- layout ----------
    def _build(self):
        top = tk.Frame(self.root, bg=BG); top.pack(fill="x", padx=12, pady=(12, 4))
        self.lbl_title = self._stat(top, "Titel:", "—")
        self.lbl_key = self._stat(top, "Toneart (send):", "—")
        self.lbl_rt = self._stat(top, "Autotune:", "FRA")
        self.lbl_mode = self._stat(top, "Tilstand:", "auto")

        grid = tk.Frame(self.root, bg=BG); grid.pack(fill="x", padx=12, pady=6)
        tk.Label(grid, text="Manuel toneart:", bg=BG, fg=FG,
                 font=("Helvetica", 11, "bold")).grid(row=0, column=0, columnspan=12, sticky="w", pady=(0, 4))
        self.btns = {}
        for pc, name in enumerate(NOTE_NAMES):
            b = self._mkbtn(grid, name, lambda pc=pc: self._manual_key(pc), w=4, big=True)
            b.grid(row=1, column=pc, padx=3, pady=(3, 0))
            self.btns[pc] = b
            # paralleltoneart (relativ mol) = grundtone - 3 halvtoner. Kun info.
            rel_min = NOTE_NAMES[(pc - 3) % 12] + "m"
            tk.Label(grid, text=rel_min, bg=BG, fg="#7a9aff",
                     font=("Helvetica", 10)).grid(row=2, column=pc, padx=3, pady=(0, 4))

        ctl = tk.Frame(self.root, bg=BG); ctl.pack(fill="x", padx=12, pady=6)
        for text, cmd, col in (
            ("Auto (slip manuel)", self._auto, "#2d2d2d"),
            ("Autotune PÅ", lambda: self._force_rt(True), "#244d33"),
            ("Autotune FRA", lambda: self._force_rt(False), "#4d2424"),
            ("Reset sang", self._reset, "#2d2d2d"),
        ):
            self._mkbtn(ctl, text, cmd, base=col).pack(side="left", padx=4)

        self.txt = scrolledtext.ScrolledText(self.root, width=78, height=18, bg="#141414",
                                             fg=FG, insertbackground=FG, font=("Menlo", 11))
        self.txt.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self.txt.configure(state="disabled")

    def _stat(self, parent, label, val):
        row = tk.Frame(parent, bg=BG); row.pack(fill="x")
        tk.Label(row, text=label, width=16, anchor="w", bg=BG, fg="#9a9a9a",
                 font=("Helvetica", 11)).pack(side="left")
        v = tk.Label(row, text=val, anchor="w", bg=BG, fg=FG, font=("Helvetica", 13, "bold"))
        v.pack(side="left")
        return v

    def _mkbtn(self, parent, text, cmd, w=None, big=False, base="#2d2d2d"):
        """Label-baseret knap — macOS-tkinter respekterer bg/fg på Label (ikke Button)."""
        font = ("Helvetica", 15, "bold") if big else ("Helvetica", 12)
        b = tk.Label(parent, text=text, bg=base, fg=FG, font=font,
                     relief="raised", bd=2, padx=10, pady=8, cursor="pointinghand")
        if w:
            b.config(width=w)
        b._base = base
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.config(bg=ACC) if b._base != ACC else None)
        b.bind("<Leave>", lambda e: b.config(bg=b._base))
        return b

    # ---------- actions (GUI-tråd) ----------
    def _manual_key(self, pc):
        self.ctrl.set_manual_key(pc)
        self.lbl_mode.config(text=f"MANUEL ({NOTE_NAMES[pc]})", fg=ACC)

    def _auto(self):
        self.ctrl.clear_manual()
        self.lbl_mode.config(text="auto", fg=FG)
        self.log("→ auto genoptaget (lyd styrer)")

    def _force_rt(self, on):
        self.ctrl.set_manual_retune(on)
        self._set_rt_label(on, manual=True)
        self.log(f"→ Autotune tvunget {'PÅ' if on else 'FRA'} (manuel)")

    def _reset(self):
        self.pipe.buffer.clear()
        self.pipe.smoother.reset()
        self.ctrl.on_reset()
        self.log("→ Reset sang (buffer ryddet)")

    # ---------- audio-tråd ----------
    def _audio(self, cfg):
        try:
            run_live_loop(cfg, self.pipe, stop=self.stop)
        except Exception as e:
            self.q.put(("error", {"msg": str(e)}))

    # ---------- kø-tømning (GUI-tråd) ----------
    def _drain(self):
        try:
            while True:
                kind, p = self.q.get_nowait()
                self._handle(kind, p)
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _handle(self, kind, p):
        if kind == "title":
            t = p.get("title"); a = p.get("artist")
            self.lbl_title.config(text=f"{a + ' - ' if a else ''}{t}")
            self.log(f"NY TITEL: {a or '?'} - {t}")
        elif kind == "lookup":
            if p.get("found"):
                pc = p["pc"]
                self.log(f"  bibliotek: {p['key_str']} (str {p['strength']:.2f}) "
                         f"→ send-tone {NOTE_NAMES[pc]}")
            else:
                self.log("  bibliotek: intet fund — venter på lyd")
        elif kind == "key":
            pc = p["pc"]
            self.lbl_key.config(text=f"{NOTE_NAMES[pc]}  ({p['src']})")
            self._mark_key(pc if p["src"] == "manuel" else None)
            self.log(f"KEY → {NOTE_NAMES[pc]}  [{p['src']}: {p.get('detail','')}]")
        elif kind == "retune":
            self._set_rt_label(p["on"], manual=False)
            self.log(f"RETUNE → autotune {'PÅ' if p['on'] else 'FRA'}  [{p['src']}]")
        elif kind == "auto":
            self._mark_key(None)
        elif kind == "reset":
            self.lbl_title.config(text="—")
            self.log("RESET (ny sang / stilhed)")
        elif kind == "error":
            self.log(f"FEJL: {p['msg']}")

    def _set_rt_label(self, on, manual):
        txt = ("PÅ" if on else "FRA") + (" (manuel)" if manual else "")
        self.lbl_rt.config(text=txt, fg=OK if on else OFF)

    def _mark_key(self, pc):
        for i, b in self.btns.items():
            on = i == pc
            b._base = ACC if on else "#2d2d2d"
            b.config(bg=b._base, relief="sunken" if on else "raised")

    def log(self, msg):
        self.txt.configure(state="normal")
        self.txt.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def _close(self):
        self.stop.set()
        try:
            self.ctrl.close()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
