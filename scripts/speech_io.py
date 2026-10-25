"""Adapt local/online speech manifests and normalize audio before video encoding."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import wave


def pcm_info(path):
    with wave.open(str(path),'rb') as wav:
        if wav.getnframes()<=0:raise ValueError(f'Empty audio: {path}')
        return (wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getcomptype())


def normalize_pcm(source,destination,ffmpeg):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if not source.is_file():raise FileNotFoundError(source)
    try:valid=pcm_info(source)==(1,2,48000,'NONE')
    except (wave.Error,EOFError):valid=False
    destination.parent.mkdir(parents=True,exist_ok=True)
    if source==destination:
        if not valid:raise ValueError('Normalized audio destination must differ from its source')
        return source
    if valid:shutil.copyfile(source,destination)
    else:
        subprocess.run([ffmpeg,'-v','error','-y','-i',str(source),'-ar','48000','-ac','1',
                        '-c:a','pcm_s16le',str(destination)],check=True,capture_output=True)
    if pcm_info(destination)!=(1,2,48000,'NONE'):raise ValueError('Audio normalization failed')
    return destination


def prepare_scene_audio(scene,root,cache,ffmpeg):
    root,cache=Path(root),Path(cache)
    sid=scene['id']
    if not re.fullmatch('[A-Za-z0-9_-]+',sid):raise ValueError('Invalid scene ID')
    if scene.get('speech'):
        manifest=root/scene['speech']
        data=json.loads(manifest.read_text(encoding='utf-8-sig'))
        if data.get('narration')!=scene['narration']:raise ValueError(f'{sid}: narration changed; regenerate speech')
        audio=normalize_pcm(manifest.parent/data['audio'],cache/f'{sid}.wav',ffmpeg)
        return audio,data
    if not scene.get('timing'):
        raise ValueError(f'{sid}: provide speech or local timing manifest; synthesize narration first')
    manifest=root/scene['timing']
    data=json.loads(manifest.read_text(encoding='utf-8-sig'))
    if data.get('narration')!=scene['narration']:raise ValueError(f'{sid}: narration changed; regenerate speech')
    segments=data.get('segments',[])
    compact=lambda s:re.sub(r'\s+','',s)
    if not segments or compact(''.join(s['text'] for s in segments))!=compact(scene['narration']):
        raise ValueError(f'{sid}: local audio transcript differs from narration')
    # Local synthesize.ps1 stores segment paths relative to the storyboard directory.
    prepared=[normalize_pcm(root/s['audio'],cache/sid/f'{i:04}.wav',ffmpeg) for i,s in enumerate(segments)]
    destination=cache/f'{sid}.wav';cues=[];frames=0
    with wave.open(str(destination),'wb') as merged:
        merged.setnchannels(1);merged.setsampwidth(2);merged.setframerate(48000)
        for segment,path in zip(segments,prepared):
            with wave.open(str(path),'rb') as wav:
                count=wav.getnframes();merged.writeframes(wav.readframes(count))
            cues.append(dict(start=frames/48000,end=(frames+count)/48000,text=segment['text']))
            frames+=count
    return destination,dict(narration=scene['narration'],cues=cues,provider='local sentence WAVs')
