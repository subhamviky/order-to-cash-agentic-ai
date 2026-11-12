"""The model boundary: E2A SimulatedLLMService (no model access). One rule per agent,
selected by the agent's system prompt. Each rule behaves like a plausible model: useful,
but its output is always checked by the agent's _evaluate_output before it is used."""
import json
import re

from e2a_simulated_llm import SimulatedLLMService, system_contains

ROUTER, INTAKE, EXECUTION, FINANCE, KNOWLEDGE = (
    "o2c router agent", "order intake agent", "order execution agent", "finance agent", "knowledge agent")


def _user(messages) -> str:
    return str(messages[-1].get("content", ""))


def _route(messages, ctx) -> str:
    text = _user(messages)
    low = text.lower()
    if re.search(r"\b(order|buy|purchase)\b", low) and re.search(r"\bSKU-\d+\b", text, re.I):
        intent = "PLACE_ORDER"
    elif re.search(r"\bORD-[A-Z0-9]+\b", text):
        intent = "ORDER_STATUS"
    elif re.search(r"need(s)? attention|open (reconciliation )?exceptions|unmatched payments|payment exceptions", low):
        intent = "PAYMENT_EXCEPTIONS"
    elif low.rstrip().endswith("?") or re.search(r"\b(policy|terms|refund|credit|approv|write[- ]?off|discount)", low):
        intent = "POLICY_QUESTION"
    else:
        intent = "UNSUPPORTED"
    return json.dumps({"intent": intent})


def _intake(messages, ctx) -> str:
    text = _user(messages).split("\nCatalog:")[0]
    quantity = re.search(r"\b(\d+)\s*(?:units?|pcs|pieces|x)?\s*(?:of\s+)?SKU-\d+", text, re.I)
    sku = re.search(r"\bSKU-\d+\b", text, re.I)
    customer = re.search(r"\bCUST-[A-Z]+\b", text, re.I)
    if not (quantity and sku and customer):
        missing = [n for n, m in (("quantity", quantity), ("sku", sku), ("customer", customer)) if not m]
        return json.dumps({"missing": missing})
    return json.dumps({"customer_id": customer.group(0).upper(), "sku": sku.group(0).upper(),
                       "quantity": int(quantity.group(1))})


def _execution(messages, ctx) -> str:
    return "Placing the order as requested. The result will follow from the order system."


def _finance(messages, ctx) -> str:
    facts = [line[2:] for line in _user(messages).splitlines() if line.startswith("- ")]
    if not facts:
        return "I found nothing for this request."
    return "Here is what the systems of record report: " + " ".join(f if f.endswith(".") else f + "." for f in facts)


def _knowledge(messages, ctx) -> str:
    user = _user(messages)
    question = user.split("\nContext:")[0].lower()
    blocks = re.findall(r"^\[(POL-[A-Z]+-\d+)\] (.+)$", user, re.M)
    if not blocks:
        return "I do not know."
    words = set(re.findall(r"[a-z]+", question))
    policy_id, text = max(blocks, key=lambda b: len(words & set(re.findall(r"[a-z]+", b[1].lower()))))
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    content = sentences[1] if len(sentences) > 1 else sentences[0]
    return f"{content.rstrip('.')} [{policy_id}]."


def build_o2c_llm() -> SimulatedLLMService:
    return (SimulatedLLMService()
            .add_rule("router", system_contains(ROUTER), _route)
            .add_rule("intake", system_contains(INTAKE), _intake)
            .add_rule("execution", system_contains(EXECUTION), _execution)
            .add_rule("finance", system_contains(FINANCE), _finance)
            .add_rule("knowledge", system_contains(KNOWLEDGE), _knowledge))
