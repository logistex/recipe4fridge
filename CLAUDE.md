# CLAUDE.md

이 파일은 이 저장소에서 작업할 때 Claude Code(claude.ai/code)에게 제공되는 안내 문서입니다.

## 프로젝트 개요

냉장고 사진에서 식재료를 인식하고 레시피를 추천하는 웹 애플리케이션 프로젝트. [OpenRouter](https://openrouter.ai) API를 통해 비전/텍스트 모델을 호출한다. 기능 요구사항은 `docs/PRD_step1.md` ~ `PRD_step3.md`에 단계별로 정의되어 있다.

## 폴더 구조

- `docs/` — 제품 요구사항 문서(PRD). `PRD_step1` 냉장고 사진 식재료 인식, `PRD_step2` 레시피 생성, `PRD_step3` 사용자 프로필/레시피 저장. 각 `.md` 파일과 동일한 내용의 `.pdf` 사본이 함께 있다.
- `src/` — 실행 코드. 현재는 OpenRouter API 연동을 검증하는 `test_api.py`만 있다.
- 루트 — `.env`(비밀 키), `.env.example`(템플릿), `.gitignore`, `CLAUDE.md`.

## 실행

```bash
python3 src/test_api.py
```
`python-dotenv`가 스크립트 위치(`src/`)에서 상위 디렉터리로 올라가며 루트의 `.env`를 자동으로 찾으므로, 실행 위치와 무관하게 `OPENROUTER_API_KEY`가 로드된다.

빌드 시스템, 패키지 매니페스트, 테스트 스위트는 아직 없다. 실제 앱(백엔드/프론트엔드) 코드가 추가되면 이 문서에 다음 내용을 업데이트해야 한다:
- 선택한 언어/프레임워크와 의존성 설치 방법.
- 빌드, 린트, 테스트 명령어 (단일 테스트 실행 방법 포함).
- PRD 단계(1~3)와 실제 코드 모듈 간의 대응 관계.

## 환경 변수

- `.env`의 `OPENROUTER_API_KEY`는 OpenRouter API 접근에 사용됩니다. 이 값을 출력하거나 로그로 남기거나 커밋하지 마세요.
- `.env`는 `.gitignore`에 등록되어 있어 커밋되지 않습니다. 실제 키가 없는 템플릿은 `.env.example`을 참고하세요.
- 코드에서는 항상 환경 변수(`process.env.OPENROUTER_API_KEY`, `os.environ["OPENROUTER_API_KEY"]` 등)로 키를 불러오고, 소스 코드에 직접 하드코딩하지 마세요.
