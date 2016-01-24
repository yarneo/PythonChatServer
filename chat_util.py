__author__ = 'yardeneitan'

import socket, pdb, sqlite3, os, ssl
import json
import random

MAX_CLIENTS = 30
PORT = 12345

def load_and_parse_emojis_json():
    emojis = {}
    with open('emojis.json') as data_file:
        data = json.load(data_file)
    for obj in data['list']:
        if 'tag' in obj and 'yan' in obj:
            for tag in obj['tag'].split():
                emojis[tag] = obj['yan']
    return emojis

def create_sqlite():
    db_filename = 'chat.db'
    sqliteconn = sqlite3.connect(db_filename)
    db_is_new = not os.path.exists(db_filename)
    c = sqliteconn.cursor()
    #
    # if db_is_new:
    #     print 'Need to create schema'
    #     # Create table
    c.execute('''CREATE TABLE IF NOT EXISTS chatusers (username TEXT, password TEXT)''')
    # else:
    #     print 'Database exists, assume schema does, too.'

    return sqliteconn, c

def create_socket(address):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setblocking(0)
    s.bind(address)
    s.listen(MAX_CLIENTS)
    wrapped_socket = ssl.wrap_socket(s, server_side=True, certfile="cert", keyfile="key")

    print("Now listening at ", address)
    return wrapped_socket

class Hall:
    def __init__(self):
        self.rooms = {} # {room_name: Room}
        self.room_user_map = {} # {userName: roomName}
        self.dbConn = None
        self.dbCursor = None
        self.users = []
        self.emojis = None

    def welcome_new(self, new_user):
        new_user.socket.sendall("Welcome to the coolest chat server on earth!\n")
        new_user.socket.sendall("What's your login name?\n")

    def list_rooms(self, user):

        if len(self.rooms) == 0:
            msg = 'Oops, no active rooms currently. Create your own!\n' \
                + 'Use /join room_name to create a room.\n'
            user.socket.sendall(msg.encode())
        else:
            msg = 'Active rooms are:\n'
            for room in self.rooms:
                msg += " * " + room + "(" + str(len(self.rooms[room].users)) + ") user(s)\n"
            msg += 'end of list.\n'
            user.socket.sendall(msg.encode())

    def handle_msg(self, user, msg):
        print(user.name + " says: " + msg)

        instructions = b'Instructions:\n'\
            + b'/rooms to list all rooms\n'\
            + b'/join room_name to join/create/switch to a room\n' \
            + b'/leave to leave a room\n' \
            + b'/pm name message -- to send a private message to name\n' \
            + b'/emojis to see list of emoji tags, and -- /emoji tag -- to send one\n' \
            + b'/help to show instructions\n' \
            + b'/quit to quit\n' \
            + b'Otherwise start typing and enjoy!' \
            + b'\n'

        if not user.is_logged_in:
            if not user.has_entered_username:
                name = msg
                user.name = name
                print("New connection from:", user.name)
                t = (name,)
                self.dbCursor.execute('SELECT * FROM chatusers WHERE username=?', t)
                entry = self.dbCursor.fetchone()
                print entry
                if entry is not None and len(entry) == 2:
                    user.password = entry[1]
                    user.socket.sendall("Name entered is already in use. What is the password?\n")
                else:
                    user.socket.sendall("New user! Please enter a password?\n")

                user.has_entered_username = True
            else:
                password = msg
                if user.password is None:
                    user.password = password
                    params = (user.name, user.password)
                    self.dbCursor.execute("INSERT INTO chatusers VALUES (?, ?)", params)
                    self.dbConn.commit()
                    user.is_logged_in = True
                    user.socket.sendall("Welcome %s!" % user.name)
                    user.socket.sendall(instructions)
                    self.users.append(user)
                else:
                    if user.password != password:
                        user.has_entered_username = False
                        user.password = None
                        user.socket.sendall("Wrong Password. Please try again.\n")
                        user.socket.sendall("What's your login name?\n")
                    else:
                        user.is_logged_in = True
                        user.socket.sendall("Welcome %s!\n" % user.name)
                        user.socket.sendall(instructions)
                        self.users.append(user)
            return


        if msg.startswith("/join"):
            same_room = False
            if len(msg.split()) >= 2: # error check
                room_name = msg.split()[1]
                if user.name in self.room_user_map: # switching?
                    if self.room_user_map[user.name] == room_name:
                        user.socket.sendall(b'You are already in room: ' + room_name.encode())
                        same_room = True
                    else: # switch
                        old_room = self.room_user_map[user.name]
                        self.rooms[old_room].remove_user(user)
                if not same_room:
                    if not room_name in self.rooms: # new room:
                        new_room = Room(room_name)
                        self.rooms[room_name] = new_room
                    self.rooms[room_name].users.append(user)
                    self.rooms[room_name].welcome_new(user)
                    self.room_user_map[user.name] = room_name
            else:
                user.socket.sendall(instructions)

        elif msg.startswith("/pm"):
            user_exists = None
            if len(msg.split()) >= 3: # error check
                send_to_name = msg.split()[1]
                for usr in self.users:
                    if usr.name == send_to_name:
                        user_exists = usr
                        break

                if user_exists is not None:
                    message = " ".join(msg.split()[2:])
                    message = user.name.encode() + b" sends you a private message: " + message + '\n'
                    user_exists.socket.sendall(message)
                else:
                    user.socket.sendall(b'No such user in the server\n')

        elif msg == "/leave":
            if user.name in self.room_user_map:
                current_room = self.room_user_map[user.name]
                self.rooms[current_room].remove_user(user)
                del self.room_user_map[user.name]
            else:
                msg = 'You are currently not in any room! \n' \
                    + 'Use /rooms to see available rooms! \n' \
                    + 'Use /join room_name to join a room! \n'
                user.socket.sendall(msg.encode())

        elif msg == "/rooms":
            self.list_rooms(user)

        elif msg == "/help":
            user.socket.sendall(instructions)

        elif msg == "/quit":
            user.socket.sendall("BYE\n")
            user.should_quit = True
            self.remove_user(user)

        elif msg == "/emojis":
            msg = "Here are the list of tags:\n"
            for key,value in self.emojis.iteritems():
                msg += key.encode('utf-8').strip() + "\n"
            msg += "To send an emoji, write: /emoji <tag>\n"
            user.socket.sendall(msg)

        elif msg.startswith("/emoji"):
            if len(msg.split()) >= 2: # error check
                tag = msg.split()[1]
                if tag in self.emojis:
                    if user.name in self.room_user_map:
                        msg = random.choice(self.emojis[tag])
                        self.rooms[self.room_user_map[user.name]].broadcast(user, msg.encode('utf-8'))

        else:
            # check if in a room or not first
            if user.name in self.room_user_map:
                self.rooms[self.room_user_map[user.name]].broadcast(user, msg.encode())
            else:
                msg = 'You are currently not in any room! \n' \
                    + 'Use /rooms to see available rooms! \n' \
                    + 'Use /join room_name to join a room! \n'
                user.socket.sendall(msg.encode())

    def remove_user(self, user):
        if user.name in self.room_user_map:
            self.rooms[self.room_user_map[user.name]].remove_user(user)
            del self.room_user_map[user.name]
        if user in self.users:
            self.users.remove(user)

        print("User: " + user.name + " has left\n")


