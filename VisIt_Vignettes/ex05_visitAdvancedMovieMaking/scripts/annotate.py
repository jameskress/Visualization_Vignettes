import sys

from visit_utils import *
from visit_utils.qannote import *

import json
import os
from os.path import join as pjoin

image_dir = "images"
output_dir = "output"

blobs_times = pjoin(output_dir, "blobs_times.json")
color_bar = pjoin(image_dir, "colorTable.png")

width = 2048
height = 1920

def fetch_proper_time(time_state):
    times = json.load(open(blobs_times))
    time = times[time_state]
    return time

def legend_items(foreground, background, time_state):
    x_offset = 80
    y_offset = 120

    items = [
            Image({ "image": color_bar,
                    "x": x_offset, "y": y_offset,
                    "vert_align": "bottom",
                    "horz_align": "center"}),
            Text({  "text": "Temperature",
                    "color": foreground,
                    "x": x_offset, "y": y_offset - 14,
                    "horz_align": "center",
                    "vert_align": "bottom",
                    "font/size": 18,
                    "font/bold": True}),
            Text({  "text": "High",
                    "color": foreground,
                    "x": x_offset + 85, "y": y_offset + 5,
                    "horz_align": "left",
                    "vert_align": "top",
                    "font/size": 14,
                    "font/bold": True}),
            Text({  "text": "Low",
                    "color": foreground,
                    "x": x_offset + 85, "y": y_offset + 520,
                    "horz_align": "left",
                    "vert_align": "bottom",
                    "font/size": 14,
                    "font/bold": True})
            ]
    return items

def time_items(foreground, background, time_state):
    time = fetch_proper_time(time_state)
    x_offset = width * 0.86
    y_offset = 30
    value_offset = 160

    items = [
            Text({ "text": "Time:",
                   "x": x_offset + 5, "y": y_offset,
                   "color": foreground,
                   "horz_align": "left",
                   "vert_align": "bottom",
                   "font/name": "Arial",
                   "font/size": 18,
                   "font/bold": True}),
            Text({ "text": "%3.0f\\0x03bcs" % time,
                   "x": x_offset + value_offset, "y": y_offset,
                   "color": foreground,
                   "horz_align": "right",
                   "vert_align": "bottom",
                   "font/name": "Arial",
                   "font/size": 16,
                   "font/bold": True})
            ]
    return items

def progress_bar_items(foreground, background, time_state):
    time = fetch_proper_time(time_state)
    total_time = 19.0
    bar_width = 1875

    s1 = 1.0
    bar_position = (float(time) / total_time)

    items = [
            MultiProgressBar({ "x": 40, "y": 37,
                               "width": bar_width, "height": 15,
                               "bg_color": (0, 0, 0, 0),
                               "force_labels": True,
                               "segment/ranges": [s1],
                               "segment/labels": [""],
                               "segment/colors": [(56, 216, 233, 255)],
                               "position": bar_position})
            ]
    return items

def render_overlay(foreground, background, time_state, input_file, output_file):
    background_image = Image({ "image": input_file})
    items = [background_image]
    items.extend(legend_items(foreground, background, time_state))
    items.extend(time_items(foreground, background, time_state))
    items.extend(progress_bar_items(foreground, background, time_state))
    Canvas.render(items, background_image.size(), output_file)

def render_black(time_state, input_file, output_file):
    render_overlay((255, 255, 255, 255), (0, 0, 0, 255),
        time_state, input_file, output_file)

time_state = int(sys.argv[1])
input_file = sys.argv[2]
output_file = sys.argv[3]

render_black(time_state, input_file, output_file)
