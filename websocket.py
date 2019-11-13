from websockethandler import WebSocketHandler
from socketserver import ThreadingMixIn, TCPServer
import hashlib
import os

class WebSocket(ThreadingMixIn, TCPServer):
    clients = []
    idCounter = 0

    def __init__(self, addr=('0.0.0.0', 9001)):
        TCPServer.__init__(self, addr, WebSocketHandler)
        self.port = self.socket.getsockname()[1]

        bigfile = open("test.zip", "rb")
        tempMsg = bigfile.read()
        self.fileRead = tempMsg
        self.fileLength = len(tempMsg)
        self.hashMD5 = hashlib.md5(tempMsg).hexdigest()
        bigfile.close()
        print(self.fileLength)

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
    
    def sending_message(self, client, msg):
        client['handler'].send_message(msg)
    
    def receiving_message(self, handler, msg):
        listOfString = self.parse_message(msg)
        print(listOfString[0])
        if(listOfString[0] == "!echo"):
            listOfString.pop(0)
            self.sending_message(self.client_handler(handler), " ".join(listOfString))
        elif(listOfString[0] == "!submission"):
            self.client_handler(handler)['handler'].send_file(self.fileRead)

    def receiving_file(self, handler, msg):
        print("File received")  
        hashed = hashlib.md5(msg).hexdigest()
        if(self.hashMD5 == hashed):
            self.sending_message(self.client_handler(handler), "1")
        else:
            self.sending_message(self.client_handler(handler), "0")
    
    def parse_message(self, msg):
        listOfString = msg.split(' ')
        return listOfString

    def receiving_ping(self, handler, msg):
        handler.send_pong(msg)

    def handle_new_client(self, handler):
        self.idCounter += 1
        client = {
            'id': self.idCounter,
            'handler': handler,
            'address': handler.client_address
        }
        self.clients.append(client)
        print("New client connected and was given id %d" % client['id'])

    def handle_client_left(self, handler):
        client = self.client_handler(handler)
        print("Client(%d) disconnected" % client['id'])
        if client in self.clients:
            self.clients.remove(client)
        
    def client_handler(self, handler):
        for client in self.clients:
            if client['handler'] == handler:
                return client


PORT = 9001
HOST = '0.0.0.0'
addr = (HOST, PORT)

server = WebSocket(addr)
print("WebSocket is ready to use...")
server.run()