import os
import threading
import time
import json
from copy import deepcopy

import jack

from audio import alsaseq
import sdlcurses
import keys
import events
import project
import connections


def log(data):
    f = open('debug.log', 'a')
    f.write(str(data) + "\n")
    f.close()


#jack.attach("beatkit")
EMPTY_NOTE = ' '
MIDI_MIDDLE = 60


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
        super(PlayerThread, self).__init__()
        self.data = None
        self._run = threading.Event()
        self._run.set()
        self.playing = False
        self._startime = 0

    def run(self):
        prev_time = self.get_time()
        while self._run.is_set():

            if not self.playing:
                time.sleep(0.1)
                continue
            
            curr_time = self.get_time()
            if prev_time > curr_time:
                prev_time = curr_time - 0.1

            self.data.play_range(prev_time, curr_time)
            prev_time = curr_time
            time.sleep(0.01)

    def play(self, data):
        self.data = data
        connections.connect()
        self.data.bind()

        if self.playing:
            self._startime = 0
        else:
            self._startime = time.time()
        self.playing = True

    def stop(self):
        self.playing = False
        self.mute()

    def quit(self):
        self._run.clear()
        self.mute()

    def mute(self):
        if self.data:
            self.data.mute()

    def get_time(self):
        # Get the time on the song. 
        #return float(jack.get_current_transport_frame()) 
        #             / jack.get_sample_rate()
        if self.playing:
            return (time.time()-self._startime) * (BPM.get()/60.)*2
        else:
            return 0

    def get_state(self):
        # Return true for play, false for stop
        #return jack.get_transport_state()
        return True


class ChannelEditor(object):
    def __init__(self, scr, channel):
        self.channel = channel
        self.scr = scr

    def run(self):
        scr = self.scr
        scr.erase()
        channel = self.channel
        self.pos = 0
        fields = 4 if channel.channel_type == project.CHANNEL_TYPE_DRUM else 3
        while True:
            self.refresh()
            if self.pos == 0:
                k, v = scr.textbox(0, 15, 30, channel.name, edit=True)
                channel.name = v
            elif self.pos == 1:
                options = [c for c in connections.get_ports() if 'beatkit' not in c]
                k, v = scr.listbox(1, 15, 30, channel.midi_port, options=options, edit=True)
                channel.midi_port = v
                channel.bind()
            elif self.pos == 2:
                k, v = scr.textbox(2, 15, 30, channel.midi_channel, edit=True)
                if v.isdigit():
                    channel.midi_channel = int(v)
            elif self.pos == 3:
                k, v = scr.textbox(3, 15, 30, channel.note, edit=True)
                if v.isdigit():
                    channel.note = int(v)
            if k in [keys.KEY_TAB, keys.KEY_DOWN]:
                self.pos = (self.pos + 1) % fields
            elif k in [keys.KEY_STAB, keys.KEY_UP]:
                self.pos = (self.pos - 1) % fields
            elif k in [keys.KEY_ENTER, keys.KEY_ESC]:
                break
                
    def refresh(self):
        scr = self.scr
        channel = self.channel
        items = [
            ('Name', channel.name),
            ('Midi Port', channel.midi_port),
            ('Midi Channel', channel.midi_channel),
        ]
        if channel.channel_type == project.CHANNEL_TYPE_DRUM:
            items.append(('Note', channel.note))

        for i, data in enumerate(items):
            label, value = data
            scr.addstr(i, 0, label)
            if i == self.pos:
                continue
            scr.textbox(i, 15, 30, value)


