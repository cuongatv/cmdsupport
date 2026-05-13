"""Progress helpers shared by ingestion workers and MRP phases."""

import uuid

from loguru import logger


class ProgressTracker:
    """Updates source.progress and source.progress_message in the database."""

    def __init__(self, source_id: uuid.UUID):
        self.source_id = source_id

    async def update(self, progress: int, message: str) -> None:
        from app.database import async_session_factory
        from app.database.models import Source

        async with async_session_factory() as session:
            source = await session.get(Source, self.source_id)
            if source:
                source.progress = progress
                source.progress_message = message
                await session.commit()
        logger.debug(f"[{self.source_id}] Progress: {progress}% - {message}")
