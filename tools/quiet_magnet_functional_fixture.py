"""Extend only a new synthetic Magnet fixture with actual history and nonexecuting Work."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quiet_magnet_fixture import FORMAT, safe_root


def extend(value: str) -> dict:
    root = safe_root(value)
    file = root / 'manifest.json'
    manifest = json.loads(file.read_text('utf-8'))
    if manifest.get('format') != FORMAT or not manifest.get('setup_closed') or manifest.get('functional'):
        raise ValueError('requires a completed, not-yet-extended synthetic fixture')
    import mentis.api as api
    from mentis.bootstrap.baseline import OWNER_ABOUT
    from mentis.conversation import text
    from mentis.conversation.owner import _owner
    corpus = api.open_corpus(str(root / 'primary'))
    try:
        if corpus.corpus_id != manifest['primary']['corpus_id']:
            raise ValueError('fixture identity mismatch')
        cv = api.conversations(corpus)
        owner = _owner(cv) or cv.resolve_participant('@PreviewOwner', about=OWNER_ABOUT)
        analyst = cv.resolve_participant('@PreviewAnalyst', about='Synthetic historical participant; no runtime or live agent is connected')
        c = manifest['primary']['C']
        for who in (owner, analyst):
            cv.join(who, c, attributed_to=owner)
        for i in range(34):
            cv.say(c, owner if i % 2 == 0 else analyst, [text(f'FIXTURE HISTORY {i + 1}: Synthetic retained observation in the Magnet\'s existing Conversation. No runtime executed this message.')])
        root_post = cv.say(c, owner, [text('FIXTURE INQUIRY: Compare the historical calibration observations. This is a recorded fixture request, not a running agent.')])
        request = cv.expect(root_post, of=analyst, kind='result', by=owner, because='Synthetic nonexecuting Work for the mini Conversation status read')
        reply = cv.say(c, analyst, [text('FIXTURE HISTORICAL REPLY: The calibration notes remain separate from source B. This reply was seeded during setup; it is not a live agent response.')], replies_to=root_post)
        extra = {'owner': owner, 'analyst': analyst, 'history_roots_added': 35, 'root_post': root_post,
                 'historical_reply': reply, 'work': request, 'no_runtime_executed': True,
                 'setup_at': datetime.now(timezone.utc).isoformat()}
    finally:
        corpus.close()
    manifest['functional'] = extra
    manifest['runtime_forbidden'] = ['dispatch', 'activation', 'own-Conversation creation or repair', 'unrelated writes', 'GET /api/capacity']
    file.write_text(json.dumps(manifest, indent=2), 'utf-8')
    return extra


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    args = parser.parse_args()
    print(json.dumps(extend(args.root), indent=2))
