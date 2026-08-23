# -*- coding: utf-8 -*-
"""
用 edge-tts 为每个段落生成俄语配音 mp3 + 逐词时间戳。
可断点续传（已存在且校验通过的跳过）。
输出: ../audio/{pid}.mp3 , ../audio/{pid}.json
"""
import asyncio
import json
import os
import sys

import edge_tts

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.abspath(os.path.join(HERE, "..", "audio"))
VOICE = "ru-RU-SvetlanaNeural"
CONCURRENCY = 6
MAX_RETRY = 4

os.makedirs(AUDIO, exist_ok=True)
LOG = open(os.path.join(HERE, "_audio_log.txt"), "a", encoding="utf-8")


def log(msg):
    print(msg)
    LOG.write(msg + "\n")
    LOG.flush()


async def synth_one(pid: str, text: str, sem: asyncio.Semaphore):
    mp3_path = os.path.join(AUDIO, f"{pid}.mp3")
    js_path = os.path.join(AUDIO, f"{pid}.json")
    # 断点续传：mp3 有内容且 json 可解析则跳过
    if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 2000 and os.path.exists(js_path):
        try:
            json.load(open(js_path, encoding="utf-8"))
            return "skip"
        except Exception:
            pass

    async with sem:
        for attempt in range(1, MAX_RETRY + 1):
            try:
                # 必须显式要求 WordBoundary，edge-tts 7.x 默认是 SentenceBoundary（且常为空）
                comm = edge_tts.Communicate(text, VOICE, boundary="WordBoundary")
                audio = bytearray()
                words = []
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        audio.extend(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        words.append({
                            "t": chunk["text"],
                            # 100ns -> ms
                            "s": round(chunk["offset"] / 10000),
                            "d": round(chunk["duration"] / 10000),
                        })
                if len(audio) < 2000:
                    raise RuntimeError(f"audio too small: {len(audio)} bytes")
                with open(mp3_path, "wb") as f:
                    f.write(bytes(audio))
                json.dump(words, open(js_path, "w", encoding="utf-8"), ensure_ascii=False)
                log(f"OK   {pid}  {len(audio)//1024}KB  words={len(words)}")
                return "ok"
            except Exception as e:
                log(f"RETRY{attempt} {pid}  {type(e).__name__}: {e}")
                await asyncio.sleep(2 * attempt)
        log(f"FAIL {pid}")
        return "fail"


async def main():
    chapters = json.load(open(os.path.join(HERE, "_sentences.json"), encoding="utf-8"))
    jobs = []
    for ch in chapters:
        for p in ch["paras"]:
            text = " ".join(p["sents"])
            jobs.append((p["id"], text))
    log(f"=== total paragraphs: {len(jobs)} voice={VOICE} ===")

    sem = asyncio.Semaphore(CONCURRENCY)
    results = await asyncio.gather(*[synth_one(pid, t, sem) for pid, t in jobs])
    from collections import Counter
    log("=== summary: " + str(dict(Counter(results))) + " ===")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
