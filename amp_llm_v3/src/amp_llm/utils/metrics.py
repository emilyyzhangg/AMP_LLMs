# src/amp_llm/utils/metrics.py
from dataclasses import dataclass
from time import time
from typing import Dict

@dataclass
class APIMetrics:
    total_requests: int = 0
    failed_requests: int = 0
    total_latency: float = 0.0
    
    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.total_requests - self.failed_requests) / self.total_requests
    
    @property
    def avg_latency(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_latency / self.total_requests

class MetricsCollector:
    def __init__(self):
        self.api_metrics: Dict[str, APIMetrics] = {}