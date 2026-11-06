# SPDX-License-Identifier: GPL-2.0-or-later
"""Display-only MY-2K layout. Preserve every protocol row/column and source key."""
from copy import deepcopy


def compact_strip_layout(layout, strips):
    if [s.get('count') for s in strips] != [19, 19, 8, 1, 8, 4, 2]:
        return layout
    result = deepcopy(layout)
    for key in result:
        # Preserve every address, but show each 19-LED strip on a single line.
        key.width = key.height = key.width2 = key.height2 = .75
        key.x2 = key.y2 = 0
        if key.row in (0, 1):
            order = key.col if key.row == 0 else 18-key.col
            key.x = (0 if key.row == 0 else 12) + order*.52
            key.y = 0
            key.width = key.width2 = .52
            key.height = key.height2 = 1.1
        elif key.row == 3:  # LED Square: three times the nominal side length.
            key.y = 1.4
            key.width = key.height = key.width2 = key.height2 = 2.25
        elif key.row == 4:  # LED Bar.
            key.y -= 2
        elif key.row == 2:  # Right Circle.
            key.x += 1.25
            key.y -= 2
        elif key.row == 5:  # Left Circle.
            key.y -= 3
    return result
