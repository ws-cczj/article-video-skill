"""Behavior checks for cue-driven motion and subtitle boundaries."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from render_motion import event_time,object_state,subtitle_cues,validate_speech,scene_frames


class MotionTests(unittest.TestCase):
    def test_omitted_defaults_are_interpolated(self):
        obj={'id':'point','type':'circle','radius':5,'fade':0,
             'keyframes':[{'at':1,'opacity':0,'scale':2,'x':100,'progress':0}]}
        halfway=object_state(obj,.5,[])
        self.assertAlmostEqual(halfway['opacity'],.5)
        self.assertAlmostEqual(halfway['scale'],1.5)
        self.assertAlmostEqual(halfway['x'],50)
        self.assertAlmostEqual(halfway['progress'],.5)
        self.assertNotIn('opacity',obj)

    def test_scene_includes_late_animations_at_120fps(self):
        scene={'objects':[{'id':'result','at':6,'until':7}]}
        frames,seconds=scene_frames(scene,4,[],120)
        self.assertEqual(frames,840);self.assertEqual(seconds,7)
        scene={'objects':[{'id':'move','keyframes':[{'at':8,'x':20}]}]}
        self.assertGreaterEqual(scene_frames(scene,4,[],120)[1],8.3)

    def test_invalid_visibility_window_is_rejected(self):
        with self.assertRaises(ValueError):
            scene_frames({'objects':[{'id':'bad','at':2,'until':1}]},3,[],120)
        with self.assertRaises(ValueError):
            scene_frames({'objects':[{'id':'bad','until':2,'keyframes':[{'at':3,'x':1}]}]},4,[],120)

    def test_motion_starts_with_speech_cue(self):
        cues=[{'start':0,'end':1},{'start':2,'end':4}]
        obj={'id':'point','type':'circle','at':0,'x':0,'y':30,'radius':5,'fade':0,
             'keyframes':[{'at':{'cue':1},'x':0},{'at':{'cue':1,'offset':1},'x':100}]}
        self.assertEqual(object_state(obj,1,cues)['x'],0)
        self.assertAlmostEqual(object_state(obj,2.5,cues)['x'],50)
        self.assertEqual(object_state(obj,4,cues)['x'],100)
        self.assertEqual(obj['x'],0)

    def test_invalid_cue_and_unordered_frames_fail(self):
        cues=[{'start':0,'end':1}]
        with self.assertRaises(ValueError):event_time({'cue':2},cues)
        with self.assertRaises(ValueError):event_time(float('nan'),cues)
        with self.assertRaises(ValueError):object_state({'at':0,'keyframes':[{'at':2,'x':1},{'at':1,'x':2}]},3,cues)

    def test_hidden_objects_do_not_leak_before_enter_or_after_exit(self):
        obj={'at':2,'until':4,'x':1}
        self.assertIsNone(object_state(obj,1,[]))
        self.assertIsNone(object_state(obj,5,[]))

    def test_subtitles_preserve_service_text_and_sentence_limits(self):
        original='先测距离，再看方位。最后保留未知。'
        caps=subtitle_cues([{'start':1,'end':7,'text':original}])
        self.assertEqual(''.join(x[2] for x in caps),original)
        self.assertAlmostEqual(caps[0][0],1)
        self.assertAlmostEqual(caps[-1][1],7)
        self.assertTrue(all(a<b for a,b,_ in caps))
        self.assertTrue(all(b<=d for (_,b,_),(d,_,_) in zip(caps,caps[1:])))

    def test_speech_rejects_old_text_and_invalid_audio_timing(self):
        speech={'narration':'第一句。第二句。','cues':[{'text':'第一句。','start':0,'end':1},{'text':'第二句。','start':1.2,'end':2}]}
        self.assertEqual(len(validate_speech(speech,speech['narration'],2)),2)
        with self.assertRaises(ValueError):validate_speech(speech,'换稿了。',2)
        with self.assertRaises(ValueError):validate_speech(speech,speech['narration'],1)
        speech['cues'][1]['start']=.5
        with self.assertRaises(ValueError):validate_speech(speech,speech['narration'],2)

    def test_service_sentence_overhang_is_clipped_without_mutating_input(self):
        speech={'narration':'甲。乙。','cues':[{'text':'甲。','start':0,'end':1},{'text':'乙。','start':.95,'end':2}]}
        clean=validate_speech(speech,speech['narration'],2)
        self.assertEqual(clean[0]['end'],.95)
        self.assertEqual(speech['cues'][0]['end'],1)


if __name__=='__main__':unittest.main()
