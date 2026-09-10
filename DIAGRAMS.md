# 그림으로 보는 시스템 — UML · 순서도

> 글보다 그림으로 이해할 수 있게 정리한 문서입니다. 모든 그림은 GitHub에서 바로 렌더링되는
> **Mermaid** 표기(UML 2.x / 순서도 표준 도형)로 작성했습니다.
> VS Code에서는 "Markdown Preview Mermaid Support" 확장을 설치하면 미리보기에서 보입니다.

---

## 1. 전체 구성도 (Component Diagram)

"누가 어디에 있고, 무엇과 연결되는가" — 한 장으로 보는 시스템 뼈대.

```mermaid
flowchart LR
    subgraph USER["👤 사용자"]
        B["웹 브라우저<br/>(PC · 모바일)"]
    end

    subgraph SRV["🖥 운영 서버 (Linux, gapps.gnu.ac.kr)"]
        N["nginx<br/>80 / 443"]
        W["주간업무보고<br/>:8080 (기존)"]
        subgraph APP["규정 통합 검색 서비스 :8000 (systemd)"]
            API["FastAPI 서버<br/>api_server.py"]
            WEB["웹 화면<br/>web/ (HTML·CSS·JS)"]
            SE["검색 엔진<br/>search_engine.py"]
            RAG["AI 답변 엔진<br/>rag_engine.py"]
        end
        subgraph DATA["📦 데이터"]
            VDB[("벡터DB<br/>ChromaDB")]
            CH[("청크 9,258개<br/>chunks.json")]
            RG[("규정 426건 메타<br/>regulations.json")]
            TXT[("규정 원문<br/>*.txt")]
        end
    end

    subgraph EXT["☁ 외부"]
        LAW["국가법령정보센터<br/>law.go.kr"]
        GNU["경상국립대 홈페이지<br/>산학협력단 규정집"]
        LLM["FactChat API<br/>Claude Haiku 4.5"]
    end

    B -- "https://gapps.gnu.ac.kr/" --> N --> W
    B -- "https://gapps.gnu.ac.kr/regulation/" --> N --> API
    API --> WEB
    API --> SE
    API --> RAG
    RAG --> SE
    SE --> VDB & CH & RG
    API --> TXT
    RAG -. "질문 재작성 · 답변 생성" .-> LLM
    LAW & GNU -. "수집 (refresh_all.py)" .-> DATA
```

---

## 2. 데이터 준비 순서도 (Flowchart) — 규정이 바뀌면 `refresh_all.py` 한 줄

```mermaid
flowchart TD
    S(["시작: python scripts/refresh_all.py"]) --> C1["① 수집<br/>collect_all.py"]
    C1 --> C1a["대학: 홈페이지 목록 → law.go.kr 원문<br/>산학협력단: 규정집(HWPX) 분할"]
    C1a --> C2["①-2 메타 보강<br/>enrich_dates.py"]
    C2 --> C2a["law.go.kr 헤더 파싱<br/>[시행일] [규정번호, 공포일, 개정종류]"]
    C2a --> D1{폐지 표기?}
    D1 -- 예 --> C2b["status = 폐지"]
    D1 -- 아니오 --> C2c["status = 현행"]
    C2b & C2c --> C3["② 청킹<br/>chunk_rules.py"]
    C3 --> C3a["'제N조 ①…' 단위로 분할<br/>소속 장(章) 제목 부착<br/>→ chunks.json · dataset_meta.json"]
    C3a --> C4["③ 임베딩 · 벡터DB<br/>build_vectordb.py"]
    C4 --> C4a["KR-SBERT로 '뜻 → 숫자'<br/>→ ChromaDB 저장 (약 8분)"]
    C4a --> C5["④ 품질 점검<br/>evaluate_search.py --direct"]
    C5 --> D2{15/15 통과?}
    D2 -- 예 --> E(["완료: 서버 재시작 후 반영"])
    D2 -- 아니오 --> F["개발 담당자 확인<br/>(search_engine.py 가중치·사전)"]
```

---

## 3. 검색 순서도 (Flowchart) — 🔍 검색 탭, 0.05초

