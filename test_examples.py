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


# Verify behavior of generator yield from ---------
#
# According to PEP 380:
# - both input and output yields get proxied
# - the yield from expression evaluates to the return
#   value of the inner generator
# - we still have to explicitly return, the inner return
#   value will *not* be proxied.
#
# My hand-written test appears to diverge from this
# behavior, I'm perplexed as to why. If I use the official
# unit test, which has slightly simpler control flow, then
# things appear to proxy as expected.

def make_yield_from_demonstration():

    sent = []

    def inner():
        sent.append("inner: {!r}".format((yield "from inner")))
        return "inner return value"

    def outer():
        sent.append("outer before: " + (yield "from outer before"))
        inner_return = yield from inner()
        sent.append("outer after: " + (yield "from outer after"))
        return inner_return, "second value from outer"

    return outer, sent


def test_yield_from():
    outer, sent = make_yield_from_demonstration()

    yielded = []
    with pytest.raises(StopIteration) as stop:
        coroutine = outer()
        while True:
            yielded.append(next(coroutine))
            coroutine.send("hello")
    # The value yielded from inner appears to get dropped. This seems to violate
    # PEP 380, but maybe something in my setup is incorrect.
    assert yielded == ["from outer before", "from outer after"]
    # It seems like the "hello" we send to `outer` does not get passed in
    # which similarly appears to violate PEP 380.
    assert sent == ["outer before: hello", "inner: None", "outer after: hello"]
    assert stop.value.value == ("inner return value", "second value from outer")


# The behavior above appears to me to be a bug.
#
# I think that the python interpreter may not be proxying in
# a composable way... I noticed that the unit test in CPython (see
# below) only checks the special case where the entire outer generator
# is a yield from, with no direct yields. But I don't think the PEP
# has this restriction, it seems like pretty bad behavior.
#
# Here's what I get using identical code except no bare yield
# statements in the outer generator: now it proxies correctly!

def make_yield_from_demonstration_no_outer_yields():

    sent = []

    def inner():
        sent.append("inner: {!r}".format((yield "from inner")))
        return "inner return value"

    def outer():
        inner_return = yield from inner()
        return inner_return, "second value from outer"

    return outer, sent


def test_yield_from_no_outer_yeilds():
    outer, sent = make_yield_from_demonstration_no_outer_yields()

    yielded = []
    with pytest.raises(StopIteration) as stop:
        coroutine = outer()
        while True:
            yielded.append(next(coroutine))
            coroutine.send("hello")
    # Now things proxy correctly!!
    assert yielded == ["from inner"]
    assert sent == ["inner: 'hello'"]
    assert stop.value.value == ("inner return value", "second value from outer")


def test_yield_from_CPython_version():
    # This test I pulled from the official CPython unit tests
    # in Lib/test/test_generators.py.
    #
    # It appears to respect PEP 380, so I'm not sure what the problem
    # is above
    f = lambda: (yield 1)
    def g(): return (yield 1)

    # test 'yield from'
    f2 = lambda: (yield from g())
    def g2(): return (yield from g())

    f3 = lambda: (yield from f())
    def g3(): return (yield from f())

    for gen_fun in (f, g, f2, g2, f3, g3):
        gen = gen_fun()
        assert next(gen) == 1
        with pytest.raises(StopIteration) as cm:
            gen.send(2)
        assert cm.value.value == 2
    

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
