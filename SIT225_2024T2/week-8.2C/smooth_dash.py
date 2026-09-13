# smooth_dash.py
# Reusable wrapper for smooth, real-time Plotly Dash graphs.
#
# Usage:
#   plotter = SmoothDashPlotter(variables=["x", "y", "z"], window=200)
#   plotter.feed("x", 0.42)      # call whenever new data arrives
#   plotter.run(port=8060)       # opens the dashboard

import threading
import logging
from collections import deque

import dash
from dash import dcc, html
from dash.dependencies import Input, Output


class SmoothDashPlotter:
    """Live line graphs that scroll smoothly for any continuous data.

    One graph per variable. New values are pushed in with feed(). Graphs update
    using Plotly's extendData (append + trim in the browser) instead of a full
    redraw, which is what makes the motion look continuous.
    """

    _COLOURS = ["red", "blue", "black", "yelloe", "green"]

    def __init__(self, variables, window=200, refresh_ms=100, title="Live Data"):
        self.variables = list(variables)
        self.window = window
        self.refresh_ms = refresh_ms
        self.title = title

        # deques with maxlen act as self-trimming rolling windows
        self.lock = threading.Lock()
        self.t = deque(maxlen=window)
        self.series = {v: deque(maxlen=window) for v in self.variables}
        self.counter = 0

        # hold the latest value per variable; only commit a row once all
        # variables are fresh, so points stay aligned across graphs
        self.latest = {v: 0.0 for v in self.variables}
        self.fresh = {v: False for v in self.variables}

        logging.getLogger().setLevel(logging.CRITICAL)  # hide library retry logs
        self.app = self._build_app()

    def feed(self, variable, value):
        """Push one new value for a variable. Safe to call from any thread."""
        self.latest[variable] = value
        self.fresh[variable] = True

        if all(self.fresh.values()):
            with self.lock:
                self.counter += 1
                self.t.append(self.counter)
                for v in self.variables:
                    self.series[v].append(self.latest[v])
            for v in self.variables:
                self.fresh[v] = False

    def _empty_fig(self, name, colour):
        return {
            "data": [{"x": [], "y": [], "mode": "lines", "line": {"color": colour}}],
            "layout": {
                "title": name,
                "margin": {"l": 45, "r": 20, "t": 40, "b": 30},
                "height": 220,
                "uirevision": "keep",   # keeps zoom/pan stable across updates
            },
        }

    def _build_app(self):
        app = dash.Dash(__name__)

        graphs = [
            dcc.Graph(id=f"graph-{v}",
                      figure=self._empty_fig(v, self._COLOURS[i % len(self._COLOURS)]))
            for i, v in enumerate(self.variables)
        ]

        app.layout = html.Div(
            [html.H2(self.title)] + graphs +
            [dcc.Interval(id="tick", interval=self.refresh_ms, n_intervals=0)],
            style={"maxWidth": "900px", "margin": "0 auto", "fontFamily": "sans-serif"},
        )

        outputs = [Output(f"graph-{v}", "extendData") for v in self.variables]

        @app.callback(outputs, Input("tick", "n_intervals"))
        def _update(_):
            with self.lock:
                t = list(self.t)
                snapshot = {v: list(self.series[v]) for v in self.variables}
            # each output: (new_data, trace_index, max_points_to_keep)
            return [({"x": [t], "y": [snapshot[v]]}, [0], self.window)
                    for v in self.variables]

        return app

    def run(self, port=8060, debug=False):
        """Start the dashboard (blocking). Open the printed URL in a browser."""
        self.app.run(debug=debug, port=port)