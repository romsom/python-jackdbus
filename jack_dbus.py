#!/usr/bin/env python3
import dbus
from functools import reduce
import re

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
        return [p for p in self.ports if AUDIO_INPUT(p)]

    def get_audio_outputs(self):
        return [p for p in self.ports if AUDIO_OUTPUT(p)]

    def get_midi_inputs(self):
        return [p for p in self.ports if MIDI_INPUT(p)]

    def get_midi_outputs(self):
        return [p for p in self.ports if MIDI_OUTPUT(p)]

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
#for c in getPorts():
#    print(c)

def AUDIO_INPUT(port):
    return port.isInput() and port.getType() == AUDIO_PORT
def AUDIO_OUTPUT(port):
    return port.isOutput() and port.getType() == AUDIO_PORT
def MIDI_INPUT(port):
    return port.isInput() and port.getType() == MIDI_PORT
def MIDI_OUTPUT(port):
    return port.isOutput() and port.getType() == MIDI_PORT

def system_clients():
    return get_clients_by_name(r'system|firewire_pcm')
