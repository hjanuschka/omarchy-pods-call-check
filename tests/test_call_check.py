import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


path = Path(__file__).resolve().parents[1] / "bin" / "call-check.py"
spec = importlib.util.spec_from_file_location("call_check", path)
call_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(call_check)


class CallCheckTest(unittest.TestCase):
    card = {
        "name": "bluez_card.11_22", "properties": {
            "device.vendor.id": "bluetooth:004c", "device.description": "AirPods Max"},
        "active_profile": "a2dp-sink",
        "profiles": {"a2dp-sink": {"available": True},
                     "headset-head-unit-msbc": {"available": True}},
    }

    @patch.object(call_check, "objects")
    def test_selects_only_connected_airpods(self, objects):
        objects.return_value = [
            {"name": "bluez_card.33_44", "properties": {
                "device.vendor.id": "bluetooth:abcd", "device.description": "Other Headset"}},
            self.card,
        ]
        self.assertEqual(call_check.headset()["name"], self.card["name"])

    @patch.object(call_check, "objects")
    def test_rejects_ambiguous_airpods(self, objects):
        objects.return_value = [self.card, dict(self.card, name="bluez_card.55_66")]
        with self.assertRaisesRegex(RuntimeError, "found 2"):
            call_check.headset()

    @patch.object(call_check.subprocess, "run")
    @patch.object(call_check, "objects")
    @patch.object(call_check, "pactl")
    @patch.object(call_check, "headset")
    def test_call_selection_routes_airpods_mic_and_output(self, headset, pactl, objects, run):
        headset.return_value = self.card
        objects.side_effect = lambda kind: [{"name": "airpods-" + kind,
                                             "properties": {"device.name": self.card["name"],
                                                            "media.class": "Audio/Source",
                                                            "object.id": "42"}}]
        call_check.select_mode("call")
        self.assertFalse(any(call.args[0] == "set-card-profile" for call in pactl.call_args_list))
        self.assertEqual(len(run.call_args_list), 2)
        self.assertIn("audio-input", run.call_args_list[1].args[0][0])

    @patch.object(call_check.subprocess, "run")
    @patch.object(call_check, "objects")
    @patch.object(call_check, "pactl")
    @patch.object(call_check, "headset")
    def test_music_selection_does_not_switch_the_mic(self, headset, pactl, objects, run):
        headset.return_value = self.card
        objects.side_effect = lambda kind: [{"name": "airpods-" + kind,
                                             "properties": {"device.name": self.card["name"],
                                                            "object.id": "42"}}] if kind == "sinks" else []
        call_check.select_mode("music")
        self.assertEqual(len(run.call_args_list), 1)
        self.assertIn("audio-output", run.call_args.args[0][0])

    @patch.object(call_check.time, "sleep")
    @patch.object(call_check, "nodes", return_value=[])
    @patch.object(call_check, "pactl", side_effect=lambda *args: "speaker" if args[0] == "get-default-sink" else "mic")
    @patch.object(call_check, "headset")
    def test_failed_call_selection_preserves_music_profile(self, headset, pactl, _nodes, _sleep):
        headset.return_value = self.card
        with self.assertRaisesRegex(RuntimeError, "did not appear"):
            call_check.select_mode("call")
        self.assertFalse(any(call.args[0] == "set-card-profile" for call in pactl.call_args_list))
        pactl.assert_any_call("set-default-source", "mic")

    @patch.object(call_check.time, "sleep")
    @patch.object(call_check, "node", side_effect=lambda kind, card: "speaker" if kind == "sinks" else "")
    @patch.object(call_check, "pactl", side_effect=lambda *args: "speaker" if args[0] == "get-default-sink" else "")
    @patch.object(call_check, "headset")
    def test_missing_mic_restores_playback_profile(self, headset, pactl, _node, _sleep):
        headset.return_value = self.card
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            call_check.main()
        pactl.assert_any_call("set-card-profile", self.card["name"], "headset-head-unit-msbc")
        pactl.assert_any_call("set-card-profile", self.card["name"], "a2dp-sink")

    @patch.object(call_check.time, "sleep")
    @patch.object(call_check, "pactl", side_effect=lambda *args: "airpods-speaker" if args[0] == "get-default-sink" else "")
    @patch.object(call_check.subprocess, "run")
    @patch.object(call_check, "record", return_value=8)
    @patch.object(call_check, "node", side_effect=lambda kind, card: "airpods-mic" if kind == "sources" else "airpods-speaker")
    @patch.object(call_check, "headset")
    def test_records_and_plays_on_same_card(self, headset, _node, record, playback, pactl, _sleep):
        headset.return_value = self.card
        self.assertIn("Played back", call_check.main())
        self.assertEqual(record.call_args.args[0], "airpods-mic")
        self.assertEqual(playback.call_args.args[0][:3],
                         (call_check.PLAY, "--target", "airpods-speaker"))
        pactl.assert_any_call("set-card-profile", self.card["name"], "a2dp-sink")


if __name__ == "__main__":
    unittest.main()
