import unittest
from workout_tools import summarize_workout

class CommentsTest(unittest.TestCase):
    def test_notes_on_pending_sets_are_not_lost_or_counted_as_completed(self):
        workout = {'id':'w','comment':'Плохо спал','trainSessions':[{'id':'s','exerciseId':'e','sets':[
            {'id':'one','number':1,'isDone':True,'weight':60,'reps':8,'comment':'Тяжело'},
            {'id':'two','number':2,'isDone':False,'weight':60,'reps':8,'comment':'Пропустил'}]}]}
        result = summarize_workout(workout, {'e':{'name':'Жим'}}, lambda _: '2026-10-23')
        self.assertEqual(result['comment'],'Плохо спал')
        self.assertEqual(result['sets_count'],1)
        self.assertEqual(result['volume_kg'],480)
        self.assertEqual(result['exercises'][0]['sets'][0]['comment'],'Тяжело')
        self.assertEqual(result['set_comments'][1]['set_id'],'two')
        self.assertEqual(result['set_comments'][1]['exercise_id'],'e')
        self.assertFalse(result['set_comments'][1]['is_done'])

    def test_old_data_is_readable(self):
        result = summarize_workout({'id':'w'}, {}, lambda _: None)
        self.assertIsNone(result['comment'])
        self.assertEqual(result['set_comments'], [])

if __name__ == '__main__': unittest.main()
