# GitLab 자체 서버 구축 매뉴얼 (Docker 기반)

이 문서는 `gapps.gnu.ac.kr/gitlab`에 GitLab Community Edition을 Docker로 구축했던
과정을 그대로 재현할 수 있도록 정리한 매뉴얼입니다. 중간에 겪었던 오류와 해결책도
그대로 남겨뒀습니다 — 새 서버에서도 같은 문제가 나올 수 있어서입니다.

`[서버]`로 표시된 명령은 GitLab을 설치할 리눅스 서버에서, `[로컬]`은 평소 작업하는
PC에서 실행합니다. `<...>` 로 표시된 값은 실제 환경에 맞게 바꿔야 합니다.

> 이 문서는 "코드를 보관·관리하는 GitLab 서버" 구축 전용입니다. "검색 서비스 앱
> 자체"를 서버에 배포하는 방법(systemd 등록, nginx 연동 등)은
> [`MANUAL.md`](../MANUAL.md) 9번 섹션(`Linux 서버로 배포하기`)을 참고하세요.
> 새 서버에 처음부터 올리는 경우 이 문서 → `MANUAL.md` 9번 → 이 문서 10번(자동
> 배포 스크립트) 순서로 진행하면 됩니다.

---

## 0. 사전 확인

```bash
# [서버] Docker / Docker Compose 설치 여부 확인
docker --version
docker compose version
```

설치가 안 돼 있다면:

```bash
# [서버] Docker 설치 (Ubuntu/Debian/RHEL 계열 공통 스크립트)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # 적용하려면 재접속 필요
```

---

## 1. 데이터 저장 폴더 준비

GitLab 컨테이너 자체는 언제든 삭제·재생성할 수 있어야 하므로, 실제 데이터(설정·로그·
저장소·DB)는 컨테이너 밖 폴더에 저장한다.

```bash
# [서버]
sudo mkdir -p /srv/gitlab/{config,logs,data}
cd /srv/gitlab
```

---

## 2. docker-compose.yml 작성

```bash
# [서버]
nano docker-compose.yml
```

```yaml
services:
  gitlab:
    image: gitlab/gitlab-ce:latest
    container_name: gitlab
    restart: always
    hostname: <도메인>                 # 예: gapps.gnu.ac.kr
    environment:
      GITLAB_OMNIBUS_CONFIG: |
        external_url 'https://<도메인>/gitlab'
        # 중요: 아래 두 줄이 없으면 GitLab이 "자기 자신의 SSL 인증서"를 찾다가
        # 없어서 내부 nginx가 아예 기동을 못 하고 502 에러가 난다(5번 문제 참고).
        # 외부 nginx가 이미 HTTPS를 처리해주므로, 컨테이너 내부는 평문 HTTP로만 동작하게 한다.
        nginx['listen_port'] = 80
        nginx['listen_https'] = false
        gitlab_rails['gitlab_shell_ssh_port'] = 2224
    ports:
      - "8929:80"     # 웹 (호스트 nginx가 이 포트로 리버스 프록시)
      - "8943:443"    # 사용 안 해도 매핑만 해둠(내부 SSL 비활성 상태라 실질 사용 안 함)
      - "2224:22"     # git clone/push용 SSH (OS 기본 22번과 겹치지 않게 분리)
    volumes:
      - /srv/gitlab/config:/etc/gitlab
      - /srv/gitlab/logs:/var/log/gitlab
      - /srv/gitlab/data:/var/opt/gitlab
    shm_size: '256m'
```

> **참고 — 경로(`/gitlab`) 방식 vs 서브도메인 방식**
> `https://도메인/gitlab`처럼 경로를 쓰는 방식은 GitLab 공식 문서에서 비권장하는
> 구성이다. 가능하면 `https://gitlab.<학교도메인>`처럼 **완전한 서브도메인**을 새로
> 발급받는 쪽을 추천한다. 그러면 아래 5번(리버스 프록시)·7번(경로 전달) 설정이
> 훨씬 단순해진다. 경로 방식으로 가야 한다면 이 매뉴얼 그대로 따라가면 된다.

---

## 3. 컨테이너 실행

```bash
# [서버]
docker compose up -d
docker compose logs -f gitlab   # 최초 기동 2~5분 소요. Ctrl+C로 보기 종료 가능
docker compose ps               # STATUS가 "Up ... (healthy)"인지 확인
```

---

## 4. 초기 관리자(root) 비밀번호 확인 및 변경

```bash
# [서버] — 최초 24시간 동안만 유효
sudo docker exec -it gitlab grep 'Password:' /etc/gitlab/initial_root_password
```

- `https://<도메인>/gitlab` 접속 → `root` / 위 비밀번호로 로그인
- 로그인 직후 **프로필 → Edit profile → Password**에서 바로 새 비밀번호로 변경

---

## 5. 리버스 프록시(nginx) 설정

GitLab이 다른 사이트와 같은 서버·같은 nginx를 공유하는 경우, `/gitlab` 경로로 들어온
요청만 컨테이너(8929번 포트)로 넘겨줘야 한다. 기존 nginx 설정 파일(예:
`/etc/nginx/conf.d/<파일명>.conf`)의 `server { listen 443 ssl; ... }` 블록 안,
마지막 `}` 직전에 아래 추가:

