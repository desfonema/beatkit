from os import popen
import re

from audio.alsaseq import alsaseq


seq = alsaseq('beatkit')
ports = {}


def get_ports(direction='o'):
    #Get MIDI Input ports LIST
    ports = {}
    engine_id = None
    engine_name = None
    with popen('aconnect -{}'.format(direction)) as f:
        for line in f:
            engine = re.search("client (\d+): '(.*?)' .*", line)
            if engine:
                engine_id, engine_name = engine.groups()
                continue

            port = re.search(" *(\d+) '(.*?) *'", line)
            if port:
                port_id, port_name = port.groups()
                if not port_name.startswith(engine_name):
                    port_name = "{} - {}".format(engine_name, port_name)
                ports[port_name] = (engine_id, port_id)

    return ports


def connect():
    oports = get_ports('o')
    iports = get_ports('i')

    for port in oports:
        if not port in ports:
            add_output(port)

    for oport in oports:
        for iport in iports:
            if "beatkit - {}".format(oport) == iport:
                popen("aconnect {i_id}:{i_port} {o_id}:{o_port} 2>/dev/null".format(
                    i_id=iports[iport][0],
                    i_port=iports[iport][1],
                    o_id=oports[oport][0],
                    o_port=oports[oport][1],
                )).close()


def add_output(name):
    output_index = len(ports)
    seq.create_output(name)
    ports[name] = output_index


def get_output(name):
    return ports.get(name)
