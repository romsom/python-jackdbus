#!/usr/bin/env python3

# Python library to manage JACK connections from python via DBUS and cli geek tool to create/break multiple connections at once using regular expressions.
# Copyright (C) 2018-2022 Roman Sommer <roman@resonant-bytes.de>
# SPDX-License-Identifier: BSD-2-Clause

import dbus
from functools import reduce
import re
import argparse

# use dbus-send --session --print-reply --dest=org.jackaudio.service /org/jackaudio/... <interface> [Parameters]
# -> tab completion is your friend (except for parameters)

bus = dbus.SessionBus()
# TODO multiple jack sessions
jack_controller = bus.get_object('org.jackaudio.service',
                                 '/org/jackaudio/Controller')
jack_patchbay = dbus.Interface(jack_controller, 'org.jackaudio.JackPatchbay')

AUDIO_PORT = 'audio'
MIDI_PORT = 'midi'
UNKNOWN_PORT = 'unknown'

SYSTEM_CLIENT_REGEX=r'system|firewire_pcm'

class JackPort():
    def __init__(self, client, port, client_id, port_id, ptype, flags):
        # TODO? ids
        #if isinstance(client, dbus.String):
        #    self.client = client.
        self.client = client
        self.port = port
        self.port_id = port_id
        self.client_id = client_id
        self.type = ptype
        self.flags = flags

    def get_type(self):
        """get string representation of port type
        reference: common/JackPortType.h"""
        if self.type == 0:
            return AUDIO_PORT
        if self.type == 1:
            return MIDI_PORT
        return UNKNOWN_PORT

    # reference for flags: common/jack/types.h -> JackPortFlags

    def is_input(self):
        return self.flags & 0x1 != 0

    def is_output(self):
        return self.flags & 0x2 != 0

    def is_physical(self):
        return self.flags & 0x4 != 0
    # missing: can_monitor (0x8), is_terminal(0x10)

    def is_audio_input(self):
        return self.is_input() and self.get_type() == AUDIO_PORT

    def is_audio_output(self):
        return self.is_output() and self.get_type() == AUDIO_PORT

    def is_midi_input(self):
        return self.is_input() and self.get_type() == MIDI_PORT

    def is_midi_output(self):
        return self.is_output() and self.get_type() == MIDI_PORT

    def __str__(self):
        return "{}:{}".format(self.client, self.port)

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        return self.client == other.client and self.port == other.port

    def is_id(self, client_id, port_id):
        return client_id == self.client_id and port_id == self.port_id

    def is_port(self, client, port):
        return client == self.client and port == self.port


class JackConnection():
    def __init__(self, dbus_data, ports):
        self.source = [p for p in ports if p.lookup_port_by_name(dbus_data[1], dbus_data[3]) is not None][0]
        self.dest = [p for p in ports if p.lookup_port_by_name(dbus_data[5], dbus_data[7]) is not None][0]
        self.id = dbus_data[8]

    def __str__(self):
        return "{} -> {}".format(self.source, self.dest)

class JackClient():
    def __init__(self, dbus_data):
        self.id = dbus_data[0]
        self.name = dbus_data[1]
        self.ports = [JackPort(self.name, d[1], self.id, d[0], d[3], d[2]) for d in dbus_data[2]]
        self.pid = jack_patchbay.GetClientPID(self.id)

    def lookup_port(self, client_id, port_id):
        for p in self.ports:
            if p.is_id(client_id, port_id):
                return p
        return None

    def lookup_port_by_name(self, client, port):
        for p in self.ports:
            if p.is_port(client, port):
                return port
        return None

    def get_ports_by_name(self, port):
        """get all matching ports"""
        r = re.compile(port)
        return [p for p in self.ports if r.match(str(p.port))]

    def has_all_ports(self, predicate_funcs):
        '''expects a function with self.ports as the only parameter which returns
        a tuple of a list of predicates which describe ports and the number of
        expected ports'''
        for predicate, n in predicate_funcs:
            if len([p for p in self.ports if predicate(p)]) < n:
                return False
        return True

    def get_audio_inputs(self):
        return [p for p in self.ports if p.is_audio_input()]

    def get_audio_outputs(self):
        return [p for p in self.ports if p.is_audio_output()]

    def get_midi_inputs(self):
        return [p for p in self.ports if p.is_midi_input()]

    def get_midi_outputs(self):
        return [p for p in self.ports if p.is_midi_output()]

    def get_inputs(self, port_type):
        return [p for p in self.ports if p.is_input() and p.get_type() == port_type]

    def get_outputs(self, port_type):
        return [p for p in self.ports if p.is_output() and p.get_type() == port_type]

    def get_name(self):
        return self.name

    def __str__(self):
        return "{}: {}\n\t{}".format(self.name, self.id, self.ports)

    def __repr__(self):
        return "{} [{}]".format(self.name, self.pid)


