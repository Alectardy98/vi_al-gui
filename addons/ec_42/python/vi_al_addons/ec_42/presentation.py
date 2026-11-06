# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure display-state helpers; these never change calibration or settings."""
GRAY = '#666b73'
RED = '#c64f52'
GREEN = '#45ae70'
BLUE = '#4b95db'
ABSENT = '#353b43'


def held(sample, capturing=False):
    if not sample.get('sampled'):
        return False
    if sample.get('active') or sample.get('debounced'):
        return True
    if sample.get('enabled'):
        # A calibrated key's ADC noise is not a logical press. During manual
        # capture QMK is suppressed, so compare against its measured threshold.
        press = sample.get('press', 1023)
        return bool(capturing and sample.get('baseline', 1023) < press <= 1023
                    and sample.get('raw', 0) > press)
    # Keep clear-motion feedback for uncalibrated/disabled keys. This remains
    # a visual indication only; it cannot activate or calibrate a firmware key.
    return sample.get('raw', 0) - sample.get('baseline', 1023) >= 100


def calibration_color(sample, capturing=False):
    if not sample.get('sampled'):
        return ABSENT
    if held(sample, capturing=capturing):
        return GREEN
    if sample.get('capture') in (2, 3):
        return RED
    if sample.get('capture') == 1:
        return BLUE
    return GRAY


def follow_pressed(samples, previous, selected):
    """Newest observed press wins; otherwise retain the currently held/last key."""
    down = {i for i, s in enumerate(samples) if held(s)}
    newly_down = down - previous
    candidates = newly_down or (down if selected not in down else set())
    if candidates:
        selected = max(candidates, key=lambda i: (samples[i].get('raw', 0)-samples[i].get('baseline', 0), -i))
    return selected, down


def actuation_references(sample, status):
    """Global base thresholds and the selected key's fixed hysteresis range.

    These are calibrated ADC values, not RT's moving extrema/boundaries. A missing
    or uncalibrated record does not provide a reliable effective actuation band.
    """
    from vi_al_addons.ec_42.protocol import affine, percent_q, u16
    if (not sample.get('sampled') or not sample.get('enabled') or not status or
            len(status) != 20 or not 0 <= sample.get('baseline', -1) < sample.get('bottom', -1) <= 1023):
        return {}
    baseline, bottom = sample['baseline'], sample['bottom']
    press_q, release_q = u16(status, 6), u16(status, 8)
    if not 0 < release_q < press_q < 1023 or status[13] > 99:
        return {}
    effective_q = percent_q(status[13]) if status[13] else press_q
    effective_release_q = effective_q-(press_q-release_q)
    if effective_release_q <= 0:
        return {}
    return dict(base_actuation=affine(press_q, baseline, bottom),
                base_release=min(affine(release_q, baseline, bottom), bottom-6),
                effective_actuation=affine(effective_q, baseline, bottom),
                effective_release=min(affine(effective_release_q, baseline, bottom), bottom-6))


class LastPressPrediction:
    """Fixed RT estimates from the last observed completed press, per key.

    Live firmware press/release boundaries are intentionally not inputs. USB
    snapshots can miss true extrema and complete press/release cycles.
    """
    def __init__(self):
        self.keys = {}

    def clear(self):
        self.keys.clear()

    def observe(self, index, sample, references, status):
        if not references or not status or not status[10] or not sample.get('enabled'):
            self.keys.pop(index, None)
            return {}
        now = sample.get('seconds', 0)
        state = self.keys.setdefault(index, dict(pressed=False, peak=0, last=None, seconds=now))
        if now < state['seconds']:
            state.update(pressed=False,peak=0,last=None)
        elif now-state['seconds'] > .5:
            state['pressed'] = False  # Do not join a press across an unobserved gap.
        state['seconds'] = now
        pressed = bool(sample.get('active'))
        raw = sample['raw']
        if pressed:
            state['peak'] = max(state['peak'], raw) if state['pressed'] else raw
        elif state['pressed']:
            state['last'] = dict(peak=state['peak'], released_at=raw, seconds=now)
        state['pressed'] = pressed
        last = state['last']
        if last is None:
            return {}
        floor = references['effective_release']
        return dict(release=max(floor, last['peak']-status[12]),
                    reactivation=(references['effective_actuation'] if last['released_at'] <= floor
                                  else last['released_at']+status[11]),
                    observed_peak=last['peak'], observed_release=last['released_at'],
                    completed_at=last['seconds'])


def follow_updated(samples, previous, selected, updated):
    """Follow newly observed activity, without reselecting a stale cached cell."""
    down = set(previous)
    new = []
    for index in updated:
        if held(samples[index]):
            if index not in down:
                new.append(index)
            down.add(index)
        else:
            down.discard(index)
    if new:
        selected = max(new, key=lambda i: (samples[i].get('raw', 0)-samples[i].get('baseline', 0), -i))
    return selected, down
