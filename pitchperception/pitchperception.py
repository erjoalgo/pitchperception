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

    # Options to play to a given PulseAudio or PipeWire sink, for the commands
    # that support one.
    DEVICE_OPTIONS = {
        "paplay": "--device={}",
        "pw-play": "--target={}",
    }

    def __init__(self, cmd, device=None):
        self.cmd = cmd
        self.device = device

    def __str__(self):
        if self.device:
            return "{} on {}".format(self.cmd[0], self.device)
        return self.cmd[0]

    @classmethod
    def installed(cls):
        """Returns a player for each available command, in order of preference."""
        return [cls(cmd) for cmd in cls.COMMANDS if shutil.which(cmd[0])]

    @classmethod
    def find(cls, name=None, device=None):
        """Returns a player for the first available command, or None.

        If name is given, only the command with that name is considered.
        If device is given, only commands that can play to it are, and the
        player plays to it."""
        for player in cls.installed():
            if name not in (None, player.cmd[0]):
                continue
            if device is None:
                return player
            if player.cmd[0] in cls.DEVICE_OPTIONS:
                return cls(player.cmd, device)
        return None

    def command(self, path):
        """Returns the command to play the WAV file at path."""
        cmd = list(self.cmd)
        if self.device:
            cmd.append(self.DEVICE_OPTIONS[self.cmd[0]].format(self.device))
        return cmd + [path]

    def try_play_tone(self, freq):
        """Play a tone at the given frequency in Hz.

        Raises subprocess.CalledProcessError if the player fails."""
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            write_tone_wav(freq, path)
            subprocess.check_output(self.command(path), stderr=subprocess.PIPE)
        finally:
            os.remove(path)

    def failure_message(self, ex):
        return "{} failed to play a tone: {}".format(
            self, ex.stderr.decode().strip())

    def play_tone(self, freq):
        """Play a tone at the given frequency in Hz, or exit if it fails."""
        try:
            self.try_play_tone(freq)
        except subprocess.CalledProcessError as ex:
            sys.exit(self.failure_message(ex))


def list_sinks():
    """Returns the names of the PulseAudio or PipeWire sinks, the default one
    first, or an empty list if they can't be listed."""
    if not shutil.which("pactl"):
        return []
    env = dict(os.environ, LC_ALL="C")  # for the "Default Sink:" label
    try:
        sinks = subprocess.check_output(["pactl", "list", "short", "sinks"],
                                        stderr=subprocess.DEVNULL, env=env,
                                        universal_newlines=True)
        info = subprocess.check_output(["pactl", "info"],
                                       stderr=subprocess.DEVNULL, env=env,
                                       universal_newlines=True)
    except subprocess.CalledProcessError:
        return []
    # each line is: index, name, driver, sample spec, state
    names = [line.split("\t")[1] for line in sinks.splitlines() if "\t" in line]
    default = None
    for line in info.splitlines():
        if line.startswith("Default Sink:"):
            default = line.split(":", 1)[1].strip()
    names.sort(key=lambda name: name != default)
    return names


def candidate_outputs():
    """Yields a player for each installed player, in order of preference, and
    for the ones that can play to a given sink, one for each sink."""
    sinks = list_sinks()
    for player in AudioPlayer.installed():
        if sinks and player.cmd[0] in AudioPlayer.DEVICE_OPTIONS:
            for sink in sinks:
                yield AudioPlayer(player.cmd, sink)
        else:
            yield player


def choose_player(test_freq=440):
    """Play a test tone with each installed player, on each sink it can play
    to, and return the first one the user hears, or None."""
    # sinks the user didn't hear from one player, to skip with the others
    unheard_sinks = set()
    for player in candidate_outputs():
        if player.device in unheard_sinks:
            continue
        while True:
            print("Playing a test tone with {}...".format(player))
            try:
                player.try_play_tone(test_freq)
            except subprocess.CalledProcessError as ex:
                print(player.failure_message(ex))
                break
            try:
                answer = input("Did you hear it (y: yes, n: no, r: repeat)? ")
            except EOFError:
                return None
            answer = answer.strip().lower()
            if answer == "y":
                options = "--player {}".format(player.cmd[0])
                if player.device:
                    options += " --device {}".format(player.device)
                print("Using {}; to skip this next time, pass {}"
                      .format(player, options))
                return player
            elif answer == "n":
                if player.device:
                    unheard_sinks.add(player.device)
                break


