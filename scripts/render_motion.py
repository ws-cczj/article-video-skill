"""Render narrated vector explanations with persistent objects and cue-driven motion.

Objects: text, rect, circle, line, arrow, polygon, image. Object keyframes change
position, size, opacity, scale and line progress. Times can refer to speech cues.
"""
import argparse
import copy
import html
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
from PIL import Image, ImageDraw, ImageFont, ImageOps

from render_video import wrap, timestamp

PALETTE = {'bg':'#252a32', 'ink':'#f7f5ed', 'muted':'#b3bcc8',
           'yellow':'#efcf67', 'cyan':'#69c4d7', 'red':'#e78783', 'green':'#9bc591'}

WARM_COLORS = {
    '#f7f5ed':'#263238', '#69c4d7':'#0c6570', '#efcf67':'#865715',
    '#a9bdd2':'#526369', '#9aaec5':'#596970', '#b3bcc8':'#526369',
    '#e78783':'#9d443b', '#9bc591':'#3e704e', '#213a50':'#e3e9e7',
    '#294650':'#d6e5df', '#244a59':'#c9e1e3', '#5e553b':'#e8d8ba',
    '#387482':'#96bec2', '#162331':'#dce2df', '#3e4955':'#718184',
    '#78818a':'#a1afb1', '#a0a7ad':'#c8d1d0',
}

OBJECT_DEFAULTS = dict(x=0,y=0,width=0,height=0,scale=1,opacity=1,
                       progress=1,stroke_width=2,font_size=26,
                       rotation=0,offset_x=0,offset_y=0)


def _init_frame_worker(root,font,height,backend):
    global _worker_canvas
    _worker_canvas=(QualityCanvas if backend=='skia' else Canvas)(Path(root),font,height)


def _save_frame(task):
    scene,index,count,time,cues,captions,path=task
    _worker_canvas.draw(scene,index,count,time,cues,captions).save(path,compress_level=1)


def event_time(value, cues):
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, dict):
        idx = value['cue']
        if not isinstance(idx, int) or not 0 <= idx < len(cues):
            raise ValueError(f'Invalid speech cue index {idx}')
        result = cues[idx]['start'] + value.get('offset', 0)
    else:
        raise ValueError('Time must be seconds or {cue, offset}')
    if not math.isfinite(result) or result < 0:
        raise ValueError('Time must be finite and nonnegative')
    return result


def object_state(obj, time, cues):
    enter = event_time(obj.get('at', 0), cues)
    end = event_time(obj['until'], cues) if 'until' in obj else math.inf
    if not enter <= time <= end:
        return None
    state = {**OBJECT_DEFAULTS, **copy.deepcopy(obj)}
    keys = obj.get('keyframes', [])
    previous, previous_time = {k:v for k,v in state.items() if k != 'keyframes'}, enter
    for key in keys:
        when = event_time(key['at'], cues)
        if when < previous_time:
            raise ValueError(f'Unordered keyframes for {obj.get("id")}')
        target = {**previous, **{k:v for k,v in key.items() if k != 'at'}}
        if time < when:
            u = min(1, max(0, (time-previous_time)/max(1e-6,when-previous_time)))
            eased = u*u*(3-2*u)
            for k,v in target.items():
                if k in previous and isinstance(v,(int,float)) and isinstance(previous[k],(int,float)):
                    state[k] = previous[k] + (v-previous[k])*eased
                else:
                    state[k] = previous.get(k,v)
            break
        previous, previous_time = target, when
        state.update(target)
    fade = min(1, max(0,(time-enter)/obj.get('fade',0.3))) if obj.get('fade',0.3)>0 else 1
    state['opacity'] = min(1,max(0,state.get('opacity',1)*fade))
    return state


