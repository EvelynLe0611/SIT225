# app.py
# Live smooth accelerometer dashboard.
# All the smooth-plotting logic lives in smooth_dash.py, so this file just
# feeds it data from Arduino IoT Cloud.
#
# Run:  py -3.12 app.py    then open http://127.0.0.1:8060/

import threading

from arduino_iot_cloud import ArduinoCloudClient
from smooth_dash import SmoothDashPlotter

DEVICE_ID = "PUT_YOUR_DEVICE_ID_HERE"
SECRET_KEY = "PUT_YOUR_SECRET_KEY_HERE"

plotter = SmoothDashPlotter(
    variables=["x", "y", "z"],
    window=200,
    refresh_ms=100,
    title="Live Accelerometer (smooth)",
)


def start_client():
    client = ArduinoCloudClient(
        device_id=DEVICE_ID,
        username=DEVICE_ID,
        password=SECRET_KEY,
    )
    client.register("accelerometer_x", value=None, on_write=lambda c, v: plotter.feed("x", v))
    client.register("accelerometer_y", value=None, on_write=lambda c, v: plotter.feed("y", v))
    client.register("accelerometer_z", value=None, on_write=lambda c, v: plotter.feed("z", v))
    client.start()


threading.Thread(target=start_client, daemon=True).start()

if __name__ == "__main__":
    plotter.run(port=8060)