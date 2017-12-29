#!/usr/bin/env python3

from threading import Thread
import traceback
import os
import cherrypy
import subprocess
from base64 import b64encode
from ws4py.server.cherrypyserver import WebSocketPlugin, WebSocketTool
from ws4py.websocket import EchoWebSocket
from time import sleep, time


INTERVAL = 2
cherrypy.config.update({'server.socket_port': 3000,
                        'server.socket_host': "0.0.0.0"})
WebSocketPlugin(cherrypy.engine).subscribe()
cherrypy.tools.websocket = WebSocketTool()


class CatHandler(Thread):
    def __init__(self, master):
        """
        Run the image creator subprocess. Every X seconds, delete all images but the newest one
        """
        super().__init__()
        self.master = master
        self.proc = None
        self.start()

    def run(self):
        compressed = ""
        self.startproc()
        while True:
            if time() - self.proctime > 15 * 60:  # restart proc every 15 minutes
                self.stopproc()
                self.startproc()
            start = time()
            images = sorted([i.name for i in os.scandir("images")])  # newer images towards end
            if images:
                for imname in images[0:-1]:
                    os.unlink(os.path.join("images", imname))
                newest = os.path.join("images", images[-1])
                if newest != compressed:
                    subprocess.check_call(["convert", "-strip", "-interlace", "Plane", "-gaussian-blur", "0.05",
                                           "-quality", "50%", newest, newest])
                    compressed = newest
                with open(newest, "rb") as f:
                        self.master.latest = f.read()
                        cherrypy.engine.publish('websocket-broadcast',
                                                "data:image/jpeg;base64,{}".format(b64encode(self.master.latest).decode("ascii")))
            spent = time() - start
            sleep(max(0.2, INTERVAL - spent))

    def stopproc(self):
        if not self.proc:
            raise Exception("No proc to kill")
        self.proc.kill()
        self.proc.wait()
        self.proc = None

    def startproc(self):
        if self.proc:
            raise Exception("Proc already running!")
        # initial cleanout
        for f in os.scandir("images"):
            os.unlink(f)
        self.proc = subprocess.Popen(["imagesnap", "-t", str(INTERVAL)],
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE,
                                     cwd=os.path.join(os.path.dirname(__file__), "images"))
        self.proctime = time()


class Root(object):
    def __init__(self):
        self.latest = None
        self.cathandler = CatHandler(self)

    @cherrypy.expose
    def index(self):
        with open("page.htm") as f:
            yield f.read()

    @cherrypy.expose
    def latest_jpg(self):
        if self.latest:
            cherrypy.response.headers['Content-Type'] = 'image/jpeg'
            yield self.latest
        else:
            raise cherrypy.HTTPError(404)

    @cherrypy.expose
    def ws(self):
        # you can access the class instance through
        handler = cherrypy.request.ws_handler


def main():
    cherrypy.quickstart(Root(), '/', config={'/ws': {'tools.websocket.on': True,
                                                     'tools.websocket.handler_cls': EchoWebSocket}})


if __name__ == '__main__':
    main()

