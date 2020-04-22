import network
import usocket
import uselect
import ujson
import mqtt

class MQTTClient:

    def __init__(self, tasks, hostname = 'simplysomethings.de', client_id = '', user_name = '', password = ''):
        self.tasks = tasks
        self.hostname = hostname
        self.client_id = client_id
        self.user_name = user_name
        self.password = password
        self.broker = None
        self.stream = None
        self.topic_listeners = []
        self.connected = False

    def is_connected(self):
        return self.connected

    def subscribe(self, topic, listener):
        self.topic_listeners.append((topic, listener))

    def publish(self, topic, payload_object, retain = True, timeout = 60000):
        payload = ujson.dumps(payload_object)
        self.tasks.only_one_of(self.tasks.when_then(lambda : self.connected, lambda : self._publish(topic, payload, retain)),
                               self.tasks.after(timeout, lambda : None))

    def activate_wlan(self, ssid_passwords):
        self.ssid_passwords = ssid_passwords
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.wlan.config(dhcp_hostname = self.user_name)

    def start(self):
        self.tasks.now(lambda : self._connect_wlan())

    def _connect_wlan(self):
        try:
            access_points = self.wlan.scan()
            for ssid_password in self.ssid_passwords:
                ssid = ssid_password[0]
                for access_point in access_points:
                    if access_point[0] == bytes(ssid, 'ascii'):
                        self.wlan.connect(ssid, ssid_password[1])
                        self.tasks.after(3000, lambda : self._create_socket())
                        return
        except Exception:
            pass
        self.tasks.after(30000, lambda : self._connect_wlan())

    def _create_socket(self):
        try:
            self.broker = usocket.socket()
            self.broker.connect(usocket.getaddrinfo(self.hostname, 1883)[0][-1])
            self.stream = self.broker.makefile('rwb')
            self.tasks.now(lambda : self._send_connect())
        except Exception:
            self.tasks.after(30000, lambda : self._connect_wlan())

    def _send_connect(self):
        try:
            mqtt.ConnectRequest(self.client_id, self.user_name, self.password).write_to(self.stream)
            self.tasks.only_one_of(self.tasks.when_then(lambda : self._can_read_socket(), lambda : self._acknowledge_connect()),
                                   self.tasks.after(3000, lambda : self._close_socket()))
        except Exception:
            self.tasks.now(lambda : self._close_socket())

    def _can_read_socket(self):
        try:
            poll = uselect.poll()
            poll.register(self.broker, uselect.POLLIN)
            return len(poll.poll(0)) > 0
        except Exception:
            return False

    def _acknowledge_connect(self):
        try:
            if mqtt.AbstractResponse.receive_from(self.stream).connection_accepted():
                self.connected = True
                self.tasks.now(lambda : self._subscribe())
                return
        except Exception:
            pass
        self.tasks.now(lambda : self._close_socket())

    def _subscribe(self):
        try:
            packet_id = 1
            for topic_listener in self.topic_listeners:
                mqtt.SubscribeRequest(packet_id, topic_listener[0], qos = 1).write_to(self.stream)
                packet_id += 1
            self.tasks.only_one_of(self.tasks.when_then(lambda : self._can_read_socket(), lambda : self._receive()),
                                   self.tasks.after(3000, lambda : self._close_socket()))
        except Exception:
            self.tasks.now(lambda : self._close_socket())

    def _receive(self):
        try:
            response = mqtt.AbstractResponse.receive_from(self.stream)
            response_type = type(response)
            if response_type is mqtt.SubscribeAcknowledgement:
                pass  # Todo prüfen, ob alle Subscriptions bestätigt wurden
            elif response_type is mqtt.PingResponse:
                pass
            elif response_type is mqtt.PublishNotification:
                packet_id = response.get_packet_id()
                if packet_id is not None:
                    self.tasks.now(lambda : self._acknowledge_publish(packet_id), priority = 1)
                for topic_listener in self.topic_listeners:
                    if response.has_topic(topic_listener[0]):
                        topic_listener[1](response.topic, ujson.loads(response.payload) if len(response.payload) > 0 else None)
                        break
            else:
                self.tasks.now(lambda : self._close_socket())
                return
            self.tasks.only_one_of(self.tasks.when_then(lambda : self._can_read_socket(), lambda : self._receive()),
                                   self.tasks.after(120000, lambda : self._ping()))
        except Exception:
            self.tasks.now(lambda : self._close_socket())

    def _acknowledge_publish(self, packet_id):
        try:
            mqtt.PublishAcknowledgement(packet_id).write_to(self.stream)
        except Exception:
            pass

    def _ping(self):
        try:
            mqtt.PingRequest().write_to(self.stream)
            self.tasks.only_one_of(self.tasks.when_then(lambda : self._can_read_socket(), lambda : self._receive()),
                                   self.tasks.after(30000, lambda : self._close_socket()))
        except Exception:
            self.tasks.now(lambda : self._close_socket())

    def _publish(self, topic, payload, retain):
        try:
            mqtt.PublishRequest(topic, payload, retain = retain).write_to(self.stream)
        except Exception:
            pass

    def _close_socket(self):
        try:
            self.broker.close()
        except Exception:
            pass
        self.broker = None
        self.stream = None
        self.connected = False
        self.tasks.after(30000, lambda : self._create_socket())
