# SPDX-License-Identifier: GPL-2.0-or-later
"""Code-drawn AW768 lighting diagram and hue/saturation picker.

The diagram is an illustrative ANSI AW768 outline, not a firmware pixel map.
Named groups use the verified masks; alternate key-zone boundaries are visual
approximations. Zone 6 is exactly Logo + Ambient, not an extra column of keys.
No external images, hardware access, animation timers or saved assets are used.
"""
from dataclasses import dataclass
import math

from PyQt5.QtCore import Qt, QSize, QPointF, QRectF, pyqtSignal
from PyQt5.QtGui import (QColor, QPainter, QPen, QBrush, QPainterPath, QLinearGradient,
                         QConicalGradient, QRadialGradient, QTransform, QFont)
from PyQt5.QtWidgets import QWidget, QSizePolicy


MACRO = 0x10000
WASD, ARROWS, NUMBERS, FUNCTION = 0x0002, 0x0010, 0xE000, 0x0700
NUMPAD, LOGO, AMBIENT, OTHER = 0x0020, 0x1000, 0x0080, 0x004D
NATIVE_GROUPS = ((WASD, 'WASD'), (ARROWS, 'Arrows'), (NUMBERS, 'Number row'),
                 (FUNCTION, 'Function row'), (NUMPAD, 'Numpad'), (LOGO, 'Logo'),
                 (AMBIENT, 'Ambient'), (OTHER, 'Other keys'))


@dataclass(frozen=True)
class _Key:
    label: str
    x: float
    y: float
    w: float = 1.
    h: float = 1.
    mask: object = OTHER

    @property
    def rect(self):
        return QRectF(45+self.x*44, 62+self.y*44, self.w*44-5, self.h*44-5)


def _keys():
    """Physical form: macro column, separated F blocks, ANSI cluster and pad."""
    keys = [_Key('X', 0, 0, mask=MACRO), _Key('Esc', 1.25, 0)]
    for block, start in enumerate((3.25, 7.75, 12.25)):
        for i in range(4):
            keys.append(_Key('F'+str(block*4+i+1), start+i, 0, mask=FUNCTION))
    keys += [_Key(label, x, 0) for label, x in (('Prt', 16.5), ('Scr', 17.5), ('Pause', 18.5))]
    for i in range(5):
        keys.append(_Key('M'+str(i+1), 0, i+1.5, mask=MACRO))
    keys.append(_Key('~', 1.25, 1.5))
    for i, label in enumerate('1234567890'):
        keys.append(_Key(label, 2.25+i, 1.5, mask=NUMBERS))
    keys += [_Key('-', 12.25, 1.5), _Key('=', 13.25, 1.5), _Key('Back', 14.25, 1.5, 2)]
    keys.append(_Key('Tab', 1.25, 2.5, 1.5))
    for i, label in enumerate('QWERTYUIOP[]'):
        keys.append(_Key(label, 2.75+i, 2.5, mask=WASD if label == 'W' else OTHER))
    keys.append(_Key('\\', 14.75, 2.5, 1.5))
    keys.append(_Key('Caps', 1.25, 3.5, 1.75))
    for i, label in enumerate("ASDFGHJKL;'"):
        keys.append(_Key(label, 3+i, 3.5, mask=WASD if label in 'ASD' else OTHER))
    keys.append(_Key('Enter', 14, 3.5, 2.25))
    keys.append(_Key('Shift', 1.25, 4.5, 2.25))
    keys += [_Key(label, 3.5+i, 4.5) for i, label in enumerate('ZXCVBNM,./')]
    keys.append(_Key('Shift', 13.5, 4.5, 2.75))
    keys += [_Key(label, x, 5.5, width) for label, x, width in (
        ('Ctrl', 1.25, 1.5), ('Win', 2.75, 1), ('Alt', 3.75, 1.5),
        ('', 5.25, 6.25), ('Alt', 11.5, 1.25), ('Fn', 12.75, 1.25),
        ('Menu', 14, 1), ('Ctrl', 15, 1.25))]
    for y, labels in ((1.5, ('Ins', 'Home', 'PgUp')), (2.5, ('Del', 'End', 'PgDn'))):
        keys += [_Key(label, 16.5+i, y) for i, label in enumerate(labels)]
    keys.append(_Key('↑', 17.5, 4.5, mask=ARROWS))
    keys += [_Key(label, 16.5+i, 5.5, mask=ARROWS) for i, label in enumerate(('←', '↓', '→'))]
    for y, labels in ((1.5, ('Num', '/', '*', '-')), (2.5, ('7', '8', '9')),
                      (3.5, ('4', '5', '6')), (4.5, ('1', '2', '3'))):
        keys += [_Key(label, 19.75+i, y, mask=NUMPAD) for i, label in enumerate(labels)]
    keys += [_Key('+', 22.75, 2.5, h=2, mask=NUMPAD),
             _Key('Enter', 22.75, 4.5, h=2, mask=NUMPAD),
             _Key('0', 19.75, 5.5, w=2, mask=NUMPAD), _Key('.', 21.75, 5.5, mask=NUMPAD)]
    return tuple(keys)


