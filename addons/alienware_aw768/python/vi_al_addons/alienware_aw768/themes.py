# SPDX-License-Identifier: GPL-2.0-or-later
"""Three explicitly saved PC-side themes; not native hardware-profile switching."""
import json
from dataclasses import asdict
from .protocol import GROUPS, ZONE_GROUPS, FINE_GROUPS, MACRO_ZONE, Lighting, ProtocolError, GLOBAL_EFFECTS, EFFECTS

SCHEMES = {'groups': GROUPS+((MACRO_ZONE,'Macro'),), 'zones': ZONE_GROUPS, 'all': ((0xFFFF, 'All keys'),),'fine': FINE_GROUPS}

def encode_theme(scheme, settings):
    allowed = ({mask for mask,_ in SCHEMES[scheme]} if scheme in SCHEMES else set())
    shape_ok = set(settings)==allowed or (scheme=='groups' and set(settings)=={mask for mask,_ in GROUPS})
    if scheme not in SCHEMES or not shape_ok:
        raise ProtocolError('Incomplete lighting theme.')
    if len({v.brightness for v in settings.values()})!=1:
        raise ProtocolError('Theme brightness must be shared across all groups.')
    for mask,setting in settings.items():
        setting.validate()
        if scheme=='groups' and mask==MACRO_ZONE and setting.mode!=0:
            raise ProtocolError('Macro zone supports color only.')
        if scheme == 'fine' and setting.mode != 0:
            raise ProtocolError('12-zone themes support color only.')
        if scheme != 'all' and setting.mode not in dict(EFFECTS):
            raise ProtocolError('This effect requires All keys.')
    return json.dumps({'version':1,'scheme':scheme,
                       'settings':{str(k):asdict(v) for k,v in settings.items()}},separators=(',',':'))

def decode_theme(value):
    if not isinstance(value,str) or len(value)>16384:
        raise ProtocolError('Invalid saved lighting theme.')
    try:
        data=json.loads(value)
        if type(data['version']) is not int or data['version']!=1:
            raise ValueError('version')
        scheme=data['scheme']
        settings={int(k):Lighting(v['mode'],tuple(v['color0']),tuple(v['color1']),v['tempo'],v['brightness'])
                  for k,v in data['settings'].items()}
        encode_theme(scheme,settings)
        return scheme,settings
    except (ValueError,TypeError,KeyError,AttributeError) as error:
        raise ProtocolError('Invalid saved lighting theme.') from error
