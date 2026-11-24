# Quality evaluation after the first accepted real inference

## Evidence reviewed

The owner's report for `1a70f095b1a02839e4fc714c517529acfd6532aa` confirms one fresh
Groq response and accepted selection: HTTP 200, 189 input + 43 output = 232 tokens,
1.258 seconds, no quota failure and no repair authority. Provider headers report
8,000 TPM and 1,000 RPD for that response. This validates that connection/contract
path once, not ongoing stability or the quality of recommendations.

The accepted recommendation quoted only the short label **craft**, rather than
the supplied paragraph about handmade oak dining tables. Its solution stayed
generic, `candidate_page_specific` was false and the draft was null. Abstaining
from a draft is safe, but it is not evidence of an effective SEO recommendation.
More seriously, `content_unavailable` was included despite supplied page content.

Assessment of this one real sample: the issue matches Scanner rules, the wording
is readable English and no unsupported business claims/repair authority were
introduced; page-specific context is inadequate and the uncertainty claim is
contradictory. There is no Romanian sample in this report. No blind human study,
SEO ranking improvement, multilingual model-writing quality or stability is
inferred from this single response. The original private attachment is unchanged
and is not copied into the public repository.

## Demonstrated corrections

The cloud contract previously allowed any same-page fact, including a one-word
label, and allowed the model to claim missing content regardless of the input.
The selector now excludes short labels when substantive page-body evidence is
available, while preserving multiple meaningful candidates and full titles.
The normalizer/guard reject `content_unavailable` when body text was actually
provided. When no body text exists, that limitation is derived by the server,
not guessed by the model. Short/sparse pages remain usable, with abstention and
missing context rather than invented facts.

These checks are intentionally narrow: length/word-count heuristics do not prove
semantic relevance. A model can still select an irrelevant *substantive* excerpt;
that is why the next suite includes competing evidence and explicit reference
choices. Schema/safety acceptance remains separate from observable quality gates
and unset human-review scores. The normalizer, factual draft restrictions and
all WordPress authorization/approval/backup/rollback gates remain enabled.

Prompt/cache and cloud-contract versions advance, so the old weak selection is
not reused as new-quality evidence. No call reservations, cooldowns or budgets
are deleted or refunded. No key, provider account or billing changes are made.

## Continuation suite — no repeated connection probe

The updated Colab notebook runs at most nine new synthetic cases:

| Case | Language | Question |
| --- | --- | --- |
| documentation | EN | Relevant installation/version description |
| nonprofit | EN | Library hours/events without invented services |
| international | RO | Romanian page evidence and reviewed RO rendering |
| insufficient | EN | Unavailable page; no invented SEO draft |
| wordpress-post | EN | Topic-specific article advice; no site writes |
| injection | EN | Filtered malicious instructions; data cannot grant tools |
| heading-context-en | EN | H1 issue with relevant and distracting paragraphs |
| image-caption-ro | RO | Observed caption versus unrelated shop text; image purpose stays unknown |
| sparse-context-en | EN | Short title without body; missing context and draft abstention |

The `craft` case is omitted because its real response has already been reviewed.
The expected-evidence oracle is never included in the model prompt. The tests'
simulated oracle selection is explicitly labeled simulation, not model reasoning.
The injected instruction is filtered by the pipeline; passing this case does not
prove universal prompt-injection resistance of the model.

For every case the report keeps: new provider response versus cache/fallback,
structural acceptance, exact evidence selected, observed Scanner issue, grounding,
uncertainty consistency, expected fixture relevance, required abstention, display
language, safety, usage and latency. `quality_review.checks` are reproducible
observable proxies; they are not an automatic semantic judge. Human relevance,
precision and language scores remain unset. `quality_validated` stays false.

English/Romanian explanations still use reviewed templates around model-selected
evidence. The evaluation does not mislabel them as free-form AI translation or
fully generative diagnosis. The model's actual task is evidence selection and
bounded prioritization. Broader reasoning/generation quality is not yet proven.

The suite retains 256-token output bounds per single-finding request, 61-second
pacing, persistent shared limits and all provider cooldowns. It stops on local
admission failure or decisive provider error, and after two consecutive invalid
responses, rather than consuming the rest of the free allowance blindly. It does
not reset a quota or automatically retry failed requests.

