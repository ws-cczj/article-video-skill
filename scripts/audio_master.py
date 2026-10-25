"""Build one lossless audio timeline; normalize once and encode only at final mux."""
import json
import math
from pathlib import Path
import shutil
import subprocess
import wave
import numpy as np


def assemble_pcm(entries, destination, rate=48000):
    """Each entry is (PCM WAV, exact scene duration); append sample-aligned silence."""
    destination=Path(destination)
    with wave.open(str(destination),'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate)
        total=0
        for source,duration in entries:
            with wave.open(str(source),'rb') as wav:
                if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate())!=(1,2,rate):
                    raise ValueError('Master inputs must be 48kHz, mono, PCM16 WAV')
                values=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').astype(np.float64)
            length=round(duration*rate)
            if len(values)>length:raise ValueError('Audio exceeds its scene duration')
            # Only 3ms at the file boundaries; avoids clicks without cutting words.
            fade=min(round(rate*.003),len(values)//2)
            if fade:
                values[:fade]*=np.linspace(0,1,fade)
                values[-fade:]*=np.linspace(1,0,fade)
            out.writeframes(np.rint(values).astype('<i2').tobytes())
            out.writeframes(bytes((length-len(values))*2));total+=length
    return total/rate


def build_master(entries,destination,ffmpeg):
    destination=Path(destination);raw=destination.with_name(destination.stem+'-unnormalized.wav')
    seconds=assemble_pcm(entries,raw)
    first=subprocess.run([ffmpeg,'-v','info','-i',str(raw),'-af','loudnorm=I=-18:TP=-2:LRA=9:print_format=json',
                          '-f','null','-'],check=True,capture_output=True,text=True,encoding='utf-8',errors='replace')
    begin=first.stderr.rfind('{');end=first.stderr.rfind('}')
    stats=json.loads(first.stderr[begin:end+1])
    if not all(math.isfinite(float(stats[key])) for key in ['input_i','input_tp','input_lra','input_thresh','target_offset']):
        # A silent or very short clip has no finite integrated loudness. Preserve
        # PCM instead of passing -inf/inf as invalid FFmpeg filter parameters.
        shutil.copyfile(raw,destination)
        destination.with_suffix('.json').write_text(json.dumps(dict(seconds=seconds,
            normalization='passthrough: no finite integrated loudness',analysis=stats),indent=2),encoding='utf-8')
        return seconds
    parameters=':'.join(f'{key}={stats[field]}' for key,field in [
        ('measured_I','input_i'),('measured_TP','input_tp'),('measured_LRA','input_lra'),
        ('measured_thresh','input_thresh'),('offset','target_offset')])
    effect='loudnorm=I=-18:TP=-2:LRA=9:linear=true:'+parameters
    subprocess.run([ffmpeg,'-v','error','-y','-i',str(raw),'-af',effect,'-ar','48000','-ac','1',str(destination)],check=True)
    destination.with_suffix('.json').write_text(json.dumps(dict(seconds=seconds,source_format='PCM16 mono 48kHz',
        normalization='whole-program, two pass, requested linear gain',analysis=stats,
        note='Measured loudness is not a subjective noise or pronunciation review.'),ensure_ascii=False,indent=2),encoding='utf-8')
    return seconds
