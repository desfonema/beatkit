from sequencer_interface import SequencerInterface
from sequencer_interface import (
    SEQ_PORT_CAP_WRITE,
    SEQ_PORT_CAP_SUBS_WRITE,
)


seq = SequencerInterface('beatkit')


def get_ports():
    # Get MIDI Input ports LIST
    ports = {}
    required_cap = SEQ_PORT_CAP_WRITE | SEQ_PORT_CAP_SUBS_WRITE

    for client_name, client_id, client_ports in seq.seq.connection_list():
        for port_name, port_id, properties in client_ports:
            capability = seq.seq.get_port_info(
                port_id, client_id).get('capability', 0)
            if capability & required_cap == required_cap:
                if port_name.startswith(client_name):
                    name = port_name
                else:
                    name = "{} - {}".format(client_name, port_name)
                ports[name] = (client_id, port_id)

    return ports


def connect():
    oports = get_ports()

    for port_name, data in oports.iteritems():
        dest_id, dest_port = data
        if dest_id == seq.seq.client_id:
            continue
        if port_name not in seq.ports:
            source_port = seq.create_output(port_name)
            seq.connect(source_port, dest_id, dest_port)
