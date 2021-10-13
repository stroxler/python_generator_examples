import asyncio
import pytest


def make_yield_from_demonstration():

    sent_to_inner = []
    sent_to_outer = []

    def inner():
        sent_to_inner.append((yield "from inner"))
        return "inner return value"

    def outer_no_yield():
        inner_return = yield from inner()
        return inner_return, "from outer_no_yield"

    def outer_with_yield_before():
        sent_to_outer.append((yield "yielded before"))
        inner_return = yield from inner()
        return inner_return, "from outer_with_yield_before"

    def outer_with_yield_after():
        inner_return = yield from inner()
        sent_to_outer.append((yield "yielded after"))
        return inner_return, "from outer_with_yield_after"

    
    return (
        outer_no_yield,
        outer_with_yield_before,
        outer_with_yield_after,
        sent_to_inner,
        sent_to_outer,
    )


def run_tcase(
    coroutine,
    sent_to_inner,
    sent_to_outer,
    expected_sent_to_inner,
    expected_sent_to_outer,
    expected_yielded,
    expected_return,
):
    yielded = []
    with pytest.raises(StopIteration) as stop:
        i = 0
        while True:
            yielded.append(next(coroutine))
            coroutine.send("sent {}".format(i))
            i += 1

    assert sent_to_inner == expected_sent_to_inner
    assert sent_to_outer == expected_sent_to_outer
    assert yielded == expected_yielded
    assert stop.value.value == expected_return

    
def test_yield_from__no_yield_in_outer():
    (
        outer_no_yield, _, _, sent_to_inner, sent_to_outer
    ) = make_yield_from_demonstration()
    run_tcase(
        coroutine=outer_no_yield(),
        sent_to_inner=sent_to_inner,
        sent_to_outer=sent_to_outer,
        expected_sent_to_inner=["sent 0"],
        expected_sent_to_outer=[],
        expected_yielded=["from inner"],
        expected_return=("inner return value", "from outer_no_yield"),
    )


    
def test_yield_from__yield_before_yield_from_in_outer():
    (
        _, outer_with_yield_before, _, sent_to_inner, sent_to_outer
    ) = make_yield_from_demonstration()
    run_tcase(
        coroutine=outer_with_yield_before(),
        sent_to_inner=sent_to_inner,
        sent_to_outer=sent_to_outer,
        expected_sent_to_inner=[None],  # I would have expected "sent 1"
        expected_sent_to_outer=["sent 0"],
        expected_yielded=["yielded before"],  # I would have expected ["yielded before", "from inner"]
        expected_return=("inner return value", "from outer_with_yield_before"),
    )


    
def test_yield_from__yield_after_yield_from_in_outer():
    (
        _, _, outer_with_yield_after, sent_to_inner, sent_to_outer
    )= make_yield_from_demonstration()
    run_tcase(
        coroutine=outer_with_yield_after(),
        sent_to_inner=sent_to_inner,
        sent_to_outer=sent_to_outer,
        expected_sent_to_inner=["sent 0"],
        expected_sent_to_outer=[None],  # I would have expected "sent 1"
        expected_yielded=["from inner"],  # I would have expected ["from inner", "yielded after"]
        expected_return=("inner return value", "from outer_with_yield_after"),
    )