def scene_frames(scene,voice_length,cues,fps):
    """Include all visible events, or reject contradictory explicit boundaries."""
    if not isinstance(fps,int) or not 1<=fps<=120:
        raise ValueError('fps must be an integer between 1 and 120')
    duration=max(voice_length+.3,event_time(scene.get('duration',0),cues))
    for obj in scene['objects']:
        enter=event_time(obj.get('at',0),cues)
        fade=obj.get('fade',.3)
        if not isinstance(fade,(int,float)) or not math.isfinite(fade) or fade<0:
            raise ValueError(f'{obj["id"]}: fade must be finite and nonnegative')
        last=enter
        for key in obj.get('keyframes',[]):
            when=event_time(key['at'],cues)
            if when<last:raise ValueError(f'Unordered keyframes for {obj["id"]}')
            last=when
        if 'until' in obj:
            end=event_time(obj['until'],cues)
            if end<enter or last>end:
                raise ValueError(f'{obj["id"]}: keyframes must lie between at and until')
        else:
            end=max(enter+max(fade,.3),last+.3)
        duration=max(duration,end)
    frames=math.ceil(duration*fps)
    return frames,frames/fps


def split_caption(text, max_chars=28):
    # Prefer clause boundaries; preserve every character from the service transcript.
    parts, current = [], ''
    for c in text:
        current += c
        if c in '，。！？；：,!?;:' and len(current) >= 7:
            parts.append(current);current=''
        elif len(current) >= max_chars:
            parts.append(current);current=''
    if current:
        if parts and len(current)<5:parts[-1]+=current
        else:parts.append(current)
    return parts


def subtitle_cues(boundaries):
    result=[]
    for cue in boundaries:
        parts=split_caption(cue['text'])
        total=sum(len(s) for s in parts)
        start=cue['start']
        for part in parts:
            end=start+(cue['end']-cue['start'])*len(part)/total
            result.append((start,end,part));start=end
    return result


def validate_speech(speech, narration, seconds):
    if speech['narration']!=narration:
        raise ValueError('Narration changed; regenerate speech')
    cues=speech.get('cues',[])
    compact=lambda text:re.sub(r'\s+','',html.unescape(text))
    if not cues or compact(''.join(c['text'] for c in cues))!=compact(narration):
        raise ValueError('Speech boundary transcript differs from narration')
    previous=0;clean=[]
    for cue in cues:
        start,end=cue['start'],cue['end']
        if not all(math.isfinite(t) for t in [start,end]) or start<previous-.1 or not 0<=start<end<=seconds+.3:
            raise ValueError('Invalid or overlapping speech boundaries')
        # The service can report a 50ms overhang at a sentence boundary.
        # Clip subtitle visibility, retaining raw timestamps in speech.json.
        if clean and start<previous:
            if start<=clean[-1]['start']:raise ValueError('Unordered speech boundaries')
            clean[-1]['end']=start
        clean.append(dict(cue))
        previous=end
    return clean