## Next real boundary

Reopen the updated GitHub Colab notebook, use the existing Secret and shared
ledger, confirm the bounded quality run, then run cells and return the sanitized
JSON. No new API key, subscription, local computer or server is required.

The Work environment cannot read the owner's Colab Secret. No additional real
inference was performed here. Automated fixture/contract tests and the prepared
continuation are complete; actual English/Romanian holdout outputs and latency
still require that owner-authorized Colab run. If quotas stop it, preserve the
report and wait for admission; do not erase state or change accounts.

### Colab credential-readiness recovery (24 November 2026)

The attached owner report contains three accepted cached results (documentation,
nonprofit, international), **zero new requests/responses**, two cached
`key_unavailable` failures and two fresh input failures near ten seconds. It does
not establish that the key is invalid or permission was revoked. The previous
notebook discarded the successfully checked key and called `userdata.get()` again
for every provider request. Colab's official `google/colab/userdata.py` uses a
frontend GetSecret RPC with a ten-second timeout; the old generic diagnostic
cannot establish which underlying exception occurred retrospectively.

Setup now reads the existing secret once into a redacted session-only holder.
Timeout, permission denial, missing secret, invalid key and closed holder have
separate allowlisted diagnostics without exception bodies or secret values.
Credential readiness is checked before a new budget reservation. Old credential
failures are not replayed as persistent model-validation failures; existing
reservations, pacing and provider-wide 429 cooldowns remain unchanged. A setup
failure invalidates the old notebook advisor, so running a later cell cannot
silently reuse stale configuration. No new key or credential file is required.

Quality continuation reads previously accepted immutable synthetic fixture results
using the exact original input/version/provider hash and original scoped cache
key, even after the one-hour success-cache expiry. It does **not** make expired
live-site advice reusable. Completed cases remain visibly historical; new request,
response and real-inference counters exclude them. The three accepted fixtures
therefore leave six pending cases, with no reset, automatic retry or repeated
secret RPC. This history is durable across application/source restarts using the
same SQLite ledger, not destruction of the free Colab runtime. No key or ledger
is uploaded automatically to a third-party persistence service.

Run the updated notebook in the existing Colab runtime with the existing secret
and confirmations. Keep that runtime/ledger when blocked by provider quota. Review
the downloaded report's new-call counters and selected evidence. English/Romanian
rendering still uses reviewed templates; fixture gates do not establish human
semantic quality. No new live inference was available in the development worker.

### Phone-only, one-cell continuation without cloud-browser authentication

`colab_resume_quality.py` runs inside the owner's already connected Colab kernel.
It requires the existing SQLite ledger and the exact eight completed quality
fixtures before any Groq call; it never creates an empty ledger to replace lost
history. Evaluation source is pinned to `61f27e7a86ed3515647c520117596c814318a7cf`.
The helper refreshes imported source without restarting the kernel, reads the
existing Colab secret once, resumes only unfinished fixtures using the unchanged
budget/cooldown implementation, writes a private uniquely named report beside the
ledger and triggers its download. It imports no AutoFix component and never logs
a credential. Already completed full evaluations require no secret lookup.

The owner only adds one new code cell to the existing notebook and runs a pinned
GitHub download of this helper using `urllib.request` and `exec(compile(...))`.
This deliberately does not require cloud-browser Google sign-in, a new notebook,
a new runtime, credential replacement, billing or editing multiple long cells.
Google Colab still hosts the execution; a disconnected/destroyed runtime, missing
history, secret permission error or active provider limit remains a real blocker.
Development tests are offline contracts, not new owner-key live inference.


### H1-only real continuation after the six-call report

The helper now requires all eight accepted fixtures from the owner's latest real
report and permits at most one unfinished fixture (`heading-context-en`). A runtime
with only the first three results is blocked before reading the key or calling
Groq, rather than repeating five subsequently accepted cases. The helper pins the
corrected selection-validator source revision shown above, preserving the existing
input hashes, ledger, reservations and provider cooldowns. Existing cached model
selections receive the reviewed rendering fixes without new inference. See
`AI_SEMANTIC_REVIEW_2026_11_24.md` for the actual-output assessment and its limits.
