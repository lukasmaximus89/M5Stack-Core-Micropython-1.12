from micropython import const
from machine import Pin
from framebuf import FrameBuffer, MONO_HLSB
import utime
import ustruct

_CMD_WAKE = const(0x11)
_CMD_DISPLAY_INVERSION_OFF = const(0x20)
_CMD_DISPLAY_INVERSION_ON = const(0x21)
_CMD_DISPLAY_ON = const(0x29)
_CMD_DISPLAY_OFF = const(0x28)
_CMD_COLUMN_SET = const(0x2a)
_CMD_PAGE_SET = const(0x2b)
_CMD_RAM_WRITE = const(0x2c)
_CMD_LINE_SET = const(0x37)

def color565(r, g, b):
    return (r & 0xf8) << 8 | (g & 0xfc) << 3 | b >> 3

class ILI9341:

    def __init__(self, spi, cs = 14, dc = 27, rst = 33, bl = 32):
        self.buffer = bytearray(32)
        self.letter = FrameBuffer(bytearray(8), 8, 8, MONO_HLSB)
        self.spi = spi
        self.cs = Pin(cs, Pin.OUT)
        self.dc = Pin(dc, Pin.OUT)
        self.rst = Pin(rst, Pin.OUT)
        self.bl = Pin(bl, Pin.OUT)
        self.width = 320
        self.height = 240
        self.char_width = 16
        self.char_height = 16
        self.offset = 0
        self.background = color565(0, 0, 0)
        self._reset()
        self._setup()

    def _reset(self):
        self.cs.value(1)
        self.dc.value(0)
        self.rst.value(0)
        utime.sleep_ms(50)
        self.rst.value(1)
        utime.sleep_ms(50)

    def _setup(self):
        for command, arguments in (
                (0xef, b'\x03\x80\x02'),
                (0xcf, b'\x00\xc1\x30'),
                (0xed, b'\x64\x03\x12\x81'),
                (0xe8, b'\x85\x00\x78'),
                (0xcb, b'\x39\x2c\x00\x34\x02'),
                (0xf7, b'\x20'),
                (0xea, b'\x00\x00'),
                (0xc0, b'\x23'),  # Power Control 1, VRH[5:0]
                (0xc1, b'\x10'),  # Power Control 2, SAP[2:0], BT[3:0]
                (0xc5, b'\x3e\x28'),  # VCM Control 1
                (0xc7, b'\x86'),  # VCM Control 2
                (0x36, b'\x48'),  # Memory Access Control
                (0x3a, b'\x55'),  # Pixel Format
                (0xb1, b'\x00\x18'),  # FRMCTR1
                (0xb6, b'\x08\x82\x27'),  # Display Function Control
                (0xf2, b'\x00'),  # Gamma Function Disable
                (0x26, b'\x01'),  # Gamma Curve Selected
                (0xe0, b'\x0f\x31\x2b\x0c\x0e\x08\x4e\xf1\x37\x07\x10\x03\x0e\x09\x00'),  # Set Gamma
                (0xe1, b'\x00\x0e\x14\x03\x11\x07\x31\xc1\x48\x08\x0f\x0c\x31\x36\x0f')):
            self._write_command(command, arguments)
        self._write_command(_CMD_WAKE)
        utime.sleep_ms(120)

    def on(self):
        self._write_command(_CMD_DISPLAY_ON)
        self.bl.value(1)

    def off(self):
        self.bl.value(0)
        self._write_command(_CMD_DISPLAY_OFF)

    def set_inversion(self, inverse):
        if inverse:
            self._write_command(_CMD_DISPLAY_INVERSION_ON)
        else:
            self._write_command(_CMD_DISPLAY_INVERSION_OFF)

    def to_color(self, r, g, b):
        return color565(r, g, b)

    def set_background(self, background = color565(0, 0, 0)):
        self.fill_rectangle(0, 0, self.width - 1, self.height - 1, background)
        self.background = background

    def set_pixel(self, x, y, color = color565(255, 255, 255)):
        if x >= 0 and x < self.width and y >= 0 and y < self.height:
            self.fill_rectangle(x, y, x, y, color)

    def draw_line(self, x0, y0, x1, y1, color = color565(255, 255, 255)):
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        e = dx + dy
        while x0 != x1 or y0 != y1:
            self.set_pixel(x0, y0, color)
            e2 = e << 1
            if e2 > dy:
                e += dy
                x0 += sx
            if e2 < dx:
                e += dx
                y0 += sy

    def draw_polyline(self, x, y, points, color = color565(255, 255, 255)):
        last_point = None
        for point in points:
            if last_point is not None:
                self.draw_line(x + last_point[0], y + last_point[1], x + point[0], y + point[1], color)
            last_point = point

    def draw_string(self, x_origin, y_origin, chars, color = color565(255, 255, 255)):
        for char in chars:
            self.letter.fill(0)
            self.letter.text(char, 0, 0)
            for x in range(0, 8):
                for y in range(0, 8):
                    x0 = x_origin + (x << 1)
                    y0 = y_origin + (y << 1)
                    x1 = x0 + 2
                    y1 = y0 + 2
                    self.fill_rectangle(x0, y0, x1, y1, color if self.letter.pixel(x, y) > 0 else self.background)
            x_origin += 16

    def rotate_up(self, delta = 1):
        self.offset = (self.offset + delta) % self.height
        self._write_command(_CMD_LINE_SET, ustruct.pack('>H', self.offset))

    def scroll_up(self, delta):
        self.fill_rectangle(0, 0, self.width - 1, delta, color = self.background)
        self.rotate_up(delta)

    def fill_rectangle(self, x0, y0, x1, y1, color):
        x0, x1 = self.width - x1 - 1, self.width - x0 - 1
        if x0 < 0 and x1 < 0:
            return
        if x0 >= self.width and x1 >= self.width:
            return
        if y0 < 0 and y1 < 0:
            return
        if y0 >= self.height and y1 >= self.height:
            return
        if x0 < 0:
            x0 = 0
        if x0 >= self.width:
            x0 = self.width - 1
        if y0 < 0:
            y0 = 0
        if y0 >= self.height:
            y0 = self.height - 1
        if x1 < 0:
            x1 = 0
        if x1 >= self.width:
            x1 = self.width - 1
        if y1 < 0:
            y1 = 0
        if y1 >= self.height:
            y1 = self.height - 1
        w = x1 - x0 + 1
        h = y1 - y0 + 1
        pixel_count = min(16, w * h)
        color_msb = color >> 8
        color_lsb = color & 255
        position = 0
        for index in range(0, pixel_count):
            self.buffer[position] = color_msb
            position += 1
            self.buffer[position] = color_lsb
            position += 1
        if pixel_count == 16:
            self._fill_large_rectangle(x0, y0, x1, y1)
        else:
            self._fill_small_rectangle(x0, y0, x1, y1, position)

    def _fill_large_rectangle(self, x0, y0, x1, y1):
        y = y0
        while y <= y1:
            x = x0
            while x <= x1:
                x_right = min(x1, x + 15)
                self._fill_small_rectangle(x, y, x_right, y, (x_right - x + 1) << 1)
                x = x_right + 1
            y += 1

    def _fill_small_rectangle(self, x0, y0, x1, y1, position):
        y0 += self.offset
        y1 += self.offset
        y0 %= self.height
        y1 %= self.height
        self._write_command(_CMD_COLUMN_SET, ustruct.pack(">HH", x0, x1))
        self._write_command(_CMD_PAGE_SET, ustruct.pack(">HH", y0, y1))
        self._write_command(_CMD_RAM_WRITE, memoryview(self.buffer)[0:position])

    def _write_command(self, command, arguments = None):
        self.dc.value(0)
        self.cs.value(0)
        self.spi.write(bytearray([command]))
        self.cs.value(1)
        if arguments is not None:
            self.dc.value(1)
            self.cs.value(0)
            self.spi.write(arguments)
            self.cs.value(1)