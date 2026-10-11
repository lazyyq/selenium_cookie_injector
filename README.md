# Chrome/Edge 쿠키 주입 CLI

실행 중인 Chrome 또는 Edge의 로컬 remote debugging port에 CDP로 연결하여 특정 호스트에 쿠키를 주입합니다. Selenium이나 브라우저 드라이버는 필요하지 않습니다.

## 설치

Python 3.10 이상을 사용합니다. PowerShell에서 프로젝트 폴더로 이동한 뒤 실행하세요.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

이후 예제의 `python` 대신 `.\.venv\Scripts\python.exe`를 사용해도 됩니다.

## 브라우저 준비

사용자가 브라우저를 디버깅 포트 옵션으로 먼저 실행해야 합니다. 아래 예제는 프로젝트 내부의 별도 프로필을 사용합니다. 설치 위치가 다르면 실행 파일 경로를 수정하세요.

Chrome:

```powershell
& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 "--user-data-dir=$PWD\browser-profiles\chrome"
```

Edge:

```powershell
& "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9223 --remote-debugging-address=127.0.0.1 "--user-data-dir=$PWD\browser-profiles\edge"
```

Chrome 136부터 기본 데이터 디렉터리에서는 remote debugging 옵션이 적용되지 않으므로 별도 `--user-data-dir`을 지정해야 합니다. [Chrome 공식 안내](https://developer.chrome.com/blog/remote-debugging-port)

## 실행

```powershell
python main.py <remote_debugging_port> <domain> <cookie key 1> <cookie value 1> <cookie key 2> <cookie value 2> ...
python main.py 9222 example.com session "abc123" token "xyz789"
python main.py 9223 example.com greeting "hello world"
python main.py --help
```

도메인은 `example.com`처럼 호스트명만 입력합니다. URL, 경로, 포트, 선행 점은 허용하지 않습니다. 국제화 도메인은 IDNA로 변환합니다. 포트 범위는 1~65535입니다. IPv4와 localhost도 가능하며 IPv6 호스트 입력은 지원하지 않습니다.

쿠키 이름·값은 하나 이상의 쌍으로 입력해야 합니다. 빈 이름은 허용하지 않고 빈 값은 허용합니다. 같은 이름을 여러 번 입력하면 마지막 값을 사용합니다. 이름·값 위치의 `-`로 시작하는 문자열도 쿠키 인자로 처리합니다.

공백이 있는 값은 따옴표로 묶으세요. PowerShell 7.3 이상의 기본 네이티브 인자 전달 모드에서는 빈 값을 다음처럼 입력할 수 있습니다.

```powershell
python main.py 9222 example.com session ""
```

Windows PowerShell 5.1 또는 `$PSNativeCommandArgumentPassing='Legacy'`에서는 빈 인자 전달에 다음 표기가 필요합니다.

```powershell
python main.py 9222 example.com session '\"\"'
```

CLI 인자는 셸 기록이나 프로세스 정보에 남을 수 있으므로 실행 환경에 맞게 쿠키 값을 관리하세요.

## VS Code 실행 구성

`.vscode/launch.json`에 다음 두 구성이 있습니다. VS Code의 Python 및 Python Debugger 확장을 설치하세요. 두 구성 모두 프로젝트의 `.venv/Scripts/python.exe`를 사용합니다.

| 구성 | 동작 |
| --- | --- |
| 1. IROS PM10SESSIONID 쿠키 주입 (9222) | 실행 중인 포트 9222 브라우저의 `www.iros.go.kr` 호스트에 지정된 PM10SESSIONID 값을 주입 |
| 2. Selenium 테스트 Chrome 실행 (9222) | Selenium으로 별도 테스트 프로필의 Chrome을 디버깅 포트 9222와 함께 실행 |

Selenium 테스트 구성에는 별도 의존성이 필요합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-selenium.txt
```

2번 구성을 먼저 실행한 뒤 브라우저를 유지한 상태에서 1번 구성을 선택하여 추가로 실행하세요. 쿠키 주입 프로그램은 결과 출력 후 5초 뒤 종료하며 Selenium 브라우저는 유지됩니다. 테스트가 끝나면 Selenium 터미널에서 Enter를 눌러 해당 테스트 브라우저를 닫으세요. Ctrl+C로도 종료할 수 있습니다.

두 구성의 포트를 바꾸려면 `launch.json`의 양쪽 `args`를 동일하게 수정하세요. 이미 다른 브라우저가 포트 9222를 사용한다면 1번만 실행하거나 다른 포트를 지정합니다. 테스트 브라우저는 빈 탭으로 시작하며 사이트 방문과 새로고침은 직접 수행합니다.

`tools/launch_selenium.py`는 쿠키 주입 코드와 독립적인 테스트 실행 도구입니다. 프로필은 실행마다 `browser-profiles/selenium-...`에 생성·보관합니다. [Selenium Manager](https://www.selenium.dev/documentation/selenium_manager/)가 드라이버를 준비하므로 첫 실행에는 드라이버 다운로드를 위한 네트워크 연결이 필요할 수 있습니다.

## 쿠키와 브라우저 동작

- 입력한 호스트에만 적용하며 하위 도메인은 포함하지 않습니다.
- 경로 `/`, Secure=true, HttpOnly=false, 만료일 없는 세션 쿠키입니다. HTTPS 요청에 사용되며 SameSite는 브라우저 기본값입니다.
- 이름·호스트·경로가 같은 기존 쿠키는 덮어쓰고 다른 쿠키는 삭제하지 않습니다.
- 일반 브라우저의 기본 컨텍스트에 주입합니다. 시크릿 컨텍스트 선택은 지원하지 않습니다.
- 설정 후 CDP로 값과 속성을 확인합니다. 브라우저가 접두사 규칙 등으로 쿠키를 거부하면 실패합니다. 예를 들어 HttpOnly가 필요한 `__Http-` 계열은 현재 기본값으로 설정할 수 없습니다.
- 탭을 열거나 이동·새로고침하지 않고 브라우저를 종료하지 않습니다. 필요하면 사용자가 주입 후 직접 새로고침하세요.

프로그램은 [Storage.setCookies](https://chromedevtools.github.io/devtools-protocol/tot/Storage/#method-setCookies)와 [Storage.getCookies](https://chromedevtools.github.io/devtools-protocol/tot/Storage/#method-getCookies)를 사용합니다. host-only 범위를 유지하기 위해 쿠키 파라미터의 `domain` 대신 `url`을 지정합니다.

## 결과와 종료 코드

성공 시 stdout에 다음처럼 출력하며 쿠키 값은 출력하지 않습니다.

```text
성공: example.com에 쿠키 2개를 주입했습니다.
5초 후 종료합니다.
```

실패 시 stderr에 실패 원인과 동일한 대기 안내를 출력합니다. 성공과 일반 오류 모두 연결을 정리하고 출력 내용을 flush한 뒤 5초 대기합니다. 도움말은 즉시 종료하고 Ctrl+C로 대기를 중단할 수 있습니다.

| 코드 | 의미 |
| --- | --- |
| 0 | 성공 또는 도움말 |
| 1 | 연결·설정·검증 등 실행 실패 |
| 2 | 인자 오류 |
| 130 | Ctrl+C로 중단 |

설정 시도 후 실패하면 일부 쿠키가 적용되었을 수 있습니다. 자동 롤백은 수행하지 않습니다.

## 문제 해결

- 연결 실패: 브라우저 실행 옵션과 포트를 확인하세요. `Invoke-RestMethod http://127.0.0.1:9222/json/version`으로 디버깅 서버 응답을 확인할 수 있습니다.
- 포트가 열리지 않음: 별도 프로필을 사용하고 다른 브라우저와 포트가 겹치지 않는지 확인하세요.
- 의존성 오류: 실행에 사용하는 Python으로 `python -m pip install -r requirements.txt`를 실행하세요.
- 설정·검증 실패: 쿠키 이름·값의 유효성, 접두사 규칙, 브라우저 정책을 확인하세요. 사이트나 다른 프로세스가 같은 쿠키를 동시에 변경해도 검증에 실패할 수 있습니다.
- 기본 컨텍스트 쿠키는 설정되지만 로그인 성공 여부는 사이트가 결정합니다. 동일 이름의 다른 경로·도메인 쿠키도 요청에 영향을 줄 수 있습니다.

연결과 각 CDP 명령의 제한 시간은 10초입니다. HTTP 리디렉션과 외부 WebSocket 주소는 허용하지 않고 프록시를 사용하지 않습니다.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

단위 테스트는 HTTP/WebSocket과 sleep을 모의 처리하므로 실행 중인 브라우저가 필요하지 않습니다. 실제 브라우저 검증은 별도 Chrome/Edge 프로필에서 더미 쿠키로 주입·덮어쓰기·호스트 범위·Secure 속성과 브라우저 유지 여부를 확인하세요.

자동 브라우저 검증은 다음처럼 실행합니다. 검증 스크립트만 별도 headless 브라우저를 실행하고 검증 후 해당 브라우저를 닫습니다. 테스트 프로필은 `browser-profiles/`에 보관합니다.

```powershell
python -X utf8 tests/smoke_browser.py "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
python -X utf8 tests/smoke_browser.py "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
```
