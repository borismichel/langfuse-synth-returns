"""Two turns in one process start parentless roots, even if a span leaked."""
from contextlib import contextmanager

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from synth.returns_agent.agent import run_ticket
from synth.returns_agent.tools import FetchedSkill


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Usage:
    input_tokens = 3
    output_tokens = 2


class _Response:
    content = [
        _Block('{"decision":"not_applicable","refund_amount":null,"reply":"ok"}')
    ]
    usage = _Usage()


class _Messages:
    def create(self, **_kwargs):
        return _Response()


class _Anthropic:
    messages = _Messages()


class _Node:
    def update(self, **_kwargs):
        return self

    @contextmanager
    def _child(self):
        yield self

    def observation(self, *_args, **_kwargs):
        return self._child()

    def span(self, *_args, **_kwargs):
        return self._child()

    def generation(self, *_args, **_kwargs):
        return self._child()

    def tool(self, *_args, **_kwargs):
        return self._child()


class _Emitter:
    """Starts the root the way LiveEmitter does: as the current OTel span."""

    def __init__(self):
        self.provider = TracerProvider()
        self.exporter = InMemorySpanExporter()
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.tracer = self.provider.get_tracer("returns-turns")

    @contextmanager
    def trace(self, name, **_kwargs):
        with self.tracer.start_as_current_span(name) as span:
            assert span.name == name
            yield _Node()


def _skill() -> FetchedSkill:
    return FetchedSkill(
        name="returns-and-refunds",
        version=1,
        files={
            "SKILL.md": (
                "---\nname: returns-and-refunds\n"
                "description: Helps with customer orders\n---\nbody\n"
            )
        },
    )


def test_two_sequential_turns_have_no_parent_span():
    leaked = NonRecordingSpan(
        SpanContext(
            trace_id=0x10,
            span_id=0x20,
            is_remote=False,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )
    )
    token = otel_context.attach(trace.set_span_in_context(leaked))
    emitter = _Emitter()
    try:
        ticket = {
            "customer_message": "Where is my parcel?",
            "order": {"order_id": "KC-LIVE", "items": []},
            "customer_tier": "standard",
        }
        for turn in (1, 2):
            run_ticket(
                _skill(),
                ticket,
                emitter=emitter,
                anthropic_client=_Anthropic(),
                model="claude-sonnet-5-5",
                session_id="kc-session",
                metadata={"turn": str(turn)},
            )
        assert (
            trace.get_current_span().get_span_context().span_id
            == leaked.get_span_context().span_id
        )
    finally:
        otel_context.detach(token)
    finished = emitter.exporter.get_finished_spans()
    roots = [span for span in finished if span.name == "returns-ticket"]
    assert len(roots) == 2
    assert all(span.parent is None for span in roots)
