# capture_activity.py
# SIT225 6D - Annotate smartphone accelerometer data by capturing activity images
#
# - Client runs in SYNCHRONOUS mode (sync_mode=True), polled with client.update()
#   in a loop, to keep the buffer drained and stop the lag growing
# - Every WINDOW_SECONDS: snapshot the last FRESH_SECONDS of readings, grab a
#   webcam frame, AND save a PNG line graph of that window's data
#
# Each capture makes three matching files:
#   1_yyyymmddHHMMss.csv   (data)
#   1_yyyymmddHHMMss.jpg   (webcam image)
#   1_yyyymmddHHMMss.png   (graph of that window)
#
# Run:  python capture_activity.py  ->  http://127.0.0.1:8060
# Needs: pip install dash plotly opencv-python arduino-iot-cloud matplotlib

import os
import csv
import time
import base64
import threading
from datetime import datetime
from collections import deque

import cv2

import matplotlib
matplotlib.use("Agg")           # non-GUI backend, safe in a background thread
import matplotlib.pyplot as plt

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
from arduino_iot_cloud import ArduinoCloudClient

DEVICE_ID = "e05103af-9ba7-4545-ab9e-6f4762dac24a"
SECRET_KEY = "7xlUMLMbGvy5FQwdjRE!S?OCf"

VAR_X = "accelerometer_x"
VAR_Y = "accelerometer_y"
VAR_Z = "accelerometer_z"

WINDOW_SECONDS = 10     # save data + image + graph every 10 seconds
FRESH_SECONDS = 3.0     # only keep readings from the last N seconds
WEBCAM_INDEX = 0
OUT_DIR = "captures"
GRAPH_SECONDS = 15      # seconds shown on the live dashboard graph

os.makedirs(OUT_DIR, exist_ok=True)


# Shared state
lock = threading.Lock()
history = deque()  # (monotonic_time, iso, x, y, z)
latest = {"x": 0.0, "y": 0.0, "z": 0.0}
fresh = {"x": False, "y": False, "z": False}
latest_image_path = {"path": None}


def _trim(now):
    keep = max(FRESH_SECONDS, GRAPH_SECONDS) + 1
    while history and (now - history[0][0]) > keep:
        history.popleft()


def commit_sample():
    now = time.monotonic()
    with lock:
        history.append((now, datetime.now().isoformat(timespec="milliseconds"),
                        latest["x"], latest["y"], latest["z"]))
        _trim(now)


# Arduino IoT Cloud callbacks (values converted g -> m/s^2)
def on_x(client, value):
    latest["x"] = value * 9.81
    fresh["x"] = True
    _maybe_commit()

def on_y(client, value):
    latest["y"] = value * 9.81
    fresh["y"] = True
    _maybe_commit()

def on_z(client, value):
    latest["z"] = value * 9.81
    fresh["z"] = True
    _maybe_commit()

def _maybe_commit():
    if all(fresh.values()):
        commit_sample()
        for axis in ("x", "y", "z"):
            fresh[axis] = False


def start_cloud_client():
    """Synchronous mode: pump update() ourselves so the buffer stays drained."""
    client = ArduinoCloudClient(device_id=DEVICE_ID,
                                username=DEVICE_ID,
                                password=SECRET_KEY,
                                sync_mode=True)
    client.register(VAR_X, value=None, on_write=on_x)
    client.register(VAR_Y, value=None, on_write=on_y)
    client.register(VAR_Z, value=None, on_write=on_z)

    client.start()   # returns immediately in sync mode
    while True:
        try:
            client.update()
        except Exception:
            import traceback
            traceback.print_exc()
            time.sleep(1)
        time.sleep(0.05)


def save_window_graph(rows, png_path):
    """Save a PNG line graph of one window's x/y/z data."""
    xs = list(range(len(rows)))
    xvals = [r[1] for r in rows]
    yvals = [r[2] for r in rows]
    zvals = [r[3] for r in rows]
    plt.figure(figsize=(6, 3))
    plt.plot(xs, xvals, color="red", marker="o", label="X")
    plt.plot(xs, yvals, color="blue", marker="o", label="Y")
    plt.plot(xs, zvals, color="green", marker="o", label="Z")
    plt.ylim(-20, 20)
    plt.xlabel("sample # in window")
    plt.ylabel("acceleration (m/s^2)")
    plt.title(os.path.basename(png_path).replace(".png", ""))
    plt.legend(loc="upper right", fontsize=8)
    plt.tight_layout()
    plt.savefig(png_path, dpi=90)
    plt.close()


