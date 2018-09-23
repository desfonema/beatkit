import os
import time
import json
from copy import deepcopy
import traceback

import sdlcurses
import keys
import events
import project
import connections

from sequencer_interface import (
    MIDI_EVENT_NOTE_ON,
    MIDI_EVENT_NOTE_OFF,
)

from player import (
    PlayerThread,
    BPM,
)

def log(data):
    f = open('debug.log', 'a')
    f.write(str(data) + "\n")
    f.close()


EMPTY_NOTE = ' '
MIDI_MIDDLE = 60


class TrackEditor(object):
    def __init__(self, scr, track):
        self.track = track
        self.scr = scr

    def run(self):
        scr = self.scr
        scr.erase()
        track = self.track
        self.pos = 0
        fields = 4 if track.track_type == project.TRACK_TYPE_DRUM else 3
        while True:
            self.refresh()
            if self.pos == 0:
                k, v = scr.textbox(0, 15, 30, track.name, edit=True)
                if k: track.name = v
            elif self.pos == 1:
                options = connections.seq.ports.keys()
                k, v = scr.listbox(1, 15, 30, track.midi_port, options=options, edit=True)
                if k:
                    track.midi_port = v
                    track.bind()
            elif self.pos == 2:
                channel_id = track.midi_channel if track.midi_channel < project.CHANNEL_ALL else 'Original'
                options = ['Original'] + [str(p) for p in range(16)]
                k, v = scr.listbox(2, 15, 30, channel_id, options=options, edit=True)
                if k and v.isdigit():
                    track.midi_channel = int(v)
                elif k:
                    track.midi_channel = project.CHANNEL_ALL
            elif self.pos == 3:
                k, v = scr.textbox(3, 15, 30, track.note, edit=True)
                if k and v.isdigit():
                    track.note = int(v)

            if k in [keys.KEY_TAB, keys.KEY_DOWN]:
                self.pos = (self.pos + 1) % fields
            elif k in [keys.KEY_STAB, keys.KEY_UP]:
                self.pos = (self.pos - 1) % fields
            elif not k and v.event_type == events.EVENT_MIDI_NOTE:
                if v.midi_event_type == MIDI_EVENT_NOTE_ON:
                    track.note_on(-1, v.channel, v.note, 127)
                elif v.midi_event_type == MIDI_EVENT_NOTE_OFF:
                    track.note_off(-1, v.channel, v.note)
            elif k in [keys.KEY_ENTER, keys.KEY_ESC]:
                break
        scr.erase()
                
    def refresh(self):
        scr = self.scr
        track = self.track
        channel_id = track.midi_channel if track.midi_channel < project.CHANNEL_ALL else 'Original'
        items = [
            ('Name', track.name),
            ('Midi Port', track.midi_port),
            ('Midi Channel', channel_id),
        ]
        if track.track_type == project.TRACK_TYPE_DRUM:
            items.append(('Note', track.note))

        for i, data in enumerate(items):
            label, value = data
            scr.addstr(i, 0, label)
            if i == self.pos:
                continue
            scr.textbox(i, 15, 30, value)


