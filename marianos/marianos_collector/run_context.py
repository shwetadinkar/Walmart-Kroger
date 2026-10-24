"""Fresh Azure execution identity, stable across replicas/retries of one execution."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
import re
import uuid


@dataclass(frozen=True)
class RunContext:
    run_id: str
    origin: str
    execution_name: str = ''
    legacy_id_ignored: bool = False


def execution_context(environment=None):
    env=os.environ if environment is None else environment
    execution=env.get('CONTAINER_APP_JOB_EXECUTION_NAME','')
    job=env.get('CONTAINER_APP_JOB_NAME','')
    if execution:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',execution):
            raise ValueError('Invalid Azure execution identity')
        digest=hashlib.sha256((job+'\n'+execution).encode()).hexdigest()[:32]
        return RunContext('azure-'+digest,'azure-execution',execution,
                          bool(env.get('MARIANOS_RUN_ID') or env.get('MARIANOS_RESUME_RUN_ID')))
    if job:
        raise ValueError('Azure job execution metadata missing; refusing unstable checkpoint identity')
    explicit=env.get('MARIANOS_RESUME_RUN_ID') or env.get('MARIANOS_RUN_ID')
    if explicit:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',explicit):
            raise ValueError('Invalid explicit resume identity')
        return RunContext(explicit,'explicit-resume')
    return RunContext(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-')+uuid.uuid4().hex,'fresh-local')
