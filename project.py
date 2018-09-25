from copy import deepcopy
from util import gen_uid

from track import (
    TRACK_TYPE_DRUM,
    DrumTrack,
    MidiTrack,
)


class Pattern(object):
    def __init__(self, name=None, tracks=None, pattern_len=None, uid=None):
        self.name = name
        self.tracks = tracks
        self.len = pattern_len
        self.uid = gen_uid() if uid is None else uid

    def resize(self, lenght):
        for track in self.tracks:
            track.stop()
            track.resize(lenght)
        self.len = lenght

    def bind(self):
        for track in self.tracks:
            track.bind()

    def play_range(self, prev_time, curr_time):
        for track in self.tracks:
            track.play_range(prev_time, curr_time)

    def mute(self):
        for track in self.tracks:
            track.stop()

    def dump(self):
        return deepcopy({
            'uid': self.uid,
            'name': self.name,
            'len': self.len,
            'tracks': [c.dump() for c in self.tracks],
        })

    def load(self, data):
        self.uid = data.get('uid', gen_uid())
        self.name = data['name']
        self.len = data['len']
        self.tracks = []
        for track in data['tracks']:
            if track['track_type'] == TRACK_TYPE_DRUM:
                tmp_track = DrumTrack(
                    track['name'],
                    track['data'],
                    track.get('midi_port', 'Undefined'),
                    track.get('midi_channel', 0),
                    track['note'],
                )
            else:
                tmp_track = MidiTrack()
                tmp_track.load(track)
            self.tracks.append(tmp_track)


class Project(object):
    def __init__(self, name=None, patterns=None, patterns_seq=None, bpm=120):
        self.name = name or 'Untitled'
        self.patterns = patterns or []
        self.patterns_seq = patterns_seq or []
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
        phash = {p.uid: p for p in self.patterns}
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
                for track in prev_pattern.tracks:
                    track.stop()
                prev_pattern = pattern

            for track in pattern.tracks:
                track.play_range(
                    play_start - pattern_start,
                    play_end - pattern_start
                )

    def mute(self):
        for pattern in self.patterns:
            pattern.mute()

    def remove_pattern(self, pattern):
        self.patterns.remove(pattern)
        self.patterns_seq = [p for p in self.patterns_seq if p != pattern.uid]
        self.rebuild_sequence()


def create_empty_pattern():
    tracks = [
        DrumTrack('Hi Hat', [' '] * 16, "", 15, 44),
        DrumTrack('Snare', [' '] * 16, "", 15, 38),
        DrumTrack('Drum', [' '] * 16, "", 15, 37),
        MidiTrack('Bass', 16, [], [0] * 16, "", 0),
        MidiTrack('Melody', 16, [], [0] * 16, "", 1),
    ]
    return Pattern('Untitled', tracks, 16)


def create_empty_project():
    patterns = [create_empty_pattern()]
    return Project('Unnamed', patterns, [])
