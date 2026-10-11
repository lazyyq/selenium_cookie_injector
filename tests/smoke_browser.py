"""Opt-in real-browser smoke check using a fresh, retained test profile."""

import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


def smoke(executable):
    root = Path(__file__).resolve().parents[1]
    profile_root = (root / "browser-profiles").resolve()
    profile = (profile_root / f"smoke-{uuid.uuid4().hex}").resolve()
    if not profile.is_relative_to(profile_root):
        raise RuntimeError("테스트 프로필 경로가 올바르지 않습니다.")
    profile.mkdir(parents=True)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    process = subprocess.Popen(
        [executable, "--headless=new", f"--remote-debugging-port={port}",
         "--remote-debugging-address=127.0.0.1", f"--user-data-dir={profile}",
         "--no-first-run", "--no-default-browser-check", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    connection = None
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                connection = main.connect_websocket(main.get_websocket_url(port))
                break
            except main.InjectionError:
                if time.monotonic() >= deadline or process.poll() is not None:
                    raise
                time.sleep(0.25)
        client = main.CDPClient(connection)
        def targets():
            return sorted((item["targetId"], item["url"]) for item in
                          client.call("Target.getTargets")["targetInfos"] if item["type"] == "page")
        before = targets()
        main.inject_cookies(port, "example.test", {"smoke": "first", "empty": ""})
        main.inject_cookies(port, "example.test", {"smoke": "second"})
        cookies = client.call("Storage.getCookies")["cookies"]
        matching = [c for c in cookies if c["domain"] == "example.test" and c["name"] == "smoke"]
        assert len(matching) == 1 and matching[0]["value"] == "second"
        assert matching[0]["secure"] and matching[0]["session"] and not matching[0]["httpOnly"]
        assert set(before).issubset(targets()), "주입 중 기존 탭이 변경되었습니다."
        assert process.poll() is None, "주입 후 브라우저가 종료되었습니다."
        page_id = before[0][0]
        session = client.call("Target.attachToTarget", {"targetId": page_id, "flatten": True})["sessionId"]
        def cookies_for(url):
            client.request_id += 1
            request_id = client.request_id
            connection.send(json.dumps({"id": request_id, "sessionId": session,
                                        "method": "Network.getCookies", "params": {"urls": [url]}}))
            deadline = time.monotonic() + 10
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("쿠키 범위 검증 시간 초과")
                connection.settimeout(remaining)
                response = json.loads(connection.recv())
                if response.get("id") == request_id:
                    assert "error" not in response, "쿠키 범위 조회 실패"
                    return response["result"]["cookies"]
        assert any(c["name"] == "smoke" for c in cookies_for("https://example.test/"))
        assert not cookies_for("https://sub.example.test/")
        assert not cookies_for("http://example.test/")
        start = time.monotonic()
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(root / "main.py"), str(port), "example.test", "smoke", "third"],
            capture_output=True, timeout=25,
        )
        assert result.returncode == 0 and time.monotonic() - start >= 5
        assert "성공:".encode() in result.stdout and "third".encode() not in result.stdout
        # Edge may asynchronously add its own startup tab during the five-second delay.
        assert set(before).issubset(targets()) and process.poll() is None
        print("PASS: 주입·빈 값·덮어쓰기·호스트 범위·Secure·탭 유지·실제 5초 대기")
    finally:
        # Only the fresh browser created by this check is closed, never user browsers.
        if connection is not None:
            try:
                main.CDPClient(connection).call("Browser.close")
            except main.InjectionError:
                pass
            connection.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=10)
        print(f"테스트 프로필 보관: {profile}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="별도 headless 프로필로 실제 브라우저를 검증합니다.")
    parser.add_argument("executable", help="Chrome 또는 Edge 실행 파일 경로")
    smoke(parser.parse_args().executable)
