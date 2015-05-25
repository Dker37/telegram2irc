#!/usr/bin/env python3
import json
import pprint
from socket import socket, AF_INET, SOCK_STREAM
from collections import namedtuple
from imgur import Imgur


TeleMessage = namedtuple(
    'TeleMessage',
    ('user_id', 'username', 'chat_id', 'content')
)

PhotoContext = namedtuple(
    'PhotoContext',
    ('user_id', 'username', 'chat_id', 'photo_id')
)


class InvalidMessage(Exception):
    pass


class Telegram(object):
    def __init__(self, ip_addr='127.0.0.1', port='4444', imgur_client_id=None):
        self._socket_init(ip_addr, port)
        self.main_session()
        self.imgur = Imgur(imgur_client_id) \
            if imgur_client_id is not None else None
        self.photo_context = None  # PhotoContext if not None

    def __del__(self):
        self.sock.close()

    def _socket_init(self, ip_addr, port):
        s = socket(AF_INET, SOCK_STREAM)
        s.connect((ip_addr, port))
        self.sock = s

    def send_cmd(self, cmd):
        if '\n' != cmd[-1]:
            cmd += '\n'
        self.sock.send(cmd.encode())

    def main_session(self):
        self.send_cmd('main_session')

    def send_msg(self, peer, msg):
        peer = peer.replace(' ', '_')
        cmd = 'msg ' + peer + ' ' + msg
        self.send_cmd(cmd)

    def send_user_msg(self, userid, msg):
        peer = 'user#' + userid
        self.send_msg(peer, msg)

    def send_chat_msg(self, chatid, msg):
        peer = 'chat#' + chatid
        self.send_msg(peer, msg)

    def download_photo(self, msg_id):
        self.send_cmd("load_photo" + ' ' + str(msg_id))

    def parse_msg(self, jmsg):
        """Parse message.

        Returns:
            TeleMessage(user_id, username, chat_id, content) if jmsg is normal
            None if else.
        """
        mtype = jmsg.get('event', None)

        if mtype == "message":
            from_info = jmsg["from"]
            user_id, username = from_info["id"], from_info.get("username", "")

            to_info = jmsg["to"]
            chat_id = to_info["id"] if to_info["type"] == "chat" else None

            if "text" not in jmsg:
                media_type = jmsg.get("media", {}).get("type", None)
                if media_type == "photo":
                    photo_id = jmsg["id"]
                    content = "[photo {}]".format(photo_id)
                    if self.imgur is not None:
                        self.download_photo(photo_id)
                        self.photo_context = \
                            PhotoContext(user_id, username, chat_id, photo_id)
                else:
                    content = "[{}]".format(media_type)
            else:
                content = jmsg["text"]

            return TeleMessage(
                user_id=user_id, username=username,
                chat_id=chat_id, content=content)

        elif mtype == "download":
            # should be `{'result': '/paht/to/image.jpg', 'type': 'download'}`
            filename = jmsg.get("result", None)
            if filename is None:
                return None
            if self.photo_context is None:
                return None

            url = self.imgur.upload_image(filename)
            if url is None:
                return None

            ctx = self.photo_context
            self.photo_context = None

            return TeleMessage(
                user_id=ctx.user_id,
                username=ctx.username,
                chat_id=ctx.chat_id,
                content="{} (photo {})".format(url, ctx.photo_id)
            )

        return None

    def recv_header(self):
        """Receive and parse message head like `ANSWER XXX\n`

        Returns:
            next message size
        """

        # states = ("ANS", "NUM")
        state = "ANS"
        ans = b""
        size = b""
        while 1:
            r = self.sock.recv(1)
            if state == "ANS":
                if r == b" " and ans == b"ANSWER":
                    state = "NUM"
                else:
                    ans = ans + r
            elif state == "NUM":
                if r == b"\n":
                    break
                else:
                    size = size + r

        return int(size) + 1

    def recv_one_msg(self):
        """Receive one message.

        Returns:
            -1 if connection is closed.
            (time, chatID, userID, content) if normal.
        """
        while True:
            buf_size = self.recv_header()

            ret = self.sock.recv(buf_size)

            if '' == ret:
                return -1

            if ret[-2:] != b"\n\n":
                print("Error: buffer receive failed")
                return -1

            try:
                jmsg = json.loads(ret[:-2].decode("utf-8"))
            except ValueError:
                print("Error parsing: ", ret[:-2])
                return None
            # pprint.pprint(msg)
            return self.parse_msg(jmsg)


if __name__ == '__main__':
    tele = Telegram('127.0.0.1', 1235)
    # tele.send_msg('user#67655173', 'hello')
    while True:
        ret = tele.recv_one_msg()
        if ret == -1:
            print('Connect closed')
            break
        else:
            print(ret)
    tele = None
