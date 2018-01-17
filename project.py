import uuid
from copy import deepcopy

from audio.alsaseq import (
    MIDI_EVENT_NOTE_ON as NOTE_ON,
    MIDI_EVENT_NOTE_OFF as NOTE_OFF,
)

import connections

CHANNEL_TYPE_DUMMY = 0
CHANNEL_TYPE_DRUM = 1
CHANNEL_TYPE_BASSLINE = 2


times = {
    ' ': [],
    '1': [0],
    '2': [0, 0.5],
    '3': [0, 1./3, 2./3],
    '4': [0, 0.25, 0.5, 0.75],
}


def log(data):
    f = open('debug.log', 'a')
    f.write(str(data) + "\n")
    f.close()


def gen_uid():
    return str(uuid.uuid4())[:8]


def ntime(time):
    return int(time * 1000000) / 1000000.


# Dummy channel definition to inherit from
class Channel(object):
    # Channel type. Each class has to have it's own
    channel_type = CHANNEL_TYPE_DUMMY
    # Channel name
    name = ''
    midi_port = 'Undefined'

    def len(self):
        pass

    def resize(self, lenght):
        pass

    def note_on(self, time, note, velocity):
        pass

    def note_off(self, time, note):
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
        self._midi_port = connections.ports.get(self.midi_port)

    def stop(self):
        pass

    def dump(self):
        pass

    def load(self, data):
        pass


class DrumChannel(Channel):
    channel_type = CHANNEL_TYPE_DRUM

    def __init__(self, name='Unnamed', data=None,
                 midi_port='', midi_channel=0, note=0):
        self.name = name
        self.midi_port = midi_port
        self._midi_port = connections.ports.get(midi_port)
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

    def note_on(self, time, note, velocity):
        nextval = {' ': '1', '1': '2', '2': '3', '3': '4', '4': ' '}
        note_to_pos = []
        for octave in xrange(6):
            note_to_pos += [n+(12*octave) for n in [48, 50, 52, 53, 55, 57, 59]]
        if note in note_to_pos:
            time = note_to_pos.index(note)
            self.data[time] = nextval[self.data[time]]
    
    def note_off(self, time, note):
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
            "channel_type": self.channel_type,
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
        # Check the data for channel y and see if there is an event between
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
                connections.seq.note_on(self._midi_port, self.note, self.midi_channel, 127)


class MidiChannel(Channel):
    channel_type = CHANNEL_TYPE_BASSLINE

    def __init__(self, name='Unnamed', lenght=0, data=None, qmap=None, 
                 midi_port='', midi_channel=0):
        self.name = name
        self._len = lenght
        self.data = data
        self.qmap = qmap
        self.midi_port = midi_port
        self._midi_port = connections.ports.get(midi_port)
        self.midi_channel = int(midi_channel)
        self._state = {}
        if data is not None:
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
                time_on, time_off, note, velocity = item
                time_on = time_base + time_on
                time_off = (time_base + time_off) % lenght
                if time_on < lenght:
                    tmp_data.append((time_on, time_off, note, velocity))
                    notes_added = True
            i += 1
    
        self.data = tmp_data
        self.qmap = tmp_qmap
        self._len = lenght
        self.rebuild_sequence()

    def dump(self):
        return deepcopy({
            "channel_type": self.channel_type,
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
        self.midi_channel = int(data['midi_channel'])
        self.midi_port = data['midi_port']
        self.data = data['data']
        self.qmap = data['qmap']
        self.rebuild_sequence()
        self.stop()

    def note_on(self, time, note, velocity):
        time_on = ntime(time) % self.len()
        self.data.append([time_on, None, note, velocity])
        self._state[note] = time_on
        if self._midi_port is not None:
            connections.seq.note_on(self._midi_port, note, self.midi_channel, velocity)
        self.rebuild_sequence()
    
    def note_off(self, time, note):
        time_off = ntime(time) % self.len()
        time_on = self._state[note]
        item = None
        for item in self.data:
            if time_on == item[0] and note == item[2]:
                break
        if item:
            item[1] = time_off

        del self._state[note]
        if self._midi_port is not None:
            connections.seq.note_off(self._midi_port, note, self.midi_channel)
        self.rebuild_sequence()

    def quantize(self, time, value):
        self.qmap[int(time)] = int(value)
        self.rebuild_sequence()

    def clear(self, time):
        mark_deletion = []
        for item in self.data:
            time_on, time_off, note, velocity = item
            if time <= time_on < time + 1:
                mark_deletion.append(item)
                connections.seq.note_off(self._midi_port, note, self.midi_channel)

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
                note,
                velocity
            )
            for time_on, time_off, note, velocity
            in self.data
        ]
        self.qmap = self.qmap[time:] + self.qmap[:time]
        self.rebuild_sequence()

    def rebuild_sequence(self):
        self.data_seq = []
        self.beat_data = [' '] * self._len
        for time_on, time_off, note, velocity in self.data:
            itime = int(time_on)
            data_repr = '*'
            qvalue = self.qmap[itime]
            qdelta = 0
            if qvalue:
                data_repr = str(qvalue)
                qdelta = time_on - round(time_on * qvalue) / qvalue

            self.data_seq.append((time_on - qdelta, NOTE_ON, note, velocity))

            if time_off:
                self.data_seq.append((time_off - qdelta, NOTE_OFF, note, 0))

            self.beat_data[itime] = data_repr
        self.data_seq.sort()
            
    def play_range(self, prev_time, curr_time):
        if self._midi_port is None:
            return

        prev_time = prev_time % self.len()
        curr_time = curr_time % self.len()
        for time, event, note, velocity in self.data_seq:
            if prev_time <= curr_time:
                play_note = prev_time <= time < curr_time
            else:
                play_note = prev_time <= time or time < curr_time

            if play_note:
                if event == NOTE_ON:
                    connections.seq.note_on(self._midi_port, note, self.midi_channel, velocity)
                elif event == NOTE_OFF:
                    connections.seq.note_off(self._midi_port, note, self.midi_channel)
    
    def stop(self):
        if self._midi_port is None:
            return

        for time, event, note, velocity in self.data_seq:
            connections.seq.note_off(self._midi_port, note, self.midi_channel)


