"""Standalone Selenium browser launcher; independent of the cookie injector."""

import argparse
from pathlib import Path
import socket
import sys
import uuid


def parse_port(value):
    try:
        port = int(value)
        if 1 <= port <= 65535:
            return port
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("포트는 1~65535 사이의 정수여야 합니다.")


def main():
    parser = argparse.ArgumentParser(description="디버깅 포트를 활성화한 테스트용 Selenium Chrome을 실행합니다.")
    parser.add_argument("--port", type=parse_port, default=9222)
    args = parser.parse_args()
    try:
        from selenium import webdriver
    except ImportError:
        print("selenium이 필요합니다. python -m pip install -r requirements-selenium.txt를 실행하세요.",
              file=sys.stderr, flush=True)
        return 1

    driver = None
    try:
        # Refuse to accidentally share a debugging port with another browser.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", args.port))
        profile = (Path(__file__).resolve().parents[1] / "browser-profiles" /
                   f"selenium-{uuid.uuid4().hex}").resolve()
        profile.mkdir(parents=True)
        options = webdriver.ChromeOptions()
        options.add_argument(f"--remote-debugging-port={args.port}")
        options.add_argument("--remote-debugging-address=127.0.0.1")
        options.add_argument(f"--user-data-dir={profile}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        driver = webdriver.Chrome(options=options)
        driver.get("about:blank")
        print(f"Selenium Chrome 실행 완료: remote debugging port={args.port}", flush=True)
        print(f"테스트 프로필: {profile}", flush=True)
        print("브라우저를 유지한 상태에서 쿠키 주입 구성을 별도로 실행할 수 있습니다.", flush=True)
        input("테스트를 끝내고 브라우저를 닫으려면 Enter를 누르세요: ")
        return 0
    except KeyboardInterrupt:
        return 130
    except EOFError:
        print("입력 가능한 터미널에서 실행하세요.", file=sys.stderr, flush=True)
        return 1
    except Exception:
        print("실행 실패: 포트 사용 여부, Chrome 설치 및 Selenium 드라이버 준비 상태를 확인하세요.",
              file=sys.stderr, flush=True)
        return 1
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
