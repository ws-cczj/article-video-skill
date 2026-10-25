"""Optional online neural narration with service-provided sentence boundaries.

Only narration text is sent to Microsoft's online service through edge-tts.
No PDF, reference recording, or creator voice is uploaded.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


async def synthesize(args):
    import edge_tts
    path = Path(args.storyboard).resolve()
    story = json.loads(path.read_text(encoding='utf-8-sig'))
    cadence=args.cadence
    if cadence=='auto':cadence='zh-explainer' if story.get('language','zh-CN').startswith('zh') else 'service'
    seen=set()
    for scene in story['scenes']:
        sid=scene.get('id','')
        if not re.fullmatch('[A-Za-z0-9_-]+',sid) or sid in seen:
            raise ValueError('Scene IDs must be unique safe identifiers.')
        if not isinstance(scene.get('narration'),str) or not scene['narration'].strip():
            raise ValueError(f'{sid}: narration is required.')
        seen.add(sid)
    ffmpeg = shutil.which(args.ffmpeg)
    if not ffmpeg:
        raise RuntimeError('FFmpeg is required to produce normalized PCM WAV.')
    for scene in story['scenes']:
        text = scene['narration']
        fingerprint = hashlib.sha256(json.dumps([text, args.voice, args.rate, args.pitch,args.audio_profile,cadence], ensure_ascii=False).encode()).hexdigest()
        folder = path.parent / 'audio' / scene['id']
        folder.mkdir(parents=True, exist_ok=True)
        manifest = folder / 'speech.json'
        if args.reuse and manifest.exists():
            old = json.loads(manifest.read_text(encoding='utf-8'))
            if old.get('fingerprint') == fingerprint and (folder/'speech.wav').exists():
                scene['speech'] = manifest.relative_to(path.parent).as_posix()
                scene.pop('timing',None)
                print(f'Reused {scene["id"]}', flush=True)
                continue
        for attempt in range(2):
            boundaries = []
            try:
                with (folder/'speech.mp3').open('wb') as audio:
                    stream = edge_tts.Communicate(text, args.voice, rate=args.rate, pitch=args.pitch,
                                                 boundary='SentenceBoundary')
                    async for event in stream.stream():
                        if event['type'] == 'audio':
                            audio.write(event['data'])
                        elif event['type'] == 'SentenceBoundary':
                            boundaries.append({'start': event['offset']/1e7,
                                               'end': (event['offset']+event['duration'])/1e7,
                                               'text': event['text']})
                if not boundaries:
                    raise RuntimeError('No sentence boundaries received; cannot align narration.')
                break
            except Exception:
                if attempt:
                    raise
                await asyncio.sleep(1)
        # Do not normalize each scene independently: preserve one consistent gain
        # across the program. Avoid strong FFT denoising that can add metallic artifacts.
        effect='highpass=f=60,lowpass=f=10000' if args.audio_profile=='clean' else 'anull'
        subprocess.run([ffmpeg, '-y', '-v', 'error', '-i', str(folder/'speech.mp3'),
                        '-af',effect, '-ar', '48000', '-ac', '1', '-c:a','pcm_s16le',str(folder/'decoded.wav')], check=True)
        from chinese_cadence import apply_cadence
        boundaries,added_pause=apply_cadence(folder/'decoded.wav',folder/'speech.wav',boundaries,cadence)
        data = dict(narration=text, voice=args.voice, rate=args.rate, pitch=args.pitch,
                    provider='Microsoft online TTS via edge-tts', fingerprint=fingerprint,
                    audio='speech.wav', cues=boundaries,audio_profile=args.audio_profile,
                    cadence=cadence,added_pause_seconds=added_pause,
                    source_quality='Online service MP3, 24kHz/48kbps; PCM export does not restore lost source detail')
        manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        scene['speech'] = manifest.relative_to(path.parent).as_posix()
        scene.pop('timing',None)
        path.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Synthesized {scene["id"]}: {len(boundaries)} sentence boundaries', flush=True)
    path.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('storyboard')
    parser.add_argument('--voice', default='zh-CN-YunyangNeural')
    parser.add_argument('--rate', default='-6%')
    parser.add_argument('--pitch', default='+0Hz')
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--reuse', action='store_true')
    parser.add_argument('--audio-profile',choices=['clean','raw'],default='clean')
    parser.add_argument('--cadence',choices=['auto','zh-explainer','service'],default='auto')
    args = parser.parse_args()
    asyncio.run(synthesize(args))
