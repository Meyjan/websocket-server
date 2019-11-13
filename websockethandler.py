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
        self.connectionAlive = True
        self.doHandshake = False
        self.approvedClient = False

    def handle(self):
        buffer = bytearray()
        waiting = False
        command = OPCODE_BINARY
        handler = self.server.receiving_file
        remainingLength = 0
        mask = 0

        while self.connectionAlive:
            if not self.doHandshake:
                self.handshake()
            elif self.approvedClient:
                if (not waiting):
                    response = self.read_next()
                    print(response)
                    if (response[0] == True):
                        if (response[1] == OPCODE_BINARY):
                            response[3](self, response[2])
                        else:
                            response[3](self, response[2].decode("utf-8"))
                    else:
                        waiting = True
                        buffer.extend(response[2])
                        command = response[1]
                        handler = response[3]
                        remainingLength = response[4]
                        mask = response[5]
                else:
                    print(waiting)
                    response = self.read_continuation(remainingLength)
                    buffer.extend(response)
                    
                    if (command == OPCODE_BINARY):
                        handler(self, buffer)
                    else:
                        handler(self, buffer.decode("utf-8"))
                    waiting = False 

    def read_bytes(self, num):
        return self.rfile.read(num)

    def read_continuation(self, length, mask):
        message = bytearray()
        for messageByte in self.read_bytes(length):
            messageByte ^= mask[len(message) % 4]
            message.append(messageByte)
        return message
    
    def read_next(self):
        try:
            byte1, byte2 = self.read_bytes(2)
        except ConnectionResetError as err:
            if err.errno == errno.ECONNRESET:
                print("Error connection reset")
                self.connectionAlive = 0
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
            self.connectionAlive = False
            return

        if not mask:
            self.connectionAlive = False
            return

        if fin == 0:
            print("Fin = 0")
            return
        
        if opc == OPCODE_CONTINUATION:
            # Do nothing because it depends on the first opcode
            return
        elif opc == OPCODE_TEXT:
            handler = self.server.receiving_message
        elif opc == OPCODE_BINARY:
            handler = self.server.receiving_file
        elif opc == OPCODE_PING:
            handler = self.server.receiving_ping
        elif opc == OPCODE_PONG:
            return
        else:
            self.connectionAlive = False
            return
        
        print("opc =", opc)
        print("length = ", length)

        if length == 126:
            length = struct.unpack(">H", self.rfile.read(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self.rfile.read(8))[0]
        
        masks = self.read_bytes(4)
        message = bytearray()
 
        for messageByte in self.read_bytes(length):
            messageByte ^= masks[len(message) % 4]
            message.append(messageByte)
        
        print("length = ", length)
        print("message length = ", len(message))

        if (length == len(message)):
            return (True, opc, message, handler)
        else:
            return (False, opc, message, handler, (length  - len(message)), masks)

        
    def send_message(self, message):
        print("Message sending:", message)
        self.send(bytes(message.encode('UTF-8')), OPCODE_TEXT)

    def send_pong(self, message):
        print("Pong sending:", message)
        self.send(bytes(message.encode('UTF-8')), OPCODE_PONG)
    
    def send_file(self, message, opcode=OPCODE_BINARY):
        self.send(message, opcode)

    def send(self, message, opcode=OPCODE_TEXT, fin = 0x80):
        payload = message
        header  = bytearray()
        lengthPayload = len(payload)

        if lengthPayload <= 125:
            header.append(fin | opcode)
            header.append(lengthPayload)
        elif lengthPayload >= 126 and lengthPayload <= 65535:
            header.append(fin | opcode)
            header.append(PAYLOAD_LEN_EXT16)
            header.extend(struct.pack(">H", lengthPayload))
        elif lengthPayload < 18446744073709551616:
            header.append(fin | opcode)
            header.append(PAYLOAD_LEN_EXT64)
            header.extend(struct.pack(">Q", lengthPayload))
        else:
            print("Unable to send package because too large")
            return
        
        print("opc=", opcode)
        
        self.request.send(header + payload)

    def read_http_headers(self):
        headers = {}
        httpGet = self.rfile.readline().decode().strip()
        assert httpGet.upper().startswith('GET')
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
            self.connectionAlive = False
            return

        try:
            key = headers['sec-websocket-key']
        except KeyError:
            print("Client tried to connect but was missing a key")
            self.connectionAlive = False
            return

        response = self.create_response_handshake(key)
        self.doHandshake = self.request.send(response.encode())
        self.approvedClient = True
        self.server.handle_new_client(self)
    
    def create_response_handshake(self, key):
        return \
          'HTTP/1.1 101 Switching Protocols\r\n'\
          'Upgrade: websocket\r\n'              \
          'Connection: Upgrade\r\n'             \
          'Sec-WebSocket-Accept: %s\r\n'        \
          '\r\n' % self.calculate_response_accept(key)

    def calculate_response_accept(self, key):
        GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
        hash = sha1(key.encode() + GUID.encode())
        responseKey = b64encode(hash.digest()).strip()
        return responseKey.decode('ASCII')

    def finish(self):
        self.server.handle_client_left(self)