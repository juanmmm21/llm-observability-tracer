# LLM Observability Tracer

Un motor de monitoreo y telemetria de extremo a extremo (End-to-End) disenado para registrar la ejecucion de llamadas de modelos de lenguaje (LLMs), consumos de tokens, estimaciones de coste de API y latencias de procesos mediante arboles de ejecucion estructurados (Spans).

Este modulo permite inyectar observabilidad profunda en pipelines complejos (como RAG o sistemas de agentes autonomos) y exportar bitacoras detalladas e interfaces interactivas de analisis de rendimiento (Flame Graphs).

## Arquitectura y Funcionamiento

### 1. Representacion por Spans
Un **Span** representa una unidad logica de trabajo o paso de procesamiento (por ejemplo, una llamada de busqueda en base de datos vectorial, una validacion de seguridad, o una inferencia de LLM). Cada Span registra:
*   Identificadores unicos (ID y Parent ID) para reconstruir la relacion jerarquica de arbol.
*   Marcas de tiempo de inicio y fin para evaluar el rendimiento fisico en milisegundos.
*   Argumentos de entrada (inputs) y resultados de retorno (outputs) para auditoria forense.
*   Metadatos flexibles (como recuento de tokens de entrada/salida y calculo de costos).
*   Detalles de excepciones en caso de fallo, permitiendo trazar errores de forma visual.

### 2. Aislamiento por Contexto (ContextVar)
Para dar soporte a servidores web concurrentes (como FastAPI) y multitarea asincrona, el rastreador almacena la pila de Spans activos utilizando `contextvars.ContextVar`. Esto garantiza que los hilos o tareas asincronas corran de forma aislada, evitando colisiones de trazas de peticiones de distintos usuarios.

### 3. Visualizaciones y Exportes
El rastreador permite exportar el arbol de trazas recolectado en dos formatos:
*   **Flame Graph ASCII:** Un resumen jerarquico de texto en consola para depuracion rapida.
*   **Flame Graph HTML Interactivo:** Una aplicacion web independiente disenada con estetica moderna (Neon Dark Violet Theme) que muestra barras temporales interactivas y paneles de detalles al hacer click en los bloques de ejecucion.

## Requisitos de Instalacion

*   Python 3.8 o superior
*   Pydantic

Para instalar las dependencias locales en su entorno virtual, ejecute:

```bash
pip install -r requirements.txt
```

## Pruebas y Verificacion

1.  **Ejecutar la suite de pruebas unitarias:**
    ```bash
    python -m unittest test_tracer.py
    ```
2.  **Ejecutar la demostracion de trazado:**
    ```bash
    python example.py
    ```
    El script simulara un pipeline completo de RAG instrumentando pasos de guardrails, busqueda semantica, reranking y generacion de texto. Mostrara la linea temporal en consola y exportara el visualizador interactivo HTML en su directorio local.