```mermaid
flowchart TD
    A(["사용자 입력<br/>예) 휴학 / 자퇴 절차"]) --> Q{"질문형 문장?<br/>물음표·어떻게·언제…"}
    Q -- "예" --> W1["가중치: 의미 75% + 키워드 25%"]
    Q -- "아니오" --> W2["가중치: 의미 60% + 키워드 40%"]
    W1 & W2 --> P

    subgraph P["병렬 검색"]
        direction LR
        V["의미 검색<br/>질문을 KR-SBERT 벡터로 →<br/>벡터DB에서 유사 조항 200개"]
        K["키워드 검색 (BM25)<br/>동의어 확장: 자퇴→퇴학, 학고→학사경고"]
    end

    P --> M["점수 합산 · 정규화"]
    M --> G1{관련성 최소 기준<br/>의미 ≥ 0.44 또는 키워드 일치?}
    G1 -- 미달 --> N0["결과 없음<br/>+ 추천 검색어 · 담당부서 안내"]
    G1 -- 충족 --> G2{폐지 규정?<br/>토글 OFF & 질문에 '폐지' 없음}
    G2 -- 제외 --> R
    G2 -- 통과 --> R["부설고·중학교 학칙<br/>×0.85 감점 (질문에 부설 표현 없을 때)"]
    R --> O["상위 N건 정렬<br/>+ 시행일·담당부서·상태 메타 부착"]
    O --> Z([결과 카드 표시<br/>미리보기 · 원문 이동])
```

---

## 4. AI 질문하기 순서도 (Flowchart) — 💬 근거만 보고 답하는 AI, 여러 겹의 안전장치

```mermaid
flowchart TD
    A(["질문 입력<br/>예) 휴학 신청은 언제까지 해야 해?"]) --> B{"외부 API<br/>사용 중?"}
    B -- "예" --> B1["① 질의 재작성 (LLM)<br/>→ 휴학 신청 시기 및 절차"]
    B -- "아니오 (로컬 Qwen)" --> B2["원문 그대로"]
    B1 --> B3{"무관한 질문?<br/>LLM이 N/A 응답"}
    B3 -- "예" --> B2
    B3 -- "아니오" --> C
    B2 --> C["② 하이브리드 검색<br/>(3번 순서도와 동일, 폐지 제외)"]
    C --> D["③ 재순위화 (cross-encoder)<br/>상위 20개를 질문과 1대1 정밀 비교"]
    D --> D1["게이트: 하이브리드 점수가<br/>1위보다 0.05 이상 낮은 후보는 승격 금지"]
    D1 --> E{"🛡 관련성 문턱<br/>1위 점수 ≥ 0.5?"}
    E -- "아니오" --> X1(["해당 내용은 규정에서<br/>찾을 수 없습니다<br/>(AI 호출 없음)"])
    E -- "예" --> F["④ 참고자료 조립<br/>상위 5개 조항 원문 전체"]
    F --> G["⑤ 답변 생성 (LLM)<br/>규칙: 참고자료 밖 내용 금지<br/>수치 없으면 찾을 수 없다고 먼저"]
    G --> H["⑥ 검증 가드레일"]
    H --> H1{"근거 목록에 없는<br/>규정명 인용?"}
    H1 -- "예" --> W1["⚠️ 자동 경고 문구 추가"]
    H1 -- "아니오" --> H2
    W1 --> H2{"참고자료에 없는<br/>숫자 사용?"}
    H2 -- "예" --> W2["⚠️ 자동 경고 문구 추가"]
    H2 -- "아니오" --> I
    W2 --> I["근거 조항 목록 첨부"]
    I --> Z(["답변 + 근거 카드 표시<br/>로그 기록 (개인정보 없음)"])
    G -. "60초 초과 / 오류" .-> X2(["검색 결과만 반환<br/>(검색 전용 모드)"])
```

---

## 5. 시퀀스 다이어그램 (Sequence) — AI 질문 한 번에 누가 무엇을 주고받나

