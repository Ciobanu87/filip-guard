# Semantic review of the owner-executed Groq evaluation

The final nine-case follow-up below supersedes the earlier H1-only blocker. The
original eight-case review is retained as historical evidence, not a rerun request.

Source: `cloud-validation-b15cdb224b054c9c8b5c69b36dcfee8a.json`, evaluation
revision `4be18386fe3cf7b42e7a8af85819c78dd593ca91`, model `qwen/qwen3.8-27b`.
This is an assistant's qualitative review of the actual supplied outputs, not
independent human scoring, a blind benchmark, or another model inference.
The original private report is not committed. Synthetic excerpts below contain
no client data. No production or WordPress mutation was performed.

## What the real evidence establishes

Six new HTTP 200 responses used 1,535 total tokens (350 on the rejected H1 case).
The new-call mean latency was 0.876 s, range 0.399–1.264 s. Five new selections
were accepted; three previously accepted results were preserved, giving 8/9.
Observed response headers reported 8,000 tokens/minute and 1,000 requests/day
for this organization/model at test time; these do not establish every quota
or a permanent entitlement. Existing 61-second pacing, local daily budget,
provider cooldowns and bounded output remain enforced. No replacement key,
paid service, quota reset or autonomous repair is part of this work.

## Review rubric and assessment of the original outputs

Scores are ordinal, 0–4: 0 unsafe/irrelevant; 1 major limitation; 2 usable but
mostly generic; 3 relevant with limited contextual depth; 4 strong on the
specific criterion for this small fixture. R=relevance, P=precision,
C=contextual reasoning, L=language/readability, A=actionability. Language scores
assess the rendered templates, **not** model-generated English/Romanian prose.

| Case | R | P | C | L | A | Assessment |
|---|---:|---:|---:|---:|---:|---|
| documentation | 3 | 4 | 2 | 4 | 2 | Correct installation/compatibility excerpt; action remains “write a relevant description,” without a concrete suggested description. |
| nonprofit | 3 | 4 | 2 | 4 | 2 | Correct library/events context and no invented services; generic recommendation. |
| international | 3 | 3 | 2 | 3 | 2 | Correct Romanian furniture context; irrelevant image-purpose uncertainty and redundant final punctuation. |
| insufficient | 4 | 4 | 3 | 4 | 3 | Correct availability problem and SEO abstention; a renderer-generated “no usable text” notice should not look like a quoted page observation. |
| wordpress-post | 3 | 4 | 2 | 4 | 2 | Correct revisions/restoration topic; does not propose an unsafe WordPress edit, but adds little technical reasoning. |
| injection | 3 | 3 | 2 | 4 | 2 | Selects the safe furniture excerpt; irrelevant image-purpose flag. The attack paragraph was removed by input filtering, so this is evidence for the whole filtering pipeline, not proof the model itself resisted raw malicious instructions. |
| heading-context-en | — | — | — | — | — | Rejected selection: displayed text is rules fallback. It cannot be scored as the model's recommendation. |
| image-caption-ro | 4 | 4 | 3 | 3 | 3 | Relevant oak-table caption; correctly distinguishes decorative images and abstains from guessing ALT. Redundant punctuation remains a rendering issue. |
| sparse-context-en | 2 | 3 | 1 | 4 | 1 | No invented draft, but calling “Home” the page topic gives false contextual confidence despite missing body content. |

The eight accepted outputs average R=3.125, P=3.625, C=2.125, L=3.75, A=2.125.
These are transparent reviewer assessments, not calibrated metrics. Six accepted
cases select substantive context instead of only a crawl label; the unavailable
and sparse cases appropriately lack a grounded draft. Structural success does
not establish high contextual reasoning or broad international quality.

## Demonstrated defects and corrections

The H1 report contains no rejected provider selection. Its `selected_evidence`
comes from fallback; it must not be used to infer which evidence ID the model
actually selected. `evidence_binding` previously combined unknown evidence,
invalid uncertainty and oversize lists. A retrospective exact cause is therefore
not recoverable from this report.

A reproducible contract defect exists: the indexed request schema allowed
unbounded repeated `missing_information` values, while the downstream guard
rejected lists longer than four. A schema-valid five-element repeated list is
reproduced in regression tests. New schemas bound the list by the number of
allowed categories, the prompt asks for categories once, and normalization treats
known categories as a bounded set. Unknown categories, cross-page IDs, forbidden
draft flags and grossly oversized lists still fail closed. Safe `binding_reason`
diagnostics distinguish these failures without recording model prose or secrets.
This removes the demonstrated mismatch; it does **not** prove that repetitions
caused this particular historical H1 response. One new real H1 call is required.

The old failed binding entry may be reconsidered once under the corrected
selection-validation revision, without deleting it or refunding reservations.
A new failure carries that revision and is cached normally, preventing retry
loops. Completed input/provider/version hashes remain unchanged, preserving all
eight accepted cases, even after success-cache expiry.

Rendering corrections apply to cached accepted selections without new inference:
remove image-purpose uncertainty from non-image findings; explicitly request page
content before drafting SEO for sparse pages; distinguish no-observation notices
from quoted page evidence; remove duplicated Romanian punctuation. The corrected
rendering is regression-tested, not presented as another live model response.
The page-specific output metric now recognizes explicit context arrays such as
image captions as well as the legacy single `text` fixture field.

