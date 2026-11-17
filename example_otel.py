"""Send a traced RAG + LLM call to an OTLP collector (Jaeger or Tempo, see deploy/otel/).

    docker compose -f deploy/otel/docker-compose.yml up -d
    python example_otel.py            # then open http://localhost:16686, service "ai-core-demo"
"""

import time

from llm_observability_tracer import GlobalTracer

tracer = GlobalTracer()
tracer.enable_otel(endpoint="http://localhost:4318/v1/traces", service_name="ai-core-demo")

with tracer.span("rag pipeline", inputs={"question": "When was the Eiffel Tower finished?"}):
    with tracer.span("retrieve", top_k=5) as s:
        time.sleep(0.02)
        s.metadata["hits"] = 5
    with tracer.span("llm", operation="chat", provider="llm-inference-server", model="qwen2.5-0.5b",
                     temperature=0.0, max_tokens=32, server_address="127.0.0.1", server_port=8000) as s:
        time.sleep(0.05)
        s.metadata.update(input_tokens=412, output_tokens=6, finish_reason="stop", response_model="qwen2.5-0.5b")
    with tracer.span("guardrails", operation="execute_tool", tool="llm-guardrails-shield"):
        time.sleep(0.005)

tracer.otel.flush()
print(tracer.generate_ascii_flamegraph())
