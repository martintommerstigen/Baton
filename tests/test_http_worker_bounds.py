"""B5/B2: bound slow-client workers and reject duplicate media-type headers.

Offline loopback tests only; no existing ChatGPT conversation is contacted.
"""
import http.client
import socket
import threading
import time
import unittest

from remote_security.http_ingress import IngressServer, MAX_ACTIVE_REQUESTS


class NoAdmissionGate:
    def accept_payload(self, *_args):
        raise AssertionError("invalid HTTP framing reached envelope admission")


class StallingServer(IngressServer):
    """Hold worker threads before parsing HTTP, simulating slow clients."""

    def __init__(self):
        self.entered = 0
        self.condition = threading.Condition()
        self.release_workers = threading.Event()
        self.finished = threading.Event()
        super().__init__(0, b't' * 32, NoAdmissionGate())
        self._request_slots = threading.BoundedSemaphore(2)

    def process_request_thread(self, request, address):
        with self.condition:
            self.entered += 1
            self.condition.notify_all()
        self.release_workers.wait(timeout=5)
        try:
            super().process_request_thread(request, address)
        finally:
            with self.condition:
                self.entered -= 1
                if self.entered == 0:
                    self.finished.set()

    def wait_for_workers(self, count):
        deadline = time.monotonic() + 3
        with self.condition:
            while self.entered < count and time.monotonic() < deadline:
                self.condition.wait(timeout=.05)
            return self.entered >= count


class IngressWorkerLimitTests(unittest.TestCase):
    def test_limit_is_explicit_and_server_is_loopback_only(self):
        self.assertEqual(MAX_ACTIVE_REQUESTS, 16)
        with IngressServer(0, b't' * 32, NoAdmissionGate()) as server:
            self.assertEqual(server.server_address[0], '127.0.0.1')

    def test_excess_slow_client_is_refused_and_capacity_recovers(self):
        with StallingServer() as server:
            runner = threading.Thread(target=server.serve_forever,
                                      kwargs={'poll_interval': .01}, daemon=True)
            runner.start()
            slow = []
            extra = None
            try:
                for _ in range(2):
                    slow.append(socket.create_connection(server.server_address, timeout=2))
                self.assertTrue(server.wait_for_workers(2), 'workers did not start')
                extra = socket.create_connection(server.server_address, timeout=2)
                extra.settimeout(2)
                # The third connection must be closed without a worker.
                try:
                    self.assertEqual(extra.recv(1), b'')
                except ConnectionResetError:
                    pass
                with server.condition:
                    self.assertEqual(server.entered, 2)
            finally:
                server.release_workers.set()
                for sock in slow:
                    sock.close()
                if extra is not None:
                    extra.close()
            self.assertTrue(server.finished.wait(timeout=4),
                            'worker slots not released')
            connection = http.client.HTTPConnection('127.0.0.1',
                                                    server.server_port, timeout=2)
            try:
                connection.request('GET', '/')
                response = connection.getresponse()
                self.assertEqual(response.status, 405)
                response.read()
            finally:
                connection.close()
            server.shutdown()
            runner.join(timeout=3)

    def test_duplicate_content_type_never_reaches_gate(self):
        with IngressServer(0, b't' * 32, NoAdmissionGate()) as server:
            runner = threading.Thread(target=server.serve_forever,
                                      kwargs={'poll_interval': .01}, daemon=True)
            runner.start()
            try:
                for second in ('application/json', 'text/plain'):
                    with self.subTest(second=second):
                        conn = http.client.HTTPConnection('127.0.0.1',
                                                          server.server_port, timeout=2)
                        try:
                            conn.putrequest('POST', '/v1/envelopes')
                            conn.putheader('Authorization', 'Bearer ' + 't' * 32)
                            conn.putheader('Content-Type', 'application/json')
                            conn.putheader('Content-Type', second)
                            conn.putheader('Content-Length', '0')
                            conn.endheaders()
                            response = conn.getresponse()
                            self.assertEqual(response.status, 404)
                            response.read()
                        finally:
                            conn.close()
            finally:
                server.shutdown()
                runner.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
