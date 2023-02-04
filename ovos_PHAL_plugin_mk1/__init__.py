import serial
import time
from mycroft_bus_client.message import Message
from ovos_plugin_manager.phal import PHALPlugin
from ovos_utils import classproperty
from ovos_utils.log import LOG
from ovos_utils.network_utils import NetworkRequirements
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
        self.config = {
            "port": "",
            "rate": "",
            "timeout": 5
        }  # TODO

        self.__init_serial()
        self.reader = EnclosureReader(self.serial, self.bus)
        self.writer = EnclosureWriter(self.serial, self.bus)

        self._num_pixels = 12 * 2
        self._current_rgb = [(255, 255, 255) for i in range(self._num_pixels)]

        self.writer.write("eyes.reset")
        self.writer.write("mouth.reset")

        self.bus.on("system.factory.reset.ping",
                    self.handle_register_factory_reset_handler)
        self.bus.on("system.factory.reset.phal",
                    self.handle_factory_reset)
        self.bus.on("mycroft.not.paired", self.handle_not_paired)
        self.bus.on("mycroft.paired", self.handle_paired)
        self.bus.on("mycroft.pairing.code", self.handle_pairing_code)
        self.bus.emit(Message("system.factory.reset.register",
                              {"skill_id": "ovos-phal-plugin-mk1"}))

    @classproperty
    def network_requirements(self):
        """ developers should override this if they do not require connectivity
         some examples:
         IOT plugin that controls devices via LAN could return:
            scans_on_init = True
            NetworkRequirements(internet_before_load=False,
                                 network_before_load=scans_on_init,
                                 requires_internet=False,
                                 requires_network=True,
                                 no_internet_fallback=True,
                                 no_network_fallback=False)
         online search plugin with a local cache:
            has_cache = False
            NetworkRequirements(internet_before_load=not has_cache,
                                 network_before_load=not has_cache,
                                 requires_internet=True,
                                 requires_network=True,
                                 no_internet_fallback=True,
                                 no_network_fallback=True)
         a fully offline plugin:
            NetworkRequirements(internet_before_load=False,
                                 network_before_load=False,
                                 requires_internet=False,
                                 requires_network=False,
                                 no_internet_fallback=True,
                                 no_network_fallback=True)
        """
        return NetworkRequirements(internet_before_load=False,
                                   network_before_load=False,
                                   requires_internet=False,
                                   requires_network=False,
                                   no_internet_fallback=True,
                                   no_network_fallback=True)

    def handle_not_paired(self, message):
        # Make sure pairing info stays on display
        # TODO - make this public in OPN
        self._deactivate_mouth_events()
        pairing_url = message.data.get("pairing_url") or "home.mycroft.ai"
        message.data["text"] = pairing_url + "      "
        self.on_text(message)

    def handle_pairing_code(self, message):
        # Make sure pairing code stays on display
        # TODO - make this public in OPN
        self._deactivate_mouth_events()
        code = message.data["code"]
        message.data["text"] = code
        self.on_text(message)

    def handle_paired(self, message):
        # reenable mouth events
        # TODO - make this public in OPN
        self._activate_mouth_events()  # clears the display

    def __init_serial(self):
        try:
            self.port = self.config.get("port")
            self.rate = self.config.get("rate")
            self.timeout = self.config.get("timeout")
            self.serial = serial.serial_for_url(
                url=self.port, baudrate=self.rate, timeout=self.timeout)
            LOG.info("Connected to: %s rate: %s timeout: %s" %
                     (self.port, self.rate, self.timeout))
        except Exception:
            LOG.error("Impossible to connect to serial port: " +
                      str(self.port))
            raise

    def __reset(self, message=None):
        self.writer.write("eyes.reset")
        self.writer.write("mouth.reset")

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
    def on_awake(self, message=None):
        ''' on wakeup animation '''
        self.writer.write("eyes.reset")
        sleep(1)
        self.writer.write("eyes.blink=b")
        sleep(1)
        # brighten the rest of the way
        self.writer.write("eyes.level=" + str(self.old_brightness))

    def on_sleep(self, message=None):
        ''' on naptime animation '''
        # Dim and look downward to 'go to sleep'
        # TODO: Get current brightness from somewhere
        self.old_brightness = 30
        for i in range(0, (self.old_brightness - 10) // 2):
            level = self.old_brightness - i * 2
            self.writer.write("eyes.level=" + str(level))
            time.sleep(0.15)
        self.writer.write("eyes.look=d")

    def on_reset(self, message=None):
        """The enclosure should restore itself to a started state.
        Typically this would be represented by the eyes being 'open'
        and the mouth reset to its default (smile or blank).
        """
        self.writer.write("eyes.reset")
        self.writer.write("mouth.reset")

    # System Events
    def on_no_internet(self, message=None):
        pass  # TODO no internet icon

    def on_system_reset(self, message=None):
        """The enclosure hardware should reset any CPUs, etc."""
        self.writer.write("system.reset")

    def on_system_mute(self, message=None):
        """Mute (turn off) the system speaker."""
        self.writer.write("system.mute")

    def on_system_unmute(self, message=None):
        """Unmute (turn on) the system speaker."""
        self.writer.write("system.unmute")

    def on_system_blink(self, message=None):
        """The 'eyes' should blink the given number of times.
        Args:
            times (int): number of times to blink
        """
        times = 1
        if message and message.data:
            times = message.data.get("times", times)
        self.writer.write("system.blink=" + str(times))

    # Eyes messages
    def on_eyes_on(self, message=None):
        """Illuminate or show the eyes."""
        self.writer.write("eyes.on")

    def on_eyes_off(self, message=None):
        """Turn off or hide the eyes."""
        self.writer.write("eyes.off")

    def on_eyes_fill(self, message=None):
        amount = 0
        if message and message.data:
            percent = int(message.data.get("percentage", 0))
            amount = int(round(23.0 * percent / 100.0))
        self.writer.write("eyes.fill=" + str(amount))

    def on_eyes_blink(self, message=None):
        """Make the eyes blink
        Args:
            side (str): 'r', 'l', or 'b' for 'right', 'left' or 'both'
        """
        side = "b"
        if message and message.data:
            side = message.data.get("side", side)
        self.writer.write("eyes.blink=" + side)

    def on_eyes_narrow(self, message=None):
        """Make the eyes look narrow, like a squint"""
        self.writer.write("eyes.narrow")

    def on_eyes_look(self, message=None):
        """Make the eyes look to the given side
        Args:
            side (str): 'r' for right
                        'l' for left
                        'u' for up
                        'd' for down
                        'c' for crossed
        """
        if message and message.data:
            side = message.data.get("side", "")
            self.writer.write("eyes.look=" + side)

    def on_eyes_color(self, message=None):
        """Change the eye color to the given RGB color
        Args:
            r (int): 0-255, red value
            g (int): 0-255, green value
            b (int): 0-255, blue value
        """
        r, g, b = 255, 255, 255
        if message and message.data:
            r = int(message.data.get("r", r))
            g = int(message.data.get("g", g))
            b = int(message.data.get("b", b))
        color = (r * 65536) + (g * 256) + b
        self._current_rgb = [(r, g, b) for i in range(self._num_pixels)]
        self.writer.write("eyes.color=" + str(color))

    def on_eyes_brightness(self, message=None):
        """Set the brightness of the eyes in the display.
        Args:
            level (int): 1-30, bigger numbers being brighter
        """
        level = 30
        if message and message.data:
            level = message.data.get("level", level)
        self.writer.write("eyes.level=" + str(level))

    def on_eyes_reset(self, message=None):
        """Restore the eyes to their default (ready) state."""
        self.writer.write("eyes.reset")

    def on_eyes_timed_spin(self, message=None):
        """Make the eyes 'roll' for the given time.
        Args:
            length (int): duration in milliseconds of roll, None = forever
        """
        length = 5000
        if message and message.data:
            length = message.data.get("length", length)
        self.writer.write("eyes.spin=" + str(length))

    def on_eyes_volume(self, message=None):
        """Indicate the volume using the eyes
        Args:
            volume (int): 0 to 11
        """
        volume = 4
        if message and message.data:
            volume = message.data.get("volume", volume)
        self.writer.write("eyes.volume=" + str(volume))

    def on_eyes_spin(self, message=None):
        self.writer.write("eyes.spin")

    def on_eyes_set_pixel(self, message=None):
        idx = 0
        r, g, b = 255, 255, 255
        if message and message.data:
            idx = int(message.data.get("idx", idx))
            r = int(message.data.get("r", r))
            g = int(message.data.get("g", g))
            b = int(message.data.get("b", b))
        self._current_rgb[idx] = (r, g, b)
        color = (r * 65536) + (g * 256) + b
        self.writer.write("eyes.set=" + str(idx) + "," + str(color))

    # Display (faceplate) messages
    def on_display_reset(self, message=None):
        """Restore the mouth display to normal (blank)"""
        self.writer.write("mouth.reset")

    def on_talk(self, message=None):
        """Show a generic 'talking' animation for non-synched speech"""
        self.writer.write("mouth.talk")

    def on_think(self, message=None):
        """Show a 'thinking' image or animation"""
        self.writer.write("mouth.think")

    def on_listen(self, message=None):
        """Show a 'thinking' image or animation"""
        self.writer.write("mouth.listen")

    def on_smile(self, message=None):
        """Show a 'smile' image or animation"""
        self.writer.write("mouth.smile")

    def on_viseme(self, message=None):
        """Display a viseme mouth shape for synched speech
        Args:
            code (int):  0 = shape for sounds like 'y' or 'aa'
                         1 = shape for sounds like 'aw'
                         2 = shape for sounds like 'uh' or 'r'
                         3 = shape for sounds like 'th' or 'sh'
                         4 = neutral shape for no sound
                         5 = shape for sounds like 'f' or 'v'
                         6 = shape for sounds like 'oy' or 'ao'
        """
        if message and message.data:
            code = message.data["code"]
            self.writer.write('mouth.viseme=' + code)

    def on_viseme_list(self, message=None):
        if message and message.data:
            start = message.data['start']
            visemes = message.data['visemes']
            self.showing_visemes = True
            for code, end in visemes:
                if not self.showing_visemes:
                    break
                if time.time() < start + end:
                    self.writer.write('mouth.viseme=' + code)
                    sleep(start + end - time.time())
            self.writer.write("mouth.reset")
            self.showing_visemes = False

    def on_text(self, message=None):
        """Display text (scrolling as needed)
        Args:
            text (str): text string to display
        """
        text = ""
        if message and message.data:
            text = message.data.get("text", text)
        self.writer.write("mouth.text=" + text)

    def on_display(self, message=None):
        """Display images on faceplate. Currently supports images up to 16x8,
           or half the face. You can use the 'x' parameter to cover the other
           half of the faceplate.
        Args:
            img_code (str): text string that encodes a black and white image
            x (int): x offset for image
            y (int): y offset for image
            refresh (bool): specify whether to clear the faceplate before
                            displaying the new image or not.
                            Useful if you'd like to display muliple images
                            on the faceplate at once.
        """
        code = ""
        x_offset = ""
        y_offset = ""
        clear_previous = ""
        if message and message.data:
            code = message.data.get("img_code", code)
            x_offset = int(message.data.get("xOffset", x_offset))
            y_offset = int(message.data.get("yOffset", y_offset))
            clear_previous = message.data.get("clearPrev", clear_previous)

        clear_previous = int(str(clear_previous) == "True")
        clear_previous = "cP=" + str(clear_previous) + ","
        x_offset = "x=" + str(x_offset) + ","
        y_offset = "y=" + str(y_offset) + ","

        message = "mouth.icon=" + x_offset + y_offset + clear_previous + code
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

    def on_weather_display(self, message=None):
        """Show a the temperature and a weather icon

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
        if message and message.data:
            # Convert img_code to icon
            img_code = message.data.get("img_code", None)
            icon = None
            if img_code == 0:
                # sunny
                icon = "IICEIBMDNLMDIBCEAA"
            elif img_code == 1:
                # partly cloudy
                icon = "IIEEGBGDHLHDHBGEEA"
            elif img_code == 2:
                # cloudy
                icon = "IIIBMDMDODODODMDIB"
            elif img_code == 3:
                # light rain
                icon = "IIMAOJOFPBPJPFOBMA"
            elif img_code == 4:
                # raining
                icon = "IIMIOFOBPFPDPJOFMA"
            elif img_code == 5:
                # storming
                icon = "IIAAIIMEODLBJAAAAA"
            elif img_code == 6:
                # snowing
                icon = "IIJEKCMBPHMBKCJEAA"
            elif img_code == 7:
                # wind/mist
                icon = "IIABIBIBIJIJJGJAGA"

            temp = message.data.get("temp", None)
            if icon is not None and temp is not None:
                icon = "x=2," + icon
                msg = "weather.display=" + str(temp) + "," + str(icon)
                self.writer.write(msg)
