__author__ = 'yardeneitan'

import select, socket, sys, pdb
from chat_util import Hall, Room, User
import chat_util

READ_BUFFER = 4096

host = sys.argv[1] if len(sys.argv) >= 2 else '0.0.0.0'
listen_sock = chat_util.create_socket((host, chat_util.PORT))
sqliteconn, curs = chat_util.create_sqlite()
emojis = chat_util.load_and_parse_emojis_json()

hall = Hall()
hall.dbConn = sqliteconn
hall.dbCursor = curs
hall.emojis = emojis

connection_list = [listen_sock]

def close_connection(user):
    user.socket.close()
    connection_list.remove(user)

while True:
    read_users, write_users, error_sockets = select.select(connection_list, [], [])
    for usr in read_users:
        if usr is listen_sock: # new connection, usr is a socket
            new_socket, add = usr.accept()
            new_usr = User(new_socket)
            connection_list.append(new_usr)
            hall.welcome_new(new_usr)

        else: # new message
            print usr.name
            msg = usr.socket.recv(READ_BUFFER)
            print msg
            if msg:
                try:
                    msg = msg.decode().lower().strip()
                    hall.handle_msg(usr, msg)

                    if msg == '/quit':
                        close_connection(usr)
                except UnicodeDecodeError:
                    close_connection(usr)
            else:
                close_connection(usr)


    for sock in error_sockets: # close error sockets
        sock.close()
        connection_list.remove(sock)