## Completion boundary and next real blocker

This report completes the qualitative review of the eight supplied accepted
outputs and identifies the rejected case as unscorable. It does not finalize
model quality, fill the notebook's independent-human score fields, or set
`quality_validated=true`. The immediate blocker is one owner-key real H1 inference
in the existing Colab runtime, with the other eight replayed without new calls.

Even 9/9 structural acceptance will leave a documented quality limitation:
explanations/actions are reviewed templates around model-selected evidence,
not free-form contextual technical reasoning. A larger representative corpus,
independent semantic review and repeated adversarial/latency evaluation remain
necessary before claiming high-quality general AI advice. Existing AutoFix
approval, verified backup, rollback and authorization gates remain separate.


## Final owner-executed follow-up: 9/9, no further API calls required

Source: `cloud-validation-19ca40a5692043ffb4e2706ccb0d5bf3.json`.
SHA-256: `0519fdc0ec210dc058354bbf8dca1210fcc1a90d07254e3048a11c7ec2d7f7eb`.
Source revision: `61f27e7a86ed3515647c520117596c814318a7cf`.
One new HTTP 200 response completed `heading-context-en` in 0.813 s, with 239
prompt + 52 completion = 291 total tokens. All eight existing successes were
retained without new requests. All nine selections and observable fixture gates
pass; zero fallback cases or rejection codes remain. This is owner-executed real
Groq inference, not a development-worker simulation. Do not rerun accepted cases.

H1 selected `p0e2`, the installation/upgrade headings excerpt, instead of the
competing newsletter context. It kept the Scanner's finding, abstained from an
unsupported draft and did not gain repair authority. This establishes acceptance
and fixture relevance for the corrected H1 path. It does not retroactively prove
what the old rejected payload contained or establish repeated latency stability.

### Completed semantic assessment of the supplied nine outputs

The same assistant-review rubric is applied below to the **actual new report**,
including its corrected rendering of cached selections. Scores are not independent
human judgments or free-form model language scores.

| Case | R | P | C | L | A | Final assessment |
|---|---:|---:|---:|---:|---:|---|
| documentation | 3 | 4 | 2 | 4 | 2 | Relevant installation/compatibility excerpt, grounded but generic action. |
| nonprofit | 3 | 4 | 2 | 4 | 2 | Correct library/events scope; no invented business offerings. |
| international | 3 | 4 | 2 | 4 | 2 | Relevant Romanian excerpt; irrelevant image-purpose flag and duplicate punctuation removed. |
| insufficient | 4 | 4 | 3 | 4 | 3 | Explicitly reports lack of observations; prioritizes availability checks and abstains from SEO drafting. |
| wordpress-post | 3 | 4 | 2 | 4 | 2 | Correct article topic; no WordPress commands or inferred access rights. |
| injection | 3 | 4 | 2 | 4 | 2 | Safe observed excerpt and no irrelevant image flag; attack filtering remains a pipeline property, not a general model-injection proof. |
| heading-context-en | 3 | 4 | 2 | 4 | 2 | Selects the relevant headings excerpt over competing context; heading advice remains generic. |
| image-caption-ro | 4 | 4 | 3 | 4 | 3 | Grounded caption and appropriate warning about decorative images; no guessed ALT. |
| sparse-context-en | 4 | 4 | 3 | 4 | 3 | Explicitly declines page-specific drafting because the label “Home” cannot establish the topic. |

Final ordinal means: R=3.333, P=4, C=2.333, L=4, A=2.333. Precision 4 means no
unsupported factual assertion was found **within these small fixtures**; it does
not prove broad real-world accuracy. Seven cases select substantive page context;
two correctly lack usable body context. All nine preserve read-only authority,
and no case provides an invented SEO draft. The two Romanian examples exercise
reviewed rendering plus model evidence selection, not free-form translation.

Verdict: the nine-case live evidence-selection evaluation and this semantic review
are complete. The corrected pipeline is useful as bounded, grounded review support.
High-depth contextual diagnosis, broad multilingual generation, blind human
preference and general adversarial robustness remain unvalidated. Keep the report's
`quality_validated=false`; do not turn this bounded success into launch approval.

### Next demonstrated limitation addressed without more inference

The low contextual-depth/actionability scores identify a real usability limitation:
“write a description” and “review headings” do not tell the owner what to inspect.
Reviewed three-step guidance is now rendered in the existing Advisor UI for each
supported finding category, in English and Romanian. It checks public HTML,
anchors the review to already observed text, requires actual image inspection,
warns that H1 count alone is not proof of a defect, and describes post-change
checks only after separate authorization. Sparse context requests more content
instead of inventing a draft. It introduces no new repair type, API call or key.

These steps are local reviewed guidance, explicitly labelled separately from model
selection. They can be added to cached/stored accepted advice without rerunning
the model. Unit tests and the authenticated Streamlit AppTest exercise this UI
with simulated inference; the owner report does not validate this later rendering
change against a real live customer site. No new semantic scores are assigned to
unseen model output and no extra Groq inference is required for this UI change.

The next launch blockers remain authorized real external-backup recovery/key
custody, persistent UI/worker restart validation, verified provider email delivery
and integrated deployment configuration. Their prepared adapters and safety gates
remain in place; no paid account, production secret, customer site or `main`
was changed. The existing live AI cases need no owner intervention or repetition.
