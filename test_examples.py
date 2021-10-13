import asyncio
import pytest


# Verify the behavior of bare yields -----------
#
# - They behave just like an explicit `yield None`

def make_send_only():
    sent = []
    def generator():
        x = yield
        sent.append(x)
    return generator(), sent


def test_send_only():
    gen, sent = make_send_only()
    out = next(gen)
    with pytest.raises(StopIteration):
        gen.send(42)
    assert out is None
    assert sent == [42]

