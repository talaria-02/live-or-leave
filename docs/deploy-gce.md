# GCE Docker Compose 배포 가이드

Day4 목표는 로컬 앱을 외부에서 호출 가능한 HTTP 서비스로 올리고, GitHub Actions에서
테스트가 자동 실행되는 최소 운영 형태를 만드는 것이다.

## 배포 구성

- `api`: FastAPI, `http://<VM_EXTERNAL_IP>:8000`
- `ui`: Streamlit 지도 UI, `http://<VM_EXTERNAL_IP>:8501`
- 같은 Docker 이미지를 사용하고 `command`만 다르게 실행한다.
- `.env`로 API 키와 런타임 옵션을 주입한다.
- `dataset/` 원본 CSV는 이미지에 넣지 않고 VM의 로컬 디렉터리를 volume으로 마운트한다.

## VM 준비

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

권한 반영을 위해 SSH를 한 번 다시 접속한다.

## 앱 배포

```bash
git clone <REPOSITORY_URL>
cd live-or-leave-team
cp .env.example .env
vi .env
```

`.env`에는 최소한 아래 값을 넣는다.

```bash
UPSTAGE_API_KEY=...
SOLAR_MODEL=solar-pro2-251215
UPSTAGE_API_BASE=https://api.upstage.ai/v1
USE_MOCK_LLM=0
```

상권 업종 기반 질문(헬스장, 카페, 버거집 등)을 실제 Solar 경로로 보여주려면
VM의 프로젝트 루트에 `dataset/` 원본 CSV를 별도로 준비한다. 이 디렉터리는 git과
Docker 이미지에 포함하지 않는다.

```bash
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8000/health
```

GCE 방화벽에서 TCP `8000`, `8501`을 허용하면 외부에서 아래 주소로 확인할 수 있다.

```text
http://<VM_EXTERNAL_IP>:8000/health
http://<VM_EXTERNAL_IP>:8501
```

## CI 확인

`.github/workflows/ci.yml`은 push/PR마다 다음을 실행한다.

- Python 3.12 의존성 설치
- `python -m pytest tests/`
- `docker build -t live-or-leave:ci .`

최종 발표 산출물로는 GitHub Actions의 초록색 통과 화면과 GCE 외부 접속 URL을 캡처한다.

## 발표 데모 운영 팁

- API 키가 없거나 UI 디자인만 확인할 때는 `.env`에서 `USE_MOCK_LLM=1`로 둔다.
- 실제 LLM 답변 품질을 보여줄 때는 `USE_MOCK_LLM=0`과 `UPSTAGE_API_KEY`가 필요하다.
- F03처럼 헬스장/공원 업종이 들어간 질문은 `dataset/` 원본 CSV가 있어야 실제 상권 조회까지 동작한다.
- F19처럼 소음/방음 등 현재 데이터가 부족한 조건은 추천을 꾸미기보다 부족 조건을 명시하는 방향으로 보여준다.
