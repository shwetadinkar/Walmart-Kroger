import unittest
from marianos_collector.run_context import execution_context


class RunContextTests(unittest.TestCase):
    def test_separate_azure_occurrences_are_fresh_even_with_legacy_fixed_id(self):
        common={'CONTAINER_APP_JOB_NAME':'marianos-westloop-api-pilot','MARIANOS_RUN_ID':'old-fixed-id'}
        first=execution_context({**common,'CONTAINER_APP_JOB_EXECUTION_NAME':'marianos-run-a'})
        second=execution_context({**common,'CONTAINER_APP_JOB_EXECUTION_NAME':'marianos-run-b'})
        self.assertNotEqual(first.run_id,second.run_id)
        self.assertNotEqual(first.run_id,'old-fixed-id')
        self.assertTrue(first.legacy_id_ignored)

    def test_replica_retry_in_one_azure_execution_has_the_same_checkpoint_identity(self):
        env={'CONTAINER_APP_JOB_NAME':'marianos','CONTAINER_APP_JOB_EXECUTION_NAME':'marianos-run-a'}
        self.assertEqual(execution_context(env),execution_context(env))

    def test_local_manual_resume_is_explicit_and_stable(self):
        result=execution_context({'MARIANOS_RESUME_RUN_ID':'local-attempt-1'})
        self.assertEqual(result.run_id,'local-attempt-1')
        self.assertEqual(result.origin,'explicit-resume')

    def test_unspecified_local_invocations_do_not_share_calendar_day_checkpoints(self):
        self.assertNotEqual(execution_context({}).run_id,execution_context({}).run_id)

    def test_azure_context_without_execution_name_fails_instead_of_replaying(self):
        with self.assertRaises(ValueError):execution_context({'CONTAINER_APP_JOB_NAME':'marianos','MARIANOS_RUN_ID':'old'})

    def test_unsafe_explicit_checkpoint_id_is_rejected(self):
        with self.assertRaises(ValueError):execution_context({'MARIANOS_RESUME_RUN_ID':'../../old'})

if __name__=='__main__':unittest.main()
