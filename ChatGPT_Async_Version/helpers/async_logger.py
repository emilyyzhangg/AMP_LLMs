import asyncio, logging
logger = logging.getLogger('amp_llm')
def configure(level=logging.INFO):
    logging.basicConfig(level=level, format='%(asctime)s %(levelname)s: %(message)s')