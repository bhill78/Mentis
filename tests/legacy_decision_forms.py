"""Construct historical read fixtures without submitting new ambiguous asks.

This adapter is scoped to fixture construction only. It calls the unchanged
internal producer constructor; the authoring validator remains enabled in all
production and in every test operation after construction.
"""
from unittest.mock import patch


def build_historical(builder, world):
    from mentis import worker
    original = worker._operate

    def fixture_operation(surface, name, args, grant):
        if name != "request_decision":
            return original(surface, name, args, grant)
        cv = surface.cv
        actor, parent = grant["participant"], grant["expectation"]
        execution = grant.get("instance")
        return worker._decision_form(
            cv, args, actor=actor, parent=parent,
            here=grant["conversation"], wrote=None, execution=execution,
            where=lambda cid: cid,
            act=lambda kind, **kw: cv.record_act(
                actor=actor, act=kind, caused_by=parent,
                execution=execution, runtime=grant.get("runtime"), **kw))

    with patch.object(worker, "_operate", fixture_operation):
        return builder(world)
