#!/usr/bin/env bash
# P3.sh - Milestone P3: Emotion from Text (PDR M3)
# Depends on: P2 merged to main and tagged p2-done.
# Contains NO application logic: only git/dir setup and prompt-filled seed files.
set -euo pipefail

if ! git rev-parse -q --verify "refs/tags/p2-done" >/dev/null; then
  echo "ERROR: tag p2-done not found. Finish P2 (implement, test, merge to main, tag p2-done) before running P3.sh"
  exit 1
fi

echo "Checking out milestone branch..."
BRANCH_NAME="milestone/p3-emotion"
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "")
if [ "$CURRENT_BRANCH" != "$BRANCH_NAME" ]; then
    if git rev-parse --verify "$BRANCH_NAME" >/dev/null 2>&1; then
        echo "Checking out existing branch: $BRANCH_NAME"
        git checkout "$BRANCH_NAME"
    else
        echo "Creating and checking out branch: $BRANCH_NAME from main"
        git checkout main
        git checkout -b "$BRANCH_NAME"
    fi
else
    echo "Already on milestone branch: $BRANCH_NAME"
fi

echo "Creating directories for P3..."
mkdir -p docs/seed_extensions

echo "Seeding P3 files..."

cat << 'EOF' > src/voxclone/engines/real_emotion.py
"""
FILE PURPOSE: DistilRoBERTa emotion classifier adapter implementing EmotionEngine (PDR 5.4).
PROMPT FOR LLM IMPLEMENTATION:
1. class RealEmotion with key "emotion". Import transformers and torch lazily inside load()/classify(); importing this module must be cheap.
2. load(device): build a transformers text-classification pipeline for the model id "j-hartmann/emotion-english-distilroberta-base" (device index 0 for cuda, -1 for cpu), returning only the top label per text. If weights are not cached and HF_HUB_OFFLINE=1 raise ModelWeightsMissingError (VX-310) with the `system fetch-models` hint.
3. classify(texts) -> list[str]: batch the inputs (batch size 16), truncate each text to the model maximum length, lower-case the returned labels, and guarantee each label is in EMOTION_LABELS (anything else becomes "neutral" and logs a WARNING). Empty list in, empty list out. Output order equals input order.
4. unload(): delete the pipeline object; set is_loaded false.
5. estimated_vram_mb() returns 600 [DEFAULT estimate; confirm in the GPU smoke test].
6. Map CUDA out-of-memory errors to RuntimeError("out of memory") for uniform handling by ModelManager.
DEBUGGING:
# print(f"[DEBUG] RealEmotion.classify n={len(texts)} -> {labels}")
OFFLINE DOCKER TEST CASES:
- `import voxclone.engines.real_emotion` does not import torch or transformers (check sys.modules).
- With HF_HUB_OFFLINE=1 and an empty cache, load() raises VX-310 (mock the pipeline factory).
- With a mocked pipeline returning "LABEL_X", classify returns "neutral" and logs a warning.
- classify([]) returns [] without loading anything.
"""
EOF

cat << 'EOF' > src/voxclone/pipelines/emotion_mapping.py
"""
FILE PURPOSE: Turn emotion labels into TTS expressiveness values and run the emotion stage (TDR 3.8).
PROMPT FOR LLM IMPLEMENTATION:
1. Dataclass EmotionResult(label: str, expressiveness: float).
2. get_emotion_map(settings_service) -> dict[str, float]: start from constants.EMOTION_TO_EXPRESSIVENESS and apply the optional user override stored under the setting key "emotion_map" (dict label -> float); ignore unknown labels with a WARNING; clamp each value to [0.25, 1.0].
3. map_label(label, emotion_map) -> float; unknown labels fall back to the neutral value.
4. resolve_expressiveness(emotion_mode, label, emotion_map) -> float: for emotion_mode "calm"/"normal"/"expressive" return the EMOTION_MODE_TO_EXPRESSIVENESS value for the WHOLE job (user override replaces detection, TDR 3.8); for "auto" return map_label(label, emotion_map).
5. classify_passages(model_manager, passages, job_id=None, emotion_map=None) -> list[EmotionResult]: inside `with model_manager.use("emotion", job_id=job_id) as engine:` classify all passages in ONE batch; return results in passage order. This function is the only place the emotion model is requested, and it never touches the TTS model.
6. Pure mapping functions must not import torch.
DEBUGGING:
# print(f"[DEBUG] emotion {i}: {label} -> {expr:.2f} (mode={emotion_mode})")
OFFLINE DOCKER TEST CASES:
- Default map returns anger 0.90, sadness 0.30, neutral 0.40.
- Mode "calm" ignores the label and returns 0.30 for every passage; mode "auto" with label "joy" returns 0.70.
- A user override {"joy": 0.9} changes joy only; {"joy": 5.0} is clamped to 1.0; {"bogus": 0.5} is ignored.
- classify_passages with the fake engine returns one result per passage, in order, and loads the emotion model once.
- The fake registry shows the emotion engine loaded and no TTS engine loaded during this call.
"""
EOF

