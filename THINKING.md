# THINKING.md

## 1. Understand the user

The intended user is a plant supervisor or maintenance-quality user working on a live production floor. They need a quick, trusted answer from controlled plant documents instead of searching through long PDFs or chasing signatures across multiple SOPs and maintenance manuals.

This tool is useful in a factory environment where people need to confirm machine limits, alarm actions, lockout rules, inspection plans, or revision status before making a decision. In that setting, accuracy and traceability matter more than a fluent-looking answer. A wrong instruction on a safety process or a stale revision can create risk.

The user expects the system to answer in the language of the document, quote the relevant material, and clearly show where it came from. If the answer is missing, they expect the tool to say that directly instead of guessing.

## 2. User journey

The typical path is simple: the user opens the app on a workstation or on a phone on the same Wi‑Fi network, types a question in natural language, and waits for a grounded answer. The app takes that question, searches the loaded PDFs, filters the evidence using terms, identifiers, and revision information, and then decides whether the answer is supported, partial, conflicting, or unavailable.

If the question is supported, the app shows a short answer and the relevant source passages with document number, revision, page, and section. The user can check the source directly and decide whether the instruction is safe to act on. If the documents do not support the answer, the app refuses the question instead of inventing a procedure or machine setting.

This is aligned with the actual implementation: the backend loads PDFs, extracts text and metadata, builds chunks, scores evidence, and chooses either an LLM summary or the extractive fallback depending on availability and validation.

## 3. AI challenge (conversation excerpts and reflection)

I did not keep a saved conversation transcript in the repository, so I am not fabricating one. The real issues I encountered were the kinds of failures that matter in an industrial setting:

- paraphrased questions not matching the exact words in a procedure,
- older revisions being treated as current by accident,
- numbers in a question being mistaken for evidence,
- unsupported answers being dressed up as procedural facts,
- and the need to distinguish “not in the document” from “partly in the document.”

Examples of the actual problems I had to solve:

- A question about a lot size of 100 pieces used the number 100 from the question itself, but the evidence table only supported a 91–500 range. The app had to avoid treating the number as proof on its own.
- A safety question about padlock removal had to match the correct procedure even when the wording was paraphrased, not a direct keyword match.
- A question about imported material had to avoid using the older Rev 03 instruction after the current Rev 04 document explicitly superseded it.

The learning from these issues was straightforward: a useful factory assistant must be conservative. In this domain, a missed answer is much safer than a confident but wrong answer.

## 4. The improvement you added, and why you chose it

The most meaningful improvement I implemented was stronger numerical grounding and safer evidence handling for range and limit questions.

The original issue was that the app could accept a number from the user’s question as if it were evidence, even when the document never stated that number. That is dangerous in a factory setting because it creates the illusion that the system has verified a limit or a table row when it has not. I fixed that by requiring that any numeric claim in the answer be traceable to the retrieved evidence and by explicitly handling lot-size table questions using the matching row instead of a generic table heading.

I also kept the revision logic explicit. An older document may still be visible for comparison, but it cannot become current evidence unless the document metadata and supersession statements support it. The app now warns when a superseded revision also matches and surfaces the conflict clearly when the values differ.

This change improves reliability because the answer is no longer just another confident sentence. It is anchored to the actual source passage, and the user can see the exact row, page, and revision that support it.

## 5. Final reflection, including the biggest challenge you faced and how you handled it

The biggest challenge was balancing trust and usefulness. In a factory context, a system that answers confidently but quietly invents missing details is much worse than one that says “not enough information.” The hardest part was not the PDF parsing itself; it was designing the evidence checks so that the app would refuse unsupported answers, flag superseded revisions, and avoid turning table rows into arbitrary guesses.

I investigated the issue by reproducing the real question flows against the available documents and by comparing the retrieved evidence with the output text. The key insight was that numbers and identifiers are not enough by themselves. A number from the user’s question is not proof; a match must come from a retrieved and cited passage.

The practical fix was a combination of tighter validation, revision-awareness, and safer document handling. I also made the fallback mode explicit so the app remains usable even without a live API key and still speaks honestly about what the documents do and do not say.

The main thing I learned is that document-grounded AI is not mainly about writing a clever answer. It is about building trust under uncertainty. In industrial workflows, a cautious system that shows its evidence and refuses unsupported claims is better than a bold one that looks helpful but is not reliable.

TODO: Personal input required if you want this reflection to include your exact workplace context, team role, or a direct narrative about the original deployment setting.