```nginx
    location = /gitlab {
        return 301 /gitlab/;
    }

    location /gitlab/ {
        proxy_pass http://127.0.0.1:8929;   # 끝에 슬래시 없음! (경로를 그대로 전달해야 함)
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;            # 큰 저장소 clone/push 대비
        client_max_body_size 0;             # 전체 기본값과 별개로 이 구간만 무제한
    }
```

> `proxy_pass` 끝에 슬래시가 있으면 nginx가 `/gitlab/` 부분을 떼고 넘기고,
> 없으면 그대로 넘긴다. GitLab은 `external_url`에 `/gitlab`이 포함돼 있어서
> **그대로 전달**해야 한다(슬래시 없이).

```bash
# [서버]
sudo cp /etc/nginx/conf.d/<파일명>.conf /etc/nginx/conf.d/<파일명>.conf.bak   # 백업
sudo nginx -t                      # 문법 검증, "syntax is ok" 확인
sudo systemctl reload nginx
```

브라우저에서 `https://<도메인>/gitlab` 재접속 → 로그인 화면이 뜨면 성공.

---

## 6. 겪었던 오류와 해결책

### 6-1. `502 Bad Gateway`
**원인**: 2번 단계에서 `nginx['listen_https']`를 안 끄면, GitLab이 자기 몫의 SSL
인증서(`/etc/gitlab/ssl/<도메인>.crt`)를 찾다가 없어서 내부 nginx가 기동 실패.
**해결**: docker-compose.yml에 `nginx['listen_port'] = 80` / `nginx['listen_https'] = false`
추가 후 `docker compose up -d`로 컨테이너 재생성.

```bash
# 진단에 쓴 명령들
docker exec -it gitlab gitlab-ctl status
docker exec -it gitlab tail -n 50 /var/log/gitlab/nginx/error.log
```

### 6-2. `{"error":"The requested URL was not found on the server..."}`
**원인**: 리버스 프록시(5번)를 설정하기 전이라, `/gitlab` 요청이 그 도메인의
**기존 다른 앱**으로 흘러가서 그 앱이 404를 응답한 것. GitLab까지 요청이 도달하지도
못한 상태였음.
**해결**: 5번의 nginx `location /gitlab/` 블록 추가.

### 6-3. `fatal: unable to access '...': SSL certificate problem: unable to get local issuer certificate`
**원인**: nginx가 내려주는 인증서 체인 자체는 정상(leaf + intermediate 2개)인데,
**git을 실행하는 서버(클라이언트 쪽) OS의 CA 신뢰 목록이 오래돼서** 새로 쓰이는
중간 인증기관(예: Sectigo의 최신 intermediate)을 인식 못 함.
**해결**:
```bash
sudo dnf update ca-certificates -y    # 또는 sudo yum update ca-certificates -y
sudo update-ca-trust extract
```
**진단에 쓴 명령**:
```bash
# 서버가 실제로 몇 개의 인증서를 보내는지 확인 (-showcerts 꼭 필요, 없으면 1개만 보임)
openssl s_client -connect <도메인>:443 -servername <도메인> -showcerts </dev/null 2>/dev/null \
  | grep -c "BEGIN CERTIFICATE"
```

### 6-4. SSH(`git@<도메인>:2224`)로 clone/pull이 안 될 때
**원인 후보 1 — 방화벽**: `git` SSH용으로 연 포트(예: 2224)가 `firewall-cmd`에 안
열려 있는 경우.
```bash
sudo firewall-cmd --list-ports                      # 확인
sudo firewall-cmd --permanent --add-port=2224/tcp    # 추가
sudo firewall-cmd --reload
```
**원인 후보 2 — 서버 접속 통제 솔루션(HIWARE 등)**: 공공기관 서버에 흔히 깔려있는
세션 감사/명령어 통제 프로그램이 `ssh` 명령 자체를 금지어로 막아버리는 경우가 있다.
이 경우 SSH 방식 자체를 포기하고 **HTTPS + 토큰 방식**으로 전환하는 게 가장 간단한
해결책이다(아래 8번 참고). `git fetch`/`git pull`처럼 "ssh"라는 단어가 직접 안 보이는
명령은 통과될 수도 있으니 먼저 시도해볼 가치는 있다.

---

## 7. 기존 GitHub 저장소 통째로 이전하기

```bash
# [로컬]
mkdir gitlab_migration && cd gitlab_migration
git clone --mirror https://github.com/<계정>/<저장소>.git
cd <저장소>.git
git push --mirror https://oauth2:<PERSONAL_ACCESS_TOKEN>@<도메인>/gitlab/<그룹>/<프로젝트>.git
```

- `--mirror`로 복사하면 모든 커밋·브랜치 이력이 그대로 옮겨진다.
- `<PERSONAL_ACCESS_TOKEN>`은 GitLab 웹 → 프로필 → **Access Tokens** →
  **Legacy token** → scope `write_repository`, `api` 체크해서 발급한 값.
  **생성 직후 화면에서만 보이므로 그 자리에서 바로 복사해둘 것.**