class Pattern(object):
    def __init__(self, name=None, channels=None, pattern_len=None, uid=None):
        self.name = name
        self.channels = channels
        self.len = pattern_len
        self.uid = gen_uid() if uid is None else uid

    def resize(self, lenght):
        for channel in self.channels:
            channel.stop()
            channel.resize(lenght)
        self.len = lenght

    def bind(self):
        for channel in self.channels:
            channel.bind()

    def play_range(self, prev_time, curr_time):
        for channel in self.channels:
            channel.play_range(prev_time, curr_time)

    def mute(self):
        for channel in self.channels:
            channel.stop()

    def dump(self):
        return deepcopy({
            'uid': self.uid,
            'name': self.name,
            'len': self.len,
            'channels': [c.dump() for c in self.channels],
        })

    def load(self, data):
        self.uid = data.get('uid', gen_uid())
        self.name = data['name']
        self.len = data['len']
        self.channels = []
        for channel in data['channels']:
            if channel['channel_type'] == CHANNEL_TYPE_DRUM:
                tmp_channel = DrumChannel(
                    channel['name'],
                    channel['data'],
                    channel.get('midi_port', 'Undefined'),
                    channel.get('midi_channel', 0),
                    channel['note'],
                )
            else:
                tmp_channel = MidiChannel(
                    channel['name'],
                    channel['len'],
                    channel['data'],
                    channel['qmap'],
                    channel.get('midi_port', 'Undefined'),
                    channel.get('midi_channel', 0),
                )
            self.channels.append(tmp_channel)


class Project(object):
    def __init__(self, name=None, patterns=None, patterns_seq=None, bpm=120):
        self.name = name or 'Untitled'
        self.patterns=patterns or []
        self.patterns_seq=patterns_seq or []
        self.bpm = bpm
        self.rebuild_sequence()

    def dump(self):
        return deepcopy({
            'name': self.name,
            'bpm': self.bpm,
            'patterns': [p.dump() for p in self.patterns],
            'patterns_seq': self.patterns_seq
        })

    def load(self, data):
        self.name = data['name']
        self.bpm = data.get('bpm', 120)
        self.patterns = []
        for pattern in data['patterns']:
            tmp_pattern = Pattern()
            tmp_pattern.load(pattern)
            self.patterns.append(tmp_pattern)
        self.patterns_seq = data['patterns_seq']
        self.rebuild_sequence()

    def rebuild_sequence(self):
        tmp_play_seq = []
        phash = {p.uid:p for p in self.patterns}
        i = 0
        for puid in self.patterns_seq:
            j = i + phash[puid].len
            tmp_play_seq.append((i, j, phash[puid]))
            i = j
        self._play_seq = tmp_play_seq

    def bind(self):
        for pattern in self.patterns:
            pattern.bind()

    def play_range(self, prev_time, curr_time):
        prev_pattern = None
        for pattern_start, pattern_end, pattern in self._play_seq:
            if pattern_start > curr_time:
                break
            if pattern_end < prev_time:
                continue

            play_start = max(pattern_start, prev_time)
            play_end = min(pattern_end, curr_time)

            if play_start >= play_end:
                continue

            if prev_pattern is None:
                prev_pattern = pattern

            if prev_pattern != pattern:
                for channel in prev_pattern.channels:
                    channel.stop()
                prev_pattern = pattern

            for channel in pattern.channels:
                channel.play_range(
                    play_start - pattern_start, 
                    play_end - pattern_start
                )

    def mute(self):
        for pattern in self.patterns:
            pattern.mute()

    def remove_pattern(self, pattern):
        self.patterns.remove(pattern)
        self.patterns_seq = [p for p in self.patterns_seq if p != pattern]
        self.rebuild_sequence()
        


def create_empty_pattern():
    channels = [
        DrumChannel('Hi Hat', [' '] * 16, "", 15, 44),
        DrumChannel('Snare', [' '] * 16, "", 15, 38),
        DrumChannel('Drum', [' '] * 16, "", 15, 37),
        MidiChannel('Bass', 16, [], [0] * 16, "", 0),
        MidiChannel('Melody', 16, [], [0] * 16, "", 1),
    ]
    return Pattern('Untitled', channels, 16)


def create_empty_project():
    patterns = [create_empty_pattern()]
    return Project('Unnamed', patterns, [])

