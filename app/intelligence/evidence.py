from app.domain import PaperComparison, PaperSummary, SourceText


def validate_evidence(output: PaperSummary | PaperComparison, sources: list[SourceText]) -> None:
    lookup = {(s.paper_id, c.id): c.text for s in sources for c in s.chunks}
    fields = output.model_dump(exclude={"evidence", "confidence", "importance"})
    claims = {key for key, value in fields.items() if value}
    supported = set()
    for evidence in output.evidence:
        text = lookup.get((evidence.paper_id, evidence.chunk_id))
        if text is None or evidence.quote not in text or evidence.field not in claims:
            raise ValueError("evidence must quote a supplied chunk and identify a claim field")
        supported.add(evidence.field)
    if claims - supported:
        raise ValueError("every nonempty claim field requires evidence")
    if isinstance(output, PaperComparison):
        cited = {e.paper_id for e in output.evidence}
        if sources[0].paper_id not in cited or not (cited - {sources[0].paper_id}):
            raise ValueError("comparison must cite current and prior paper")
