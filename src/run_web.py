"""Start YouTube karaoke-web-app + aabn browser."""
import threading
import webbrowser

import uvicorn

PORT = 8731

if __name__ == "__main__":
    threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}/")).start()
    uvicorn.run("server:app", host="127.0.0.1", port=PORT, log_level="info")