class Canvas:
    def __init__(self, root, font, height=1080):
        self.scale=height/720;self.size=(round(1280*self.scale),height)
        self.root=root;self.font=font;self.fonts={};self.pictures={}
    def f(self,size):
        px=round(size*self.scale)
        if px not in self.fonts:self.fonts[px]=ImageFont.truetype(self.font,px)
        return self.fonts[px]
    def draw(self,scene,index,count,time,cues,captions):
        if scene.get('theme','deep-ocean')!='deep-ocean':
            raise ValueError('Color themes require --backend skia')
        s=self.scale
        im=Image.new('RGB',self.size,scene.get('background',PALETTE['bg']))
        d=ImageDraw.Draw(im)
        d.text((45*s,24*s),scene.get('chapter',f'论文讲解 / {index+1:02}'),font=self.f(16),fill=PALETTE['muted'])
        title=scene['title'];f=self.f(34)
        if f.getlength(title)>1170*s:raise ValueError(f'Heading too long: {title}')
        d.text(((self.size[0]-f.getlength(title))/2,59*s),title,font=f,fill=PALETTE['ink'])
        for obj in scene['objects']:
            state=object_state(obj,time,cues)
            if state is not None and state['opacity']>0:self.paint(im,state)
        d=ImageDraw.Draw(im)
        source=scene.get('source','')
        if self.f(14).getlength(source)>1170*s:raise ValueError('Source line too long')
        d.text((45*s,590*s),source,font=self.f(14),fill=PALETTE['muted'])
        caption=next((text for a,b,text in captions if a<=time<b),'')
        lines=wrap(caption,self.f(28),1150*s)
        if len(lines)>2:raise ValueError(f'Subtitle overflow: {caption}')
        for j,line in enumerate(lines):
            f=self.f(28);x=(self.size[0]-f.getlength(line))/2
            d.text((x,(630+j*38)*s),line,font=f,fill=PALETTE['ink'],stroke_width=round(2*s),stroke_fill=PALETTE['bg'])
        return im
    def paint(self,im,o):
        if any(o.get(k,0) for k in ('rotation','offset_x','offset_y')):
            raise ValueError('Rotated linked diagrams require --backend skia')
        s=self.scale;direct=o['opacity']>=.999
        layer=im if direct else Image.new('RGBA',self.size);d=ImageDraw.Draw(layer)
        alpha=round(255*o['opacity'])
        def color(key,default):
            value=o.get(key,default)
            if value is None:return None
            rgb=tuple(int(value[i:i+2],16) for i in (1,3,5))
            return rgb if direct else (*rgb,alpha)
        x=o.get('x',0);y=o.get('y',0);z=o.get('scale',1)
        point=lambda a:((x+a[0]*z)*s,(y+a[1]*z)*s)
        w=o.get('width',0)*z;h=o.get('height',0)*z
        stroke=max(1,round(o.get('stroke_width',2)*s*z))
        fill=color('fill',PALETTE['ink']);outline=color('stroke',None);kind=o['type']
        if kind=='text':
            font=self.f(o.get('font_size',26)*z);lines=wrap(o['text'],font,o.get('max_width',1100)*s)
            if len(lines)>o.get('max_lines',3):raise ValueError(f'Text overflow: {o["text"]}')
            for j,line in enumerate(lines):
                px=x*s
                if o.get('align')=='center':px-=font.getlength(line)/2
                d.text((px,(y+j*o.get('line_height',o.get('font_size',26)*1.4)*z)*s),line,font=font,fill=fill)
        elif kind=='rect':
            d.rounded_rectangle((x*s,y*s,(x+w)*s,(y+h)*s),radius=max(0,o.get('radius',8)*s),fill=fill,outline=outline,width=stroke)
        elif kind=='circle':
            r=o['radius']*z;d.ellipse(((x-r)*s,(y-r)*s,(x+r)*s,(y+r)*s),fill=fill,outline=outline,width=stroke)
        elif kind in ('line','arrow','polygon'):
            pts=[point(p) for p in o['points']]
            if kind=='polygon':d.polygon(pts,fill=fill,outline=outline,width=stroke)
            else:
                progress=min(1,max(0,o.get('progress',1)))
                lengths=[math.dist(a,b) for a,b in zip(pts,pts[1:])];remaining=sum(lengths)*progress;visible=[pts[0]]
                for a,b,length in zip(pts,pts[1:],lengths):
                    if remaining>=length:visible.append(b);remaining-=length
                    else:
                        u=remaining/max(length,1e-6);visible.append((a[0]+(b[0]-a[0])*u,a[1]+(b[1]-a[1])*u));break
                if len(visible)>1:
                    d.line(visible,fill=fill,width=stroke,joint='curve')
                    if kind=='arrow' and progress>0:
                        a,b=visible[-2:];angle=math.atan2(b[1]-a[1],b[0]-a[0]);r=12*s
                        d.polygon([b,(b[0]-r*math.cos(angle-.5),b[1]-r*math.sin(angle-.5)),(b[0]-r*math.cos(angle+.5),b[1]-r*math.sin(angle+.5))],fill=fill)
        elif kind=='image':
            path=str((self.root/o['image']).resolve())
            if path not in self.pictures:
                with Image.open(path) as source:self.pictures[path]=source.convert('RGBA')
            picture=ImageOps.contain(self.pictures[path],(max(1,round(w*s)),max(1,round(h*s))))
            picture=picture.copy();picture.putalpha(picture.getchannel('A').point(lambda a:round(a*o['opacity'])))
            position=(round((x+w/2)*s-picture.width/2),round((y+h/2)*s-picture.height/2))
            if direct:im.paste(picture,position,picture)
            else:layer.alpha_composite(picture,position)
        else:raise ValueError(f'Unsupported object type {kind}')
        if not direct:im.paste(layer,(0,0),layer)


