import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import MagicMock, patch

import main


def stored_cookie(name="session", value="secret"):
    return {"name": name, "value": value, "domain": "example.com", "path": "/",
            "secure": True, "httpOnly": False, "session": True}


class ArgumentTests(unittest.TestCase):
    def test_multiple_empty_and_duplicate_values(self):
        self.assertEqual(main.parse_arguments(
            ["9222", "EXAMPLE.COM", "a", "first", "b", "", "a", "--last"]
        ), (9222, "example.com", {"a": "--last", "b": ""}))

    def test_idna(self):
        self.assertEqual(main.parse_arguments(["9222", "예시.kr", "a", "b"])[1],
                         "예시.kr".encode("idna").decode())

    def test_invalid_arguments(self):
        cases = [[], ["9222"], ["0", "example.com", "a", "v"],
                 ["65536", "example.com", "a", "v"], ["abc", "example.com", "a", "v"],
                 ["9222", "example.com"], ["9222", "example.com", "a"],
                 ["9222", "example.com", "", "v"], ["9222", "example.com", "a b", "v"]]
        for domain in ["https://example.com", ".example.com", "example.com/x",
                       "example.com:443", "example.com.", "-example.com", "a..com"]:
            cases.append(["9222", domain, "a", "v"])
        for argv in cases:
            with self.subTest(argv=argv), self.assertRaises(main.ArgumentError):
                main.parse_arguments(argv)


class DiscoveryTests(unittest.TestCase):
    def discover(self, address):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(
            {"webSocketDebuggerUrl": address}).encode()
        with patch.object(main, "build_opener", return_value=opener) as factory:
            result = main.get_websocket_url(9222)
        self.assertEqual(factory.call_args.args[0].proxies, {})
        opener.open.assert_called_once_with("http://127.0.0.1:9222/json/version", timeout=10)
        return result

    def test_loopback_normalized(self):
        for host in ["localhost", "127.0.0.1", "[::1]"]:
            self.assertEqual(self.discover(f"ws://{host}:9222/devtools/browser/id"),
                             "ws://127.0.0.1:9222/devtools/browser/id")

    def test_remote_or_invalid_endpoints_rejected(self):
        for address in ["ws://example.com:9222/devtools/browser/id",
                        "ws://192.168.1.1:9222/devtools/browser/id",
                        "ws://127.0.0.1:9223/devtools/browser/id",
                        "wss://127.0.0.1:9222/devtools/browser/id",
                        "ws://user:password@127.0.0.1:9222/devtools/browser/id",
                        "ws://127.0.0.1:9222/devtools/page/id"]:
            with self.subTest(address=address), self.assertRaises(main.InjectionError):
                self.discover(address)

    def test_http_failure_does_not_echo_exception(self):
        with patch.object(main, "build_opener", side_effect=OSError("secret")):
            with self.assertRaises(main.InjectionError) as result:
                main.get_websocket_url(9222)
        self.assertNotIn("secret", str(result.exception))

    def test_redirect_rejected(self):
        with self.assertRaises(main.InjectionError):
            main.NoRedirect().redirect_request(None, None, 302, "", {}, "http://example.com")

    def test_websocket_options(self):
        import websocket
        with patch.object(websocket, "create_connection") as connect:
            main.connect_websocket("ws://127.0.0.1:9222/devtools/browser/id")
        self.assertTrue(connect.call_args.kwargs["suppress_origin"])
        self.assertEqual(connect.call_args.kwargs["timeout"], 10)
        self.assertIn("127.0.0.1", connect.call_args.kwargs["http_no_proxy"])


class CDPTests(unittest.TestCase):
    def test_event_and_unrelated_response_skipped(self):
        connection = MagicMock()
        connection.recv.side_effect = [json.dumps({"method": "event"}),
                                       json.dumps({"id": 100, "result": {}}),
                                       json.dumps({"id": 1, "result": {"ok": True}})]
        client = main.CDPClient(connection)
        self.assertEqual(client.call("Storage.getCookies"), {"ok": True})
        self.assertEqual(json.loads(connection.send.call_args.args[0])["id"], 1)

    def test_cdp_error_redacted(self):
        connection = MagicMock()
        connection.recv.return_value = json.dumps({"id": 1, "error": {"message": "secret"}})
        with self.assertRaises(main.InjectionError) as result:
            main.CDPClient(connection).call("Storage.setCookies")
        self.assertNotIn("secret", str(result.exception))

    def test_receive_failure(self):
        connection = MagicMock()
        connection.recv.side_effect = TimeoutError("secret")
        with self.assertRaises(main.InjectionError) as result:
            main.CDPClient(connection).call("Storage.getCookies")
        self.assertNotIn("secret", str(result.exception))

    def test_total_deadline_even_with_events(self):
        connection = MagicMock()
        connection.recv.return_value = json.dumps({"method": "event"})
        with patch.object(main.time, "monotonic", side_effect=[0, 1, 11]):
            with self.assertRaises(main.InjectionError):
                main.CDPClient(connection).call("Storage.getCookies")
        self.assertEqual(connection.recv.call_count, 1)


