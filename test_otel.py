import unittest

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from llm_observability_tracer.otel import OTelBridge, genai_attributes, span_name
from llm_observability_tracer.tracer import GlobalTracer


def make(capture_content: bool = False):
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = GlobalTracer(otel=OTelBridge(tracer_provider=provider, capture_content=capture_content))
    return tracer, exporter


class TestGenAIConventions(unittest.TestCase):
    def test_attribute_mapping(self) -> None:
        attrs = genai_attributes(
            {"operation": "chat", "provider": "ollama", "model": "qwen2.5:0.5b", "input_tokens": 12,
             "output_tokens": 30, "finish_reason": "stop", "temperature": 0.0, "custom": "x", "nested": {"a": 1}}
        )
        self.assertEqual(attrs["gen_ai.operation.name"], "chat")
        self.assertEqual(attrs["gen_ai.provider.name"], "ollama")
        self.assertEqual(attrs["gen_ai.system"], "ollama")
        self.assertEqual(attrs["gen_ai.request.model"], "qwen2.5:0.5b")
        self.assertEqual(attrs["gen_ai.usage.input_tokens"], 12)
        self.assertEqual(attrs["gen_ai.usage.output_tokens"], 30)
        self.assertEqual(attrs["gen_ai.response.finish_reasons"], ["stop"])
        self.assertEqual(attrs["ai_core.custom"], "x")
        self.assertNotIn("ai_core.nested", attrs)

    def test_request_keys_only_on_model_calls(self) -> None:
        attrs = genai_attributes({"top_k": 5, "model": "minilm"})
        self.assertEqual(attrs, {"ai_core.top_k": 5, "ai_core.model": "minilm"})

    def test_span_names(self) -> None:
        self.assertEqual(span_name("llm", {"operation": "chat", "model": "m"}), "chat m")
        self.assertEqual(span_name("t", {"operation": "execute_tool", "tool": "search"}), "execute_tool search")
        self.assertEqual(span_name("retrieve", {}), "retrieve")


class TestLiveExport(unittest.TestCase):
    def test_tree_kinds_attributes_and_timing(self) -> None:
        tracer, exporter = make()
        with tracer.span("pipeline", inputs={"prompt": "secreto personal"}):
            with tracer.span("retrieve"):
                pass
            with tracer.span("llm", inputs={"messages": "hola"}, operation="chat", provider="openai", model="m1") as s:
                s.metadata.update(input_tokens=5, output_tokens=7, finish_reason="stop")
                s.outputs["text"] = "respuesta"
        spans = {sp.name: sp for sp in exporter.get_finished_spans()}
        self.assertEqual(set(spans), {"pipeline", "retrieve", "chat m1"})
        root, chat = spans["pipeline"], spans["chat m1"]
        self.assertEqual(chat.parent.span_id, root.context.span_id)
        self.assertEqual(spans["retrieve"].parent.span_id, root.context.span_id)
        self.assertEqual(chat.context.trace_id, root.context.trace_id)
        self.assertEqual(chat.kind, SpanKind.CLIENT)
        self.assertEqual(spans["retrieve"].kind, SpanKind.INTERNAL)
        self.assertEqual(chat.attributes["gen_ai.usage.output_tokens"], 7)
        self.assertEqual(chat.attributes["ai_core.span"], "llm")
        self.assertLessEqual(root.start_time, chat.start_time)
        self.assertLessEqual(chat.end_time, root.end_time)

    def test_content_is_not_exported_by_default(self) -> None:
        tracer, exporter = make()
        with tracer.span("llm", inputs={"prompt": "dato privado"}, operation="chat", model="m") as s:
            s.outputs["text"] = "otro dato privado"
        for sp in exporter.get_finished_spans():
            self.assertNotIn("dato privado", str(dict(sp.attributes)))

    def test_content_capture_is_opt_in(self) -> None:
        tracer, exporter = make(capture_content=True)
        with tracer.span("llm", inputs={"prompt": "hola"}, operation="chat", model="m") as s:
            s.outputs["text"] = "adios"
        sp = exporter.get_finished_spans()[0]
        self.assertIn("hola", sp.attributes["gen_ai.input.messages"])
        self.assertIn("adios", sp.attributes["gen_ai.output.messages"])

    def test_errors_set_status(self) -> None:
        tracer, exporter = make()
        with self.assertRaises(ValueError):
            with tracer.span("tool", operation="execute_tool", tool="calc"):
                raise ValueError("boom")
        sp = exporter.get_finished_spans()[0]
        self.assertEqual(sp.name, "execute_tool calc")
        self.assertEqual(sp.status.status_code, StatusCode.ERROR)
        self.assertEqual(sp.attributes["error.type"], "ValueError")

    def test_record_span_with_explicit_times(self) -> None:
        tracer, exporter = make()
        root = tracer.record_span("turn general", 1000.0, 1002.5, {"origin": "telegram"})
        tracer.record_span("route", 1000.1, 1000.3, parent=root)
        tracer.record_span("llm", 1000.4, 1002.4, {"operation": "chat", "model": "gemini"}, parent=root)
        spans = {sp.name: sp for sp in exporter.get_finished_spans()}
        self.assertEqual(spans["turn general"].start_time, 1000 * 10**9)
        self.assertEqual(spans["turn general"].end_time, int(1002.5 * 10**9))
        self.assertEqual(spans["chat gemini"].parent.span_id, spans["turn general"].context.span_id)
        self.assertEqual(spans["route"].attributes.get("ai_core.origin"), None)
        tracer.record_tree([root])
        self.assertEqual(tracer.root_spans, [])

    def test_bridge_failures_never_break_tracing(self) -> None:
        class Broken:
            def on_start(self, span, parent):
                raise RuntimeError("collector down")

            def on_end(self, span):
                raise RuntimeError("collector down")

        tracer = GlobalTracer(otel=Broken())
        with tracer.span("x"):
            pass
        self.assertEqual(tracer.get_trace_tree()[0]["name"], "x")


if __name__ == "__main__":
    unittest.main()
