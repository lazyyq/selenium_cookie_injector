"""Inject host-only HTTPS session cookies into an existing Chromium browser."""

import argparse
import ipaddress
import json
import re
import sys
import time
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


TIMEOUT = 10
EXIT_DELAY = 5


class ArgumentError(ValueError):
    pass


class InjectionError(RuntimeError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse messages can echo arguments containing cookie secrets.
        raise ArgumentError("인자를 확인하세요. 포트, 도메인, 쿠키 이름·값 쌍이 필요합니다. (--help 참고)")


def parse_arguments(argv):
    parser = Parser(
        description="Chrome/Edge에 HTTPS 전용 세션 쿠키를 주입합니다.",
        usage="%(prog)s <remote_debugging_port> <domain> <cookie key> <cookie value> ...",
    )
    parser.add_argument("port", help="로컬 remote debugging port (1~65535)")
    parser.add_argument("domain", help="URL이 아닌 호스트명 (예: example.com)")
    parser.add_argument("cookies", nargs=argparse.REMAINDER, help="하나 이상의 쿠키 이름·값 쌍")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9]+", args.port) or not 1 <= int(args.port) <= 65535:
        raise ArgumentError("포트는 1~65535 사이의 정수여야 합니다.")
    try:
        domain = args.domain.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise ArgumentError("올바른 호스트명을 입력하세요.") from None
    labels = domain.split(".")
    if len(domain) > 253 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in labels
    ):
        raise ArgumentError("도메인은 URL·경로·포트·선행 점이 없는 호스트명이어야 합니다.")
    if not args.cookies or len(args.cookies) % 2:
        raise ArgumentError("쿠키 이름·값을 하나 이상의 쌍으로 입력하세요.")
    cookies = {}
    for name, value in zip(args.cookies[::2], args.cookies[1::2]):
        if not re.fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", name):
            raise ArgumentError("쿠키 이름은 비어 있거나 공백·구분 문자를 포함할 수 없습니다.")
        cookies[name] = value
    return int(args.port), domain, cookies


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise InjectionError("디버깅 서버의 HTTP 리디렉션은 허용하지 않습니다.")


def get_websocket_url(port):
    try:
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(f"http://127.0.0.1:{port}/json/version", timeout=TIMEOUT) as response:
            data = json.loads(response.read(1024 * 1024))
        address = data["webSocketDebuggerUrl"]
        parts = urlsplit(address)
        host = parts.hostname
        is_local = host == "localhost" or ipaddress.ip_address(host).is_loopback
        if (
            parts.scheme != "ws" or not is_local or parts.port != port
            or parts.username is not None or parts.password is not None
            or not parts.path.startswith("/devtools/browser/") or parts.fragment
        ):
            raise ValueError()
        # Use the already contacted IPv4 loopback endpoint, avoiding DNS/proxies.
        return urlunsplit(("ws", f"127.0.0.1:{port}", parts.path, parts.query, ""))
    except InjectionError:
        raise
    except Exception:
        raise InjectionError("디버깅 서버에 연결할 수 없거나 브라우저 WebSocket 주소가 올바르지 않습니다.") from None


def connect_websocket(address):
    try:
        import websocket
    except ImportError:
        raise InjectionError("websocket-client가 필요합니다. python -m pip install -r requirements.txt를 실행하세요.") from None
    try:
        return websocket.create_connection(
            address, timeout=TIMEOUT, suppress_origin=True,
            http_no_proxy=["127.0.0.1", "localhost", "::1"],
        )
    except Exception:
        raise InjectionError("브라우저 WebSocket에 연결하지 못했습니다.") from None


class CDPClient:
    def __init__(self, connection):
        self.connection = connection
        self.request_id = 0

    def call(self, method, params=None):
        self.request_id += 1
        request_id = self.request_id
        deadline = time.monotonic() + TIMEOUT
        try:
            self.connection.settimeout(TIMEOUT)
            self.connection.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                self.connection.settimeout(remaining)
                message = json.loads(self.connection.recv())
                if message.get("id") != request_id:
                    continue
                if "error" in message:
                    raise InjectionError(f"브라우저가 {method} 명령을 거부했습니다.")
                result = message["result"]
                if not isinstance(result, dict):
                    raise ValueError()
                return result
        except InjectionError:
            raise
        except Exception:
            raise InjectionError(f"{method} 명령 응답을 받지 못했습니다. 연결 또는 제한 시간을 확인하세요.") from None


def inject_cookies(port, domain, cookies):
    connection = connect_websocket(get_websocket_url(port))
    attempted = False
    try:
        client = CDPClient(connection)
        parameters = [
            {"name": name, "value": value, "url": f"https://{domain}/",
             "path": "/", "secure": True, "httpOnly": False}
            for name, value in cookies.items()
        ]
        attempted = True
        client.call("Storage.setCookies", {"cookies": parameters})
        stored = client.call("Storage.getCookies").get("cookies", [])
        for name, value in cookies.items():
            if not any(
                item.get("name") == name and item.get("value") == value
                and item.get("domain") == domain and item.get("path") == "/"
                and item.get("secure") is True and item.get("httpOnly") is False
                and item.get("session") is True and not item.get("partitionKey")
                for item in stored
            ):
                raise InjectionError("쿠키 설정 결과가 요청한 값 또는 속성과 일치하지 않습니다.")
    except Exception as error:
        reason = str(error) if isinstance(error, InjectionError) else "쿠키 처리 중 오류가 발생했습니다."
        if attempted:
            reason += " 일부 쿠키가 적용되었을 수 있습니다. 자동 롤백은 수행하지 않습니다."
        raise InjectionError(reason) from None
    finally:
        try:
            connection.close()
        except Exception:
            pass


def main(argv=None):
    try:
        try:
            port, domain, cookies = parse_arguments(sys.argv[1:] if argv is None else argv)
            inject_cookies(port, domain, cookies)
            message, code, stream = f"성공: {domain}에 쿠키 {len(cookies)}개를 주입했습니다.", 0, sys.stdout
        except ArgumentError as error:
            message, code, stream = f"실패: {error}", 2, sys.stderr
        except InjectionError as error:
            message, code, stream = f"실패: {error}", 1, sys.stderr
        except Exception:
            message, code, stream = "실패: 실행 중 예상하지 못한 오류가 발생했습니다.", 1, sys.stderr
        print(message, file=stream, flush=True)
        print("5초 후 종료합니다.", file=stream, flush=True)
        time.sleep(EXIT_DELAY)
        return code
    except KeyboardInterrupt:
        print("중단: 사용자 요청으로 종료합니다.", file=sys.stderr, flush=True)
        return 130


if __name__ == "__main__":
    sys.exit(main())
