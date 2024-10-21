import serial
import time
from ovos_bus_client.message import Message
from ovos_mark1.faceplate.icons import MusicIcon, WarningIcon, SnowIcon, StormIcon, SunnyIcon, \
    CloudyIcon, PartlyCloudyIcon, WindIcon, RainIcon, LightRainIcon
from ovos_plugin_manager.phal import PHALPlugin
from ovos_utils import create_daemon
from ovos_utils.log import LOG
from ovos_utils.network_utils import is_connected
from threading import Event
from time import sleep

from ovos_PHAL_plugin_mk1.arduino import EnclosureReader, EnclosureWriter


# The Mark 1 hardware consists of a Raspberry Pi main CPU which is connected
# to an Arduino over the serial port.  A custom serial protocol sends
# commands to control various visual elements which are controlled by the
# Arduino (e.g. two circular rings of RGB LEDs; and four 8x8 white LEDs).
#
# The Arduino can also send back notifications in response to either
# pressing or turning a rotary encoder.


class MycroftMark1Validator:
    @staticmethod
    def validate(config=None):
        """ this method is called before loading the plugin.
        If it returns False the plugin is not loaded.
        This allows a plugin to run platform checks"""
        # TODO how to detect if running in a mark1 ?
        #  detect "/dev/ttyAMA0" ?
        return True


