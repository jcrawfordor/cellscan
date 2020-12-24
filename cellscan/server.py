import socket, json, argparse
from cellscan.data import db, Cellsite, Location

def __main__():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('0.0.0.0', 6402))
    sock.listen(1)

    db.connect()
    db.create_tables([Cellsite, Location])

    print("Cellscan server up")

    while True:
        conn, client = sock.accept()
        obj = recvObject(conn)
        print(f"{client}: {obj}")

        if obj['action'] == "upload":
            handleUpload(obj)

        resp = {'status': 'OK'}
        conn.sendall(json.dumps(resp).encode())
        conn.sendall(b'\x04')
        conn.close()

def recvObject(sock):
    message = b''
    while not message.endswith(b'\x04'):
        message += sock.recv(1)
    return json.loads(message[:-1].decode('UTF-8'))

def handleUpload(obj):
    device = obj['device']
    for site in obj['sites']:
        parsedSite = Cellsite(**site)
        parsedSite.save()

if __name__ == "__main__":
    __main__()