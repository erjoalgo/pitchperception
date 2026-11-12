An interactive terminal game to test your pitch perception. Inspired by
"Measure your pitch perception abilities" from
http://jakemandell.com/adaptivepitch.

The game plays two tones and asks whether the second was higher or lower.
Answer with the Up and Down arrow keys (`r` repeats the tones, `q` quits).
Each time you answer enough correctly, the difference between the tones is
halved; when you miss too many, the game reports the smallest difference you
could hear.

Requirements: the tones are played with the `beep` command
(`$ sudo apt install beep`), which needs a PC speaker and permission to use
it, so the game won't make sound on most laptops.

To install:

`$ pip install pitchperception`

To play:

`$ pitchperception`