# Saver thread - every WINDOW_SECONDS: CSV + image + graph, all matched
def start_saver():
    cam = cv2.VideoCapture(WEBCAM_INDEX)
    if not cam.isOpened():
        print("WARNING: could not open webcam index", WEBCAM_INDEX)

    seq = 1
    while True:
        time.sleep(WINDOW_SECONDS)
        now = time.monotonic()
        with lock:
            _trim(now)
            rows = [(iso, x, y, z) for (t, iso, x, y, z) in history
                    if (now - t) <= FRESH_SECONDS]
        if not rows:
            print("(no fresh data this window - skipped)")
            continue

        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        base = f"{seq}_{stamp}"
        csv_path = os.path.join(OUT_DIR, base + ".csv")
        jpg_path = os.path.join(OUT_DIR, base + ".jpg")
        png_path = os.path.join(OUT_DIR, base + ".png")

        # 1) data
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "x", "y", "z"])
            w.writerows(rows)

        # 2) webcam image
        ok, frame = cam.read()
        if ok:
            cv2.imwrite(jpg_path, frame)
            latest_image_path["path"] = jpg_path

        # 3) graph of this window
        try:
            save_window_graph(rows, png_path)
        except Exception as e:
            print("graph save failed:", e)

        status = "+img" if ok else "-IMG FAILED"
        print(f"saved {base}.csv ({len(rows)} rows) {status} +graph")
        seq += 1


# Dash app - live graph (last GRAPH_SECONDS) + latest image
def build_app():
    app = dash.Dash(__name__)

    app.layout = html.Div([
        html.H2("SIT225 6D - Live Accelerometer + Activity Capture"),
        html.Div([
            html.Div([dcc.Graph(id="graph")], style={"flex": "1"}),
            html.Div([
                html.H3("Latest captured activity image"),
                html.Img(id="live-image",
                         style={"width": "100%", "border": "1px solid #ccc"}),
            ], style={"flex": "1", "paddingLeft": "20px"}),
        ], style={"display": "flex"}),
        dcc.Interval(id="tick", interval=300, n_intervals=0),
    ], style={"maxWidth": "1100px", "margin": "0 auto", "fontFamily": "sans-serif"})

    @app.callback(Output("graph", "figure"), Input("tick", "n_intervals"))
    def update_graph(_):
        now = time.monotonic()
        with lock:
            _trim(now)
            recent = [(t, x, y, z) for (t, iso, x, y, z) in history
                      if (now - t) <= GRAPH_SECONDS]
        xs = [-(now - t) for (t, x, y, z) in recent]
        data = [
            {"x": xs, "y": [x for (t, x, y, z) in recent], "mode": "lines",
             "name": "X", "line": {"color": "red"}},
            {"x": xs, "y": [y for (t, x, y, z) in recent], "mode": "lines",
             "name": "Y", "line": {"color": "blue"}},
            {"x": xs, "y": [z for (t, x, y, z) in recent], "mode": "lines",
             "name": "Z", "line": {"color": "green"}},
        ]
        return {
            "data": data,
            "layout": {
                "title": "Accelerometer (X, Y, Z) - last %ds" % GRAPH_SECONDS,
                "xaxis": {"title": "seconds ago", "range": [-GRAPH_SECONDS, 0]},
                "yaxis": {"title": "acceleration (m/s^2)", "range": [-20, 20]},
                "margin": {"l": 55, "r": 20, "t": 40, "b": 40},
                "height": 420, "uirevision": "keep",
            },
        }

    @app.callback(Output("live-image", "src"), Input("tick", "n_intervals"))
    def update_image(_):
        path = latest_image_path["path"]
        if not path or not os.path.exists(path):
            return dash.no_update
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        return "data:image/jpeg;base64," + encoded

    return app


# Main
if __name__ == "__main__":
    threading.Thread(target=start_cloud_client, daemon=True).start()
    threading.Thread(target=start_saver, daemon=True).start()
    print("Starting dashboard on http://127.0.0.1:8060")
    build_app().run(port=8060, debug=False)