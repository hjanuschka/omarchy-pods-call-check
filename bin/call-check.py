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


def nodes(kind, card):
    return [entry for entry in objects(kind)
            if entry.get("properties", {}).get("device.name") == card
            and (kind != "sources" or entry.get("properties", {}).get("media.class") == "Audio/Source")]


def node(kind, card):
    return next((entry["name"] for entry in nodes(kind, card)), "")


def profile_status():
    return headset().get("active_profile", "off")


def restore_profile(name, profile, sink):
    pactl("set-card-profile", name, profile)
    for _ in range(20):
        if profile_status() == profile and node("sinks", name):
            break
        time.sleep(0.1)
    if profile_status() != profile:
        pactl("set-card-profile", name, profile)
    if profile_status() != profile:
        raise RuntimeError("AirPods did not restore their " + profile + " profile")
    pactl("set-default-sink", sink)


def select_mode(mode):
    card = headset()
    name = card["name"]
    profiles = card.get("profiles", {})
    if mode == "music":
        choices = ("a2dp-sink", "a2dp-sink-sbc")
    elif mode == "call":
        choices = ("headset-head-unit-msbc", "headset-head-unit-cvsd", "headset-head-unit")
    else:
        raise ValueError("Unknown AirPods audio mode: " + mode)
    profile = next((p for p in choices if p in profiles and profiles[p].get("available", True)), None)
    if not profile:
        raise RuntimeError("No available AirPods " + mode + " profile")
    previous = card.get("active_profile", "off")
    previous_sink = pactl("get-default-sink")
    previous_source = pactl("get-default-source")
    try:
        if mode == "music":
            pactl("set-card-profile", name, profile)
        for _ in range(20):
            sink = next(iter(nodes("sinks", name)), None)
            source = next(iter(nodes("sources", name)), None)
            if sink and (mode == "music" or source):
                break
            time.sleep(0.1)
        if not sink or (mode == "call" and not source):
            raise RuntimeError("AirPods " + mode + " audio nodes did not appear")
        subprocess.run(("/usr/bin/omarchy-audio-output-set-default",
                        str(sink["properties"]["object.id"]), sink["name"]), check=True, timeout=10)
        if mode == "call":
            subprocess.run(("/usr/bin/omarchy-audio-input-set-default",
                            str(source["properties"]["object.id"]), source["name"]), check=True, timeout=10)
        if mode == "call":
            return "AirPods mic selected; call audio starts when the mic opens"
        return f"AirPods music mode selected ({profile})"
    except (ValueError, RuntimeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, OSError, KeyError):
        if mode == "music" and previous != profile:
            restore_profile(name, previous, previous_sink)
        pactl("set-default-source", previous_source)
        raise


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
            restore_profile(name, previous, previous_sink)


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["status"]:
            print(profile_status())
        elif len(sys.argv) == 3 and sys.argv[1] == "select":
            print(select_mode(sys.argv[2]))
        elif sys.argv[1:] == ["test"]:
            print(main())
        else:
            raise ValueError("Usage: call-check.py status | select music|call | test")
    except (ValueError, RuntimeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, OSError, KeyError) as error:
        print(f"AirPods audio: {error}", file=sys.stderr)
        sys.exit(1)
