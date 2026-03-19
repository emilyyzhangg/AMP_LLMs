"""
Persistence service for intermediate pipeline state.

Saves research and annotation results to disk for crash resilience
and resumability. All writes are atomic (write to .tmp, then rename).
"""

import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.models.job import now_pacific

from app.models.research import ResearchResult

logger = logging.getLogger("agent_annotate.persistence")


class PersistenceService:
    """Manages disk I/O for intermediate pipeline state."""

    def __init__(self, results_dir: Path):
        self._results_dir = results_dir

    # --- Research ---

    def _research_dir(self, job_id: str) -> Path:
        return self._results_dir / "research" / job_id

    def init_research_dir(
        self,
        job_id: str,
        nct_ids: list[str],
        version_stamp: dict,
        config_snapshot: dict,
    ) -> Path:
        """Create research directory and write _meta.json."""
        rdir = self._research_dir(job_id)
        rdir.mkdir(parents=True, exist_ok=True)
        self._cleanup_tmp_files(rdir)

        meta = {
            "job_id": job_id,
            "git_commit_full": version_stamp.get("git_commit_full", "unknown"),
            "config_hash": version_stamp.get("config_hash", ""),
            "created_at": now_pacific().strftime("%Y-%m-%d %H:%M:%S PT"),
            "nct_ids": nct_ids,
            "total_trials": len(nct_ids),
            "config_snapshot": config_snapshot,
        }
        meta_path = rdir / "_meta.json"
        if not meta_path.exists():
            self._atomic_write(meta_path, meta)
        return rdir

    def save_research(
        self, job_id: str, nct_id: str, results: list[ResearchResult]
    ) -> Path:
        """Atomically save research results for a single trial."""
        rdir = self._research_dir(job_id)
        path = rdir / f"{nct_id}.json"
        data = {
            "nct_id": nct_id,
            "completed_at": now_pacific().strftime("%Y-%m-%d %H:%M:%S PT"),
            "results": [r.model_dump() for r in results],
        }
        self._atomic_write(path, data)
        logger.debug(f"Saved research for {nct_id} -> {path}")
        return path

    def load_research(self, job_id: str, nct_id: str) -> Optional[list[ResearchResult]]:
        """Load research results for a single trial, or None if not found."""
        path = self._research_dir(job_id) / f"{nct_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return [ResearchResult(**r) for r in data.get("results", [])]
        except Exception as e:
            logger.warning(f"Failed to load research for {nct_id}: {e}")
            return None

    def load_research_meta(self, job_id: str) -> Optional[dict]:
        """Load _meta.json for a research directory."""
        path = self._research_dir(job_id) / "_meta.json"
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load research meta for {job_id}: {e}")
            return None

    def get_completed_research(self, job_id: str) -> set[str]:
        """Return set of nct_ids that have completed research on disk."""
        rdir = self._research_dir(job_id)
        if not rdir.exists():
            return set()
        completed = set()
        for f in rdir.iterdir():
            if f.suffix == ".json" and f.name != "_meta.json" and not f.name.endswith(".tmp"):
                completed.add(f.stem)
        return completed

    def research_exists(self, job_id: str) -> bool:
        """Check if research directory with meta exists for this job."""
        return (self._research_dir(job_id) / "_meta.json").exists()

    # --- Annotations ---

    def _annotations_dir(self, job_id: str) -> Path:
        return self._results_dir / "annotations" / job_id

    def init_annotations_dir(self, job_id: str) -> Path:
        """Create annotations directory."""
        adir = self._annotations_dir(job_id)
        adir.mkdir(parents=True, exist_ok=True)
        self._cleanup_tmp_files(adir)
        return adir

    def save_annotation(self, job_id: str, nct_id: str, trial_output: dict) -> Path:
        """Atomically save annotation result for a single trial."""
        adir = self._annotations_dir(job_id)
        path = adir / f"{nct_id}.json"
        self._atomic_write(path, trial_output)
        logger.debug(f"Saved annotation for {nct_id} -> {path}")
        return path

    def load_annotation(self, job_id: str, nct_id: str) -> Optional[dict]:
        """Load annotation result for a single trial."""
        path = self._annotations_dir(job_id) / f"{nct_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load annotation for {nct_id}: {e}")
            return None

    def get_completed_annotations(self, job_id: str) -> set[str]:
        """Return set of nct_ids that have completed annotations on disk."""
        adir = self._annotations_dir(job_id)
        if not adir.exists():
            return set()
        completed = set()
        for f in adir.iterdir():
            if f.suffix == ".json" and not f.name.endswith(".tmp"):
                completed.add(f.stem)
        return completed

    # --- Resume validation ---

    def validate_resume(self, job_id: str, current_commit: str) -> "ResumeValidation":
        """Validate whether a job can be safely resumed."""
        from app.models.resume import ResumeValidation

        meta = self.load_research_meta(job_id)
        if not meta:
            return ResumeValidation(
                can_resume=False,
                commit_match=False,
                original_commit="",
                current_commit=current_commit,
                config_match=False,
                research_completed=0,
                research_total=0,
                annotations_completed=0,
                warnings=["No research data found for this job"],
            )

        original_commit = meta.get("git_commit_full", "unknown")
        commit_match = original_commit == current_commit

        from app.services.config_service import config_service
        current_config_hash = config_service.get_hash()
        config_hash = meta.get("config_hash", "")
        config_match = config_hash == current_config_hash

        research_completed = len(self.get_completed_research(job_id))
        research_total = meta.get("total_trials", 0)
        annotations_completed = len(self.get_completed_annotations(job_id))

        warnings = []
        if not commit_match:
            warnings.append(
                f"Git commit mismatch: research was done at {original_commit[:8]}, "
                f"current is {current_commit[:8]}"
            )
        if not config_match:
            warnings.append("Config has changed since research was performed")

        return ResumeValidation(
            can_resume=True,
            commit_match=commit_match,
            original_commit=original_commit,
            current_commit=current_commit,
            config_match=config_match,
            research_completed=research_completed,
            research_total=research_total,
            annotations_completed=annotations_completed,
            warnings=warnings,
        )

    # --- Job state ---

    def save_job_state(self, job_id: str, job_data: dict) -> None:
        """Persist job state to disk. Called after each trial and status change."""
        jobs_dir = self._results_dir / "jobs"
        jobs_dir.mkdir(exist_ok=True)
        path = jobs_dir / f"{job_id}.json"
        with open(path, "w") as f:
            json.dump(job_data, f, indent=2, default=str)

    def load_all_job_states(self) -> dict[str, dict]:
        """Load all persisted job states. Called on startup."""
        jobs_dir = self._results_dir / "jobs"
        if not jobs_dir.exists():
            return {}
        states = {}
        for path in jobs_dir.glob("*.json"):
            try:
                with open(path) as f:
                    states[path.stem] = json.load(f)
            except Exception:
                pass
        return states

    # --- Internal helpers ---

    @staticmethod
    def _atomic_write(path: Path, data: dict) -> None:
        """Write JSON atomically: write to .tmp, then rename."""
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.rename(tmp_path, path)

    @staticmethod
    def _cleanup_tmp_files(directory: Path) -> None:
        """Remove orphaned .tmp files from a directory."""
        for f in directory.iterdir():
            if f.name.endswith(".tmp"):
                try:
                    f.unlink()
                    logger.debug(f"Cleaned up orphaned tmp file: {f}")
                except OSError:
                    pass
