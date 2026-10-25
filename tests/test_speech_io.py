"""Exercise both shipped speech formats and real FFmpeg PCM conversion."""
from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from speech_io import prepare_scene_audio,pcm_info
from chinese_cadence import apply_cadence
from render_motion import render
from argparse import Namespace


def write_tone(path,rate=48000,channels=1,seconds=.1):
    values=(np.sin(np.arange(round(rate*seconds))*2*np.pi*440/rate)*3000).astype('<i2')
    if channels==2:values=np.repeat(values[:,None],2,axis=1)
    with wave.open(str(path),'wb') as wav:
        wav.setnchannels(channels);wav.setsampwidth(2);wav.setframerate(rate);wav.writeframes(values.tobytes())


class SpeechIOTests(unittest.TestCase):
    def test_local_timing_manifest_produces_renderable_speech(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            write_tone(root/'a.wav',seconds=.1);write_tone(root/'b.wav',seconds=.2)
            (root/'timing.json').write_text(json.dumps({'narration':'甲。乙。','segments':[
                {'text':'甲。','audio':'a.wav'},{'text':'乙。','audio':'b.wav'}]}),encoding='utf-8')
            audio,data=prepare_scene_audio({'id':'s1','narration':'甲。乙。','timing':'timing.json'},root,root/'cache','ffmpeg')
            self.assertEqual(pcm_info(audio),(1,2,48000,'NONE'))
            self.assertEqual(data['cues'],[{'start':0,'end':.1,'text':'甲。'},{'start':.1,'end':.3,'text':'乙。'}])
            with wave.open(str(audio),'rb') as wav:self.assertEqual(wav.getnframes(),14400)

    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
    def test_external_stereo_24khz_audio_is_normalized(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);write_tone(root/'external.wav',rate=24000,channels=2)
            (root/'speech.json').write_text(json.dumps({'narration':'测试。','audio':'external.wav','cues':[{'start':0,'end':.1,'text':'测试。'}]}),encoding='utf-8')
            audio,data=prepare_scene_audio({'id':'s1','narration':'测试。','speech':'speech.json'},root,root/'cache','ffmpeg')
            self.assertEqual(pcm_info(audio),(1,2,48000,'NONE'))
            with wave.open(str(audio),'rb') as wav:self.assertEqual(wav.getnframes(),4800)

    @unittest.skipUnless(shutil.which('ffmpeg') and Path('C:/Windows/Fonts/msyh.ttc').exists(),'FFmpeg and font required')
    def test_all_audio_inputs_are_checked_before_encoder_starts(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);write_tone(root/'valid.wav')
            for name,audio in [('one','valid.wav'),('two','missing.wav')]:
                (root/f'{name}.json').write_text(json.dumps({'narration':'测试。','audio':audio,'cues':[{'start':0,'end':.1,'text':'测试。'}]}),encoding='utf-8')
            scenes=[{'id':name,'title':'验证','narration':'测试。','speech':f'{name}.json','objects':[]} for name in ['one','two']]
            (root/'story.json').write_text(json.dumps({'scenes':scenes}),encoding='utf-8')
            args=Namespace(storyboard=str(root/'story.json'),output=str(root/'video.mp4'),font='C:/Windows/Fonts/msyh.ttc',ffmpeg='ffmpeg',fps=120)
            with patch('subprocess.Popen') as encoder:
                with self.assertRaises(FileNotFoundError):render(args)
                encoder.assert_not_called()

    def test_chinese_pauses_retime_cues_without_changing_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);write_tone(root/'input.wav',seconds=1)
            cues=[{'start':0,'end':.5,'text':'为什么？'},{'start':.5,'end':1,'text':'看这里。'}]
            result,added=apply_cadence(root/'input.wav',root/'output.wav',cues)
            self.assertAlmostEqual(added,.32)
            self.assertAlmostEqual(result[1]['start'],.82)
            self.assertAlmostEqual(result[0]['end'],.5)
            self.assertEqual(''.join(c['text'] for c in result),'为什么？看这里。')
            self.assertEqual(cues[1]['start'],.5)
            with wave.open(str(root/'output.wav'),'rb') as wav:
                self.assertEqual(wav.getnframes(),63360)
                data=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2')
            self.assertTrue(np.all(data[24000:39360]==0))


if __name__=='__main__':unittest.main()
