"""
Hands-on comparison: local semantic embeddings vs. the production LLM, for the
specific sub-job of "which existing task does this free-text message refer to."

Background: today, every message the bot receives triggers one LLM call that
(among other things) decides whether you're marking an existing task done or
rescheduling it, and if so, WHICH one. This script asks: could a local
embedding model -- running entirely on your own machine, no API call, no
per-message cost -- do that specific matching job on its own?

What an embedding actually is: a model turns a piece of text into a vector of
numbers (384 of them, for the model used here) such that texts with similar
*meaning* end up as vectors pointing in similar directions. "Cosine similarity"
just measures the angle between two vectors -- 1.0 means "pointing the same
way" (same meaning), 0 means unrelated. That's what lets "finished figuring out
the ITR stuff" match "Figure out ITR" despite sharing few exact words.

What this script does:
1. Loads a small local embedding model (all-MiniLM-L6-v2, ~80MB, CPU-only).
2. Embeds a set of REAL open task titles (pulled once from the live DB, hard-
   coded below so this script never needs DB access itself) as the "haystack."
3. Runs a labeled test set of messages -- each with a KNOWN correct answer --
   through two independent approaches and scores both:
     a) Embeddings: cosine similarity against the task embeddings, picks the
        closest match, abstains ("new_task") below a similarity threshold.
     b) LLM: the exact real production prompt/harness (build_triage_system_prompt),
        via the real configured provider (whatever LLM_PROVIDER points at).

Important honesty note baked into the scoring: embeddings alone can only do
*matching* (which task, if any, does this resemble) -- they have no way to
tell "finished the thing" (mark_done) apart from "push the thing to next week"
(reschedule); that's a tense/intent distinction, not a similarity one. So the
embeddings score below measures "did it find the right task (or correctly find
none)," not full intent classification -- that gap is the actual finding, not
a scoring bug.

Run:
    pip install -e ".[experiments]"   # local-only; never touches the deployed app
    python experiments/embeddings_vs_llm.py

Reads no DB, writes nothing, makes real (tiny, ~cents) calls to your configured
LLM provider for the comparison half.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import date

from sentence_transformers import SentenceTransformer, util

from app.config import settings
from app.llm.factory import get_provider
from app.llm.prompts import build_triage_system_prompt

# Pulled once (read-only) from the real, live task list -- a realistic mix of
# short direct titles and long, paraphrase-prone ones.
REAL_TASK_TITLES = [
    "Eval frameworks",
    "Synthetic data generation",
    "Prompt engineering",
    "Respond to videographer about feedback (fix background score in haldi, "
    "fix soundtrack in baraat, better moments & slow motion & effects)",
    "Build on-call triage agent from scratch",
    "Figure out Reinforcement Learning things",
    "Explore photos for album",
    "Explore the 852hz",
    "Figure out ITR",
    "Remind to call plumber over the weekend",
    "Fix jet spray in bathroom",
    "Research and decide on gym options (Cult Fit vs regular gym vs other)",
    "Look at Karpathy LLM videos",
    "Finish the second Karpathy LLM video",
]


@dataclass
class TestCase:
    message: str
    expected_intent: str  # "mark_done" | "reschedule" | "new_task"
    expected_task: str | None = None  # exact title from REAL_TASK_TITLES, if applicable


TEST_CASES = [
    # Easy: strong word overlap with the target title.
    TestCase("finished figuring out the ITR stuff", "mark_done", "Figure out ITR"),
    TestCase("fixed the jet spray in the bathroom finally", "mark_done", "Fix jet spray in bathroom"),
    # Medium: real paraphrasing, few shared words.
    TestCase("watched and finished the second karpathy video", "mark_done", "Finish the second Karpathy LLM video"),
    TestCase(
        "sorted out the gym situation, going with cult fit",
        "mark_done",
        "Research and decide on gym options (Cult Fit vs regular gym vs other)",
    ),
    TestCase(
        "replied to the wedding videographer about the feedback",
        "mark_done",
        "Respond to videographer about feedback (fix background score in haldi, "
        "fix soundtrack in baraat, better moments & slow motion & effects)",
    ),
    TestCase("done with the reinforcement learning research", "mark_done", "Figure out Reinforcement Learning things"),
    # Hard: shares vocabulary with an existing task but is NOT that task.
    TestCase("need to look at karpathy's newer videos too", "new_task", None),
    TestCase("need to also check out the 432hz stuff, not just 852hz", "new_task", None),
    # Hard: negation -- similar wording, opposite meaning (not actually done).
    TestCase("explored some photos today, still not done though", "new_task", None),
    # Reschedule: needs date extraction, which similarity alone can't do at all.
    TestCase("push the plumber call to next weekend instead", "reschedule", "Remind to call plumber over the weekend"),
    # True negatives: no existing task resembles these.
    TestCase("need to buy groceries this weekend", "new_task", None),
    TestCase("call mom tomorrow evening", "new_task", None),
]

SIMILARITY_THRESHOLD = 0.55
DEEPSEEK_INPUT_PRICE_PER_TOKEN = 0.14 / 1_000_000
DEEPSEEK_OUTPUT_PRICE_PER_TOKEN = 0.28 / 1_000_000


def embeddings_predict(model, task_embeddings, message: str) -> dict:
    start = time.perf_counter()
    msg_embedding = model.encode(message, convert_to_tensor=True)
    scores = util.cos_sim(msg_embedding, task_embeddings)[0]
    best_idx = int(scores.argmax())
    best_score = float(scores[best_idx])
    latency = time.perf_counter() - start

    predicted_task = REAL_TASK_TITLES[best_idx] if best_score >= SIMILARITY_THRESHOLD else None
    return {"predicted_task": predicted_task, "best_score": best_score, "latency": latency}


async def llm_predict(provider, id_to_title: dict, message: str) -> dict:
    open_tasks_context = [{"id": i, "title": t, "due_date": None} for i, t in id_to_title.items()]
    prompt = build_triage_system_prompt(date.today().isoformat(), settings.tz, open_tasks_context, [])

    start = time.perf_counter()
    # Reaching into the provider's internal client (not the complete() wrapper)
    # deliberately, so we can read real token usage for a cost estimate --
    # complete() only returns text, since production code never needs usage.
    resp = await provider._client.chat.completions.create(
        model=provider._model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": message},
        ],
    )
    latency = time.perf_counter() - start

    raw = resp.choices[0].message.content
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"intent": "parse_error"}

    intent = payload.get("intent", "parse_error")
    predicted_task = None
    if intent in ("mark_done", "reschedule"):
        predicted_task = id_to_title.get(payload.get("task_id"))

    usage = resp.usage
    cost = None
    if usage is not None:
        cost = (
            usage.prompt_tokens * DEEPSEEK_INPUT_PRICE_PER_TOKEN
            + usage.completion_tokens * DEEPSEEK_OUTPUT_PRICE_PER_TOKEN
        )

    return {"intent": intent, "predicted_task": predicted_task, "latency": latency, "cost": cost, "raw": raw}


def embeddings_is_correct(case: TestCase, result: dict) -> bool:
    """Embeddings only ever produce a task match (or none) -- there's no intent
    to compare, so "correct" means: found the right task, or correctly found
    none when there wasn't one to find."""
    return result["predicted_task"] == case.expected_task