class MycroftMark1(PHALPlugin):
    """
       Serves as a communication interface between Arduino and Mycroft Core.

       ``Enclosure`` initializes and aggregates all enclosures implementation.

       E.g. ``EnclosureEyes``, ``EnclosureMouth`` and ``EnclosureArduino``

       It also listens to the basic messages in order to perform those core actions
       on the unit.

       E.g. Start and Stop talk animation
       """
    validator = MycroftMark1Validator

    def __init__(self, bus=None, config=None):
        super().__init__(bus=bus, name="ovos-PHAL-plugin-mk1", config=config)
        self.stopped = Event()
        self.config = config or {
            "port": "/dev/ttyAMA0",
            "rate": 9600,
            "timeout": 5.0
        }
        self.__init_serial()
        self.reader = EnclosureReader(self.serial, self.bus, self.handle_button_press)
        self.writer = EnclosureWriter(self.serial, self.bus)

        self._num_pixels = 12 * 2
        self._current_rgb = [(255, 255, 255) for i in range(self._num_pixels)]
        self.showing_visemes = False
        self.speaking = False
        self.listening = False

        LOG.debug("clearing eyes and mouth")
        self.__reset()

        # TODO settings
        #  - default eye color
        #  - narrow / half / full eyes default position
        self._init_animation()

        self.bus.on("system.factory.reset.ping", self.handle_register_factory_reset_handler)
        self.bus.on("system.factory.reset.phal", self.handle_factory_reset)

        self.bus.on("mycroft.internet.connected", self.on_display_reset)
        self.bus.on("mycroft.stop", self.on_display_reset)
        self.bus.on("ovos.common_play.play", self.on_music)
        self.bus.on("ovos.common_play.stop", self.on_display_reset)
        self.bus.on("mycroft.audio.service.play", self.on_music)
        self.bus.on("mycroft.audio.service.stop", self.on_display_reset)

        self.bus.on("ovos.mk1.display_date", self.on_display_date)
        self.bus.on("ovos.mk1.display_time", self.on_display_time)

        self.bus.emit(Message("system.factory.reset.register",
                              {"skill_id": "ovos-phal-plugin-mk1"}))

    def _init_animation(self):
        # change eye color
        r = 0
        g = 0
        b = 255
        color = (r * 65536) + (g * 256) + b
        self._current_rgb = [(r, g, b) for i in range(self._num_pixels)]
        self.writer.write("eyes.color=" + str(color))

        # narrow eyes while we do system checks
        self.on_eyes_narrow()

        # signal no internet
        if not is_connected():
            self.on_no_internet()

        # if core is ready, reset eyes
        self.bus.once("mycroft.ready", self.on_eyes_reset)
        if self._check_services_ready():
            self.on_eyes_reset()

    def _check_services_ready(self):
        """Report if all specified services are ready.

        services (iterable): service names to check.
        """
        services = {k: False for k in ["skills",  # ovos-core
                                       "audio",  # ovos-audio
                                       "voice"  # ovos-dinkum-listener
                                       ]}

        for ser, rdy in services.items():
            if rdy:
                # already reported ready
                continue
            response = self.bus.wait_for_response(
                Message(f'mycroft.{ser}.is_ready',
                        context={"source": "mk1", "destination": "skills"}))
            if response and response.data['status']:
                services[ser] = True
        return all([services[ser] for ser in services])

    def __init_serial(self):
        LOG.info("Connecting to mark1 faceplate")
        try:
            self.port = self.config.get("port", "/dev/ttyAMA0")
            self.rate = self.config.get("rate", 9600)
            self.timeout = self.config.get("timeout", 5.0)
            self.serial = serial.serial_for_url(
                url=self.port, baudrate=self.rate, timeout=self.timeout)
            LOG.info("Connected to: %s rate: %s timeout: %s" %
                     (self.port, self.rate, self.timeout))
        except Exception as e:
            LOG.exception(f"Impossible to connect to serial: {self.port}")
            raise

    def __reset(self, message: Message):
        self.writer.write("eyes.reset")
        self.writer.write("mouth.reset")

    def handle_button_press(self):
        if self.speaking or self.listening:
            self.bus.emit(Message("mycroft.stop"))
        else:
            self.bus.emit(Message("mycroft.mic.listen"))

    def on_music(self, message: Message):
        MusicIcon(bus=self.bus).display()

    def handle_get_color(self, message):
        """Get the eye RGB color for all pixels
        Returns:
           (list) list of (r,g,b) tuples for each eye pixel
        """
        self.bus.emit(message.reply("enclosure.eyes.rgb",
                                    {"pixels": self._current_rgb}))

    def handle_factory_reset(self, message):
        self.writer.write("eyes.spin")
        self.writer.write("mouth.reset")
        # TODO re-flash firmware to faceplate

    def handle_register_factory_reset_handler(self, message):
        self.bus.emit(message.reply("system.factory.reset.register",
                                    {"skill_id": "ovos-phal-plugin-mk1"}))

    # Audio Events
    def on_record_begin(self, message: Message):
        # NOTE: ignore self._mouth_events, listening should ALWAYS be obvious
        self.listening = True
        self.on_listen(message)

    def on_record_end(self, message: Message):
        self.listening = False
        self.on_display_reset(message)

    def on_audio_output_start(self, message: Message):
        self.speaking = True
        if self._mouth_events:
            self.on_talk(message)

    def on_audio_output_end(self, message: Message):
        self.speaking = False
        if self._mouth_events:
            self.on_display_reset(message)

    def on_awake(self, message: Message):
        ''' on wakeup animation
        triggered by "mycroft.awoken"
        '''
        self.writer.write("eyes.reset")
        sleep(1)
        self.writer.write("eyes.blink=b")
        sleep(1)
        # brighten the rest of the way
        self.writer.write("eyes.level=" + str(self.old_brightness))

    def on_sleep(self, message: Message):
        ''' on naptime animation
        triggered by "recognizer_loop:sleep"
        '''
        # Dim and look downward to 'go to sleep'
        # TODO: Get current brightness from somewhere
        self.old_brightness = 30
        for i in range(0, (self.old_brightness - 10) // 2):
            level = self.old_brightness - i * 2
            self.writer.write("eyes.level=" + str(level))
            time.sleep(0.15)
        self.writer.write("eyes.look=d")

    def on_reset(self, message: Message):
        """The enclosure should restore itself to a started state.
        Typically this would be represented by the eyes being 'open'
        and the mouth reset to its default (smile or blank).
        triggered by "enclosure.reset"
        """
        self.writer.write("eyes.reset")
        self.writer.write("mouth.reset")

    # System Events
    def on_no_internet(self, message: Message):
        """
        triggered by "enclosure.notify.no_internet"
        """
        WarningIcon(bus=self.bus).display()

    def on_system_reset(self, message: Message):
        """The enclosure hardware should reset any CPUs, etc.
        triggered by "enclosure.system.reset"
        """
        self.writer.write("system.reset")

    def on_system_mute(self, message: Message):
        """Mute (turn off) the system speaker.
        triggered by "enclosure.system.mute"
        """
        self.writer.write("system.mute")

    def on_system_unmute(self, message: Message):
        """Unmute (turn on) the system speaker.
        triggered by "enclosure.system.unmute"
        """
        self.writer.write("system.unmute")

    def on_system_blink(self, message: Message):
        """The 'eyes' should blink the given number of times.
        triggered by "enclosure.system.blink"

        Args:
            times (int): number of times to blink
        """
        times = 1
        times = message.data.get("times", times)
        self.writer.write("system.blink=" + str(times))

    # Eyes messages
    def on_eyes_on(self, message: Message):
        """Illuminate or show the eyes.
        triggered by "enclosure.eyes.on"
        """
        self.writer.write("eyes.on")

    def on_eyes_off(self, message: Message):
        """Turn off or hide the eyes.
        triggered by "enclosure.eyes.off"
        """
        self.writer.write("eyes.off")

    def on_eyes_fill(self, message: Message):
        """triggered by "enclosure.eyes.fill" """
        percent = int(message.data.get("percentage", 0))
        amount = int(round(23.0 * percent / 100.0))
        self.writer.write("eyes.fill=" + str(amount))

    def on_eyes_blink(self, message: Message):
        """Make the eyes blink
        triggered by "enclosure.eyes.blink"
        Args:
            side (str): 'r', 'l', or 'b' for 'right', 'left' or 'both'
        """
        side = message.data.get("side", "b")
        self.writer.write("eyes.blink=" + side)

    def on_eyes_narrow(self, message: Message):
        """Make the eyes look narrow, like a squint
        triggered by "enclosure.eyes.narrow"
        """
        self.writer.write("eyes.narrow")

    def on_eyes_look(self, message: Message):
        """Make the eyes look to the given side
        triggered by "enclosure.eyes.look"
        Args:
            side (str): 'r' for right
                        'l' for left
                        'u' for up
                        'd' for down
                        'c' for crossed
        """
        side = message.data.get("side", "")
        self.writer.write("eyes.look=" + side)

    def on_eyes_color(self, message: Message):
        """Change the eye color to the given RGB color
        triggered by "enclosure.eyes.color"
        Args:
            r (int): 0-255, red value
            g (int): 0-255, green value
            b (int): 0-255, blue value
        """
        r = int(message.data.get("r", 255))
        g = int(message.data.get("g", 255))
        b = int(message.data.get("b", 255))
        color = (r * 65536) + (g * 256) + b
        self._current_rgb = [(r, g, b) for i in range(self._num_pixels)]
        self.writer.write("eyes.color=" + str(color))

    def on_eyes_brightness(self, message: Message):
        """Set the brightness of the eyes in the display.
        triggered by "enclosure.eyes.brightness"
        Args:
            level (int): 1-30, bigger numbers being brighter
        """
        level = message.data.get("level", 30)
        self.writer.write("eyes.level=" + str(level))

    def on_eyes_reset(self, message: Message):
        """Restore the eyes to their default (ready) state
        triggered by "enclosure.eyes.reset".
        """
        self.writer.write("eyes.reset")

    def on_eyes_timed_spin(self, message: Message):
        """Make the eyes 'roll' for the given time.
        triggered by "enclosure.eyes.timedspin"
        Args:
            length (int): duration in milliseconds of roll, None = forever
        """
        length = message.data.get("length", 5000)
        self.writer.write("eyes.spin=" + str(length))

    def on_eyes_volume(self, message: Message):
        """Indicate the volume using the eyes
        triggered by "enclosure.eyes.volume"
        Args:
            volume (int): 0 to 11
        """
        volume = message.data.get("volume", 4)
        self.writer.write("eyes.volume=" + str(volume))

    def on_eyes_spin(self, message: Message):
        """
        triggered by "enclosure.eyes.spin"
        """
        self.writer.write("eyes.spin")

    def on_eyes_set_pixel(self, message: Message):
        """
        triggered by "enclosure.eyes.set_pixel"
        """
        idx = int(message.data.get("idx", 0))
        r = int(message.data.get("r", 255))
        g = int(message.data.get("g", 255))
        b = int(message.data.get("b", 255))
        self._current_rgb[idx] = (r, g, b)
        color = (r * 65536) + (g * 256) + b
        self.writer.write("eyes.set=" + str(idx) + "," + str(color))

    # Display (faceplate) messages
    def on_display_reset(self, message: Message):
        """Restore the mouth display to normal (blank)
        triggered by "enclosure.mouth.reset" / "recognizer_loop:record_end"
        """
        self.writer.write("mouth.reset")

    def on_talk(self, message: Message):
        """Show a generic 'talking' animation for non-synched speech
        triggered by "enclosure.mouth.talk"
        """
        self.writer.write("mouth.talk")

    def on_think(self, message: Message):
        """Show a 'thinking' image or animation
        triggered by "enclosure.mouth.think"
        """
        self.writer.write("mouth.think")

    def on_listen(self, message: Message):
        """Show a 'thinking' image or animation
        triggered by "enclosure.mouth.listen" / "recognizer_loop:record_begin"
        """
        self.writer.write("mouth.listen")

    def on_smile(self, message: Message):
        """Show a 'smile' image or animation
        triggered by "enclosure.mouth.smile"
        """
        self.writer.write("mouth.smile")

    def on_viseme(self, message: Message):
        """Display a viseme mouth shape for synced speech

        triggered by "enclosure.mouth.viseme"

        Args:
            code (int):  0 = shape for sounds like 'y' or 'aa'
                         1 = shape for sounds like 'aw'
                         2 = shape for sounds like 'uh' or 'r'
                         3 = shape for sounds like 'th' or 'sh'
                         4 = neutral shape for no sound
                         5 = shape for sounds like 'f' or 'v'
                         6 = shape for sounds like 'oy' or 'ao'
        """
        code = message.data["code"]
        self.writer.write('mouth.viseme=' + code)

    def on_viseme_list(self, message: Message):
        """ Send mouth visemes as a list in a single message.

            Args:
                start (int):    Timestamp for start of speech
                viseme_pairs:   Pairs of viseme id and cumulative end times
                                (code, end time)

                                codes:
                                 0 = shape for sounds like 'y' or 'aa'
                                 1 = shape for sounds like 'aw'
                                 2 = shape for sounds like 'uh' or 'r'
                                 3 = shape for sounds like 'th' or 'sh'
                                 4 = neutral shape for no sound
                                 5 = shape for sounds like 'f' or 'v'
                                 6 = shape for sounds like 'oy' or 'ao'
        """
        start = message.data['start']
        visemes = message.data['visemes']

        def animate_mouth():
            nonlocal start, visemes
            self.showing_visemes = True
            previous_end = -1
            for code, end in visemes:
                if not self.showing_visemes:
                    break
                if end < previous_end:
                    start = time.time()
                previous_end = end
                if time.time() < start + end:
                    self.writer.write('mouth.viseme=' + code)
                    sleep(start + end - time.time())
            self.writer.write("mouth.reset")
            self.showing_visemes = False

        # use a thread to not block FakeBus (eg, voice sat)
        create_daemon(animate_mouth)

    def on_text(self, message: Message):
        """Display text (scrolling as needed)

        triggered by "enclosure.mouth.text"

        Args:
            text (str): text string to display
        """
        text = message.data.get("text", "")
        self.writer.write("mouth.text=" + text)

    def on_display(self, message: Message):
        """Display images on faceplate. Currently supports images up to 16x8,
           or half the face. You can use the 'x' parameter to cover the other
           half of the faceplate.

       triggered by "enclosure.mouth.display"

        Args:
            img_code (str): text string that encodes a black and white image
            x (int): x offset for image
            y (int): y offset for image
            refresh (bool): specify whether to clear the faceplate before
                            displaying the new image or not.
                            Useful if you'd like to display muliple images
                            on the faceplate at once.
        """
        code = message.data.get("img_code", "")
        x_offset = int(message.data.get("xOffset", 0))
        y_offset = int(message.data.get("yOffset", 0))
        clear_previous = message.data.get("clearPrev", "")
        self._do_display(code, int(x_offset), int(y_offset), clear_previous.lower() == "true")

    def _do_display(self, img_code: str, x_offset: int = 0, y_offset: int = 0, refresh: bool = False):
        """Display images on faceplate. Currently supports images up to 16x8,
           or half the face. You can use the 'x' parameter to cover the other
           half of the faceplate.

       triggered by "enclosure.mouth.display"

        Args:
            img_code (str): text string that encodes a black and white image
            x (int): x offset for image
            y (int): y offset for image
            refresh (bool): specify whether to clear the faceplate before
                            displaying the new image or not.
                            Useful if you'd like to display muliple images
                            on the faceplate at once.
        """

        clear_previous = int(refresh)
        clear_previous = "cP=" + str(clear_previous) + ","
        x_offset = "x=" + str(x_offset) + ","
        y_offset = "y=" + str(y_offset) + ","

        message = "mouth.icon=" + x_offset + y_offset + clear_previous + img_code
        # Check if message exceeds Arduino's serial buffer input limit 64 bytes
        if len(message) > 60:
            message1 = message[:31] + "$"
            message2 = "mouth.icon=$" + message[31:]
            self.writer.write(message1)
            sleep(0.25)  # writer bugs out if sending messages too rapidly
            self.writer.write(message2)
        else:
            sleep(0.1)
            self.writer.write(message)

    def on_weather_display(self, message):
        """Show a the temperature and a weather icon

        triggered by "enclosure.weather.display"

        Args:
            img_code (char): one of the following icon codes
                         0 = sunny
                         1 = partly cloudy
                         2 = cloudy
                         3 = light rain
                         4 = raining
                         5 = stormy
                         6 = snowing
                         7 = wind/mist
            temp (int): the temperature (either C or F, not indicated)
        """
        # Convert img_code to icon
        img_code = message.data.get("img_code", None)
        icon = None
        if img_code == 0:
            # sunny
            icon = SunnyIcon(bus=self.bus).encode()
        elif img_code == 1:
            # partly cloudy
            icon = PartlyCloudyIcon(bus=self.bus).encode()
        elif img_code == 2:
            # cloudy
            icon = CloudyIcon(bus=self.bus).encode()
        elif img_code == 3:
            # light rain
            icon = LightRainIcon(bus=self.bus).encode()
        elif img_code == 4:
            # raining
            icon = RainIcon(bus=self.bus).encode()
        elif img_code == 5:
            # storming
            icon = StormIcon(bus=self.bus).encode()
        elif img_code == 6:
            # snowing
            icon = SnowIcon(bus=self.bus).encode()
        elif img_code == 7:
            # wind/mist
            icon = WindIcon(bus=self.bus).encode()

        temp = message.data.get("temp", None)
        if icon is not None and temp is not None:
            icon = "x=2," + icon
            msg = "weather.display=" + str(temp) + "," + str(icon)
            self.writer.write(msg)

    # date/time
    def on_display_date(self, message: Message):
        self._deactivate_mouth_events()
        self.on_text(message)
        sleep(10)
        self.on_display_reset()
        self._activate_mouth_events()

    def on_display_time(self, message: Message):
        code_dict = {
            ':': 'CIICAA',
            '0': 'EIMHEEMHAA',
            '1': 'EIIEMHAEAA',
            '2': 'EIEHEFMFAA',
            '3': 'EIEFEFMHAA',
            '4': 'EIMBABMHAA',
            '5': 'EIMFEFEHAA',
            '6': 'EIMHEFEHAA',
            '7': 'EIEAEAMHAA',
            '8': 'EIMHEFMHAA',
            '9': 'EIMBEBMHAA',
        }

        self._deactivate_mouth_events()
        display_time = message.data.get("text")
        # clear screen (draw two blank sections, numbers cover rest)
        if len(display_time) == 4:
            # for 4-character times, 9x8 blank
            self._do_display(img_code="JIAAAAAAAAAAAAAAAAAA", refresh=False)
            # self.enclosure.mouth_display(img_code="JIAAAAAAAAAAAAAAAAAA",
            # refresh=False)
            self._do_display(img_code="JIAAAAAAAAAAAAAAAAAA", x_offset=22, refresh=False)
            # self.enclosure.mouth_display(img_code="JIAAAAAAAAAAAAAAAAAA",
            #                              x=22, refresh=False)
        else:
            # for 5-character times, 7x8 blank
            self._do_display(img_code="HIAAAAAAAAAAAAAA", refresh=False)
            # self.enclosure.mouth_display(img_code="HIAAAAAAAAAAAAAA",
            #                              refresh=False)
            self._do_display(img_code="HIAAAAAAAAAAAAAA", x_offset=24, refresh=False)
            # self.enclosure.mouth_display(img_code="HIAAAAAAAAAAAAAA",
            #                              x=24, refresh=False)

        # draw the time, centered on display
        xoffset = (32 - (4 * (len(display_time)) - 2)) / 2
        for c in display_time:
            if c in code_dict:
                self._do_display(code_dict[c], x_offset=xoffset, refresh=False)
                if c == ":":
                    xoffset += 2  # colon is 1 pixels + a space
                else:
                    xoffset += 4  # digits are 3 pixels + a space

        self._do_display("CIAAAA", x_offset=29, refresh=False)
        sleep(5)
        self.on_display_reset()
        self._activate_mouth_events()
