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


# async and yield from ------------
#
# But as of 3.9 using @asyncio.coroutine gives a
# deprecation warning, but you can still use it.
#
# You must use that decorator to get interop between async
# and generators. Otherwise, nesting in either direction will
# produce TypeErrors (I only have a test of one direction of
# nesting for conciseness, but I checked both).
#
# If you do mark a generator as a coroutine then
# to be type safe all yield expressions:
# - will evalueate to None (i.e. the coroutine input type is None)
# - must produce None, or asyncio will crash with a RuntimeError
#   (i.e. the coroutine output type must be None)
#
# The resulting function can be run either as an awaitable or
# as a coroutine, although it doesn't really make sense to run
# it as a generator.


def make_generators_async():
    sent = []

    async def async_inner():
        return 42

    @asyncio.coroutine
    def generator_middle():
        sent.append((yield))
        sent.append((yield))
        return (yield from async_inner())

    async def async_outer():
        return await generator_middle()

    @asyncio.coroutine
    def generator_illegal_yield():
        yield "illegal yield from asyncio.coroutine"
        return (yield from async_inner())

    def generator_not_marked_as_coroutine():
        return (yield from async_inner())

    return (
        async_outer,
        generator_middle,
        generator_illegal_yield,
        generator_not_marked_as_coroutine,
        sent
    )
    
    
def test_async_generator_interactions():
    (
        async_outer,
        generator_middle,
        generator_illegal_yield,
        generator_not_marked_as_coroutine,
        sent
    ) = make_generators_async()

    # verify that we get a TypeError when we try to use a generator
    # yielding from an async coroutine that omits the decorator
    with pytest.raises(TypeError):
        for _ in generator_not_marked_as_coroutine():
            pass
    
    # verify that it all works if we run the awaitable
    out = asyncio.run(async_outer())
    assert out == 42
    assert sent == [None, None]

    # verify that it also works to run the generator as a coroutine
    yielded = []
    with pytest.raises(StopIteration) as stop:
        coroutine = generator_middle()
        while True:
            yielded.append(next(coroutine))
    assert yielded == [None, None]
    assert stop.value.value == 42
    
    # verify that the non-None yield works if we run as a generator
    yielded = []
    with pytest.raises(StopIteration) as stop:
        coroutine = generator_illegal_yield()
        while True:  
            yielded.append(next(coroutine))
    assert yielded == ["illegal yield from asyncio.coroutine"]
    assert stop.value.value == 42

    with pytest.raises(RuntimeError):
        asyncio.run(generator_illegal_yield())