- 마이그레이션 전용으로 만든 토큰은 작업이 끝나면 **Revoke(폐기)** 한다.

---

## 8. 평소 작업 환경(로컬)의 원격 주소 전환

```bash
# [로컬] 이미 작업 중이던 프로젝트 폴더에서
git remote rename origin github                 # 기존 GitHub 주소는 보존(백업용)
git remote add origin https://<도메인>/gitlab/<그룹>/<프로젝트>.git
git remote -v                                   # 확인
```

이후 `git push` / `git pull`은 기본적으로 `origin`(=GitLab)을 대상으로 동작한다.
GitHub에도 계속 올리고 싶다면 `git push github main`처럼 이름을 명시하면 된다.

평소 작업용 **개인 토큰**(마이그레이션용과 별개, 만료기간 길게)을 하나 더 만들어서
처음 push할 때 비밀번호 대신 입력해두면, Windows의 Git Credential Manager가
저장해줘서 이후로는 다시 안 물어본다.

---

## 9. 서버 쪽 — 원격 저장소를 GitLab으로 전환 + 자동 pull 준비

서버에 이미 clone돼 있는 운영 코드 폴더의 origin도 GitLab으로 바꿔야 한다.
SSH 방식이 막히는 환경(6-4번 참고)이라면 **Deploy Token**(읽기 전용, 서버 배포
전용으로 설계된 토큰)으로 HTTPS 인증을 쓴다.

1. GitLab 웹 → 프로젝트 → **Settings → Repository → Deploy tokens** → **Add token**
   - Name: `server-pull`, Expiration: 비워두면 무기한, Scope: `read_repository`만 체크
   - 생성 직후 나오는 **Username**과 **Deploy token** 값을 복사해둔다(한 번만 표시).

```bash
# [서버]
cd <운영 코드 폴더>
git remote set-url origin https://<DEPLOY_USERNAME>:<DEPLOY_TOKEN>@<도메인>/gitlab/<그룹>/<프로젝트>.git
git fetch origin
git pull origin main
```

---

## 10. 배포 스크립트 (수동 1회 실행용)

```bash
# [서버]
nano <운영 코드 폴더>/deploy.sh
```

```bash
#!/bin/bash
# [자동배포] GitLab에 새 커밋이 있으면 받아와서 서비스를 재시작한다.
# 변경사항이 없으면 아무것도 안 하고 조용히 끝난다.
set -e
cd <운영 코드 폴더>

LOG=<운영 코드 폴더>/deploy.log
echo "[$(date '+%F %T')] 확인 시작" >> "$LOG"

git fetch origin main >> "$LOG" 2>&1

LOCAL=$(git rev-parse main)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "[$(date '+%F %T')] 변경 없음" >> "$LOG"
    exit 0
fi

echo "[$(date '+%F %T')] 새 커밋 발견 ($LOCAL -> $REMOTE), 배포 시작" >> "$LOG"
git pull origin main >> "$LOG" 2>&1
sudo systemctl restart <서비스 유닛 이름>
echo "[$(date '+%F %T')] 배포 완료" >> "$LOG"
```

```bash
# [서버]
chmod +x <운영 코드 폴더>/deploy.sh
```

**root가 아닌 계정으로 서비스를 재시작해야 한다면**, 비밀번호 없이 딱 그 명령만
허용하도록 제한해서 등록:

```bash
# [서버]
echo "<사용자계정> ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart <서비스 유닛 이름>" \
  | sudo tee /etc/sudoers.d/deploy-restart
sudo chmod 440 /etc/sudoers.d/deploy-restart
sudo visudo -c   # 문법 검증
```

**짧게 명령 치기용 alias**(선택):

```bash
# [서버]
echo "alias deploy='<운영 코드 폴더>/deploy.sh && tail -5 <운영 코드 폴더>/deploy.log'" >> ~/.bashrc
source ~/.bashrc
```

이후로는 로컬에서 `git push` 하고, 서버에서 `deploy` 한 번 치면 pull + 재시작까지
끝난다.

---

## 11. (선택) 더 나아가려면 — 완전 자동화

지금 구성은 "서버에서 직접 `deploy` 명령을 쳐야" 배포되는 방식이다. push하자마자
사람 개입 없이 자동으로 배포되길 원하면:

- **GitLab CI/CD + Runner**: 서버에 GitLab Runner를 설치해 등록하고, 레포에
  `.gitlab-ci.yml`을 추가해 `main` push 시 자동으로 10번의 `deploy.sh`를 실행하게
  만드는 방식. 가장 "정석"이지만 Runner 설치·등록이 한 단계 더 필요하다.
- **cron 폴링**: `deploy.sh`를 1~5분마다 cron으로 돌려 변경사항을 주기적으로
  확인하는 방식. 설정은 가장 간단하지만 실시간은 아니다(최대 몇 분 지연).

필요해지면 그때 추가로 설계하면 된다.
