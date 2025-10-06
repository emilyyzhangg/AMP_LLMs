import asyncio, aiofiles
async def read_text(path): 
    async with aiofiles.open(path,'r',encoding='utf-8') as f:
        return await f.read()