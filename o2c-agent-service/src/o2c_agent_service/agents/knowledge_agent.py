"""KnowledgeAgent: answers policy questions, grounded in retrieved policy paragraphs.
Retrieval happens while the prompt is built; the answer must cite what was retrieved and
pass the pipeline's groundedness check, or the agent says it does not know."""
import logging

from e2a_base import BaseAgent

from ..rag.policy_rag import POLICY_ID, PolicyRAGPipeline
from ..services.llm import KNOWLEDGE


class KnowledgeAgent(BaseAgent):
    agent_name = 'KnowledgeAgent'

    def __init__(self, rag: PolicyRAGPipeline) -> None:
        self.rag = rag

    def _build_messages(self, state, config=None, **kwargs) -> list:
        retrieved = self.rag.retrieve(state['query'], config, tenant_id=kwargs['tenant_id'], rerank_top_n=3)
        state['retrieved'] = retrieved
        context = '\n'.join(f"[{r['policy_id']}] {r['text']}" for r in retrieved)
        return [{'role': 'system', 'content': f'You are the {KNOWLEDGE}. Answer in one sentence from the context '
                                              'and cite the policy id in brackets.'},
                {'role': 'user', 'content': f"{state['query']}\nContext:\n{context}"}]

    def _apply_policy(self, state, config=None, **kwargs) -> None:
        if not state.get('tenant_id'):
            raise PermissionError('a tenant is required')

    def _evaluate_output(self, response, state, config=None, **kwargs) -> float:
        text = (response or {}).get('text', '')
        # E2A reference pattern: the agent calls its composed pipeline's evaluation hook
        score = self.rag._evaluate_answer(text, config, retrieved=state.get('retrieved', []))
        state['groundedness'] = score
        retrieved = {r['policy_id'] for r in state.get('retrieved', [])}
        state['citations'] = sorted(set(POLICY_ID.findall(text)) & retrieved)
        return score

    def _fallback(self, state, config=None, **kwargs):
        state['citations'] = []
        return {'text': 'I could not find an O2C policy that answers this question.', 'degraded': True}

    def _handle_error(self, error, state, config=None, **kwargs):
        logging.error(f'[{self.agent_name}] {error}')
        state.setdefault('errors', []).append(str(error))
        return state
