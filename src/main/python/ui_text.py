# SPDX-License-Identifier: GPL-2.0-or-later
"""English presentation of labels supplied by keyboard definitions.

Never apply this to protocol values, device identifiers or user-entered content.
The original definition and list order remain untouched.
"""
import re

# Chinese-only definitions use the same vocabulary as bilingual definitions.
_DEVICE_LABELS = {
    "关闭": "Disabled", "静态": "Static", "渐变": "Gradient",
    "呼吸": "Breathing", "闪烁": "Blink", "彩虹": "Rainbow",
    "随机": "Random", "自定义": "Custom", "右上灯阵": "Upper-right grid",
    "左右渐变": "Gradient left to right", "上下渐变": "Gradient top to bottom",
    "左右扫描": "Scan left to right", "上下扫描": "Scan top to bottom",
    "左右擦除": "Wipe left to right", "上下擦除": "Wipe top to bottom",
    "左右循环": "Cycle left to right", "上下循环": "Cycle top to bottom",
    "内外循环": "Cycle inward and outward", "双重内外循环": "Dual inward/outward cycle",
    "风车循环": "Pinwheel cycle", "螺旋循环": "Spiral cycle",
    "配列": "Layout", "分裂空格": "Split spacebar", "分裂退格": "Split Backspace",
    "分裂左Shift": "Split left Shift", "阶梯Caps Lock": "Stepped Caps Lock",
    "是": "Yes", "否": "No", "开": "On", "关": "Off",
}
_ENGLISH_LABELS = {
    "Right Grid": "Upper-right grid", "Breath": "Breathing",
    "Gradient Left Right": "Gradient left to right",
    "Gradient Up Down": "Gradient top to bottom",
    "Scan Left Right": "Scan left to right", "Scan Up Down": "Scan top to bottom",
    "Wipe Left Right": "Wipe left to right", "Wipe Up Down": "Wipe top to bottom",
    "Cycle Left Right": "Cycle left to right", "Cycle Up Down": "Cycle top to bottom",
    "Cycle Out In": "Cycle inward and outward", "Cycle Out In Dual": "Dual inward/outward cycle",
    "Cycle Pinwheel": "Pinwheel cycle", "Cycle Spiral": "Spiral cycle",
    "Led square": "LED square", "Led bar": "LED bar", "Left Circle": "Left circle",
}


def device_text(text):
    """Return a display label without modifying its source or protocol meaning.

    Unknown labels are retained, rather than guessed or silently discarded.
    Slash-separated English technical terms (APC/RT, ISO/JIS) are preserved.
    """
    if text in _DEVICE_LABELS:
        return _DEVICE_LABELS[text]
    # Only strip a Chinese suffix when the definition supplies an ASCII label.
    match = re.fullmatch(r'([\x20-\x7e]+?)/([^\x00-\x7f].*)', text)
    if match:
        text = match.group(1).strip()
    return _ENGLISH_LABELS.get(text, text)
