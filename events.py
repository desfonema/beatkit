import Queue
import threading
from util import set_thread_name

from sequencer_interface import (
    MIDI_EVENT_CONTROLLER,
    MIDI_EVENT_PITCH,
    MIDI_EVENT_NOTE_ON,
    MIDI_EVENT_NOTE_OFF,
)

EVENT_NONE = 0
EVENT_KEY_UP = 1
EVENT_KEY_DOWN = 2
EVENT_MIDI_NOTE = 4
EVENT_MIDI_CONTROLLER = 8
EVENT_MIDI_PITCHBEND = 16
EVENT_QUIT = 64
EVENT_REFRESH = 128


event_queue = Queue.Queue()


def get():
    return event_queue.get(timeout=0.3)


def put(ev):
    event_queue.put(ev)


class Event(object):
    event_type = EVENT_NONE


class KeyboardDownEvent(Event):
    event_type = EVENT_KEY_DOWN

    def __init__(self, key_code, char=None):

        self.key_code = key_code
        self.char = char


class KeyboardUpEvent(Event):
    event_type = EVENT_KEY_UP

    def __init__(self, key_code, char=None):

        self.key_code = key_code
        self.char = char


class MidiNoteEvent(Event):
    event_type = EVENT_MIDI_NOTE

    def __init__(self, midi_event_type, channel, note, velocity):
        self.midi_event_type = midi_event_type
        self.channel = channel
        self.note = note
        self.velocity = velocity


class MidiControllerEvent(Event):
    event_type = EVENT_MIDI_CONTROLLER

    def __init__(self, channel, param, value):
        self.midi_event_type = MIDI_EVENT_CONTROLLER
        self.channel = channel
        self.param = param
        self.value = value


class MidiPitchbendEvent(Event):
    event_type = EVENT_MIDI_PITCHBEND

    def __init__(self, channel, value):
        self.midi_event_type = MIDI_EVENT_PITCH
        self.channel = channel
        self.value = value


class QuitEvent(Event):
    event_type = EVENT_QUIT


class RefreshEvent(Event):
    event_type = EVENT_REFRESH


class MidiInThread(threading.Thread):
    def __init__(self, seq):
        super(MidiInThread, self).__init__()
        set_thread_name("beatkit midi-in")
        self.seq = seq
        self._run = threading.Event()
        self._run.set()

    def run(self):
        while self._run.is_set():
            for ev in self.seq.event_input():
                data = ev.get_data()

                if ev.type == MIDI_EVENT_NOTE_ON:
                    # Deal with Keystation 61es "Note off"
                    if not data['note.velocity']:
                        ev.type = MIDI_EVENT_NOTE_OFF
                    event = MidiNoteEvent(
                        ev.type,
                        data['note.channel'],
                        data['note.note'],
                        data['note.velocity']
                    )
                elif ev.type == MIDI_EVENT_NOTE_OFF:
                    event = MidiNoteEvent(
                        ev.type,
                        data['note.channel'],
                        data['note.note'],
                        data['note.velocity']
                    )
                elif ev.type == MIDI_EVENT_CONTROLLER:
                    event = MidiControllerEvent(
                        data['control.channel'],
                        data['control.param'],
                        data['control.value']
                    )
                elif ev.type == MIDI_EVENT_PITCH:
                    event = MidiPitchbendEvent(
                        data['control.channel'],
                        data['control.value']
                    )
                else:
                    continue

                put(event)

    def stop(self):
        self._run.clear()