cat << 'EOF' > tests/unit/test_emotion_mapping.py
"""
FILE PURPOSE: Cover mapping functions, overrides and the classify stage.
PROMPT FOR LLM IMPLEMENTATION:
1. Parametrize all seven labels against the TDR 3.8 table; test the three fixed modes; test override merging, clamping and ignoring unknown labels.
2. classify_passages tests with FakeEmotion: ordering, empty list, single model-load event, error mapping when the engine raises.
3. Assert that an emotion_mode of "auto" and label None raises or falls back to neutral exactly as the seed specifies.
DEBUGGING:
# print(f"[DEBUG] mapping case {label}/{mode} -> {value}")
OFFLINE DOCKER TEST CASES:
- All seven label values equal the table; every value is within [0.25, 1.0].
- classify_passages([]) returns [] and records no model event.
"""
EOF

cat << 'EOF' > tests/gpu/test_real_emotion_smoke.py
"""
FILE PURPOSE: OPT-IN real-model check for the emotion classifier (pytest -m gpu).
PROMPT FOR LLM IMPLEMENTATION:
1. Mark gpu; skip when CUDA is unavailable or the model is not cached (VX-310).
2. Through the real ModelManager classify five hand-written sentences expressing joy, sadness, anger, fear and neutral content; assert every returned label is in EMOTION_LABELS and that at least 3 of the 5 match the intended emotion.
3. Print measured VRAM so estimated_vram_mb can be corrected; assert the emotion model is unloaded (resident None) after calling manager.free().
DEBUGGING:
# print(f"[DEBUG] emotion smoke labels={labels} vram={vram_mb} MB")
OFFLINE DOCKER TEST CASES:
- Skipped on a CPU-only container.
- On the GPU machine at least 3 of 5 labels match.
"""
EOF

cat << 'EOF' > docs/seed_extensions/P3_extensions.md
<!--
FILE PURPOSE: Additive changes P3 needs in files that ALREADY exist. Give this document to code-implementer with the current contents of each listed file. Keep ALL existing code, apply only the additions, re-emit the complete file.
-->

# P3 Extensions

## EXTEND: src/voxclone/pipelines/text_pipeline.py
PROMPT FOR LLM IMPLEMENTATION:
1. Replace the P2 behaviour "auto is treated as normal" with a real two-stage flow: when job.emotion_mode == "auto", after splitting add stage "emotion": call emotion_mapping.classify_passages (loads the emotion model, ONE batch), write detected_emotion and expressiveness into each job_chunks row, yield an "emotion" event summarising label counts, THEN request the TTS model. The ModelManager guarantees the emotion model is unloaded before TTS loads; do not unload manually.
2. For modes calm/normal/expressive skip the emotion stage entirely (the emotion model must not be loaded).
3. Use emotion_mapping.resolve_expressiveness for each passage; load the user override map through get_emotion_map(settings_service).
4. Never log passage text beyond 40 characters; log label and expressiveness per passage at DEBUG.
DEBUGGING:
# print(f"[DEBUG] passage {i}: emotion={label} expr={expr:.2f}")
OFFLINE DOCKER TEST CASES:
- Auto mode with fake engines: model events are exactly: load emotion, unload emotion, load tts (in this order).
- Modes calm/normal/expressive produce no emotion model events.
- Chunk rows contain detected_emotion for auto jobs and NULL for fixed-mode jobs.
- Input "Great news! I am so sad." yields joy then sadness with the fake classifier and different amplitudes in the fake TTS output.

