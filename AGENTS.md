# 프로젝트 작업 지침

## 구조와 명령

- `main.py`: CLI, 로컬 CDP 연결, 쿠키 주입·검증, 결과 출력과 종료.
- `tests/`: 표준 unittest 기반 테스트. 실제 브라우저와 쿠키 없이 실행 가능해야 합니다.
- `README.md`: 한국어 설치·실행·문제 해결 안내.
- `.vscode/launch.json`: IROS 쿠키 주입과 독립 Selenium 테스트 실행 구성. 양쪽 디버깅 포트는 동일하게 유지합니다.
- `tools/launch_selenium.py`: 쿠키 주입 코드에 의존하지 않는 Selenium 테스트 브라우저 실행 도구.
- Selenium 테스트 의존성 설치: `python -m pip install -r requirements-selenium.txt`
- 설치: `python -m pip install -r requirements.txt`
- 테스트: `python -m unittest discover -s tests -v`

## 유지할 동작

- CLI는 `python main.py <port> <domain> <name> <value> ...` 형식을 유지합니다.
- Selenium/드라이버 대신 websocket-client로 CDP에 연결합니다. HTTP/WebSocket은 로컬 주소만 허용하며 프록시와 HTTP 리디렉션을 사용하지 않습니다.
- 쿠키는 해당 호스트 전용, 경로 `/`, Secure=true, HttpOnly=false, 세션 쿠키입니다. SameSite는 브라우저 기본값입니다.
- 중복 이름은 마지막 값으로 처리하고 같은 이름·호스트·경로의 기존 쿠키를 덮어씁니다.
- 브라우저를 자동 실행하거나 종료하지 않고 탭을 열거나 이동·새로고침하지 않습니다. 기본 브라우저 컨텍스트만 사용합니다.
- 위 브라우저 유지 규칙은 쿠키 주입 프로그램에 적용됩니다. 독립 Selenium 실행 도구는 별도 테스트 프로필의 Chrome을 생성하고 Enter 또는 Ctrl+C 종료 시 해당 브라우저만 닫습니다. Selenium 의존성은 별도 requirements 파일로 유지합니다.
- 쿠키 값, 인자 전체, 원본 CDP 응답, 외부 예외 메시지를 콘솔이나 로그에 출력하지 않습니다.
- 성공과 일반 오류 모두 연결 정리 후 한국어 결과와 대기 안내를 flush하고 5초 기다립니다.
- 종료 코드: 성공 0, 실행 실패 1, 인자 오류 2, Ctrl+C 130. 도움말은 대기 없이 종료합니다.
- 설정 시도 후 실패하면 일부 적용 가능성을 알리며 자동 롤백하지 않습니다.

## 변경과 검증

- 동작 변경에는 관련 테스트와 README를 함께 갱신합니다.
- 테스트에서는 sleep과 HTTP/WebSocket을 모의 처리하며 출력·flush·대기 순서와 연결 정리를 검증합니다.
- 실제 브라우저 검증은 별도 테스트 프로필과 더미 쿠키만 사용합니다. 사용자의 기존 프로필을 사용하지 않습니다.
- 실제 Chrome/Edge 검증을 수행하지 못했다면 완료 보고에 미검증 항목을 명시합니다.
