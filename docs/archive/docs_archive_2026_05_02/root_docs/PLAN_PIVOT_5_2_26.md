# CloudHammer Model vs Pipeline Handoff

## Current Concern

We may have spent significant effort building a strong company-specific detection pipeline, but it is not yet clear how much of the intelligence lives inside the trained model versus how much lives in surrounding pipeline logic.

The immediate goal is to clarify exactly what has been learned by the model and what has been handled procedurally after detection. Once that is clear, we can decide how to move useful pipeline logic into the model training process, either directly through better labels/training data or indirectly through staged models and post-processing.

This is not necessarily a failure. It may simply mean CloudHammer currently has a strong domain-specific pipeline, while the desired long-term direction is a model that directly detects revision cloud motifs with less reliance on downstream shortcut logic.

## Working Hypothesis

The model may not have shortcut learning baked in as badly as initially feared.

Reason: triangle-based split logic and other procedural rules may have been added after the detector rather than being present in the detector's training labels or inputs. If true, the model was not necessarily trained to rely on triangles, revision markers, or pipeline-derived hints. Instead, the pipeline may have been using those cues after model inference to organize, split, filter, or interpret detections.

This needs to be verified by reviewing the actual training dataset, label classes, model inputs, training config, and inference pipeline order.

## Key Question

What work has been done by the model itself, and what work has been done by the surrounding pipeline?

### Model-side work means

The model directly learned something because it was present in the training images and labels.

Examples:

* A YOLO model trained on labeled `cloud_motif` bounding boxes.
* The model seeing visual examples of clouds during training.
* The model learning line thickness, shape, texture, or repeated cloud-chain structure from labeled examples.
* The model learning from hard negatives if they were included as no-label images in the training set.

### Pipeline-side work means

The code around the model performed logic before or after the model prediction.

Examples:

* Rasterizing blueprint PDFs into page images.
* Extracting ROIs from pages.
* Using delta images to find changed regions.
* Using revision triangles or markers to split, group, or filter regions.
* Cropping likely areas before sending them to the model.
* Merging nearby detections.
* Filtering detections by geometry, confidence, proximity, or page metadata.
* Exporting final results to Excel or another deliverable.

## Important Distinction

If the triangle logic was only used after the detector, then the model may not have learned triangles as a shortcut.

If triangle logic was used to choose which crops were included in the training data, then it may have indirectly shaped the model's training distribution.

That distinction matters.

For example:

* If training positives were mostly crops near revision triangles, the model may learn visual context around triangle-adjacent areas even if triangles were not labeled.
* If training negatives excluded triangle-heavy no-cloud areas, the model may not learn to reject triangles well.
* If the model was only trained on crops already selected by a triangle/delta heuristic, it may perform well inside that pre-filtered world but less well on whole pages or broader candidate regions.

## Immediate Verification Checklist

Ask the agent to inspect and report the following:

1. What model architecture and task were used?

   * YOLOv8
   * detection vs segmentation
   * classes trained
   * image size
   * training config

2. What exact labels were used for training?

   * class names
   * class IDs
   * whether only `cloud_motif` was labeled
   * whether triangles, markers, sheets, notes, or other cues were labeled

3. What exact image set was used for training?

   * source directory
   * train/val split file or YAML
   * number of train images
   * number of validation images
   * whether validation is real-only
   * whether any crops from the same pages appear in both train and val

4. How were training images/crops selected?

   * random page crops
   * delta-based ROIs
   * marker/triangle-based ROIs
   * manually curated crops
   * OpenAI prelabel-assisted crops
   * reviewed YOLO labels only

5. Did triangle or revision-marker logic affect training data selection?

   * before model training
   * during label creation
   * only after inference
   * not at all

6. What happens during inference?

   * page rasterization
   * ROI extraction
   * model prediction
   * post-processing
   * triangle/marker splitting
   * grouping/merging
   * filtering
   * export

