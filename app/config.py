from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding="utf-8")

    #Application
    app_name:str = "Order-to-Case Agentic AI"
    app_version:str = "0.1.0"
    environment: str = "development"
    debug:bool = False

    #AWS
    aws_region: str = "ap_south-1"
    aws_account_id: str = "494899930475"

    #LLM
    bedrock_model_id:str = "anthropic.claude-3-sonnet-20240229-v1:0"
    bedrock_model_id_small: = "anthropic.claude-3-haiku-20240307-v1:0"
    max_tokens: int = 2048
    temperature: float = 0.1

    #OpenSearch
    openSearch_endpoint:str = "http://localhost:9200"
    opensearch_index:str = "02c-knowledge"

    #SQS
    sqs_queue_url:str = ""
    sqs_dlq_url:str = ""

    #Tool Endpoints
    tool_base_url:str = "http"://localhost:8001"

    #Guardrails
    max_agent_steps:int = 10
    max_tool_calls:int = 5
    max_llm_time_seconds:float = 20.0

    #SLOs
    slo_p95_latency_ms: float = 2500.0
    slo_groundedness_min:float = 0.85
    slo_cost_per_workflow_usd:float = 0.03

@lru_cache()
def get_settings()->Settings:
    return Settings()