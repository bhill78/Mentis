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