class PatternEditor(object):
    def __init__(self, project, pattern, pad, player):
        self._current_channel = 0
        self._channel_offset = 0
        self._octave = 0
        self.project = project
        self.pattern = pattern
        self.pad = pad
        self.player = player
        self.delete_keys = ['A', 'S', 'D', 'F']
        self._undo_buffer = [self.pattern.dump()]

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
        move_channel_keys = {keys.KEY_SR: -1, keys.KEY_SF: 1}
        shift_channel_keys = {keys.KEY_SLEFT: 1, keys.KEY_SRIGHT: -1}
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
                break

            self._current_channel = min(self._current_channel, len(self.pattern.channels) - 1)
            channel = self.pattern.channels[self._current_channel]

            if ev.event_type == events.EVENT_MIDI:
                # Process input values
                if ev.midi_event_type == alsaseq.MIDI_EVENT_NOTE_ON:
                    if ev.note not in midi_state:
                        channel.note_on(self.player.get_time(), ev.note, 127)
                        midi_state.add(ev.note)
                elif ev.midi_event_type == alsaseq.MIDI_EVENT_NOTE_OFF:
                    if ev.note in midi_state:
                        channel.note_off(self.player.get_time(), ev.note)
                        midi_state.remove(ev.note)

                    if not midi_state:
                        self.push_undo()

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
                        channel = project.DrumChannel(name, [' '] * channel.len(), "", 15, 44)
                        self.pattern.channels.append(channel)
                        self._current_channel = len(self.pattern.channels) - 1
                        ChannelEditor(pad, channel).run()
                    elif command == 'nm':
                        name = parameters or 'Midi Channel'
                        channel = project.MidiChannel(name, channel.len(), [], [0] * channel.len(), "", 0)
                        self.pattern.channels.append(channel)
                        self._current_channel = len(self.pattern.channels) - 1
                        ChannelEditor(pad, channel).run()
                    elif command == 'd':
                        tmp_channel = channel.__class__()
                        tmp_channel.load(channel.dump())
                        self.pattern.channels.append(tmp_channel)
                        self._current_channel = len(self.pattern.channels) - 1
                    elif command == 'r':
                        self.pattern.channels.remove(channel)
                        self._current_channel = min(self._current_channel, len(self.pattern.channels) - 1)
                    elif command == 'e':
                        ChannelEditor(pad, channel).run()
                    elif command == 'en':
                        channel.name = parameters
                    elif command == 'bpm':
                        set_bpm(parameters, self.project)
                    elif command == 'pl':
                        self.pattern.resize(int(parameters))
                    
                elif c in key_to_midi + drum_keys:
                    midi_note = None
                    if channel.channel_type == project.CHANNEL_TYPE_DRUM:
                        if c in drum_keys:
                            pos = drum_keys.index(c)
                            pos += self._channel_offset * len(delete_keys)
                            midi_note = drum_key_to_note[pos]
                    else:
                        midi_note = key_to_midi.index(c) + key_to_midi_octave * 12 + 60
                    
                    if not key_to_midi_state.get(midi_note):
                        events.put(events.MidiEvent(alsaseq.MIDI_EVENT_NOTE_ON, 0, midi_note, 127))
                        key_to_midi_state[midi_note] = True
                elif c == " ":
                    if self.player.playing:
                        self.player.stop()
                    else:
                        self.player.play(self.pattern)
                elif k in row_keys:
                    self._current_channel = (self._current_channel + row_keys[k]) % len(self.pattern.channels)
                elif k in move_channel_keys:
                    i =  self._current_channel
                    j =  (i + move_channel_keys[k]) % len(self.pattern.channels)
                    self.pattern.channels[i], self.pattern.channels[j] = self.pattern.channels[j], self.pattern.channels[i]
                    self._current_channel = (self._current_channel + move_channel_keys[k]) % len(self.pattern.channels)
                elif k in shift_channel_keys:
                    channel.shift(shift_channel_keys[k])
                elif k in offset_keys:
                    self._channel_offset = (self._channel_offset + offset_keys[k]) % len(delete_keys)
                elif c in octave_keys:
                    key_to_midi_octave += octave_keys[c]
                elif c in delete_keys:
                    pos = delete_keys.index(c) + self._channel_offset * len(delete_keys)
                    channel.clear(pos)
                    self.push_undo()
                elif c in quantize_keys:
                    if True or channel.channel_type == project.CHANNEL_TYPE_DRUM:
                        pos = self._channel_offset * len(delete_keys)
                        for i in range(len(delete_keys)):
                            channel.quantize(pos + i, c)
                        self.push_undo()
                elif k == keys.KEY_BACKSPACE:
                    self.pop_undo()
                elif k == keys.KEY_ENTER:
                    ChannelEditor(pad, channel).run()
                elif c == 'q' or k == keys.KEY_ESC:
                    break
                else:
                    # Print unhandled event
                    pad.addstr(10,0,c + '                ')
                pad.addstr(15,0,'KEY DN: ' +str(k) + '                ')
                pad.addstr(17,0,'octave: {}   '.format(key_to_midi_octave))

            elif ev.event_type == events.EVENT_KEY_UP:
                k = ev.key_code
                c = chr(k & 0xff)
                pad.addstr(16,0,'KEY UP: ' +str(k) + '                ')
                if c in key_to_midi + drum_keys:
                    midi_note = None
                    if channel.channel_type == project.CHANNEL_TYPE_DRUM:
                        if c in drum_keys:
                            pos = drum_keys.index(c)
                            pos += self._channel_offset * len(delete_keys)
                            midi_note = drum_key_to_note[pos]
                    else:
                        midi_note = key_to_midi.index(c) + key_to_midi_octave * 12 + 60

                    if key_to_midi_state.get(midi_note):
                        events.put(events.MidiEvent(alsaseq.MIDI_EVENT_NOTE_OFF, 0, midi_note, 127))
                        key_to_midi_state[midi_note] = False

            nowtime = time.time()
            if repaint < nowtime - 0.05:
                self.paint()
                repaint = nowtime


    def paint(self, only_pos=False):
        pad = self.pad
        channels = self.pattern.channels
        current_channel = self._current_channel
        curr_time = self.player.get_time()
        if self.pattern.channels:
            pad.addstr(0, 0, " " * (20 + int(curr_time)%self.pattern.len*3) + " *                     ", keys.A_BOLD)
            
        for channel in channels:
            if only_pos: break
            y = channels.index(channel)
            offset_len = len(self.delete_keys)
            for offset in range(0, self.pattern.len / offset_len):
                if y == current_channel and offset == self._channel_offset:
                    attr = keys.A_BOLD
                else:
                    attr = 0
                pad.addstr(y+1, 0, "{: >20}".format(channel.name))
                for x in range(offset * offset_len, min((offset+1) * offset_len, self.pattern.len)):
                    data = '-'
                    if channel.channel_type == project.CHANNEL_TYPE_DRUM:
                        data = channel.data[x]
                    elif channel.channel_type == project.CHANNEL_TYPE_BASSLINE:
                        data = channel.beat_data[x]
                    pad.addstr(y+1, x*3 + 20, "[{}]".format(data), attr)
        
        pad.refresh(0,0, 0,0, 30,100)