def llm_is_correct(case: TestCase, result: dict) -> bool:
    if result["intent"] != case.expected_intent:
        return False
    if case.expected_task is not None:
        return result["predicted_task"] == case.expected_task
    return True


async def main() -> None:
    print("Loading local embedding model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    task_embeddings = model.encode(REAL_TASK_TITLES, convert_to_tensor=True)
    id_to_title = dict(enumerate(REAL_TASK_TITLES))

    provider = get_provider(settings)
    print(f"LLM provider: {settings.llm_provider} / {settings.llm_model}\n")

    emb_correct = 0
    llm_correct = 0
    emb_latencies = []
    llm_latencies = []
    llm_total_cost = 0.0

    header = f"{'MESSAGE':<55} {'EXPECTED':<28} {'EMBEDDINGS':<35} {'LLM':<35}"
    print(header)
    print("-" * len(header))

    for case in TEST_CASES:
        emb_result = embeddings_predict(model, task_embeddings, case.message)
        llm_result = await llm_predict(provider, id_to_title, case.message)

        emb_ok = embeddings_is_correct(case, emb_result)
        llm_ok = llm_is_correct(case, llm_result)
        emb_correct += emb_ok
        llm_correct += llm_ok
        emb_latencies.append(emb_result["latency"])
        llm_latencies.append(llm_result["latency"])
        if llm_result["cost"] is not None:
            llm_total_cost += llm_result["cost"]

        expected_str = f"{case.expected_intent}" + (f"->{case.expected_task[:20]}" if case.expected_task else "")
        emb_str = f"{'OK' if emb_ok else 'X'} {emb_result['predicted_task'] or 'none'} ({emb_result['best_score']:.2f})"
        llm_str = f"{'OK' if llm_ok else 'X'} {llm_result['intent']}" + (
            f"->{llm_result['predicted_task'][:15]}" if llm_result["predicted_task"] else ""
        )

        print(f"{case.message[:53]:<55} {expected_str[:26]:<28} {emb_str[:33]:<35} {llm_str[:33]:<35}")

    n = len(TEST_CASES)
    print("\n" + "=" * len(header))
    print(f"Embeddings: {emb_correct}/{n} correct ({100 * emb_correct / n:.0f}%), "
          f"avg latency {1000 * sum(emb_latencies) / n:.1f}ms, cost $0 (local, no API call)")
    print(f"LLM:        {llm_correct}/{n} correct ({100 * llm_correct / n:.0f}%), "
          f"avg latency {1000 * sum(llm_latencies) / n:.1f}ms, total cost ${llm_total_cost:.5f} "
          f"(${llm_total_cost / n:.6f}/message)")


if __name__ == "__main__":
    asyncio.run(main())
