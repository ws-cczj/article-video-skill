"""Add measured sentence pauses to Chinese narration without changing its text."""
from pathlib import Path
import wave
import numpy as np


def apply_cadence(source,destination,cues,profile='zh-explainer'):
    with wave.open(str(source),'rb') as wav:
        fmt=wav.getparams()
        if (fmt.nchannels,fmt.sampwidth,fmt.framerate)!=(1,2,48000):
            raise ValueError('Cadence input must be 48kHz mono PCM16')
        samples=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').copy()
    clean=[dict(c) for c in cues]
    if profile not in ('zh-explainer','service'):raise ValueError('Unknown cadence profile')
    for left,right in zip(clean,clean[1:]):
        if right['start']<left['end']:left['end']=right['start']
    insertions=[]
    if profile=='zh-explainer':
        for left,right in zip(clean,clean[1:]):
            desired=.32 if left['text'].rstrip().endswith(('？','?','！','!')) else .18
            gap=max(0,right['start']-left['end'])
            count=round(max(0,desired-gap)*48000)
            if count:
                position=round(right['start']*48000)
                if not 0<=position<=len(samples):raise ValueError('Speech boundary exceeds WAV')
                insertions.append((position,count))
    chunks=[];cursor=0
    for position,count in insertions:
        part=samples[cursor:position].copy().astype(float)
        fade=min(144,len(part)//2)
        if fade:
            part[-fade:]*=np.linspace(1,0,fade)
            # Fade into the next section at a newly inserted pause boundary.
            if cursor:part[:fade]*=np.linspace(0,1,fade)
        chunks.extend([np.rint(part).astype('<i2'),np.zeros(count,dtype='<i2')]);cursor=position
    tail=samples[cursor:].copy().astype(float)
    fade=min(144,len(tail)//2)
    if cursor and fade:tail[:fade]*=np.linspace(0,1,fade)
    chunks.append(np.rint(tail).astype('<i2'))
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(destination),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000)
        for part in chunks:wav.writeframes(part.tobytes())
    for cue in clean:
        start=round(cue['start']*48000);end=round(cue['end']*48000)
        cue['start']=(start+sum(n for pos,n in insertions if pos<=start))/48000
        cue['end']=(end+sum(n for pos,n in insertions if pos<end))/48000
    return clean,sum(n for _,n in insertions)/48000
