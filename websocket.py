from websockethandler import WebSocketHandler
from socketserver import ThreadingMixIn, TCPServer
import hashlib
import os

class WebSocket(ThreadingMixIn, TCPServer):
    clients = []
    id_counter = 0

    def __init__(self, addr=('0.0.0.0', 9001)):
        TCPServer.__init__(self, addr, WebSocketHandler)
        self.port = self.socket.getsockname()[1]

        bigfile = open("test.zip", "rb")
        temp_msg = bigfile.read()
        self.file_read = temp_msg
        self.file_length = len(temp_msg)
        self.hash_md5 = hashlib.md5(temp_msg).hexdigest()
        bigfile.close()
        print(self.file_length)

    def run(self):
        try:
            print("Server start running")
            self.serve_forever()
        except KeyboardInterrupt:
            self.server_close()
            print("Keyboard interrupt")
        except Exception as err:
            print(str(err))
            exit(1)
    
    def send_message(self, to_client, msg):
        to_client['handler'].send_message(msg)
    
    def _message_received_(self, handler, msg):
        listOfString = self.parse_message(msg)
        print(listOfString[0])
        if(listOfString[0] == "!echo"):
            listOfString.pop(0)
            self.send_message(self.handler_to_client(handler), " ".join(listOfString))
        elif(listOfString[0] == "!submission"):
            self.handler_to_client(handler)['handler'].send_file(self.file_read)

    def _file_received_(self, handler, msg):
        print("File received")
        hash_md5_1 = self.hash_md5
        hash_md5_2 = hashlib.md5(msg).hexdigest()
        if(hash_md5_1 == hash_md5_2):
            self.send_message(self.handler_to_client(handler), "1")
        else:
            self.send_message(self.handler_to_client(handler), "0")
    
    def parse_message(self, msg):
        listOfString = msg.split(' ')
        return listOfString

    def _ping_received_(self, handler, msg):
        handler.send_pong(msg)

    def _pong_received_(self, handler, msg):
        pass

    def _new_client_(self, handler):
        self.id_counter += 1
        client = {
            'id': self.id_counter,
            'handler': handler,
            'address': handler.client_address
        }
        self.clients.append(client)
        print("New client connected and was given id %d" % client['id'])

    def _client_left_(self, handler):
        client = self.handler_to_client(handler)
        print("Client(%d) disconnected" % client['id'])
        if client in self.clients:
            self.clients.remove(client)
        
    def handler_to_client(self, handler):
        for client in self.clients:
            if client['handler'] == handler:
                return client


PORT = 9001
HOST = '0.0.0.0'
addr = (HOST, PORT)

server = WebSocket(addr)
print("WebSocket is ready to use...")
server.run()