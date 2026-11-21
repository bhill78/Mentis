"""Explicit run starts for synthetic respond grants; never used by production."""


def bind_run(cv, grant, *, ended=True):
    """A new fixture run, even when execution/request/text are reused.

    Most direct operation fixtures model a run that is not executing. Keep its
    end so existing completion tests can reconcile it. Active-run tests use the
    actual dispatch grant or pass ended=False.
    """
    grant = dict(grant)
    start = cv.record_act(
        actor=grant['participant'], act='execution-started',
        execution=grant['instance'], caused_by=grant['expectation'],
        conversation=grant['conversation'], turn=cv._act(grant['expectation'])['turn'])
    grant['run'] = start
    if ended:
        cv.record_act(actor=grant['participant'], act='result-returned',
                      execution=grant['instance'], caused_by=start,
                      conversation=grant['conversation'], detail={'terminal': 'reported_done'})
    return grant
