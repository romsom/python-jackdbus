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
    def __init__(self, client, port, clientID, portID, ptype, flags):
        # TODO? ids
        #if isinstance(client, dbus.String):
        #    self.client = client.
        self.client = client
        self.port = port
        self.portID = portID
        self.clientID = clientID
        self.type = ptype
        self.flags = flags

    def getType(self):
        """get string representation of port type
        reference: common/JackPortType.h"""
        if self.type == 0:
            return AUDIO_PORT
        if self.type == 1:
            return MIDI_PORT
        return UNKNOWN_PORT

    # reference for flags: common/jack/types.h -> JackPortFlags

    def isInput(self):
        return self.flags & 0x1 != 0

    def isOutput(self):
        return self.flags & 0x2 != 0

    def isPhysical(self):
        return self.flags & 0x4 != 0
    # missing: canMonitor (0x8), isTerminal(0x10)

    def __str__(self):
        return "{}:{}".format(self.client, self.port)

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        return self.client == other.client and self.port == other.port

    def isID(self, clientID, portID):
        return clientID == self.clientID and portID == self.portID

    def isPort(self, client, port):
        return client == self.client and port == self.port


class JackConnection():
    def __init__(self, dbus_data, ports):
        self.source = [p for p in ports if p.lookupPortByName(dbus_data[1], dbus_data[3]) is not None][0]
        self.dest = [p for p in ports if p.lookupPortByName(dbus_data[5], dbus_data[7]) is not None][0]
        self.id = dbus_data[8]

    def __str__(self):
        return "{} -> {}".format(self.source, self.dest)

class JackClient():
    def __init__(self, dbus_data):
        self.id = dbus_data[0]
        self.name = dbus_data[1]
        self.ports = [JackPort(self.name, d[1], self.id, d[0], d[3], d[2]) for d in dbus_data[2]]
        self.pid = jack_patchbay.GetClientPID(self.id)

    def lookupPort(self, clientID, portID):
        for p in self.ports:
            if p.isID(clientID, portID):
                return p
        return None

    def lookupPortByName(self, client, port):
        for p in self.ports:
            if p.isPort(client, port):
                return port
        return None

    def getPortsByName(self, port):
        """get all matching ports"""
        r = re.compile(port)
        return [p for p in self.ports if r.match(str(p.port))]

    def hasAllPorts(self, predicate_funcs):
        '''expects a function with self.ports as the only parameter which returns
        a tuple of a list of predicates which describe ports and the number of
        expected ports'''
        for predicate, n in predicate_funcs:
            if len([p for p in self.ports if predicate(p)]) < n:
                return False
        return True

    def getAudioInputs(self):
        return [p for p in self.ports if AUDIO_INPUT(p)]

    def getAudioOutputs(self):
        return [p for p in self.ports if AUDIO_OUTPUT(p)]

    def getMidiInputs(self):
        return [p for p in self.ports if MIDI_INPUT(p)]

    def getMidiOutputs(self):
        return [p for p in self.ports if MIDI_OUTPUT(p)]

    def getInputs(self, port_type):
        return [p for p in self.ports if p.isInput() and p.getType() == port_type]

    def getOutputs(self, port_type):
        return [p for p in self.ports if p.isOutput() and p.getType() == port_type]

    def getName(self):
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

    def lookupPort(self, clientID, portID):
        return self.clients.lookupPort(clientID, portID)

    def lookupPortByName(self, client, port):
        return self.clients.lookupPortByName(client, port)

    def ports(self):
        return reduce(lambda a,b: a+b, [c.ports for c in self.clients], [])


def getGraph():
    return JackGraph(jack_patchbay.GetGraph(0))

def getClients():
    graph = JackGraph(jack_patchbay.GetGraph(0))
    return graph.clients

def getClientsByPID(pid):
    cs = getClients()
    return [c for c in cs if c.pid == pid]

def getClientsByName(name):
    cs = getClients()
    r = re.compile(name)
    return [c for c in cs if r.match(c.name)]

def getPorts():
    graph = JackGraph(jack_patchbay.GetGraph(0))
    return graph.ports()

def getConnections():
    graph = JackGraph(jack_patchbay.GetGraph(0))
    return graph.connections

def connect(sPort, dPort):
    print('connecting [{}:{}] -> [{}:{}]'.format(sPort.client, sPort.port, dPort.client, dPort.port))
    jack_patchbay.ConnectPortsByName(sPort.client, sPort.port,
                                     dPort.client, dPort.port)
def disconnect(sPort, dPort):
    print('disconnecting [{}:{}] -|> [{}:{}]'.format(sPort.client, sPort.port, dPort.client, dPort.port))
    jack_patchbay.DisconnectPortsByName(dbus.String(sPort.client), dbus.String(sPort.port),
                                     dbus.String(dPort.client), dbus.String(dPort.port))
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
    return getClientsByName(r'system|firewire_pcm')
