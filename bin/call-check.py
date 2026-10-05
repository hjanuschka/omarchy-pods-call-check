#!/usr/bin/python3
"""Record from the connected AirPods mic and play back through its headset."""
import json
import signal
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

PACTL = "/usr/bin/pactl"
RECORD = "/usr/bin/pw-record"
PLAY = "/usr/bin/pw-play"


def pactl(*args):
    return subprocess.check_output((PACTL, *args), text=True, timeout=5).strip()


# pactl --format=json list cards: [{"name":"bluez_card.11_22","properties":{"device.vendor.id":"bluetooth:004c"}}]
def objects(kind):
    return json.loads(pactl("--format=json", "list", kind))


def headset():
    cards = [card for card in objects("cards")
             if card["name"].startswith("bluez_card.")
             and card.get("properties", {}).get("device.vendor.id") == "bluetooth:004c"]
    if len(cards) > 1:
        cards = [card for card in cards
                 if "AirPods" in card.get("properties", {}).get("device.description", "")]
    if len(cards) != 1:
        raise RuntimeError(f"Expected one connected AirPods audio device, found {len(cards)}")
    return cards[0]


def node(kind, card):
    for entry in objects(kind):
        if entry.get("properties", {}).get("device.name") == card:
            return entry["name"]
    return ""


def record(source, file):
    proc = subprocess.Popen((RECORD, "--target", source, "--rate", "48000",
                             "--channels", "1", file), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    try:
        with wave.open(file, "rb") as audio:
            return audio.getnframes() / audio.getframerate()
    except (OSError, EOFError, wave.Error):
        return 0


def main():
    card = headset()
    name = card["name"]
    previous = card.get("active_profile", "off")
    if previous == "off":
        raise RuntimeError("AirPods audio profile is off; connect them before testing")
    previous_sink = pactl("get-default-sink")
    profiles = card.get("profiles", {})
    profile = previous if previous.startswith("headset-head-unit") else next(
        (p for p in ("headset-head-unit-msbc", "headset-head-unit-cvsd", "headset-head-unit")
         if p in profiles and profiles[p].get("available", True)), "")
    if not profile:
        raise RuntimeError("AirPods have no available headset microphone profile")
    try:
        if profile != previous:
            pactl("set-card-profile", name, profile)
            time.sleep(1)
        source = node("sources", name)
        sink = node("sinks", name)
        if not source or not sink:
            raise RuntimeError("AirPods mic or speaker unavailable in headset mode")
        with tempfile.TemporaryDirectory(prefix="omapods-call-") as directory:
            file = str(Path(directory) / "mic.wav")
            seconds = record(source, file)
            if seconds < 2:
                raise RuntimeError("No usable mic audio captured; Bluetooth transport may have stalled")
            subprocess.run((PLAY, "--target", sink, file), timeout=20, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Played back {seconds:.1f}s from AirPods mic"
    finally:
        if profile != previous:
            pactl("set-card-profile", name, previous)
            for _ in range(20):
                if headset().get("active_profile") == previous and node("sinks", name):
                    break
                time.sleep(0.1)
            if headset().get("active_profile") != previous:
                pactl("set-card-profile", name, previous)
            if headset().get("active_profile") != previous:
                raise RuntimeError("AirPods did not restore their " + previous + " profile")
            pactl("set-default-sink", previous_sink)


if __name__ == "__main__":
    try:
        print(main())
    except (RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as error:
        print(f"AirPods call check: {error}", file=sys.stderr)
        sys.exit(1)
