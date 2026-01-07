"""
Verification Script for Ingestion Pipeline

Robust KG Extraction Pipeline을 검증합니다.
"""

import sys
import asyncio
import logging
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.loaders.csv_loader import CSVLoader

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Setting up verification...")

    # 1. Setup Loader
    csv_path = Path(__file__).parent / "sample_data.csv"
    if not csv_path.exists():
        logger.error(f"Sample data not found: {csv_path}")
        return

    loader = CSVLoader(csv_path)

    # 2. Setup Pipeline
    pipeline = IngestionPipeline()

    # 3. Run Pipeline
    logger.info("Running pipeline with sample data...")
    try:
        await pipeline.run(loader)
        logger.info("✅ Verification Passed")
    except Exception as e:
        logger.error(f"❌ Verification Failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
