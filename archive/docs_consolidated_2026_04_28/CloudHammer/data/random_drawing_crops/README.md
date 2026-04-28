# Random Drawing Crops

This folder contains a random audit set for checking GPT behavior on ordinary
drawing-area crops.

## What This Is

- `200` random crops
- `1024 x 1024` pixels each
- sampled from drawing pages across revision sets
- avoids the most likely title block/header/footer regions
- does not use cloud detection to choose crops

The point is to get a mostly natural mix of cloud and non-cloud drawing areas,
not a curated cloud-positive training set.

## Files

- `images/`: original random crop images
- `manifest.jsonl`: crop metadata
- `review_sheet.csv`: blank human quick-review sheet
- `api_inputs/`: compressed images sent to GPT
- `api_predictions/predictions.jsonl`: raw GPT responses
- `gpt_labels/`: GPT YOLO labels
- `gpt_review/`: overlay images showing GPT boxes
- `gpt_quick_review.csv`: GPT prediction summary with blank human review columns

## GPT Run Summary

GPT prelabel run:

- model: `gpt-5.4`
- processed: `200`
- failed: `0`
- GPT said no cloud: `186`
- GPT said cloud: `14`

Accepted GPT box counts:

- `0` boxes: `187` crops
- `1` box: `11` crops
- `2` boxes: `1` crop
- `3` boxes: `1` crop

Accepted box confidence range:

- min: `0.67`
- max: `0.98`
- average: `0.905`

## Quick Review Plan

Open `gpt_quick_review.csv` and the `gpt_review/` overlays.

For each crop, fill `human_quick_label` with something simple:

- `positive`
- `negative`
- `unsure`

Use `human_notes` only when useful, for example:

- false positive
- missed faint cloud
- title block slipped in
- dense repeated detail
- good GPT hit
