import Queue
import threading
from time import sleep
from util import set_thread_name


EVENT_NONE = 0
EVENT_KEY_UP = 1
EVENT_KEY_DOWN = 2
EVENT_MIDI = 4
EVENT_QUIT = 64


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


class MidiEvent(Event):
    event_type = EVENT_MIDI
    
    def __init__(self, midi_event_type, channel, note, velocity):
        self.midi_event_type = midi_event_type
        self.channel = channel
        self.note = note
        self.velocity = velocity

        
class QuitEvent(Event):
    event_type = EVENT_QUIT


class MidiInThread(threading.Thread):
    def __init__(self, seq):
        super(MidiInThread, self).__init__()
        set_thread_name("beatkit midi-in")
        self.seq = seq
        seq.create_input()
        self._run = threading.Event()
        self._run.set()

    def run(self):
        while self._run.is_set():
            while self.seq.event_input_pending():
                ev = self.seq.event_input()
                put(MidiEvent(
                    ev['type'],
                    ev['data']['note']['channel'],
                    ev['data']['note']['note'],
                    ev['data']['note']['velocity']
                ))
            sleep(0.01)
                
        
    def stop(self):
        self._run.clear()