class Room:
    def __init__(self, name):
        self.users = [] # a list of sockets
        self.name = name

    def welcome_new(self, from_user):

        msg = "* new user joined chat: " + from_user.name + "\n"
        own_user_msg = "entering room: " + self.name + "\n"
        for usr in self.users:
            if usr == from_user:
                own_user_msg += " * " + usr.name +  " (** this is you)\n"
            else:
                own_user_msg += " * " + usr.name +  "\n"
                usr.socket.sendall(msg.encode())
        own_user_msg += "end of list.\n"
        from_user.socket.sendall(own_user_msg.encode())


    def broadcast(self, from_user, msg):
        msg = from_user.name.encode() + b":" + msg + '\n'
        for usr in self.users:
            usr.socket.sendall(msg)

    def remove_user(self, from_user):
        leave_msg = "* user user has left chat: " + from_user.name
        for usr in self.users:
            if usr == from_user:
                usr.socket.sendall(leave_msg + " (** this is you)\n")
            else:
                usr.socket.sendall(leave_msg + "\n")
        self.users.remove(from_user)

class User:
    def __init__(self, socket, name = "new"):
        socket.setblocking(0)
        self.socket = socket
        self.name = name
        self.is_logged_in = False
        self.has_entered_username = False
        self.password = None
        self.should_quit = False

    def fileno(self):
        return self.socket.fileno()