class InjectionTests(unittest.TestCase):
    def inject(self, results):
        connection = MagicMock()
        with patch.object(main, "get_websocket_url", return_value="ws://local"), \
             patch.object(main, "connect_websocket", return_value=connection), \
             patch.object(main.CDPClient, "call", side_effect=results) as call:
            try:
                main.inject_cookies(9222, "example.com", {"session": "secret"})
            finally:
                connection.close.assert_called_once()
        return call

    def test_parameters_and_verification(self):
        call = self.inject([{}, {"cookies": [stored_cookie()]}])
        self.assertEqual(call.call_args_list[0].args, ("Storage.setCookies", {"cookies": [
            {"name": "session", "value": "secret", "url": "https://example.com/",
             "path": "/", "secure": True, "httpOnly": False}]}))
        self.assertEqual(call.call_args_list[1].args, ("Storage.getCookies",))

    def test_mismatch_and_attributes(self):
        for field, value in [("value", "wrong"), ("domain", ".example.com"),
                             ("path", "/other"), ("secure", False),
                             ("httpOnly", True), ("session", False),
                             ("partitionKey", {"topLevelSite": "https://other.com"})]:
            cookie = stored_cookie()
            cookie[field] = value
            with self.subTest(field=field), self.assertRaises(main.InjectionError) as result:
                self.inject([{}, {"cookies": [cookie]}])
            self.assertIn("일부 쿠키", str(result.exception))
            self.assertNotIn("secret", str(result.exception))

    def test_rejected_setting_and_malformed_verification(self):
        for results in [[main.InjectionError("설정 거부")], [{}, {"cookies": None}]]:
            with self.assertRaises(main.InjectionError) as result:
                self.inject(results)
            self.assertIn("일부 쿠키", str(result.exception))


class ExitTests(unittest.TestCase):
    def test_all_results_flush_before_five_second_delay(self):
        for argv, failure, expected, output in [
            (["9222", "example.com", "a", "secret"], None, 0, "성공:"),
            (["9222", "example.com", "a", "secret"], main.InjectionError("연결 실패"), 1, "실패:"),
            ([], None, 2, "실패:"),
        ]:
            events = []
            class Stream(io.StringIO):
                def flush(self):
                    events.append("flush")
            stdout, stderr = Stream(), Stream()
            def delay(seconds):
                self.assertEqual(seconds, 5)
                self.assertGreaterEqual(events.count("flush"), 2)
                target = stdout if expected == 0 else stderr
                self.assertIn(output, target.getvalue())
                self.assertIn("5초 후 종료합니다.", target.getvalue())
                events.append("sleep")
            with self.subTest(code=expected), redirect_stdout(stdout), redirect_stderr(stderr), \
                 patch.object(main, "inject_cookies", side_effect=failure), \
                 patch.object(main.time, "sleep", side_effect=delay) as sleep:
                self.assertEqual(main.main(argv), expected)
                sleep.assert_called_once_with(5)
            self.assertEqual(events[-1], "sleep")
            self.assertNotIn("secret", stdout.getvalue() + stderr.getvalue())

    def test_cleanup_precedes_output(self):
        connection = MagicMock()
        events = []
        connection.close.side_effect = lambda: events.append("close")
        with patch.object(main, "get_websocket_url", return_value="ws://local"), \
             patch.object(main, "connect_websocket", return_value=connection), \
             patch.object(main.CDPClient, "call", side_effect=[{}, {"cookies": [stored_cookie()]}]), \
             patch("builtins.print", side_effect=lambda *a, **kw: events.append("print")), \
             patch.object(main.time, "sleep", side_effect=lambda s: events.append("sleep")):
            self.assertEqual(main.main(["9222", "example.com", "session", "secret"]), 0)
        self.assertEqual(events, ["close", "print", "print", "sleep"])

    def test_help_exits_immediately(self):
        with redirect_stdout(io.StringIO()), patch.object(main.time, "sleep") as sleep:
            with self.assertRaises(SystemExit) as result:
                main.main(["--help"])
            self.assertEqual(result.exception.code, 0)
            sleep.assert_not_called()

    def test_ctrl_c_during_delay_or_injection(self):
        for during_delay in [True, False]:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
                 patch.object(main, "inject_cookies", side_effect=None if during_delay else KeyboardInterrupt()), \
                 patch.object(main.time, "sleep", side_effect=KeyboardInterrupt()) as sleep:
                self.assertEqual(main.main(["9222", "example.com", "a", "v"]), 130)
                self.assertEqual(sleep.call_count, int(during_delay))


if __name__ == "__main__":
    unittest.main()
