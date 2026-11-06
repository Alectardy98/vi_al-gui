# SPDX-License-Identifier: GPL-2.0-or-later
"""MY-2K/legacy AMK reload lifecycle, kept out of the base Vial codec."""
from kle_serial import Serial as KleSerial
from .protocol import ProtocolAmk, RGB_TYPE_MATRIX, RGB_TYPE_STRIP, RGB_TYPE_GRID, RGB_TYPE_INDICATOR

class My2KKeyboard(ProtocolAmk):
    def reload_amk(self):
        #reload nkro
        self.amk_nkro = False
        supported = bool(self.definition.get('amkFeature')) or 'animation' in self.definition or self.input_performance_version == 1
        if supported:
            self.reload_nkro()

        self.amk_feature = {"datetime": False, "aux_display": False, "switch_type": False,"switch_state": False, 
                            "calibrate": False, "firmware": False, "rgb_matrix": False, "bright": False, "esp32at": False, "esp32at_test": False,
                            "use_custom_color": False}

        self.amk_rgb = []
        self.amk_rgb_led = {"protocol_v2":False, "total":0, "bright":0}
        self.amk_rgb_matrix = {}
        self.amk_rgb_strip = {}
        self.amk_rgb_grid = {}
        self.amk_rgb_indicator = {}
        self.amk_rgb_data = []
        self.amk_aux_display = {}
        self.amk_switch_states = []
        self.amk_esp32_state = {"ready": False, "connected": False, "ssid": "", "password": "", "ssid_count": 0, "ssid_list":{}} 

        if not supported:
            self.animations = {'format': [], 'file': {}, 'disk': {}, 'transfer': ''}
            return

        if "amkFeature" in self.definition:
            for feature in self.definition["amkFeature"]:
                if feature == "datetime":
                    self.amk_feature["datetime"] = True

                if feature == "aux_display":
                    self.amk_feature["aux_display"]= True
                    self.amk_aux_display["width"] = 70
                    self.amk_aux_display["height"] = 40
                    self.amk_aux_display["mode"] = 0

                if isinstance(feature, dict):
                    if "esp32at" in feature:
                        self.amk_feature["esp32at"] = feature["esp32at"].get("enabled", False)
                        self.amk_feature[""] = feature["esp32at"].get("test_mode", False)
                        #print(feature)
                        #print("ESP32-AT feature enabled: {}, test mode: {}".format(self.amk_feature["esp32at"], self.amk_feature["esp32at_test"]))
                    if "aux_display_params" in feature:
                        self.amk_aux_display["width"] = feature["aux_display_params"]["width"]
                        self.amk_aux_display["height"] = feature["aux_display_params"]["height"]
                        self.amk_aux_display["mode"] = feature["aux_display_params"]["mode"]
                    if "rgb" in feature:
                        for r in feature["rgb"]:
                            rgb_inst = {"type": r["type"]}
                            rgb_inst["index"] = r["index"]
                            rgb_inst["start"] = r["start"]
                            rgb_inst["count"] = r["count"]
                            rgb_inst["leds"] = []
                            serial = KleSerial()
                            leds = serial.deserialize(r["leds"])
                            for led in leds.keys:
                                led.row = led.col = None
                                led.encoder_idx = led.encoder_dir = None
                                row, col = 0, 0
                                if led.labels[0] and "," in led.labels[0]:
                                    row, col = led.labels[0].split(",")
                                    row, col = int(row), int(col)
                                    led.row = row
                                    led.col = col
                                    #self.rowcol[(row, col)] = True
                                    led.layout_index = -1
                                    led.layout_option = -1
                                rgb_inst["leds"].append(led)
                            if rgb_inst["type"] == "matrix":
                                self.reload_amk_rgb_matrix()
                            self.amk_rgb.append(rgb_inst)
                    if "rgb_led" in feature:
                        self.amk_rgb_led["total"] = feature["rgb_led"]["total"]
                        if self.amk_rgb_led["total"] > 254:
                            self.amk_rgb_led["protocol_v2"] = True
                            print("Use RGB Protocol V2")
                        else:
                            print("Use RGB Protocol V1")

                        self.amk_rgb_data = [0] * self.amk_rgb_led["total"]
                        if "bright" in feature["rgb_led"]:
                            self.amk_rgb_led["bright"] = feature["rgb_led"]["bright"] 
                            self.amk_feature["bright"] = True
                        
                        if "use_custom_color" in feature["rgb_led"]:
                            self.amk_feature["use_custom_color"] = True
                            #print("Enable use custom color")

                    if "rgb_matrix" in feature:
                        self.amk_feature["rgb_matrix"] = True
                        self.amk_rgb_matrix["start"] = feature["rgb_matrix"]["start"]
                        self.amk_rgb_matrix["count"] = feature["rgb_matrix"]["count"]
                        self.amk_rgb_matrix["effects"] = feature["rgb_matrix"]["effects"]
                        if "animation" in feature["rgb_matrix"]:
                            self.amk_rgb_matrix["animation_file"] = True
                        else:
                            self.amk_rgb_matrix["animation_file"] = False

                        self.reload_amk_rgb_matrix()
                        self.reload_amk_rgb_params(RGB_TYPE_MATRIX)

                    if "rgb_strip" in feature:
                        self.amk_rgb_strip["config_start"] = feature["rgb_strip"]["config_start"]
                        self.amk_rgb_strip["start"] = feature["rgb_strip"]["start"]
                        self.amk_rgb_strip["count"] = feature["rgb_strip"]["count"]
                        self.amk_rgb_strip["strips"] = feature["rgb_strip"]["strips"]
                        self.amk_rgb_strip["effects"] = feature["rgb_strip"]["effects"]
                        self.amk_rgb_strip["layout"] = []
                        serial = KleSerial()
                        leds = serial.deserialize(feature["rgb_strip"]["layout"])
                        for led in leds.keys:
                            led.row = led.col = None
                            led.encoder_idx = led.encoder_dir = None
                            row, col = 0, 0
                            if led.labels[0] and "," in led.labels[0]:
                                row, col = led.labels[0].split(",")
                                row, col = int(row), int(col)
                                led.row = row
                                led.col = col
                                led.layout_index = -1
                                led.layout_option = -1
                            self.amk_rgb_strip["layout"].append(led)
                        self.amk_rgb_strip["leds"] = {}
                        self.reload_amk_rgb_strip()
                        self.reload_amk_rgb_params(RGB_TYPE_STRIP)

                    if "rgb_grid" in feature:
                        self.amk_rgb_grid["config_start"] = feature["rgb_grid"]["config_start"]
                        self.amk_rgb_grid["start"] = feature["rgb_grid"]["start"]
                        self.amk_rgb_grid["count"] = feature["rgb_grid"]["count"]
                        self.amk_rgb_grid["grids"] = feature["rgb_grid"]["grids"]
                        self.amk_rgb_grid["effects"] = feature["rgb_grid"]["effects"]
                        self.amk_rgb_grid["layout"] = []
                        serial = KleSerial()
                        leds = serial.deserialize(feature["rgb_grid"]["layout"])
                        for led in leds.keys:
                            led.row = led.col = None
                            led.encoder_idx = led.encoder_dir = None
                            row, col = 0, 0
                            if led.labels[0] and "," in led.labels[0]:
                                row, col = led.labels[0].split(",")
                                row, col = int(row), int(col)
                                led.row = row
                                led.col = col
                                led.layout_index = -1
                                led.layout_option = -1
                            self.amk_rgb_grid["layout"].append(led)
                        self.amk_rgb_grid["leds"] = {}
                        self.reload_amk_rgb_grid()
                        self.reload_amk_rgb_params(RGB_TYPE_GRID)

                    if "rgb_indicator" in feature:
                        if "layout" in feature["rgb_indicator"]:
                            if "on_off" in feature["rgb_indicator"]:
                                self.amk_rgb_indicator["on_off"] = feature["rgb_indicator"]["on_off"]
                            else:
                                self.amk_rgb_indicator["on_off"] = False

                            self.amk_rgb_indicator["layout"] = []
                            serial = KleSerial()
                            leds = serial.deserialize(feature["rgb_indicator"]["layout"])
                            for led in leds.keys:
                                led.row = led.col = None
                                led.encoder_idx = led.encoder_dir = None
                                row, col = 0, 0
                                if led.labels[0] and "," in led.labels[0]:
                                    row, col = led.labels[0].split(",")
                                    row, col = int(row), int(col)
                                    led.row = row
                                    led.col = col
                                    led.layout_index = -1
                                    led.layout_option = -1
                                self.amk_rgb_indicator["layout"].append(led)
                            self.amk_rgb_indicator["indicators"] = feature["rgb_indicator"]["leds"]
                            self.amk_rgb_indicator["leds"] = {}
                            self.reload_amk_rgb_indicators()

                    if "firmware" in feature:
                        self.amk_feature["firmware"]= True

        #reload apc/rt/dks/sensitivity
        if self.keyboard_type.startswith("ms") or self.keyboard_type == "ec":
            self.amk_pole = False
            self.amk_profile = 0
            self.amk_dks_disable = False
            self.keyboard_profile = 0
            self.amk_apcrt_scale = 10
            self.amk_apcrt_version = 1
            self.reload_ms_config()

            self.amk_snaptap = False
            if "amkFeature" in self.definition:
                for feature in self.definition["amkFeature"]:
                    if isinstance(feature, dict):
                        if "apcrtScale" in feature:
                            self.amk_apcrt_scale = feature.get("apcrtScale")
                            self.amk_apcrt_version = 2
                    else:
                        if feature == "snaptap":
                            self.amk_snaptap = True
                        elif feature == "switchType":
                            self.amk_feature["switch_type"] = True
                        elif feature == "switchState":
                            self.amk_feature["switch_state"] = True
                        elif feature == "calibrate":
                            self.amk_feature["calibrate"] = True
                        else:
                            print("unknown feature: {}".format(feature))

            self.amk_apc = [dict(), dict(), dict(), dict()]
            self.amk_rt = [dict(), dict(), dict(), dict()]
            self.amk_profile_count = 4 if self.keyboard_type == "ms_v2" else 1
            for i in range(self.amk_profile_count):
                self.reload_apc(i)
                self.reload_rt(i)

            self.amk_snaptap_count = 0
            self.amk_snaptap_index = 0
            self.amk_snaptap_keys = []
            if self.amk_snaptap:
                self.reload_snaptap()

            self.amk_dks = dict()
            self.reload_dks()

            self.amk_rt_sens = 80
            self.reload_rt_sensitivity()

            self.amk_top_sens = 100
            self.reload_top_sensitivity()

            self.amk_btm_sens = 150
            self.reload_bottom_sensitivity()

            self.amk_apc_sens = 80
            self.reload_apc_sensitivity()

            self.amk_noise_sens = 50
            self.reload_noise_sensitivity()

            if self.amk_feature["switch_type"]:
                self.reload_switch_type()

        # A versioned MY-2K input policy is independent of the legacy HS menu.
        if self.input_performance_version == 1:
            self.reload_input_performance()
            if self.keyboard_type == "mx":
                self.amk_down_debounce = 0
                self.amk_up_debounce = 5
                self.reload_debounce()
        #reload poll rate and debounce setting
        elif self.keyboard_speed == "hs":
            self.amk_poll_rate = 0
            self.reload_poll_rate()
            if self.keyboard_type == "mx":
                self.amk_down_debounce = 0
                self.amk_up_debounce = 5
                self.reload_debounce()

        if self.keyboard_type == "mx_state":
            self.amk_down_debounce = 0
            self.amk_up_debounce = 5
            self.reload_debounce()

        #if "amk_rgb_matrix" in self.definition:
        #    self.amk_rgb_matrix["start"] = self.definition["amk_rgb_matrix"]["start"]
        #    self.amk_rgb_matrix["count"] = self.definition["amk_rgb_matrix"]["count"]
        #    self.reload_amk_rgb_matrix()

        #reload animation
        self.animations = {"format":[], "file":{}, "disk":{}, "transfer":""}
        if "animation" in self.definition:
            for anim in self.definition["animation"]["format"]:
                self.animations["format"].append({"name":anim["name"], "mode":anim["mode"], "suffix":anim["suffix"]})
            transfer = self.definition["animation"].get("transfer")
            if transfer is not None:
                self.animations["transfer"] = transfer

            self.reload_anim_file_list()
