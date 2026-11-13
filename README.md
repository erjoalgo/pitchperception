An interactive terminal game to test your pitch perception. Inspired by
"Measure your pitch perception abilities" from
http://jakemandell.com/adaptivepitch.

The game plays two tones and asks whether the second was higher or lower.
Answer with the Up and Down arrow keys (`r` repeats the tones, `q` quits).
Each time you answer enough correctly, the difference between the tones is
halved; when you miss too many, the game reports the smallest difference you
could hear.

Requirements: a command to play the tones: `paplay` or `pw-play` (PulseAudio
or PipeWire, which most Linux desktops have), `aplay` (ALSA), or `afplay`
(macOS). The first one installed is used; to choose another, pass
`--player`, e.g. `pitchperception --player aplay`.

To install:

`$ pip install pitchperception`

To play:

`$ pitchperception`
