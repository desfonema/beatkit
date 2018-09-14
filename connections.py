from os import popen
import re

from audio.alsaseq import alsaseq
from pyalsa import alsaseq as aseq


seq = alsaseq('beatkit')

def get_ports(direction='o'):
    #Get MIDI Input ports LIST
    ports = {}
    if direction == 'o':
        required_cap = aseq.SEQ_PORT_CAP_WRITE | aseq.SEQ_PORT_CAP_SUBS_WRITE
    else:
        required_cap = aseq.SEQ_PORT_CAP_READ | aseq.SEQ_PORT_CAP_SUBS_READ

    for client_name, client_id, client_ports in seq.seq.connection_list():
        for port_name, port_id, properties in client_ports:
            capability = seq.seq.get_port_info(port_id, client_id).get('capability', 0)
            if capability & required_cap == required_cap:
                if port_name.startswith(client_name):
                    name = port_name
                else:
                    name = "{} - {}".format(client_name, port_name)
                ports[name] = (client_id, port_id)

    return ports


def connect():
    oports = get_ports('o')

    for port_name, data in oports.iteritems():
        dest_id, dest_port = data
        if dest_id == seq.seq.client_id:
            continue
        if not port_name in seq.ports:
            source_port = seq.create_output(port_name)
            seq.connect(source_port, dest_id, dest_port)
