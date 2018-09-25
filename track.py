from copy import deepcopy
from bisect import bisect_left

from connections import seq
from util import ntime

from sequencer_interface import (
    MIDI_EVENT_NOTE_ON as NOTE_ON,
    MIDI_EVENT_NOTE_OFF as NOTE_OFF,
)

TRACK_TYPE_DUMMY = 0
TRACK_TYPE_DRUM = 1
TRACK_TYPE_BASSLINE = 2

# There are at most 16 channels for MIDI, so 256 shuold be safe to indicate we
# want to pass along the original MIDI channel.
CHANNEL_ALL = 256


times = {
    ' ': [],
    '1': [0],
    '2': [0, 0.5],
    '3': [0, 1./3, 2./3],
    '4': [0, 0.25, 0.5, 0.75],
}


# Dummy track definition to inherit from
class Track(object):
    # Track type. Each class has to have it's own
    track_type = TRACK_TYPE_DUMMY
    # Track name
    name = ''
    midi_port = 'Undefined'

    def len(self):
        pass

    def resize(self, lenght):
        pass

    def note_on(self, time, channel, note, velocity):
        pass

    def note_off(self, time, channel, note):
        pass

    def quantize(self, time, value):
        pass

    def clear(self, time):
        pass

    def play_range(self, prev_time, curr_time):
        pass

    def shift(self, time):
        pass

    def transpose(self, notes):
        pass

    def bind(self):
        self._midi_port = seq.ports.get(self.midi_port)

    def stop(self):
        pass

    def dump(self):
        pass

    def load(self, data):
        pass


class DrumTrack(Track):
    track_type = TRACK_TYPE_DRUM

    def __init__(self, name='Unnamed', data=None,
                 midi_port='', midi_channel=0, note=0):
        self.name = name
        self.midi_port = midi_port
        self._midi_port = seq.ports.get(midi_port)
        self.midi_channel = int(midi_channel)
        self.note = note
        self.data = data

    def len(self):
        return len(self.data)

    def resize(self, lenght):
        old_len = self.len()
        tmp_data = [' '] * lenght
        for i in xrange(lenght):
            tmp_data[i] = self.data[i % old_len]
        self.data = tmp_data

    def note_on(self, time, channel, note, velocity):
        if self._midi_port is None:
            seq.note_on(self._midi_port, self.note, self.midi_channel, 127)
        if time < 0:
            return

        nextval = {' ': '1', '1': '2', '2': '3', '3': '4', '4': ' '}
        note_pos = []
        for octave in xrange(6):
            note_pos += [n+(12*octave) for n in [48, 50, 52, 53, 55, 57, 59]]
        if note in note_pos:
            time = note_pos.index(note)
            self.data[time] = nextval[self.data[time]]

    def note_off(self, time, channel, note):
        pass

    def quantize(self, time, value):
        if value != "0" and self.data[int(time)] != ' ':
            self.data[int(time)] = value

    def clear(self, time):
        self.data[int(time)] = ' '

    def shift(self, time):
        time = int(time)
        self.data = self.data[time:] + self.data[:time]

    def dump(self):
        return deepcopy({
            "track_type": self.track_type,
            "name": self.name,
            "midi_port": self.midi_port,
            "midi_channel": self.midi_channel,
            "note": self.note,
            "data": self.data,
        })

    def load(self, data):
        self.name = data['name']
        self.midi_port = data['midi_port']
        self.midi_channel = int(data['midi_channel'])
        self.note = data['note']
        self.data = data['data']

    def play_range(self, prev_time, curr_time):
        # Check the data for track y and see if there is an event between
        # prev_time and curr_time
        if self._midi_port is None:
            return

        pos = int(curr_time)
        note = self.data[pos % len(self.data)]
        for time in times[note]:
            time += pos
            if prev_time <= curr_time:
                play_note = prev_time <= time < curr_time
            else:
                play_note = prev_time <= time or time < curr_time

            if play_note:
                seq.note_on(self._midi_port, self.note, self.midi_channel, 127)