class AW768Preview(QWidget):
    selectionChanged = pyqtSignal(object)
    WIDTH, HEIGHT = 1180., 440.
    KEYS = _keys()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui_scale = 1.
        self.groups = NATIVE_GROUPS
        self.scheme = 'groups'
        self.settings = {}
        self.selected = set()
        self.hovered = None
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMouseTracking(True)
        self.setAccessibleName('AW768 keyboard lighting diagram')
        self.setToolTip('Click a lighting region. Ctrl-click adds or removes regions. This is a static color preview. Key-zone boundaries are illustrative; Logo and Ambient use their verified native masks.')

    def minimumSizeHint(self):
        return QSize(round(300*self.ui_scale), round(120*self.ui_scale))

    def sizeHint(self):
        return QSize(round(1000*self.ui_scale), round(373*self.ui_scale))

    def set_ui_scale(self, scale):
        self.ui_scale = scale
        self.updateGeometry()
        self.update()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return max(1, round(width*self.HEIGHT/self.WIDTH))

    def set_groups(self, groups, scheme='groups'):
        groups = tuple((int(mask), str(label)) for mask, label in groups)
        if (scheme not in ('groups', 'zones', 'all', 'fine') or not groups or
                len({mask for mask, _ in groups}) != len(groups) or
                any(not 0 < mask <= 0x10000 for mask, _ in groups) or
                (scheme == 'zones' and len(groups) != 6)):
            raise ValueError('Expected named AW768 groups or six native zones.')
        self.groups, self.scheme = groups, scheme
        self.selected &= {mask for mask, _ in groups}
        self.hovered = None
        self.update()

    def set_settings(self, mapping):
        self.settings = dict(mapping)
        self.update()

    def set_selected(self, masks):
        self.selected = set(masks) & {mask for mask, _ in self.groups}
        self.update()

    def _transform(self):
        scale = min(self.width()/self.WIDTH, self.height()/self.HEIGHT)
        transform = QTransform()
        transform.translate((self.width()-self.WIDTH*scale)/2,
                            (self.height()-self.HEIGHT*scale)/2)
        transform.scale(scale, scale)
        return transform

    def _key_mask(self, key):
        if key.mask is None:
            return None  # Macro LEDs and media controls are not configured here.
        if self.scheme == 'groups':
            return key.mask if key.mask in dict(self.groups) else None
        if key.mask==MACRO:return MACRO if self.scheme=='groups' and MACRO in dict(self.groups) else None
        if self.scheme == 'all':
            return 0xFFFF
        if self.scheme == 'fine':
            memberships=[2 if key.x<6.5 else 3 if key.x<11.5 else 4] if key.x<16.5 else [5] if key.x<19.75 else [6]
            if key.mask==WASD:memberships.append(7)
            if key.mask==ARROWS:memberships.append(8)
            if key.mask==NUMBERS:memberships.append(9)
            if key.mask==FUNCTION or key.label=='Esc':memberships.append(10)
            if key.mask==NUMPAD and (key.label.isdigit() or key.label=='.'):memberships.append(11)
            selected=[mask for mask in memberships if mask in self.selected]
            return (selected or memberships)[-1]
        # Firmware masks partition the key area into five column-like zones;
        # the sixth is exactly Logo + Ambient (0x1080).
        # The third main-key cluster includes the full right edge: backslash
        # and Right Ctrl. Navigation and numpad have separate native zones.
        index = (0 if key.x < 6.5 else 1 if key.x < 11.5 else
                 2 if key.x < 16.5 else 3 if key.x < 19.75 else 4)
        return self.groups[index][0]

    def _special_mask(self, named_mask):
        if self.scheme == 'groups':
            return named_mask if named_mask in dict(self.groups) else None
        if self.scheme=='all':return 0xFFFF
        if self.scheme=='fine':return 12 if named_mask==LOGO else 13
        return 0x1080 if 0x1080 in dict(self.groups) else None

    @staticmethod
    def _logo_rect():
        return QRectF(1052, 62, 33, 42)

    @staticmethod
    def _ambient_path():
        path = QPainterPath(QPointF(29, 363))
        path.lineTo(63, 402); path.lineTo(1121, 402); path.lineTo(1152, 363)
        return path

    def _badges(self):
        if self.scheme=='all':return [(0xFFFF,'All',QPointF(590,31),'')]
        if self.scheme=='fine':
            positions={2:(210,359),3:(490,359),4:(720,359),5:(840,116),6:(1120,170),7:(232,163),8:(837,359),9:(493,111),10:(493,31),11:(1120,260),12:(1068,27),13:(590,421)}
            return [(mask,str(mask-1),QPointF(*positions[mask]),'') for mask,_ in self.groups]
        if self.scheme == 'zones':
            return [(mask, str(index+1), QPointF(198+index*198, 31), 'Zone '+str(index+1))
                    for index, (mask, _) in enumerate(self.groups[:5])] + [
                    (self.groups[5][0], '6', QPointF(590, 421), 'Zone 6 · Logo + Ambient')]
        positions = {WASD: (232, 163), ARROWS: (837, 359), NUMBERS: (493, 111),
                     FUNCTION: (493, 31), NUMPAD: (1120, 245), LOGO: (1068, 27),
                     AMBIENT: (590, 421), OTHER: (590, 359), MACRO: (49,27)}
        return [(mask, str(index+1), QPointF(*positions[mask]), '')
                for index, (mask, _) in enumerate(self.groups) if mask in positions]

    def hit_test(self, point):
        point = QPointF(point)
        transform = self._transform()
        inverse, invertible = transform.inverted()
        if not invertible:
            return None
        # Badge targets stay usable as the whole diagram scales down.
        for mask, _, center, label in self._badges():
            center = transform.map(center)
            width = (24+min(155, len(label)*6.5) if label else 24)*self.ui_scale
            radius = 12*self.ui_scale
            if QRectF(center.x()-radius, center.y()-radius, width, 2*radius).contains(point):
                return mask
        scene = inverse.map(point)
        if self._logo_rect().adjusted(-4, -4, 4, 4).contains(scene):
            return self._special_mask(LOGO)
        # The lower bezel is a generous target for the ambient strip.
        if QRectF(50, 372, 1080, 36).contains(scene):
            return self._special_mask(AMBIENT)
        for key in self.KEYS:
            if key.rect.contains(scene):
                return self._key_mask(key)
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        mask = self.hit_test(event.pos())
        if mask is None:
            return
        selected = set(self.selected) if event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier) else set()
        if mask in selected:
            selected.remove(mask)
        else:
            selected.add(mask)
        if selected != self.selected:
            self.set_selected(selected)
            self.selectionChanged.emit(set(selected))

    def mouseMoveEvent(self, event):
        mask = self.hover_hit_test(event.pos())
        if mask != self.hovered:
            self.hovered = mask
            self.setCursor(Qt.PointingHandCursor if mask is not None else Qt.ArrowCursor)
            self.update()

    def hover_hit_test(self, point):
        mask = self.hit_test(point)
        if mask is not None:
            return mask
        inverse, invertible = self._transform().inverted()
        if not invertible:
            return None
        scene = inverse.map(QPointF(point))
        # Keycaps leave five scene units between neighbours. Cover half that
        # spacing on each side for hover, avoiding off/on flashes within a
        # group. Strict click hit-testing and group boundaries stay unchanged.
        for key in self.KEYS:
            if key.rect.adjusted(-2.5, -2.5, 2.5, 2.5).contains(scene):
                return self._key_mask(key)
        return None

    def leaveEvent(self, event):
        self.hovered = None
        self.unsetCursor()
        self.update()
        super().leaveEvent(event)

    def _color(self, mask, position=0.):
        setting = self.settings.get(mask)
        if setting is None:
            return QColor('#718391')
        if getattr(setting, 'mode', 0) in (4,10):
            return QColor.fromHsvF(position % 1., .85, 1.)
        if getattr(setting,'mode',0)==3:
            t=max(0.,min(1.,position))
            return QColor(*(round(a*(1-t)+b*t) for a,b in zip(setting.color0,setting.color1)))
        return QColor(*setting.color0)

    def _pen(self, mask, ordinary='#333941'):
        if mask is not None and mask in self.selected:
            return QPen(QColor('#55d5ff'), 2.8)
        if mask is not None and mask == self.hovered:
            return QPen(QColor('#a6e8ff'), 1.8)
        return QPen(QColor(ordinary), 1.)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setTransform(self._transform())
        body = QPainterPath(QPointF(25, 31))
        body.lineTo(1155, 31); body.lineTo(1160, 363); body.lineTo(1121, 404)
        body.lineTo(63, 404); body.lineTo(20, 363); body.closeSubpath()
        metal = QLinearGradient(0, 31, 0, 404)
        metal.setColorAt(0, QColor('#8d9297')); metal.setColorAt(.1, QColor('#555c63'))
        metal.setColorAt(.83, QColor('#72777c')); metal.setColorAt(1, QColor('#363d45'))
        painter.setPen(QPen(QColor('#9babb8'), 1.2)); painter.setBrush(QBrush(metal)); painter.drawPath(body)
        for rect in (QRectF(36, 54, 52, 292), QRectF(94, 54, 669, 292),
                     QRectF(767, 54, 139, 292), QRectF(910, 120, 188, 226),
                     QRectF(910, 54, 139, 51)):
            painter.setPen(QColor('#8d949d')); painter.setBrush(QColor('#11161c'))
            painter.drawRoundedRect(rect, 5, 5)
        # Mute and roller are deliberately neutral, rather than fake RGB groups.
        painter.setPen(QColor('#71808c')); painter.setBrush(QColor('#202830'))
        painter.drawRoundedRect(QRectF(916, 64, 36, 33), 4, 4)
        painter.drawRoundedRect(QRectF(959, 64, 79, 33), 4, 4)
        for x in range(965, 1036, 5):
            painter.drawLine(QPointF(x, 68), QPointF(x, 92))
        font = QFont(self.font()); font.setPixelSize(12); painter.setFont(font)
        for key in self.KEYS:
            rect = key.rect
            mask = self._key_mask(key)
            color = self._color(mask, rect.center().x()/self.WIDTH) if mask is not None else QColor('#687581')
            cap = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            cap.setColorAt(0, QColor('#292f36')); cap.setColorAt(1, color.darker(550))
            painter.setPen(self._pen(mask, '#0d1116')); painter.setBrush(QBrush(cap))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(QPen(color.darker(140), 1.5))
            painter.drawLine(rect.bottomLeft()+QPointF(4, -3), rect.bottomRight()+QPointF(-4, -3))
            text = QColor(min(255, int(color.red()*.8+51)), min(255, int(color.green()*.8+51)),
                          min(255, int(color.blue()*.8+51)))
            painter.setPen(text)
            painter.drawText(rect, Qt.AlignCenter, key.label)
        logo_mask = self._special_mask(LOGO)
        logo = self._logo_rect()
        painter.save()
        painter.translate(logo.topLeft());painter.scale(logo.width()/100,logo.height()/125)
        head=QPainterPath(QPointF(50,125))
        head.cubicTo(30,112,2,71,2,43)
        head.cubicTo(2,-15,98,-15,98,43)
        head.cubicTo(98,71,70,112,50,125)
        head.closeSubpath()
        painter.setPen(QPen(QColor('#55d5ff') if logo_mask in self.selected else QColor('#333941'),3))
        painter.setBrush(self._color(logo_mask));painter.drawPath(head)
        painter.setPen(Qt.NoPen);painter.setBrush(QColor('#182029'))
        # Slanted almond eyes follow the tapered head, rather than upright ovals.
        for mirror in (False,True):
            painter.save()
            if mirror:painter.translate(100,0);painter.scale(-1,1)
            eye=QPainterPath(QPointF(12,46))
            eye.cubicTo(34,47,47,62,44,84)
            eye.cubicTo(24,82,15,67,12,46)
            painter.drawPath(eye);painter.restore()
        painter.restore()
        ambient_mask = self._special_mask(AMBIENT)
        ambient_color = self._color(ambient_mask)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(ambient_color.darker(270), 13, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(self._ambient_path())
        painter.setPen(QPen(QColor('#55d5ff') if ambient_mask in self.selected else ambient_color, 3,
                            Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(self._ambient_path())
        brand = QFont(self.font()); brand.setPixelSize(11); brand.setLetterSpacing(QFont.AbsoluteSpacing, 5)
        painter.setFont(brand); painter.setPen(QColor('#353e48'))
        painter.drawText(QRectF(875, 361, 251, 20), Qt.AlignCenter, 'ALIENWARE')
        transform = self._transform()
        painter.resetTransform()
        badge_font = QFont(self.font()); badge_font.setPixelSize(round(11*self.ui_scale)); badge_font.setBold(True)
        painter.setFont(badge_font)
        for mask, number, scene, label in self._badges():
            center = transform.map(scene)
            painter.setPen(QPen(QColor('#55d5ff') if mask in self.selected else QColor('#99a9b6'), 1.2*self.ui_scale))
            painter.setBrush(QColor('#167293') if mask in self.selected else QColor('#293440'))
            radius=10*self.ui_scale
            painter.drawEllipse(center, radius, radius)
            painter.setPen(QColor('#ecf7ff'))
            painter.drawText(QRectF(center.x()-radius, center.y()-radius, 2*radius, 2*radius), Qt.AlignCenter, number)
            if label:
                painter.drawText(QRectF(center.x()+14*self.ui_scale, center.y()-9*self.ui_scale, 155*self.ui_scale, 18*self.ui_scale), Qt.AlignLeft | Qt.AlignVCenter, label)


class HueWheel(QWidget):
    """Hue/saturation selection at full value; exact RGB remains a separate control."""
    colorChanged = pyqtSignal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui_scale = 1.
        self._color = QColor('#ffffff')
        self._hue = 0.
        self._dragging = False
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setAccessibleName('Hue and saturation color wheel')
        self.setToolTip('Choose hue and saturation. Exact RGB controls can set darker colors.')

    def minimumSizeHint(self):
        return QSize(round(110*self.ui_scale), round(110*self.ui_scale))

    def sizeHint(self):
        return QSize(round(210*self.ui_scale), round(210*self.ui_scale))

    def set_ui_scale(self, scale):
        self.ui_scale = scale
        self.updateGeometry()
        self.update()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return max(1, width)

    def setColor(self, color):
        color = QColor(color)
        if not color.isValid():
            raise ValueError('Expected a valid wheel color.')
        color = color.toRgb()
        color.setAlpha(255)
        self._color = color
        if color.hsvHueF() >= 0:
            self._hue = color.hsvHueF()
        self.update()

    def color(self):
        return QColor(self._color)

    def _geometry(self):
        return QPointF(self.width()/2, self.height()/2), max(1., min(self.width(), self.height())/2-13*self.ui_scale)

    def _choose(self, point):
        center, radius = self._geometry()
        dx, dy = point.x()-center.x(), point.y()-center.y()
        saturation = min(1., math.hypot(dx, dy)/radius)
        hue = (-math.atan2(dy, dx)/(2*math.pi)) % 1.
        color = QColor.fromHsvF(hue, saturation, 1.).toRgb()
        if color != self._color:
            self._color, self._hue = color, hue
            self.update()
            self.colorChanged.emit(QColor(color))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            center, radius = self._geometry()
            if math.hypot(event.x()-center.x(), event.y()-center.y()) <= radius:
                self._dragging = True
                self._choose(event.pos())
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._choose(event.pos())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center, radius = self._geometry()
        colors = QConicalGradient(center, 0)
        for index in range(7):
            colors.setColorAt(index/6, QColor.fromHsvF((index/6) % 1., 1., 1.))
        painter.setPen(Qt.NoPen); painter.setBrush(QBrush(colors))
        painter.drawEllipse(center, radius, radius)
        saturation = QRadialGradient(center, radius)
        saturation.setColorAt(0, QColor(255, 255, 255, 255))
        saturation.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(saturation)); painter.drawEllipse(center, radius, radius)
        painter.setPen(QPen(QColor('#737f8c'), 1.5*self.ui_scale)); painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, radius, radius)
        angle = self._hue*2*math.pi
        distance = self._color.hsvSaturationF()*radius
        marker = center+QPointF(math.cos(angle)*distance, -math.sin(angle)*distance)
        radius=6*self.ui_scale
        painter.setPen(QPen(QColor('#111820'), 4*self.ui_scale)); painter.drawEllipse(marker, radius, radius)
        painter.setPen(QPen(QColor('#ffffff'), 2*self.ui_scale)); painter.drawEllipse(marker, radius, radius)