7. What part of the current pipeline would fail if the detector was run alone on a full page?

   * false positives
   * missed faint clouds
   * wrong grouping
   * too many overlapping boxes
   * poor confidence separation
   * inability to associate clouds with revision markers

## Near-Term Plan

### Phase 1: Audit What Already Exists

Before changing strategy, inspect the current model and pipeline.

Deliverable from agent:

* list of trained model files
* list of training data directories
* dataset YAML/config
* class names
* train/val image counts
* label counts
* how train/val split was created
* whether crops from same source pages leaked across train/val
* exact inference order
* where triangle/marker logic enters the pipeline

### Phase 2: Freeze a Real Full-Page Eval Set

Create a small but honest real-only evaluation set using full, uncropped blueprint pages/diagrams.

This is the move: full-page eval tests the actual deployment problem instead of only testing preselected crops.

Rules:

* no synthetic data
* no training use
* no prelabel tuning
* no threshold tuning except final reporting
* no crops, tiles, or ROIs from these pages enter training
* preferably split by full page or drawing set, not random crop
* label every true cloud on the selected full pages as carefully and completely as possible
* include empty label files for true no-cloud pages

The frozen full-page set should include:

* full pages with bold easy clouds
* full pages with faint thin clouds
* full pages with partial/clipped clouds
* full pages with dense-linework clouds
* full pages with triangles but no clouds
* full pages with cloud-like non-cloud linework
* full boring no-cloud pages

Evaluation should compare predictions back against full-page ground truth.

Training and inference may still use crops, tiles, or ROIs, but the evaluation truth should remain full-page. The pipeline can tile/crop full pages during inference and then map detections back to full-page coordinates for scoring.

This allows separate evaluation of:

* model-only behavior: YOLOv8 run across full-page tiles and merged back to page coordinates
* pipeline behavior: the full CloudHammer pipeline including ROI extraction, post-processing, grouping, filtering, and marker/triangle logic

Both should be compared against the same frozen full-page labels.

### Phase 3: Run the Natural Data Dry

Use all allowed non-holdout real data to improve the model.

Focus areas:

* more reviewed positive cloud labels
* more hard negatives
* better no-cloud page/crop coverage
* faint/thin cloud examples
* partial edge cases
* dense geometry cases

### Phase 4: Decide What Pipeline Logic Should Become Training Signal

Useful pipeline discoveries should be translated into training data where possible.

Examples:

* If triangle-adjacent areas caused false positives, include them as hard negatives.
* If delta-based regions find faint clouds, label those clouds directly.
* If certain shapes confuse the model, add those as hard negatives.
* If grouping logic identifies cloud fragments, label complete cloud extents more consistently.

The goal is not necessarily to remove all pipeline logic. The goal is to make the model better at the core visual task.

### Phase 5: Synthetic Data Later

Synthetic data should come after the real-only baseline and frozen eval exist.

Best synthetic direction:

* use real blueprint backgrounds
* use tilemap/bitmask-style procedural cloud topology
* ideally use real cloud-chain fragments or carefully matched rendered fragments
* generate closed cloud contours
* degrade with realistic scan/CAD artifacts
* use synthetic only in training
* keep validation/test real-only

## Current Strategic View

This project may be best understood as two related but different goals:

1. Current consulting goal: build a reliable detector/pipeline for this client/company's drawing universe.
2. Future product goal: build a more general revision-cloud detection system across many drawing sources.

The current work may still be extremely valuable even if it is not yet general. It may be a strong client-specific specialist and a foundation for the later general system.

## GPT-Assisted Label Bootstrapping Plan

GPT-5.5 is currently being used to prelabel crops for human review. This has been highly useful because it can identify many cloud motifs accurately and reduce the amount of fully manual labeling required.

The goal is to reduce human review time without allowing automated label errors to become permanent ground truth.

### Core Idea

