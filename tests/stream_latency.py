"""Test 3 — Stream latency: how late the live video is (phone camera → dashboard).

Method ("film a clock"), only the Python standard library (Tkinter comes with Python):
  1. On the laptop:  python tests/stream_latency.py --stopwatch
     A window shows a big stopwatch (seconds with milliseconds).
  2. Open the dashboard next to it (same screen), phone streaming.
  3. Point the phone camera at the stopwatch window. The dashboard's live video now shows
     the stopwatch as the phone saw it, a little in the past.
  4. Take a screenshot showing BOTH (Windows: Win + Shift + S). In the screenshot:
        real time  = the stopwatch window
        video time = the stopwatch inside the dashboard video
        latency    = real time − video time
     Repeat about 10 times (a few seconds apart).
  5. Type the readings:   python tests/stream_latency.py
     Enter "real video" pairs, e.g.  "437.812 436.990"  → 822 ms. Empty line = done.
     The script prints min / avg / max and saves them.

Notes: the screen refreshes every ~17 ms and the camera exposure adds a few ms, so the
result is accurate to about ±30 ms, which is enough (WebRTC latency is usually 200-800 ms).
"""
import argparse
import csv
import statistics
import time

from common import output_file, setup_console

WRAP = 1000.0  # the stopwatch shows seconds modulo 1000 (000.000 → 999.999)


def show_stopwatch():
    """Full-size stopwatch window, updated as fast as the screen allows."""
    import tkinter as tk

    window = tk.Tk()
    window.title("Stream latency stopwatch")
    window.configure(bg="black")
    label = tk.Label(window, font=("Consolas", 110, "bold"), fg="#ffd400", bg="black", padx=40, pady=40)
    label.pack(expand=True, fill="both")
    tk.Label(window, text="Point the phone camera here. Screenshot: Win + Shift + S",
             font=("Arial", 16), fg="white", bg="black").pack(pady=10)

    def tick():
        label.config(text=f"{time.time() % WRAP:07.3f}")  # e.g. 437.812
        window.after(5, tick)  # ~200 times per second (the screen shows ~60)

    tick()
    window.mainloop()


def parse_pair(line):
    """'437.812 436.990' → latency in ms (handles the 999.999 → 000.000 wrap)."""
    real, video = (float(v.replace(",", ".")) for v in line.split())
    latency = (real - video) % WRAP  # a video reading just before the wrap still works
    return latency * 1000


def enter_readings():
    """Ask for 'real video' pairs, print min / avg / max, save a CSV."""
    print("Type each screenshot reading as:  <real time> <time in the video>   e.g. 437.812 436.990")
    print("Empty line when done.\n")
    latencies = []
    while True:
        line = input(f"Reading {len(latencies) + 1}: ").strip()
        if not line:
            break
        try:
            latency = parse_pair(line)
        except ValueError:
            print("  Please type two numbers separated by a space.")
            continue
        if latency > 10_000:
            print(f"  {latency:.0f} ms looks wrong (more than 10 s): check the order (real first). Skipped.")
            continue
        latencies.append(latency)
        print(f"  → {latency:.0f} ms")

    if not latencies:
        print("No readings.")
        return
    print("\n===== Stream latency (phone → dashboard) =====")
    print(f"  min {min(latencies):.0f} ms | avg {statistics.mean(latencies):.0f} ms | "
          f"median {statistics.median(latencies):.0f} ms | max {max(latencies):.0f} ms  (n={len(latencies)})")

    path = output_file("stream_latency", "csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["reading", "latency_ms"])
        writer.writerows([i + 1, round(v)] for i, v in enumerate(latencies))
    print(f"\nReadings saved to {path}")


def main():
    setup_console()
    parser = argparse.ArgumentParser(description="Measure phone → dashboard video latency.")
    parser.add_argument("--stopwatch", action="store_true", help="show the stopwatch window to film")
    args = parser.parse_args()
    if args.stopwatch:
        show_stopwatch()
    else:
        enter_readings()


if __name__ == "__main__":
    main()
