param(
    [ValidateSet("overmerge_rescue", "split_release", "candidate_review", "low_priority", "marker_fp", "marker_retained")]
    [string] $Queue = "overmerge_rescue"
)

$ErrorActionPreference = "Stop"

$CloudHammerRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$RepoRoot = Resolve-Path (Join-Path $CloudHammerRoot "..")
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Missing Python interpreter: $Python"
}

$RunRoot = Join-Path $CloudHammerRoot "runs\whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428"
$DataRoot = Join-Path $CloudHammerRoot "data"

switch ($Queue) {
    "overmerge_rescue" {
        $Tool = Join-Path $CloudHammerRoot "utilities\whole_cloud_split_reviewer.py"
        $Manifest = Join-Path $RunRoot "split_review_analysis\still_overmerged_candidates.jsonl"
        $ReviewLog = Join-Path $DataRoot "whole_cloud_split_reviews\whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428.still_overmerged_rescue.review.jsonl"
        $ToolArgs = @($Tool, "--manifest", $Manifest, "--review-log", $ReviewLog)
    }
    "split_release" {
        $Tool = Join-Path $CloudHammerRoot "utilities\whole_cloud_split_reviewer.py"
        $Manifest = Join-Path $RunRoot "release_v1\split_review_queue.jsonl"
        $ReviewLog = Join-Path $DataRoot "whole_cloud_split_reviews\whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428.release_v1.split_review.jsonl"
        $ToolArgs = @($Tool, "--manifest", $Manifest, "--review-log", $ReviewLog)
    }
    "candidate_review" {
        $Tool = Join-Path $CloudHammerRoot "utilities\whole_cloud_candidate_reviewer.py"
        $Manifest = Join-Path $RunRoot "release_v1\review_queue.jsonl"
        $ReviewLog = Join-Path $DataRoot "whole_cloud_candidate_reviews\whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428.release_v1.review.jsonl"
        $ToolArgs = @($Tool, "--manifest", $Manifest, "--review-log", $ReviewLog, "--order", "confidence_asc")
    }
    "low_priority" {
        $Tool = Join-Path $CloudHammerRoot "utilities\whole_cloud_candidate_reviewer.py"
        $Manifest = Join-Path $RunRoot "release_v1\low_priority_review_queue.jsonl"
        $ReviewLog = Join-Path $DataRoot "whole_cloud_candidate_reviews\whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428.low_priority.review.jsonl"
        $ToolArgs = @($Tool, "--manifest", $Manifest, "--review-log", $ReviewLog, "--order", "confidence_asc")
    }
    "marker_fp" {
        $Tool = Join-Path $CloudHammerRoot "utilities\whole_cloud_candidate_reviewer.py"
        $Manifest = Join-Path $RunRoot "marker_anchor_analysis_v1\marker_false_positive_review_queue.jsonl"
        $ReviewLog = Join-Path $DataRoot "whole_cloud_candidate_reviews\whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428.marker_fp.review.jsonl"
        $ToolArgs = @($Tool, "--manifest", $Manifest, "--review-log", $ReviewLog, "--order", "confidence_asc")
    }
    "marker_retained" {
        $Tool = Join-Path $CloudHammerRoot "utilities\whole_cloud_candidate_reviewer.py"
        $Manifest = Join-Path $RunRoot "marker_anchor_retained_review_v1\review_queue.jsonl"
        $ReviewLog = Join-Path $DataRoot "whole_cloud_candidate_reviews\whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428.marker_retained.review.jsonl"
        $ToolArgs = @($Tool, "--manifest", $Manifest, "--review-log", $ReviewLog, "--order", "confidence_asc")
    }
}

Push-Location $RepoRoot
try {
    & $Python @ToolArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