class UserQuitError(Exception):
    """Propagates a user quit up the stack."""
    pass

class PitchPerceptionChallenge(object):
    """An interactive game to test the user's pitch perception abilities."""
    def __init__(self, game_config, audio_player):
        self.game_config = game_config
        self.audio_player = audio_player
        self.win = None
        # (delta, [whether each attempt was correct]) for each delta tried
        self.attempts = []
        # attributes for the box of a correct and an incorrect attempt
        self.box_attrs = {True: curses.A_NORMAL, False: curses.A_NORMAL}

    def init_colors(self):
        if not curses.has_colors():
            return
        curses.start_color()
        # keep the terminal's own colors for everything else
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_GREEN)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_RED)
        self.box_attrs = {True: curses.color_pair(1),
                          False: curses.color_pair(2)}

    def curses_print(self, message):
        self.win.clear()
        self.win.addstr(0, 0, message)
        y, x = self.win.getyx()
        self.draw_attempts(y + 2)
        # leave the cursor after the message, where the user answers
        self.win.move(y, x)
        self.win.refresh()

    def draw_attempts(self, top):
        """Draw a row for each delta tried, from the top row, with a green box
        for each correct attempt and a red one for each incorrect one."""
        height, _ = self.win.getmaxyx()
        # the most recent rows that fit
        rows = self.attempts[max(0, len(self.attempts) - (height - top)):]
        for y, (delta, results) in enumerate(rows, top):
            self.win.addstr(y, 0, "{:>8g}Hz ".format(delta))
            for is_correct in results:
                self.win.addstr(" o " if is_correct else " x ",
                                self.box_attrs[is_correct])
                self.win.addstr(" ")

    def curses_getch(self):
        return self.win.getch()

    def _play_tone_challenge(self, first, second):
        assert first != second
        self.curses_print("Listen...")
        self.audio_player.play_tone(first)
        self.audio_player.play_tone(second)
        prompt = ("Is the second pitch higher or lower "
                  "(Up: higher, Down: lower, r: repeat, q: quit)? ")
        UP, DOWN, REPEAT, QUIT = curses.KEY_UP, curses.KEY_DOWN, ord("r"), ord("q")
        while True:
            self.curses_print(prompt)
            ch = self.curses_getch()
            if ch == REPEAT:
                self.curses_print("Listen...")
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
        results = []
        self.attempts.append((delta, results))

        while True:
            first = self.game_config.ref_tone
            second = first + delta * (1 if self.flip_coin() else -1)
            if self.flip_coin():
                first, second = second, first
            is_correct = self._play_tone_challenge(first, second)
            results.append(is_correct)
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
            self.init_colors()
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
    player_group = parser.add_mutually_exclusive_group()
    player_group.add_argument("--player",
                              choices=[cmd[0] for cmd in AudioPlayer.COMMANDS],
                              help="the command to play tones with "
                              "(default: the first one installed)")
    player_group.add_argument("--choose-player", action="store_true",
                              help="play a test tone with each installed "
                              "player, and use the first one you hear")
    parser.add_argument("--device",
                        help="the PulseAudio or PipeWire sink to play tones "
                        "to, with paplay or pw-play; 'pactl list short sinks' "
                        "lists them")
    args = parser.parse_args()
    if args.device and args.choose_player:
        parser.error("--device can't be used with --choose-player")

    if not AudioPlayer.installed():
        sys.exit("pitchperception needs a command to play sound: one of {}"
                 .format(", ".join(cmd[0] for cmd in AudioPlayer.COMMANDS)))
    if args.choose_player:
        audio_player = choose_player()
        if not audio_player:
            sys.exit("No player played a tone you could hear; check your "
                     "sound output device and volume.")
    else:
        audio_player = AudioPlayer.find(args.player, args.device)
        if not audio_player:
            if args.player and not shutil.which(args.player):
                sys.exit("{} is not installed".format(args.player))
            sys.exit("--device needs paplay or pw-play")

    game_config = PitchPerceptionGameConfig()
    game = PitchPerceptionChallenge(game_config, audio_player)
    game.start()


if __name__ == "__main__":
    main()
