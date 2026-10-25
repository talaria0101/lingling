"""Loopback substitution for hosts that refuse TCP bind().

Some sandboxes block bind() on AF_INET/AF_INET6 while still allowing AF_UNIX.
The lingling verify suites all open their loopback servers with the single
pattern bind(("127.0.0.1", 0)), so translating that pattern onto a unix
listener keeps every suite runnable.

What this does NOT establish: nothing here exercises TCP.  Nagle, TCP_NODELAY,
real socket-level timeouts and kernel TCP behaviour are not measured.
"""
import os
import socket

#: fake port -> unix path, for every listener this process opened
_PORTS = {}
_PORTS_BY_PATH = {}
#: id(socket) -> fake port, for both listeners and their connections
_STATE = {}
_NEXT = [21000]
_LOOPBACK = ("127.0.0.1", "::1", "localhost", "0.0.0.0")
_DEBUG = bool(os.environ.get("LL_SHIM_DEBUG"))


def _log(msg):
    if _DEBUG:
        print("[shim] " + msg, flush=True)


def _alloc():
    while True:
        port = _NEXT[0]
        _NEXT[0] += 1
        if port not in _PORTS:
            return port


def _path(port):
    return "/tmp/lingling-loopback-%d" % port


def _retarget(self, family):
    """Re-open this socket object on another family, keeping its timeout.

    Re-initialising a socket object resets its timeout to blocking, which
    silently removes every deadline the caller had already armed.  lingling's
    socks5_open derives its whole window from sock.gettimeout(), so losing it
    turns a bounded read into an unbounded one.
    """
    timeout = self.gettimeout()
    fd = self.detach()
    if fd is not None and fd >= 0:
        os.close(fd)
    socket.socket.__init__(self, family, socket.SOCK_STREAM)
    if timeout is not None:
        self.settimeout(timeout)
    _log("retarget fd=%s family=%s timeout=%s" % (id(self), family, timeout))


def _pair(address):
    host = address[0] if isinstance(address, tuple) else None
    port = address[1] if isinstance(address, tuple) else None
    return host, port


def _install():
    _bind = socket.socket.bind
    _getsockname = socket.socket.getsockname
    _getpeername = socket.socket.getpeername
    _connect = socket.socket.connect
    _accept = socket.socket.accept

    def bind(self, address):
        try:
            return _bind(self, address)
        except PermissionError:
            host, _port = _pair(address)
            if self.family not in (socket.AF_INET, socket.AF_INET6):
                raise
            if host not in _LOOPBACK:
                raise
            port = _alloc()
            path = _path(port)
            try:
                os.unlink(path)
            except OSError:
                pass
            _retarget(self, socket.AF_UNIX)
            _bind(self, path)
            _PORTS[port] = path
            _PORTS_BY_PATH[path] = port
            _STATE[id(self)] = port
            _log("bind -> unix %s as port %s" % (path, port))
            return None

    def _known(self):
        """The fake port this socket speaks, from either end."""
        port = _STATE.get(id(self))
        if port is not None:
            return port
        try:
            raw = _getpeername(self)
        except OSError:
            return None
        if isinstance(raw, str):
            return _PORTS_BY_PATH.get(raw)
        return None

    def getsockname(self):
        port = _known(self)
        if port is not None:
            return ("127.0.0.1", port)
        return _getsockname(self)

    def getpeername(self):
        port = _known(self)
        if port is not None:
            return ("127.0.0.1", port)
        return _getpeername(self)

    def connect(self, address):
        host, port = _pair(address)
        if host in _LOOPBACK and port in _PORTS:
            _log("connect port %s -> unix %s" % (port, _PORTS[port]))
            _retarget(self, socket.AF_UNIX)
            _connect(self, _PORTS[port])
            _STATE[id(self)] = port
            return None
        return _connect(self, address)

    def accept(self):
        conn, addr = _accept(self)
        port = _STATE.get(id(self))
        if port is not None:
            _STATE[id(conn)] = port
            addr = ("127.0.0.1", port)
        return conn, addr

    socket.socket.bind = bind
    socket.socket.getsockname = getsockname
    socket.socket.getpeername = getpeername
    socket.socket.connect = connect
    socket.socket.accept = accept


_install()