class JackGraph():
    def __init__(self, dbus_data):
        self.version = dbus_data[0]
        self.clients = [JackClient(d) for d in dbus_data[1]]
        self.connections = [JackConnection(d, self.clients) for d in dbus_data[2]]

    def lookup_port(self, client_id, port_id):
        return self.clients.lookup_port(client_id, port_id)

    def lookup_port_by_name(self, client, port):
        return self.clients.lookup_port_by_name(client, port)

    def ports(self):
        return reduce(lambda a,b: a+b, [c.ports for c in self.clients], [])


def get_graph():
    return JackGraph(jack_patchbay.GetGraph(0))

def get_clients():
    graph = JackGraph(jack_patchbay.GetGraph(0))
    return graph.clients

def get_clients_by_pid(pid):
    cs = get_clients()
    return [c for c in cs if c.pid == pid]

def get_clients_by_name(name):
    cs = get_clients()
    r = re.compile(name)
    return [c for c in cs if r.match(c.name)]

def get_ports():
    graph = JackGraph(jack_patchbay.GetGraph(0))
    return graph.ports()

def get_connections():
    graph = JackGraph(jack_patchbay.GetGraph(0))
    return graph.connections

def connect(s_port, d_port):
    print('connecting [{}:{}] -> [{}:{}]'.format(s_port.client, s_port.port, d_port.client, d_port.port))
    jack_patchbay.ConnectPortsByName(s_port.client, s_port.port,
                                     d_port.client, d_port.port)
def disconnect(s_port, d_port):
    print('disconnecting [{}:{}] -|> [{}:{}]'.format(s_port.client, s_port.port, d_port.client, d_port.port))
    jack_patchbay.DisconnectPortsByName(dbus.String(s_port.client), dbus.String(s_port.port),
                                        dbus.String(d_port.client), dbus.String(d_port.port))

def system_clients():
    return get_clients_by_name(SYSTEM_CLIENT_REGEX)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Connect/disconnect jack ports consecutively by matching them with regular expressions.",
                                     prog='jack_re_connect')
    parser.add_argument('action', choices=['connect', 'disconnect'], help='Should the ports be connected or disconnected?')
    parser.add_argument('--sclient', default=SYSTEM_CLIENT_REGEX, help='Regex for the source jack client')
    parser.add_argument('--sport', default=".*", help='Regex for the source jack port')
    parser.add_argument('--dclient', default=SYSTEM_CLIENT_REGEX, help='Regex for the destination jack client')
    parser.add_argument('--dport', default=".*", help='Regex for the destination jack port')
    parser.add_argument('--number-of-ports', '-n', default=-1, type=int,
                        help='Limit the number of consecutive connections to NUMBER_OF_PORTS')
    parser.add_argument('--sstart', default=0, type=int, help='The index of the first source match to be connected')
    parser.add_argument('--dstart', default=0, type=int, help='The index of the first destination match to be connected')

    args = parser.parse_args()

    source_client_re = re.compile(args.sclient)
    source_port_re = re.compile(args.sport)
    dest_client_re = re.compile(args.dclient)
    dest_port_re = re.compile(args.dport)

    ports = get_ports()
    sources = [p for p in ports if source_client_re.match(p.client) and source_port_re.match(p.port) and p.is_output()]
    dests = [p for p in ports if dest_client_re.match(p.client) and dest_port_re.match(p.port) and p.is_input()]

    n = min(len(sources), len(dests))
    if args.number_of_ports >= 0:
        n = min(n, args.number_of_ports)
    send = min(len(sources), args.sstart + n)
    dend = min(len(dests), args.dstart + n)
    pairs = zip(sources[args.sstart:send], dests[args.dstart:dend])

    if args.action == 'connect':
        for s, d in pairs:
            connect(s, d)
    elif args.action == 'disconnect':
        for s, d in pairs:
            disconnect(s, d)
