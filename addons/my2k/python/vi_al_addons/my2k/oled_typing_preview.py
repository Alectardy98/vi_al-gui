# SPDX-License-Identifier: GPL-2.0-or-later
"""Release 1 typing preview: fixed native 6x8 glyphs, not a selectable Qt font.

ASCII glyphs copied from QMK drivers/oled/glcdfont.c (GPL-2.0-or-later).
The Release 1 AUX text renderer uses five visible columns with a six-pixel
advance. Only the printable ASCII subset used by the protocol is included.
This module never accesses a device or writes configuration.
"""

ASCII_GLYPHS = bytes.fromhex(
    "00000000000000005f000000000700070000147f147f1400242a7f2a1200231308646200364956205000000807030000"
    "001c224100000041221c00002a1c7f1c2a0008083e080800008070300000080808080800000060600000201008040200"
    "3e5149453e0000427f4000007249494946002141494d33001814127f10002745454539003c4a49493100412111090700"
    "364949493600464949291e00000014000000004034000000000814224100141414141400004122140800020159090600"
    "3e415d594e007c1211127c007f49494936003e41414122007f4141413e007f49494941007f09090901003e4141517300"
    "7f0808087f0000417f4100002040413f01007f08142241007f40404040007f021c027f007f0408107f003e4141413e00"
    "7f09090906003e4151215e007f091929460026494949320003017f0103003f4040403f001f2040201f003f4038403f00"
    "6314081463000304780403006159494d4300007f41414100020408102000004141417f00040201020400404040404000"
    "0003070800002054547840007f2844443800384444442800384444287f0038545454180000087e09020018a4a49c7800"
    "7f080404780000447d4000002040403d00007f102844000000417f4000007c04780478007c0804047800384444443800"
    "fc182424180018242418fc007c080404080048545454240004043f4424003c4040207c001c2040201c003c4030403c00"
    "4428102844004c9090907c004464544c4400000836410000000077000000004136080000020102040200"
)


def typing_bitmap(label, history="ABC", current="D"):
    """Page-packed 72x40 sample; label is live, key history is illustrative."""
    bitmap = bytearray(360)

    def glyph(ch, x, y, scale=1):
        if not 32 <= ord(ch) <= 126:
            return  # Invalid input remains visible in the editor for validation.
        at = (ord(ch)-32)*6
        for col in range(5):
            for row in range(8):
                if ASCII_GLYPHS[at+col] & (1 << row):
                    for dx in range(scale):
                        for dy in range(scale):
                            px, py = x+col*scale+dx, y+row*scale+dy
                            if 0 <= px < 72 and 0 <= py < 40:
                                bitmap[py//8*72+px] |= 1 << (py % 8)

    for i, ch in enumerate(label[:10]):
        glyph(ch, i*6, 0)
    history = history[-7:]
    for i, ch in enumerate(history):
        glyph(ch, (7-len(history)+i)*6, 28)
    if current:
        glyph(current[0], 44, 20, 2)
    return bytes(bitmap)
