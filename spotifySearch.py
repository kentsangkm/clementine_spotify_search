#!/usr/bin/env python3
#-*- coding: UTF-8 -*-

import requests
import urllib
import re
import sys
import os
import json
from html.parser import HTMLParser
from collections import defaultdict
from urllib.parse import urlparse, parse_qs

def getKeyPress():
    def getch():
        import sys, tty, termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

    ch = getch()
    if ch == '\x1b':
        ch = getch()
        if ch == '[':
            ch = getch()
            if ch == "1": return "HOME"
            if ch == "2": return "INSERT"
            if ch == "3": return "DELETE"
            if ch == "4": return "END"
            if ch == "5": return "PAGEUP"
            if ch == "6": return "PAGEDOWN"
            if ch == "7": return "HOME"
            if ch == "8": return "END"

            if ch == "A": return "UP"
            if ch == "B": return "DOWN"
            if ch == "C": return "RIGHT"
            if ch == "D": return "LEFT"
            if ch == "F": return "END"
            if ch == "H": return "HOME"
        elif ch == '\x1b':
            return "ESC"
        raise Exception()
    elif ch == '\r':
        return "ENTER"
    elif ch == '\t':
        return "TAB"
    elif ch == '\x7f':
        return "BACKSPACE"
    elif ch == '\x03':
        exit()
    else:
        return ch if ch.isprintable() else int(ch)

def getArtistNames(items):
    keys=[]
    for item in items:
        keys.append(item["name"])
    return ", ".join(keys)

def format(format, maxLen, str):
    for c in str:
        if re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff]', c):
            maxLen -= 1
    return format.format(str, max(maxLen, 1))

class LimitedRange():
    def __init__(self, maxSize, val = 0):
        self.maxSize = maxSize
        self.curr = min(max(val, 0), maxSize - 1)

    def addOne(self):
        oldCurr = self.curr
        self.curr = min(self.curr + 1, self.maxSize - 1)
        return oldCurr != self.curr

    def minusOne(self):
        oldCurr = self.curr
        self.curr = max(self.curr - 1, 0)
        return oldCurr != self.curr

class ApiSession():
    accessToken = ""
    session = None

    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self.accessToken = self.session.get("https://open.spotify.com/get_access_token?reason=transport&productType=web_player").json()["accessToken"]

    def query(self, url, args={}):
        selectedIdx = 0

        ret = re.search("/track(s?)/(\\w+)", url);
        if ret:
            track = self.wget("https://api.spotify.com/v1/tracks/{}".format(ret.group(2)), args)
            selectedIdx = int(track["track_number"]) - 1
            url = track["album"]["href"]
            # go to next case

        ret = re.search("/album(s?)/(\\w+)", url)
        if ret:
            return SongList(self.wget("https://api.spotify.com/v1/albums/{}".format(ret.group(2)), args), selectedIdx)

        ret = re.search("/artist(s?)/(\\w+)", url)
        if ret:
            return AlbumList(self.wget("https://api.spotify.com/v1/artists/{}/albums".format(ret.group(2)), dict(args, **{"limit":20})))

        if "type" in args:
            return Search(self.wget("https://api.spotify.com/v1/search", dict(args, **{"q":url})))
        else:
            return Search(self.wget("https://api.spotify.com/v1/search", dict(args, **{"q":url, "type":"track"})))

    def wget(self, api, args={}):
        args = dict(args, **{"access_token":self.accessToken})
        resp = self.session.get(api, params=args).json()
        if "error" in resp:
            raise Exception(resp)
        return resp

class RefreshPage():
    def __init__(self, url, args={}):
        self.url = url
        self.args = args

class NextPage():
    def __init__(self, url, args={}):
        self.url = url
        self.args = args

class BasicPage():
    def __init__(self, href, next, previous, offset, total):
        self.href = href
        self.next = next
        self.previous = previous
        self.offset = offset
        self.total = total
        self.items = []
        self.selectIdx = LimitedRange(0)

    def refreshCursor(self, newCursor = None):
        self.selectIdx = LimitedRange(len(self.items), self.selectIdx.curr if newCursor is None else newCursor)

    def nextPage(self):
        if self.next is not None:
            return RefreshPage(self.next)
        return None

    def prevPage(self):
        if self.previous is not None:
            return RefreshPage(self.previous)
        return None

    def up(self):
        self.selectIdx.minusOne()
        return None

    def down(self):
        self.selectIdx.addOne()
        return None

    def getKeyInHandler(self, ch):
        return None

    def print(self):
        self._header()
        self._body()

    def _printHeader(self, title, tab = ""):
        self.refreshCursor()
        print(tab)
        print("{:4} {:>30} {:^20}                    {:4}".format(
            "Prev" if self.previous is not None else "",
            title,
            ("{:>6} out of {:<6}" if self.offset is not None else "").format(
                self.offset, self.total
            ),
            "Next" if self.next is not None else ""
        ))
        print("================================================================================")

    def _printEachItem(self, functor):
        for idx,item in enumerate(self.items):
            print("{}{}".format(
                "> " if idx == self.selectIdx.curr else "  ",
                functor(idx,item)
            ))

    def _getSelectedItem(self):
        return self.items[self.selectIdx.curr]

    def _addItem(self, obj):
        self.items.append(obj)

    def _header(self):
        raise Exception("Missing implementation")

    def _body(self):
        raise Exception("Missing implementation")

