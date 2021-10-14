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
# - all data sent to a generator gets proxied to the
#   inner generator called by yield from.
# - all data returned by the inner generator gets proxied
#   out to the caller of the outer generator.
# - the yield from expression will evaluate to the return
#   type of the inner generator.
# - yield from never interacts directly with the return type
#   of the outer generator (it's not unusual to directly return
#   the yield from, but that has to be explicit. If we just
#   yield from and don't return, the inner return value will
#   be dropped.


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

    with pytest.raises(StopIteration) as stop:
        coroutine = outer()
        yielded = [next(coroutine)]
        for letter in "abcdefghij":
            yielded.append(coroutine.send(letter))
    assert yielded == ["from outer before", "from inner", "from outer after"]
    assert sent == ["outer before: a", "inner: 'b'", "outer after: c"]
    assert stop.value.value == ("inner return value", "second value from outer")



# What about yield from and iterators? ----------------
#
# Iterator[T] behaves exactly the same as Generator[None, T, None]


def test_yield_from_iterator():
    sent = []
    
    def yields_from_list():
        sent.append((yield "yielded_before"))
        return_from_yf = yield from ["a", "b", "c"]
        sent.append((yield "yielded_after"))
        return (return_from_yf, "returned_from_generator")

    # this test is special-cased because I'm exercising a strange edge
    # condition: we're not allowed to send data to the list iterator or we get
    #   AttributeError: 'list_iterator' object has no attribute 'send'
    # but we are allowed to send to the surroundin generator.
    #
    # From a typechecking point of view, we should probably require that
    # any generator yielding from an iterator has None as the send type;
    # other behavior is legal but unsound and should require a pyre-ignore.
    coroutine = yields_from_list()
    yielded = []
    with pytest.raises(StopIteration) as stop:
        yielded = [next(coroutine)]
        yielded.append(coroutine.send("sent_before"))
        for i in range(3):
            # we could also use next(coroutine) here, which is
            # equivalent to coroutine.send(None) according to PEP 342.
            yielded.append(coroutine.send(None))
        yielded.append(coroutine.send("sent_after"))

    assert sent == ["sent_before", "sent_after"]
    assert yielded == ["yielded_before", "a", "b", "c", "yielded_after"]
    assert stop.value.value == (None, "returned_from_generator")


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
