import threading
import jack
from time import sleep

import connections
from util import set_thread_name

jack_client = jack.Client("beatkit")


class ObjectInt(object):
    value = None

    def __init__(self, value):
        self.set(value)

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


BPM = ObjectInt(120)


class PlayerThread(threading.Thread):
    def __init__(self):
        set_thread_name("beatkit player")
        super(PlayerThread, self).__init__()
        self.data = None
        self._run = threading.Event()
        self._run.set()
        self.prev_time = 0

    def run(self):
        self.prev_time = self.get_time()
        mute_notes = False
        while self._run.is_set():
            curr_time = self.get_time()

            if not self.playing() or self.data is None:
                if mute_notes:
                    self.mute()
                    mute_notes = False
                sleep(0.05)
                self.prev_time = curr_time
                continue

            mute_notes = True

            self.data.play_range(self.prev_time, curr_time)
            self.prev_time = curr_time
            sleep(0.01)

    def play(self, data):
        self.set_data(data)
        connections.connect()
        self.data.bind()
        jack_client.transport_start()

    def set_data(self, data):
        if data:
            self.mute()
        self.data = data

    def pause(self):
        jack_client.transport_stop()
        self.mute()

    def stop(self):
        self.pause()
        self.prev_time = 0
        jack_client.transport_locate(0)

    def quit(self):
        self._run.clear()
        self.mute()

    def playing(self):
        return jack_client.transport_state == jack.ROLLING

    def mute(self):
        if self.data:
            self.data.mute()

    def get_time(self):
        # Get the time on the song.
        return (
            float(jack_client.transport_frame) /
            jack_client.samplerate * (BPM.get()/60.) * 2
        )