```mermaid
sequenceDiagram
    actor U as 사용자
    participant W as 웹 화면<br/>(app.js)
    participant A as FastAPI<br/>(api_server.py)
    participant R as RAG 엔진<br/>(rag_engine.py)
    participant S as 검색 엔진<br/>(search_engine.py)
    participant V as 벡터DB<br/>(ChromaDB)
    participant L as Claude Haiku 4.5<br/>(FactChat API)

    U->>W: 질문 입력
    W->>A: POST /api/ask {question}
    A->>R: answer(question)
    R->>L: 질의 재작성 요청 (규정 문체로)
    L-->>R: '휴학 신청 시기 및 절차' (또는 N/A)
    R->>S: search(query, rerank=True)
    S->>V: 유사 벡터 200개 조회
    V-->>S: 후보 + 유사도
    S->>S: BM25 · 점수 합산 · 폐지 제외 · 재순위화
    S-->>R: 상위 5개 조항 (+시행일·상태)
    alt 1위 점수 < 0.5
        R-->>A: "규정에서 찾을 수 없습니다" (LLM 호출 없음)
    else 충분히 관련 있음
        R->>L: 참고자료 5개 + 질문 + 규칙
        L-->>R: 답변 문장
        R->>R: 규정명·숫자 가드레일 검사, 근거 목록 첨부
        R-->>A: 답변 + 근거
    end
    A->>A: 로그 기록 (data/rag_logs/)
    A-->>W: JSON {answer, results}
    W-->>U: 답변 말풍선 + 근거 조항 카드
```

---

## 6. 클래스 다이어그램 (Class) — 핵심 모듈과 관계

```mermaid
classDiagram
    direction LR

    class SearchEngine {
        +chunks : list
        +reg_by_id : dict
        +model : SentenceTransformer (KR-SBERT)
        +collection : ChromaDB
        +bm25 : BM25
        -_reranker : CrossEncoder
        +search(query, top_k, sources, categories, rerank, include_repealed) dict
        +get_chunk(chunk_id) dict
        +get_regulation_fulltext(reg_id) dict
        -_lazy_reranker()
        -_minmax_norm()
    }

    class RagEngine {
        <<module>>
        +TOP_N_FOR_CONTEXT = 5
        +MIN_TOP_SCORE_FOR_ANSWER = 0.5
        +answer(query) dict
        +retrieve(query) dict
        +rewrite_query(query, backend) str
        +build_context(search_result) str
        +apply_citation_guardrail(answer) str
        +apply_number_guardrail(answer, context) str
    }

    class LLMBackend {
        <<abstract>>
        +generate(system_prompt, user_prompt) str
        +is_available() bool
    }
    class OpenAICompatibleBackend {
        +api_base : GNU_RAG_API_BASE
        +model_name : GNU_RAG_API_MODEL
        +generate()
    }
    class LocalHFBackend {
        +MODEL_NAME = Qwen2.5-1.5B
        -_generate_lock : Lock
        +generate()
    }

    class ApiServer {
        <<FastAPI>>
        +GET /api/search
        +POST /api/ask
        +GET /api/filters
        +GET /api/chunks/{id}
        +GET /api/regulations/{id}
        +StaticFiles web/
    }

    class Regulation {
        +id, name, source, category
        +department, contact
        +enforce_date, revision_date
        +revision_type, rule_no
        +status : 현행 | 폐지
        +text_file, law_url
    }
    class Chunk {
        +chunk_id, reg_id
        +article, article_title, clause
        +chapter
        +text
    }

    ApiServer --> SearchEngine : 검색 탭
    ApiServer --> RagEngine : AI 질문 탭
    RagEngine --> SearchEngine : retrieve()
    RagEngine --> LLMBackend : generate()
    LLMBackend <|-- OpenAICompatibleBackend
    LLMBackend <|-- LocalHFBackend
    SearchEngine "1" o-- "9,258" Chunk
    SearchEngine "1" o-- "426" Regulation
    Regulation "1" *-- "n" Chunk
```

---

## 7. 배포 다이어그램 (Deployment) — 업무보고 서버와 포트 공유

```mermaid
flowchart TB
    subgraph LAN["학내망 (현재 정보전산처 공개 단계)"]
        PC["직원 PC / 휴대폰"]
    end

    subgraph HOST["gapps.gnu.ac.kr — Linux (CentOS 계열, VMware)"]
        direction TB
        NG["nginx :80 → 301 → :443 (TLS)"]
        subgraph LOC["location 규칙 (gapps.conf)"]
            L1["/            → 127.0.0.1:8080"]
            L2["/regulation/ → 127.0.0.1:8000<br/>(접두어 제거해 전달)"]
        end
        GU["gunicorn :8080<br/>주간업무보고 (기존)"]
        UV["uvicorn :8000<br/>gnu-regulation-search.service<br/>(systemd · 재부팅 자동시작)"]
        ENV["Environment=<br/>GNU_VECTORDB=/var/lib/gnu_vectordb<br/>GNU_RAG_API_KEY · _BASE · _MODEL"]
        VD[("/var/lib/gnu_vectordb")]
        REPO["/…/Academic_Regulations_AIProject<br/>(git pull로 갱신)"]
    end

    subgraph CLOUD["외부"]
        FC["FactChat 브리지<br/>hello.timelygpt.co.kr → Claude Haiku 4.5"]
        GH["GitHub 저장소<br/>(코드·데이터 정본)"]
    end

    PC -->|https| NG --> LOC
    L1 --> GU
    L2 --> UV
    ENV -.-> UV
    UV --> VD
    UV --> REPO
    UV -.->|https, API 키| FC
    GH -.->|git pull| REPO
```

