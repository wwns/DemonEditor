import re
from functools import lru_cache

from app.commons import run_idle
from app.eparser import Service, get_satellites
from app.eparser.ecommons import MODULATION, Inversion, ROLL_OFF, Pilot, Flag, Pids, SERVICE_TYPE, POLARIZATION, FEC, \
    SYSTEM, get_key_by_value, get_value_by_name
from app.properties import Profile
from app.ui.dialogs import show_dialog, DialogType
from app.ui.main_helper import get_base_model
from . import Gtk, Gdk, UI_RESOURCES_PATH, HIDE_ICON


@lru_cache(maxsize=1)
def get_sat_positions(path):
    return ["{:.1f}".format(float(x.position) / 10) for x in get_satellites(path)]


class ServiceDetailsDialog:
    _DATA_ID = "{:04x}:{:08x}:{:04x}:{:04x}:{}:{}"

    _FAV_ID = "{:X}:{:X}:{:X}:{:X}"

    _TRANSPONDER_DATA = " {}:{}:{}:{}:{}:{}:{}:{}"

    _DIGIT_ENTRY_ELEMENTS = ("id_entry", "bitstream_entry", "pcm_entry", "video_pid_entry", "pcr_pid_entry",
                             "audio_pid_entry", "ac3_pid_entry", "ac3plus_pid_entry", "acc_pid_entry", "freq_entry",
                             "he_acc_pid_entry", "teletext_pid_entry", "transponder_id_entry", "network_id_entry",
                             "rate_entry", "pls_code_entry", "stream_id_entry", "flags_entry", "namespace_entry")

    def __init__(self, transient, options, view, services, bouquets):
        handlers = {"on_system_changed": self.on_system_changed,
                    "on_save": self.on_save,
                    "on_create_new": self.on_create_new,
                    "on_digit_entry_changed": self.on_digit_entry_changed,
                    "on_tr_edit_toggled": self.on_tr_edit_toggled}

        builder = Gtk.Builder()
        builder.add_from_file(UI_RESOURCES_PATH + "service_details_dialog.glade")
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("service_details_dialog")
        self._dialog.set_transient_for(transient)
        self._profile = Profile(options["profile"])
        self._satellites_xml_path = options.get(self._profile.value)["data_dir_path"] + "satellites.xml"
        self._services_view = view
        self._old_service = None
        self._services = services
        self._bouquets = bouquets
        self._current_model = None
        self._pattern = re.compile("\D")
        # style
        self._style_provider = Gtk.CssProvider()
        self._style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        # initialize only digit elements
        self._digit_elements = {k: builder.get_object(k) for k in self._DIGIT_ENTRY_ELEMENTS}
        for elem in self._digit_elements.values():
            elem.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                             Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self._id_entry = self._digit_elements.get("id_entry")
        self._bitstream_entry = self._digit_elements.get("bitstream_entry")
        self._pcm_entry = self._digit_elements.get("pcm_entry")
        self._video_pid_entry = self._digit_elements.get("video_pid_entry")
        self._pcr_pid_entry = self._digit_elements.get("pcr_pid_entry")
        self._audio_pid_entry = self._digit_elements.get("audio_pid_entry")
        self._ac3_pid_entry = self._digit_elements.get("ac3_pid_entry")
        self._ac3plus_pid_entry = self._digit_elements.get("ac3plus_pid_entry")
        self._acc_pid_entry = self._digit_elements.get("acc_pid_entry")
        self._he_acc_pid_entry = self._digit_elements.get("he_acc_pid_entry")
        self._teletext_pid_entry = self._digit_elements.get("teletext_pid_entry")
        self._transponder_id_entry = self._digit_elements.get("transponder_id_entry")
        self._network_id_entry = self._digit_elements.get("network_id_entry")
        self._freq_entry = self._digit_elements.get("freq_entry")
        self._rate_entry = self._digit_elements.get("rate_entry")
        self._pls_code_entry = self._digit_elements.get("pls_code_entry")
        self._stream_id_entry = self._digit_elements.get("stream_id_entry")
        self._flags_entry = self._digit_elements.get("flags_entry")
        self._namespace_entry = self._digit_elements.get("namespace_entry")
        # Service elements
        self._name_entry = builder.get_object("name_entry")
        self._package_entry = builder.get_object("package_entry")
        self._service_type_combo_box = builder.get_object("service_type_combo_box")
        self._cas_entry = builder.get_object("cas_entry")
        self._reference_entry = builder.get_object("reference_entry")
        self._keep_check_button = builder.get_object("keep_check_button")
        self._hide_check_button = builder.get_object("hide_check_button")
        self._use_pids_check_button = builder.get_object("use_pids_check_button")
        self._new_check_button = builder.get_object("new_check_button")
        # Transponder elements
        self._sat_pos_combo_box = builder.get_object("sat_pos_combo_box")
        self._pol_combo_box = builder.get_object("pol_combo_box")
        self._fec_combo_box = builder.get_object("fec_combo_box")
        self._sys_combo_box = builder.get_object("sys_combo_box")
        self._mod_combo_box = builder.get_object("mod_combo_box")
        self._invertion_combo_box = builder.get_object("invertion_combo_box")
        self._rolloff_combo_box = builder.get_object("rolloff_combo_box")
        self._pilot_combo_box = builder.get_object("pilot_combo_box")
        self._pls_mode_combo_box = builder.get_object("pls_mode_combo_box")

        self._DVB_S2_ELEMENTS = (self._mod_combo_box, self._rolloff_combo_box, self._pilot_combo_box,
                                 self._pls_mode_combo_box, self._pls_code_entry, self._stream_id_entry)
        self._TRANSPONDER_ELEMENTS = (self._sat_pos_combo_box, self._pol_combo_box, self._invertion_combo_box,
                                      self._sys_combo_box, self._freq_entry, self._transponder_id_entry,
                                      self._network_id_entry, self._namespace_entry, self._fec_combo_box,
                                      self._rate_entry)

        self.update_data_elements()

    @run_idle
    def update_data_elements(self):
        model, paths = self._services_view.get_selection().get_selected_rows()
        srv = Service(*model[paths][:])
        self._old_service = srv
        self._current_model = get_base_model(model)
        # Service
        self._name_entry.set_text(srv.service)
        self._package_entry.set_text(srv.package)
        self.select_active_text(self._service_type_combo_box, srv.service_type)
        self._id_entry.set_text(str(int(srv.ssid, 16)))
        # Transponder
        self._freq_entry.set_text(srv.freq)
        self._rate_entry.set_text(srv.rate)
        self.select_active_text(self._pol_combo_box, srv.pol)
        self.select_active_text(self._fec_combo_box, srv.fec)
        self.select_active_text(self._sys_combo_box, srv.system)
        self.set_sat_positions(srv.pos)

        if self._profile is Profile.ENIGMA_2:
            self.init_enigma2_service_data(srv)
            self.init_enigma2_transponder_data(srv)

    @run_idle
    def init_enigma2_service_data(self, srv):
        """ Service data initialisation """
        flags = srv.flags_cas
        if flags:
            flags = flags.split(",")
            self.init_enigma2_flags(flags)
            self.init_enigma2_pids(flags)
            self.init_enigma2_cas(flags)

        self._reference_entry.set_text(srv.picon_id.replace("_", ":").rstrip(".png"))

    def init_enigma2_flags(self, flags):
        f_flags = list(filter(lambda x: x.startswith("f:"), flags))
        if f_flags:
            value = int(f_flags[0][2:])
            self._keep_check_button.set_active(Flag.is_keep(value))
            self._hide_check_button.set_active(Flag.is_hide(value))
            self._use_pids_check_button.set_active(Flag.is_pids(value))
            self._new_check_button.set_active(Flag.is_new(value))

    def init_enigma2_cas(self, flags):
        cas = list(filter(lambda x: x.startswith("C:"), flags))
        if cas:
            self._cas_entry.set_text(",".join(cas))

    def init_enigma2_pids(self, flags):
        pids = list(filter(lambda x: x.startswith("c:"), flags))
        if pids:
            for pid in pids:
                if pid.startswith(Pids.VIDEO.value):
                    self._video_pid_entry.set_text(str(int(pid[4:], 16)))
                elif pid.startswith(Pids.AUDIO.value):
                    self._audio_pid_entry.set_text(str(int(pid[4:], 16)))
                elif pid.startswith(Pids.TELETEXT.value):
                    self._teletext_pid_entry.set_text(str(int(pid[4:], 16)))
                elif pid.startswith(Pids.PCR.value):
                    self._pcr_pid_entry.set_text(str(int(pid[4:], 16)))
                elif pid.startswith(Pids.AC3.value):
                    self._ac3_pid_entry.set_text(str(int(pid[4:], 16)))
                elif pid.startswith(Pids.VIDEO_TYPE.value):
                    pass
                elif pid.startswith(Pids.AUDIO_CHANNEL.value):
                    pass
                elif pid.startswith(Pids.BIT_STREAM_DELAY.value):
                    self._bitstream_entry.set_text(str(int(pid[4:], 16)))
                elif pid.startswith(Pids.PCM_DELAY.value):
                    self._pcm_entry.set_text(str(int(pid[4:], 16)))
                elif pid.startswith(Pids.SUBTITLE.value):
                    pass

    @run_idle
    def init_enigma2_transponder_data(self, srv):
        """ Transponder data initialisation """
        data = srv.data_id.split(":")
        tr_data = srv.transponder.split(":")

        if srv.system == "DVB-S2":
            self.select_active_text(self._mod_combo_box, MODULATION.get(tr_data[8]))
            self.select_active_text(self._rolloff_combo_box, ROLL_OFF.get(tr_data[9]))
            self.select_active_text(self._pilot_combo_box, Pilot(tr_data[10]).name)

        self._namespace_entry.set_text(str(int(data[1], 16)))
        self._transponder_id_entry.set_text(str(int(data[2], 16)))
        self._network_id_entry.set_text(str(int(data[3], 16)))
        self.select_active_text(self._invertion_combo_box, Inversion(tr_data[5]).name)
        self._flags_entry.set_text(tr_data[6])

    def select_active_text(self, box: Gtk.ComboBox, text):
        model = box.get_model()
        for index, row in enumerate(model):
            if row[0] == text:
                box.set_active(index)
                break

    @run_idle
    def set_sat_positions(self, sat_pos):
        model = self._sat_pos_combo_box.get_model()
        positions = get_sat_positions(self._satellites_xml_path)
        for pos in positions:
            model.append((pos,))
        self.select_active_text(self._sat_pos_combo_box, sat_pos)

    def on_system_changed(self, box):
        for elem in self._DVB_S2_ELEMENTS:
            elem.set_sensitive(box.get_active())
        self._pls_code_entry.set_name("GtkEntry")
        self._pls_code_entry.set_text("")
        self._stream_id_entry.set_name("GtkEntry")
        self._stream_id_entry.set_text("")

    def show(self):
        response = self._dialog.run()
        if response == Gtk.ResponseType.OK:
            pass
        self._dialog.destroy()

        return response

    def on_save(self, item):
        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return
        fav_id, data_id = self.get_srv_data()
        service = Service(flags_cas=self.get_flags(),
                          transponder_type="s",
                          coded=self._old_service.coded,
                          service=self._name_entry.get_text(),
                          locked=self._old_service.locked,
                          hide=HIDE_ICON if self._hide_check_button.get_active() else None,
                          package=self._package_entry.get_text(),
                          service_type=self._service_type_combo_box.get_active_id(),
                          picon=self._old_service.picon,
                          picon_id=self._old_service.picon_id,
                          ssid="{:x}".format(int(self._id_entry.get_text())),
                          freq=self._freq_entry.get_text(),
                          rate=self._rate_entry.get_text(),
                          pol=self._pol_combo_box.get_active_id(),
                          fec=self._fec_combo_box.get_active_id(),
                          system=self._sys_combo_box.get_active_id(),
                          pos=self._sat_pos_combo_box.get_active_id(),
                          data_id=data_id,
                          fav_id=fav_id,
                          transponder=self._old_service.transponder)

        old_fav_id = self._old_service.fav_id
        if old_fav_id != fav_id:
            self._services.pop(old_fav_id, None)
            for bq in self._bouquets.values():
                indexes = []
                for i, f_id in enumerate(bq):
                    if old_fav_id == f_id:
                        indexes.append(i)
                for i in indexes:
                    bq[i] = fav_id

        self._services[fav_id] = service
        self.update_data_in_model(service)

    def update_data_in_model(self, srv: Service):
        fav_id = self._old_service.fav_id
        for row in get_base_model(self._current_model):
            if row[18] == fav_id:
                self._current_model.set(self._current_model.get_iter(row.path), {i: v for i, v in enumerate(srv)})
                break

    def on_create_new(self, item):
        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        show_dialog(DialogType.ERROR, transient=self._dialog, text="Not implemented yet!")

    def get_flags(self):
        if self._profile is Profile.ENIGMA_2:
            return self.get_enigma2_flags()
        elif self._profile is Profile.NEUTRINO_MP:
            return self._old_service.flags_cas

    def get_enigma2_flags(self):
        flags = []
        # cas
        cas = self._cas_entry.get_text()
        if cas:
            flags.append(cas)
        # pids
        video_pid = self._video_pid_entry.get_text()
        if video_pid:
            flags.append("{}{:04x}".format(Pids.VIDEO.value, int(video_pid)))
        audio_pid = self._audio_pid_entry.get_text()
        if audio_pid:
            flags.append("{}{:04x}".format(Pids.AUDIO.value, int(audio_pid)))
        teletext_pid = self._teletext_pid_entry.get_text()
        if teletext_pid:
            flags.append("{}{:04x}".format(Pids.TELETEXT.value, int(teletext_pid)))
        pcr_pid = self._pcr_pid_entry.get_text()
        if pcr_pid:
            flags.append("{}{:04x}".format(Pids.PCR.value, int(pcr_pid)))
        ac3_pid = self._ac3_pid_entry.get_text()
        if ac3_pid:
            flags.append("{}{:04x}".format(Pids.AC3.value, int(ac3_pid)))
        bitstream_pid = self._bitstream_entry.get_text()
        if bitstream_pid:
            flags.append("{}{:04x}".format(Pids.BIT_STREAM_DELAY.value, int(bitstream_pid)))
        pcm_pid = self._pcm_entry.get_text()
        if pcm_pid:
            flags.append("{}{:04x}".format(Pids.PCM_DELAY.value, int(pcm_pid)))
        # flags
        f_flags = Flag.KEEP.value if self._keep_check_button.get_active() else 0
        f_flags = f_flags + Flag.HIDE.value if self._hide_check_button.get_active() else f_flags
        f_flags = f_flags + Flag.PIDS.value if self._use_pids_check_button.get_active() else f_flags
        f_flags = f_flags + Flag.NEW.value if self._new_check_button.get_active() else f_flags
        if f_flags:
            flags.append("f:{:02d}".format(f_flags))

        return ",".join(flags)

    def get_srv_data(self):
        ssid = int(self._id_entry.get_text())
        namespace = int(self._namespace_entry.get_text())
        transponder_id = int(self._transponder_id_entry.get_text())
        network_id = int(self._network_id_entry.get_text())
        service_type = self.get_value_from_combobox_id(self._service_type_combo_box, SERVICE_TYPE)

        if self._profile is Profile.ENIGMA_2:
            data_id = self._DATA_ID.format(ssid, namespace, transponder_id, network_id, service_type, 0)
            fav_id = self._FAV_ID.format(ssid, transponder_id, network_id, namespace)
            return fav_id, data_id
        elif self._profile is Profile.NEUTRINO_MP:
            return self._old_service.fav_id, self._old_service.data_id

    def get_fav_id(self):
        if self._profile is Profile.ENIGMA_2:
            return self._old_service.fav_id
        elif self._profile is Profile.NEUTRINO_MP:
            return self._old_service.fav_id

    def get_transponder_data(self):
        sys = self._sys_combo_box.get_active_id()
        freq = self._freq_entry.get_text()
        rate = self._rate_entry.get_text()
        pol = self.get_value_from_combobox_id(self._pol_combo_box, POLARIZATION)
        fec = self.get_value_from_combobox_id(self._fec_combo_box, FEC)
        sat_pos = self._sat_pos_combo_box.get_active_id().replace(".", "")
        inv = get_value_by_name(Inversion, self._invertion_combo_box.get_active_id())
        srv_sys = get_key_by_value(SYSTEM, sys)

        if self._profile is Profile.ENIGMA_2:
            dvb_s_tr = self._TRANSPONDER_DATA.format("s", freq, rate, pol, fec, sat_pos, inv, srv_sys)
            if sys == "DVB-S":
                return dvb_s_tr
            if sys == "DVB-S2":
                flag = self._flags_entry.get_text()
                mod = self.get_value_from_combobox_id(self._mod_combo_box, MODULATION)
                roll_off = self.get_value_from_combobox_id(self._rolloff_combo_box, ROLL_OFF)
                pilot = get_value_by_name(Pilot, self._pilot_combo_box.get_active_id())
                return "{}:{}:{}:{}:{}:-1:1:0".format(dvb_s_tr, flag, mod, roll_off, pilot)
        elif self._profile is Profile.NEUTRINO_MP:
            return self._old_service.transponder

    def on_digit_entry_changed(self, entry):
        entry.set_name("digit-entry" if self._pattern.search(entry.get_text()) else "GtkEntry")

    def get_value_from_combobox_id(self, box: Gtk.ComboBox, dc: dict):
        cb_id = box.get_active_id()
        return get_key_by_value(dc, cb_id)

    @run_idle
    def on_tr_edit_toggled(self, switch: Gtk.Switch, active):
        if active:
            response = TransponderServicesDialog(self._dialog, self._services_view,
                                                 self._old_service.transponder).show()
            if response == Gtk.ResponseType.CANCEL or response == -4:
                switch.set_active(False)
                return

        for elem in self._TRANSPONDER_ELEMENTS:
            elem.set_sensitive(active)


class TransponderServicesDialog:
    def __init__(self, transient, view, transponder):
        builder = Gtk.Builder()
        builder.add_objects_from_file(UI_RESOURCES_PATH + "service_details_dialog.glade",
                                      ("tr_services_dialog", "transponder_services_liststore"))
        self._dialog = builder.get_object("tr_services_dialog")
        self._dialog.set_transient_for(transient)
        self._srv_model = builder.get_object("transponder_services_liststore")
        self.append_services(view, transponder)

    def append_services(self, view, transponder):
        for row in view.get_model():
            if row[-1] == transponder:
                self._srv_model.append((row[3], row[6], row[10]))

    def show(self):
        response = self._dialog.run()
        self._dialog.destroy()
        return response


if __name__ == "__main__":
    pass