class QualityCanvas(Canvas):
    """Native-resolution Skia geometry with coverage AA and subpixel placement."""
    def __init__(self,root,font,height=2160):
        super().__init__(root,font,height)
        import skia
        self.skia=skia;self.typeface=skia.Typeface.MakeFromFile(font)
        if self.typeface is None:raise RuntimeError(f'Could not load font: {font}')
        self.skfonts={};self.skimages={};self.backgrounds={};self.theme='deep-ocean'
    def sf(self,size):
        if size not in self.skfonts:
            font=self.skia.Font(self.typeface,size)
            font.setSubpixel(True);font.setEdging(self.skia.Font.Edging.kAntiAlias)
            self.skfonts[size]=font
        return self.skfonts[size]
    def color(self,value,alpha=1):
        return self.skia.ColorSetARGB(round(255*alpha),*(int(value[i:i+2],16) for i in (1,3,5)))
    def paint_for(self,color,alpha=1,stroke=None):
        if self.theme=='warm-paper':color=WARM_COLORS.get(color.lower(),color)
        p=self.skia.Paint(AntiAlias=True,Color=self.color(color,alpha))
        if stroke is not None:
            p.setStyle(self.skia.Paint.kStroke_Style);p.setStrokeWidth(stroke)
            p.setStrokeCap(self.skia.Paint.kRound_Cap);p.setStrokeJoin(self.skia.Paint.kRound_Join)
        return p
    def background(self,theme):
        if theme not in self.backgrounds:
            sk=self.skia;surface=sk.Surface(*self.size);c=surface.getCanvas()
            colors=('#faf8f2','#f4f0e7','#ede8df') if theme=='warm-paper' else ('#1b3047','#101f33','#090f1c')
            shader=sk.GradientShader.MakeRadial((self.size[0]*.4,self.size[1]*.32),self.size[0]*.77,
                [self.color(x) for x in colors],[0,.55,1])
            c.drawPaint(sk.Paint(Shader=shader,Dither=True))
            c.scale(self.scale,self.scale)
            # A quiet stage, controlled lighting and one small accent; no moving noise.
            c.drawRoundRect(sk.Rect.MakeXYWH(38,126,1204,450),18,18,self.paint_for('#ffffff',.76) if theme=='warm-paper' else self.paint_for('#1a2a40',.40))
            c.drawLine(64,111,1216,111,self.paint_for('#7493b3',.16,1))
            c.drawLine(48,27,48,48,self.paint_for('#78c9dc',.85,3))
            for x,y in [(1085,162),(1125,162),(1165,162),(1205,162)]:
                c.drawCircle(x,y,1.2,self.paint_for('#8da5bf',.25))
            self.backgrounds[theme]=surface.makeImageSnapshot()
        return self.backgrounds[theme]
    def text(self,c,text,x,y,size=26,color='#f7f5ed',alpha=1,align='left',max_width=1100,max_lines=3):
        font=self.sf(size);lines=wrap(text,self.f(size),max_width*self.scale)
        if len(lines)>max_lines:raise ValueError(f'Text overflow: {text}')
        baseline=-font.getMetrics().fAscent
        for j,line in enumerate(lines):
            px=x-font.measureText(line)/2 if align=='center' else x
            c.drawString(line,px,y+baseline+j*size*1.4,font,self.paint_for(color,alpha))
    def draw(self,scene,index,count,time,cues,captions):
        self.theme=scene.get('theme','deep-ocean')
        if self.theme not in ('deep-ocean','warm-paper'):raise ValueError(f'Unknown theme: {self.theme}')
        sk=self.skia;surface=sk.Surface(*self.size);c=surface.getCanvas()
        c.drawImage(self.background(scene.get('theme','deep-ocean')),0,0)
        c.scale(self.scale,self.scale)
        self.text(c,scene.get('chapter',f'论文讲解 / {index+1:02}'),64,25,16,'#a9bdd2')
        self.text(c,scene['title'],640,61,34,align='center',max_width=1170,max_lines=1)
        for obj in scene['objects']:
            state=object_state(obj,time,cues)
            # Explicit theme overrides keep labels legible on colored fills.
            if state is not None and self.theme=='warm-paper' and state.get('theme_fill'):
                state['fill']=state['theme_fill'].get(self.theme,state.get('fill',PALETTE['ink']))
            if state is not None and state['opacity']>0:self.paint_object(c,state)
        self.text(c,scene.get('source',''),48,592,14,'#9aaec5',max_width=1170,max_lines=1)
        caption=next((text for a,b,text in captions if a<=time<b),'')
        self.text(c,caption,640,633,28,align='center',max_width=1145,max_lines=2)
        array=surface.makeImageSnapshot().toarray(colorType=sk.ColorType.kRGBA_8888_ColorType)
        return Image.fromarray(array,'RGBA').convert('RGB')
    def paint_object(self,c,o):
        sk=self.skia;c.save();c.translate(o.get('x',0),o.get('y',0));z=o.get('scale',1);c.scale(z,z)
        c.rotate(o.get('rotation',0));c.translate(o.get('offset_x',0),o.get('offset_y',0))
        alpha=o['opacity'];fill=o.get('fill',PALETTE['ink']);stroke=o.get('stroke');sw=o.get('stroke_width',2)
        kind=o['type'];w=o.get('width',0);h=o.get('height',0)
        if kind=='text':
            self.text(c,o['text'],0,0,o.get('font_size',26),fill,alpha,o.get('align','left'),o.get('max_width',1100),o.get('max_lines',3))
        elif kind in ('rect','circle'):
            def shape(p):
                if kind=='rect':c.drawRoundRect(sk.Rect.MakeXYWH(0,0,w,h),o.get('radius',8),o.get('radius',8),p)
                else:c.drawCircle(0,0,o['radius'],p)
            if fill:shape(self.paint_for(fill,alpha))
            if stroke:shape(self.paint_for(stroke,alpha,sw))
        elif kind in ('line','arrow','polygon'):
            pts=o['points'];path=sk.Path();path.moveTo(*pts[0]);visible=[pts[0]]
            if kind=='polygon':
                for pt in pts[1:]:path.lineTo(*pt)
                path.close()
                if fill:c.drawPath(path,self.paint_for(fill,alpha))
                if stroke:c.drawPath(path,self.paint_for(stroke,alpha,sw))
            else:
                lengths=[math.dist(a,b) for a,b in zip(pts,pts[1:])]
                remaining=sum(lengths)*min(1,max(0,o.get('progress',1)))
                for a,b,length in zip(pts,pts[1:],lengths):
                    if remaining>=length:visible.append(b);remaining-=length
                    else:
                        u=remaining/max(length,1e-6);visible.append((a[0]+(b[0]-a[0])*u,a[1]+(b[1]-a[1])*u));break
                for pt in visible[1:]:path.lineTo(*pt)
                c.drawPath(path,self.paint_for(fill,alpha,sw))
                if kind=='arrow' and o.get('progress',1)>0 and len(visible)>1:
                    a,b=visible[-2:];angle=math.atan2(b[1]-a[1],b[0]-a[0]);r=10
                    head=sk.Path();head.moveTo(*b)
                    head.lineTo(b[0]-r*math.cos(angle-.48),b[1]-r*math.sin(angle-.48))
                    head.lineTo(b[0]-r*math.cos(angle+.48),b[1]-r*math.sin(angle+.48));head.close()
                    c.drawPath(head,self.paint_for(fill,alpha))
        elif kind=='image':
            path=str((self.root/o['image']).resolve())
            if path not in self.skimages:
                picture=sk.Image.MakeFromEncoded(sk.Data.MakeFromFileName(path))
                if picture is None:raise ValueError(f'Invalid image {path}')
                self.skimages[path]=picture
            picture=self.skimages[path];ratio=min(w/picture.width(),h/picture.height())
            iw,ih=picture.width()*ratio,picture.height()*ratio
            target=sk.Rect.MakeXYWH((w-iw)/2,(h-ih)/2,iw,ih)
            paint=sk.Paint(AntiAlias=True,Alphaf=alpha)
            c.drawImageRect(picture,target,sk.SamplingOptions(sk.CubicResampler.Mitchell()),paint)
        else:raise ValueError(f'Unsupported object {kind}')
        c.restore()


