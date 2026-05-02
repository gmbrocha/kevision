# ScopeLedger Architecture

Status: canonical high-level architecture as of 2026-05-02.

## Overview

ScopeLedger is an application for turning drawing revision packages into
reviewable change evidence and deliverables. It is organized as an application
layer plus a cloud-detection subsystem.

## Application Layer

The application layer owns:

- package intake and workspace state
- backend scan/populate/export workflows
- webapp and reviewer-facing surfaces
- deliverable/workbook shaping
- client workflow and review policy
- project-level security and deployment decisions

## Detection Subsystem

`CloudHammer_v2/` owns revision-cloud detection, eval, labeling, and training
policy. It is a subsystem/dependency, not the whole product.

The legacy `CloudHammer/` folder remains reference-only until code is audited
and imported into `CloudHammer_v2`.

## Data And Artifacts

- `revision_sets/` and `resources/`: source drawing packages and durable inputs
- `CloudHammer_v2/`: active eval-pivot detection workspace
- `backend/`: application scan/export services
- `webapp/`: application UI/review surface
- `runs/`, `outputs/`, and subsystem output folders: generated artifacts
- `docs/anchors/`: product references, examples, images, templates, and
  benchmark/reference files

## Boundary

Client-facing workflow ends at reviewable product evidence and exports.
CloudHammer_v2 ends at detection/eval/training outputs that the application can
consume. Deep YOLO mechanics belong in `CloudHammer_v2/docs/`, not root docs.