class PatternEditor(object):
    def __init__(self, project, pattern, pad, player):
        self._current_track = 0
        self._track_offset = 0
        self._octave = 0
        self.project = project
        self.pattern = pattern
        self.pad = pad
        self.player = player
        self.rec = True
        self.delete_keys = ['A', 'S', 'D', 'F']
        self._undo_buffer = [self.pattern.dump()]
        self._prev_pos = None

    def push_undo(self):
        current_state = self.pattern.dump()
        if current_state != self._undo_buffer[-1]:
            self._undo_buffer.append(current_state)

    def pop_undo(self):
        if len(self._undo_buffer) > 1:
            disc = self._undo_buffer.pop()
        self.pattern.load(self._undo_buffer[-1])
        self._undo_buffer = deepcopy(self._undo_buffer)

    def run(self):
        delete_keys = self.delete_keys
        drum_keys = [k.lower() for k in delete_keys]
        drum_key_to_note = []
        for octave in xrange(6):
            drum_key_to_note += [n+(12*octave) for n in [48, 50, 52, 53, 55, 57, 59]]

        key_to_midi = ['a', 'w', 's', 'e', 'd', 'f', 't', 'g', 'y', 'h', 'u', 'j', 'k']
        key_to_midi_octave = 0
        key_to_midi_state = {}
        midi_state = set()

        row_keys = {keys.KEY_UP: -1, keys.KEY_DOWN: 1}
        move_track_keys = {keys.KEY_SR: -1, keys.KEY_SF: 1}
        shift_track_keys = {keys.KEY_SLEFT: 1, keys.KEY_SRIGHT: -1}
        offset_keys = {keys.KEY_LEFT: -1, keys.KEY_RIGHT: 1}
        octave_keys = {'-': -1, '+': 1}

        quantize_keys = ['1', '2', '3', '4', '0']
        
        pad = self.pad
        pad.erase()


        prev_time = None
        repaint = 0
        while True:
            try:
                ev = events.get()
            except:
                curr_time = int(self.player.get_time())
                if prev_time != curr_time:
                    prev_time = curr_time
                    self.paint(only_pos=True)

                continue

            if ev.event_type == events.EVENT_QUIT:
                events.put(ev)
                break

            if ev.event_type == events.EVENT_REFRESH:
                self.paint()
                continue

            self._current_track = min(self._current_track, len(self.pattern.tracks) - 1)
            track = self.pattern.tracks[self._current_track]

            if ev.event_type == events.EVENT_MIDI_NOTE:
                # Process input values
                ntime = self.player.get_time() if self.rec else -1
                channel_note = (ev.channel, ev.note)
                if ev.midi_event_type == MIDI_EVENT_NOTE_ON:
                    if channel_note not in midi_state:
                        track.note_on(ntime, ev.channel, ev.note, ev.velocity)
                        midi_state.add(channel_note)
                elif ev.midi_event_type == MIDI_EVENT_NOTE_OFF:
                    if channel_note in midi_state:
                        track.note_off(ntime, ev.channel, ev.note)
                        try:
                            midi_state.remove(channel_note)
                        except:
                            pass

                    if not midi_state:
                        self.push_undo()
            elif ev.event_type == events.EVENT_MIDI_CONTROLLER:
                connections.seq.set_control(track._midi_port, ev.value, ev.param, ev.channel)
            elif ev.event_type == events.EVENT_MIDI_PITCHBEND:
                connections.seq.set_pitchbend(track._midi_port, ev.value, ev.channel)

            elif ev.event_type == events.EVENT_KEY_DOWN:
                k = ev.key_code
                c = ev.char
                if c == ':':
                    command, parameters = sdlcurses.Menu(pad, commands = [
                        ('pl', ['_Pattern _Length']),
                        ('nd', ['_New', '_Drum Channel']),
                        ('nm', ['_New', '_Midi Channel']),
                        ('e', ['_Edit Channel']),
                        ('en', ['_Edit Channel _Name']),
                        ('d', ['_Duplicate Channel']),
                        ('r', ['_Remove Channel']),
                        ('bpm', ['_Beats _per _minute']),
                    ]).run()

                    if command == 'nd':
                        name = parameters or 'Drum Channel'
                        track = project.DrumTrack(name, [' '] * track.len(), "", 15, 44)
                        self.pattern.tracks.append(track)
                        self._current_track = len(self.pattern.tracks) - 1
                        TrackEditor(pad, track).run()
                    elif command == 'nm':
                        name = parameters or 'Midi Channel'
                        track = project.MidiTrack(name, track.len(), [], [0] * track.len(), "", 0)
                        self.pattern.tracks.append(track)
                        self._current_track = len(self.pattern.tracks) - 1
                        TrackEditor(pad, track).run()
                    elif command == 'd':
                        tmp_track = track.__class__()
                        tmp_track.load(track.dump())
                        self.pattern.tracks.append(tmp_track)
                        self._current_track = len(self.pattern.tracks) - 1
                    elif command == 'r':
                        self.pattern.tracks.remove(track)
                        self._current_track = min(self._current_track, len(self.pattern.tracks) - 1)
                        pad.erase()
                    elif command == 'e':
                        TrackEditor(pad, track).run()
                    elif command == 'en':
                        track.name = parameters
                    elif command == 'bpm':
                        set_bpm(parameters, self.project)
                    elif command == 'pl':
                        self.pattern.resize(int(parameters))
                    
                elif c in key_to_midi + drum_keys:
                    midi_note = None
                    if track.track_type == project.TRACK_TYPE_DRUM:
                        if c in drum_keys:
                            pos = drum_keys.index(c)
                            pos += self._track_offset * len(delete_keys)
                            midi_note = drum_key_to_note[pos]
                    else:
                        midi_note = key_to_midi.index(c) + key_to_midi_octave * 12 + 60
                    
                    if not key_to_midi_state.get(midi_note):
                        events.put(events.MidiNoteEvent(MIDI_EVENT_NOTE_ON, track.midi_channel, midi_note, 127))
                        key_to_midi_state[midi_note] = True
                elif c == " ":
                    if self.player.playing():
                        self.player.stop()
                    else:
                        self.player.play(self.pattern)
                elif k in row_keys:
                    self._current_track = (self._current_track + row_keys[k]) % len(self.pattern.tracks)
                elif k in move_track_keys:
                    i =  self._current_track
                    j =  (i + move_track_keys[k]) % len(self.pattern.tracks)
                    self.pattern.tracks[i], self.pattern.tracks[j] = self.pattern.tracks[j], self.pattern.tracks[i]
                    self._current_track = (self._current_track + move_track_keys[k]) % len(self.pattern.tracks)
                elif k in shift_track_keys:
                    track.shift(shift_track_keys[k])
                elif k in offset_keys:
                    self._track_offset = (self._track_offset + offset_keys[k]) % (self.pattern.len / len(delete_keys))
                elif c in octave_keys:
                    key_to_midi_octave += octave_keys[c]
                elif c in delete_keys:
                    pos = delete_keys.index(c) + self._track_offset * len(delete_keys)
                    track.clear(pos)
                    self.push_undo()
                elif c in quantize_keys:
                    if True or track.track_type == project.TRACK_TYPE_DRUM:
                        pos = self._track_offset * len(delete_keys)
                        for i in range(len(delete_keys)):
                            track.quantize(pos + i, c)
                        self.push_undo()
                elif c == 'R':
                    self.rec = not self.rec
                elif k == keys.KEY_BACKSPACE:
                    self.pop_undo()
                elif k == keys.KEY_ENTER:
                    TrackEditor(pad, track).run()
                elif c == 'q' or k == keys.KEY_ESC:
                    break
            elif ev.event_type == events.EVENT_KEY_UP:
                k = ev.key_code
                c = chr(k & 0xff)
                if c in key_to_midi + drum_keys:
                    midi_note = None
                    if track.track_type == project.TRACK_TYPE_DRUM:
                        if c in drum_keys:
                            pos = drum_keys.index(c)
                            pos += self._track_offset * len(delete_keys)
                            midi_note = drum_key_to_note[pos]
                    else:
                        midi_note = key_to_midi.index(c) + key_to_midi_octave * 12 + 60

                    if key_to_midi_state.get(midi_note):
                        events.put(events.MidiNoteEvent(MIDI_EVENT_NOTE_OFF, track.midi_channel, midi_note, 127))
                        key_to_midi_state[midi_note] = False

            nowtime = time.time()
            if repaint < nowtime - 0.05:
                self._octave = key_to_midi_octave
                self.paint()
                repaint = nowtime

    def paint(self, only_pos=False):
        pad = self.pad
        tracks = self.pattern.tracks
        current_track = self._current_track
        curr_time = self.player.get_time()
        y = 0
        pad.addstr(y, 0, 'Pattern Name: {} | Len: {} | Octave: {} | BPM: {} | {}         '.format(
            self.pattern.name,
            self.pattern.len,
            self._octave,
            self.project.bpm,
            '(REC)' if self.rec else '(---)'
        ))
        y = 1
        if self.pattern.tracks:
            if self._prev_pos:
                pad.addstr(y, self._prev_pos, " ", keys.A_BOLD)

            pos = (21 + int(curr_time)%self.pattern.len*3)
            pad.addstr(y, pos, "*", keys.A_BOLD)
            self._prev_pos = pos

        y = 2
            
        for track in tracks:
            if only_pos: break
            i = tracks.index(track)
            offset_len = len(self.delete_keys)

            attr = keys.A_BOLD if i == current_track else 0

            pad.addstr(y+i, 0, "{: >20}".format(track.name), attr)

            data = ['-'] * self.pattern.len
            if track.track_type == project.TRACK_TYPE_DRUM:
                data = track.data
            elif track.track_type == project.TRACK_TYPE_BASSLINE:
                data = track.beat_data

            pad.addstr(y+i, 20, "[" + "][".join(data) + "]")
            
            if attr:
                start = (self._track_offset * offset_len) % self.pattern.len
                end = start + offset_len
                pad.addstr(y+i, 3*start + 20, "[" + "][".join(data[start:end]) + "]", attr)
        
        pad.refresh(0,0, 0,0, 30,100)


