#!/usr/bin/env python3

"""An interactive game to test the user's pitch perception abilities.


Inspired by "Measure your pitch perception abilities"
from http://jakemandell.com/adaptivepitch.
"""

import array
import contextlib
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import wave

import curses

try:
    from ._version import __version__
except ImportError:
    __version__ = "unknown"


class PitchPerceptionGameConfig(object):
    """Config for a PitchPerceptionGame."""
    def __init__(self,
                 initial_delta=220,
                 ref_tone=440,
                 max_incorrect_attempts=2,
                 min_correct_attempts=3):
        self.initial_delta = initial_delta
        self.ref_tone = ref_tone
        self.max_incorrect_attempts = max_incorrect_attempts
        self.min_correct_attempts = min_correct_attempts


SAMPLE_RATE = 44100
TONE_SECONDS = 0.5

def write_tone_wav(freq, path, seconds=TONE_SECONDS):
    """Write a sine tone at freq Hz as a 16-bit mono WAV file."""
    n_samples = int(SAMPLE_RATE * seconds)
    # fade in and out over 10ms, so the tone doesn't start or end with a click
    fade = int(SAMPLE_RATE * 0.01)
    samples = array.array("h")
    for i in range(n_samples):
        envelope = min(1.0, i / fade, (n_samples - i) / fade)
        value = 0.5 * envelope * math.sin(2 * math.pi * freq * i / SAMPLE_RATE)
        samples.append(int(value * 32767))
    if sys.byteorder == "big":
        samples.byteswap()  # WAV data is little-endian
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(samples.tobytes())


class AudioPlayer(object):
    """Plays tones with a command that plays a WAV file."""

    # Commands that play a WAV file, in order of preference.
    COMMANDS = [
        ["paplay"],         # PulseAudio, and PipeWire's PulseAudio support
        ["pw-play"],        # PipeWire
        ["aplay", "-q"],    # ALSA
        ["afplay"],         # macOS
    ]

    def __init__(self, cmd):
        self.cmd = cmd

    @classmethod
    def find(cls):
        """Returns a player for the first available command, or None."""
        for cmd in cls.COMMANDS:
            if shutil.which(cmd[0]):
                return cls(cmd)
        return None

    def play_tone(self, freq):
        """Play a tone at the given frequency in Hz."""
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            write_tone_wav(freq, path)
            try:
                subprocess.check_output(self.cmd + [path],
                                        stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as ex:
                sys.exit("{} failed to play a tone: {}".format(
                    self.cmd[0], ex.stderr.decode().strip()))
        finally:
            os.remove(path)


class UserQuitError(Exception):
    """Propagates a user quit up the stack."""
    pass

class PitchPerceptionChallenge(object):
    """An interactive game to test the user's pitch perception abilities."""
    def __init__(self, game_config, audio_player):
        self.game_config = game_config
        self.audio_player = audio_player
        self.win = None

    def curses_print(self, message):
        self.win.clear()
        self.win.addstr(0, 0, message)
        self.win.refresh()

    def curses_getch(self):
        return self.win.getch()

    def _play_tone_challenge(self, first, second):
        assert first != second
        self.audio_player.play_tone(first)
        self.audio_player.play_tone(second)
        prompt = ("Is the second pitch higher or lower "
                  "(Up: higher, Down: lower, r: repeat, q: quit)? ")
        UP, DOWN, REPEAT, QUIT = curses.KEY_UP, curses.KEY_DOWN, ord("r"), ord("q")
        while True:
            self.curses_print(prompt)
            ch = self.curses_getch()
            if ch == REPEAT:
                self.audio_player.play_tone(first)
                self.audio_player.play_tone(second)
            elif ch in (UP, DOWN):
                return (second > first) == (ch == UP)
            elif ch == QUIT:
                raise UserQuitError()
            else:
                self.curses_print("unknown key: {}".format(ch))
                time.sleep(2)

    @staticmethod
    def flip_coin():
        return random.randint(0, 1)

    def _challenge_at_delta(self, delta):
        """Returns true iff the user can distinguish pitch up to delta Hz."""
        assert delta > 0
        correct, incorrect = 0, 0

        while True:
            first = self.game_config.ref_tone
            second = first + delta * (1 if self.flip_coin() else -1)
            if self.flip_coin():
                first, second = second, first
            is_correct = self._play_tone_challenge(first, second)
            if is_correct:
                correct += 1
                if correct >= self.game_config.min_correct_attempts:
                    return True
            else:
                incorrect += 1
                self.curses_print("incorrect: {} => {}".format(first, second))
                time.sleep(1)
                if incorrect >= self.game_config.max_incorrect_attempts:
                    return False

    @staticmethod
    @contextlib.contextmanager
    def ncurses_win():
        curses_win = curses.initscr()
        try:
            yield curses_win
        finally:
            curses.endwin()

    def start(self):
        end_message = None

        with self.ncurses_win() as self.win:
            curses.noecho()
            # let curses decode arrow keys, whichever escape sequence the
            # terminal sends for them
            self.win.keypad(True)
            delta = self.game_config.initial_delta
            last_delta = None
            while True:
                try:
                    passed = self._challenge_at_delta(delta)
                except UserQuitError:
                    passed = False
                if passed:
                    last_delta, delta = delta, delta/2.0
                elif last_delta is None:
                    end_message = "unable to determine pitch perception"
                    break
                else:
                    end_message = (
                        ("your ear is sensitive to pitch differences "
                         "up to {}Hz").format(delta*2))
                    break

        print (end_message)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args()

    audio_player = AudioPlayer.find()
    if not audio_player:
        sys.exit("pitchperception needs a command to play sound: one of {}"
                 .format(", ".join(cmd[0] for cmd in AudioPlayer.COMMANDS)))

    game_config = PitchPerceptionGameConfig()
    game = PitchPerceptionChallenge(game_config, audio_player)
    game.start()
