# Copyright (C) 2018, 2019 Andreas Motzek andreas-motzek@t-online.de
#
# This file is part of the MQTT package.
#
# You can use, redistribute and/or modify this file under the terms of the Modified Artistic License.
# See http://simplysomethings.de/open+source/modified+artistic+license.html for details.
#
# This file is distributed in the hope that it will be useful, but without any warranty; without even
# the implied warranty of merchantability or fitness for a particular purpose.

class AbstractRequest:

    def __init__(self, packet_type, flags):
        self.content = []
        self.size = 0
        self.packet_type = packet_type
        self.flags = flags

    def _append_byte(self, value):
        self.content.append(lambda stream : stream.write(bytes([value])))
        self.size += 1

    def _append_short(self, value):
        self.content.append(lambda stream : stream.write(bytes([value >> 8, value & 255])))
        self.size += 2

    def _append_string(self, value):
        self.content.append(lambda stream : stream.write(bytes(value, 'ascii')))
        self.size += len(value)

    def _append_len_string(self, value):
        self._append_short(len(value))
        self._append_string(value)

    def write_to(self, stream):
        meta = [(self.packet_type << 4) | (self.flags & 15)]
        size = self.size
        while True:
            digit = size & 127
            size >>= 7
            if size > 0:
                meta.append(digit | 128)
            else:
                meta.append(digit)
                break
        stream.write(bytes(meta))
        for writer in self.content:
            writer(stream)
        # stream.flush()

class ConnectRequest(AbstractRequest):

    def __init__(self, client_id, user_name, password):
        super().__init__(1, 0)  # connect
        self._append_len_string('MQTT')
        self._append_byte(4)  # level
        self._append_byte(2 | 64 | 128)  # clean session, password, user name
        self._append_short(600)  # keep alive
        self._append_len_string(client_id)
        self._append_len_string(user_name)
        self._append_len_string(password)

class PublishRequest(AbstractRequest):

    def __init__(self, topic_name, payload, retain = True):
        super().__init__(3, 1 if retain else 0)  # publish, retain
        self._append_len_string(topic_name)
        self._append_string(payload)

class PublishAcknowledgement(AbstractRequest):

    def __init__(self, packet_id):
        super().__init__(4, 0)  # publish acknowledgement
        self._append_short(packet_id)

class SubscribeRequest(AbstractRequest):

    def __init__(self, packet_id, topic_filter, qos = 0):
        super().__init__(8, 2)  # subscribe
        self._append_short(packet_id)
        self._append_len_string(topic_filter)
        self._append_byte(qos)

class PingRequest(AbstractRequest):

    def __init__(self):
        super().__init__(12, 0)  # ping request

class AbstractResponse:

    def __init__(self, flags, size):
        self.flags = flags
        self.size = size

    @staticmethod
    def receive_from(stream):
        first_byte = AbstractResponse._read_byte(stream)
        flags = first_byte & 15
        packet_type = first_byte >> 4
        size = 0
        multiplier = 1
        while True:
            digit = AbstractResponse._read_byte(stream)
            size += (digit & 127) * multiplier
            multiplier <<= 7
            if (digit & 128) == 0:
                break
        if packet_type == 2:
            return ConnectAcknowledgement(flags, size, stream)
        if packet_type == 3:
            return PublishNotification(flags, size, stream)
        if packet_type == 9:
            return SubscribeAcknowledgement(flags, size, stream)
        if packet_type == 13:
            return PingResponse(flags, size)
        raise NotImplementedError('packet type ' + str(packet_type) + ' not implemented')

    @staticmethod
    def _read_byte(stream):
        return stream.read(1)[0]

    @staticmethod
    def _read_short(stream):
        short = stream.read(2)
        return (short[0] << 8) + short[1]

    @staticmethod
    def _read_string(stream, size):
        return str(stream.read(size), 'ascii')

class ConnectAcknowledgement(AbstractResponse):

    def __init__(self, flags, size, stream):
        if size != 2:
            raise ValueError('size was ' + str(size))
        super().__init__(flags, size)
        self.session_present = AbstractResponse._read_byte(stream)
        self.return_code = AbstractResponse._read_byte(stream)

    def connection_accepted(self):
        return self.return_code == 0

class SubscribeAcknowledgement(AbstractResponse):

    def __init__(self, flags, size, stream):
        if size != 3:
            raise ValueError('size was ' + str(size))
        super().__init__(flags, size)
        self.packet_id = AbstractResponse._read_short(stream)
        self.return_code = AbstractResponse._read_byte(stream)

    def has_packet_id(self, packet_id):
        return self.packet_id == packet_id

    def subscription_accepted(self):
        return self.return_code != 128

class PublishNotification(AbstractResponse):

    def __init__(self, flags, size, stream):
        super().__init__(flags, size)
        topic_length = AbstractResponse._read_short(stream)
        self.topic = AbstractResponse._read_string(stream, topic_length)
        if (flags & 6) > 0:
            self.packet_id = AbstractResponse._read_short(stream)
            self.payload = AbstractResponse._read_string(stream, size - topic_length - 4)
        else:
            self.packet_id = None
            self.payload = AbstractResponse._read_string(stream, size - topic_length - 2)

    def get_packet_id(self):
        return self.packet_id

    def has_topic(self, topic):
        return self.topic == topic

class PingResponse(AbstractResponse):

    def __init__(self, flags, size):
        if size != 0:
            raise ValueError('size was ' + str(size))
        super().__init__(flags, size)
