from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import Paper
from app.storage.repository import PaperRepository


@pytest.mark.integration
async def test_round_trip(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    repo = PaperRepository(session)
    paper = Paper(
        id=uuid4(),
        canonical_id="arxiv:2609.00100",
        title="Agent memory",
        normalized_title="agent memory",
        authors=["A"],
        published_at=now,
        paper_url="https://arxiv.org/abs/2609.00100",
    )
    await repo.create_paper(paper)
    await session.commit()
    await repo.update_paper(paper.id, abstract="A learned memory policy")
    await session.commit()
    session.expunge_all()
    saved = await repo.get_paper(paper.id)
    assert saved and saved.abstract == "A learned memory policy"
    assert len(await repo.list_papers(now - timedelta(days=1), now + timedelta(days=1))) == 1