## EXTEND: src/voxclone/ui/screens/text_to_voice.py
PROMPT FOR LLM IMPLEMENTATION:
1. S-22: add "Auto (detect from the text)" as the FIRST and default choice before Calm / Normal / Expressive.
2. S-23 (Auto only): before creating the job, split the text, call classify_passages, and show a table with columns #, Passage (first 60 characters), Emotion, Expressiveness; then dropdown "Continue", "Change emotion" (return to S-22), "Cancel". The job re-runs classification inside the pipeline; this is cheap because the emotion model is still resident under keep_warm.
3. During the job show the loading badge for the emotion model and the swap banner "Freeing emotion model, loading voice model".
DEBUGGING:
# print(f"[DEBUG] preview emotions={[r.label for r in results]}")
OFFLINE DOCKER TEST CASES:
- (pexpect, fake) Auto mode shows the preview table with one row per passage.
- "Change emotion" returns to S-22; "Cancel" creates no job row.
- Choosing Normal skips the table and never loads the emotion engine.

## EXTEND: src/voxclone/cli.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add "auto" to --emotion choices of `speak` and make it the new default; add --show-emotions flag that prints the detected-emotion table before generating.
DEBUGGING:
# print(f"[DEBUG] cli speak emotion={emotion}")
OFFLINE DOCKER TEST CASES:
- `speak --text "Hello!" --emotion auto --save` exits 0 under the fake engine.
- `--emotion shouting` exits 1 with a usage error.

## EXTEND: src/voxclone/services/settings_service.py
PROMPT FOR LLM IMPLEMENTATION:
1. Accept one OPTIONAL extra key "emotion_map": a dict label -> float in [0.25, 1.0] for labels in EMOTION_LABELS; it is NOT part of DEFAULT_SETTINGS (the app_settings table still has nine default rows) and reading it when unset returns None.
2. reset_defaults() also deletes "emotion_map".
DEBUGGING:
# print(f"[DEBUG] emotion_map override={value}")
OFFLINE DOCKER TEST CASES:
- set("emotion_map", {"joy": 0.9}) succeeds; {"joy": 2.0} and {"bogus": 0.5} raise VoxcloneError.
- After reset_defaults, get("emotion_map") is None.

## EXTEND: tests/integration/test_text_pipeline.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add auto-mode tests: event stage order includes "emotion" before "loading_model"; model_events order (emotion load, emotion unload, tts load); chunk detected_emotion values; failure in the emotion engine maps to a VoxcloneError and the job is "failed" with no TTS load recorded.
DEBUGGING:
# print(f"[DEBUG] model events={[(e.action, e.model_key) for e in events]}")
OFFLINE DOCKER TEST CASES:
- The handoff order assertion fails if the TTS model is loaded before the emotion model is unloaded.

## EXTEND: tests/unit/test_model_manager.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add a regression test for the emotion -> tts handoff: peak number of simultaneously loaded engines is 1, and total unloads equal loads minus resident count.
DEBUGGING:
# print(f"[DEBUG] peak loaded engines={peak}")
OFFLINE DOCKER TEST CASES:
- The test passes with keep_warm True and False.
EOF

echo "====================================================="
echo "Milestone P3 Seeded Successfully!"
echo "NEXT STEPS:"
echo "1. Provide the seeded files AND docs/seed_extensions/P3_extensions.md to generate the code."
echo "2. Run offline tests: 'python -m pytest tests/ -v -m \"not gpu\"' or 'docker compose -f docker-compose.test.yml run --rm tests make test'."
echo "3. For local GPU smoke test: 'docker compose run --rm voxclone pytest -m gpu'."
echo "   For CPU / AMD Radeon APU execution: set VOXCLONE_DEVICE=cpu or use docker-compose.cpu.yml."
echo "   Notice: DistilRoBERTa emotion classification runs efficiently on CPU (~600 MB RAM)."
echo "4. Run 'git add . && git commit -m \"feat: complete P3\"'"
echo "5. Merge and tag: 'git checkout main && git merge --no-ff milestone/p3-emotion && git tag p3-done'"
echo "6. Execute P4.sh"
echo "====================================================="
