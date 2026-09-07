    vec = [0.0] * dim
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 1) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = sum(v * v for v in vec) ** 0.5
    return [v / norm for v in vec] if norm else vec


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return max(dot / (na * nb), 0.0)


def precision_at_k(retrieved, relevant, k):
    top = retrieved[:k]
    if not top:
        return 0.0
    return sum(1 for r in top if r in relevant) / len(top)


def recall_at_k(retrieved, relevant, k):
    if not relevant:
        return 1.0 if not retrieved[:k] else 0.0
    top = set(retrieved[:k])
    return len(top & relevant) / len(relevant)


def keyword_relevance(answer: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    lower = answer.lower()
    return sum(1 for k in keywords if k.lower() in lower) / len(keywords)


def looks_like_math(text: str) -> bool:
    return bool(re.search(r"\d+\s*[\+\-\*/]\s*\d+", text.lower()))


def main() -> None:
    dataset_path = Path(__file__).parent / "datasets" / "rag_eval_set.json"
    data = json.loads(dataset_path.read_text())
    corpus = data["corpus"]
    corpus_vectors = {d["document_id"]: hash_embed(d["text"]) for d in corpus}

    case_reports = []
    for case in data["cases"]:
        t0 = time.perf_counter()
        qv = hash_embed(case["query"])
        scored = sorted(
            ((cosine(qv, corpus_vectors[d["document_id"]]), d["document_id"]) for d in corpus),
            reverse=True,
        )
        retrieval_latency_ms = (time.perf_counter() - t0) * 1000
        above_threshold = [
            doc_id for score, doc_id in scored if score >= SIMILARITY_THRESHOLD
        ][:TOP_K]

        relevant = set(case["relevant_document_ids"])
        grounded = len(above_threshold) > 0
        expect_grounded = case["expect_grounded"]

        if grounded:
            cited_text = " ".join(
                d["text"] for d in corpus if d["document_id"] in above_threshold
            )
