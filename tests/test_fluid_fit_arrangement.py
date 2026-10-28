"""Fit to content (Fluid Focus): a zone's `fit` is kept by the arrangement
when it is a boolean, and only then."""

from mentis.fluid import arrangements as A


def _layout(fit):
    zone = {"type": "zone", "id": "z1", "show": "objects"}
    if fit is not ...:
        zone["fit"] = fit
    return {"format": A.FORMAT, "version": A.VERSION,
            "tree": {"type": "split", "dir": "col", "sizes": [0.5, 0.5],
                     "kids": [zone, {"type": "zone", "id": "z2", "show": "objects"}]}}


def test_fit_true_and_false_are_kept():
    assert A.check(_layout(True))["tree"]["kids"][0]["fit"] is True
    assert A.check(_layout(False))["tree"]["kids"][0]["fit"] is False


def test_fit_absent_stays_absent():
    kept = A.check(_layout(...))["tree"]["kids"][0]
    assert "fit" not in kept


def test_fit_not_a_boolean_is_dropped():
    for bad in ("yes", 1, None, [True]):
        assert "fit" not in A.check(_layout(bad))["tree"]["kids"][0]


def test_fit_survives_a_named_layout():
    shaped = A.shape_of(A.check(_layout(True)))
    assert shaped["tree"]["kids"][0]["fit"] is True
