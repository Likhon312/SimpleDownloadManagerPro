import os
import re
import json
import math
import threading
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from urllib.parse import urlparse, unquote

APP_NAME = "Simple Download Manager Pro"
CHUNK_SIZE = 8 * 1024 * 1024
CONNECTIONS = 4
USER_AGENT = "SimpleDownloadManagerPro/1.0"

def safe_filename(url):
    name = os.path.basename(unquote(urlparse(url).path)) or "download"
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or "download"

def format_size(n):
    if n is None:
        return "Unknown"
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024

class Job:
    def __init__(self, url, folder):
        self.url = url
        self.folder = folder
        self.filename = safe_filename(url)
        self.path = os.path.join(folder, self.filename)
        self.temp_dir = self.path + ".smdm_parts"
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.thread = None
        self.status = "Queued"
        self.total = None
        self.downloaded = 0
        self.error = ""
        self.parts = []
        self.supports_ranges = False

    def get_size_and_ranges(self):
        req = urllib.request.Request(self.url, method="HEAD",
            headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                length = r.headers.get("Content-Length")
                self.total = int(length) if length and length.isdigit() else None
                self.supports_ranges = "bytes" in r.headers.get("Accept-Ranges", "").lower()
        except Exception:
            self.total = None
            self.supports_ranges = False
        if self.total and not self.supports_ranges:
            # Probe a one-byte range; some servers omit Accept-Ranges on HEAD.
            try:
                req = urllib.request.Request(self.url, headers={
                    "User-Agent": USER_AGENT, "Range": "bytes=0-0"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    self.supports_ranges = getattr(r, "status", 200) == 206
                    if self.total is None:
                        cr = r.headers.get("Content-Range", "")
                        m = re.search(r"/(\d+)$", cr)
                        if m:
                            self.total = int(m.group(1))
            except Exception:
                pass

    def part_path(self, i):
        return os.path.join(self.temp_dir, f"part_{i:02d}.bin")

    def run(self):
        try:
            os.makedirs(self.folder, exist_ok=True)
            self.status = "Checking server"
            self.get_size_and_ranges()
            if self.total and self.supports_ranges and self.total > CHUNK_SIZE:
                self.run_parallel()
            else:
                self.run_single()
        except Exception as e:
            self.error = str(e)
            self.status = "Error"

    def run_single(self):
        existing = os.path.getsize(self.path) if os.path.exists(self.path) else 0
        headers = {"User-Agent": USER_AGENT}
        if existing:
            headers["Range"] = f"bytes={existing}-"
        req = urllib.request.Request(self.url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            if existing and getattr(response, "status", 200) != 206:
                existing = 0
                mode = "wb"
            else:
                mode = "ab" if existing else "wb"
            cl = response.headers.get("Content-Length")
            if cl and cl.isdigit():
                self.total = existing + int(cl)
            self.downloaded = existing
            self.status = "Downloading"
            with open(self.path, mode) as f:
                while not self.stop.is_set():
                    data = response.read(256 * 1024)
                    if not data:
                        self.status = "Complete"
                        return
                    f.write(data)
                    self.downloaded += len(data)
        if self.stop.is_set():
            self.status = "Paused"

    def run_parallel(self):
        os.makedirs(self.temp_dir, exist_ok=True)
        count = min(CONNECTIONS, max(2, math.ceil(self.total / CHUNK_SIZE)))
        self.parts = []
        ranges = []
        for i in range(count):
            start = i * self.total // count
            end = (i + 1) * self.total // count - 1
            ranges.append((start, end))
            p = self.part_path(i)
            have = os.path.getsize(p) if os.path.exists(p) else 0
            expected = end - start + 1
            if have > expected:
                os.remove(p)
                have = 0
            self.parts.append((p, start, end, have))
        self.downloaded = sum(x[3] for x in self.parts)
        self.status = "Downloading (multi-connection)"
        errors = []

        def worker(part):
            path, start, end, have = part
            if self.stop.is_set() or have >= end - start + 1:
                return
            headers = {"User-Agent": USER_AGENT, "Range": f"bytes={start + have}-{end}"}
            req = urllib.request.Request(self.url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    if getattr(response, "status", 200) != 206:
                        raise RuntimeError("Server stopped supporting byte-range downloads")
                    with open(path, "ab" if have else "wb") as f:
                        while not self.stop.is_set():
                            data = response.read(256 * 1024)
                            if not data:
                                break
                            f.write(data)
                            with self.lock:
                                self.downloaded += len(data)
            except Exception as e:
                with self.lock:
                    errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(p,), daemon=True) for p in self.parts]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if self.stop.is_set():
            self.status = "Paused"
            return
        if errors:
            raise RuntimeError(errors[0])
        for path, start, end, _ in self.parts:
            expected = end - start + 1
            if not os.path.exists(path) or os.path.getsize(path) != expected:
                raise RuntimeError("A download segment is incomplete. Select Resume to retry.")
        with open(self.path, "wb") as output:
            for path, *_ in self.parts:
                with open(path, "rb") as part_file:
                    while True:
                        data = part_file.read(1024 * 1024)
                        if not data:
                            break
                        output.write(data)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.status = "Complete"
        self.downloaded = self.total

class App:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("980x600")
        self.root.minsize(760, 470)
        self.jobs = []
        self.build()
        self.root.after(300, self.refresh)

    def build(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="Download URL").pack(side="left")
        self.url = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.url)
        ent.pack(side="left", fill="x", expand=True, padx=8)
        ent.bind("<Return>", lambda e: self.add_job())
        ttk.Button(top, text="Add to queue", command=self.add_job).pack(side="left")

        bar = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        bar.pack(fill="x")
        for label, fn in [
            ("Start queue", self.start_queue),
            ("Start / Resume", self.resume_selected),
            ("Pause", self.pause_selected),
            ("Remove", self.remove_selected),
            ("Open folder", self.open_folder),
        ]:
            ttk.Button(bar, text=label, command=fn).pack(side="left", padx=(0, 6))

        cols = ("file", "size", "progress", "status")
        self.tree = ttk.Treeview(self.root, columns=cols, show="headings", selectmode="browse")
        for c, title in zip(cols, ("File", "Downloaded / Total", "Progress", "Status")):
            self.tree.heading(c, text=title)
        self.tree.column("file", width=360)
        self.tree.column("size", width=180, anchor="center")
        self.tree.column("progress", width=100, anchor="center")
        self.tree.column("status", width=240, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        bottom = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        bottom.pack(fill="x")
        self.folder = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads"))
        ttk.Label(bottom, text="Save folder:").pack(side="left")
        ttk.Label(bottom, textvariable=self.folder).pack(side="left", padx=6)
        ttk.Button(bottom, text="Change folder", command=self.choose_folder).pack(side="right")
        ttk.Label(self.root, text="Up to 4 connections per file when the server supports HTTP byte ranges.",
                  padding=(10, 0, 10, 8)).pack(anchor="w")

    def choose_folder(self):
        d = filedialog.askdirectory(initialdir=self.folder.get())
        if d:
            self.folder.set(d)

    def add_job(self):
        url = self.url.get().strip()
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.netloc:
            messagebox.showwarning("Invalid URL", "Please enter a valid HTTP or HTTPS direct-download URL.")
            return
        job = Job(url, self.folder.get())
        if any(j.path == job.path and j.status != "Complete" for j in self.jobs):
            messagebox.showwarning("Already queued", "This filename is already in the queue.")
            return
        self.jobs.append(job)
        self.tree.insert("", "end", iid=str(id(job)),
                         values=(job.filename, "0 B / Unknown", "—", "Queued"))
        self.url.set("")

    def selected(self):
        s = self.tree.selection()
        return next((j for j in self.jobs if s and str(id(j)) == s[0]), None)

    def launch(self, job):
        if job.thread and job.thread.is_alive():
            return
        if job.status == "Complete":
            return
        job.stop.clear()
        job.thread = threading.Thread(target=job.run, daemon=True)
        job.thread.start()

    def start_queue(self):
        # Queue starts jobs one by one to avoid overloading the connection.
        def next_job(index=0):
            while index < len(self.jobs) and self.jobs[index].status == "Complete":
                index += 1
            if index >= len(self.jobs):
                return
            job = self.jobs[index]
            if job.thread and job.thread.is_alive():
                self.root.after(500, lambda: next_job(index))
                return
            if job.status in ("Queued", "Paused", "Error"):
                self.launch(job)
            self.root.after(500, lambda: wait_job(index))
        def wait_job(index):
            job = self.jobs[index]
            if job.thread and job.thread.is_alive():
                self.root.after(500, lambda: wait_job(index))
            else:
                next_job(index + 1)
        next_job()

    def resume_selected(self):
        j = self.selected()
        if j and j.status in ("Queued", "Paused", "Error"):
            self.launch(j)

    def pause_selected(self):
        j = self.selected()
        if j and j.thread and j.thread.is_alive():
            j.stop.set()
            j.status = "Pausing"

    def remove_selected(self):
        j = self.selected()
        if not j:
            return
        if j.thread and j.thread.is_alive():
            messagebox.showinfo("Download active", "Pause it and wait until it stops before removing.")
            return
        self.jobs.remove(j)
        self.tree.delete(str(id(j)))

    def open_folder(self):
        j = self.selected()
        folder = j.folder if j else self.folder.get()
        os.startfile(folder)

    def refresh(self):
        for j in self.jobs:
            total = format_size(j.total)
            downloaded = format_size(j.downloaded)
            progress = f"{j.downloaded / j.total * 100:.1f}%" if j.total else ("100%" if j.status == "Complete" else "—")
            status = ("Error: " + j.error[:50]) if j.status == "Error" else j.status
            try:
                self.tree.item(str(id(j)), values=(j.filename, f"{downloaded} / {total}", progress, status))
            except tk.TclError:
                pass
        self.root.after(400, self.refresh)

if __name__ == "__main__":
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()
