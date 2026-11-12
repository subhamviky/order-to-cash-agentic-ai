"""KnowledgeAgent: answers policy questions, grounded in retrieved policy paragraphs
(E2A v1.2 contract). Retrieval is a read in _prepare, after the firewall has screened the
question; the answer must cite what was retrieved and pass the pipeline's public
evaluate_answer(), or the agent says it does not know."""
import logging

from e2a import BaseAgent, RAGPipeline

from ..rag.policy_rag import POLICY_ID
from ..services.llm import KNOWLEDGE


class KnowledgeAgent(BaseAgent):
    agent_name = 'KnowledgeAgent'

    def __init__(self, rag: RAGPipeline) -> None:
        self.rag = rag

    def _prepare(self, state, ctx) -> None:
        state['retrieved'] = self.rag.retrieve(state['query'], dict(ctx.settings), ctx=ctx, rerank_top_n=3)

    def _build_messages(self, state, ctx) -> list:
        context = '\n'.join(f"[{r['policy_id']}] {r['text']}" for r in state['retrieved'])
        return [{'role': 'system', 'content': f'You are the {KNOWLEDGE}. Answer in one sentence from the context '
                                              'and cite the policy id in brackets.'},
                {'role': 'user', 'content': f"{state['query']}\nContext:\n{context}"}]

    def _evaluate_output(self, response, state, ctx) -> float:
        text = (response or {}).get('text', '')
        score = self.rag.evaluate_answer(text, state.get('retrieved', []), dict(ctx.settings))
        state['groundedness'] = score
        retrieved = {r['policy_id'] for r in state.get('retrieved', [])}
        state['citations'] = sorted(set(POLICY_ID.findall(text)) & retrieved)
        return score

    def _fallback(self, state, ctx):
        state['citations'] = []
        return {'text': 'I could not find an O2C policy that answers this question.', 'degraded': True}

    def _handle_error(self, error, state, ctx):
        logging.error(f'[{self.agent_name}] {error}')
        state.setdefault('errors', []).append(str(error))
