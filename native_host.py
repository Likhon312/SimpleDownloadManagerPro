import json
import os
import struct
import sys
import subprocess

def read_message():
    raw = sys.stdin.buffer.read(4)
    if len(raw) != 4:
        return None
    size = struct.unpack("=I", raw)[0]
    if size > 8 * 1024 * 1024:
        return None
    data = sys.stdin.buffer.read(size)
    if len(data) != size:
        return None
    return json.loads(data.decode("utf-8"))

def send_message(obj):
    data = json.dumps(obj).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("=I", len(data)) + data)
    sys.stdout.buffer.flush()

def main():
    msg = read_message()
    if not isinstance(msg, dict) or msg.get("action") != "add_download":
        send_message({"ok": False, "error": "Unsupported request"})
        return
    url = msg.get("url", "")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        send_message({"ok": False, "error": "Only HTTP/HTTPS URLs are supported"})
        return
    cookie = msg.get("cookie", "")
    filename = msg.get("filename", "")
    if not isinstance(cookie, str) or len(cookie) > 1024 * 1024:
        send_message({"ok": False, "error": "Invalid cookie data"})
        return
    if not isinstance(filename, str):
        filename = ""
    folder = os.path.dirname(os.path.abspath(sys.argv[0]))
    app = os.path.join(folder, "SimpleDownloadManagerPro.exe")
    if not os.path.isfile(app):
        send_message({"ok": False, "error": "Download manager EXE not found beside native host"})
        return
    try:
        subprocess.Popen(
            [app, "--add-url", url, "--cookie", cookie, "--filename", filename],
            cwd=folder, close_fds=True
        )
        send_message({"ok": True})
    except Exception as exc:
        send_message({"ok": False, "error": str(exc)})

if __name__ == "__main__":
    main()
