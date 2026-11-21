"""Explicit synthetic authoring descriptors; historical fixtures stay historical."""


def question(words="Build the chart candidate?", **updates):
    q = {"question": words, "because": "The owner must choose whether this chart candidate is built.",
         "options": [{"label": "Build", "consequence": "Implement the chart candidate; no integration or deployment."},
                     {"label": "Wait", "consequence": "Defer implementation until the owner requests it."}],
         "presentation": {"version": 1, "type": "action_approval",
                          "scope": "Implementation of the chart candidate only; no integration or deployment.",
                          "stages": ["implementation"], "primary": None,
                          "primary_reason": "This synthetic action has no separate artifact."}}
    q.update(updates)
    return q


def placement_question(args):
    """A complete synthetic question for tests whose subject is placement."""
    q = question(args['question'])
    q.update(args)
    if 'options' in args:
        q['options'] = [{**o, 'consequence': o.get('consequence') or
                         f"Select {o['label']} in this fixture; no external action."}
                        for o in args['options']]
    return q