---

## 8. 상태 다이어그램 (State) — 규정 한 건의 생애

```mermaid
stateDiagram-v2
    [*] --> 수집됨 : collect_all.py
    수집됨 --> 메타보강 : enrich_dates.py<br/>(시행일·개정종류·규정번호)
    메타보강 --> 현행 : 개정종류 ≠ 폐지
    메타보강 --> 폐지 : 개정종류 = 폐지 / 타법폐지<br/>또는 규정명에 '폐지'
    현행 --> 청킹됨 : chunk_rules.py
    폐지 --> 청킹됨 : chunk_rules.py<br/>(본문은 유지)
    청킹됨 --> 색인됨 : build_vectordb.py
    색인됨 --> 검색노출 : 현행 → 기본 노출
    색인됨 --> 숨김 : 폐지 → 기본 제외<br/>('폐지된 규정도 포함' 토글 시 빨간 배지로 노출)
    검색노출 --> 수집됨 : 규정 개정 → refresh_all.py
    숨김 --> 수집됨 : refresh_all.py
```

---

## 9. 운영자 의사결정 순서도 — "문제가 생겼을 때 어디를 보나"

```mermaid
flowchart TD
    A([이상 신고 접수]) --> B{어떤 증상?}
    B -- 화면이 안 열림 --> C1["서버 상태 확인<br/>systemctl status gnu-regulation-search"]
    C1 --> C1a{active?}
    C1a -- 아니오 --> C1b["journalctl -u … -n 50<br/>→ 재시작 / 개발 담당자"]
    C1a -- 예 --> C1c["nginx -t · reload<br/>/regulation/ 규칙 확인 (MANUAL 9-8-1)"]
    B -- 검색 결과가 이상함 --> C2["evaluate_search.py --direct<br/>evaluate_academic.py"]
    C2 --> C2a{100%?}
    C2a -- 아니오 --> C2b["search_engine.py 가중치·동의어 사전<br/>→ 개발 담당자"]
    C2a -- 예 --> C2c["해당 규정만 갱신<br/>refresh_all.py --skip-collect --name …"]
    B -- AI 답변이 이상함 --> C3["화면의 근거 조항 확인<br/>data/rag_logs/YYYY-MM-DD.jsonl"]
    C3 --> C3a{근거 조항이<br/>질문과 맞나?}
    C3a -- 아니오 --> C3b["검색 문제 → C2로"]
    C3a -- 예 --> C3c["evaluate_rag.py 실행<br/>프롬프트·가드레일 → 개발 담당자"]
    B -- AI가 너무 느림 --> C4["서버 로그에<br/>'[RAG] 외부 API 백엔드 사용' 있나?"]
    C4 -- 없음 --> C4a["환경변수(API 키) 미설정<br/>→ MANUAL 6-2 · 9-6 Environment="]
    C4 -- 있음 --> C4b["API 401/400 → 키·모델명 확인<br/>정상인데 느리면 재순위화 단계(~10초)"]
```

---

### 그림 읽는 법 (범례)

| 도형 | 뜻 |
|---|---|
| `([ … ])` 둥근 모서리 | 시작 / 끝 |
| `[ … ]` 사각형 | 처리 단계 |
| `{ … }` 마름모 | 판단(분기) |
| `[( … )]` 원통 | 데이터 저장소 |
| 점선 화살표 | 외부 호출 · 조건부 흐름 |
| 실선 화살표 | 기본 흐름 · 의존 |

관련 문서: [README.md](README.md) (개발 현황·근거) · [MANUAL.md](MANUAL.md) (운영 매뉴얼) · [PRD.md](PRD.md)
