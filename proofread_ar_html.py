import os, re, textwrap, asyncio, sys
from pathlib import Path

import openai
from openai import AsyncOpenAI

# Make sure API key is present
if not os.getenv("OPENAI_API_KEY"):
    print("Error: OPENAI_API_KEY environment variable not set.")
    sys.exit(1)

MODEL = "o4-mini"
MAX_CHARS_PER_CHUNK = 127000  # conservative size; model supports ~128k tokens but we stay small

FILES_DIR = Path("files")
FIXED_DIR = FILES_DIR / "fixed"
FIXED_DIR.mkdir(exist_ok=True)

html_files = [
    p for p in FILES_DIR.glob("*.html")
    if p.is_file() and not (FIXED_DIR / p.name).exists()]

SYSTEM_PROMPT = textwrap.dedent(
    """
    Make this HTML science paper looks better. Do not change any words, just improve HTML
    aesthetics. 
    """
)

client = AsyncOpenAI()

async def fix_chunk(chunk: str) -> str:
    response = await client.chat.completions.create(
        model=MODEL,
        temperature=1.,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": chunk},
        ],
    )
    return response.choices[0].message.content

async def process_file(path: Path):
    print(f"Processing {path.name} …")
    content = path.read_text(encoding="utf-8", errors="ignore")

    # quick path when short
    if len(content) <= MAX_CHARS_PER_CHUNK:
        fixed = await fix_chunk(content)
    else:
        # split into chunks by paragraphs to stay inside limit
        parts = re.split(r"(<\/p>)", content, flags=re.IGNORECASE)
        # Build chunks while respecting size
        chunks = []
        buff = ""
        for part in parts:
            if len(buff) + len(part) > MAX_CHARS_PER_CHUNK:
                if buff:
                    chunks.append(buff)
                buff = part
            else:
                buff += part
        if buff:
            chunks.append(buff)

        fixed_parts = []
        for idx, ch in enumerate(chunks):
            print(f"  sending chunk {idx+1}/{len(chunks)}")
            fixed_parts.append(await fix_chunk(ch))
        fixed = "".join(fixed_parts)

    out_path = FIXED_DIR / path.name
    out_path.write_text(fixed, encoding="utf-8")
    print(f"✓ Saved corrected file to {out_path}")

#async def main():
    # Only run on first N files for demo
#    to_process = html_files[:50]
#    await asyncio.gather(*[process_file(p) for p in to_process])
MAX_PARALLEL = 10  # only 10 tasks in parallel

async def process_file_limited(path, sem):
    async with sem:
        await process_file(path)

async def main():
    sem = asyncio.Semaphore(MAX_PARALLEL)
    # Use *all* html_files, or a subset if you want
    to_process = html_files  # or html_files[:50]
    tasks = [process_file_limited(p, sem) for p in to_process]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
