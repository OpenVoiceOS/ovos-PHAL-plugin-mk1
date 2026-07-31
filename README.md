# ovos-PHAL-plugin-mk1

This is a PHAL (Platform Hardware Abstraction Layer) plugin for OpenVoiceOS. It controls the Mark 1 hardware: the eye and mouth faceplate, and the pins on the back of the device.

The firmware for the Mark 1 Arduino, which drives the eyes and faceplate, is in [OpenVoiceOS/mycroft-mark1-firmware](https://github.com/OpenVoiceOS/mycroft-mark1-firmware).

[OpenVoiceOS/ovos-mark1-utils](https://github.com/OpenVoiceOS/ovos-mark1-utils) has utilities to set the faceplate pixel by pixel.

## Install

```bash
pip install ovos-PHAL-plugin-mk1
```

## Usage

OpenVoiceOS loads this plugin through the `opm.phal` entry point. Once installed, PHAL detects and starts it automatically on Mark 1 hardware.

### Serial port protocol

See [protocols.txt](./protocols.txt) for the full list of commands you can send to the faceplate.

You can send commands from the command line on a Raspberry Pi:

```
$ echo "eyes.blink" > /dev/ttyAMA0
$ echo "eyes.color=16711680" > /dev/ttyAMA0
$ echo "mouth.text=I am angry!" > /dev/ttyAMA0
```

These commands blink the eyes, turn them red, then show the phrase on the faceplate.

### Graphics

The `mouth.icon=` command takes a custom format for black-and-white images. Use the [HTML editor](http://htmlpreview.github.io/?https://raw.githubusercontent.com/MycroftAI/enclosure-mark1/master/editor.html) to create the image strings you send.

### IO pins

Looking at the device from the back, the pins are laid out as:

```
             -----------------------------------------------------------------------------------------------
RCA Port    | 2 | 4 | 6 | 8 | 10 | 12 | 14 | 16 | 18 | 20 | 22 | 24 | 26 | 28 | 30 | 32 | 34 | 36 | 38 | 40 |
            | 1 | 3 | 5 | 7 |  9 | 11 | 13 | 15 | 17 | 19 | 21 | 23 | 25 | 27 | 29 | 31 | 33 | 35 | 37 | 39 |
             -----------------------------------------------------------------------------------------------

 HDMI                         Ethernet                        USB     USB
```

| Pin| Description          |
|:--:|:---------------------|
| 1  | GND                  |
| 2  | +12V                 |
| 3  | GND                  |
| 4  | +5V                  |
| 5  | GND                  |
| 6  | +3.3V                |
| 7  | Arduino Reset        |
| 8  | Arduino D5           |
| 9  | Arduino D6           |
| 10 | Arduino D10          |
| 11 | Arduino A2           |
| 12 | Arduino A3           |
| 13 | +3.3V                |
| 14 | +3.3V                |
| 15 | +3.3V                |
| 16 | GND                  |
| 17 | GND                  |
| 18 | GND                  |
| 19 | +5V                  |
| 20 | +5V                  |
| 21 | +5V                  |
| 22 | +5V                  |
| 23 | GND                  |
| 24 | GND                  |
| 25 | Raspberry Pi ID_SC   |
| 26 | Raspberry Pi ID_SD   |
| 27 | Raspberry Pi GPIO 4  |
| 28 | Raspberry Pi GPIO 5  |
| 29 | Raspberry Pi GPIO 6  |
| 30 | Raspberry Pi GPIO 7  |
| 31 | Raspberry Pi GPIO 8  |
| 32 | Raspberry Pi GPIO 9  |
| 33 | Raspberry Pi GPIO 10 |
| 34 | Raspberry Pi GPIO 11 |
| 35 | Raspberry Pi GPIO 12 |
| 36 | Raspberry Pi GPIO 16 |
| 37 | Raspberry Pi GPIO 25 |
| 38 | Raspberry Pi GPIO 26 |
| 39 | GND                  |
| 40 | GND                  |

**WARNING: This is not the same as the standard Raspberry Pi GPIO headers.**

## Related projects

- [OpenVoiceOS/mycroft-mark1-firmware](https://github.com/OpenVoiceOS/mycroft-mark1-firmware) — the Arduino firmware for the Mark 1 eyes and faceplate.
- [OpenVoiceOS/ovos-mark1-utils](https://github.com/OpenVoiceOS/ovos-mark1-utils) — utilities to set the faceplate pixel by pixel.

## License

Apache-2.0, see [LICENSE](./LICENSE).