class ProjectEditor(object):
    def __init__(self, project, scr, player):
        self.project = project
        self.scr = scr
        self.player = player
        self._pattern = None
        self._seq_pos = 0
        self._seq_edit = False
        self._debug = ''
        self._undo_buffer = [self.project.dump()]

    def push_undo(self):
        self._undo_buffer.append(self.project.dump())

    def pop_undo(self):
        if len(self._undo_buffer) > 1:
            disc = self._undo_buffer.pop()
        self.project.load(self._undo_buffer[-1])

    def run(self):
        row_keys = {keys.KEY_UP: -1, keys.KEY_DOWN: 1}
        move_pattern_keys = {keys.KEY_SR: -1, keys.KEY_SF: 1}
        self.refresh()
        while True:
            try:
                ev = events.get()
            except:
                continue

            if ev.event_type == events.EVENT_QUIT:
                break

            if ev.event_type != events.EVENT_KEY_DOWN:
                continue

            k,c  = ev.key_code, ev.char
            if c == ':':
                command, parameters = sdlcurses.Menu(self.scr, commands = [
                    ('n', ['_New Project']),
                    ('o', ['_Open Project']),
                    ('s', ['_Save Project']),
                    ('np', ['_New', '_Pattern']),
                    ('dp', ['_Duplicate', '_Pattern']),
                    ('ep', ['_Edit', '_Pattern']),
                    ('epn', ['_Edit', '_Pattern', '_Name']),
                    ('rp', ['_Remove', '_Pattern']),
                    ('bpm', ['_Beats _per _minute']),
                    ('q', ['_Quit']),
                ]).run()

                if command == 'q':
                    break
                elif command == 'n':
                    self.player.stop()
                    self.project = project.create_empty_project()
                elif command == 'o':
                    with open('{}.json'.format(parameters), 'r') as f:
                        self.project.load(json.loads(f.read()))
                elif command == 's':
                    with open('{}.json'.format(parameters), 'w') as f:
                        f.write(json.dumps(self.project.dump(), indent=2))
                elif command == 'np':
                    self._new_pattern(parameters)
                elif command == 'dp':
                    self._duplicate_pattern()
                elif command == 'ep':
                    self._edit_pattern()
                elif command == 'epn':
                    if parameters:
                        self._pattern.name = parameters
                elif command == 'rp':
                    self._remove_pattern()
                elif command == 'bpm':
                    self._set_bpm(parameters)
            elif c == 'q' or k == keys.KEY_ESC:
                break
            elif k in row_keys:
                if self._seq_edit:
                    if  self._seq_pos is not None:
                        self._seq_pos = (self._seq_pos + row_keys[k]) % len(self.project.patterns_seq)
                elif self.project.patterns and self._pattern:
                    self._pattern = self.project.patterns[
                        (self._pattern_idx() + row_keys[k])
                        % len(self.project.patterns)
                    ]
                    if self.player.playing() and issubclass(self.player.data.__class__, project.Pattern):
                        self.player.mute()
                        self.player.play(self._pattern)
            elif k in move_pattern_keys:
                if self._seq_edit:
                    pseq = self.project.patterns_seq
                    i = self._seq_pos
                    j = (i + move_pattern_keys[k]) % len(pseq)
                    pseq[i], pseq[j] = pseq[j], pseq[i]
                    self._seq_pos = j
                    self.project.rebuild_sequence()
                else:
                    patterns = self.project.patterns
                    if len(patterns) < 2:
                        return
                    self.push_undo()
                    i = self._pattern_idx()
                    j = (i + move_pattern_keys[k]) % len(patterns)
                    patterns[i], patterns[j] = patterns[j], patterns[i]
            elif k in [keys.KEY_LEFT, keys.KEY_RIGHT]:
                self._seq_edit = not self._seq_edit
            elif k == keys.KEY_BACKSPACE:
                self.pop_undo()
            elif c == 'n':
                self._new_pattern(None)
            elif c == 'd':
                self._duplicate_pattern()
            elif c == 'r':
                if self._seq_edit:
                    if self._seq_pos is not None:
                        self.project.patterns_seq.pop(self._seq_pos)
                        self._seq_pos = min(self._seq_pos, len(self.project.patterns_seq)-1)
                        if self._seq_pos == -1:
                            self._seq_pos = None
                else:
                    self._remove_pattern()
                self.project.rebuild_sequence()
            elif k == keys.KEY_ENTER:
                self._edit_pattern()
            elif c == " ":
                if self.player.playing():
                    self.player.stop()
                else:
                    self.player.play(self._pattern)
            elif c == "+":
                self.push_undo()
                self._seq_pos = 0 if self._seq_pos is None else self._seq_pos + 1
                self.project.patterns_seq.insert(self._seq_pos, self._pattern.uid)
                self.project.rebuild_sequence()
            elif c == 'p':
                self.project.rebuild_sequence()
                if self.player.playing():
                    self.player.stop()
                self.player.play(self.project)
            else:
                self._debug = 'DEBUG: KEY {} | CHAR "{}"'.format(k, c)

            self._seq_edit = self._seq_edit and len(self.project.patterns_seq)
            self.refresh()

    def refresh(self):
        addstr =self.scr.addstr
        self.scr.erase()
        addstr(0, 0, 'PROJECT: {: <20} | BPM {}'.format(self.project.name, self.project.bpm))
        addstr(2, 0, '[{: ^40}] [{: ^40}]'.format('PATTERNS', 'SEQUENCE'))
        y = 3
        for pattern in self.project.patterns:
            if self._pattern not in self.project.patterns:
                self._pattern = pattern

            if self._pattern == pattern:
                a, b, attr = '>', '<', keys.A_BOLD
            else:
                a,b, attr = '.', '.', 0
            attr = 0 if self._seq_edit else attr

            addstr(y, 0, '[{}{:.^38}{}]'.format(a, pattern.name, b), attr)
            y = y + 1
        addstr(y + 1, 0, self._debug)
        for y, pattern_uid in enumerate(self.project.patterns_seq):
            if self._seq_pos is None:
                self._seq_pos = len(self.project.patterns_seq)-1

            if self._seq_pos == y:
                a, b, attr = '>', '<', keys.A_BOLD
            else:
                a,b, attr = '.', '.', 0
            attr = attr if self._seq_edit else 0

            name = [p.name for p in self.project.patterns if p.uid == pattern_uid]
            addstr(y+3, 43, '[{}{:.^38}{}]'.format(a, name[0], b), attr)
            
        self.scr.refresh(0,0, 0,0, 30,100)
    
    def _new_pattern(self, name):
        self.push_undo()
        pattern = project.create_empty_pattern()
        if name: pattern.name = name
        self.project.patterns.insert(
            0 if self._pattern is None else self._pattern_idx()+1,
            pattern
        )
        self._pattern = pattern

    def _duplicate_pattern(self):
        if self._pattern is None:
            return

        self.push_undo()
        new_pattern = project.Pattern()
        new_pattern.load(self._pattern.dump())
        new_pattern.uid = project.gen_uid()
        i = 1
        tmp_name = '{} ({})'.format(new_pattern.name, i)
        while len([n for n in self.project.patterns if n.name == tmp_name]):
            i += 1
            tmp_name = '{} ({})'.format(new_pattern.name, i)
        new_pattern.name = tmp_name
        self.project.patterns.insert(self._pattern_idx()+1, new_pattern)
    
    def _edit_pattern(self):
        if self._pattern is None:
            return

        PatternEditor(
            self.project, 
            self._pattern,
            self.scr,
            self.player, 
        ).run()
    
    def _remove_pattern(self):
        if self._pattern is None: return

        self.push_undo()
        project = self.project
        i = self._pattern_idx()
        project.remove_pattern(self._pattern)
        if project.patterns:
            self._pattern = project.patterns[min(i, len(project.patterns)-1)]
        else:
            self._pattern = None
    
    def _set_bpm(self, bpm):
        self.push_undo()
        set_bpm(bpm, self.project)
    
    def _pattern_idx(self):
        return self.project.patterns.index(self._pattern)
  

def set_bpm(bpm, project):
    if bpm and str(bpm).isdigit():
        bpm = int(bpm)
        project.bpm = bpm
        BPM.set(bpm)


def main():
    connections.connect()

    proj = project.create_empty_project()

    if os.path.exists('state.json'):
        with open('state.json') as f:
            proj.load(json.loads(f.read()))

    screen = sdlcurses.initscr('BeatKit v0.1', 'beatkit.png')

    # Pattern Player thread
    player = PlayerThread()
    player.start()
    set_bpm(proj.bpm, project)

    # Input sources
    keychars = sdlcurses.PyGameThread()
    keychars.start()
    midi_input = events.MidiInThread(connections.seq)
    midi_input.start()

    pated = ProjectEditor(proj, screen, player)

    try:
        pated.run()
    except Exception:
        print traceback.format_exc()

    with open('state.json', 'w') as f:
        f.write(json.dumps(pated.project.dump(), indent=2))

    player.quit()
    keychars.stop()
    midi_input.stop()


if __name__ == "__main__":
    main()