Use GPT-assisted labeling as a bootstrapping loop:

1. GPT prelabels candidate crops.
2. Human reviews a subset or priority queue of labels.
3. Reviewed labels become trusted training data.
4. YOLOv8 trains on the trusted set.
5. The trained model predicts on additional unlabeled crops.
6. GPT reviews, corrects, or regenerates labels for uncertain/model-disagreed cases.
7. Human reviews the most important or most ambiguous cases.
8. Repeat while measuring performance on a frozen real-only evaluation set.

### Important Guardrail

GPT labels should not automatically become permanent ground truth without some confidence strategy, disagreement check, or sampled human audit.

The risk is label drift: repeated automated relabeling can reinforce early mistakes and make the training set cleaner-looking but less true.

### Safer Use Pattern

Use GPT and YOLO together as a triage system:

* If GPT and YOLO agree strongly, send to a low-priority or sample-audited review path.
* If GPT finds a cloud YOLO missed, send to human review as a likely new positive.
* If YOLO finds a cloud GPT rejects, send to human review as a disagreement case.
* If both reject the crop, treat it as a likely negative, but periodically audit samples.
* If confidence is low, weird, faint, clipped, or dense, prioritize for human review.

### Evaluation Requirement

Every loop must be judged against a frozen real-only holdout set.

Synthetic data, GPT-generated labels, and model-generated labels should not enter the frozen eval set.

The key measurement is not only whether validation metrics improve, but whether real-world behavior improves:

* better recall on faint clouds
* fewer false positives on triangles, arcs, dense linework, title blocks, and tables
* better handling of partial/clipped clouds
* better confidence separation between real clouds and confusing non-clouds

### Practical Goal

The purpose is not to eliminate human review. The purpose is to move the human from full manual labeling into high-value arbitration.

Human time should be spent mostly on:

* disagreements
* faint or ambiguous clouds
* hard negatives
* representative samples from auto-accepted batches
* frozen eval labeling

This can turn manual review from a grind into a targeted QA process.

## Synthetic Data Plan

Synthetic data should come only after we have fully exploited the natural data and established a real-only evaluation baseline.

The plan is to create semi-random synthetic revision clouds using strict procedural grammar, similar to a tilemap/autotile system.

Core idea:

* Start with real non-cloud blueprint backgrounds.
* Generate valid closed cloud shapes using constrained topology rather than freeform random drawing.
* Treat cloud-chain pieces like legal tile sections: horizontals, verticals, inner corners, outside corners, and orientation-specific transitions.
* Use neighbor rules so each section can only connect to valid adjacent sections.
* Avoid illegal dangling ends except when intentionally creating partial or edge-clipped clouds.
* Prefer shape-first generation: create a rough closed footprint first, then walk/render the cloud chain around that perimeter.
* Add controlled dents, notches, long skinny shapes, large clouds, small clouds, and partial clipped clouds to increase shape diversity.
* Render the cloud perimeter using realistic company-specific cloud-chain fragments or closely matched synthetic fragments.
* Degrade the rendered clouds to match real blueprint conditions: line-weight variation, opacity variation, scan noise, blur, broken gaps, compression artifacts, overlap with existing plan lines, and slight placement/jitter irregularity.
* Keep synthetic data out of validation and test sets.

The goal is not to replace real clouds. The goal is to fill missing shape and placement diversity after the natural dataset becomes saturated.

Synthetic examples should be treated as training-only augmentation. Real-only holdouts remain the source of truth for evaluation.

## Open Questions

* What exactly was the model trained on?
* Did triangle/marker logic influence training data selection?
* Are train and validation split by crop, page, PDF, or drawing set?
* How much performance comes from YOLO detection alone?
* How much performance comes from ROI extraction and post-processing?
* Can the model run directly on full pages or large tiles?
* What hard negatives are currently included?
* Do current validation metrics reflect real deployment behavior?
* What should the first frozen eval set contain?
