"""
Enhanced election data loader with certification status tracking.

This module extends the base ElectionLoader with support for certification
status fields, quality checks, and certification filtering.

Files live in the repo under:
    elections/dim_elections.parquet
    elections/dim_swings.parquet
    elections/*.parquet | *.csv

Certificate-enabled fields:
    - certification_status: uncertified | certified | certified_with_caveats
    - certified_date: ISO date string
    - certified_by: String identifying who certified
    - audit_status: pending | in_progress | complete | flagged
    - caveat_notes: Human-readable notes
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from enum import Enum

import pandas as pd

from fdp.loaders.base import BaseLoader
from fdp.quality.checks import QualityReport, check_no_null_required

# Certification types
CertificationStatus = Literal["uncertified", "certified", "certified_with_caveats"]
AuditStatus = Literal["pending", "in_progress", "complete", "flagged"]

KNOWN_DATASETS = {
    "elections": "elections/dim_elections.parquet",
    "swings":    "elections/dim_swings.parquet",
}

ELECTION_REQUIRED_COLS = ["county", "year", "race", "dem_votes", "rep_votes"]
SWING_REQUIRED_COLS    = ["county", "race_a", "race_b", "dem_swing"]

# Certification fields added to all election records
CERTIFICATION_COLS = [
    "certification_status",
    "certified_date",
    "certified_by",
    "audit_status",
    "caveat_notes",
]


class ElectionLoaderEnhanced(BaseLoader):
    """
    Load county-level election results with certification status tracking.

    The loader automatically validates and filters election data based on
    certification status, audit status, and data quality.

    Examples::

        loader = ElectionLoaderEnhanced(repo)

        # Load all elections (including uncertified)
        all_elections = loader.load("elections")

        # Load only certified results
        certified = loader.load("elections", certification_status="certified")

        # Load elections pending audit
        pending = loader.load("elections", audit_status="in_progress")

        # Load custom dataset
        custom = loader.load("my_results.parquet")
    """

    def load(
        self,
        name: str,
        certification_status: CertificationStatus | None = None,
        audit_status: AuditStatus | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """
        Load election data with optional certification filtering.

        Args:
            name: Dataset name or path (e.g., "elections", "my_file.parquet")
            certification_status: Filter by certification status
            audit_status: Filter by audit status
            **kwargs: Additional arguments passed to pandas read functions

        Returns:
            DataFrame with election results and certification columns

        Raises:
            FileNotFoundError: If dataset not found
            ValueError: If dataset format unsupported
        """
        rel_path = KNOWN_DATASETS.get(name, f"elections/{name}")
        abs_path = self.path(rel_path)

        if abs_path.suffix == ".parquet":
            df = pd.read_parquet(abs_path, **kwargs)
        elif abs_path.suffix == ".csv":
            df = pd.read_csv(abs_path, **kwargs)
        else:
            raise ValueError(f"Unsupported election data format: {abs_path.suffix}")

        # Validate and apply filters
        self._check_quality(df, name)

        # Apply certification filters if specified
        if certification_status is not None:
            df = df[df["certification_status"] == certification_status]

        if audit_status is not None:
            df = df[df["audit_status"] == audit_status]

        return df.reset_index(drop=True)

    def filter_by_certification(
        self,
        df: pd.DataFrame,
        status: CertificationStatus,
    ) -> pd.DataFrame:
        """
        Filter election results by certification status.

        Args:
            df: Election results DataFrame
            status: Desired certification status

        Returns:
            Filtered DataFrame containing only matching records
        """
        if "certification_status" not in df.columns:
            raise ValueError("DataFrame missing 'certification_status' column")

        return df[df["certification_status"] == status].reset_index(drop=True)

    def filter_by_audit_status(
        self,
        df: pd.DataFrame,
        status: AuditStatus,
    ) -> pd.DataFrame:
        """
        Filter election results by audit status.

        Args:
            df: Election results DataFrame
            status: Desired audit status

        Returns:
            Filtered DataFrame containing only matching records
        """
        if "audit_status" not in df.columns:
            raise ValueError("DataFrame missing 'audit_status' column")

        return df[df["audit_status"] == status].reset_index(drop=True)

    def get_certification_summary(self, df: pd.DataFrame) -> dict:
        """
        Get summary statistics about certification status.

        Args:
            df: Election results DataFrame

        Returns:
            Dictionary with certification breakdown and statistics
        """
        if "certification_status" not in df.columns:
            raise ValueError("DataFrame missing 'certification_status' column")

        return {
            "total_records": len(df),
            "by_status": df["certification_status"].value_counts().to_dict(),
            "by_audit": df["audit_status"].value_counts().to_dict()
            if "audit_status" in df.columns
            else {},
            "with_caveats": len(df[df["caveat_notes"].notna()])
            if "caveat_notes" in df.columns
            else 0,
        }

    def list_available(self) -> list[str]:
        """List available election datasets."""
        elec_dir = self.repo.path / "elections"
        if not elec_dir.exists():
            return []
        return sorted(
            str(p.relative_to(self.repo.path))
            for p in elec_dir.iterdir()
            if p.is_file() and p.name != ".gitkeep"
        )

    def _validate(self, data: pd.DataFrame) -> QualityReport:
        """
        Validate election data quality.

        Checks include:
        - Required columns present
        - No null values in required fields
        - Valid certification status values
        - Consistent certification metadata
        """
        report = QualityReport()

        # Core election data validation
        if "county" in data.columns:
            check_no_null_required(data, ELECTION_REQUIRED_COLS, report)

        # Certification field validation
        self._check_certification_fields(data, report)

        return report

    def _check_certification_fields(self, data: pd.DataFrame, report: QualityReport) -> None:
        """
        Validate certification-related fields.

        Args:
            data: DataFrame to validate
            report: QualityReport to accumulate issues
        """
        # Check certification_status presence and values
        if "certification_status" in data.columns:
            valid_statuses = {"uncertified", "certified", "certified_with_caveats"}
            invalid = data[~data["certification_status"].isin(valid_statuses)]

            if len(invalid) > 0:
                report.add_issue(
                    "invalid_certification_status",
                    f"{len(invalid)} records have invalid certification_status values",
                    severity="warning",
                )

        # Check date consistency
        if "certification_status" in data.columns and "certified_date" in data.columns:
            certified = data[data["certification_status"] != "uncertified"]
            missing_dates = certified[certified["certified_date"].isna()]

            if len(missing_dates) > 0:
                report.add_issue(
                    "missing_certified_date",
                    f"{len(missing_dates)} certified records missing certified_date",
                    severity="warning",
                )

        # Check audit status values
        if "audit_status" in data.columns:
            valid_audits = {"pending", "in_progress", "complete", "flagged", None}
            invalid_audits = data[
                ~data["audit_status"].isin(valid_audits) & data["audit_status"].notna()
            ]

            if len(invalid_audits) > 0:
                report.add_issue(
                    "invalid_audit_status",
                    f"{len(invalid_audits)} records have invalid audit_status values",
                    severity="warning",
                )
