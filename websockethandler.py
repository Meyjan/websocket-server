# Imports
import sys
import struct
from base64 import b64encode
from hashlib import sha1
import errno
from socketserver import StreamRequestHandler

# First byte
FIN    = 0x80               # 1000 0000
RSV    = 0x70               # 0111 0000
OPCODE = 0x0f               # 0000 1111
# Second byte
MASKED = 0x80               # 1000 0000
PAYLOAD_LEN = 0x7f          # 0111 1111
# Extra payload length
PAYLOAD_LEN_EXT16 = 0x7e    # Checking if payload = 126
PAYLOAD_LEN_EXT64 = 0x7f    # Checking if payload = 127

OPCODE_CONTINUATION = 0x0
OPCODE_TEXT         = 0x1
OPCODE_BINARY       = 0x2
OPCODE_CLOSE_CONN   = 0x8
OPCODE_PING         = 0x9
OPCODE_PONG         = 0xA


class WebSocketHandler(StreamRequestHandler):
    def __init__(self, socket, addr, server):
        self.server = server
        StreamRequestHandler.__init__(self, socket, addr, server)

    def setup(self):
        StreamRequestHandler.setup(self)
        self.keep_alive = True
        self.handshake_done = False
        self.valid_client = False

    def handle(self):
        while self.keep_alive:
            if not self.handshake_done:
                self.handshake()
            elif self.valid_client:
                self.read_next()

    def read_bytes(self, num):
        return self.rfile.read(num)
    
    def read_next(self):
        print("Read next called")
        message_buffer = bytearray()

        try:
            byte1, byte2 = self.read_bytes(2)
        except ConnectionResetError as err:
            if err.errno == errno.ECONNRESET:
                print("Error connection reset")
                self.keep_alive = 0
                return
            byte1, byte2 = 0, 0
        except ValueError as err:
            byte1, byte2 = 0, 0

        fin = byte1 & FIN
        rsv = byte1 & RSV
        opc = byte1 & OPCODE
        mask = byte2 & MASKED
        length = byte2 & PAYLOAD_LEN

        if opc == OPCODE_CLOSE_CONN:
            print("Connection to handler ended. Detected FIN OPCODE_CLOSSCONN")
            self.keep_alive = False
            return

        if not mask:
            print("Client is not masked. Ending connection to the handler")
            self.send(bytes(encode_to_UTF8("1002")), OPCODE_CLOSE_CONN)
            self.keep_alive = False
            return
        
        if opc == OPCODE_CONTINUATION:
            # Do nothing... Cuz why not? It depends on the first opcode
            print("Continued frame")
            return
        elif opc == OPCODE_TEXT:
            print("Text detected")
            handler = self.server._message_received_
        elif opc == OPCODE_BINARY:
            print("Binary detected")
            handler = self.server._file_received_
        elif opc == OPCODE_PING:
            print("PING")
            handler = self.server._ping_received_
        elif opc == OPCODE_PONG:
            print("PONG")
            handler = self.server._pong_received_
        else:
            print("Invalid opcode. Ending connection to the handler")
            self.keep_alive = False
            return

        if length == 126:
            length = struct.unpack(">H", self.rfile.read(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self.rfile.read(8))[0]
        
        masks = self.read_bytes(4)
        message = bytearray()
 
        for message_byte in self.read_bytes(length):
            message_byte ^= masks[len(message) % 4]
            message.append(message_byte)
        
        print("fin =", fin)
        print("opc =", opc)

        print("Try calling handler")
        try:
            handler(self, message.decode("utf-8"))
        except Exception as err:
            handler(self, message)
        
    def send_message(self, message):
        print("Message sending:", message)
        self.send(bytes(encode_to_UTF8(message)), OPCODE_TEXT)

    def send_pong(self, message):
        print("Pong sending:", message)
        self.send(bytes(encode_to_UTF8(message)), OPCODE_PONG)
    
    def send_file(self, fileName, opcode=OPCODE_BINARY):
        print("File name =", fileName)
        first_frame = True
        last_frame = False
        bigfile = open(fileName, "rb")
        temp_msg = bigfile.read()
        bigfile.close()

        self.send(temp_msg, OPCODE_BINARY)

    def send(self, message, opcode=OPCODE_TEXT, fin = 0x80):
        payload = message
        header  = bytearray()
        payload_length = len(payload)

        if payload_length <= 125:
            header.append(fin | opcode)
            header.append(payload_length)
        elif payload_length >= 126 and payload_length <= 65535:
            header.append(fin | opcode)
            header.append(PAYLOAD_LEN_EXT16)
            header.extend(struct.pack(">H", payload_length))
        elif payload_length < 18446744073709551616:
            header.append(fin | opcode)
            header.append(PAYLOAD_LEN_EXT64)
            header.extend(struct.pack(">Q", payload_length))
        else:
            print("Unable to send package because too large")
            return
        
        print(header)
        print(payload)
        
        self.request.send(header + payload)

    def read_http_headers(self):
        headers = {}
        http_get = self.rfile.readline().decode().strip()
        assert http_get.upper().startswith('GET')
        while True:
            header = self.rfile.readline().decode().strip()
            if not header:
                break
            head, value = header.split(':', 1)
            headers[head.lower().strip()] = value.strip()
        return headers

    def handshake(self):
        headers = self.read_http_headers()

        try:
            assert headers['upgrade'].lower() == 'websocket'
        except AssertionError:
            print("Header is not websocket")
            self.keep_alive = False
            return

        try:
            key = headers['sec-websocket-key']
        except KeyError:
            print("Client tried to connect but was missing a key")
            self.keep_alive = False
            return

        response = self.make_handshake_response(key)
        self.handshake_done = self.request.send(response.encode())
        self.valid_client = True
        self.server._new_client_(self)

    @classmethod
    def make_handshake_response(cls, key):
        return \
          'HTTP/1.1 101 Switching Protocols\r\n'\
          'Upgrade: websocket\r\n'              \
          'Connection: Upgrade\r\n'             \
          'Sec-WebSocket-Accept: %s\r\n'        \
          '\r\n' % cls.calculate_response_key(key)

    @classmethod
    def calculate_response_key(cls, key):
        GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
        hash = sha1(key.encode() + GUID.encode())
        response_key = b64encode(hash.digest()).strip()
        return response_key.decode('ASCII')

    def finish(self):
        self.server._client_left_(self)


def encode_to_UTF8(data):
    try:
        return data.encode('UTF-8')
    except UnicodeEncodeError as e:
        print("Could not encode data to UTF-8 -- %s" % e)
        return False
    except Exception as e:
        raise(e)
        return False