class ArtistList(BasicPage):
    def __init__(self, obj):
        self.setContext(obj)

    def setContext(self, obj):
        super().__init__(obj["href"], obj["next"], obj["previous"], obj["offset"], obj["total"])
        for idx,item in enumerate(obj["items"]):
            tmp = {}
            tmp["name"] = item["name"]
            tmp["href"] = item["href"]
            self._addItem(tmp)

    def _body(self):
        self._printEachItem(lambda idx, item:
            "{}".format(
                format("{:{}}", 80, item["name"])
            )
        )

    def enter(self):
        return NextPage(self._getSelectedItem()["href"])

class AlbumList(BasicPage):
    def __init__(self, obj):
        self.setContext(obj)

    def setContext(self, obj):
        super().__init__(obj["href"], obj["next"], obj["previous"], obj["offset"], obj["total"])
        for idx,item in enumerate(obj["items"]):
            tmp = {}
            tmp["artists"] = getArtistNames(item["artists"])
            tmp["name"] = item["name"]
            tmp["release_date"] = item["release_date"]
            tmp["uri"] = item["uri"]
            tmp["href"] = item["href"]
            self._addItem(tmp)

    def _header(self):
        self._printHeader("Artist")

    def _body(self):
        self._printEachItem(lambda idx, item:
            "{}{}{}".format(
                format("{:{}}", 34, item["name"]),
                format("{:{}}", 34, item["artists"]),
                item["release_date"]
            )
        )

    def enter(self):
        return NextPage(self._getSelectedItem()["href"])

class SongList(BasicPage):
    def __init__(self, obj, selectedIdx = None):
        self.setContext(obj, selectedIdx)

    def setContext(self, obj, selectedIdx = None):
        super().__init__(obj["tracks"]["href"], obj["tracks"]["next"], obj["tracks"]["previous"],
                         obj["tracks"]["offset"], obj["tracks"]["total"])
        self.artists = getArtistNames(obj["artists"]) if "artists" in obj else ""
        self.name = obj["name"] if "name" in obj else ""
        self.release_date = obj["release_date"] if "release_date" in obj else ""
        for idx,item in enumerate(obj["tracks"]["items"]):
            tmp = {}
            tmp["artists"] = getArtistNames(item["artists"])
            tmp["name"] = item["name"]
            tmp["track_number"] = item["track_number"]
            tmp["disc_number"] = item["disc_number"]
            tmp["duration_ms"] = item["duration_ms"]
            tmp["uri"] = item["uri"]
            tmp["href"] = item["href"]
            tmp["album"] = item["album"]["name"] if "album" in item else self.name
            self._addItem(tmp)
        self.refreshCursor(selectedIdx)

    def _header(self):
        self._printHeader("", "{:<35}{:35}{:>10}".format(
            self.artists, self.name, self.release_date
        ))

    def _body(self):
        self._printEachItem(lambda idx, item:
            "{:>2} {} {} {:02}m{:02}s".format(
                item["track_number"],
                format("{:{}}", 34, item["name"]),
                format("{:{}}", 33, item["artists"]),
                int(int(item["duration_ms"]) / 1000 / 60),
                int(int(item["duration_ms"]) / 1000 % 60)
            )
        )

    def enter(self):
        self.importSong(False)

    def addAll(self):
        self.importSong(True)

    def importSong(self, all):
        global album
        global highLight

        file = open("/tmp/song.xspf", "w")
        file.write("""<?xml version="1.0" encoding="UTF-8"?>
    <playlist version="1" xmlns="http://xspf.org/ns/0/"><trackList>""");

        songList = []
        if all:
            for idx,item in enumerate(self.items):
                songList.append(item)
        else:
            songList.append(self._getSelectedItem())

        for song in songList:
            file.write("""
    <track>
      <location>{}</location>
      <title>{}</title>
      <creator>{}</creator>
      <duration>{}</duration>
      <trackNum>{}</trackNum>
      <album>{}</album>
    </track>""".format(
                song["uri"],
                escape(song["name"]),
                escape(song["artists"]),
                song["duration_ms"],
                song["track_number"],
                escape(song["album"])
            ))
        file.write("""</trackList></playlist>""")
        file.close()
        os.system("/usr/bin/clementine -a /tmp/song.xspf")

    def getKeyInHandler(self, ch):
        if ch == 'A' or ch == 'a':
            return self.addAll
        return None