def render(args):
    path=Path(args.storyboard).resolve();root=path.parent
    story=json.loads(path.read_text(encoding='utf-8-sig'));scenes=story['scenes']
    if getattr(args,'theme',None):
        for scene in scenes:scene['theme']=args.theme
    ffmpeg=shutil.which(args.ffmpeg)
    if not ffmpeg:raise RuntimeError('FFmpeg unavailable')
    font=args.font or os.path.join(os.environ.get('WINDIR','C:/Windows'),'Fonts/msyh.ttc')
    if not Path(font).exists():raise RuntimeError('Specify a Chinese font with --font')
    output=Path(args.output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    previews=output.with_name(output.stem+'-frames');previews.mkdir(exist_ok=True)
    from speech_io import prepare_scene_audio
    audio_cache=output.with_name(output.stem+'-audio-cache')
    # Resolve and normalize every input before any preview or video encoding.
    audio_plans=[];ids=set()
    for i,scene in enumerate(scenes):
        sid=scene['id']
        if not re.fullmatch('[A-Za-z0-9_-]+',sid) or sid in ids:raise ValueError('Invalid/duplicate scene ID')
        ids.add(sid)
        audio,speech=prepare_scene_audio(scene,root,audio_cache,ffmpeg)
        with wave.open(str(audio),'rb') as wav:seconds=wav.getnframes()/wav.getframerate()
        cues=validate_speech(speech,scene['narration'],seconds);caps=subtitle_cues(cues)
        frames,duration=scene_frames(scene,seconds,cues,args.fps)
        object_ids=[o['id'] for o in scene['objects']]
        if len(object_ids)!=len(set(object_ids)):raise ValueError('Object IDs must be unique within a scene')
        audio_plans.append((scene,audio,duration,frames,cues,caps))
    canvas_type=QualityCanvas if args.backend=='skia' else Canvas
    canvas=canvas_type(root,font,args.height);plans=[]
    layout_canvas=canvas if args.height<=1080 else canvas_type(root,font,1080)
    for i,(scene,audio,duration,frames,cues,caps) in enumerate(audio_plans):
        sid=scene['id']
        # Preflight every speech change and animation endpoint before encoding.
        points={.4,duration-.1,*[x['start']+.3 for x in cues]}
        for o in scene['objects']:
            points.add(event_time(o.get('at',0),cues)+.4)
            points.update(event_time(k['at'],cues)+.1 for k in o.get('keyframes',[]))
        for t in sorted(points):
            if t<duration:layout_canvas.draw(scene,i,len(scenes),t,cues,caps)
        canvas.draw(scene,i,len(scenes),duration*.7,cues,caps).save(previews/f'{sid}.png')
        plans.append((scene,audio,duration,frames,cues,caps))
    timeline=[];subtitles=[];offset=0
    segment_cache=output.with_name(output.stem+'-segments');segment_cache.mkdir(exist_ok=True)
    code_hash=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))).hexdigest()
    font_hash=hashlib.sha256(Path(font).read_bytes()).hexdigest()
    worker_count=getattr(args,'workers',1)
    executor=(ProcessPoolExecutor(max_workers=worker_count,initializer=_init_frame_worker,
              initargs=(str(root),font,args.height,args.backend)) if worker_count>1 else nullcontext(None))
    with tempfile.TemporaryDirectory(prefix='article-motion-') as temp, executor as pool:
        parts=[]
        for i,(scene,audio,duration,frames,cues,caps) in enumerate(plans):
            fingerprint=hashlib.sha256(json.dumps([scene,cues,caps,frames,i,len(scenes),args.height,args.fps,args.backend,args.crf,args.preset,getattr(args,'encoder','libx264'),getattr(args,'transport','frames'),code_hash,font_hash],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            # Referenced image content must also invalidate a cached segment.
            for obj in scene['objects']:
                if obj.get('image'):fingerprint=hashlib.sha256((fingerprint+hashlib.sha256((root/obj['image']).read_bytes()).hexdigest()).encode()).hexdigest()
            part=segment_cache/f'{scene["id"]}-{fingerprint}.mp4'
            codec_options=(['-c:v','h264_nvenc','-preset','p4','-rc','vbr','-cq',str(args.crf),'-b:v','0']
                           if getattr(args,'encoder','libx264')=='h264_nvenc' else
                           ['-c:v','libx264','-preset',args.preset,'-crf',str(args.crf)])
            cmd=[ffmpeg,'-v','error','-y','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{canvas.size[0]}x{canvas.size[1]}','-framerate',str(args.fps),'-i','pipe:0',
                 '-t',str(duration),'-an',*codec_options,'-pix_fmt','yuv420p',
                 '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709',str(part.with_suffix('.partial.mp4'))]
            if part.exists():
                print(f'Reused encoded {scene["id"]}',flush=True)
            elif getattr(args,'transport','frames')=='frames':
                # Encode each changed visual state once. Duration entries preserve
                # every 1/fps animation sample and hold genuinely static pictures.
                with tempfile.TemporaryDirectory(prefix='scene-frames-',dir=temp) as frame_dir:
                    folder=Path(frame_dir);entries=[];previous=None;run=0;frame_path=None;pending_frames=deque()
                    for f in range(frames):
                        t=f/args.fps
                        signature=repr([object_state(o,t,cues) for o in scene['objects']])+next((text for a,b,text in caps if a<=t<b),'')
                        if signature!=previous:
                            if frame_path is not None:entries.append((frame_path.name,run/args.fps))
                            frame_path=folder/f'{len(entries):06}.png'
                            if pool is None:
                                canvas.draw(scene,i,len(scenes),t,cues,caps).save(frame_path,compress_level=1)
                            else:
                                pending_frames.append(pool.submit(_save_frame,(scene,i,len(scenes),t,cues,caps,str(frame_path))))
                                if len(pending_frames)>=worker_count*2:pending_frames.popleft().result()
                            previous=signature;run=0
                        run+=1
                    entries.append((frame_path.name,run/args.fps))
                    for future in pending_frames:future.result()
                    listing=folder/'frames.txt'
                    listing.write_text(''.join(f"file '{name}'\noption framerate {args.fps}\nduration {seconds:.12f}\n" for name,seconds in entries)+f"file '{frame_path.name}'\noption framerate {args.fps}\n",encoding='utf-8')
                    pending=part.with_suffix('.partial.mp4')
                    subprocess.run([ffmpeg,'-v','error','-y','-f','concat','-safe','0','-i',str(listing),'-vf',f'fps={args.fps}','-frames:v',str(frames),'-an',*codec_options,'-pix_fmt','yuv420p','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709',str(pending)],check=True)
                    pending.replace(part)
            else:
              with tempfile.TemporaryFile() as errors:
                p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=errors)
                try:
                    previous,cached=None,None
                    for f in range(frames):
                        t=f/args.fps
                        signature=repr([object_state(o,t,cues) for o in scene['objects']])+next((text for a,b,text in caps if a<=t<b),'')
                        if signature!=previous:
                            cached=canvas.draw(scene,i,len(scenes),t,cues,caps).tobytes();previous=signature
                        p.stdin.write(cached)
                    p.stdin.close();code=p.wait()
                    if code:
                        errors.seek(0);raise RuntimeError(errors.read().decode(errors='replace'))
                    part.with_suffix('.partial.mp4').replace(part)
                except BaseException:
                    p.kill();p.wait();raise
            parts.append(part)
            for a,b,text in caps:subtitles.append(f'{len(subtitles)+1}\n{timestamp(offset+a)} --> {timestamp(offset+b)}\n{text}\n')
            timeline.append(dict(id=scene['id'],title=scene['title'],start=offset,end=offset+duration,
                                 caption_timing='sentence boundaries; clause timing proportional within sentence',
                                 claim_ids=scene.get('claim_ids',[])))
            offset+=duration;print(f'Rendered {scene["id"]}: {duration:.2f}s',flush=True)
        listing=Path(temp)/'parts.txt';listing.write_text('\n'.join("file '"+p.as_posix().replace("'","'\\''")+"'" for p in parts),encoding='utf-8')
        picture=Path(temp)/'picture-track.mp4'
        subprocess.run([ffmpeg,'-v','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(picture)],check=True)
        from audio_master import build_master
        master=output.with_name(output.stem+'-audio-master.wav')
        build_master([(audio,duration) for _,audio,duration,_,_,_ in plans],master,ffmpeg)
        # One AAC encoder for the entire lossless timeline, avoiding per-scene
        # priming/padding discontinuities and repeated lossy audio compression.
        subprocess.run([ffmpeg,'-v','error','-y','-i',str(picture),'-i',str(master),'-map','0:v:0','-map','1:a:0',
                        '-c:v','copy','-c:a','aac','-b:a','256k','-ar','48000','-ac','2','-movflags','+faststart',str(output)],check=True)
    output.with_suffix('.srt').write_text('\n'.join(subtitles),encoding='utf-8')
    output.with_suffix('.timeline.json').write_text(json.dumps(timeline,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Created {output}; {offset:.2f}s; {canvas.size[0]}x{canvas.size[1]}',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('storyboard');parser.add_argument('--output',required=True)
    parser.add_argument('--height',type=int,choices=[720,1080,1440,2160],default=2160)
    parser.add_argument('--fps',type=int,choices=range(1,121),default=120)
    parser.add_argument('--font');parser.add_argument('--ffmpeg',default='ffmpeg')
    parser.add_argument('--backend',choices=['skia','pillow'],default='skia')
    parser.add_argument('--crf',type=int,choices=range(0,52),default=16)
    parser.add_argument('--preset',choices=['veryfast','fast','medium','slow'],default='medium')
    parser.add_argument('--encoder',choices=['libx264','h264_nvenc'],default='libx264',
                        help='Use h264_nvenc only with a working NVIDIA encoder; --crf sets NVENC CQ instead')
    parser.add_argument('--transport',choices=['frames','raw'],default='frames',help='Lossless changed-frame images or raw RGB pipe')
    parser.add_argument('--theme',choices=['deep-ocean','warm-paper'],help='Override the storyboard scene palette (Skia)')
    parser.add_argument('--workers',type=int,choices=range(1,9),default=min(4,os.cpu_count() or 1),help='Parallel changed-frame rendering workers; 1 runs serially')
    render(parser.parse_args())
