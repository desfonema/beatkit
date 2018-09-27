from pyalsa import alsaseq

MIDI_EVENT_NOTE_ON = alsaseq.SEQ_EVENT_NOTEON
MIDI_EVENT_NOTE_OFF = alsaseq.SEQ_EVENT_NOTEOFF
MIDI_EVENT_CONTROLLER = alsaseq.SEQ_EVENT_CONTROLLER
MIDI_EVENT_PITCH = alsaseq.SEQ_EVENT_PITCHBEND

SEQ_PORT_CAP_WRITE = alsaseq.SEQ_PORT_CAP_WRITE
SEQ_PORT_CAP_SUBS_WRITE = alsaseq.SEQ_PORT_CAP_SUBS_WRITE
SEQ_PORT_CAP_READ = alsaseq.SEQ_PORT_CAP_READ
SEQ_PORT_CAP_SUBS_READ = alsaseq.SEQ_PORT_CAP_SUBS_READ
SEQ_PORT_TYPE_APPLICATION = alsaseq.SEQ_PORT_TYPE_APPLICATION

SeqEvent = alsaseq.SeqEvent


class SequencerInterface:
    def __init__(self, name):
        self.seq = alsaseq.Sequencer(clientname=name)
        self.intput = self.seq.create_simple_port(
            'Midi Input',
            SEQ_PORT_TYPE_APPLICATION,
            SEQ_PORT_CAP_WRITE | SEQ_PORT_CAP_SUBS_WRITE,
        )
        self.ports = {}

    def create_output(self, name):
        port_id = self.seq.create_simple_port(
            name,
            SEQ_PORT_TYPE_APPLICATION,
            SEQ_PORT_CAP_READ | SEQ_PORT_CAP_SUBS_READ
        )
        self.ports[name] = port_id
        return port_id

    def connect(self, port, dest_id, dest_port):
        self.seq.connect_ports((self.seq.client_id, port),
                               (dest_id, dest_port))

    def event_input(self):
        return self.seq.receive_events(timeout=250, maxevents=10)

    def send_output(self, port, event_type, event_data):
        if not isinstance(port, int):
            return

        ev = SeqEvent(type=event_type)
        ev.source = (self.seq.client_id, port)
        ev.set_data(event_data)
        self.seq.output_event(ev)
        self.seq.drain_output()

    def note_on(self, port, note, channel, velocity):
        self.send_output(port, MIDI_EVENT_NOTE_ON, {
            'note.channel': channel,
            'note.note': note,
            'note.velocity': velocity,
        })

    def note_off(self, port, note, channel):
        self.send_output(port, MIDI_EVENT_NOTE_OFF, {
            'note.channel': channel,
            'note.note': note,
            'note.velocity': 0,
        })

    def set_control(self, port, value, param, channel):
        self.send_output(port, MIDI_EVENT_CONTROLLER, {
            'control.value': value,
            'control.param': param,
            'control.channel': channel,
        })

    def set_pitchbend(self, port, value, channel):
        self.send_output(port, MIDI_EVENT_PITCH, {
            'control.value': value,
            'control.channel': channel,
        })