def escape(txt):
    return txt.replace("&", "&amp;")

class Search(BasicPage):
    def __init__(self, obj):
        self.setContext(obj)

    def setContext(self, obj):
        curIdx = self.selectIdx if "selectIdx" in self.__dict__ else None
        curTab = self.tabIdx if "tabIdx" in self.__dict__ else LimitedRange(3, 0)
        if "tracks" in obj:
            tmp = SongList(obj)
            self.__dict__ = tmp.__dict__
            self.printFunc = tmp._body
            self.enterFunc = tmp.enter
        elif "albums" in obj:
            tmp = AlbumList(obj["albums"])
            self.__dict__ = tmp.__dict__
            self.printFunc = tmp._body
            self.enterFunc = tmp.enter
        elif "artists" in obj:
            tmp = ArtistList(obj["artists"])
            self.__dict__ = tmp.__dict__
            self.printFunc = tmp._body
            self.enterFunc = tmp.enter
        else:
            raise Exception("Unexpected context")

        if curIdx is not None:
            self.selectIdx = curIdx
        self.tabIdx = curTab

    def enter(self):
        return self.enterFunc()

    def _loadTab(self):
        type = ["track", "album", "artist"]
        getArgs = parse_qs(urlparse(self.href).query)
        return RefreshPage("https://api.spotify.com/v1/search", {"query": getArgs["query"][0], "type": type[self.tabIdx.curr]})

    def _nextTab(self):
        if self.tabIdx.addOne():
            return self._loadTab()
        return None

    def _prevTab(self):
        if self.tabIdx.minusOne():
            return self._loadTab()
        return None

    def getKeyInHandler(self, ch):
        if ch == "ENTER":
            return self._enter
        if ch == "LEFT":
            return self._prevTab
        if ch == "RIGHT":
            return self._nextTab
        return None

    def _header(self):
        self._printHeader("", "{}                            {}                          {}".format(
            "> Track <"  if self.tabIdx.curr == 0 else "  Track  ",
            "> Artist <" if self.tabIdx.curr == 1 else "  Artist  ",
            "> Album <"  if self.tabIdx.curr == 2 else "  Album  "
        ))

    def _body(self):
        self.printFunc()

class Browser():
    api = None
    history = None
    current = None

    def __init__(self):
        super().__init__()
        self.api = ApiSession()
        self.history = []
        self.current = None

    def query(self,url,args={}):
        if self.current is not None:
            self.history.append(self.current)
        self.current = self.api.query(url,args)
        return self.current

    def back(self):
        if len(self.history):
            self.current = self.history.pop()

    def print(self):
        os.system('clear')
        self.current.print()

    def nextAction(self):
        ch = getKeyPress()
        if ch == "UP":
            return self.current.up
        elif ch == "DOWN":
            return self.current.down
        elif ch == "PAGEUP":
            return self.current.prevPage
        elif ch == "PAGEDOWN":
            return self.current.nextPage
        elif ch == "BACKSPACE":
            return self.back
        elif ch == "ENTER":
            return self.current.enter
        return self.current.getKeyInHandler(ch)

    def run(self):
        while True:
            self.print()
            handler = self.nextAction()
            while (handler is None):
                handler = self.nextAction()
            result = handler()

            if type(result) is RefreshPage:
                self.current.setContext(self.api.wget(result.url, result.args))
            elif type(result) is NextPage:
                self.query(result.url, result.args)

if __name__ == "__main__":
    if len(sys.argv) >= 2:
        url = " ".join(sys.argv[1:])
        browser = Browser()
        browser.query(url)
        browser.run()
    else:
        print("Usage:")
        print("  ", sys.argv[0], "[keyword...]", " -- search spotify with keyword(s)")
        print("  ", sys.argv[0], "[spotify url]", "-- go to specify spotify url")
        print("Control:")
        print("  UP/DOWN            -- Select Item ")
        print("  PAGE UP/ PAGE DOWN -- Select page (if available)")
        print("  Enter              -- Open the content / add a song to clementine")
        print("  a / A              -- Add all songs in this album to clementine")
