"""
SmartAttendance Desktop Client (Tkinter)
Run from project root:
    venv/Scripts/python.exe client/desktop_client.py
"""

import io
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import requests
from PIL import Image, ImageTk

API  = "http://localhost:8000"
FEED_W, FEED_H = 400, 300


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SmartAttendance")
        self.resizable(False, False)
        self.configure(bg="#1e1e2e")

        self._selected_photos: list[str] = []
        self._stream_running  = True
        self._current_photo   = None
        self._seen_ids: set   = set()
        self._refreshing      = False

        self._build_ui()
        self._start_stream()
        self._check_api()
        self._poll_loop()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame",            background="#1e1e2e")
        s.configure("TLabelframe",       background="#1e1e2e", foreground="#cdd6f4")
        s.configure("TLabelframe.Label", background="#1e1e2e", foreground="#89b4fa",
                    font=("Segoe UI", 9, "bold"))
        s.configure("TLabel",  background="#1e1e2e", foreground="#cdd6f4")
        s.configure("TEntry",  fieldbackground="#313244", foreground="#cdd6f4",
                    insertcolor="#cdd6f4")
        s.configure("TButton", background="#313244", foreground="#cdd6f4", padding=4)
        s.configure("TNotebook",     background="#1e1e2e", tabmargins=[2,2,2,0])
        s.configure("TNotebook.Tab", background="#313244", foreground="#cdd6f4",
                    padding=[10,4])
        s.map("TNotebook.Tab",
              background=[("selected","#89b4fa")],
              foreground=[("selected","#1e1e2e")])
        s.configure("Treeview", background="#313244", foreground="#cdd6f4",
                    fieldbackground="#313244", rowheight=22)
        s.configure("Treeview.Heading", background="#45475a", foreground="#cdd6f4")

        outer = ttk.Frame(self, padding=8)
        outer.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(outer)
        left.grid(row=0, column=0, padx=(0,10), sticky="nsew")

        feed_border = tk.Frame(left, bg="#313244", padx=2, pady=2)
        feed_border.pack()

        feed_container = tk.Frame(feed_border, width=FEED_W, height=FEED_H, bg="#181825")
        feed_container.pack_propagate(False)
        feed_container.pack()

        self.feed_label = tk.Label(feed_container, bg="#181825",
                                   text="Connecting to stream...",
                                   fg="#6c7086", font=("Segoe UI", 10))
        self.feed_label.place(relwidth=1, relheight=1)

        self.alert_frame = tk.Frame(left, bg="#a6e3a1", padx=8, pady=6)
        self.alert_lbl   = tk.Label(self.alert_frame, text="", bg="#a6e3a1",
                                    fg="#1e1e2e", font=("Segoe UI", 11, "bold"))
        self.alert_lbl.pack()

        log_frame = ttk.LabelFrame(left, text=" Recent Attendance ", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(8,0))

        self.event_list = tk.Listbox(
            log_frame, height=6,
            bg="#181825", fg="#a6e3a1",
            selectbackground="#313244",
            font=("Consolas", 9),
            relief=tk.FLAT, bd=0,
        )
        self.event_list.pack(fill=tk.BOTH, expand=True)

        right = ttk.Frame(outer)
        right.grid(row=0, column=1, sticky="nsew")

        nb = ttk.Notebook(right)
        nb.pack(fill=tk.BOTH, expand=True)

        monitor_tab = ttk.Frame(nb, padding=8)
        nb.add(monitor_tab, text="  Live Monitor  ")
        self._build_monitor(monitor_tab)

        enroll_tab = ttk.Frame(nb, padding=12)
        nb.add(enroll_tab, text="  Enroll  ")
        self._build_enroll(enroll_tab)

        att_tab = ttk.Frame(nb, padding=8)
        nb.add(att_tab, text="  Attendance  ")
        self._build_attendance(att_tab)

        unk_tab = ttk.Frame(nb, padding=8)
        nb.add(unk_tab, text="  Unknown Faces  ")
        self._build_unknown(unk_tab)

        self.status_var = tk.StringVar(value="Connecting...")
        tk.Label(self, textvariable=self.status_var,
                 bg="#181825", fg="#a6adc8", anchor=tk.W,
                 padx=8, pady=3, font=("Segoe UI", 8)
                 ).pack(fill=tk.X, side=tk.BOTTOM)

    def _build_monitor(self, p):
        hdr = ttk.Frame(p)
        hdr.pack(fill=tk.X, pady=(0, 8))

        self.in_count_var = tk.StringVar(value="IN: 0")
        tk.Label(hdr, textvariable=self.in_count_var,
                 bg="#a6e3a1", fg="#1e1e2e",
                 font=("Segoe UI", 11, "bold"), padx=12, pady=4
                 ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(hdr, text="People currently inside the building",
                 bg="#1e1e2e", fg="#a6adc8",
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)

        ttk.Button(hdr, text="Refresh", command=self._refresh_monitor).pack(side=tk.RIGHT)

        cols = ("name", "id", "checkin", "duration")
        self.mon_tree = ttk.Treeview(p, columns=cols, show="headings", height=7)
        self.mon_tree.heading("name",     text="Name")
        self.mon_tree.heading("id",       text="Emp ID")
        self.mon_tree.heading("checkin",  text="Checked In")
        self.mon_tree.heading("duration", text="Duration")
        self.mon_tree.column("name",     width=140)
        self.mon_tree.column("id",       width=70)
        self.mon_tree.column("checkin",  width=85)
        self.mon_tree.column("duration", width=85, anchor=tk.CENTER)
        sb = ttk.Scrollbar(p, orient=tk.VERTICAL, command=self.mon_tree.yview)
        self.mon_tree.configure(yscrollcommand=sb.set)
        self.mon_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, pady=(0,8))
        sb.pack(side=tk.LEFT, fill=tk.Y, pady=(0,8))

        ttk.Separator(p, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)

        tk.Label(p, text="Today's Events (check-in & check-out)",
                 bg="#1e1e2e", fg="#89b4fa",
                 font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(4,4))

        cols2 = ("name","event","time","conf")
        self.log_tree = ttk.Treeview(p, columns=cols2, show="headings", height=7)
        self.log_tree.heading("name",  text="Name")
        self.log_tree.heading("event", text="Event")
        self.log_tree.heading("time",  text="Time")
        self.log_tree.heading("conf",  text="Confidence")
        self.log_tree.column("name",  width=140)
        self.log_tree.column("event", width=80, anchor=tk.CENTER)
        self.log_tree.column("time",  width=85)
        self.log_tree.column("conf",  width=80, anchor=tk.CENTER)
        self.log_tree.tag_configure("checkin",  background="#1e3a2f", foreground="#a6e3a1")
        self.log_tree.tag_configure("checkout", background="#3a1e1e", foreground="#f38ba8")
        sb2 = ttk.Scrollbar(p, orient=tk.VERTICAL, command=self.log_tree.yview)
        self.log_tree.configure(yscrollcommand=sb2.set)
        self.log_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb2.pack(side=tk.LEFT, fill=tk.Y)

    def _build_enroll(self, p):
        fields = [
            ("Full Name *",   "name_var"),
            ("Employee ID *", "empid_var"),
            ("Email",         "email_var"),
            ("Department",    "dept_var"),
        ]
        for i, (label, attr) in enumerate(fields):
            ttk.Label(p, text=label).grid(row=i, column=0, sticky=tk.W, pady=5)
            var = tk.StringVar()
            setattr(self, attr, var)
            ttk.Entry(p, textvariable=var, width=26).grid(row=i, column=1, pady=5, padx=(8,0))

        ttk.Separator(p, orient=tk.HORIZONTAL).grid(
            row=len(fields), column=0, columnspan=2, sticky=tk.EW, pady=10)

        ttk.Button(p, text="Browse Face Photos  (3-5 recommended)",
                   command=self._browse_photos
                   ).grid(row=5, column=0, columnspan=2, sticky=tk.EW, pady=3)

        self.photo_info = tk.StringVar(value="No photos selected")
        ttk.Label(p, textvariable=self.photo_info,
                  foreground="#6c7086").grid(row=6, column=0, columnspan=2, pady=2)

        ttk.Separator(p, orient=tk.HORIZONTAL).grid(
            row=7, column=0, columnspan=2, sticky=tk.EW, pady=10)

        self.enroll_btn = ttk.Button(p, text="Enroll Person", command=self._do_enroll)
        self.enroll_btn.grid(row=8, column=0, columnspan=2, sticky=tk.EW, ipady=5)

        self.enroll_msg = tk.StringVar()
        self._enroll_msg_lbl = tk.Label(p, textvariable=self.enroll_msg,
                                        bg="#1e1e2e", fg="#a6e3a1",
                                        wraplength=260, justify=tk.LEFT,
                                        font=("Segoe UI", 9))
        self._enroll_msg_lbl.grid(row=9, column=0, columnspan=2, pady=6)

    def _build_attendance(self, p):
        top = ttk.Frame(p)
        top.pack(fill=tk.X, pady=(0,6))
        ttk.Label(top, text="Date:").pack(side=tk.LEFT)
        self.date_var = tk.StringVar(value=time.strftime("%Y-%m-%d"))
        ttk.Entry(top, textvariable=self.date_var, width=12).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Refresh", command=self._refresh_attendance).pack(side=tk.LEFT)
        self.att_count = tk.StringVar()
        ttk.Label(top, textvariable=self.att_count,
                  foreground="#89b4fa").pack(side=tk.RIGHT)

        cols = ("name","id","time","conf")
        self.att_tree = ttk.Treeview(p, columns=cols, show="headings", height=16)
        self.att_tree.heading("name", text="Name")
        self.att_tree.heading("id",   text="Emp ID")
        self.att_tree.heading("time", text="Time")
        self.att_tree.heading("conf", text="Confidence")
        self.att_tree.column("name", width=140)
        self.att_tree.column("id",   width=70)
        self.att_tree.column("time", width=80)
        self.att_tree.column("conf", width=80, anchor=tk.CENTER)
        sb = ttk.Scrollbar(p, orient=tk.VERTICAL, command=self.att_tree.yview)
        self.att_tree.configure(yscrollcommand=sb.set)
        self.att_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_unknown(self, p):
        top = ttk.Frame(p)
        top.pack(fill=tk.X, pady=(0,6))
        ttk.Button(top, text="Refresh", command=self._refresh_unknown).pack(side=tk.LEFT)
        self.unk_count = tk.StringVar()
        ttk.Label(top, textvariable=self.unk_count,
                  foreground="#f38ba8").pack(side=tk.RIGHT)

        cols = ("id","time","reviewed")
        self.unk_tree = ttk.Treeview(p, columns=cols, show="headings", height=16)
        self.unk_tree.heading("id",       text="Record ID")
        self.unk_tree.heading("time",     text="Detected At")
        self.unk_tree.heading("reviewed", text="Reviewed")
        self.unk_tree.column("id",       width=160)
        self.unk_tree.column("time",     width=155)
        self.unk_tree.column("reviewed", width=75, anchor=tk.CENTER)
        sb = ttk.Scrollbar(p, orient=tk.VERTICAL, command=self.unk_tree.yview)
        self.unk_tree.configure(yscrollcommand=sb.set)
        self.unk_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    # ── Monitor ──────────────────────────────────────────────────────────────

    def _refresh_monitor(self):
        def run():
            try:
                presence = requests.get(f"{API}/presence", timeout=5).json()
                today = time.strftime("%Y-%m-%d")
                log = requests.get(f"{API}/presence/log?date={today}&limit=100", timeout=5).json()
                self.after(0, lambda: self._fill_monitor(presence, log))
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    def _fill_monitor(self, presence: list, log: list):
        self.mon_tree.delete(*self.mon_tree.get_children())
        for r in presence:
            dur = r.get("duration_min", 0)
            dur_str = f"{dur//60}h {dur%60}m" if dur >= 60 else f"{dur}m"
            self.mon_tree.insert("", tk.END, values=(
                r.get("name","—"), "",
                r.get("checkin_at","—"), dur_str,
            ))
        self.in_count_var.set(f"IN: {len(presence)}")

        self.log_tree.delete(*self.log_tree.get_children())
        for r in log:
            p      = r.get("persons") or {}
            ts     = r.get("timestamp","")
            etype  = r.get("event_type","")
            conf   = r.get("confidence")
            tag    = "checkin" if etype == "checkin" else "checkout"
            label  = "CHECK IN" if etype == "checkin" else "CHECK OUT"
            self.log_tree.insert("", tk.END, values=(
                p.get("name","—"), label,
                ts[11:19] if len(ts)>=19 else ts,
                f"{conf:.3f}" if conf else "—",
            ), tags=(tag,))

    # ── Enroll ───────────────────────────────────────────────────────────────

    def _browse_photos(self):
        paths = filedialog.askopenfilenames(
            title="Select 3-5 clear front-face photos",
            filetypes=[("Images","*.jpg *.jpeg *.png *.bmp *.webp")],
        )
        self._selected_photos = list(paths)
        n = len(self._selected_photos)
        self.photo_info.set(f"{n} photo(s) selected" if n else "No photos selected")

    def _do_enroll(self):
        name  = self.name_var.get().strip()
        empid = self.empid_var.get().strip()
        if not name or not empid:
            messagebox.showwarning("Missing fields", "Name and Employee ID are required.")
            return
        if not self._selected_photos:
            messagebox.showwarning("No photos", "Browse at least one photo first.")
            return

        self.enroll_btn.config(state=tk.DISABLED)
        self.enroll_msg.set("Uploading & processing...")
        self._enroll_msg_lbl.config(fg="#89dceb")

        def run():
            try:
                files = [("images", open(p, "rb")) for p in self._selected_photos]
                data  = {"name": name, "employee_id": empid}
                if self.email_var.get().strip():
                    data["email"] = self.email_var.get().strip()
                if self.dept_var.get().strip():
                    data["department"] = self.dept_var.get().strip()
                r = requests.post(f"{API}/enroll", data=data, files=files, timeout=30)
                if r.status_code == 200:
                    j   = r.json()
                    msg = f"Enrolled '{j['name']}'  —  {j['embeddings_added']} embedding(s) saved.\nStep in front of the camera to test!"
                    clr = "#a6e3a1"
                    self.after(0, self._refresh_attendance)
                    self.after(0, self._check_api)
                else:
                    msg = f"Error: {r.json().get('detail', r.text)}"
                    clr = "#f38ba8"
                self.after(0, lambda: self.enroll_msg.set(msg))
                self.after(0, lambda: self._enroll_msg_lbl.config(fg=clr))
            except Exception as exc:
                self.after(0, lambda: self.enroll_msg.set(f"Error: {exc}"))
                self.after(0, lambda: self._enroll_msg_lbl.config(fg="#f38ba8"))
            finally:
                self.after(0, lambda: self.enroll_btn.config(state=tk.NORMAL))

        threading.Thread(target=run, daemon=True).start()

    # ── Attendance ───────────────────────────────────────────────────────────

    def _refresh_attendance(self):
        date = self.date_var.get().strip()
        def run():
            try:
                url  = f"{API}/attendance?limit=200" + (f"&date={date}" if date else "")
                rows = requests.get(url, timeout=5).json()
                self.after(0, lambda: self._fill_att(rows))
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    def _fill_att(self, rows: list):
        self.att_tree.delete(*self.att_tree.get_children())
        for r in rows:
            p  = r.get("persons") or {}
            ts = r.get("timestamp","")
            self.att_tree.insert("", tk.END, values=(
                p.get("name","—"), p.get("employee_id","—"),
                ts[11:19] if len(ts)>=19 else ts,
                f"{r.get('confidence',0):.3f}",
            ))
        self.att_count.set(f"{len(rows)} record(s)")

        new_events = []
        for r in rows:
            rid = r.get("id","")
            if rid and rid not in self._seen_ids:
                self._seen_ids.add(rid)
                p    = r.get("persons") or {}
                name = p.get("name","Unknown")
                ts   = r.get("timestamp","")
                t    = ts[11:19] if len(ts)>=19 else ts
                new_events.append((name, t, r.get("confidence",0)))

        for name, t, conf in new_events:
            self._fire_alert(name, t, conf)

    def _fire_alert(self, name: str, t: str, conf: float, event_type: str = "checkin"):
        if event_type == "checkin":
            msg   = f"  {name}  CHECKED IN   ({t})"
            color = "#a6e3a1"
        else:
            msg   = f"  {name}  CHECKED OUT   ({t})"
            color = "#f38ba8"
        self.alert_lbl.config(text=msg, bg=color, fg="#1e1e2e")
        self.alert_frame.config(bg=color)
        self.alert_frame.pack(fill=tk.X, pady=(6,0))
        self.after(5000, lambda: self.alert_frame.pack_forget())

        entry = f"{name}  {t}  [{conf:.3f}]"
        self.event_list.insert(0, entry)
        if self.event_list.size() > 20:
            self.event_list.delete(tk.END)

    def _refresh_unknown(self):
        def run():
            try:
                rows = requests.get(f"{API}/unknown-faces?limit=100", timeout=5).json()
                self.after(0, lambda: self._fill_unk(rows))
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    def _fill_unk(self, rows: list):
        self.unk_tree.delete(*self.unk_tree.get_children())
        for r in rows:
            ts = r.get("timestamp","")
            self.unk_tree.insert("", tk.END, values=(
                r.get("id","")[:20]+"...",
                ts[:19].replace("T"," "),
                "Yes" if r.get("reviewed") else "No",
            ))
        self.unk_count.set(f"{len(rows)} unreviewed")

    # ── Snapshot stream ───────────────────────────────────────────────────────

    def _start_stream(self):
        threading.Thread(target=self._stream_loop, daemon=True).start()

    def _stream_loop(self):
        url = f"{API}/snapshot"
        while self._stream_running:
            try:
                r = requests.get(url, timeout=2)
                if r.status_code == 200:
                    img   = Image.open(io.BytesIO(r.content))
                    img   = img.resize((FEED_W, FEED_H), Image.NEAREST)
                    photo = ImageTk.PhotoImage(img)
                    self.after(0, self._update_feed, photo)
            except Exception:
                pass
            time.sleep(0.25)

    def _update_feed(self, photo):
        self._current_photo = photo
        self.feed_label.configure(image=photo, text="")

    # ── Poll loop ─────────────────────────────────────────────────────────────

    def _poll_loop(self):
        if not self._refreshing:
            self._refreshing = True
            self._refresh_attendance()
            self._refresh_unknown()
            self._refresh_monitor()
            self.after(500, lambda: setattr(self, "_refreshing", False))
        self.after(4000, self._poll_loop)

    def _check_api(self):
        def run():
            try:
                d   = requests.get(f"{API}/health", timeout=3).json()
                msg = (f"  Connected  |  {d['enrolled_faces']} enrolled face(s)"
                       f"  |  model: {d['model']}  |  {API}")
                self.after(0, lambda: self.status_var.set(msg))
            except Exception:
                self.after(0, lambda: self.status_var.set(
                    f"  Cannot reach {API} — is the server running?"))
        threading.Thread(target=run, daemon=True).start()
        self.after(8000, self._check_api)

    def _on_close(self):
        self._stream_running = False
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app._on_close)
    app.mainloop()