class MidiTrack(Track):
    track_type = TRACK_TYPE_BASSLINE

    def __init__(self, name='Unnamed', lenght=0, data=None, qmap=None,
                 midi_port='', midi_channel=0):
        self.name = name
        self._len = lenght
        self.data = data
        self.qmap = qmap
        self.midi_port = midi_port
        self._midi_port = seq.ports.get(midi_port)
        self._midi_channel = int(midi_channel)
        self._state = {}
        if data is not None:
            self.rebuild_sequence()

    @property
    def midi_channel(self):
        return self._midi_channel

    @midi_channel.setter
    def midi_channel(self, value):
        channel = int(value)
        if channel != self._midi_channel:
            self.stop()
            self._midi_channel = channel
            self.rebuild_sequence()

    def len(self):
        return self._len

    def resize(self, lenght):
        old_len = self.len()
        tmp_qmap = [0] * lenght
        for i in xrange(lenght):
            tmp_qmap[i] = self.qmap[i % old_len]

        tmp_data = []
        i, notes_added = 0, True

        while notes_added:
            notes_added = False
            time_base = old_len * i
            for item in self.data:
                time_on, time_off, channel, note, velocity = item
                time_on = time_base + time_on
                time_off = (time_base + time_off) % lenght
                if time_on < lenght:
                    tmp_data.append(
                        (time_on, time_off, channel, note, velocity)
                    )
                    notes_added = True
            i += 1

        self.data = tmp_data
        self.qmap = tmp_qmap
        self._len = lenght
        self.rebuild_sequence()

    def dump(self):
        return deepcopy({
            "track_type": self.track_type,
            'name': self.name,
            'len': self.len(),
            'midi_port': self.midi_port,
            'midi_channel': self.midi_channel,
            'data': self.data,
            'qmap': self.qmap
        })

    def load(self, data):
        self.name = data['name']
        self._len = data['len']
        self.midi_channel = int(data.get('midi_channel', 0))
        self.midi_port = data.get('midi_port', 'Undefined')
        self.data = []
        for item in data['data']:
            # Add track to old tracks
            if len(item) == 4:
                time_on, time_off, note, velocity = item
                item = (time_on, time_off, 0, note, velocity)

            self.data.append(item)

        self.qmap = data['qmap']
        self.rebuild_sequence()
        self.stop()

    def note_on(self, time, channel, note, velocity):
        if self._midi_port is not None:
            if self.midi_channel != CHANNEL_ALL:
                tmp_channel = self.midi_channel
            seq.note_on(self._midi_port, note, tmp_channel, velocity)
        if time < 0:
            return

        time_on = ntime(time) % self.len()
        self.data.append([time_on, None, channel, note, velocity])
        self._state[note] = time_on
        self.rebuild_sequence()

    def note_off(self, time, channel, note):
        if self._midi_port is not None:
            if self.midi_channel != CHANNEL_ALL:
                tmp_channel = self.midi_channel
            seq.note_off(self._midi_port, note, tmp_channel)
        if time < 0:
            return

        if note not in self._state:
            return

        time_off = ntime(time) % self.len()
        time_on = self._state[note]
        item = None
        for item in self.data:
            if time_on == item[0] and note == item[3] and channel == item[2]:
                break
        if item:
            item[1] = time_off

        del self._state[note]
        self.rebuild_sequence()

    def quantize(self, time, value):
        self.qmap[int(time)] = int(value)
        self.rebuild_sequence()

    def clear(self, time):
        mark_deletion = []
        for item in self.data:
            time_on, time_off, channel, note, velocity = item
            if time <= time_on < time + 1:
                mark_deletion.append(item)
                channel = channel & 255 or self.midi_channel
                seq.note_off(self._midi_port, note, channel)

        for del_item in mark_deletion:
            self.data.remove(del_item)
        self.rebuild_sequence()

    def shift(self, time):
        time = int(time)
        clen = self.len()
        self.data = [
            (
                (time_on-time) % clen,
                (time_off-time) % clen,
                channel,
                note,
                velocity
            )
            for time_on, time_off, channel, note, velocity
            in self.data
            if time_on is not None and time_off is not None
        ]
        self.qmap = self.qmap[time:] + self.qmap[:time]
        self.rebuild_sequence()

    def rebuild_sequence(self):
        self.data_seq = []
        self.beat_data = [' '] * self._len
        if not self.data:
            return
        for time_on, time_off, channel, note, velocity in self.data:
            itime = int(time_on)
            data_repr = '*'
            qvalue = self.qmap[itime]
            qdelta = 0
            if qvalue:
                data_repr = str(qvalue)
                qdelta = time_on - round(time_on * qvalue) / qvalue

            time_on = (time_on - qdelta) % self._len
            if self.midi_channel != CHANNEL_ALL:
                self.midi_channel
            self.data_seq.append((time_on, NOTE_ON, channel, note, velocity))

            if time_off:
                time_off = (time_off - qdelta) % self._len
                self.data_seq.append((time_off, NOTE_OFF, channel, note, 0))

            self.beat_data[itime] = data_repr
        self.data_seq.sort()

    def play_range(self, prev_time, curr_time):
        if self._midi_port is None:
            return

        prev_time = prev_time % self.len()
        curr_time = curr_time % self.len()

        prev_i = bisect_left(self.data_seq, (prev_time, None))
        curr_i = bisect_left(self.data_seq, (curr_time, None))

        if prev_i <= curr_i:
            play_seq = self.data_seq[prev_i:curr_i]
        else:
            play_seq = self.data_seq[prev_i:] + self.data_seq[:curr_i]

        for time, event, channel, note, velocity in play_seq:
            if event == NOTE_ON:
                seq.note_on(self._midi_port, note, channel, velocity)
            elif event == NOTE_OFF:
                seq.note_off(self._midi_port, note, channel)

    def stop(self):
        if self._midi_port is None:
            return

        for time, event, channel, note, velocity in self.data_seq:
            seq.note_off(self._midi_port, note, channel)