class ProjectEditor(object):
    def __init__(self, project, scr, player):
        self.project = project
        self.scr = scr
        self.player = player
        self._pattern = None
        self._seq_pos = None
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
                        (self.project.patterns.index(self._pattern) + row_keys[k])
                        % len(self.project.patterns)
                    ]
                    if self.player.playing and issubclass(self.player.data.__class__, project.Pattern):
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
                    i = patterns.index(self._pattern)
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
                if self.player.playing:
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
                if self.player.playing:
                    self.player.stop()
                self.player.play(self.project)
            else:
                self._debug = 'DEBUG: KEY {} | CHAR "{}"'.format(k, c)

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
        if name:
            pattern.name = name
        if self._pattern:
            i = self.project.patterns.index(self._pattern)
        else:
            i = -1

        self.project.patterns.insert(i+1, pattern)
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
        i = self.project.patterns.index(self._pattern)
        self.project.patterns.insert(i+1, new_pattern)
    
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
        if self._pattern is None:
            return

        self.push_undo()
        patterns = self.project.patterns
        i = patterns.index(self._pattern)
        patterns.remove(self._pattern)

        self.project.patterns_seq = [p for p in self.project.patterns_seq 
                                     if p != self._pattern.uid]
        if not patterns:
            self._pattern = None
            return
        if i < len(patterns):
            self._pattern = patterns[i]
        else:
            self._pattern = patterns[-1]
    
    def _set_bpm(self, bpm):
        self.push_undo()
        set_bpm(bpm, self.project)
  

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

    screen = sdlcurses.initscr()

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
    pated.run()

    with open('state.json', 'w') as f:
        f.write(json.dumps(proj.dump(), indent=2))

    player.quit()
    keychars.stop()
    midi_input.stop()


if __name__ == "__main__":
    main()
